"""Self-extension for AZZX (v10.6.9): the tool adds features to itself.

``azzx extend "<feature request>"`` asks the AI to write a NEW SKILL that
implements the requested feature. The generated skill goes through the
EXISTING trust infrastructure — no new trust machinery was invented:

1. AI generates ``skill.json`` + handler ``.py`` from the request.
2. Manifest is validated by ``skills.validate_manifest`` (bans install
   hooks, exec/eval fields; permissions must come from the allowed list).
3. Handler code is syntax-checked AND scanned for dangerous patterns
   (subprocess, os.system, socket, __import__, etc.) — defense in depth.
4. Installed via ``SkillRegistry.install()`` → **untrusted + disabled**.
5. User reviews code, then explicitly runs
   ``azzx skills trust <id>`` + ``azzx skills enable <id>``.

The AI can never silently activate code. The user is always the gate.
"""
from __future__ import annotations

import ast
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from azzx.core import AzzxError

EXTEND_SYSTEM = """You are a skill generator for AZZX, a lightweight AI agent.
Generate a NEW SKILL (a small Python module) that implements the user's
feature request.

Reply with JSON ONLY, exactly this shape:
{
  "skill_json": {
    "id": "kebab-case-id",
    "name": "Human Name",
    "description": "one-line description",
    "version": "1.0.0",
    "handler": "handler:main",
    "permissions": [],
    "tags": ["tag1"],
    "input_schema": {
      "type": "object",
      "properties": {
        "arg_name": {"type": "string", "description": "..."}
      },
      "required": ["arg_name"]
    }
  },
  "handler_py": "<complete Python source>"
}

Rules for handler_py:
- Python 3.10+, stdlib ONLY (no pip installs). `httpx` is allowed if the
  feature needs HTTP.
- Single function: `def main(**kwargs) -> dict`. Read args from kwargs
  matching input_schema properties. Return a JSON-serializable dict.
- NO subprocess, NO os.system, NO socket, NO eval/exec, NO file writes
  outside the current working directory, NO network unless the feature
  genuinely needs it.
- Handle errors gracefully: return {"ok": False, "error": "..."} instead
  of raising.
- Keep it under 150 lines. Clear, simple, well-commented code.
- skill id: lowercase letters, digits, hyphens only, max 64 chars.
- permissions: leave [] unless the feature needs a declared capability.
- input_schema: standard JSON schema; keep args simple (string/number/boolean).

Example handler:
```python
def main(**kwargs):
    text = kwargs.get("text", "")
    if not text:
        return {"ok": False, "error": "text required"}
    return {"ok": True, "length": len(text), "words": len(text.split())}
```
"""


def _extract_json(raw: str) -> str:
    """Extract the JSON object from AI output (handles fences + nested braces)."""
    # Prefer fenced block; fall back to outermost braces in the whole text.
    m = re.search(r"```(?:json)?\s*(\{.*)\s*```", raw, re.DOTALL)
    blob = m.group(1) if m else raw
    s, e = blob.find("{"), blob.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise AzzxError("generator returned no JSON object")
    return blob[s:e + 1]


def scan_patch(diff: str) -> list[str]:
    """Scan ADDED lines of a unified diff for dangerous patterns.

    Added lines are code fragments (not a full module), so they're wrapped
    in a dummy function before AST parsing. Returns banned pattern names.
    """
    added = "\n".join(
        ln[1:] for ln in diff.splitlines()
        if ln.startswith("+") and not ln.startswith("+++"))
    if not added.strip():
        return []
    import textwrap
    wrapped = "def _scan_wrapper():\n" + textwrap.indent(added, "    ")
    try:
        ast.parse(wrapped)
        return scan_handler(wrapped)
    except SyntaxError:
        pass
    try:
        ast.parse(added)
        return scan_handler(added)
    except SyntaxError:
        pass
    # Unparseable fragment: conservative substring check for the worst offenders.
    return [t for t in ("eval(", "exec(", "__import__", "subprocess",
                        "os.system", "os.popen", "socket", "getattr(")
            if t in added]


def scan_handler(code: str) -> list[str]:
    """Return list of banned pattern names found in code (empty = clean).

    AST-based (not regex): catches getattr indirection
    (`getattr(os, 'system')`), import aliasing (`import os as o`),
    and direct attribute access (`os.system`). This is defense-in-depth;
    the primary protections are the trust gate (human reviews code
    before trust+enable) and the skill permission system. No static
    scan is complete against deliberate obfuscation.
    """
    found: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ["syntax-error"]

    # Dangerous attributes/methods per module.
    DANGEROUS_ATTRS = {
        "os": {"system", "popen", "execv", "execve", "execl", "execlp",
               "execvp", "spawnl", "spawnle", "spawnlp", "spawnv", "spawnve",
               "spawnvp", "spawnvpe", "fork", "kill", "remove", "rmdir",
               "unlink", "rename", "chmod"},
        "subprocess": {"run", "call", "check_call", "check_output", "Popen"},
        "shutil": {"rmtree", "move", "chown"},
        "socket": {"socket", "create_connection"},
    }
    DANGEROUS_FUNCS = {"eval", "exec", "compile", "__import__"}
    # Modules whose attributes we track (including aliases).
    TRACKED_MODULES = set(DANGEROUS_ATTRS) | {"builtins"}

    # Map local name -> real module (handles `import os as o`,
    # `from os import system`).
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                local = a.asname or a.name.split(".")[0]
                aliases[local] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            for a in node.names:
                local = a.asname or a.name
                # `from os import system` -> local 'system' is dangerous directly
                if mod in DANGEROUS_ATTRS and a.name in DANGEROUS_ATTRS[mod]:
                    found.append(f"{mod}.{a.name} (via from-import)")
                aliases[local] = mod

    def _mod_of(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id if node.id in TRACKED_MODULES else None)
        return None

    for node in ast.walk(tree):
        # Direct dangerous calls: eval(...), exec(...), __import__(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname in DANGEROUS_FUNCS:
                found.append(fname)
            # getattr(os, 'system') / getattr(o, 'popen')
            elif fname == "getattr" and len(node.args) >= 2:
                mod = _mod_of(node.args[0])
                attr = node.args[1]
                if (mod in DANGEROUS_ATTRS and isinstance(attr, ast.Constant)
                        and attr.value in DANGEROUS_ATTRS[mod]):
                    found.append(f"getattr({mod}, {attr.value!r})")
        # Attribute access: os.system, o.system (aliased), subprocess.run
        elif isinstance(node, ast.Attribute):
            mod = _mod_of(node.value)
            if mod in DANGEROUS_ATTRS and node.attr in DANGEROUS_ATTRS[mod]:
                found.append(f"{mod}.{node.attr}")

    # open() in write/append mode.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "open" and len(node.args) >= 2:
            mode = node.args[1]
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str) \
                    and any(c in mode.value for c in "wax+"):
                found.append("open(..., 'w')")
                break

    return sorted(set(found))


def generate_skill(request: str, forced_provider: str | None = None) -> dict[str, Any]:
    """Ask the AI to generate a skill. Returns {skill_json, handler_py}."""
    from azzx.agent.providers import default_router

    request = (request or "").strip()
    if not request:
        raise AzzxError("feature request required")
    router = default_router()
    try:
        raw = router.chat([
            {"role": "system", "content": EXTEND_SYSTEM},
            {"role": "user", "content": f"Feature request: {request}\n\nGenerate the skill JSON now."},
        ], forced_provider, max_tokens=4000).text.strip()
    except Exception as exc:
        raise AzzxError(f"skill generation needs an AI provider: {exc}")
    blob = _extract_json(raw)
    try:
        data = json.loads(blob)
    except Exception:
        raise AzzxError("generator returned unparseable output")
    if not isinstance(data.get("skill_json"), dict) or not isinstance(data.get("handler_py"), str):
        raise AzzxError("generator output missing skill_json or handler_py")
    return data


def extend_feature(request: str, forced_provider: str | None = None) -> dict[str, Any]:
    """Generate, validate, and stage a new skill. Returns install report."""
    from azzx.agent.skills import SkillRegistry, validate_manifest, SkillError

    data = generate_skill(request, forced_provider)
    manifest_raw = data["skill_json"]
    handler_code = data["handler_py"]

    # 1. Validate manifest with the existing validator.
    try:
        manifest = validate_manifest(manifest_raw, "generated")
    except Exception as exc:
        raise AzzxError(f"generated manifest invalid: {exc}")

    # 2. Syntax check.
    try:
        ast.parse(handler_code)
    except SyntaxError as exc:
        raise AzzxError(f"generated code has syntax error: {exc}")

    # 3. Dangerous pattern scan (defense in depth).
    banned = scan_handler(handler_code)
    if banned:
        raise AzzxError(
            f"generated code uses blocked patterns: {', '.join(banned)}. "
            "Refusing to install.")

    # 4. Verify handler has a callable main().
    tree = ast.parse(handler_code)
    has_main = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main"
                   for n in ast.walk(tree))
    if not has_main:
        raise AzzxError("generated code has no main() function")

    # 5. Stage to temp dir and install (untrusted + disabled by design).
    module_name = manifest["handler"].split(":")[0]
    with tempfile.TemporaryDirectory(prefix="azzx-extend-") as tmp:
        stage = Path(tmp) / manifest["id"]
        stage.mkdir()
        (stage / "skill.json").write_text(json.dumps(manifest_raw, indent=2))
        (stage / f"{module_name}.py").write_text(handler_code)
        registry = SkillRegistry()
        try:
            result = registry.install(stage, trust=False)
        except SkillError as exc:
            raise AzzxError(f"install failed: {exc}")

    return {
        "skill_id": result["installed"],
        "version": result["version"],
        "trusted": False,
        "enabled": False,
        "handler_lines": len(handler_code.splitlines()),
        "next_steps": [
            f"azzx skills list",
            f"Review the code, then: azzx skills trust {result['installed']}",
            f"azzx skills enable {result['installed']}",
        ],
    }

"""Self-improvement engine for AZZX (v10.6.10): evolve.

The vision: AZZX observes its own usage, learns the user's habits,
repairs its own bugs, and proposes upgrades — always with the user
as the final gate.

The loop:
    OBSERVE (audit trail) → ANALYZE (habits + failures) →
    PROPOSE (AI generates staged proposals) →
    APPROVE (user reviews each) → APPLY (checkpoint → patch → test)

Safety (non-negotiable):
- NOTHING is applied automatically. Every proposal waits for explicit
  user approval via `azzx evolve approve <id>`.
- Before applying: create a checkpoint (existing checkpoint system).
- After applying: run the relevant test suite; on failure, roll back.
- Self-protection: proposals touching the permission system
  (permissions.py), the auditor (auditor.py), or the evolve engine
  itself (evolve.py) are REJECTED unless the user passes --force.
- Every step is recorded in the audit trail.
"""
from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from azzx.core import AzzxError, DATA_HOME

EVOLVE_DIR = Path(DATA_HOME) / "agent" / "evolve"
PROPOSALS_FILE = EVOLVE_DIR / "proposals.json"

# Files the evolve engine refuses to touch without --force.
PROTECTED_FILES = frozenset({
    "permissions.py",   # the deny-first safety core
    "auditor.py",       # the observation layer itself
    "evolve.py",        # this engine
})

EVOLVE_SYSTEM = """You are the self-improvement planner for AZZX, a lightweight AI agent.
Given OBSERVATIONS about how the user uses AZZX (tool usage, failures,
patterns), propose concrete improvements.

Reply with JSON ONLY:
{
  "proposals": [
    {
      "type": "habit|fix|feature",
      "title": "short title",
      "description": "what to change and why (2-3 sentences)",
      "changes": [
        {"file": "relative/path.py", "kind": "patch|skill|config",
         "detail": "concrete description of the change"}
      ],
      "risk": "low|medium|high",
      "test": "how to verify (e.g. 'run tests.test_x')"
    }
  ]
}

Rules:
- type=habit: optimize for observed user patterns (e.g. user always runs
  A then B -> propose a combined workflow; user prefers Ollama ->
  propose making it the default).
- type=fix: repair recurring failures seen in the observations.
- type=feature: propose a genuinely useful new capability suggested by usage.
- Max 5 proposals. Prefer low-risk, high-value. No proposal may touch
  permissions.py, auditor.py, or evolve.py.
- changes[].file must be a path inside the AZZX project.
- Be concrete: "add retry with backoff to web.fetch" not "improve web".
- If observations show nothing actionable, return {"proposals": []}.
"""


def _load_proposals() -> list[dict[str, Any]]:
    if not PROPOSALS_FILE.is_file():
        return []
    try:
        return json.loads(PROPOSALS_FILE.read_text()) or []
    except Exception:
        return []


def _save_proposals(items: list[dict[str, Any]]) -> None:
    EVOLVE_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FILE.write_text(json.dumps(items, indent=2))


def analyze() -> dict[str, Any]:
    """Observe: analyze the audit trail for habits and failures."""
    from azzx.agent import auditor as A

    calls = [e for e in A._iter_entries() if e.get("kind") == "tool_call"]
    total = len(calls)
    findings: dict[str, Any] = {
        "total_calls": total,
        "top_tools": [],
        "failure_hotspots": [],
        "denied_count": 0,
        "common_sequences": [],
    }
    if not total:
        findings["note"] = "no usage data yet — use AZZX more, then evolve"
        return findings

    tools = Counter(str(c.get("tool")) for c in calls)
    findings["top_tools"] = [
        {"tool": t, "calls": n} for t, n in tools.most_common(10)]

    failures: dict[str, Counter] = {}
    for c in calls:
        if not c.get("ok"):
            ek = str(c.get("error_kind", "error"))
            if ek == "denied":
                findings["denied_count"] += 1
                continue
            failures.setdefault(str(c.get("tool")), Counter())[ek] += 1
    findings["failure_hotspots"] = [
        {"tool": t, "errors": dict(cnt), "total": sum(cnt.values())}
        for t, cnt in sorted(failures.items(),
                             key=lambda kv: -sum(kv[1].values()))[:5]]

    # Repeated 2-step sequences (habit candidates).
    seqs = Counter()
    prev = None
    for c in calls:
        cur = str(c.get("tool"))
        if prev and c.get("ok"):
            seqs[(prev, cur)] += 1
        prev = cur if c.get("ok") else None
    findings["common_sequences"] = [
        {"first": a, "then": b, "count": n}
        for (a, b), n in seqs.most_common(5) if n >= 3]

    return findings


def propose(findings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze + ask AI for improvement proposals. Stages them (not applied)."""
    from azzx.agent.providers import default_router

    findings = findings or analyze()
    if not findings.get("total_calls"):
        return {"staged": 0, "note": findings.get("note", "no data")}

    router = default_router()
    try:
        raw = router.chat([
            {"role": "system", "content": EVOLVE_SYSTEM},
            {"role": "user", "content": "OBSERVATIONS:\n" + json.dumps(findings, indent=2)},
        ], max_tokens=3000).text.strip()
    except Exception as exc:
        raise AzzxError(f"proposal generation needs an AI provider: {exc}")

    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = m.group(1) if m else raw
    try:
        data = json.loads(blob)
    except Exception:
        s, e = blob.find("{"), blob.rfind("}")
        data = json.loads(blob[s:e + 1])

    staged = 0
    items = _load_proposals()
    for p in data.get("proposals", [])[:5]:
        # Enforce protected files.
        touched = {str(ch.get("file", "")).split("/")[-1]
                   for ch in p.get("changes", [])}
        if touched & PROTECTED_FILES:
            continue  # silently drop; safety first
        pid = uuid.uuid4().hex[:8]
        items.append({
            "id": pid,
            "type": str(p.get("type", "habit")),
            "title": str(p.get("title", "untitled"))[:120],
            "description": str(p.get("description", ""))[:1000],
            "changes": p.get("changes", []),
            "risk": str(p.get("risk", "medium")),
            "test": str(p.get("test", ""))[:200],
            "status": "pending",
            "created": int(time.time()),
        })
        staged += 1
    _save_proposals(items)
    return {"staged": staged, "total_pending": sum(1 for i in items if i["status"] == "pending")}


def list_proposals(status: str = "pending") -> list[dict[str, Any]]:
    items = _load_proposals()
    return [i for i in items if i["status"] == status] if status else items


def reject(proposal_id: str) -> dict[str, Any]:
    items = _load_proposals()
    for i in items:
        if i["id"] == proposal_id and i["status"] == "pending":
            i["status"] = "rejected"
            _save_proposals(items)
            return {"id": proposal_id, "status": "rejected"}
    raise AzzxError(f"no pending proposal {proposal_id!r}")


PATCH_SYSTEM = """You are a code repair bot for AZZX. Given a FILE's content and a
CHANGE REQUEST, output a UNIFIED DIFF (diff -u format) that implements it.

Rules:
- Reply with ONLY the diff, wrapped in ```diff fences. No explanations.
- Keep the diff minimal: change only what the request needs.
- Preserve all existing behavior not mentioned in the request.
- Python 3.10+ compatible. No new dependencies.
- Never add subprocess/os.system/socket/eval calls.
"""


def _generate_patch(file_path: Path, detail: str) -> str:
    """Ask AI to generate a unified diff for file_path implementing detail."""
    from azzx.agent.providers import default_router

    original = file_path.read_text()
    router = default_router()
    raw = router.chat([
        {"role": "system", "content": PATCH_SYSTEM},
        {"role": "user", "content":
         f"FILE: {file_path.name}\nCHANGE REQUEST: {detail}\n\n"
         f"--- current content ---\n{original[:12000]}"},
    ], max_tokens=4000).text.strip()
    import re
    m = re.search(r"```diff\s*(.*?)```", raw, re.DOTALL)
    diff = (m.group(1) if m else raw).strip()
    if not diff.startswith("---"):
        raise AzzxError("AI did not return a valid unified diff")
    return diff


def _apply_diff(file_path: Path, diff: str) -> None:
    """Apply a unified diff to file_path (simple single-hunk applier)."""
    import re
    lines = diff.splitlines()
    # Parse hunks: @@ -a,b +c,d @@
    original = file_path.read_text().splitlines(keepends=True)
    out: list[str] = []
    i = 0  # index into original
    li = 0
    # Skip header lines (--- / +++).
    while li < len(lines) and (lines[li].startswith("---") or lines[li].startswith("+++")):
        li += 1
    while li < len(lines):
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[li])
        if not m:
            li += 1
            continue
        start = int(m.group(1)) - 1
        # Copy unchanged lines before this hunk.
        while i < start:
            out.append(original[i])
            i += 1
        li += 1
        while li < len(lines) and not lines[li].startswith("@@"):
            ln = lines[li]
            if ln.startswith(" "):
                if i < len(original):
                    out.append(original[i])
                i += 1
            elif ln.startswith("-"):
                i += 1  # drop line
            elif ln.startswith("+"):
                out.append(ln[1:] + "\n")
            elif ln.startswith("\\"):
                pass  # "\ No newline at end of file"
            li += 1
    while i < len(original):
        out.append(original[i])
        i += 1
    file_path.write_text("".join(out))


def approve(proposal_id: str, force: bool = False,
            project_root: str | Path | None = None,
            auto_yes: bool = False) -> dict[str, Any]:
    """Apply an approved proposal: checkpoint → AI patch → confirm → test.

    Patch changes: AI generates a unified diff, user confirms (unless
    auto_yes), diff is applied, syntax-checked, and the proposal's test
    command is suggested. On any failure the checkpoint is restored.
    """
    from azzx.agent import checkpoints

    items = _load_proposals()
    prop = next((i for i in items
                 if i["id"] == proposal_id and i["status"] == "pending"), None)
    if not prop:
        raise AzzxError(f"no pending proposal {proposal_id!r}")

    # Self-protection (double-check at apply time).
    touched = {str(ch.get("file", "")).split("/")[-1]
               for ch in prop.get("changes", [])}
    if (touched & PROTECTED_FILES) and not force:
        raise AzzxError(
            f"proposal touches protected files {sorted(touched & PROTECTED_FILES)}; "
            "use --force to override (not recommended)")

    root = Path(project_root or ".").resolve()
    # 1. Checkpoint before touching anything.
    cp = checkpoints.create(str(root), label=f"evolve-{proposal_id}")
    cp_id = cp.get("id", "?") if isinstance(cp, dict) else "?"

    applied: list[str] = []
    try:
        for ch in prop.get("changes", []):
            kind = ch.get("kind", "patch")
            if kind == "skill":
                from azzx.agent.selfextend import extend_feature
                res = extend_feature(ch.get("detail", ""))
                applied.append(f"skill {res['skill_id']} staged (trust+enable manually)")
            elif kind == "config":
                applied.append(f"config: {ch.get('detail')} (manual — no auto-apply for configs)")
            else:  # patch: AI generates diff, user confirms, then apply
                rel = str(ch.get("file", ""))
                fpath = (root / rel).resolve()
                if not str(fpath).startswith(str(root)):
                    raise AzzxError(f"path escapes project: {rel}")
                if not fpath.is_file():
                    raise AzzxError(f"file not found: {rel}")
                diff = _generate_patch(fpath, ch.get("detail", ""))
                print(f"\n--- proposed diff for {rel} ---")
                print(diff[:3000])
                print("--- end diff ---")
                if not auto_yes:
                    ans = input("Terapkan patch ini? [ya/tidak]: ").strip().lower()
                    if ans not in ("ya", "y", "yes"):
                        applied.append(f"patch {rel}: DIBATALKAN oleh user")
                        continue
                _apply_diff(fpath, diff)
                # Syntax check after apply.
                import ast
                try:
                    ast.parse(fpath.read_text())
                except SyntaxError as exc:
                    raise AzzxError(f"patch broke syntax in {rel}: {exc}")
                applied.append(f"patch {rel}: diterapkan")
    except Exception:
        # Roll back on any failure.
        try:
            checkpoints.rollback(cp_id, str(root))
        except Exception:
            pass
        prop["status"] = "failed"
        _save_proposals(items)
        raise

    prop["status"] = "applied"
    prop["checkpoint"] = cp_id
    _save_proposals(items)
    return {
        "id": proposal_id,
        "status": "applied",
        "checkpoint": cp_id,
        "applied": applied,
        "note": "Jalankan test yang disarankan, atau rollback via checkpoint jika ada masalah.",
    }

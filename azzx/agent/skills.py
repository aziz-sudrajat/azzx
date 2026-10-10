"""Native skill registry for AZZX (v10.4).

A *skill* is a small, validated, permission-bound capability the agent can
discover and invoke through the normal tool pipeline:

- stable ``id``, human-readable ``description``, ``version``
- ``input_schema`` (JSON-schema subset) — arguments are validated *before*
  the handler runs
- ``handler`` — a ``module:function`` inside the skill directory
- declared ``permissions`` — enforced at execution time, like any tool

Trust model: freshly installed skills are **untrusted and disabled**.
A skill only becomes invokable after an explicit ``trust()`` *and*
``enable()``. Third-party code is never executed automatically.

Skills complement the raw plugin system (``azzx.plugins``): plugins register
arbitrary tools; skills are the stricter, schema-validated, trust-gated
layer. Each trusted+enabled skill is exposed to the agent as the registered
tool ``skill.<id>``, so workflows, the task queue, and multi-agent roles all
apply the same permission checks.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path
from typing import Any

from azzx.core import (
    AzzxError,
    DATA_HOME,
    PERMISSION_CAPABILITIES,
    REGISTRY,
    ToolSpec,
    load_json,
    require_permission,
    save_json,
    setup_homes,
)

SKILL_DIR = DATA_HOME / "skills"
MANIFEST_NAME = "skill.json"
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([.+-][A-Za-z0-9.+-]+)?$")
HANDLER_RE = re.compile(r"^[a-z_][a-z0-9_]*:[a-z_][a-z0-9_]*$")
_SCHEMA_TYPES = {"string", "integer", "number", "boolean", "array", "object", "null"}


class SkillError(AzzxError):
    """Skill registry failure (validation, trust, invocation)."""


def _validate_schema(schema: Any, where: str) -> dict[str, Any]:
    """Validate the JSON-schema subset used for skill input schemas."""
    if not isinstance(schema, dict):
        raise SkillError(f"{where}: input_schema must be an object")
    if schema.get("type", "object") != "object":
        raise SkillError(f"{where}: input_schema type must be 'object'")
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        raise SkillError(f"{where}: input_schema.properties must be an object")
    for pname, pspec in props.items():
        if not isinstance(pspec, dict):
            raise SkillError(f"{where}: property {pname!r} must be an object")
        ptype = pspec.get("type", "string")
        if ptype not in _SCHEMA_TYPES:
            raise SkillError(f"{where}: property {pname!r} has unknown type {ptype!r}")
        if "enum" in pspec and not isinstance(pspec["enum"], list):
            raise SkillError(f"{where}: property {pname!r} enum must be a list")
    required = schema.get("required") or []
    if not isinstance(required, list) or any(not isinstance(r, str) for r in required):
        raise SkillError(f"{where}: input_schema.required must be a list of strings")
    unknown_required = [r for r in required if r not in props]
    if unknown_required:
        raise SkillError(f"{where}: required {unknown_required} not in properties")
    return {
        "type": "object",
        "properties": {str(k): dict(v) for k, v in props.items()},
        "required": [str(r) for r in required],
        "additionalProperties": bool(schema.get("additionalProperties", True)),
    }


def validate_manifest(obj: dict[str, Any], source: str = "") -> dict[str, Any]:
    """Validate a skill.json manifest. Returns the normalized manifest."""
    if not isinstance(obj, dict):
        raise SkillError(f"Invalid skill manifest (not an object): {source}")
    sid = str(obj.get("id") or "").strip()
    if not ID_RE.match(sid):
        raise SkillError(f"Invalid skill id {sid!r}: ^[a-z][a-z0-9_-]{{0,63}}$")
    version = str(obj.get("version") or "").strip()
    if not VERSION_RE.match(version):
        raise SkillError(f"Invalid skill version {version!r}: expected semver like 1.0.0")
    handler = str(obj.get("handler") or "").strip()
    if not HANDLER_RE.match(handler):
        raise SkillError(
            f"Invalid skill handler {handler!r}: expected 'module:function' "
            "(e.g. 'handler:main', module file must live in the skill directory)"
        )
    permissions = obj.get("permissions") or []
    if not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions):
        raise SkillError("skill permissions must be a list of strings")
    unknown = [p for p in permissions if p not in PERMISSION_CAPABILITIES]
    if unknown:
        raise SkillError(
            f"Skill declares unknown permission(s) {unknown}. Allowed: {PERMISSION_CAPABILITIES}"
        )
    # Reject anything that smells like an install hook / code escape hatch.
    for banned in ("install_script", "shell", "postinstall", "command", "exec", "eval"):
        if banned in obj:
            raise SkillError(f"Manifest field not allowed: {banned}")
    tags = obj.get("tags") or []
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        raise SkillError("skill tags must be a list of strings")
    schema = _validate_schema(obj.get("input_schema") or {}, f"skill {sid!r}")
    return {
        "id": sid,
        "name": str(obj.get("name") or sid),
        "description": str(obj.get("description") or ""),
        "version": version,
        "handler": handler,
        "permissions": [str(p) for p in permissions],
        "tags": [str(t).strip().lower() for t in tags if str(t).strip()],
        "input_schema": schema,
        "trusted": bool(obj.get("trusted", False)),
        "enabled": bool(obj.get("enabled", False)),
    }


def validate_args(schema: dict[str, Any], args: Any) -> dict[str, Any]:
    """Validate invocation args against the skill's input schema."""
    if not isinstance(args, dict):
        raise SkillError("skill args must be a JSON object")
    props: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])
    for name in required:
        if name not in args:
            raise SkillError(f"missing required argument: {name!r}")
    if not schema.get("additionalProperties", True):
        for name in args:
            if name not in props:
                raise SkillError(f"unexpected argument: {name!r}")
    clean: dict[str, Any] = {}
    for name, value in args.items():
        if name not in props:
            clean[name] = value
            continue
        pspec = props[name]
        clean[name] = _coerce_value(name, value, pspec)
    return clean


def _coerce_value(name: str, value: Any, pspec: dict[str, Any]) -> Any:
    ptype = pspec.get("type", "string")

    def fail(why: str) -> SkillError:
        return SkillError(f"argument {name!r}: {why} (expected {ptype})")

    if value is None:
        if ptype == "null":
            return None
        raise fail("is null")
    if ptype == "string":
        if not isinstance(value, str):
            raise fail(f"got {type(value).__name__}")
    elif ptype == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise fail(f"got {type(value).__name__}")
    elif ptype == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise fail(f"got {type(value).__name__}")
    elif ptype == "boolean":
        if not isinstance(value, bool):
            raise fail(f"got {type(value).__name__}")
    elif ptype == "array":
        if not isinstance(value, list):
            raise fail(f"got {type(value).__name__}")
    elif ptype == "object":
        if not isinstance(value, dict):
            raise fail(f"got {type(value).__name__}")
    if "enum" in pspec and value not in pspec["enum"]:
        raise fail(f"{value!r} not in {pspec['enum']}")
    if isinstance(value, str):
        if "minLength" in pspec and len(value) < int(pspec["minLength"]):
            raise fail("too short")
        if "maxLength" in pspec and len(value) > int(pspec["maxLength"]):
            raise fail("too long")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in pspec and value < pspec["minimum"]:
            raise fail(f"below minimum {pspec['minimum']}")
        if "maximum" in pspec and value > pspec["maximum"]:
            raise fail(f"above maximum {pspec['maximum']}")
    return value


class SkillRegistry:
    """Discovers, validates, and invokes skills from the skill directory."""

    def __init__(self, root: str | Path | None = None) -> None:
        setup_homes()
        self.root = Path(root) if root is not None else SKILL_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths -----------------------------------------------------------
    def skill_path(self, skill_id: str) -> Path:
        if not ID_RE.match(skill_id):
            raise SkillError(f"Invalid skill id: {skill_id}")
        return self.root / skill_id

    def _manifest_path(self, skill_id: str) -> Path:
        return self.skill_path(skill_id) / MANIFEST_NAME

    def _read_manifest(self, skill_id: str) -> dict[str, Any]:
        path = self._manifest_path(skill_id)
        if not path.is_file():
            raise SkillError(f"Skill not found: {skill_id}")
        raw = load_json(path, {})
        return validate_manifest(raw, str(path))

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        save_json(self._manifest_path(manifest["id"]), manifest)

    # -- discovery ----------------------------------------------------------
    def list(self) -> list[dict[str, Any]]:
        result = []
        for d in sorted(self.root.iterdir() if self.root.exists() else []):
            if not d.is_dir():
                continue
            man = d / MANIFEST_NAME
            if not man.is_file():
                result.append({"id": d.name, "error": "missing skill.json"})
                continue
            try:
                result.append(self._read_manifest(d.name))
            except SkillError as exc:
                result.append({"id": d.name, "error": str(exc)})
        return result

    def find(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Keyword discovery over id / name / description / tags."""
        terms = [t.lower() for t in (query or "").split() if t.strip()]
        scored: list[tuple[int, dict[str, Any]]] = []
        for meta in self.list():
            if meta.get("error"):
                continue
            haystack = " ".join([
                meta["id"], meta["name"], meta["description"], *meta.get("tags", []),
            ]).lower()
            score = sum(2 if term in meta["id"].lower() else 1
                        for term in terms if term in haystack)
            if score or not terms:
                scored.append((score, meta))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        return [m for _, m in scored[: max(1, limit)]]

    # -- lifecycle ------------------------------------------------------------
    def install(self, source: str | Path, trust: bool = False) -> dict[str, Any]:
        """Install a skill from a local directory. Untrusted + disabled by default."""
        src = Path(source).expanduser().resolve()
        if not src.is_dir():
            raise SkillError(f"Skill source must be a directory: {src}")
        man_path = src / MANIFEST_NAME
        if not man_path.is_file():
            raise SkillError(f"Missing {MANIFEST_NAME} in {src}")
        manifest = validate_manifest(load_json(man_path, {}), str(man_path))
        module, _func = manifest["handler"].split(":")
        handler_src = src / f"{module}.py"
        if not handler_src.is_file():
            raise SkillError(f"Handler module missing: {handler_src.name}")
        dest = self.skill_path(manifest["id"])
        if dest.exists():
            raise SkillError(f"Skill already installed: {manifest['id']} (uninstall first)")
        shutil.copytree(
            src, dest,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".env", ".venv"),
        )
        # Re-validate after copy; fail closed.
        manifest = validate_manifest(load_json(dest / MANIFEST_NAME, {}), str(dest))
        manifest["trusted"] = bool(trust)
        manifest["enabled"] = False  # enabling is always a separate, deliberate step
        self._write_manifest(manifest)
        return {"installed": manifest["id"], "version": manifest["version"],
                "trusted": manifest["trusted"], "enabled": False}

    def uninstall(self, skill_id: str) -> bool:
        path = self.skill_path(skill_id)
        if not path.is_dir():
            return False
        shutil.rmtree(path)
        return True

    def trust(self, skill_id: str) -> dict[str, Any]:
        manifest = self._read_manifest(skill_id)
        manifest["trusted"] = True
        self._write_manifest(manifest)
        return {"id": skill_id, "trusted": True, "enabled": manifest["enabled"]}

    def untrust(self, skill_id: str) -> dict[str, Any]:
        manifest = self._read_manifest(skill_id)
        manifest["trusted"] = False
        manifest["enabled"] = False  # untrusting also disables
        self._write_manifest(manifest)
        return {"id": skill_id, "trusted": False, "enabled": False}

    def enable(self, skill_id: str) -> dict[str, Any]:
        manifest = self._read_manifest(skill_id)
        if not manifest["trusted"]:
            raise SkillError(
                f"Skill {skill_id!r} is not trusted. Review its code, then run "
                f"`azzx skills trust {skill_id}` before enabling."
            )
        manifest["enabled"] = True
        self._write_manifest(manifest)
        register_skill_tools(self)
        return {"id": skill_id, "trusted": True, "enabled": True}

    def disable(self, skill_id: str) -> dict[str, Any]:
        manifest = self._read_manifest(skill_id)
        manifest["enabled"] = False
        self._write_manifest(manifest)
        return {"id": skill_id, "trusted": manifest["trusted"], "enabled": False}

    # -- invocation ----------------------------------------------------------
    def invoke(
        self,
        skill_id: str,
        args: dict[str, Any] | None = None,
        noninteractive: bool = False,
        force_yes: bool = False,
    ) -> Any:
        """Validate, permission-check, and run a skill handler.

        The handler module is imported fresh from the skill directory on each
        call; only trusted+enabled skills can be invoked.
        """
        manifest = self._read_manifest(skill_id)
        if not manifest["trusted"]:
            raise SkillError(
                f"Skill {skill_id!r} is not trusted — refusing to execute. "
                f"Run `azzx skills trust {skill_id}` after reviewing its code."
            )
        if not manifest["enabled"]:
            raise SkillError(f"Skill {skill_id!r} is disabled — enable it first.")
        clean_args = validate_args(manifest["input_schema"], args or {})
        for cap in manifest["permissions"]:
            require_permission(
                cap, detail=f"skill {skill_id}",
                noninteractive=noninteractive, force_yes=force_yes,
            )
        module_name, func_name = manifest["handler"].split(":")
        handler_path = self.skill_path(skill_id) / f"{module_name}.py"
        if not handler_path.is_file():
            raise SkillError(f"Skill handler missing: {handler_path.name}")
        try:
            spec = importlib.util.spec_from_file_location(
                f"azzx_skill_{manifest['id']}_{module_name}", handler_path
            )
            if spec is None or spec.loader is None:
                raise SkillError("could not load handler module")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:  # noqa: BLE001
            raise SkillError(f"Skill handler failed to load: {exc}") from exc
        fn = getattr(mod, func_name, None)
        if not callable(fn):
            raise SkillError(f"Skill handler has no callable {func_name!r}")
        try:
            return fn(**clean_args)
        except TypeError as exc:
            raise SkillError(f"Skill handler argument mismatch: {exc}") from exc


def register_skill_tools(registry: SkillRegistry | None = None) -> None:
    """Expose trusted+enabled skills as `skill.<id>` tools in the registry.

    Idempotent: re-registering overwrites the previous ToolSpec. Permission
    checks still happen at execution time inside `SkillRegistry.invoke`.
    """
    reg = registry or SkillRegistry()

    def _make_handler(skill_id: str):
        def _handler(**kwargs: Any) -> Any:
            return reg.invoke(skill_id, kwargs)
        return _handler

    for meta in reg.list():
        if meta.get("error") or not meta.get("trusted") or not meta.get("enabled"):
            continue
        REGISTRY.register(ToolSpec(
            name=f"skill.{meta['id']}",
            description=f"[skill v{meta['version']}] {meta['description'] or meta['name']}",
            permissions=list(meta["permissions"]),
            handler=_make_handler(meta["id"]),
            schema={k: v.get("type", "string")
                    for k, v in meta["input_schema"].get("properties", {}).items()},
        ))


__all__ = [
    "SkillRegistry", "SkillError", "validate_manifest", "validate_args",
    "register_skill_tools", "SKILL_DIR",
]

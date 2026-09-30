"""Plugin loader: manifest.json required, declared permissions only, no arbitrary shell."""
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

PLUGIN_DIR = DATA_HOME / "plugins"
MANIFEST_NAME = "manifest.json"
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def validate_manifest(obj: dict[str, Any], source: str = "") -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise AzzxError(f"Invalid manifest (not object): {source}")
    pid = str(obj.get("id") or "").strip()
    if not ID_RE.match(pid):
        raise AzzxError(f"Invalid plugin id: {pid!r}")
    version = str(obj.get("version") or "0.0.0")
    tools = obj.get("tools") or []
    if not isinstance(tools, list):
        raise AzzxError("manifest.tools must be a list")
    for t in tools:
        if not isinstance(t, str) or not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*", t):
            raise AzzxError(f"Invalid tool name in manifest: {t!r}")
    perms = obj.get("permissions") or []
    if not isinstance(perms, list):
        raise AzzxError("manifest.permissions must be a list")
    for p in perms:
        if p not in PERMISSION_CAPABILITIES:
            raise AzzxError(
                f"Plugin declares unknown permission {p!r}. "
                f"Allowed: {PERMISSION_CAPABILITIES}"
            )
    entry = str(obj.get("entrypoint") or "plugin.py")
    if "/" in entry or "\\" in entry or entry.startswith("."):
        raise AzzxError(f"Invalid entrypoint: {entry!r}")
    # Explicitly reject shell hooks
    for banned in ("install_script", "shell", "postinstall", "command"):
        if banned in obj:
            raise AzzxError(f"Manifest field not allowed: {banned}")
    return {
        "id": pid,
        "name": str(obj.get("name") or pid),
        "version": version,
        "description": str(obj.get("description") or ""),
        "tools": [str(t) for t in tools],
        "permissions": [str(p) for p in perms],
        "entrypoint": entry,
        "enabled": bool(obj.get("enabled", True)),
    }


class PluginManager:
    def __init__(self) -> None:
        setup_homes()
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

    def plugin_path(self, plugin_id: str) -> Path:
        if not ID_RE.match(plugin_id):
            raise AzzxError(f"Invalid plugin id: {plugin_id}")
        return PLUGIN_DIR / plugin_id

    def list_installed(self) -> list[dict[str, Any]]:
        result = []
        for d in sorted(PLUGIN_DIR.iterdir() if PLUGIN_DIR.exists() else []):
            if not d.is_dir():
                continue
            man = d / MANIFEST_NAME
            if not man.exists():
                result.append({"id": d.name, "error": "missing manifest"})
                continue
            try:
                raw = load_json(man, {})
                meta = validate_manifest(raw, str(man))
                result.append(meta)
            except AzzxError as exc:
                result.append({"id": d.name, "error": str(exc)})
        return result


def install_plugin(source: str, force: bool = False, yes: bool = False) -> dict[str, Any]:
    """Install plugin from a local directory containing manifest.json."""
    require_permission("plugin.install", detail=f"install from {source}", force_yes=yes)
    src = Path(source).expanduser().resolve()
    if not src.is_dir():
        raise AzzxError(f"Plugin source must be a directory: {src}")
    man_path = src / MANIFEST_NAME
    if not man_path.is_file():
        raise AzzxError(f"Missing {MANIFEST_NAME} in {src}")
    raw = load_json(man_path, {})
    meta = validate_manifest(raw, str(man_path))
    dest = PluginManager().plugin_path(meta["id"])
    if dest.exists():
        if not force:
            raise AzzxError(f"Plugin already installed: {meta['id']} (use force)")
        shutil.rmtree(dest)
    # Copy only safe files (no nested .git execution, etc.)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".env"),
    )
    # Re-validate after copy
    validate_manifest(load_json(dest / MANIFEST_NAME, {}), str(dest))
    return {"installed": meta["id"], "path": str(dest), "version": meta["version"]}


def list_plugins() -> list[dict[str, Any]]:
    return PluginManager().list_installed()


def load_enabled_plugins() -> dict[str, Any]:
    """
    Load plugin entrypoints that expose a register(registry) function.
    Plugins may only register tools; they cannot bypass permission checks
    because REGISTRY.call still enforces permissions.
    """
    loaded = []
    errors = []
    for meta in list_plugins():
        if meta.get("error") or not meta.get("enabled", True):
            continue
        pid = meta["id"]
        entry = meta.get("entrypoint") or "plugin.py"
        path = PLUGIN_DIR / pid / entry
        if not path.is_file():
            errors.append({"id": pid, "error": f"entrypoint missing: {entry}"})
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"azzx_plugin_{pid}", path)
            if spec is None or spec.loader is None:
                raise AzzxError("import spec failed")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "register") and callable(mod.register):
                mod.register(REGISTRY)
            loaded.append(pid)
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": pid, "error": str(exc)})
    return {"loaded": loaded, "errors": errors}


def register_plugin_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="plugin.list",
        description="List installed local plugins",
        permissions=[],
        handler=lambda: {"plugins": list_plugins()},
        schema={},
    ))

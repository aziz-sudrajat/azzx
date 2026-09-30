"""Core utilities shared by all AZZX modules (v10)."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


class AzzxError(Exception):
    """User-facing recoverable error."""


class PermissionDenied(AzzxError):
    """Raised when a capability is denied by policy."""


APP_NAME = "AZZATSSINS LITE AGENT"
APP_SLUG = "azzatssins-lite-agent"
VERSION = "10.0.0"

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_SLUG
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_SLUG
CONFIG_FILE = CONFIG_HOME / "config.json"

# Extended permission capabilities for v7–v10
PERMISSION_CAPABILITIES = [
    "filesystem.write",
    "filesystem.read",
    "shell.run",
    "package.install",
    "git.commit",
    "git.push",
    "ssh",
    "database.write",
    "network.http",
    "release.publish",
    "device.adb",
    "device.mirror",
    "workflow.run",
    "plugin.install",
    "process.inspect",
    "archive.write",
]

DEFAULT_PERMISSIONS: dict[str, str] = {
    "filesystem.write": "allow",
    "filesystem.read": "allow",
    "shell.run": "ask",
    "package.install": "ask",
    "git.commit": "ask",
    "git.push": "deny",
    "ssh": "ask",
    "database.write": "ask",
    "network.http": "allow",
    "release.publish": "deny",
    "device.adb": "ask",
    "device.mirror": "ask",
    "workflow.run": "ask",
    "plugin.install": "ask",
    "process.inspect": "allow",
    "archive.write": "ask",
}


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def setup_homes() -> None:
    ensure_private_dir(CONFIG_HOME)
    ensure_private_dir(DATA_HOME)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".azzx-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def save_json(path: Path, data: Any, private: bool = False) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    atomic_write(path, text, mode=0o600 if private else None)


def load_config() -> dict[str, Any]:
    setup_homes()
    cfg = load_json(CONFIG_FILE, {})
    if not isinstance(cfg, dict):
        cfg = {}
    # Merge permissions with defaults so new capabilities appear after upgrade
    perms = dict(DEFAULT_PERMISSIONS)
    perms.update(cfg.get("permissions") or {})
    cfg["permissions"] = perms
    if "version" not in cfg:
        cfg["version"] = 2
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    setup_homes()
    save_json(CONFIG_FILE, cfg, private=True)


def permission_policy(capability: str) -> str:
    cfg = load_config()
    perms = cfg.get("permissions") or {}
    value = str(perms.get(capability, "ask")).lower()
    return value if value in {"allow", "ask", "deny"} else "ask"


def require_permission(
    capability: str,
    detail: str = "",
    noninteractive: bool = False,
    ask_fn: Optional[Callable[[str], bool]] = None,
    force_yes: bool = False,
) -> bool:
    policy = permission_policy(capability)
    if policy == "allow" or force_yes:
        return True
    if policy == "deny":
        raise PermissionDenied(f"Permission denied by AZZX policy: {capability}")
    if noninteractive and not force_yes:
        raise PermissionDenied(
            f"Permission requires confirmation: {capability}. "
            f"Set with `azzx permissions set {capability} allow` or pass -y after reviewing."
        )
    prompt = f"Allow {capability}?" + (f"\n{detail}" if detail else "")
    if ask_fn is not None:
        if not ask_fn(prompt):
            raise PermissionDenied(f"Permission not granted: {capability}")
        return True
    # Fallback: deny in non-TTY without ask_fn
    import sys
    if not sys.stdin.isatty():
        raise PermissionDenied(f"Permission requires confirmation: {capability}")
    try:
        from rich.prompt import Confirm
        if not Confirm.ask(prompt, default=False):
            raise PermissionDenied(f"Permission not granted: {capability}")
    except ImportError:
        ans = input(f"{prompt} [y/N] ").strip().lower()
        if ans not in {"y", "yes"}:
            raise PermissionDenied(f"Permission not granted: {capability}")
    return True


def sanitize_id(name: str, pattern: str = r"[A-Za-z0-9][A-Za-z0-9+._:@-]*") -> str:
    value = name.strip()
    if not re.fullmatch(pattern, value):
        raise AzzxError(f"Invalid identifier: {name!r}")
    return value


def safe_path_under(root: Path, relative: str) -> Path:
    """Resolve relative path and ensure it stays under root."""
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AzzxError(f"Path escapes workspace: {relative}") from exc
    return candidate


@dataclass
class ToolSpec:
    """Registered deterministic tool."""
    name: str
    description: str
    permissions: list[str] = field(default_factory=list)
    handler: Optional[Callable[..., Any]] = None
    schema: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Central registry: AI orchestrator may only call registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*", spec.name):
            raise AzzxError(f"Invalid tool name: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise AzzxError(f"Unknown tool: {name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolSpec]:
        return [self._tools[k] for k in sorted(self._tools)]

    def call(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        noninteractive: bool = False,
        force_yes: bool = False,
    ) -> Any:
        spec = self.get(name)
        args = args or {}
        for cap in spec.permissions:
            require_permission(cap, detail=f"tool {name}", noninteractive=noninteractive, force_yes=force_yes)
        if spec.handler is None:
            raise AzzxError(f"Tool has no handler: {name}")
        return spec.handler(**args)


# Global registry instance used by toolkit / workflow / device modules
REGISTRY = ToolRegistry()

"""Orchestrator helpers: tool catalog for AI + safe NL shortcuts for simple ops."""
from __future__ import annotations

import re
from typing import Any

from azzx.core import REGISTRY, AzzxError
from azzx.tools import register_all_toolkit_tools
from azzx.workflow.engine import register_workflow_tools
from azzx.device import register_all_device_tools
from azzx.plugins.loader import register_plugin_tools, load_enabled_plugins


_REGISTERED = False


def register_all() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_all_toolkit_tools()
    register_workflow_tools()
    register_all_device_tools()
    register_plugin_tools()
    try:
        load_enabled_plugins()
    except Exception:  # noqa: BLE001 — plugins must not break boot
        pass
    _REGISTERED = True


def describe_tools_for_ai() -> list[dict[str, Any]]:
    register_all()
    return [
        {
            "name": t.name,
            "description": t.description,
            "permissions": t.permissions,
            "schema": t.schema,
        }
        for t in REGISTRY.list_tools()
    ]


def run_tool_call(name: str, args: dict[str, Any] | None = None, noninteractive: bool = False, force_yes: bool = False) -> Any:
    register_all()
    return REGISTRY.call(name, args or {}, noninteractive=noninteractive, force_yes=force_yes or noninteractive)


# Simple deterministic NL → tool mapping for common phrases (no LLM required)
_NL_PATTERNS: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    (re.compile(r"(?i)\b(system|sys)\s*(info|information|health)\b"), "sys.health", {}),
    (re.compile(r"(?i)\bdisk\s*(usage|space|health)?\b"), "sys.health", {}),
    (re.compile(r"(?i)\bgit\s*status\b"), "git.status", {"path": "."}),
    (re.compile(r"(?i)\b(list|show)\s*processes?\b"), "sys.processes", {"limit": 20}),
    (re.compile(r"(?i)\b(check\s*)?(network|connectivity|online)\b"), "net.connectivity", {}),
    (re.compile(r"(?i)\b(mirror|scrcpy)\s*(status)?\b"), "device.mirror.status", {}),
    (re.compile(r"(?i)\b(start\s*)?(screen\s*)?mirror\b"), "device.mirror.start", {}),
    (re.compile(r"(?i)\bstop\s*(screen\s*)?mirror\b"), "device.mirror.stop", {}),
    (re.compile(r"(?i)\badb\s*devices\b"), "device.adb.devices", {}),
    (re.compile(r"(?i)\blargest\s*files?\b"), "fs.largest", {"path": ".", "limit": 15}),
    (re.compile(r"(?i)\b(find\s*)?duplicates?\b"), "fs.duplicates", {"path": ".", "limit_groups": 10}),
    (re.compile(r"(?i)\btermux\s*(api)?\b"), "device.termux.detect", {}),
]


def map_nl_to_tool(text: str) -> dict[str, Any] | None:
    """Map a simple natural-language request to a registered tool call.

    Returns None if no safe mapping exists (caller may fall back to AI coding agent).
    Never maps to arbitrary shell.
    """
    text = (text or "").strip()
    if not text:
        return None
    for pattern, tool, args in _NL_PATTERNS:
        if pattern.search(text):
            return {"tool": tool, "args": dict(args), "matched": pattern.pattern}
    # website status: "check https://example.com"
    m = re.search(r"(?i)\b(check|status|ping)\s+(https?://\S+)", text)
    if m:
        return {"tool": "net.website", "args": {"url": m.group(2)}, "matched": "website"}
    # hash file
    m = re.search(r"(?i)\b(sha256|md5|sha1|checksum)\s+(\S+)", text)
    if m:
        return {"tool": "hash.file", "args": {"path": m.group(2), "algorithm": m.group(1) if m.group(1) != "checksum" else "sha256"}, "matched": "hash"}
    return None

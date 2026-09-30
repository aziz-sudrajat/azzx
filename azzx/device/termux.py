"""Termux API capability detection (no arbitrary termux-command execution)."""
from __future__ import annotations

import os
import shutil
from typing import Any

from azzx.core import REGISTRY, ToolSpec

# Known Termux:API binaries we only *detect*, not invoke freely
TERMUX_API_BINS = [
    "termux-battery-status",
    "termux-clipboard-get",
    "termux-clipboard-set",
    "termux-notification",
    "termux-toast",
    "termux-vibrate",
    "termux-wifi-connectioninfo",
    "termux-telephony-deviceinfo",
    "termux-info",
]


def detect_termux_api() -> dict[str, Any]:
    is_termux = bool(
        os.environ.get("TERMUX_VERSION")
        or os.environ.get("PREFIX", "").endswith("com.termux/files/usr")
        or (os.environ.get("PREFIX") or "").find("com.termux") >= 0
    )
    found = {}
    for name in TERMUX_API_BINS:
        path = shutil.which(name)
        found[name] = path is not None
    available = sum(1 for v in found.values() if v)
    return {
        "is_termux": is_termux,
        "api_commands_found": available,
        "total_checked": len(TERMUX_API_BINS),
        "details": found,
        "hint": None if available else "Install Termux:API app + `pkg install termux-api`",
    }


def register_termux_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="device.termux.detect",
        description="Detect Termux environment and Termux:API binaries",
        permissions=[],
        handler=detect_termux_api,
        schema={},
    ))

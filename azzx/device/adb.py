"""ADB detection and safe device listing — no free-form adb shell."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError, require_permission

# Only these adb subcommands are allowed through the tool layer
ALLOWED_ADB = {"devices", "version", "get-state", "get-serialno"}


def detect_adb() -> dict[str, Any]:
    path = shutil.which("adb")
    if not path:
        return {"available": False, "path": None, "version": None}
    version = None
    try:
        proc = subprocess.run([path, "version"], capture_output=True, text=True, timeout=5)
        first = (proc.stdout or "").splitlines()[:1]
        version = first[0] if first else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"available": True, "path": path, "version": version}


def list_devices() -> dict[str, Any]:
    require_permission("device.adb", detail="adb devices")
    info = detect_adb()
    if not info["available"]:
        raise AzzxError("adb not found. Install Android platform-tools.")
    try:
        proc = subprocess.run(
            [info["path"], "devices", "-l"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AzzxError(f"adb failed: {exc}") from exc
    devices = []
    for line in (proc.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            serial, state = parts[0], parts[1]
            extra = " ".join(parts[2:]) if len(parts) > 2 else ""
            devices.append({"serial": serial, "state": state, "info": extra})
    return {"adb": info, "devices": devices, "count": len(devices)}


def register_adb_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="device.adb.detect",
        description="Detect whether adb is installed",
        permissions=[],
        handler=detect_adb,
        schema={},
    ))
    REGISTRY.register(ToolSpec(
        name="device.adb.devices",
        description="List connected Android devices via adb",
        permissions=["device.adb"],
        handler=list_devices,
        schema={},
    ))

"""Realistic Android screen mirroring via scrcpy (not a full DeX clone).

AZZX orchestrates scrcpy with a strict argument whitelist:
  - no arbitrary shell
  - permission device.mirror + device.adb
  - process tracking for start/stop/status
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from azzx.core import (
    AzzxError,
    DATA_HOME,
    REGISTRY,
    ToolSpec,
    load_json,
    require_permission,
    save_json,
    setup_homes,
)
from azzx.device.adb import detect_adb, list_devices

STATE_FILE = DATA_HOME / "mirror_state.json"

# Whitelisted scrcpy flags only (values validated separately)
MAX_SIZE_RANGE = (64, 4096)
BITRATE_RANGE = (100_000, 100_000_000)


def detect_scrcpy() -> dict[str, Any]:
    import shutil
    path = shutil.which("scrcpy")
    if not path:
        return {"available": False, "path": None, "hint": "azzx install scrcpy  # or package manager"}
    version = None
    try:
        proc = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        version = (proc.stdout or proc.stderr or "").strip().splitlines()[:1]
        version = version[0] if version else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"available": True, "path": path, "version": version}


def _load_state() -> dict[str, Any]:
    setup_homes()
    data = load_json(STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_state(data: dict[str, Any]) -> None:
    setup_homes()
    save_json(STATE_FILE, data)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def mirror_status() -> dict[str, Any]:
    state = _load_state()
    pid = int(state.get("pid") or 0)
    alive = _pid_alive(pid)
    if state and not alive:
        state["running"] = False
        _save_state(state)
    return {
        "running": alive,
        "pid": pid if alive else None,
        "started_at": state.get("started_at"),
        "serial": state.get("serial"),
        "args": state.get("display_args"),
        "scrcpy": detect_scrcpy(),
        "adb": detect_adb(),
    }


def mirror_stop() -> dict[str, Any]:
    require_permission("device.mirror", detail="stop screen mirror")
    state = _load_state()
    pid = int(state.get("pid") or 0)
    if not pid or not _pid_alive(pid):
        _save_state({"running": False})
        return {"stopped": False, "reason": "not running"}
    try:
        os.kill(pid, signal.SIGTERM)
        # brief wait
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.1)
        if _pid_alive(pid):
            os.kill(pid, signal.SIGKILL)
    except OSError as exc:
        raise AzzxError(f"Failed to stop mirror: {exc}") from exc
    _save_state({"running": False, "pid": None})
    return {"stopped": True, "pid": pid}


def mirror_start(
    serial: str = "",
    max_size: int = 0,
    bit_rate: int = 0,
    stay_awake: bool = True,
    fullscreen: bool = False,
    always_on_top: bool = False,
    window_title: str = "AZZX Mirror",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Start scrcpy with validated arguments only."""
    if not dry_run:
        require_permission("device.mirror", detail="start Android screen mirror (scrcpy)")
        require_permission("device.adb", detail="adb transport for mirror")

    scrcpy = detect_scrcpy()
    adb = detect_adb()
    if not dry_run:
        if not scrcpy["available"]:
            raise AzzxError(
                "scrcpy not found. Install it first, e.g. "
                "`azzx install scrcpy` or your distro package manager."
            )
        if not adb["available"]:
            raise AzzxError("adb not found. Install Android platform-tools.")

    # Optional: ensure at least one device (skip on dry_run to allow plan without grants)
    if not dry_run:
        try:
            devs = list_devices()
            if devs["count"] == 0:
                raise AzzxError(
                    "No Android device connected. Enable USB debugging or wireless adb, "
                    "then run: adb devices"
                )
            if serial:
                serials = {d["serial"] for d in devs["devices"]}
                if serial not in serials:
                    raise AzzxError(f"Device serial not found: {serial}")
        except AzzxError:
            raise

    # Stop existing session
    st = mirror_status()
    if st["running"] and not dry_run:
        mirror_stop()

    cmd: list[str] = [scrcpy["path"] or "scrcpy"]
    display_args: list[str] = []

    if serial:
        if not re_serial(serial):
            raise AzzxError(f"Invalid serial: {serial!r}")
        cmd.extend(["-s", serial])
        display_args.append(f"serial={serial}")

    if max_size:
        if not (MAX_SIZE_RANGE[0] <= int(max_size) <= MAX_SIZE_RANGE[1]):
            raise AzzxError(f"max_size out of range {MAX_SIZE_RANGE}")
        cmd.extend(["-m", str(int(max_size))])
        display_args.append(f"max_size={max_size}")

    if bit_rate:
        if not (BITRATE_RANGE[0] <= int(bit_rate) <= BITRATE_RANGE[1]):
            raise AzzxError(f"bit_rate out of range {BITRATE_RANGE}")
        cmd.extend(["-b", str(int(bit_rate))])
        display_args.append(f"bit_rate={bit_rate}")

    if stay_awake:
        cmd.append("--stay-awake")
        display_args.append("stay_awake")
    if fullscreen:
        cmd.append("--fullscreen")
        display_args.append("fullscreen")
    if always_on_top:
        cmd.append("--always-on-top")
        display_args.append("always_on_top")
    if window_title:
        title = str(window_title)[:64]
        # strip shell-metacharacters
        title = "".join(c for c in title if c.isalnum() or c in " _-.")
        cmd.extend(["--window-title", title or "AZZX Mirror"])
        display_args.append(f"title={title}")

    if dry_run:
        return {"dry_run": True, "command": cmd, "display_args": display_args}

    # Launch detached
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise AzzxError(f"Failed to start scrcpy: {exc}") from exc

    state = {
        "running": True,
        "pid": proc.pid,
        "started_at": time.time(),
        "serial": serial or None,
        "display_args": display_args,
        "command_head": cmd[:3],
    }
    _save_state(state)
    return {
        "started": True,
        "pid": proc.pid,
        "serial": serial or None,
        "args": display_args,
        "note": "Android screen is mirroring via scrcpy (desktop control). "
                "This is not a full Samsung DeX desktop environment.",
    }


def re_serial(serial: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_:.-]{1,64}", serial))


def register_mirror_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="device.mirror.detect",
        description="Detect scrcpy availability",
        permissions=[],
        handler=detect_scrcpy,
        schema={},
    ))
    REGISTRY.register(ToolSpec(
        name="device.mirror.start",
        description="Start Android screen mirror via scrcpy (whitelisted args)",
        permissions=["device.mirror", "device.adb"],
        handler=mirror_start,
        schema={
            "serial": "str", "max_size": "int", "bit_rate": "int",
            "stay_awake": "bool", "fullscreen": "bool", "always_on_top": "bool",
            "window_title": "str", "dry_run": "bool",
        },
    ))
    REGISTRY.register(ToolSpec(
        name="device.mirror.stop",
        description="Stop active scrcpy mirror session",
        permissions=["device.mirror"],
        handler=mirror_stop,
        schema={},
    ))
    REGISTRY.register(ToolSpec(
        name="device.mirror.status",
        description="Status of mirror session",
        permissions=[],
        handler=mirror_status,
        schema={},
    ))

"""v8 Device layer: ADB detection + realistic screen mirroring (scrcpy)."""
from .adb import detect_adb, list_devices, register_adb_tools
from .mirror import (
    detect_scrcpy,
    mirror_start,
    mirror_status,
    mirror_stop,
    register_mirror_tools,
)
from .termux import detect_termux_api, register_termux_tools


def register_all_device_tools() -> None:
    register_adb_tools()
    register_mirror_tools()
    register_termux_tools()

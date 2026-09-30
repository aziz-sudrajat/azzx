"""Process viewer, service status, git status, system health."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError, require_permission


def system_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hostname": platform.node(),
        "cpus": os.cpu_count(),
    }
    # memory (Linux)
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        data = {}
        for line in meminfo.read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
        info["mem_total"] = data.get("MemTotal")
        info["mem_available"] = data.get("MemAvailable")
    # load
    try:
        info["loadavg"] = os.getloadavg()
    except (OSError, AttributeError):
        pass
    # Termux
    if os.environ.get("PREFIX", "").endswith("com.termux/files/usr") or shutil.which("termux-info"):
        info["environment"] = "termux"
    elif os.environ.get("WSL_DISTRO_NAME"):
        info["environment"] = "wsl"
    else:
        info["environment"] = "linux"
    return info


def process_list(limit: int = 30, name_filter: str = "") -> dict[str, Any]:
    require_permission("process.inspect")
    procs = []
    # Prefer ps
    ps = shutil.which("ps")
    if ps:
        try:
            out = subprocess.run(
                [ps, "ax", "-o", "pid,user,pcpu,pmem,stat,comm"],
                capture_output=True, text=True, timeout=5,
            )
            lines = out.stdout.strip().splitlines()[1:]
            for line in lines:
                parts = line.split(None, 5)
                if len(parts) < 6:
                    continue
                pid, user, pcpu, pmem, stat, comm = parts
                if name_filter and name_filter.lower() not in comm.lower():
                    continue
                procs.append({
                    "pid": pid, "user": user, "cpu": pcpu, "mem": pmem,
                    "stat": stat, "command": comm,
                })
                if len(procs) >= max(1, limit):
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"count": len(procs), "processes": procs}


def service_status(name: str) -> dict[str, Any]:
    """systemctl status if available; Termux-friendly fallback."""
    require_permission("process.inspect")
    name = name.strip()
    if not name or not all(c.isalnum() or c in "._@-+" for c in name):
        raise AzzxError(f"Invalid service name: {name!r}")
    systemctl = shutil.which("systemctl")
    if systemctl:
        try:
            proc = subprocess.run(
                [systemctl, "is-active", name],
                capture_output=True, text=True, timeout=5,
            )
            active = proc.stdout.strip()
            return {"service": name, "manager": "systemd", "state": active or "unknown"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"service": name, "manager": "systemd", "error": str(exc)}
    return {"service": name, "manager": "none", "state": "unsupported", "note": "systemctl not found (Termux/container?)"}


def git_status(path: str = ".") -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    git = shutil.which("git")
    if not git:
        return {"git": False, "error": "git not installed"}
    try:
        branch = subprocess.run(
            [git, "branch", "--show-current"], cwd=root,
            capture_output=True, text=True, timeout=5,
        )
        status = subprocess.run(
            [git, "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, timeout=10,
        )
        if status.returncode != 0:
            return {"git": False, "error": status.stderr.strip() or "not a git repo"}
        lines = [l for l in status.stdout.splitlines() if l.strip()]
        return {
            "git": True,
            "root": str(root),
            "branch": branch.stdout.strip() or "(detached)",
            "dirty": len(lines) > 0,
            "changes": len(lines),
            "sample": lines[:20],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"git": False, "error": str(exc)}


def system_health() -> dict[str, Any]:
    info = system_info()
    health: dict[str, Any] = {"info": info, "checks": []}
    # disk
    try:
        usage = shutil.disk_usage(Path.home())
        pct = round(100 * usage.used / usage.total, 1) if usage.total else 0
        health["disk"] = {
            "total": usage.total, "used": usage.used, "free": usage.free, "percent_used": pct,
        }
        health["checks"].append({"name": "disk", "ok": pct < 90, "detail": f"{pct}% used"})
    except OSError as exc:
        health["checks"].append({"name": "disk", "ok": False, "detail": str(exc)})
    load = info.get("loadavg")
    cpus = info.get("cpus") or 1
    if load:
        health["checks"].append({
            "name": "load",
            "ok": load[0] < cpus * 2,
            "detail": f"load1={load[0]} cpus={cpus}",
        })
    return health


def register_system_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="sys.info", description="OS / hardware summary",
        permissions=[], handler=system_info, schema={},
    ))
    REGISTRY.register(ToolSpec(
        name="sys.health", description="Disk/load health snapshot",
        permissions=[], handler=system_health, schema={},
    ))
    REGISTRY.register(ToolSpec(
        name="sys.processes", description="List running processes",
        permissions=["process.inspect"], handler=process_list,
        schema={"limit": "int", "name_filter": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="sys.service", description="Check systemd service state",
        permissions=["process.inspect"], handler=service_status,
        schema={"name": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="git.status", description="Git working tree status",
        permissions=["filesystem.read"], handler=git_status,
        schema={"path": "str"},
    ))

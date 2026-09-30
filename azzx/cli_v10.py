"""CLI handlers for v7–v10 features (toolkit, workflow, device/mirror, plugins, tools)."""
from __future__ import annotations

import json
from typing import Any

from azzx.agent.orchestrator import describe_tools_for_ai, map_nl_to_tool, register_all, run_tool_call
from azzx.core import AzzxError, REGISTRY
from azzx.device.adb import detect_adb, list_devices
from azzx.device.mirror import detect_scrcpy, mirror_start, mirror_status, mirror_stop
from azzx.device.termux import detect_termux_api
from azzx.plugins.loader import install_plugin, list_plugins, load_enabled_plugins
from azzx.workflow.engine import (
    create_workflow,
    delete_workflow,
    list_workflows,
    run_workflow,
    show_workflow,
)


def _guard(fn):
    """Convert azzx.core errors into printable exits for the v6 CLI shell."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AzzxError as exc:
            try:
                from rich.console import Console
                from rich.panel import Panel
                Console().print(Panel(str(exc), title="AZZX ERROR", border_style="red"))
            except Exception:
                print(f"AZZX ERROR: {exc}")
            return 2
    return wrapper



def _print_json(data: Any) -> None:
    try:
        from rich.console import Console
        from rich.syntax import Syntax
        c = Console()
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        c.print(Syntax(text, "json", theme="monokai", word_wrap=True))
    except Exception:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


@_guard
def cmd_tools_list() -> int:
    register_all()
    tools = describe_tools_for_ai()
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
        c = Console()
        t = Table(title="AZZX Tool Registry (v10)", box=box.ROUNDED)
        t.add_column("Tool")
        t.add_column("Permissions")
        t.add_column("Description")
        for x in tools:
            t.add_row(x["name"], ", ".join(x["permissions"]) or "-", x["description"][:60])
        c.print(t)
    except Exception:
        for x in tools:
            print(f"{x['name']}: {x['description']}")
    return 0


@_guard
def cmd_tool_run(name: str, args_json: str = "{}", yes: bool = False) -> int:
    register_all()
    try:
        args = json.loads(args_json) if args_json else {}
        if not isinstance(args, dict):
            raise AzzxError("args must be a JSON object")
    except json.JSONDecodeError as exc:
        raise AzzxError(f"Invalid JSON args: {exc}") from exc
    result = run_tool_call(name, args, noninteractive=yes)
    _print_json(result)
    return 0


@_guard
def cmd_nl(text: str, yes: bool = False) -> int:
    register_all()
    mapped = map_nl_to_tool(text)
    if not mapped:
        raise AzzxError(
            "No safe toolkit mapping for that phrase. "
            "Use `azzx tools list` or the coding agent for complex tasks."
        )
    result = run_tool_call(mapped["tool"], mapped["args"], noninteractive=yes)
    _print_json({"matched": mapped, "result": result})
    return 0


@_guard
def cmd_workflow(action: str, name: str = "", steps_json: str = "", description: str = "", yes: bool = False) -> int:
    register_all()
    if action == "list":
        _print_json(list_workflows())
        return 0
    if action == "show":
        if not name:
            raise AzzxError("workflow show requires NAME")
        _print_json(show_workflow(name))
        return 0
    if action == "delete":
        if not name:
            raise AzzxError("workflow delete requires NAME")
        delete_workflow(name)
        print(f"Deleted workflow: {name}")
        return 0
    if action == "run":
        if not name:
            raise AzzxError("workflow run requires NAME")
        result = run_workflow(name, noninteractive=yes)
        _print_json(result)
        return 0 if result.get("ok") else 1
    if action == "create":
        if not name:
            raise AzzxError("workflow create requires NAME")
        if not steps_json:
            raise AzzxError('Provide --steps JSON, e.g. \'[{"tool":"sys.health","args":{}}]\'')
        try:
            steps = json.loads(steps_json)
        except json.JSONDecodeError as exc:
            raise AzzxError(f"Invalid steps JSON: {exc}") from exc
        data = create_workflow(name, steps, description=description, overwrite=yes)
        _print_json(data)
        return 0
    raise AzzxError(f"Unknown workflow action: {action}")


@_guard
def cmd_mirror(action: str, serial: str = "", max_size: int = 0, bit_rate: int = 0,
               fullscreen: bool = False, dry_run: bool = False, yes: bool = False) -> int:
    register_all()
    if action in {"detect", "status"}:
        _print_json({
            "scrcpy": detect_scrcpy(),
            "adb": detect_adb(),
            "status": mirror_status() if action == "status" else None,
            "termux": detect_termux_api(),
        })
        return 0
    if action == "devices":
        _print_json(list_devices())
        return 0
    if action == "start":
        # Permission prompts happen inside mirror_start unless we need --yes path
        if yes:
            # temporarily allow by relying on noninteractive only when policy is allow;
            # mirror_start uses require_permission which respects config
            pass
        result = mirror_start(
            serial=serial,
            max_size=max_size or 0,
            bit_rate=bit_rate or 0,
            fullscreen=fullscreen,
            dry_run=dry_run,
        )
        _print_json(result)
        return 0
    if action == "stop":
        _print_json(mirror_stop())
        return 0
    raise AzzxError(f"Unknown mirror action: {action}")


@_guard
def cmd_plugin(action: str, source: str = "", force: bool = False) -> int:
    register_all()
    if action == "list":
        _print_json(list_plugins())
        return 0
    if action == "install":
        if not source:
            raise AzzxError("plugin install requires SOURCE directory")
        _print_json(install_plugin(source, force=force, yes=True))
        return 0
    if action == "load":
        _print_json(load_enabled_plugins())
        return 0
    raise AzzxError(f"Unknown plugin action: {action}")


@_guard
def cmd_toolkit(kind: str, **kwargs: Any) -> int:
    """Dispatch high-level toolkit shortcuts."""
    register_all()
    mapping = {
        "search": ("fs.search", {"path": kwargs.get("path") or ".", "pattern": kwargs.get("pattern") or "*", "limit": int(kwargs.get("limit") or 50)}),
        "largest": ("fs.largest", {"path": kwargs.get("path") or ".", "limit": int(kwargs.get("limit") or 20)}),
        "duplicates": ("fs.duplicates", {"path": kwargs.get("path") or ".", "limit_groups": int(kwargs.get("limit") or 20)}),
        "hash": ("hash.file", {"path": kwargs.get("path") or "", "algorithm": kwargs.get("algorithm") or "sha256"}),
        "health": ("sys.health", {}),
        "info": ("sys.info", {}),
        "processes": ("sys.processes", {"limit": int(kwargs.get("limit") or 30)}),
        "git-status": ("git.status", {"path": kwargs.get("path") or "."}),
        "connectivity": ("net.connectivity", {}),
        "website": ("net.website", {"url": kwargs.get("url") or ""}),
    }
    if kind not in mapping:
        raise AzzxError(f"Unknown toolkit command: {kind}")
    tool, args = mapping[kind]
    if kind == "hash" and not args["path"]:
        raise AzzxError("hash requires --path")
    if kind == "website" and not args["url"]:
        raise AzzxError("website requires --url")
    yes = bool(kwargs.get("yes"))
    result = run_tool_call(tool, args, noninteractive=yes)
    _print_json(result)
    return 0

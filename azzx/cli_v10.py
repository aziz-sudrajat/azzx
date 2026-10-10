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


# ---------------------------------------------------------------------------
# v10.2 Hermes-like commands
# ---------------------------------------------------------------------------

@_guard
def cmd_hermes(args: Any, root: Any = None, forced_provider: str | None = None) -> int:
    """Dispatch `azzx hermes <think|memory|trace|queue|stream>`."""
    from azzx.agent.memory import get_memory_store
    from azzx.agent.multi_agent import get_multi_agent_orchestrator
    from azzx.agent.tasks import get_task_queue
    from azzx.agent.tracer import get_tracer

    action = getattr(args, "hermes_action", None)

    if action == "think":
        prompt = " ".join(getattr(args, "prompt", []) or []).strip()
        if not prompt:
            raise AzzxError("think membutuhkan prompt")
        agents_raw = (getattr(args, "agents", "") or "").strip()
        order = [a.strip() for a in agents_raw.split(",") if a.strip()] or None
        show_reasoning = not getattr(args, "hide_reasoning", False)
        orch = get_multi_agent_orchestrator()
        result = orch.run_task(prompt, agent_order=order)
        try:
            from rich.console import Console
            from rich.panel import Panel
            c = Console()
            for entry in result.get("results", []):
                agent = entry.get("agent", "?")
                c.print(Panel(str(entry.get("output", "")), title=f"[{agent}] {entry.get('role', '')}", border_style="cyan"))
                if show_reasoning:
                    reasoning = entry.get("reasoning") or {}
                    steps = reasoning.get("steps", [])
                    if steps:
                        lines = [f"  {s['kind'].upper():<10} {s['content']}" for s in steps]
                        c.print(Panel("\n".join(lines), title=f"reasoning: {agent}", border_style="dim"))
        except Exception:
            _print_json(result)
        return 0

    if action == "memory":
        query = " ".join(getattr(args, "query", []) or []).strip()
        mode = getattr(args, "mode", "hybrid")
        limit = int(getattr(args, "limit", 8) or 8)
        store = get_memory_store()
        if mode == "keyword":
            hits = [(m, 1.0) for m in store.search(query, limit=limit, min_importance=0.0)]
        elif mode == "semantic":
            hits = store.search_semantic(query, limit=limit)
        else:
            hits = store.search_hybrid(query, limit=limit)
        rows = [
            {
                "score": round(score, 3),
                "agent": m.agent_id,
                "type": m.memory_type,
                "importance": m.importance,
                "content": (m.content or "")[:220],
            }
            for m, score in hits
        ]
        try:
            from rich.console import Console
            from rich.table import Table
            from rich import box
            c = Console()
            t = Table(title=f"Memory ({mode}): {query[:60]}", box=box.ROUNDED)
            t.add_column("Score", justify="right")
            t.add_column("Agent")
            t.add_column("Type")
            t.add_column("Content")
            for r in rows:
                t.add_row(str(r["score"]), r["agent"], r["type"], r["content"])
            c.print(t)
        except Exception:
            _print_json(rows)
        return 0

    if action == "trace":
        limit = int(getattr(args, "limit", 20) or 20)
        kind = (getattr(args, "kind", "") or "").strip() or None
        tracer = get_tracer()
        items = tracer.recent_from_log(limit * 2)
        if kind:
            items = [i for i in items if i.get("kind") == kind][:limit]
        else:
            items = items[:limit]
        try:
            from rich.console import Console
            from rich.table import Table
            from rich import box
            c = Console()
            t = Table(title="Execution timeline", box=box.ROUNDED)
            t.add_column("Span")
            t.add_column("Kind")
            t.add_column("Duration", justify="right")
            t.add_column("Status")
            for i in items:
                status = i.get("status", "?")
                style = "red" if status == "error" else "green"
                t.add_row(
                    str(i.get("name", ""))[:48],
                    str(i.get("kind", "")),
                    f"{i.get('duration_ms', 0)} ms",
                    f"[{style}]{status}[/{style}]",
                )
            c.print(t)
            stats = tracer.stats()
            c.print(f"[dim]spans this session: {stats['spans']} | errors: {stats['errors']} | total {stats['total_ms']} ms[/]")
        except Exception:
            _print_json(items)
        return 0

    if action == "queue":
        q_action = getattr(args, "queue_action", None)
        if q_action == "submit":
            tool = getattr(args, "tool", "")
            try:
                tool_args = json.loads(getattr(args, "args", "{}") or "{}")
            except ValueError as exc:
                raise AzzxError(f"--args harus JSON valid: {exc}")
            # No in-process worker for CLI one-shots: the detached drainer
            # owns execution, so a dying CLI process can't half-run the task.
            from azzx.agent.tasks import TaskQueue, spawn_drainer
            q = TaskQueue(auto_worker=False)
            task_id = q.submit_tool(tool, tool_args if isinstance(tool_args, dict) else {})
            if not spawn_drainer():
                raise AzzxError("gagal meluncurkan background worker")
            print(task_id)
            return 0
        q = get_task_queue()
        if q_action == "list":
            _print_json(q.list_tasks())
            return 0
        if q_action == "status":
            snap = q.status(getattr(args, "task_id", ""))
            if snap is None:
                raise AzzxError("task tidak ditemukan")
            _print_json(snap)
            return 0
        if q_action == "result":
            snap = q.result(getattr(args, "task_id", ""), timeout=float(getattr(args, "wait", 0) or 0))
            if snap is None:
                raise AzzxError("task tidak ditemukan")
            _print_json(snap)
            return 0
        raise AzzxError("queue action tidak dikenal")

    if action == "schedule":
        from azzx.agent.orchestrator import register_all
        from azzx.agent.scheduler import ToolScheduler
        register_all()
        scheduler = ToolScheduler()
        schedule_action = getattr(args, "schedule_action", "list")
        if schedule_action == "list":
            _print_json(scheduler.list())
            return 0
        if schedule_action == "add":
            try:
                payload = json.loads(getattr(args, "args", "{}") or "{}")
            except ValueError as exc:
                raise AzzxError(f"--args harus JSON valid: {exc}")
            if not isinstance(payload, dict):
                raise AzzxError("--args harus berupa JSON object")
            job = scheduler.add(
                getattr(args, "tool", ""), payload,
                int(getattr(args, "every", 3600)),
                getattr(args, "name", ""),
            )
            _print_json(job)
            return 0
        if schedule_action == "remove":
            if not scheduler.remove(getattr(args, "job_id", "")):
                raise AzzxError("schedule ID tidak ditemukan")
            print("Schedule removed")
            return 0
        if schedule_action == "run-due":
            _print_json(scheduler.run_due(limit=int(getattr(args, "limit", 20))))
            return 0
        raise AzzxError("schedule action tidak dikenal")

    if action == "stream":
        prompt = " ".join(getattr(args, "prompt", []) or []).strip()
        if not prompt:
            raise AzzxError("stream membutuhkan prompt")
        from azzx_cli import run_stream_ask  # lazy: azzx_cli owns the AI pipeline
        images = getattr(args, "image", []) or []
        return run_stream_ask(root, prompt, forced_provider, images)

    raise AzzxError("hermes action tidak dikenal")

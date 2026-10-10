"""CLI handlers for v7–v10 features (toolkit, workflow, device/mirror, plugins,
tools, and the native v10.4 agent commands: agent, queue, schedule, recall,
trace, session, skills)."""
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


def _parse_json_arg(raw: str, flag: str = "--args") -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except ValueError as exc:
        raise AzzxError(f"{flag} must be valid JSON: {exc}")
    if not isinstance(payload, dict):
        raise AzzxError(f"{flag} must be a JSON object")
    return payload


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
    args = _parse_json_arg(args_json)
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
# v10.4 native agent commands (one unified agent — no separate modes)
# ---------------------------------------------------------------------------

def cmd_hermes_migration() -> int:
    """`azzx hermes` was removed in v10.4: print where each feature moved."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
        c = Console()
        t = Table(title="azzx hermes → removed in v10.4 (one unified agent)",
                  box=box.ROUNDED, show_lines=False)
        t.add_column("Old", style="dim")
        t.add_column("New")
        rows = [
            ("hermes think …", "azzx agent \"…\" [--agents planner,coder,…]"),
            ("hermes memory …", "azzx recall search|add|list|delete|rebuild|stats"),
            ("hermes trace", "azzx trace [--limit N] [--kind K]"),
            ("hermes queue …", "azzx queue submit|list|status|result|cancel|resume"),
            ("hermes schedule …", "azzx schedule list|add|remove|run-due"),
            ("hermes stream …", "azzx ask --stream \"…\""),
        ]
        for old, new in rows:
            t.add_row(old, new)
        c.print(t)
        c.print("[dim]The capabilities are unchanged — only the separate "
                "`hermes` mode is gone.[/]")
    except Exception:
        print("azzx hermes was removed in v10.4. Use: agent, recall, trace, queue, schedule, skills.")
    return 2


@_guard
def cmd_agent(args: Any, root: Any = None, forced_provider: str | None = None) -> int:
    """Run the unified multi-agent pipeline against the configured provider."""
    from azzx.agent.multi_agent import MultiAgentOrchestrator

    if getattr(args, "roles", False):
        orch = MultiAgentOrchestrator()
        try:
            from rich.console import Console
            from rich.table import Table
            from rich import box
            c = Console()
            t = Table(title="AZZX agent roles", box=box.ROUNDED)
            t.add_column("Role")
            t.add_column("Read-only")
            t.add_column("Tools")
            t.add_column("Description")
            for p in orch.list_profiles():
                t.add_row(p["name"], "yes" if p["read_only"] else "no",
                          ", ".join(p["allowed_tools"]) or "-",
                          p["description"])
            c.print(t)
        except Exception:
            _print_json(orch.list_profiles())
        return 0

    prompt = " ".join(getattr(args, "text", []) or []).strip()
    if not prompt:
        raise AzzxError("Usage: azzx agent \"<task>\" [--agents planner,coder,…]  (or --roles to list roles)")
    order = [a.strip() for a in (getattr(args, "agents", "") or "").split(",") if a.strip()] or None

    context = ""
    try:  # workspace context is a CLI-layer concern; never break the run
        from azzx_cli import build_workspace_context, load_config
        cfg = load_config()
        context, _selected, _files = build_workspace_context(root, prompt, cfg)
    except Exception:
        context = ""

    orch = MultiAgentOrchestrator()
    yes = bool(getattr(args, "yes", False))
    try:
        result = orch.run_task(
            prompt,
            context=context,
            agent_order=order,
            forced_provider=forced_provider,
            parallel=bool(getattr(args, "parallel", False)),
            fail_fast=bool(getattr(args, "fail_fast", False)),
            session_id=(getattr(args, "session", "") or None),
            noninteractive=yes,
            force_yes=yes,
        )
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        c = Console()
        for entry in result.get("results", []):
            status = entry.get("status", "?")
            color = "green" if status == "ok" else "red"
            title = f"[{entry.get('agent', '?')}] {entry.get('role', '')}  [{color}]{status}[/{color}]"
            if entry.get("provider"):
                title += f"  [dim]{entry['provider']}/{entry.get('model', '')}[/dim]"
            body = entry.get("summary", "") or "(no output)"
            if entry.get("error"):
                body += f"\n\n[red]Error: {entry['error']}[/red]"
            findings = entry.get("findings") or []
            if findings:
                body += "\n\nFindings:\n" + "\n".join(f"- {f}" for f in findings[:8])
            tools = entry.get("tool_calls") or []
            if tools:
                lines = []
                for tc in tools:
                    mark = "✓" if tc.get("ok") else "✗"
                    lines.append(f"{mark} {tc.get('tool')}")
                body += "\n\nTools:\n" + "\n".join(lines)
            c.print(Panel(Markdown(body), title=title, border_style="cyan"))
        failed = result.get("failed_agents") or []
        if failed:
            c.print(f"[yellow]{len(failed)} agent(s) failed: {', '.join(failed)}[/yellow]")
        c.print(f"[dim]pipeline status: {result.get('status')}[/dim]")
    except Exception:
        _print_json(result)
    return 0 if result.get("status") == "ok" else 1


@_guard
def cmd_queue(args: Any) -> int:
    from azzx.agent.orchestrator import register_all as _reg
    from azzx.agent.tasks import TaskQueue, get_task_queue, spawn_drainer

    _reg()
    action = getattr(args, "queue_action", None)
    if action == "submit":
        tool = getattr(args, "tool", "")
        tool_args = _parse_json_arg(getattr(args, "args", "{}") or "{}")
        try:
            REGISTRY.get(tool)
        except AzzxError as exc:
            raise AzzxError(str(exc))
        # No in-process worker for CLI one-shots: the detached drainer owns
        # execution, so a dying CLI process can't half-run the task.
        q = TaskQueue(auto_worker=False)
        task_id = q.submit_tool(tool, tool_args, approved=bool(getattr(args, "yes", False)))
        if not spawn_drainer():
            raise AzzxError("Failed to launch the background worker")
        print(task_id)
        return 0
    q = TaskQueue(auto_worker=False)
    if action == "list":
        status = (getattr(args, "status", "") or "").strip() or None
        _print_json(q.list_tasks(status=status))
        return 0
    if action == "status":
        snap = q.status(getattr(args, "task_id", ""))
        if snap is None:
            # The task may belong to another process's state file — refresh.
            raise AzzxError("task not found")
        _print_json(snap)
        return 0
    if action == "result":
        snap = q.result(getattr(args, "task_id", ""), timeout=float(getattr(args, "wait", 0) or 0))
        if snap is None:
            raise AzzxError("task not found")
        _print_json(snap)
        return 0
    if action == "cancel":
        if not q.cancel(getattr(args, "task_id", "")):
            raise AzzxError("task not found or already running/finished (only queued tasks can be cancelled)")
        print("Task cancelled")
        return 0
    if action == "resume":
        if not q.resume_task(getattr(args, "task_id", "")):
            raise AzzxError("task not found or not resumable (only interrupted/error/cancelled)")
        if not spawn_drainer():
            raise AzzxError("Failed to launch the background worker")
        print("Task requeued")
        return 0
    raise AzzxError("queue action not recognized")


@_guard
def cmd_schedule(args: Any) -> int:
    from azzx.agent.scheduler import ToolScheduler
    register_all()
    scheduler = ToolScheduler()
    action = getattr(args, "schedule_action", "list")
    if action == "list":
        _print_json(scheduler.list())
        return 0
    if action == "add":
        tool_args = _parse_json_arg(getattr(args, "args", "{}") or "{}")
        job = scheduler.add(
            getattr(args, "tool", ""), tool_args,
            int(getattr(args, "every", 3600)),
            getattr(args, "name", ""),
        )
        _print_json(job)
        return 0
    if action == "remove":
        if not scheduler.remove(getattr(args, "job_id", "")):
            raise AzzxError("schedule ID not found")
        print("Schedule removed")
        return 0
    if action == "run-due":
        _print_json(scheduler.run_due(limit=int(getattr(args, "limit", 20))))
        return 0
    raise AzzxError("schedule action not recognized")


@_guard
def cmd_recall(args: Any) -> int:
    """Persistent agent memory: search/add/list/delete/rebuild/stats."""
    from azzx.agent.memory import get_memory_store
    store = get_memory_store()
    action = getattr(args, "recall_action", None)

    if action == "search":
        query = " ".join(getattr(args, "query", []) or []).strip()
        mode = getattr(args, "mode", "hybrid")
        limit = int(getattr(args, "limit", 8) or 8)
        project = (getattr(args, "project", "") or "").strip() or None
        agent = (getattr(args, "agent", "") or "").strip() or None
        if mode == "keyword":
            hits = [(m, 1.0) for m in store.search(query, agent_id=agent, project=project,
                                                   limit=limit, min_importance=0.0)]
        elif mode == "semantic":
            hits = store.search_semantic(query, agent_id=agent, project=project, limit=limit)
        else:
            hits = store.search_hybrid(query, agent_id=agent, project=project, limit=limit)
        rows = [{
            "id": m.id, "score": round(s, 3), "agent": m.agent_id,
            "type": m.memory_type, "importance": m.importance,
            "shared": m.shared, "project": m.project,
            "content": (m.content or "")[:220],
        } for m, s in hits]
        try:
            from rich.console import Console
            from rich.table import Table
            from rich import box
            c = Console()
            t = Table(title=f"Memory ({mode}): {query[:60]}", box=box.ROUNDED)
            for col in ("ID", "Score", "Agent", "Type", "Content"):
                t.add_column(col, justify="right" if col in ("ID", "Score") else "left")
            for r in rows:
                t.add_row(str(r["id"]), str(r["score"]), r["agent"], r["type"], r["content"])
            c.print(t)
        except Exception:
            _print_json(rows)
        return 0

    if action == "add":
        text = " ".join(getattr(args, "text", []) or []).strip()
        if not text:
            raise AzzxError("recall add needs text")
        tags = [t.strip() for t in (getattr(args, "tags", "") or "").split(",") if t.strip()]
        mid = store.store(
            agent_id=(getattr(args, "agent", "") or "user").strip() or "user",
            content=text,
            memory_type=getattr(args, "type", "fact") or "fact",
            importance=float(getattr(args, "importance", 0.7) or 0.7),
            tags=tags,
            shared=not bool(getattr(args, "private", False)),
            project=(getattr(args, "project", "") or "").strip(),
        )
        print(mid)
        return 0

    if action == "list":
        entries = store.get_recent(
            agent_id=(getattr(args, "agent", "") or "").strip() or None,
            project=(getattr(args, "project", "") or "").strip() or None,
            limit=int(getattr(args, "limit", 10) or 10),
            include_private=True,
        )
        _print_json([e.to_dict() for e in entries])
        return 0

    if action == "delete":
        if not store.delete(int(getattr(args, "memory_id", 0))):
            raise AzzxError("memory ID not found")
        print("Memory deleted")
        return 0

    if action == "rebuild":
        n = store.rebuild_vectors()
        print(f"Rebuilt semantic index for {n} memories")
        return 0

    if action == "stats":
        _print_json(store.get_stats())
        return 0

    raise AzzxError("recall action not recognized")


@_guard
def cmd_trace(args: Any) -> int:
    from azzx.agent.tracer import get_tracer
    tracer = get_tracer()
    if getattr(args, "clear", False):
        tracer.clear()
        print("Timeline cleared")
        return 0
    limit = int(getattr(args, "limit", 20) or 20)
    kind = (getattr(args, "kind", "") or "").strip() or None
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
        c.print(f"[dim]spans this session: {stats['spans']} | errors: {stats['errors']} | "
                f"total {stats['total_ms']} ms[/]")
    except Exception:
        _print_json(items)
    return 0


@_guard
def cmd_session(args: Any) -> int:
    from azzx.agent.session import get_session_journal
    journal = get_session_journal()
    action = getattr(args, "session_action", None)

    if action == "start":
        project = (getattr(args, "project", "") or "").strip()
        if not project:
            raise AzzxError("session start needs a PROJECT name")
        title = " ".join(getattr(args, "title", []) or []).strip() or project
        sid = journal.start_session(project, title)
        print(sid)
        return 0

    if action == "log":
        message = " ".join(getattr(args, "message", []) or []).strip()
        if not message:
            raise AzzxError("session log needs a message")
        journal.log_event(
            getattr(args, "session_id", ""),
            (getattr(args, "agent", "") or "user").strip() or "user",
            (getattr(args, "stage", "") or "note").strip() or "note",
            message,
        )
        journal.touch_session(getattr(args, "session_id", ""))
        print("Logged")
        return 0

    if action == "end":
        ok = journal.end_session(
            getattr(args, "session_id", ""),
            status=getattr(args, "status", "done") or "done",
            summary=getattr(args, "summary", "") or "",
        )
        if not ok:
            raise AzzxError("session not found")
        print("Session ended")
        return 0

    if action == "resume":
        try:
            bundle = journal.resume_session(getattr(args, "session_id", ""))
        except KeyError as exc:
            raise AzzxError(str(exc))
        _print_json(bundle)
        return 0

    if action == "list":
        _print_json(journal.get_recent_sessions(
            project=(getattr(args, "project", "") or "").strip() or None,
            status=(getattr(args, "status", "") or "").strip() or None,
        ))
        return 0

    if action == "stale":
        _print_json(journal.find_stale(
            project=(getattr(args, "project", "") or "").strip() or None,
            stale_hours=float(getattr(args, "hours", 24.0) or 24.0),
        ))
        return 0

    raise AzzxError("session action not recognized")


@_guard
def cmd_skills(args: Any) -> int:
    from azzx.agent.skills import SkillRegistry
    reg = SkillRegistry()
    action = getattr(args, "skill_action", None)

    if action == "list":
        rows = []
        for m in reg.list():
            if m.get("error"):
                rows.append({"id": m["id"], "error": m["error"]})
            else:
                rows.append({
                    "id": m["id"], "name": m["name"], "version": m["version"],
                    "description": m["description"][:80],
                    "trusted": m["trusted"], "enabled": m["enabled"],
                    "permissions": m["permissions"],
                })
        _print_json(rows)
        return 0

    if action == "find":
        query = " ".join(getattr(args, "query", []) or []).strip()
        _print_json([{
            "id": m["id"], "name": m["name"], "version": m["version"],
            "description": m["description"][:120],
            "trusted": m["trusted"], "enabled": m["enabled"],
        } for m in reg.find(query)])
        return 0

    if action == "show":
        _print_json(reg._read_manifest(getattr(args, "skill_id", "")))
        return 0

    if action == "install":
        _print_json(reg.install(getattr(args, "source", ""),
                                trust=bool(getattr(args, "trust", False))))
        return 0

    if action == "uninstall":
        if not reg.uninstall(getattr(args, "skill_id", "")):
            raise AzzxError("skill not found")
        print("Skill uninstalled")
        return 0

    if action == "trust":
        _print_json(reg.trust(getattr(args, "skill_id", "")))
        return 0

    if action == "untrust":
        _print_json(reg.untrust(getattr(args, "skill_id", "")))
        return 0

    if action == "enable":
        _print_json(reg.enable(getattr(args, "skill_id", "")))
        return 0

    if action == "disable":
        _print_json(reg.disable(getattr(args, "skill_id", "")))
        return 0

    if action == "invoke":
        tool_args = _parse_json_arg(getattr(args, "args", "{}") or "{}")
        result = reg.invoke(
            getattr(args, "skill_id", ""), tool_args,
            noninteractive=bool(getattr(args, "yes", False)),
            force_yes=bool(getattr(args, "yes", False)),
        )
        _print_json(result)
        return 0

    raise AzzxError("skills action not recognized")

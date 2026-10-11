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
    from azzx.agent.tasks import TaskQueue, spawn_drainer

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
            cron=getattr(args, "cron", "") or "",
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

    if action == "search":
        query = " ".join(getattr(args, "query", []) or []).strip()
        _print_json(journal.search(query, limit=int(getattr(args, "limit", 20) or 20)))
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
        source = getattr(args, "source", "") or ""
        if source.startswith(("http://", "https://", "git@")):
            source = _clone_skill_repo(source)
        _print_json(reg.install(source, trust=bool(getattr(args, "trust", False))))
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


def _clone_skill_repo(url: str) -> str:
    """Shallow-clone a git repo containing a skill; return the local dir.

    If the repo root has no skill.json but exactly one subdirectory does,
    that subdirectory is used. The clone is temporary; install() copies
    what it needs into the registry.
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path as _Path
    if not shutil.which("git"):
        raise AzzxError("git is required to install a skill from URL")
    tmp = _Path(tempfile.mkdtemp(prefix="azzx-skill-clone-"))
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(tmp / "repo")],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise AzzxError("git clone timed out")
    if proc.returncode != 0:
        raise AzzxError(f"git clone failed: {(proc.stderr or '').strip()[:200]}")
    repo = tmp / "repo"
    if (repo / "skill.json").is_file():
        return str(repo)
    candidates = [d for d in repo.iterdir() if d.is_dir() and (d / "skill.json").is_file()
                  and d.name != ".git"]
    if len(candidates) == 1:
        return str(candidates[0])
    raise AzzxError("repo must contain skill.json at root or in exactly one subdirectory")


# ---------------------------------------------------------------------------
# v10.5 — sandbox / planning / learning / checkpoints / autonomy / chat
# ---------------------------------------------------------------------------

@_guard
def cmd_exec(args: Any) -> int:
    """azzx exec run|backends — run a command inside a sandbox."""
    from azzx.agent.sandbox import get_sandbox_executor, register_sandbox_tools
    register_sandbox_tools()
    register_all()
    action = getattr(args, "exec_action", "run")
    if action == "backends":
        _print_json({"backends": get_sandbox_executor().backends()})
        return 0
    # run
    parts = list(getattr(args, "cmdline", "") or "")
    if parts and parts[0] == "--":
        parts = parts[1:]
    command = " ".join(parts).strip()
    if not command:
        raise AzzxError("Usage: azzx exec run -- <command>")
    result = get_sandbox_executor().run(
        command=command,
        workdir=getattr(args, "workdir", "") or None,
        timeout=int(getattr(args, "timeout", 60) or 60),
        backend=getattr(args, "backend", "auto") or "auto",
        allow_network=bool(getattr(args, "allow_network", False)),
    )
    d = result.to_dict()
    try:
        from rich.console import Console
        from rich.panel import Panel
        c = Console()
        color = "green" if d["ok"] else "red"
        body = d["stdout"] or "(no stdout)"
        if d["stderr"]:
            body += "\n\n[dim]stderr:[/]\n" + d["stderr"]
        c.print(Panel(body, title=f"sandbox [{d['backend']}] exit={d['exit_code']} [{color}]{'ok' if d['ok'] else 'failed'}[/{color}]",
                      border_style="cyan"))
    except Exception:
        _print_json(d)
    return 0 if d["ok"] else 1


@_guard
def cmd_plan(args: Any) -> int:
    """azzx plan "<goal>" [--execute] [-y]."""
    from azzx.agent.planning import generate_plan, render_plan_text
    goal = " ".join(getattr(args, "text", []) or []).strip()
    if not goal:
        raise AzzxError('Usage: azzx plan "<goal>" [--execute]')
    plan = generate_plan(goal, project_root=getattr(args, "workdir", "") or ".")
    print(render_plan_text(plan))
    print(f"\n[dim]saved to {plan.get('path')}[/dim]")
    if plan.get("needs_clarification"):
        print("[yellow]The planner has questions — answer them, then re-run with a refined goal.[/yellow]")
        return 0
    if getattr(args, "execute", False):
        from azzx.agent.autonomy import AutonomousRunner
        runner = AutonomousRunner(
            workdir=getattr(args, "workdir", "") or ".",
            auto_approve=bool(getattr(args, "yes", False)),
        )
        # Reuse the approved plan file directly.
        result = _run_plan_file(runner, plan["path"])
        _print_json(result)
        return 0 if result.get("status") == "ok" else 1
    return 0


def _run_plan_file(runner: Any, path: str) -> dict[str, Any]:
    """Execute an already-generated plan file through the autonomy runner."""
    from azzx.agent import planning
    plan = planning.load_plan(path)
    # Drive the runner with the just-generated plan: monkey-patch plan generation.
    # Approval still goes through the runner (asks unless -y was passed).
    orig = planning.generate_plan
    planning.generate_plan = lambda *a, **k: plan  # type: ignore
    try:
        return runner.run(plan.get("goal", ""))
    finally:
        planning.generate_plan = orig


@_guard
def cmd_learn(args: Any) -> int:
    """azzx learn list|approve|discard."""
    from azzx.agent import learning
    action = getattr(args, "learn_action", "list")
    if action == "list":
        _print_json(learning.list_pending())
        return 0
    kind = getattr(args, "kind", "")
    index = int(getattr(args, "index", 0) or 0)
    if action == "approve":
        _print_json(learning.approve(kind, index))
        return 0
    if action == "discard":
        _print_json(learning.discard(kind, index))
        return 0
    raise AzzxError("learn action not recognized (list|approve|discard)")


@_guard
def cmd_checkpoint(args: Any) -> int:
    """azzx checkpoint create|list|rollback|prune."""
    from azzx.agent import checkpoints
    action = getattr(args, "checkpoint_action", "list")
    if action == "create":
        _print_json(checkpoints.create(
            getattr(args, "workdir", "") or ".",
            label=getattr(args, "label", "") or ""))
        return 0
    if action == "list":
        _print_json({"checkpoints": checkpoints.list_checkpoints()})
        return 0
    if action == "rollback":
        cid = getattr(args, "checkpoint_id", "")
        _print_json(checkpoints.rollback(cid, getattr(args, "workdir", "") or None))
        return 0
    if action == "prune":
        _print_json(checkpoints.prune(keep=int(getattr(args, "keep", 20) or 20)))
        return 0
    raise AzzxError("checkpoint action not recognized")


@_guard
def cmd_auto(args: Any) -> int:
    """azzx auto "<goal>" [-y] [--max-steps N] — plan -> approve -> execute -> learn."""
    from azzx.agent.autonomy import AutonomousRunner
    goal = " ".join(getattr(args, "text", []) or []).strip()
    if not goal:
        raise AzzxError('Usage: azzx auto "<goal>" [-y]')
    runner = AutonomousRunner(
        workdir=getattr(args, "workdir", "") or ".",
        max_steps=int(getattr(args, "max_steps", 25) or 25),
        auto_approve=bool(getattr(args, "yes", False)),
        namespace="auto",
        on_event=_auto_event_printer,
    )
    try:
        result = runner.run(goal)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    if result.get("status") == "needs_clarification":
        print("[yellow]The planner needs clarification before executing:[/yellow]")
        for q in result.get("questions", []):
            print(f"  ? {q}")
        return 2
    if result.get("status") == "aborted":
        print("[yellow]Aborted: plan not approved.[/yellow]")
        return 2
    _print_json(result)
    return 0 if result.get("status") == "ok" else 1


def _auto_event_printer(event: dict[str, Any]) -> None:
    kind = event.get("kind")
    try:
        if kind == "step_start":
            s = event.get("step", {})
            print(f"  ▸ [{s.get('id')}] {s.get('title')}  (tool: {s.get('tool')}, risk: {s.get('risk')})")
        elif kind == "step_ok":
            print("    ✓ done")
        elif kind == "step_failed":
            print(f"    ✗ failed: {str(event.get('error', ''))[:160]}")
        elif kind == "checkpoint":
            print(f"    ◈ checkpoint {event.get('id')}")
        elif kind == "replanned":
            print("    ↻ replanned remaining steps")
    except Exception:
        pass


@_guard
def cmd_setup(args: Any) -> int:
    """azzx setup — first-run companion setup (name, language, notes)."""
    from azzx.agent.companion import get_profile, save_profile
    existing = get_profile()
    # Non-interactive flags (scriptable); prompt for whatever is missing.
    name = (getattr(args, "name", "") or "").strip()
    language = (getattr(args, "language", "") or "").strip().lower()
    timezone = (getattr(args, "timezone", "") or "").strip()
    notes = (getattr(args, "notes", "") or "").strip()
    if not name or not language:
        print("AZZX companion setup — ini hanya tersimpan lokal di perangkatmu.\n")
        try:
            if not name:
                name = input(f"Namamu siapa? [{existing.get('name') or ''}]: ").strip() \
                    or existing.get("name", "")
            if not language:
                language = input("Bahasa (id/en) [id]: ").strip().lower() or "id"
            if not timezone:
                timezone = input("Zona waktu mis. Asia/Jakarta [kosongkan]: ").strip()
            if not notes:
                notes = input("Catatan tentangmu (opsional): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup dibatalkan.")
            return 130
    if language not in ("id", "en"):
        language = "id"
    if not name:
        print("Nama wajib diisi agar AZZX bisa menyapamu dengan akrab.")
        return 2
    profile = save_profile({"name": name, "language": language,
                            "timezone": timezone, "notes": notes})
    print(f"\nSiap! Halo {profile['name']} — AZZX sekarang mengenalmu. Coba: azzx chat")
    return 0


@_guard
def cmd_chat(args: Any) -> int:
    """Interactive AZZX chat REPL with slash commands (v10.5)."""
    from azzx.agent.providers import default_router
    from azzx.agent.orchestrator import assemble_memory_prompt
    from azzx.agent.companion import companion_system_prompt

    try:
        from rich.console import Console
        from rich.panel import Panel
        c = Console()
        use_rich = True
    except Exception:
        c = None  # type: ignore
        use_rich = False

    def out(text: str, style: str = "") -> None:
        if use_rich:
            c.print(text, style=style) if style else c.print(text)
        else:
            print(text)

    router = default_router()
    history: list[dict[str, str]] = [
        {"role": "system", "content": companion_system_prompt()},
    ]
    # Workspace root for @file mentions and /add (v10.6.4).
    from pathlib import Path as _Path
    try:
        _root = _Path(getattr(args, "path", None) or ".").expanduser().resolve()
    except Exception:
        _root = _Path.cwd()
    _attached: list[_Path] = []
    if use_rich:
        c.print(Panel("AZZX interactive chat — /help for commands, @file to let the AI "
                      f"read a file. Workspace: {_root}", border_style="cyan"))
    else:
        print("AZZX interactive chat — /help for commands, @file to attach. "
              f"Workspace: {_root}")

    while True:
        try:
            line = input("azzx> ").strip()
        except (EOFError, KeyboardInterrupt):
            out("\nBye.", "dim")
            return 0
        if not line:
            continue
        if line.startswith("/"):
            rc = _chat_slash(line, out, use_rich, history, root=_root, attached=_attached)
            if rc == "quit":
                out("Bye.", "dim")
                return 0
            continue
        # Plain chat -> provider with memory context + file attachments, streamed.
        try:
            from azzx.agent import attachments as AT
            line, _mention_ctx = AT.resolve_mentions(line, _root)
            _sess_ctx = AT.session_attachments(_attached, _root)
            prompt = assemble_memory_prompt(line)
            if _sess_ctx or _mention_ctx:
                prompt = prompt + "\n" + _sess_ctx + _mention_ctx
            messages = history + [{"role": "user", "content": prompt}]
            buf: list[str] = []
            for _pid, token in router.stream(messages):
                buf.append(token)
                if use_rich:
                    c.print(token, end="")
                else:
                    print(token, end="", flush=True)
            text = "".join(buf)
            if use_rich:
                c.print()
            else:
                print()
            history += [{"role": "user", "content": line}, {"role": "assistant", "content": text}]
            history = history[-20:]
        except KeyboardInterrupt:
            out("\n(interrupted)", "dim")
        except Exception as exc:
            out(f"Error: {exc}", "red")


def _chat_slash(line: str, out: Any, use_rich: bool, history: list,
                root=None, attached=None) -> Any:
    parts = line.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit", "/q"):
        return "quit"
    if cmd == "/help":
        out("Commands:\n"
            "  /plan <goal>     generate an execution plan\n"
            "  /auto <goal>     autonomous run (plan -> approve -> execute -> learn)\n"
            "  /agent <task>    multi-agent pipeline\n"
            "  /add <file>      attach a file to this session (AI can read it)\n"
            "  /added           list attached files\n"
            "  /unadd <file>    detach a file\n"
            "  /learn           show staged learnings\n"
            "  /remember <fakta> simpan fakta/preferensi tentangmu ke memori\n"
            "  /memory <q>      search persistent memory\n"
            "  /skills          list skills\n"
            "  /trace           recent execution timeline\n"
            "  /clear           clear chat history\n"
            "  /quit            exit\n"
            "Tip: mention @path/to/file in any message to let the AI read it.")
        return None
    if cmd == "/add":
        from azzx.agent import attachments as AT
        if not arg:
            out("Usage: /add <file> — attach a file so the AI can read it", "yellow")
            return None
        p = AT.resolve_in_root(root, arg.strip())
        if p is None:
            out(f"Tidak bisa attach: {arg.strip()} (tidak ada / di luar workspace)", "red")
            return None
        if attached is not None and p not in attached:
            attached.append(p)
        out(f"✓ Attached: {p.name} (AI bisa membacanya sekarang)", "green")
        return None
    if cmd == "/added":
        if not attached:
            out("(belum ada file ter-attach — pakai /add <file> atau @file di pesan)", "dim")
        else:
            out("Attached:\n" + "\n".join(f"  • {p}" for p in attached))
        return None
    if cmd == "/unadd":
        if not arg or not attached:
            out("Usage: /unadd <file>", "yellow")
            return None
        before = len(attached)
        attached[:] = [p for p in attached if p.name != arg.strip() and str(p) != arg.strip()]
        out("✓ Detached." if len(attached) < before else "Tidak ada yang cocok.", "green")
        return None
    if cmd == "/remember":
        if not arg:
            out("Usage: /remember <fakta tentangmu>", "yellow")
            return None
        from azzx.agent.companion import remember_fact
        try:
            res = remember_fact(arg)
            out(f"✓ Diingat: {res['stored']}", "green")
        except Exception as exc:
            out(f"Tidak disimpan: {exc}", "red")
        return None
    if cmd == "/clear":
        system = history[0] if history and history[0].get("role") == "system" else None
        history.clear()
        if system:
            history.append(system)
        out("✓ Chat history dibersihkan.", "green")
        return None
    if cmd == "/plan":
        if not arg:
            out("Usage: /plan <goal>", "yellow")
            return None
        from azzx.agent.planning import generate_plan, render_plan_text
        plan = generate_plan(arg)
        out(render_plan_text(plan))
        return None
    if cmd == "/auto":
        if not arg:
            out("Usage: /auto <goal>", "yellow")
            return None
        from azzx.agent.autonomy import AutonomousRunner
        runner = AutonomousRunner(auto_approve=False, on_event=_auto_event_printer)
        try:
            result = runner.run(arg)
        except KeyboardInterrupt:
            out("\nCancelled.", "dim")
            return None
        import json as _json
        out(_json.dumps(result, indent=2, ensure_ascii=False, default=str)[:3000])
        return None
    if cmd == "/agent":
        if not arg:
            out("Usage: /agent <task>", "yellow")
            return None
        from azzx.agent.multi_agent import MultiAgentOrchestrator
        result = MultiAgentOrchestrator().run_task(arg)
        for entry in result.get("results", []):
            out(f"[{entry.get('agent')}] {entry.get('summary', '')[:400]}")
        return None
    if cmd == "/learn":
        from azzx.agent import learning
        import json as _json
        out(_json.dumps(learning.list_pending(), indent=2, ensure_ascii=False)[:3000])
        out("(use `azzx learn approve|discard <memory|skill> <index>`)", "dim")
        return None
    if cmd == "/memory":
        from azzx.agent.memory import get_memory_store
        hits = get_memory_store().search_hybrid(query=arg or "", limit=8)
        for m, s in hits:
            out(f"[{s:.2f}] {m.content[:160]}")
        return None
    if cmd == "/skills":
        from azzx.agent.skills import get_skill_registry
        for sk in get_skill_registry().list():
            out(f"- {sk.get('id')}  trusted={sk.get('trusted')} enabled={sk.get('enabled')}")
        return None
    if cmd == "/trace":
        from azzx.agent.tracer import get_tracer
        for i in get_tracer().recent_from_log(10):
            out(f"- {i.get('name', '')} [{i.get('kind')}] {i.get('status', '')}")
        return None
    out(f"Unknown command: {cmd}  (try /help)", "yellow")
    return None


@_guard
def cmd_gateway(args: Any) -> int:
    """azzx gateway telegram — run the messaging gateway."""
    import os
    platform = getattr(args, "gateway_platform", "")
    if platform != "telegram":
        raise AzzxError("Only 'telegram' gateway is available in v10.5")
    from azzx.gateway.telegram import TelegramGateway
    token = getattr(args, "token", "") or os.environ.get("AZZX_TELEGRAM_TOKEN", "")
    if not token:
        raise AzzxError("Bot token required: --token <token> or AZZX_TELEGRAM_TOKEN env")
    allow_raw = getattr(args, "allow_from", "") or ""
    allow_from = {int(x) for x in allow_raw.split(",") if x.strip().isdigit()} or None
    gw = TelegramGateway(token, allow_from=allow_from,
                         auto_approve=bool(getattr(args, "yes", False)))
    gw.run_forever()
    return 0



@_guard
def cmd_gui(args: Any) -> int:
    """azzx gui — friendly ChatGPT-like web chat UI."""
    from azzx.gui.server import run_gui
    run_gui(
        host=getattr(args, "host", "127.0.0.1") or "127.0.0.1",
        port=int(getattr(args, "port", 8766) or 8766),
        open_browser=bool(getattr(args, "open", False)),
    )
    return 0


@_guard
def cmd_browse(args: Any) -> int:
    """azzx browse fetch|links|mode|forms|submit — web reader + write mode."""
    action = getattr(args, "browse_action", "fetch")
    if action == "mode":
        from azzx.agent import webforms as WF
        value = (getattr(args, "value", "") or "").strip().lower()
        if value:
            mode = WF.set_browser_mode(value)
            warn = ""
            if mode == "write":
                warn = (" — WRITE mode: the agent may submit HTML forms "
                        "(HTTP-level, no JS). Each submit still asks permission.")
            print(f"Browser mode = {mode}{warn}")
        else:
            print(f"Browser mode = {WF.browser_mode()} (read|write)")
        return 0
    if action == "forms":
        from azzx.agent import webforms as WF
        _print_json(WF.forms(getattr(args, "url", "")))
        return 0
    if action == "submit":
        from azzx.agent import webforms as WF
        from azzx.agent.orchestrator import run_tool_call
        fields: dict[str, str] = {}
        for item in getattr(args, "field", []) or []:
            if "=" in item:
                k, v = item.split("=", 1)
                fields[k.strip()] = v
        result = run_tool_call("web.submit", {
            "url": getattr(args, "url", ""),
            "form_index": int(getattr(args, "form", 0) or 0),
            "fields": fields,
            "session": getattr(args, "session", "default") or "default",
        }, force_yes=bool(getattr(args, "yes", False)))
        _print_json(result)
        return 0
    from azzx.agent.webreader import fetch
    url = getattr(args, "url", "")
    page = fetch(url)
    if action == "links":
        _print_json({"url": page["final_url"], "title": page["title"], "links": page["links"]})
        return 0
    try:
        from rich.console import Console
        from rich.panel import Panel
        c = Console()
        c.print(Panel(page["text"] or "(no readable text)",
                      title=f"{page['title'] or page['final_url']}",
                      subtitle=page["final_url"], border_style="cyan"))
    except Exception:
        _print_json({"url": page["final_url"], "title": page["title"], "text": page["text"]})
    return 0


@_guard
def cmd_connector(args: Any) -> int:
    """azzx connector setup|list|remove — app connectors (GitHub, email)."""
    from azzx.agent import connectors as C
    action = getattr(args, "connector_action", "list")
    if action == "list":
        rows = []
        for name, cfg in C.load_connectors().items():
            rows.append({"name": name, "type": cfg.get("type"),
                         "detail": {k: v for k, v in cfg.items()
                                    if k not in ("type",) and "vault" not in str(v)}})
        _print_json({"connectors": rows})
        return 0
    if action == "setup":
        name = getattr(args, "name", "")
        if name == "github":
            _print_json(C.setup_github())
        elif name == "email":
            _print_json(C.setup_email())
        else:
            raise AzzxError("available connectors: github, email")
        return 0
    if action == "remove":
        name = getattr(args, "name", "")
        data = C.load_connectors()
        if name not in data:
            raise AzzxError("connector not found")
        del data[name]
        C.save_connectors(data)
        print(f"Connector '{name}' removed (vault secrets kept; delete manually if needed)")
        return 0
    raise AzzxError("connector action not recognized")




@_guard
def cmd_webauto(args: Any) -> int:
    """azzx webauto "<task>" — autonomous goal-driven browsing (read/write)."""
    from azzx.agent.webagent import WebAgent
    task = getattr(args, "task", "")
    write = bool(getattr(args, "write", False))
    if write:
        from azzx.agent.webforms import browser_mode, WRITE
        if browser_mode() != WRITE:
            raise AzzxError("webauto --write needs browser write mode: azzx browse mode write")
    agent = WebAgent(max_steps=int(getattr(args, "max_steps", 12) or 12),
                     write_mode=write,
                     noninteractive_submit=bool(getattr(args, "yes", False)))
    result = agent.run(task, start_url=getattr(args, "start_url", None) or None)
    try:
        from rich.console import Console
        from rich.panel import Panel
        c = Console()
        status = result.get("status")
        if status == "answered":
            c.print(Panel(result["answer"], title="🌐 webauto — jawaban",
                          subtitle=f"{result['steps']} halaman dikunjungi",
                          border_style="green"))
        else:
            c.print(Panel(f"status: {status}\n"
                          f"alasan: {result.get('reason', '-')}\n"
                          f"jejak: {', '.join(result.get('trail', [])[:5])}",
                          title="🌐 webauto", border_style="yellow"))
        if getattr(args, "verbose", False):
            _print_json(result)
    except Exception:
        _print_json(result)
    return 0 if result.get("status") == "answered" else 2


@_guard
def cmd_browse_search(args: Any) -> int:
    """azzx browse search — web search via DuckDuckGo."""
    from azzx.agent.webreader import search
    _print_json({"results": search(getattr(args, "query", ""),
                                   int(getattr(args, "limit", 8) or 8))})
    return 0


@_guard
def cmd_audit(args: Any) -> int:
    """azzx audit list|stats|report — did the agent do it right?"""
    from azzx.agent import auditor as A
    action = getattr(args, "audit_action", "stats")
    if action == "list":
        limit = int(getattr(args, "limit", 30) or 30)
        run_id = getattr(args, "run", "") or ""
        entries = A.recent_calls(limit=limit, run_id=run_id)
        rows = [{"ts": e.get("ts"), "run": (e.get("run_id") or "")[:12],
                 "tool": e.get("tool"),
                 "ok": e.get("ok"),
                 "ms": e.get("duration_ms"),
                 "err": (e.get("error_kind") or "") if not e.get("ok") else ""}
                for e in entries]
        _print_json({"entries": rows})
        return 0
    if action == "stats":
        _print_json(A.stats())
        return 0
    if action == "report":
        run_id = getattr(args, "run", "") or ""
        if not run_id:
            raise AzzxError("audit report needs --run <id> (see `azzx audit list`)")
        rep = A.report(run_id)
        if getattr(args, "judge", False):
            try:
                rep["llm_judge"] = A.judge(run_id)
            except Exception as exc:
                rep["llm_judge_error"] = str(exc)[:200]
        try:
            from rich.console import Console
            from rich.panel import Panel
            c = Console()
            color = {"pass": "green", "needs_work": "yellow", "fail": "red"}.get(
                rep["rule_verdict"], "white")
            body = (f"Skor aturan: [bold]{rep['rule_score']}/100[/] "
                    f"([{color}]{rep['rule_verdict']}[/])\n"
                    f"Calls: {rep['calls']} — ok {rep['ok']}, gagal {rep['failed']}\n")
            if rep["findings"]:
                body += "\nTemuan:\n" + "\n".join(f"• {f}" for f in rep["findings"])
            else:
                body += "\nTidak ada temuan — bersih."
            if rep.get("llm_judge"):
                j = rep["llm_judge"]
                body += (f"\n\n[bold]Penilaian AI:[/] {j.get('score')}/100 "
                         f"({j.get('verdict')})\n"
                         + "\n".join(f"• {i}" for i in (j.get("issues") or [])[:5]))
            c.print(Panel(body, title=f"Audit {run_id[:16]}", border_style=color))
            if getattr(args, "verbose", False):
                _print_json(rep)
        except Exception:
            _print_json(rep)
        return 0 if rep["rule_verdict"] == "pass" else 2
    raise AzzxError("audit action not recognized")


@_guard
def cmd_compress(args: Any) -> int:
    """azzx compress <file> — shrink a big file before it enters AI context."""
    from azzx.agent.compressor import compress_file
    res = compress_file(
        getattr(args, "file", ""),
        budget_chars=int(getattr(args, "budget", 8000) or 8000),
        strategy=getattr(args, "strategy", "auto") or "auto",
        query=getattr(args, "query", "") or "",
    )
    try:
        from rich.console import Console
        from rich.panel import Panel
        c = Console()
        c.print(Panel(
            f"Strategi: [cyan]{res['strategy']}[/] — "
            f"{res['original_chars']:,} → {res['compressed_chars']:,} chars "
            f"(~{res['original_tokens_est']:,} → ~{res['compressed_tokens_est']:,} tokens, "
            f"rasio {res['ratio']*100:.0f}%)",
            title=f"Compressed {res['file']}", border_style="cyan"))
        if not getattr(args, "quiet", False):
            print(res["text"][:20000])
    except Exception:
        _print_json({k: v for k, v in res.items() if k != "text"})
        if not getattr(args, "quiet", False):
            print(res["text"][:20000])
    return 0


def cmd_do(args: Any, root: Any, forced: Any = None) -> int:
    """azzx do "<natural language>" — smart intent router (v10.6.6).

    The single front door: detects intent from Indonesian/English keywords
    (offline, deterministic) and runs the right pipeline. Always prints
    which command it routes to, so users learn the underlying commands.
    """
    from azzx.agent.intent import route, describe_target

    text = " ".join(getattr(args, "text", []) or []).strip()
    if not text:
        print("Usage: azzx do \"<apa yang mau dikerjakan>\"\n"
              "Contoh:\n"
              "  azzx do \"perbaiki bug login\"\n"
              "  azzx do \"buatkan fungsi hitung diskon\"\n"
              "  azzx do \"review kode ini\"\n"
              "  azzx do \"cari harga kopi hari ini\"\n"
              "  azzx do \"ingat bahwa saya suka kopi tubruk\"")
        return 2
    target, task, score = route(text)
    print(f"→ {target}: {describe_target(target)}")
    if getattr(args, "dry_run", False):
        print(f"(dry-run: task = {task!r})")
        return 0

    import azzx_cli as A
    if target == "fix":
        return 0 if A.run_edit_task(root, task, "fix", forced) else 1
    if target == "implement":
        return 0 if A.run_edit_task(root, task, "implement", forced) else 1
    if target == "review":
        A.run_review(root, task, forced)
        return 0
    if target == "debug":
        A.run_debug(root, task, forced)
        return 0
    if target == "test":
        return 0 if A.run_tests(root, task or None) else 1
    if target == "web":
        from azzx.agent.webagent import WebAgent
        agent = WebAgent()
        res = agent.run(task)
        print(res.get("answer", res))
        return 0 if res.get("status") == "answered" else 2
    if target == "fetch":
        from azzx.agent.webreader import fetch
        page = fetch(task.split()[0] if task else "")
        print(page.get("text", "")[:8000])
        return 0
    if target == "remember":
        from azzx.agent.companion import remember_fact
        res = remember_fact(task)
        print(f"✓ Diingat: {res.get('stored', task)}")
        return 0
    if target == "recall":
        from azzx.agent.orchestrator import get_memory_store
        store = get_memory_store()
        hits = store.search_hybrid(query=task, limit=5) or []
        if not hits:
            print("(tidak ada memori yang cocok)")
        for entry, _s in hits:
            print(f"• {getattr(entry, 'content', '')[:200]}")
        return 0
    if target == "plan":
        from azzx.agent.planning import generate_plan, render_plan_text
        print(render_plan_text(generate_plan(task)))
        return 0
    if target == "auto":
        from azzx.agent.autonomy import AutonomousRunner
        res = AutonomousRunner(auto_approve=False).run(task)
        print(f"status: {res.get('status')}")
        return 0
    if target == "compress":
        from azzx.agent.compressor import compress_file
        res = compress_file(task.split()[0] if task else "")
        print(f"compressed {res['original_chars']} → {res['compressed_chars']} chars "
              f"({res['strategy']})")
        return 0
    if target == "doctor":
        A.doctor(False)
        return 0
    if target == "checkpoint":
        from azzx.agent import checkpoints
        res = checkpoints.create(str(root), label=task or "do-checkpoint")
        print(f"✓ Checkpoint: {res}")
        return 0
    if target == "schedule":
        from types import SimpleNamespace
        return cmd_schedule(SimpleNamespace(schedule_action="list"))
    if target == "audit":
        from types import SimpleNamespace
        return cmd_audit(SimpleNamespace(audit_action="list", limit=15, run=""))
    if target == "extend":
        return cmd_extend(SimpleNamespace(text=[task], dry_run=False), root, forced)
    if target == "evolve":
        return cmd_evolve(SimpleNamespace(evolve_action="analyze"), root, forced)
    # fallback: ask
    A.run_ask(root, task or text, forced)
    return 0


def cmd_help(args: Any) -> int:
    """azzx help — the curated command guide (v10.6.6)."""
    groups = [
        ("MULAI DARI SINI", [
            ("do \"<tugas>\"", "Perintah pintar — ketik bahasa sehari-hari, AZZX yang routing"),
            ("chat", "Ngobrol dengan AZZX (bisa @file, /add)"),
            ("gui", "Tampilan web seperti ChatGPT"),
        ]),
        ("BANGUN & PERBAIKI", [
            ("fix \"<masalah>\"", "Perbaiki kode (auto recall + learn)"),
            ("implement \"<fitur>\"", "Bangun fitur baru"),
            ("review", "Review kode"),
            ("test", "Jalankan test project"),
            ("auto \"<tujuan>\"", "Mode otonom: plan → approve → execute → learn"),
        ]),
        ("WEB", [
            ("webauto \"<tugas>\"", "Browsing yang menyelesaikan tugas sendiri"),
            ("browse fetch <url>", "Ambil halaman sebagai teks"),
            ("browse mode [read|write]", "Mode browser"),
        ]),
        ("MEMORI & BELAJAR", [
            ("remember \"<fakta>\"", "Simpan fakta ke memori"),
            ("recall \"<q>\"", "Cari di memori"),
            ("learn", "Lihat usulan learning (staged)"),
        ]),
        ("SISTEM", [
            ("setup", "Setup awal"), ("ai", "Setup AI provider (termasuk Ollama lokal)"),
            ("doctor", "Cek kesehatan"), ("audit", "Audit pekerjaan agent"),
            ("schedule", "Jadwalkan tugas"), ("checkpoint", "Checkpoint project"),
        ]),
    ]
    try:
        from rich.console import Console
        from rich.table import Table
        c = Console()
        for title, rows in groups:
            t = Table(title=title, show_header=False, border_style="dim")
            t.add_column("cmd", style="cyan")
            t.add_column("desc")
            for cmd, desc in rows:
                t.add_row(f"azzx {cmd}", desc)
            c.print(t)
        c.print("\n[dim]Semua 93 command tetap bisa dipakai langsung — ini hanya jalan pintas.[/]")
    except Exception:
        for title, rows in groups:
            print(f"\n== {title} ==")
            for cmd, desc in rows:
                print(f"  azzx {cmd:28s} {desc}")
    return 0


def cmd_extend(args: Any, root: Any, forced: Any = None) -> int:
    """azzx extend "<request>" — AZZX builds a new skill for itself (v10.6.9)."""
    from azzx.agent.selfextend import extend_feature, generate_skill

    text = " ".join(getattr(args, "text", []) or []).strip()
    if not text:
        print("Usage: azzx extend \"<fitur yang diinginkan>\"\n"
              "Contoh:\n"
              "  azzx extend \"buatkan tool untuk menghitung kata di file\"\n"
              "  azzx extend \"skill untuk convert celsius ke fahrenheit\"\n"
              "\nHasilnya berupa skill baru (untrusted + disabled).\n"
              "Review kodenya, lalu aktifkan manual:\n"
              "  azzx skills trust <id> && azzx skills enable <id>")
        return 2
    if getattr(args, "dry_run", False):
        print(f"Would generate a skill for: {text!r}")
        print("(dry-run: no AI call, nothing installed)")
        return 0
    print(f"→ Generating skill for: {text}")
    print("  (AI menulis kode → validasi → install sebagai untrusted+disabled)")
    try:
        result = extend_feature(text, forced)
    except Exception as exc:
        print(f"✗ Gagal: {exc}")
        return 1
    print(f"\n✓ Skill '{result['skill_id']}' v{result['version']} dibuat "
          f"({result['handler_lines']} baris).")
    print("  Status: UNTRUSTED + DISABLED (aman — tidak aktif otomatis).")
    print("\nLangkah selanjutnya:")
    for step in result["next_steps"]:
        print(f"  • {step}")
    return 0


def cmd_evolve(args: Any, root: Any, forced: Any = None) -> int:
    """azzx evolve analyze|propose|proposals|approve|reject — self-improvement (v10.6.10)."""
    from azzx.agent import evolve as E

    action = getattr(args, "evolve_action", "") or "analyze"
    if action == "analyze":
        f = E.analyze()
        print(f"Observasi dari {f['total_calls']} tool calls:")
        if f.get("note"):
            print(f"  {f['note']}")
            return 0
        print("\n  Kebiasaan (tool tersering):")
        for t in f["top_tools"][:5]:
            print(f"    • {t['tool']}: {t['calls']}x")
        if f["failure_hotspots"]:
            print("\n  Titik kegagalan:")
            for h in f["failure_hotspots"]:
                print(f"    • {h['tool']}: {h['total']} error {h['errors']}")
        if f["common_sequences"]:
            print("\n  Pola berulang:")
            for s in f["common_sequences"]:
                print(f"    • {s['first']} → {s['then']}: {s['count']}x")
        if f["denied_count"]:
            print(f"\n  Permission ditolak: {f['denied_count']}x")
        print("\nJalankan `azzx evolve propose` untuk minta AI membuat usulan perbaikan.")
        return 0
    if action == "propose":
        print("→ Menganalisis kebiasaan & meminta AI membuat usulan...")
        try:
            res = E.propose(forced_provider=forced)
        except Exception as exc:
            print(f"✗ Gagal: {exc}")
            return 1
        if res.get("staged", 0) == 0:
            print(f"  {res.get('note', 'tidak ada usulan')}")
            return 0
        print(f"✓ {res['staged']} usulan dibuat (BELUM diterapkan).")
        print(f"  Review: azzx evolve proposals")
        return 0
    if action == "proposals":
        items = E.list_proposals()
        if not items:
            print("Tidak ada usulan pending. Jalankan `azzx evolve propose`.")
            return 0
        for p in items:
            print(f"\n[{p['id']}] ({p['type']}/{p['risk']}) {p['title']}")
            print(f"  {p['description']}")
            for ch in p.get("changes", []):
                print(f"    → {ch.get('kind')}: {ch.get('file') or ch.get('detail', '')[:60]}")
        print(f"\nTerapkan: azzx evolve approve <id>   |   Tolak: azzx evolve reject <id>")
        return 0
    if action == "approve":
        pid = getattr(args, "proposal_id", "")
        try:
            # NB: no project_root — self-modification targets the AZZX
            # installation itself (azzx_install_root()), not the user's cwd.
            res = E.approve(pid, force=getattr(args, "force", False),
                            auto_yes=getattr(args, "yes", False),
                            forced_provider=forced)
        except Exception as exc:
            print(f"✗ Gagal: {exc}")
            return 1
        print(f"✓ Proposal {res['id']} diterapkan (checkpoint: {res['checkpoint']}).")
        for a in res["applied"]:
            print(f"  • {a}")
        if res.get("note"):
            print(f"  Catatan: {res['note']}")
        return 0
    if action == "reject":
        pid = getattr(args, "proposal_id", "")
        try:
            E.reject(pid)
        except Exception as exc:
            print(f"✗ Gagal: {exc}")
            return 1
        print(f"✓ Proposal {pid} ditolak.")
        return 0
    print(f"Unknown evolve action: {action}")
    return 2

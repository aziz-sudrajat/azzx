"""AI orchestrator: tool registry, NL mapping, memory-aware prompts, multi-agent (v10.1)."""
from __future__ import annotations

import re
from typing import Any

from azzx.agent.memory import MemoryStore, get_memory_store as _memory_store_factory
from azzx.agent.message_bus import get_message_bus as _message_bus_factory
from azzx.agent.multi_agent import MultiAgentOrchestrator, get_multi_agent_orchestrator
from azzx.agent.skills import register_skill_tools
from azzx.agent.streaming import AgentStream, stream_task_progress
from azzx.agent.tracer import get_tracer
from azzx.core import DATA_HOME, REGISTRY, AzzxError
from azzx.device import register_all_device_tools
from azzx.plugins.loader import load_enabled_plugins, register_plugin_tools
from azzx.tools import register_all_toolkit_tools
from azzx.workflow.engine import register_workflow_tools

_REGISTERED = False
_MEMORY_STORE: MemoryStore | None = None
_MULTI_AGENT: MultiAgentOrchestrator | None = None


def register_all() -> None:
    """Register all tool categories."""
    global _REGISTERED
    if _REGISTERED:
        return
    register_all_toolkit_tools()
    register_workflow_tools()
    register_all_device_tools()
    register_plugin_tools()
    try:
        register_skill_tools()
    except Exception:  # noqa: BLE001 — skills must not break boot
        pass
    try:
        load_enabled_plugins()
    except Exception:  # noqa: BLE001 — plugins must not break boot
        pass
    _REGISTERED = True


def get_memory_store() -> MemoryStore:
    """Get or initialize the global memory store."""
    global _MEMORY_STORE
    if _MEMORY_STORE is None:
        _MEMORY_STORE = _memory_store_factory()
    return _MEMORY_STORE


def get_orchestrator() -> MultiAgentOrchestrator:
    """Get or initialize the global multi-agent orchestrator."""
    global _MULTI_AGENT
    if _MULTI_AGENT is None:
        _MULTI_AGENT = get_multi_agent_orchestrator()
    return _MULTI_AGENT


def get_message_bus() -> Any:
    """Get the global agent message bus."""
    return _message_bus_factory()


def describe_tools_for_ai() -> list[dict[str, Any]]:
    """Describe available tools with full schema for AI orchestration."""
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
    """Execute a registered tool call with permission checks (traced)."""
    register_all()
    tracer = get_tracer()
    with tracer.span(f"tool:{name}", kind="tool", tool=name, args=args or {}):
        return REGISTRY.call(name, args or {}, noninteractive=noninteractive, force_yes=force_yes or noninteractive)


def assemble_memory_prompt(user_prompt: str, agent_id: str | None = None, project_context: str = "") -> str:
    """Build an enhanced prompt with relevant memory context."""
    memory_store = get_memory_store()
    query_terms = " ".join(user_prompt.split()[:15])
    try:
        hits = memory_store.search_hybrid(query=user_prompt, agent_id=agent_id, limit=10)
        memories = [entry for entry, _ in hits if entry.importance >= 0.5]
    except Exception:
        memories = memory_store.search(query=query_terms, agent_id=agent_id, limit=10, min_importance=0.5)

    enhanced = user_prompt
    if memories:
        memory_section = "\n\n[CONTEXT FROM PREVIOUS SESSIONS]\n"
        for memory in memories:
            importance_indicator = "⭐" * int(memory.importance * 3)
            memory_section += f"{importance_indicator} [{memory.memory_type}] {memory.content}\n"
        enhanced = user_prompt + memory_section

    if project_context:
        enhanced = f"[PROJECT CONTEXT]\n{project_context}\n\n" + enhanced

    return enhanced


def run_multi_agent_task(prompt: str, context: str = "", agent_order: list[str] | None = None) -> dict[str, Any]:
    """Execute a task across multiple agents with persistent memory."""
    orchestrator = get_orchestrator()
    return orchestrator.run_task(prompt=prompt, context=context, agent_order=agent_order)


def stream_multi_agent_task(prompt: str, context: str = "", agent_order: list[str] | None = None) -> list[dict[str, Any]]:
    """Return an agent execution stream suitable for a terminal UI."""
    orchestrator = get_orchestrator()
    events = [
        {"kind": "start", "message": "Starting multi-agent workflow", "step": "orchestrator"},
    ]
    for agent in agent_order or ["planner", "coder", "reviewer", "tester", "security"]:
        result = orchestrator.delegate(prompt, agent, context=context)
        events.append({
            "kind": "progress",
            "message": result["output"],
            "step": agent,
            "metadata": {"agent": agent},
        })
    events.append({"kind": "done", "message": "Multi-agent workflow completed", "step": "orchestrator"})
    return stream_task_progress("multi-agent-task", events)


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
    """Map a simple natural-language request to a registered tool call."""
    text = (text or "").strip()
    if not text:
        return None
    for pattern, tool, args in _NL_PATTERNS:
        if pattern.search(text):
            return {"tool": tool, "args": dict(args), "matched": pattern.pattern}

    m = re.search(r"(?i)\b(check|status|ping)\s+(https?:/\S+)", text)
    if m:
        return {"tool": "net.website", "args": {"url": m.group(2)}, "matched": "website"}

    m = re.search(r"(?i)\b(sha256|md5|sha1|checksum)\s+(\S+)", text)
    if m:
        return {
            "tool": "hash.file",
            "args": {"path": m.group(2), "algorithm": m.group(1) if m.group(1) != "checksum" else "sha256"},
            "matched": "hash",
        }
    return None


__all__ = [
    "register_all",
    "describe_tools_for_ai",
    "run_tool_call",
    "map_nl_to_tool",
    "get_memory_store",
    "get_orchestrator",
    "get_message_bus",
    "run_multi_agent_task",
    "stream_multi_agent_task",
    "assemble_memory_prompt",
]

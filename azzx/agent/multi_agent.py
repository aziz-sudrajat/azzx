"""Native multi-agent collaboration for AZZX (v10.4).

One unified agent. Roles (planner, researcher, coder, reviewer, tester,
security) are *personas with tool allowlists* that delegate real work to the
configured AI provider — never canned responses.

Pipeline per delegation:
    role prompt + memory context + allowed tools
      -> provider chat (bounded tokens, cancellable)
      -> structured JSON result (summary / findings / actions / tool_requests)
      -> orchestrator executes *allowed* tool_requests via the permission-
         enforcing registry, feeds results back for one follow-up pass
      -> final structured result handed to the next agent

Sequential execution is the default (reliable on lightweight devices).
Parallel fan-out is only permitted when every selected agent is read-only.
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from azzx.agent.message_bus import get_message_bus
from azzx.agent.memory import MemoryStore, get_memory_store
from azzx.agent.reasoning import ReasoningTrace
from azzx.agent.tracer import get_tracer
from azzx.core import AzzxError, DATA_HOME

_RESPONSE_CONTRACT = """\
Respond with a single JSON object and nothing else — no prose outside the JSON.
Shape:
{
  "summary": "2-4 sentence result for this role",
  "findings": ["concrete finding 1", "..."],
  "actions": ["what was done or should be done next"],
  "tool_requests": [{"tool": "<tool name>", "args": {}}],
  "needs": ["what the next agent needs from you"]
}
Rules:
- "tool_requests" may only name tools from the ALLOWED TOOLS list below; others will be refused.
- Keep "tool_requests" minimal — only tools whose output you genuinely need.
- Do not reveal chain-of-thought or internal deliberation; only the structured result above.
"""

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_structured(text: str) -> dict[str, Any]:
    """Best-effort parse of the agent's structured response.

    Returns {"summary","findings","actions","tool_requests","needs"}.
    Never raises: unparseable output becomes the summary verbatim.
    """
    fallback = {
        "summary": (text or "").strip()[:4000],
        "findings": [],
        "actions": [],
        "tool_requests": [],
        "needs": [],
    }
    candidate = (text or "").strip()
    if not candidate:
        fallback["summary"] = "(empty response from provider)"
        return fallback
    m = _JSON_BLOCK_RE.search(candidate)
    raw = m.group(1) if m else candidate
    # Tolerate leading/trailing prose: find the outermost JSON object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return fallback
    if not isinstance(obj, dict):
        return fallback

    def _str_list(v: Any) -> list[str]:
        return [str(x)[:2000] for x in v if isinstance(v, list)][:20] if isinstance(v, list) else []

    tool_requests: list[dict[str, Any]] = []
    if isinstance(obj.get("tool_requests"), list):
        for item in obj["tool_requests"][:10]:
            if isinstance(item, dict) and item.get("tool"):
                args = item.get("args")
                tool_requests.append({
                    "tool": str(item["tool"]),
                    "args": args if isinstance(args, dict) else {},
                })
    return {
        "summary": str(obj.get("summary") or fallback["summary"])[:4000],
        "findings": _str_list(obj.get("findings")),
        "actions": _str_list(obj.get("actions")),
        "tool_requests": tool_requests,
        "needs": _str_list(obj.get("needs")),
    }


@dataclass
class AgentProfile:
    """A role persona: prompt, tool allowlist, and execution budget."""

    name: str
    role: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    read_only: bool = True
    model: str = ""          # "" = provider default
    max_tokens: int = 1500
    memory_access: bool = True
    priority: int = 100

    def tool_allowed(self, tool_name: str) -> bool:
        for allowed in self.allowed_tools:
            if allowed.endswith("."):
                if tool_name.startswith(allowed):
                    return True
            elif tool_name == allowed:
                return True
        return False


def _planner_prompt() -> str:
    return (
        "You are the PLANNER of the AZZX agent team. Break the user's request into "
        "an actionable plan: concrete steps in order, risks/unknowns, and clear "
        "deliverables. Prefer the smallest safe scope. Do not write code yourself; "
        "produce the plan other agents will execute."
    )


def _researcher_prompt() -> str:
    return (
        "You are the RESEARCHER of the AZZX agent team. Gather facts needed for the "
        "task: inspect files, check system/network state, look up references. Use "
        "tool_requests for anything you cannot answer from the context given. "
        "Report evidence with paths, versions, and exact observations."
    )


def _coder_prompt() -> str:
    return (
        "You are the CODER of the AZZX agent team. Propose the minimal concrete "
        "change that satisfies the request: exact file paths, precise edits, and "
        "why each edit is safe. You may inspect files via tool_requests. Keep the "
        "change surface small and backwards compatible."
    )


def _reviewer_prompt() -> str:
    return (
        "You are the REVIEWER of the AZZX agent team. Critically evaluate the "
        "proposed work: correctness, edge cases, maintainability, API "
        "compatibility, and alignment with the request. List concrete issues "
        "with severity; approve explicitly only when there is nothing material "
        "left to fix."
    )


def _tester_prompt() -> str:
    return (
        "You are the TESTER of the AZZX agent team. Define and (via tool_requests "
        "where possible) run focused validation: the smallest checks that prove "
        "the change works and nothing nearby regressed. Report pass/fail per "
        "check with evidence. Never claim a test passed unless it actually ran."
    )


def _security_prompt() -> str:
    return (
        "You are the SECURITY REVIEWER of the AZZX agent team. Assess the work "
        "for: secret leakage, unsafe shell/command construction, path traversal, "
        "permission overreach, unvalidated external input, and dependency risk. "
        "Be conservative: flag anything uncertain and say what would make it safe."
    )


class MultiAgentOrchestrator:
    """Role-based orchestration backed by the configured AI provider."""

    def __init__(
        self,
        memory_dir: str | Any | None = None,
        router: Any | None = None,
    ) -> None:
        self.memory_store = MemoryStore(memory_dir or DATA_HOME / "agent")
        self.message_bus = get_message_bus()
        # router is injected in tests (MockAdapter-backed); lazily built otherwise
        # so importing this module never requires provider configuration.
        self._router = router
        self.profiles = {
            "planner": AgentProfile(
                name="planner", role="planner",
                description="Breaks requests into actionable plans, risks, deliverables.",
                system_prompt=_planner_prompt(),
                allowed_tools=[], read_only=True, priority=10,
            ),
            "researcher": AgentProfile(
                name="researcher", role="researcher",
                description="Gathers evidence: files, system state, references.",
                system_prompt=_researcher_prompt(),
                allowed_tools=["fs.", "net.", "sys.info", "sys.health", "hash.file", "json."],
                read_only=True, priority=15,
            ),
            "coder": AgentProfile(
                name="coder", role="coder",
                description="Proposes minimal, safe code changes.",
                system_prompt=_coder_prompt(),
                allowed_tools=["fs.", "hash.file", "json.", "archive."],
                read_only=True, priority=20,
            ),
            "reviewer": AgentProfile(
                name="reviewer", role="reviewer",
                description="Checks correctness, edge cases, compatibility.",
                system_prompt=_reviewer_prompt(),
                allowed_tools=["fs.", "sys.info", "sys.health", "hash.file"],
                read_only=True, priority=30,
            ),
            "tester": AgentProfile(
                name="tester", role="tester",
                description="Defines and runs focused validation checks.",
                system_prompt=_tester_prompt(),
                allowed_tools=["fs.", "sys.info", "sys.health", "sys.processes", "hash.file", "json."],
                read_only=True, priority=40,
            ),
            "security": AgentProfile(
                name="security", role="security",
                description="Reviews permissions, secrets, unsafe execution paths.",
                system_prompt=_security_prompt(),
                allowed_tools=["fs.", "sys.", "hash.file"],
                read_only=True, priority=50,
            ),
        }

    # -- wiring ---------------------------------------------------------
    def _get_router(self) -> Any:
        if self._router is None:
            from azzx.agent.providers import default_router
            self._router = default_router()
        return self._router

    def get_profile(self, name: str) -> AgentProfile | None:
        return self.profiles.get(name)

    def list_profiles(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name, "role": p.role, "description": p.description,
                "read_only": p.read_only, "allowed_tools": p.allowed_tools,
                "max_tokens": p.max_tokens,
            }
            for p in sorted(self.profiles.values(), key=lambda p: p.priority)
        ]

    # -- memory ----------------------------------------------------------
    def remember(self, agent_id: str, content: str, memory_type: str = "fact",
                 importance: float = 0.7, tags: list[str] | None = None,
                 shared: bool = True, project: str = "") -> str:
        return self.memory_store.store(
            agent_id=agent_id, content=content, memory_type=memory_type,
            importance=importance, tags=tags or [], shared=shared, project=project,
        )

    def _memory_context(self, prompt: str, agent_id: str | None = None, limit: int = 5) -> str:
        if not prompt:
            return "No relevant memories found."
        hits = self.memory_store.search_hybrid(query=prompt, agent_id=agent_id, limit=limit)
        relevant = [(m, s) for m, s in hits if m.importance >= 0.4]
        if not relevant:
            return "No relevant memories found."
        lines = ["Relevant memory from previous sessions:"]
        for m, _ in relevant:
            lines.append(f"- [{m.agent_id}:{m.memory_type}] {m.content[:400]}")
        return "\n".join(lines)

    # -- delegation -------------------------------------------------------
    def _build_messages(self, profile: AgentProfile, task: str, context: str,
                        prior: list[dict[str, Any]], tool_results: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        from azzx.agent.orchestrator import describe_tools_for_ai, register_all
        register_all()
        tool_lines = []
        for t in describe_tools_for_ai():
            if profile.tool_allowed(t["name"]):
                tool_lines.append(f"- {t['name']}: {t['description']}")
        allowed = "\n".join(tool_lines) if tool_lines else "(no tools available to this role)"

        system = (
            f"{profile.system_prompt}\n\n"
            f"ALLOWED TOOLS:\n{allowed}\n\n{_RESPONSE_CONTRACT}"
        )
        memory_ctx = self._memory_context(task, agent_id=profile.name) if profile.memory_access else ""
        user_parts = [f"TASK: {task}"]
        if context:
            user_parts.append(f"CONTEXT:\n{context[:6000]}")
        if memory_ctx:
            user_parts.append(f"MEMORY:\n{memory_ctx[:3000]}")
        if prior:
            chain = "\n".join(
                f"[{p['agent']}] {p.get('summary', '')[:800]}" for p in prior
            )
            user_parts.append(f"PREVIOUS AGENTS' RESULTS:\n{chain[:4000]}")
        if tool_results:
            rendered = "\n".join(
                f"[{r['tool']}] ok={r['ok']}: {str(r.get('result') or r.get('error'))[:1500]}"
                for r in tool_results
            )
            user_parts.append(f"TOOL RESULTS:\n{rendered[:4000]}")
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    def _execute_tool_requests(
        self,
        profile: AgentProfile,
        requests: list[dict[str, Any]],
        noninteractive: bool,
        force_yes: bool,
    ) -> list[dict[str, Any]]:
        from azzx.agent.orchestrator import run_tool_call
        outcomes: list[dict[str, Any]] = []
        for req in requests:
            tool = str(req.get("tool", ""))
            args = req.get("args") or {}
            if not profile.tool_allowed(tool):
                outcomes.append({
                    "tool": tool, "args": args, "ok": False,
                    "error": f"denied: '{tool}' is not in {profile.name}'s allowed tools",
                })
                continue
            try:
                result = run_tool_call(tool, args, noninteractive=noninteractive, force_yes=force_yes)
                outcomes.append({"tool": tool, "args": args, "ok": True, "result": result})
            except Exception as exc:  # noqa: BLE001 — surfaced in the result
                outcomes.append({"tool": tool, "args": args, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return outcomes

    def delegate(
        self,
        task: str,
        agent: str,
        context: str = "",
        prior: list[dict[str, Any]] | None = None,
        forced_provider: str | None = None,
        cancel_event: threading.Event | None = None,
        noninteractive: bool = False,
        force_yes: bool = False,
        max_tool_rounds: int = 1,
    ) -> dict[str, Any]:
        """Run one role against the task via the configured AI provider."""
        profile = self.get_profile(agent)
        if profile is None:
            raise ValueError(f"Unknown agent profile: {agent}")
        prior = prior or []
        tracer = get_tracer()
        trace = ReasoningTrace(task=task, agent=agent)
        tool_calls: list[dict[str, Any]] = []
        status = "ok"
        error: str | None = None
        parsed: dict[str, Any] = {}
        provider_id = model = ""
        attempts = 0

        def _chat(msgs: list[dict[str, str]]) -> str:
            nonlocal provider_id, model, attempts
            router = self._get_router()
            result = router.chat_role(
                msgs, role=profile.role,
                forced_provider=forced_provider,
                cancel_event=cancel_event,
                max_tokens=profile.max_tokens,
            )
            provider_id, model, attempts = result.provider_id, result.model, result.attempts
            return result.text

        with tracer.span(f"delegate:{agent}", kind="agent", task=task[:120]):
            trace.think(f"Routing to '{agent}' ({profile.role}, read_only={profile.read_only}).")
            self.message_bus.send(
                sender="orchestrator", recipient=agent, body=task, kind="delegation",
                metadata={"context": context[:500], "profile": profile.role},
                correlation_id=f"task-{agent}",
            )
            try:
                trace.plan("Initial provider call with role prompt, memory, and tool contract.")
                with tracer.span("provider.chat", kind="agent", agent=agent):
                    text = _chat(self._build_messages(profile, task, context, prior, None))
                trace.act(f"Provider responded ({len(text)} chars) via {provider_id}/{model}.")
                parsed = _parse_structured(text)
                trace.observe(f"Parsed summary + {len(parsed['tool_requests'])} tool request(s).")

                rounds = 0
                while parsed["tool_requests"] and rounds < max_tool_rounds:
                    rounds += 1
                    trace.act(f"Executing {len(parsed['tool_requests'])} tool request(s) (round {rounds}).")
                    with tracer.span("agent.tools", kind="tool", agent=agent):
                        outcomes = self._execute_tool_requests(
                            profile, parsed["tool_requests"],
                            noninteractive=noninteractive, force_yes=force_yes,
                        )
                    tool_calls.extend(outcomes)
                    trace.observe(f"{sum(1 for o in outcomes if o['ok'])}/{len(outcomes)} tool call(s) succeeded.")
                    with tracer.span("provider.chat.followup", kind="agent", agent=agent):
                        text = _chat(self._build_messages(profile, task, context, prior, tool_calls))
                    parsed = _parse_structured(text)

                trace.reflect("Result references the task scope and stays within the role.")
                trace.conclude(f"Delegation to '{agent}' complete: {status}.")
            except Exception as exc:  # noqa: BLE001 — failures are visible, not hidden
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                trace.observe(f"Delegation failed: {error}")
                trace.conclude(f"Delegation to '{agent}' failed.")
                parsed = parsed or {
                    "summary": f"(agent {agent} failed: {error})",
                    "findings": [], "actions": [], "tool_requests": [], "needs": [],
                }

            with tracer.span("memory.remember", kind="memory"):
                try:
                    self.remember(
                        agent_id=agent,
                        content=f"Task: {task[:500]}\nResult: {parsed.get('summary', '')[:800]}",
                        memory_type="decision", importance=0.6,
                        tags=[agent, "delegated"], shared=True,
                    )
                except Exception:
                    pass  # memory must never break delegation
            self.message_bus.send(
                sender=agent, recipient="orchestrator", body=parsed.get("summary", ""),
                kind="result", metadata={"task": task[:300], "status": status},
                correlation_id=f"result-{agent}",
            )

        return {
            "agent": agent,
            "role": profile.role,
            "status": status,
            "error": error,
            "summary": parsed.get("summary", ""),
            "findings": parsed.get("findings", []),
            "actions": parsed.get("actions", []),
            "needs": parsed.get("needs", []),
            "tool_calls": tool_calls,
            "provider": provider_id,
            "model": model,
            "attempts": attempts,
            "reasoning": trace.to_dict(),
        }

    def collaborate(
        self,
        agents: list[str],
        prompt: str,
        context: str = "",
        forced_provider: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Parallel fan-out. Only safe for read-only roles; others run sequentially."""
        for name in agents:
            profile = self.get_profile(name)
            if profile is None:
                raise ValueError(f"Unknown agent profile: {name}")
            if not profile.read_only:
                raise AzzxError(
                    f"Parallel collaborate() refused: '{name}' is not read-only. "
                    "Use run_task() (sequential) for roles that may change state."
                )
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(4, len(agents))) as pool:
            futures = [
                pool.submit(self.delegate, prompt, name, context, None, forced_provider, cancel_event)
                for name in agents
            ]
            for fut in futures:
                results.append(fut.result())
        return {"status": "ok", "prompt": prompt, "context": context,
                "participants": agents, "results": results}

    def run_task(
        self,
        prompt: str,
        context: str = "",
        agent_order: list[str] | None = None,
        forced_provider: str | None = None,
        parallel: bool = False,
        fail_fast: bool = False,
        cancel_event: threading.Event | None = None,
        session_id: str | None = None,
        noninteractive: bool = False,
        force_yes: bool = False,
    ) -> dict[str, Any]:
        """Sequential multi-agent pipeline (default). Each agent sees prior summaries."""
        order = agent_order or ["planner", "coder", "reviewer", "tester", "security"]
        unknown = [a for a in order if a not in self.profiles]
        if unknown:
            raise ValueError(f"Unknown agent profile(s): {', '.join(unknown)}")
        if parallel:
            non_readonly = [a for a in order if not self.profiles[a].read_only]
            if non_readonly:
                raise AzzxError(
                    f"Parallel run refused for non-read-only role(s): {', '.join(non_readonly)}. "
                    "Run sequentially or pick read-only roles."
                )
            return self.collaborate(order, prompt, context, forced_provider, cancel_event)

        tracer = get_tracer()
        journal = None
        if session_id:
            from azzx.agent.session import get_session_journal
            journal = get_session_journal()
        final: list[dict[str, Any]] = []
        failed: list[str] = []
        with tracer.span("run_task", kind="task", prompt=prompt[:160]):
            if journal:
                journal.log_event(session_id, "orchestrator", "start",
                                  f"multi-agent task started: {prompt[:200]}")
            self.remember(agent_id="system", content=f"Task: {prompt[:500]}",
                           memory_type="interaction", importance=0.9,
                           tags=["task", "session"], shared=True)
            for agent_name in order:
                if cancel_event is not None and cancel_event.is_set():
                    from azzx.agent.providers import CancelledError
                    raise CancelledError("multi-agent run cancelled by user")
                agent_result = self.delegate(
                    prompt, agent_name, context=context, prior=final,
                    forced_provider=forced_provider, cancel_event=cancel_event,
                    noninteractive=noninteractive, force_yes=force_yes,
                )
                final.append(agent_result)
                if journal:
                    journal.log_event(
                        session_id, agent_name, "agent_result",
                        agent_result["summary"][:500],
                        metadata={"status": agent_result["status"]},
                    )
                if agent_result["status"] == "error":
                    failed.append(agent_name)
                    if fail_fast:
                        break
            if journal:
                journal.log_event(session_id, "orchestrator", "end",
                                  f"multi-agent task finished ({len(failed)} failed)")

        ok_count = sum(1 for r in final if r["status"] == "ok")
        return {
            "status": "ok" if not failed else ("partial" if ok_count else "failed"),
            "prompt": prompt, "context": context,
            "agents_used": [e["agent"] for e in final],
            "failed_agents": failed,
            "results": final,
            "final_summary": final[-1]["summary"] if final else "",
        }


_DEFAULT_MULTI_AGENT: MultiAgentOrchestrator | None = None


def get_multi_agent_orchestrator() -> MultiAgentOrchestrator:
    """Process-wide lazy orchestrator (builds no provider client until first use)."""
    global _DEFAULT_MULTI_AGENT
    if _DEFAULT_MULTI_AGENT is None:
        _DEFAULT_MULTI_AGENT = MultiAgentOrchestrator()
    return _DEFAULT_MULTI_AGENT


def run_multi_agent_task(prompt: str, context: str = "",
                         agent_order: list[str] | None = None) -> dict[str, Any]:
    return get_multi_agent_orchestrator().run_task(prompt=prompt, context=context, agent_order=agent_order)


__all__ = [
    "AgentProfile", "MultiAgentOrchestrator",
    "get_multi_agent_orchestrator", "run_multi_agent_task",
]

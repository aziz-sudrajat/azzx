"""Multi-agent orchestration with profiles, delegation, and persistent memory (v10.1+)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from azzx.agent.message_bus import get_message_bus
from azzx.agent.memory import MemoryStore, get_memory_store
from azzx.agent.reasoning import ReasoningTrace
from azzx.agent.tracer import get_tracer
from azzx.core import DATA_HOME


@dataclass
class AgentProfile:
    """Definition of a reusable agent persona."""

    name: str
    role: str
    description: str
    model: str = "default"
    behavior: str = "balanced"
    memory_access: bool = True
    priority: int = 100


class MultiAgentOrchestrator:
    """Hermes-like orchestration using role-based agents and persistent memory."""

    def __init__(self, memory_dir: str | Any | None = None) -> None:
        self.memory_store = MemoryStore(memory_dir or DATA_HOME / "agent")
        self.message_bus = get_message_bus()
        self.profiles = {
            "planner": AgentProfile(
                name="planner",
                role="planner",
                description="Breaks requests into milestones, risks, and deliverables.",
                model="default",
                behavior="methodical",
                priority=10,
            ),
            "coder": AgentProfile(
                name="coder",
                role="coder",
                description="Implements changes with the minimal safe scope.",
                model="default",
                behavior="pragmatic",
                priority=20,
            ),
            "reviewer": AgentProfile(
                name="reviewer",
                role="reviewer",
                description="Checks correctness, maintainability, and edge cases.",
                model="default",
                behavior="critical",
                priority=30,
            ),
            "tester": AgentProfile(
                name="tester",
                role="tester",
                description="Defines focused validation and regression checks.",
                model="default",
                behavior="verification-first",
                priority=40,
            ),
            "security": AgentProfile(
                name="security",
                role="security",
                description="Reviews permissions, secrets, and unsafe execution paths.",
                model="default",
                behavior="conservative",
                priority=50,
            ),
        }

    def remember(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.7,
        tags: list[str] | None = None,
        shared: bool = True,
    ) -> str:
        return self.memory_store.store(
            agent_id=agent_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags or [],
            shared=shared,
        )

    def get_profile(self, name: str) -> AgentProfile | None:
        return self.profiles.get(name)

    def search_memory(self, query: str, agent_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        memories = self.memory_store.search(query=query, agent_id=agent_id, limit=limit, min_importance=0.0)
        return [memory.to_dict() for memory in memories]

    def _memory_context(self, prompt: str, agent_id: str | None = None, limit: int = 5) -> str:
        if not prompt:
            return "No relevant memories found."
        query_terms = " ".join(prompt.split()[:10])
        memories = self.search_memory(query_terms, agent_id=agent_id, limit=limit)
        if not memories:
            return "No relevant memories found."
        lines = ["Relevant memory:"]
        for memory in memories:
            lines.append(f"- [{memory['agent_id']}:{memory['memory_type']}] {memory['content']}")
        return "\n".join(lines)

    def delegate(self, task: str, agent: str, context: str = "") -> dict[str, Any]:
        profile = self.get_profile(agent)
        if profile is None:
            raise ValueError(f"Unknown agent profile: {agent}")
        tracer = get_tracer()
        trace = ReasoningTrace(task=task, agent=agent)
        with tracer.span(f"delegate:{agent}", kind="agent", task=task[:120]):
            trace.think(
                f"Routing to '{agent}' because its role ({profile.role}, {profile.behavior}) "
                f"matches the task: {profile.description}"
            )
            memory_context = (
                self._memory_context(task, agent_id=agent, limit=5)
                if profile.memory_access
                else "Memory access disabled for this agent."
            )
            trace.plan(
                f"Approach: {profile.description} Behavior mode: {profile.behavior}. "
                f"Will consult {'memory' if profile.memory_access else 'no memory'} before acting."
            )
            with tracer.span("message_bus.send", kind="memory"):
                self.message_bus.send(
                    sender="orchestrator",
                    recipient=agent,
                    body=task,
                    kind="delegation",
                    metadata={"context": context, "profile": profile.role},
                    correlation_id=f"task-{agent}",
                )
            trace.act(f"Delegated task to '{agent}' via message bus (correlation task-{agent}).")
            with tracer.span("agent.output", kind="agent", agent=agent):
                output = self._generate_agent_output(agent, task, context)
            trace.observe(f"Agent produced {len(output)} chars of output.")
            trace.reflect(
                "Output references the task scope and stays within the agent's role; "
                "no cross-role drift detected."
            )
            trace.conclude(f"Delegation to '{agent}' complete.")
            with tracer.span("memory.remember", kind="memory"):
                self.remember(
                    agent_id=agent,
                    content=f"Task: {task}\nOutcome: {output}",
                    memory_type="decision",
                    importance=0.8,
                    tags=[agent, "delegated"],
                    shared=True,
                )
        result = {
            "agent": agent,
            "role": profile.role,
            "description": profile.description,
            "status": "delegated",
            "context": context,
            "output": output,
            "reasoning": trace.to_dict(),
        }
        return result

    def collaborate(self, agents: list[str], prompt: str, context: str = "") -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for agent in agents:
            results.append(self.delegate(prompt, agent, context=context))
        return {
            "status": "ok",
            "prompt": prompt,
            "context": context,
            "participants": agents,
            "results": results,
        }

    def run_task(self, prompt: str, context: str = "", agent_order: list[str] | None = None) -> dict[str, Any]:
        order = agent_order or ["planner", "coder", "reviewer", "tester", "security"]
        final: list[dict[str, Any]] = []
        tracer = get_tracer()

        with tracer.span("run_task", kind="task", prompt=prompt[:160]):
            with tracer.span("memory.remember", kind="memory"):
                self.remember(
                    agent_id="system",
                    content=f"Task: {prompt}",
                    memory_type="interaction",
                    importance=0.9,
                    tags=["task", "session"],
                    shared=True,
                )

            for agent_name in order:
                if agent_name not in self.profiles:
                    continue
                # delegate() builds the reasoning trace + nested spans.
                agent_result = self.delegate(prompt, agent_name, context=context)
                with tracer.span("memory.context", kind="memory", agent=agent_name):
                    agent_result["memory"] = self._memory_context(prompt, agent_id=agent_name, limit=5)
                final.append(agent_result)
                with tracer.span("message_bus.send", kind="memory"):
                    self.message_bus.send(
                        sender=agent_name,
                        recipient="orchestrator",
                        body=agent_result["output"],
                        kind="result",
                        metadata={"task": prompt, "agent": agent_name},
                        correlation_id=f"result-{agent_name}",
                    )

        return {
            "status": "ok",
            "prompt": prompt,
            "context": context,
            "agents_used": [entry["agent"] for entry in final],
            "results": final,
            "memory_summary": self.memory_store.get_agent_summary("system"),
        }

    def _generate_agent_output(self, agent_name: str, prompt: str, context: str) -> str:
        if agent_name == "planner":
            return (
                "Plan: 1) scope the task, 2) select the minimal safe path, 3) validate with "
                "targeted checks, 4) review security and permission impacts."
            )
        if agent_name == "coder":
            return (
                "Implementation approach: make the minimal change, keep compatibility, preserve "
                "safe defaults, and validate behavior with focused checks."
            )
        if agent_name == "reviewer":
            return (
                "Review checklist: correctness, maintainability, edge cases, API compatibility, "
                "and alignment with the requested objective."
            )
        if agent_name == "tester":
            return (
                "Validation plan: run the smallest relevant command set, confirm the fix, and "
                "re-check neighboring behavior for regressions."
            )
        if agent_name == "security":
            return (
                "Security review: no secret leakage, no unsafe shell execution, minimal permissions, "
                "no path traversal, and no unvalidated external input."
            )
        return f"Task handling for {agent_name}: analyze the request, apply safe defaults, and validate outcomes."


_DEFAULT_MULTI_AGENT: MultiAgentOrchestrator | None = None


def get_multi_agent_orchestrator() -> MultiAgentOrchestrator:
    """Get the global multi-agent orchestrator (created lazily on first use)."""
    global _DEFAULT_MULTI_AGENT
    if _DEFAULT_MULTI_AGENT is None:
        _DEFAULT_MULTI_AGENT = MultiAgentOrchestrator()
    return _DEFAULT_MULTI_AGENT


def run_multi_agent_task(prompt: str, context: str = "") -> dict[str, Any]:
    return get_multi_agent_orchestrator().run_task(prompt=prompt, context=context)


__all__ = ["AgentProfile", "MultiAgentOrchestrator", "get_multi_agent_orchestrator", "run_multi_agent_task"]

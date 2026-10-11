"""Explicit reasoning traces for native agent delegation (v10.2+).

Instead of jumping straight to an answer, an agent records its reasoning
as an ordered trace: thought -> plan -> act -> observe -> reflect ->
conclusion. The trace is inspectable, auditable, and renderable in the
terminal or dashboard.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

STEP_KINDS = ("thought", "plan", "act", "observe", "reflect", "conclusion")


@dataclass
class ThoughtStep:
    kind: str
    content: str
    at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "content": self.content,
            "at": self.at,
            "metadata": self.metadata,
        }


class ReasoningTrace:
    """An explicit reasoning trace for one task."""

    def __init__(self, task: str, agent: str = "") -> None:
        self.task = task
        self.agent = agent
        self.started_at = time.time()
        self.steps: list[ThoughtStep] = []

    def add(self, kind: str, content: str, **metadata: Any) -> ThoughtStep:
        if kind not in STEP_KINDS:
            raise ValueError(f"unknown step kind: {kind!r} (expected one of {STEP_KINDS})")
        step = ThoughtStep(kind=kind, content=str(content), metadata=metadata)
        self.steps.append(step)
        return step

    # Convenience builders -------------------------------------------------
    def think(self, content: str, **meta: Any) -> ThoughtStep:
        return self.add("thought", content, **meta)

    def plan(self, content: str, **meta: Any) -> ThoughtStep:
        return self.add("plan", content, **meta)

    def act(self, content: str, **meta: Any) -> ThoughtStep:
        return self.add("act", content, **meta)

    def observe(self, content: str, **meta: Any) -> ThoughtStep:
        return self.add("observe", content, **meta)

    def reflect(self, content: str, **meta: Any) -> ThoughtStep:
        return self.add("reflect", content, **meta)

    def conclude(self, content: str, **meta: Any) -> ThoughtStep:
        return self.add("conclusion", content, **meta)

    # Introspection ---------------------------------------------------------
    @property
    def duration_s(self) -> float:
        return round(time.time() - self.started_at, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "agent": self.agent,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
            "steps": [s.to_dict() for s in self.steps],
        }

    def render(self, width: int = 88) -> str:
        """Plain-text rendering for terminal display."""
        icons = {
            "thought": "💭",
            "plan": "🗺️",
            "act": "⚙️",
            "observe": "👁️",
            "reflect": "🪞",
            "conclusion": "✅",
        }
        lines = [f"Reasoning trace — {self.agent or 'agent'}: {self.task[:width]}".rstrip()]
        for step in self.steps:
            icon = icons.get(step.kind, "•")
            label = step.kind.upper().ljust(10)
            lines.append(f"  {icon} {label} {step.content}")
        return "\n".join(lines)


__all__ = ["ReasoningTrace", "ThoughtStep", "STEP_KINDS"]

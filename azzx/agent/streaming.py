from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class StreamEvent:
    """A single streaming event for progress or agent updates."""

    kind: str
    message: str
    step: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "step": self.step,
            "metadata": dict(self.metadata),
        }


class AgentStream:
    """Minimal streaming layer for interactive terminal and task reporting."""

    def __init__(self) -> None:
        self.events: list[StreamEvent] = []

    def emit(self, kind: str, message: str, step: str | None = None, **metadata: Any) -> StreamEvent:
        event = StreamEvent(kind=kind, message=message, step=step, metadata=metadata)
        self.events.append(event)
        return event

    def as_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]

    def step(self, name: str, status: str, detail: str = "") -> StreamEvent:
        return self.emit("step", detail or status, step=name, status=status)


class TokenStream:
    """Accumulates token-by-token LLM output for live display (v10.2).

    Feed raw token chunks via `feed()`; iterate or read `.text` for the
    full response so far. Thread-safe for adapter callbacks.
    """

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self._chunks: list[str] = []
        self.finished = False
        self.provider_id = ""
        self.model = ""

    def feed(self, token: str) -> None:
        if token:
            with self._lock:
                self._chunks.append(token)

    def finish(self, provider_id: str = "", model: str = "") -> str:
        self.finished = True
        self.provider_id = provider_id
        self.model = model
        return self.text

    @property
    def text(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    def __iter__(self):  # yields a snapshot; adapters stream via feed()
        return iter(self.text)


def stream_task_progress(task_name: str, events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    stream = AgentStream()
    stream.emit("start", f"Starting {task_name}")
    for payload in events or []:
        stream.emit(payload.get("kind", "update"), str(payload.get("message", "")), step=payload.get("step"), **payload.get("metadata", {}))
    stream.emit("done", f"Completed {task_name}")
    return stream.as_dicts()


__all__ = ["AgentStream", "StreamEvent", "TokenStream", "stream_task_progress"]


if __name__ == "__main__":
    print(stream_task_progress("demo", [{"kind": "progress", "message": "Analyzing", "step": "planner"}]))

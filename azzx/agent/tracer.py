"""Hermes-like observability: execution tracing with spans (v10.2).

A lightweight, dependency-free tracer. Spans nest naturally via a
thread-local stack, so tool calls inside agent workflows produce a proper
timeline: who called what, how long it took, and whether it succeeded.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from azzx.core import DATA_HOME


class Span:
    """One timed unit of work in the execution timeline."""

    def __init__(self, name: str, kind: str = "task", parent_id: str | None = None) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.kind = kind  # task | tool | agent | memory | reasoning | queue
        self.parent_id = parent_id
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.status = "running"
        self.attributes: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.error: str | None = None

    @property
    def duration_ms(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.time()
        return round((end - self.started_at) * 1000, 2)

    def set(self, key: str, value: Any) -> "Span":
        self.attributes[key] = value
        return self

    def event(self, name: str, **fields: Any) -> "Span":
        self.events.append({"name": name, "at": time.time(), **fields})
        return self

    def finish(self, status: str = "ok", error: str | None = None) -> "Span":
        self.ended_at = time.time()
        self.status = status
        if error:
            self.error = error
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
            "error": self.error,
        }


class Tracer:
    """Collects spans; thread-safe; persists a JSONL timeline."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self._spans: list[Span] = []
        self.log_path = (
            Path(log_path)
            if log_path
            else DATA_HOME / "agent" / "trace.jsonl"
        )

    def _stack(self) -> list[Span]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    @contextmanager
    def span(self, name: str, kind: str = "task", **attrs: Any) -> Iterator[Span]:
        stack = self._stack()
        parent = stack[-1] if stack else None
        span = Span(name, kind, parent.id if parent else None)
        for key, value in attrs.items():
            span.set(key, value)
        stack.append(span)
        try:
            yield span
            span.finish("ok")
        except Exception as exc:  # noqa: BLE001
            span.finish("error", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            stack.pop()
            with self._lock:
                self._spans.append(span)
            self._persist(span)

    def _persist(self, span: Span) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(span.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def current(self) -> Span | None:
        stack = self._stack()
        return stack[-1] if stack else None

    def timeline(self, limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
        """Newest-first timeline of finished spans (in-memory)."""
        with self._lock:
            spans = list(self._spans)
        if kind:
            spans = [s for s in spans if s.kind == kind]
        spans.sort(key=lambda s: s.started_at, reverse=True)
        return [s.to_dict() for s in spans[: max(1, limit)]]

    def recent_from_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read the persisted timeline (survives process restarts)."""
        if not self.log_path.exists():
            return []
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        items: list[dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
        return list(reversed(items))

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()
        try:
            if self.log_path.exists():
                self.log_path.unlink()
        except OSError:
            pass

    def stats(self) -> dict[str, Any]:
        with self._lock:
            spans = list(self._spans)
        by_kind: dict[str, int] = {}
        total_ms = 0.0
        errors = 0
        for span in spans:
            by_kind[span.kind] = by_kind.get(span.kind, 0) + 1
            total_ms += span.duration_ms
            if span.status == "error":
                errors += 1
        return {
            "spans": len(spans),
            "by_kind": by_kind,
            "total_ms": round(total_ms, 2),
            "errors": errors,
        }


_TRACER: Tracer | None = None
_TRACER_LOCK = threading.Lock()


def get_tracer() -> Tracer:
    """Process-wide lazy tracer (creates no files until a span finishes)."""
    global _TRACER
    if _TRACER is None:
        with _TRACER_LOCK:
            if _TRACER is None:
                _TRACER = Tracer()
    return _TRACER


__all__ = ["Span", "Tracer", "get_tracer"]

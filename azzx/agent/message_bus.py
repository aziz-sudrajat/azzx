from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class MessageEnvelope:
    """A simple message passed between agents."""

    sender: str
    recipient: str | None
    body: str
    kind: str = "message"
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "body": self.body,
            "kind": self.kind,
            "metadata": dict(self.metadata),
            "correlation_id": self.correlation_id,
        }


class MessageBus:
    """Lightweight local message bus for native agent coordination.

    This intentionally avoids heavy dependencies and remains usable on Termux.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Any]] = defaultdict(list)
        self._queue: deque[MessageEnvelope] = deque()
        self._lock = Lock()

    def subscribe(self, recipient: str, callback: Any) -> None:
        with self._lock:
            self._subscribers[recipient].append(callback)

    def publish(self, message: MessageEnvelope) -> MessageEnvelope:
        with self._lock:
            self._queue.append(message)
        self._dispatch(message)
        return message

    def send(
        self,
        sender: str,
        recipient: str | None,
        body: str,
        kind: str = "message",
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> MessageEnvelope:
        message = MessageEnvelope(
            sender=sender,
            recipient=recipient,
            body=body,
            kind=kind,
            metadata=metadata or {},
            correlation_id=correlation_id,
        )
        return self.publish(message)

    def _dispatch(self, message: MessageEnvelope) -> None:
        if message.recipient is None:
            for callbacks in self._subscribers.values():
                for cb in callbacks:
                    try:
                        cb(message)
                    except Exception:  # pragma: no cover - best effort bus callback
                        pass
            return
        for callback in self._subscribers.get(message.recipient, []):
            try:
                callback(message)
            except Exception:  # pragma: no cover
                pass

    def get_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            result = [msg.to_dict() for msg in list(self._queue)]
        return result

    def flush(self) -> list[dict[str, Any]]:
        with self._lock:
            result = [msg.to_dict() for msg in list(self._queue)]
            self._queue.clear()
        return result


DEFAULT_MESSAGE_BUS = MessageBus()


def get_message_bus() -> MessageBus:
    return DEFAULT_MESSAGE_BUS


__all__ = ["MessageBus", "MessageEnvelope", "get_message_bus"]

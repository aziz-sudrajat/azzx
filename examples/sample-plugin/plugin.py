"""Sample AZZX v9 plugin."""
from __future__ import annotations

from typing import Any


def echo(message: str = "hello") -> dict[str, Any]:
    # No shell, no filesystem side effects
    return {"echo": str(message)[:500]}


def register(registry) -> None:
    from azzx.core import ToolSpec

    registry.register(ToolSpec(
        name="sample.echo",
        description="Echo a message (sample plugin)",
        permissions=[],
        handler=echo,
        schema={"message": "str"},
    ))

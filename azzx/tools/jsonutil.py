"""JSON formatter / validator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError


def json_format(path: str = "", text: str = "", indent: int = 2, sort_keys: bool = False) -> dict[str, Any]:
    if path:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            raise AzzxError(f"File not found: {p}")
        raw = p.read_text(encoding="utf-8")
    elif text:
        raw = text
        p = None
    else:
        raise AzzxError("Provide path or text")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AzzxError(f"Invalid JSON: {exc}") from exc
    formatted = json.dumps(obj, indent=max(0, indent), ensure_ascii=False, sort_keys=sort_keys) + "\n"
    if p is not None:
        p.write_text(formatted, encoding="utf-8")
        return {"path": str(p), "written": True, "keys": list(obj.keys()) if isinstance(obj, dict) else None}
    return {"formatted": formatted, "written": False}


def json_validate(path: str) -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise AzzxError(f"File not found: {p}")
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"path": str(p), "valid": False, "error": str(exc)}
    return {
        "path": str(p),
        "valid": True,
        "type": type(obj).__name__,
        "size_bytes": p.stat().st_size,
    }


def register_json_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="json.format",
        description="Pretty-print JSON file or text",
        permissions=["filesystem.write"],
        handler=json_format,
        schema={"path": "str", "text": "str", "indent": "int", "sort_keys": "bool"},
    ))
    REGISTRY.register(ToolSpec(
        name="json.validate",
        description="Validate JSON file",
        permissions=["filesystem.read"],
        handler=json_validate,
        schema={"path": "str"},
    ))

"""Hermes-like multimodal support: image input for vision-capable models (v10.2).

Encodes local images as base64 data-URLs in OpenAI-style `content` parts.
Adapters decide whether the active model supports vision via
`is_vision_model()` and degrade gracefully otherwise.
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

_VISION_HINTS = (
    "vision",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4-vision",
    "claude-3",
    "claude-opus-4",
    "claude-sonnet-4",
    "gemini-1.5",
    "gemini-2",
    "llava",
    "qwen-vl",
    "minicpm",
)


def is_vision_model(model: str) -> bool:
    """Heuristic: does this model name look vision-capable?"""
    name = (model or "").lower()
    return any(hint in name for hint in _VISION_HINTS)


def encode_image(path: str | Path, max_bytes: int = 4 * 1024 * 1024) -> dict[str, str]:
    """Read an image file and return a data-URL payload dict.

    Raises FileNotFoundError / ValueError on missing or oversized files.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"image not found: {p}")
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"image too large ({size} bytes > {max_bytes} bytes): {p}")
    mime, _ = mimetypes.guess_type(str(p))
    if not mime or not mime.startswith("image/"):
        raise ValueError(f"not an image file: {p}")
    raw = p.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return {"mime": mime, "data_url": f"data:{mime};base64,{b64}"}


def to_vision_content(text: str, image_paths: list[str | Path]) -> list[dict[str, Any]]:
    """Build an OpenAI-style multimodal `content` list.

    `[{"type": "text", ...}, {"type": "image_url", "image_url": {"url": ...}}]`
    """
    parts: list[dict[str, Any]] = [{"type": "text", "text": text or ""}]
    for img_path in image_paths:
        payload = encode_image(img_path)
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": payload["data_url"]},
            }
        )
    return parts


__all__ = ["encode_image", "is_vision_model", "to_vision_content"]

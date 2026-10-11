"""File attachments for chat & GUI (v10.6.4).

Problem: ``azzx chat`` and ``azzx gui`` sent only the system prompt + memory
to the provider — the AI could never see project files, so "analisa file X"
always failed. This module implements ``@path`` mentions: any ``@relative/
path`` in a message is resolved inside the workspace root, read, compressed
(via the token compressor), and appended as context.

Safety: paths must stay inside root (no ``..`` escapes, no absolute paths
outside root); directories, binaries, and files >2 MiB are skipped with a
note instead of failing the whole message.
"""
from __future__ import annotations

import re
from pathlib import Path

MENTION_RE = re.compile(r"@([^\s@,;:'\"]+)")
MAX_FILE_BYTES = 2 * 1024 * 1024


def _safe_resolve(root: Path, raw: str) -> Path | None:
    try:
        p = (root / raw).resolve()
        if not str(p).startswith(str(root.resolve())):
            return None
        return p
    except Exception:
        return None


def resolve_in_root(root: Path, raw: str) -> Path | None:
    """Public: resolve a user-supplied path safely inside root."""
    p = _safe_resolve(root, raw)
    if p is None or not p.is_file():
        return None
    return p


def _read_text(p: Path) -> str | None:
    try:
        if not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
            return None
        data = p.read_bytes()
        if b"\x00" in data[:8192]:
            return None  # binary
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None


def attach_file(path: str | Path, root: Path, budget_chars: int = 12000) -> str:
    """Read + compress one file. Returns a context chunk (or a skip note)."""
    from azzx.agent.compressor import compress_text

    p = _safe_resolve(root, str(path))
    if p is None:
        return f"[ATTACH SKIP] {path}: outside workspace\n"
    text = _read_text(p)
    if text is None:
        return f"[ATTACH SKIP] {p.name}: unreadable/binary/too large\n"
    rel = str(p.relative_to(root.resolve()))
    res = compress_text(text, budget_chars, "auto", filename=p.name)
    tag = "" if res["strategy"] == "none (already fits)" else f" (compressed: {res['strategy']})"
    return (f"\n===== FILE: {rel}{tag} =====\n{res['text']}\n"
            f"===== END FILE: {rel} =====\n")


def resolve_mentions(message: str, root: Path,
                     budget_chars: int = 12000) -> tuple[str, str]:
    """Extract @path mentions. Returns (message, context_block)."""
    found = MENTION_RE.findall(message or "")
    if not found:
        return message, ""
    seen: set[str] = set()
    chunks: list[str] = []
    per_file = max(2000, budget_chars // max(1, len(found)))
    for raw in found:
        if raw in seen:
            continue
        seen.add(raw)
        chunks.append(attach_file(raw, root, per_file))
    context = "\n[ATTACHED FILES — content of @mentions below]\n" + "".join(chunks)
    return message, context


def session_attachments(paths: list[Path], root: Path,
                        budget_chars: int = 24000) -> str:
    """Build a context block for session-persistent /add attachments."""
    if not paths:
        return ""
    per_file = max(2000, budget_chars // len(paths))
    chunks = [attach_file(p, root, per_file) for p in paths]
    return "\n[ATTACHED FILES — added via /add]\n" + "".join(chunks)

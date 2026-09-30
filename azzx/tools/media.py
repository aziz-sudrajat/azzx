"""FFmpeg media conversion — argument whitelist only."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError, require_permission

# Allowed output containers / simple presets only — no free-form filter graphs from NL
ALLOWED_FORMATS = {
    "mp4": ["-c:v", "libx264", "-c:a", "aac"],
    "webm": ["-c:v", "libvpx-vp9", "-c:a", "libopus"],
    "mp3": ["-vn", "-c:a", "libmp3lame"],
    "wav": ["-vn", "-c:a", "pcm_s16le"],
    "gif": ["-vf", "fps=10,scale=480:-1:flags=lanczos", "-an"],
    "mkv": ["-c:v", "libx264", "-c:a", "aac"],
}


def ffmpeg_convert(
    src: str,
    dest: str,
    fmt: str = "mp4",
    overwrite: bool = False,
) -> dict[str, Any]:
    require_permission("shell.run", detail=f"ffmpeg {src} → {dest}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AzzxError("ffmpeg not found. Install with: azzx install ffmpeg")
    source = Path(src).expanduser().resolve()
    out = Path(dest).expanduser().resolve()
    if not source.is_file():
        raise AzzxError(f"Source not found: {source}")
    fmt = fmt.lower().strip().lstrip(".")
    if fmt not in ALLOWED_FORMATS:
        raise AzzxError(f"Unsupported format: {fmt}. Allowed: {sorted(ALLOWED_FORMATS)}")
    if out.exists() and not overwrite:
        raise AzzxError(f"Destination exists (use overwrite=true): {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y" if overwrite else "-n",
           "-i", str(source), *ALLOWED_FORMATS[fmt], str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise AzzxError("ffmpeg timed out") from exc
    if proc.returncode != 0:
        raise AzzxError(f"ffmpeg failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return {
        "src": str(source),
        "dest": str(out),
        "format": fmt,
        "size": out.stat().st_size if out.exists() else 0,
        "command": cmd[:6] + ["..."],  # truncated for safety in logs
    }


def ffmpeg_probe(path: str) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise AzzxError("ffprobe not found (install ffmpeg)")
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise AzzxError(f"Not a file: {p}")
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(p),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise AzzxError(f"ffprobe failed: {proc.stderr.strip()}")
    import json
    data = json.loads(proc.stdout or "{}")
    fmt = data.get("format") or {}
    return {
        "path": str(p),
        "duration": fmt.get("duration"),
        "size": fmt.get("size"),
        "format_name": fmt.get("format_name"),
        "streams": len(data.get("streams") or []),
    }


def register_media_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="media.convert",
        description="Convert media with ffmpeg (whitelisted formats only)",
        permissions=["shell.run", "filesystem.read", "filesystem.write"],
        handler=ffmpeg_convert,
        schema={"src": "str", "dest": "str", "fmt": "str", "overwrite": "bool"},
    ))
    REGISTRY.register(ToolSpec(
        name="media.probe",
        description="Probe media file metadata via ffprobe",
        permissions=["filesystem.read"],
        handler=ffmpeg_probe,
        schema={"path": "str"},
    ))

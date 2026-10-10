"""Project checkpoints for AZZX (v10.5): snapshot before destructive work.

Snapshots are gzipped tarballs of a working directory stored under
``~/.azzx/agent/checkpoints/`` with a JSON manifest. ``rollback`` restores
the snapshot's files over the working directory.

Honest semantics: rollback is an *overlay*, not a wipe. Files that exist in
the snapshot are restored; files created *after* the checkpoint are kept,
not deleted (deleting user work silently would be worse). Before extracting,
rollback takes a fresh "pre-rollback" checkpoint of the current state, so a
rollback itself can always be undone.

Kept deliberately simple: no git dependency, works on Termux.
"""
from __future__ import annotations

import io
import json
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azzx.core import AzzxError, DATA_HOME

MAX_SNAPSHOT_BYTES = 500 * 1024 * 1024  # 500 MiB guard
_EXCLUDE = {".git", "__pycache__", ".azzx"}


def checkpoints_dir() -> Path:
    d = Path(DATA_HOME) / "agent" / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tar_filter(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = Path(ti.name).parts
    if any(p in _EXCLUDE for p in parts):
        return None
    return ti


def create(workdir: str, label: str = "") -> dict[str, Any]:
    wd = Path(workdir or ".").expanduser().resolve()
    if not wd.is_dir():
        raise AzzxError(f"checkpoint: not a directory: {wd}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    cid = f"{stamp}-{abs(hash(str(wd))) % 10000:04d}"
    archive = checkpoints_dir() / f"{cid}.tar.gz"

    total = 0
    with tarfile.open(archive, "w:gz") as tf:
        for path in sorted(wd.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(wd)
            if any(p in _EXCLUDE for p in rel.parts):
                continue
            size = path.stat().st_size
            total += size
            if total > MAX_SNAPSHOT_BYTES:
                archive.unlink(missing_ok=True)
                raise AzzxError("checkpoint: working dir exceeds 500 MiB snapshot guard")
            tf.add(path, arcname=str(rel), filter=_tar_filter)

    manifest = {
        "id": cid, "workdir": str(wd), "label": label[:120],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "archive": str(archive), "bytes": archive.stat().st_size,
    }
    (checkpoints_dir() / f"{cid}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def list_checkpoints() -> list[dict[str, Any]]:
    out = []
    for mf in sorted(checkpoints_dir().glob("*.json"), reverse=True):
        try:
            out.append(json.loads(mf.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def get(cid: str) -> dict[str, Any]:
    mf = checkpoints_dir() / f"{cid}.json"
    if not mf.is_file():
        raise AzzxError(f"checkpoint not found: {cid}")
    return json.loads(mf.read_text(encoding="utf-8"))


def rollback(cid: str, workdir: str | None = None) -> dict[str, Any]:
    """Restore a snapshot's files over the working directory.

    Overlay semantics: snapshot files are restored; files created after the
    checkpoint are kept. A pre-rollback checkpoint of the current state is
    taken first, so the rollback itself is reversible.
    """
    manifest = get(cid)
    archive = Path(manifest["archive"])
    if not archive.is_file():
        raise AzzxError(f"checkpoint archive missing: {cid}")
    wd = Path(workdir or manifest["workdir"]).expanduser().resolve()
    wd.mkdir(parents=True, exist_ok=True)

    # Safety first: snapshot the *current* state before touching anything.
    pre = create(str(wd), label=f"pre-rollback {cid}")

    restored = 0
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        # Safety: refuse absolute paths / path traversal inside the archive.
        for m in members:
            target = (wd / m.name).resolve()
            if not str(target).startswith(str(wd)):
                raise AzzxError(f"checkpoint: unsafe archive entry: {m.name}")
        tf.extractall(wd, members=[_tar_filter(m) for m in members if _tar_filter(m)])
        restored = len(members)
    return {"id": cid, "workdir": str(wd), "restored_files": restored,
            "pre_rollback_checkpoint": pre["id"],
            "note": "overlay restore: files created after the checkpoint were kept",
            "rolled_back_at": datetime.now(timezone.utc).isoformat()}


def prune(keep: int = 20) -> dict[str, Any]:
    items = list_checkpoints()
    removed = 0
    for mf in items[keep:]:
        try:
            Path(mf["archive"]).unlink(missing_ok=True)
            (checkpoints_dir() / f"{mf['id']}.json").unlink(missing_ok=True)
            removed += 1
        except Exception:
            continue
    return {"removed": removed, "kept": min(keep, len(items))}

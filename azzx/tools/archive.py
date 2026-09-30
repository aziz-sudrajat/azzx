"""Archive create / extract — no path traversal."""
from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError, require_permission


def _safe_extract_members_tar(tf: tarfile.TarFile, dest: Path) -> list[str]:
    extracted = []
    dest = dest.resolve()
    for member in tf.getmembers():
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            raise AzzxError(f"Refusing unsafe archive member: {name}")
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise AzzxError(f"Archive member escapes destination: {name}") from exc
        extracted.append(name)
    # Python 3.12+ supports filter= to harden extraction further
    try:
        tf.extractall(dest, filter="data")
    except TypeError:
        tf.extractall(dest)
    return extracted


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> list[str]:
    extracted = []
    dest = dest.resolve()
    for name in zf.namelist():
        if name.startswith("/") or ".." in Path(name).parts:
            raise AzzxError(f"Refusing unsafe archive member: {name}")
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise AzzxError(f"Archive member escapes destination: {name}") from exc
        extracted.append(name)
    zf.extractall(dest)
    return extracted


def archive_create(src: str, dest: str, fmt: str = "tar.gz") -> dict[str, Any]:
    require_permission("archive.write", detail=f"create {dest}")
    source = Path(src).expanduser().resolve()
    out = Path(dest).expanduser().resolve()
    if not source.exists():
        raise AzzxError(f"Source not found: {source}")
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower().strip()
    if fmt in {"tar.gz", "tgz"}:
        with tarfile.open(out, "w:gz") as tf:
            tf.add(source, arcname=source.name)
    elif fmt == "tar":
        with tarfile.open(out, "w") as tf:
            tf.add(source, arcname=source.name)
    elif fmt == "zip":
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if source.is_file():
                zf.write(source, arcname=source.name)
            else:
                for p in source.rglob("*"):
                    if p.is_file():
                        zf.write(p, arcname=str(p.relative_to(source.parent)))
    else:
        raise AzzxError("fmt must be tar.gz, tar, or zip")
    return {"created": str(out), "format": fmt, "size": out.stat().st_size}


def archive_extract(archive: str, dest: str = ".") -> dict[str, Any]:
    require_permission("archive.write", detail=f"extract {archive} → {dest}")
    arc = Path(archive).expanduser().resolve()
    destination = Path(dest).expanduser().resolve()
    if not arc.is_file():
        raise AzzxError(f"Archive not found: {arc}")
    destination.mkdir(parents=True, exist_ok=True)
    name = arc.name.lower()
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        mode = "r:gz" if name.endswith((".tar.gz", ".tgz")) else "r:"
        with tarfile.open(arc, mode) as tf:
            members = _safe_extract_members_tar(tf, destination)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(arc, "r") as zf:
            members = _safe_extract_zip(zf, destination)
    else:
        raise AzzxError("Supported archives: .tar, .tar.gz, .tgz, .zip")
    return {"archive": str(arc), "dest": str(destination), "members": len(members)}


def register_archive_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="archive.create",
        description="Create tar/tar.gz/zip archive",
        permissions=["archive.write", "filesystem.read"],
        handler=archive_create,
        schema={"src": "str", "dest": "str", "fmt": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="archive.extract",
        description="Extract archive with path-traversal protection",
        permissions=["archive.write"],
        handler=archive_extract,
        schema={"archive": "str", "dest": "str"},
    ))

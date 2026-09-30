"""File search, largest files, duplicate finder."""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError, safe_path_under


SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".azzx", ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
}


def _iter_files(root: Path, pattern: str = "*", max_files: int = 50_000):
    count = 0
    root = root.resolve()
    if not root.is_dir():
        raise AzzxError(f"Not a directory: {root}")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if count >= max_files:
                return
            p = Path(dirpath) / name
            if pattern != "*" and not p.match(pattern) and not Path(name).match(pattern):
                # simple suffix / glob support
                from fnmatch import fnmatch
                if not fnmatch(name, pattern) and not fnmatch(str(p.relative_to(root)), pattern):
                    continue
            yield p
            count += 1


def file_search(path: str = ".", pattern: str = "*", limit: int = 50) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    matches = []
    for p in _iter_files(root, pattern):
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = str(p)
        matches.append(rel)
        if len(matches) >= max(1, limit):
            break
    return {"root": str(root), "pattern": pattern, "count": len(matches), "files": matches}


def largest_files(path: str = ".", limit: int = 20, pattern: str = "*") -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    items: list[tuple[int, str]] = []
    for p in _iter_files(root, pattern):
        try:
            size = p.stat().st_size
            rel = str(p.relative_to(root))
            items.append((size, rel))
        except OSError:
            continue
    items.sort(key=lambda x: x[0], reverse=True)
    top = items[: max(1, limit)]
    return {
        "root": str(root),
        "files": [{"path": rel, "size": size, "size_human": _human(size)} for size, rel in top],
    }


def find_duplicates(path: str = ".", limit_groups: int = 20, min_size: int = 1) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in _iter_files(root):
        try:
            st = p.stat()
            if st.st_size < min_size:
                continue
            by_size[st.st_size].append(p)
        except OSError:
            continue
    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        hashes: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            try:
                h = _file_hash(p, "md5")
                hashes[h].append(str(p.relative_to(root)))
            except OSError:
                continue
        for h, files in hashes.items():
            if len(files) >= 2:
                groups.append({"hash": h, "size": size, "size_human": _human(size), "files": files})
                if len(groups) >= max(1, limit_groups):
                    return {"root": str(root), "duplicate_groups": groups}
    groups.sort(key=lambda g: g["size"], reverse=True)
    return {"root": str(root), "duplicate_groups": groups[: max(1, limit_groups)]}


def _file_hash(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _human(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < step:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= step  # type: ignore[assignment]
    return f"{n:.1f} PB"


def register_filesystem_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="fs.search",
        description="Search files under a directory by glob pattern",
        permissions=["filesystem.read"],
        handler=file_search,
        schema={"path": "str", "pattern": "str", "limit": "int"},
    ))
    REGISTRY.register(ToolSpec(
        name="fs.largest",
        description="List largest files under a directory",
        permissions=["filesystem.read"],
        handler=largest_files,
        schema={"path": "str", "limit": "int", "pattern": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="fs.duplicates",
        description="Find duplicate files by content hash",
        permissions=["filesystem.read"],
        handler=find_duplicates,
        schema={"path": "str", "limit_groups": "int", "min_size": "int"},
    ))

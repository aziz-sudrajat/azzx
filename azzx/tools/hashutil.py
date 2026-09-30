"""Hash / checksum tools."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from azzx.core import REGISTRY, ToolSpec, AzzxError

ALLOWED_ALGOS = {"md5", "sha1", "sha256", "sha512", "blake2b"}


def file_checksum(path: str, algorithm: str = "sha256") -> dict[str, Any]:
    algo = algorithm.lower().strip()
    if algo not in ALLOWED_ALGOS:
        raise AzzxError(f"Unsupported algorithm: {algorithm}. Use one of {sorted(ALLOWED_ALGOS)}")
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise AzzxError(f"Not a file: {p}")
    h = hashlib.new(algo)
    size = 0
    with p.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return {"path": str(p), "algorithm": algo, "hash": h.hexdigest(), "size": size}


def register_hash_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="hash.file",
        description="Compute file checksum (md5/sha1/sha256/sha512/blake2b)",
        permissions=["filesystem.read"],
        handler=file_checksum,
        schema={"path": "str", "algorithm": "str"},
    ))

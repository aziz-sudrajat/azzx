"""Self-update for AZZX (v10.6.14): `azzx update`.

Checks the GitHub repo for a newer VERSION, downloads the main-branch
tarball, backs up the current installation, replaces program files,
and verifies. User data (DATA_HOME) and config are never touched;
the venv is kept (dependencies don't change).

Safety:
- Backup of APP_DIR is taken before replacing (last 3 kept).
- After update: VERSION is re-read and azzx_cli.py is syntax-checked.
- On any failure, the backup is restored automatically.
- `--check` only reports; nothing is downloaded or changed.
"""
from __future__ import annotations

import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from azzx.core import AzzxError

REPO = "aziz-sudrajat/azzx"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
TARBALL_URL = f"https://github.com/{REPO}/archive/refs/heads/main.tar.gz"

# Same file set that install.sh copies into APP_DIR.
CODE_FILES = ["azzx_cli.py", "requirements.txt"]
DOC_FILES = ["README.md", "README_ID.md", "INSTALL.md", "CHANGELOG.md", "VERSION"]
CODE_DIRS = ["azzx", "examples"]


def _install_root() -> Path:
    """Resolve the AZZX installation directory."""
    import azzx_cli
    return Path(azzx_cli.__file__).resolve().parent


def _http_get(url: str, timeout: float = 30.0) -> bytes:
    import httpx
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        raise AzzxError(f"download failed ({url}): {exc}")


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        raise AzzxError(f"invalid version string: {v!r}")


def local_version() -> str:
    vf = _install_root() / "VERSION"
    if not vf.is_file():
        # Dev checkout: read from source tree.
        vf = Path(__file__).resolve().parent.parent.parent / "VERSION"
    return vf.read_text().strip() if vf.is_file() else "0.0.0"


def remote_version() -> str:
    return _http_get(f"{RAW_BASE}/VERSION").decode().strip()


def check() -> dict[str, Any]:
    """Compare local vs remote version. No changes made."""
    local = local_version()
    remote = remote_version()
    cmp = (_parse_version(remote) > _parse_version(local))
    return {
        "local": local,
        "remote": remote,
        "update_available": cmp,
    }


def _backup(app_dir: Path) -> Path:
    backup_root = app_dir.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = backup_root / f"azzx-{local_version()}-{stamp}"
    shutil.copytree(app_dir, dest, ignore=shutil.ignore_patterns(
        "venv", "__pycache__", "*.pyc", "backups"))
    # Keep last 3 backups.
    existing = sorted(backup_root.glob("azzx-*"))
    for old in existing[:-3]:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def _changelog_since(local: str) -> str:
    """Return CHANGELOG entries newer than the local version."""
    try:
        text = _http_get(f"{RAW_BASE}/CHANGELOG.md").decode()
    except AzzxError:
        return ""
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## v"):
            ver = line.split()[1].lstrip("v")
            try:
                if _parse_version(ver) <= _parse_version(local):
                    break
            except AzzxError:
                pass
        out.append(line)
    return "\n".join(out).strip()


def update(yes: bool = False) -> dict[str, Any]:
    """Download and apply the latest version. Returns a report dict."""
    info = check()
    if not info["update_available"]:
        return {"updated": False, "local": info["local"],
                "note": "sudah versi terbaru"}

    app_dir = _install_root()
    print(f"Update tersedia: {info['local']} → {info['remote']}")
    changes = _changelog_since(info["local"])
    if changes:
        print("\n--- perubahan ---")
        print(changes[:2000])
        print("--- akhir perubahan ---\n")
    if not yes:
        try:
            ans = input("Lanjutkan update? [ya/tidak]: ").strip().lower()
        except EOFError:
            return {"updated": False, "note": "dibatalkan (non-interaktif, pakai --yes)"}
        if ans not in ("ya", "y", "yes"):
            return {"updated": False, "note": "dibatalkan oleh user"}

    # 1. Backup.
    backup = _backup(app_dir)
    print(f"Backup: {backup}")

    # 2. Download + extract tarball.
    with tempfile.TemporaryDirectory(prefix="azzx-update-") as tmp:
        tgz = Path(tmp) / "main.tar.gz"
        tgz.write_bytes(_http_get(TARBALL_URL, timeout=120.0))
        with tarfile.open(tgz, "r:gz") as tf:
            # Security: prevent path traversal in tarball.
            for m in tf.getmembers():
                if m.name != "azzx-main" and not m.name.startswith("azzx-main/"):
                    raise AzzxError(f"unexpected tarball entry: {m.name}")
                if ".." in m.name.split("/"):
                    raise AzzxError(f"path traversal in tarball: {m.name}")
            tf.extractall(tmp)
        src = Path(tmp) / "azzx-main"

        # 3. Replace program files (same set as install.sh).
        for f in CODE_FILES + DOC_FILES:
            s = src / f
            if s.is_file():
                shutil.copy2(s, app_dir / f)
        for d in CODE_DIRS:
            s = src / d
            if s.is_dir():
                dest = app_dir / d
                shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(s, dest, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc"))

    # 4. Verify.
    try:
        new_ver = local_version()
        if _parse_version(new_ver) < _parse_version(info["remote"]):
            raise AzzxError(f"version mismatch after update: {new_ver}")
        import ast
        ast.parse((app_dir / "azzx_cli.py").read_text())
    except Exception as exc:
        # Roll back.
        shutil.rmtree(app_dir, ignore_errors=True)
        shutil.copytree(backup, app_dir)
        raise AzzxError(f"update verification failed, rolled back: {exc}")

    return {
        "updated": True,
        "from": info["local"],
        "to": new_ver,
        "backup": str(backup),
        "note": f"restart shell / rehash agar perintah azzx memakai versi baru",
    }

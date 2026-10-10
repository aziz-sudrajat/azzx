"""Persistent, opt-in scheduler for registered AZZX tools.

The scheduler never evaluates Python, shell strings, or arbitrary scripts. Jobs
contain only a registered tool name and JSON arguments. It is intentionally a
single-shot runner (`run_due`) so users can choose cron/systemd or run it on demand.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from azzx.core import DATA_HOME, AzzxError, REGISTRY


class ToolScheduler:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DATA_HOME / "agent" / "schedules.json"
        self.lock_path = self.path.with_suffix(".lock")

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            raise AzzxError(f"Schedule database is unreadable: {self.path}")

    def _write(self, jobs: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(jobs, fh, ensure_ascii=False, indent=2, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            try:
                os.chmod(self.path, 0o600)  # job args may carry sensitive values
            except OSError:
                pass
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def list(self) -> list[dict[str, Any]]:
        with self._locked():
            return sorted(self._read(), key=lambda j: float(j.get("next_run", 0)))

    def add(self, tool: str, args: dict[str, Any], every_seconds: int, name: str = "",
            cron: str = "") -> dict[str, Any]:
        if not isinstance(args, dict):
            raise AzzxError("Schedule args harus berupa JSON object.")
        # Fail closed: require tool registration and validate schema before saving.
        spec = REGISTRY.get(tool)
        if not spec:
            raise AzzxError(f"Tool tidak dikenal: {tool}")
        cron = (cron or "").strip()
        if cron:
            from azzx.agent.cronutil import next_cron_time
            next_run = next_cron_time(cron)  # validates the expression
            every_seconds = 60
        else:
            if every_seconds < 60:
                raise AzzxError("Interval minimum 60 detik untuk mencegah loop yang tidak disengaja.")
            next_run = time.time() + int(every_seconds)
        job = {
            "id": uuid.uuid4().hex[:10],
            "name": name.strip() or tool,
            "tool": tool,
            "args": args,
            "every_seconds": int(every_seconds),
            "cron": cron or None,
            "enabled": True,
            "created_at": time.time(),
            "next_run": next_run,
            "last_run": None,
            "last_status": None,
            "last_error": None,
        }
        with self._locked():
            jobs = self._read()
            jobs.append(job)
            self._write(jobs)
        return job

    def remove(self, job_id: str) -> bool:
        with self._locked():
            jobs = self._read()
            remaining = [j for j in jobs if str(j.get("id")) != job_id]
            if len(remaining) == len(jobs):
                return False
            self._write(remaining)
            return True

    def run_due(self, now: float | None = None, limit: int = 20) -> dict[str, Any]:
        """Run due jobs once; record outcomes and advance each next-run time."""
        now = time.time() if now is None else float(now)
        # Hold the cross-process lock through execution to prevent two cron
        # invocations from executing the same due job concurrently.
        with self._locked():
            jobs = self._read()
            due = [j for j in jobs if j.get("enabled", True) and float(j.get("next_run", 0)) <= now]
            due.sort(key=lambda j: float(j.get("next_run", 0)))
            reports: list[dict[str, Any]] = []
            for job in due[:max(1, min(int(limit), 100))]:
                try:
                    outcome = REGISTRY.call(str(job["tool"]), dict(job.get("args") or {}))
                    job["last_status"] = "done"
                    job["last_error"] = None
                    reports.append({"id": job["id"], "ok": True, "result": outcome})
                except Exception as exc:  # noqa: BLE001
                    job["last_status"] = "error"
                    job["last_error"] = f"{type(exc).__name__}: {exc}"
                    reports.append({"id": job["id"], "ok": False, "error": job["last_error"]})
                job["last_run"] = now
                # Skip missed intervals rather than stampeding through a backlog.
                if job.get("cron"):
                    from azzx.agent.cronutil import next_cron_time
                    try:
                        job["next_run"] = next_cron_time(str(job["cron"]), after=now)
                    except Exception:
                        job["next_run"] = now + 3600
                else:
                    interval = max(60, int(job.get("every_seconds", 60)))
                    job["next_run"] = now + interval
            if due:
                self._write(jobs)
            return {"due": len(due), "executed": len(reports), "results": reports}


__all__ = ["ToolScheduler"]

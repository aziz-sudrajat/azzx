"""Hermes-like async task queue: background agent/tool work (v10.2).

Submit registered tool calls (or plain callables) and poll for results.
Two execution modes:

- In-process worker thread (library/REPL/dashboard use): a daemon thread
  drains the queue FIFO while the process lives.
- Detached drainer (CLI one-shots): `spawn_drainer()` starts a fully
  detached process that claims queued tasks via a lock file and runs them
  to completion, so `azzx hermes queue submit` truly fire-and-forgets.

Task claims carry the owner's PID; a task whose owner died is reclaimed.
"""
from __future__ import annotations

import fcntl
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from azzx.core import DATA_HOME

_ACTIVE_STATUSES = {"queued", "running"}


def _safe_pid_alive(value: Any) -> bool:
    try:
        return _pid_alive(int(value))
    except (TypeError, ValueError):
        return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass
class QueuedTask:
    id: str
    kind: str  # "tool" | "callable"
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued | running | done | error
    result: Any = None
    error: str | None = None
    submitted_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    owner: str | None = None  # PID of the worker/drainer currently owning the task

    @property
    def duration_s(self) -> float | None:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 2)
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "args": self.args,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "owner": self.owner,
        }


class TaskQueue:
    """FIFO background queue with daemon worker and/or detached drainer."""

    def __init__(self, state_path: str | Path | None = None, auto_worker: bool = True) -> None:
        self.state_path = Path(state_path) if state_path else DATA_HOME / "agent" / "task_queue.json"
        self.lock_path = self.state_path.with_suffix(".lock")
        self.auto_worker = auto_worker
        self._q: "queue.Queue[QueuedTask]" = queue.Queue()
        self._tasks: dict[str, QueuedTask] = {}
        self._callables: dict[str, Callable[..., Any]] = {}
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._load()

    @contextmanager
    def _file_locked(self) -> Iterator[None]:
        """Cross-process mutex (the state file itself is atomically replaced)."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    # -- submission ------------------------------------------------------
    def submit_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> str:
        return self._submit("tool", tool_name, args or {})

    def submit(self, name: str, fn: Callable[..., Any], args: dict[str, Any] | None = None) -> str:
        task_id = uuid.uuid4().hex[:12]
        # Register the callable BEFORE the task becomes visible to workers.
        self._callables[task_id] = fn
        try:
            return self._submit("callable", name, args or {}, task_id=task_id)
        except Exception:
            self._callables.pop(task_id, None)
            raise

    def _submit(self, kind: str, name: str, args: dict[str, Any], task_id: str | None = None) -> str:
        task = QueuedTask(id=task_id or uuid.uuid4().hex[:12], kind=kind, name=name, args=args)
        with self._lock:
            self._tasks[task.id] = task
            # Persist before making the task visible to a worker. Otherwise a
            # fast worker can finish and race with this initial queued snapshot.
            self._save()
            self._q.put(task)
        self._ensure_worker()
        return task.id

    # -- inspection -------------------------------------------------------
    def status(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def result(self, task_id: str, timeout: float = 0.0) -> dict[str, Any] | None:
        """Return the task dict; optionally wait up to `timeout` seconds."""
        deadline = time.time() + max(0.0, timeout)
        while True:
            snap = self.status(task_id)
            if snap is None:
                return None
            if snap["status"] in {"done", "error"} or time.time() >= deadline:
                return snap
            time.sleep(0.05)

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.submitted_at, reverse=True)
        return [t.to_dict() for t in tasks[: max(1, limit)]]

    # -- worker ------------------------------------------------------------
    def _ensure_worker(self) -> None:
        if not self.auto_worker:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._drain, name="azzx-task-queue", daemon=True)
        self._worker.start()

    def _drain(self) -> None:
        while True:
            try:
                task = self._q.get(timeout=1.0)
            except queue.Empty:
                return  # idle: let the thread exit; resubmission restarts it
            self._run_task(task)
            self._q.task_done()

    def _run_task(self, task: QueuedTask) -> None:
        with self._lock:
            task.status = "running"
            task.started_at = time.time()
            task.owner = str(os.getpid())
        self._save()
        try:
            if task.kind == "tool":
                from azzx.core import REGISTRY  # deferred: registry may not be populated yet

                outcome = REGISTRY.call(task.name, dict(task.args))
                task.result = outcome
            else:
                fn = self._callables.pop(task.id, None)
                if fn is None:
                    raise RuntimeError("callable no longer registered for task")
                task.result = fn(**task.args)
            task.status = "done"
        except Exception as exc:  # noqa: BLE001
            task.status = "error"
            task.error = f"{type(exc).__name__}: {exc}"
        finally:
            # Make terminal status and its persisted snapshot one critical
            # section: result()/status() must not observe a completed task
            # before the final state has reached disk.
            with self._lock:
                task.finished_at = time.time()
                self._save()

    # -- detached drainer ------------------------------------------------------
    def _claim_next(self) -> QueuedTask | None:
        """Atomically claim one actionable task for this process (or None)."""
        with self._file_locked():
            items = self._read_state_unlocked()
            for item in items:
                if str(item.get("kind")) != "tool":
                    continue  # callables cannot cross processes
                status = str(item.get("status", ""))
                owner = item.get("owner")
                actionable = status == "queued" or (
                    status == "running" and (not owner or not _pid_alive(int(owner)))
                )
                if not actionable:
                    continue
                item["status"] = "running"
                item["owner"] = str(os.getpid())
                item["started_at"] = time.time()
                self._write_state_unlocked(items)
                return QueuedTask(
                    id=str(item.get("id")),
                    kind="tool",
                    name=str(item.get("name")),
                    args=dict(item.get("args") or {}),
                    status="running",
                    started_at=float(item["started_at"]),
                    owner=str(os.getpid()),
                )
            return None

    def _read_state_unlocked(self) -> list[dict[str, Any]]:
        try:
            if not self.state_path.exists():
                return []
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _write_state_unlocked(self, items: list[dict[str, Any]]) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")
            tmp.replace(self.state_path)
        except OSError:
            pass

    def _finish_claim(self, task: QueuedTask, status: str, result: Any = None, error: str | None = None) -> None:
        with self._file_locked():
            items = self._read_state_unlocked()
            for item in items:
                if str(item.get("id")) == task.id:
                    item["status"] = status
                    item["result"] = result
                    item["error"] = error
                    item["finished_at"] = time.time()
                    break
            self._write_state_unlocked(items)

    def _any_active(self) -> bool:
        with self._file_locked():
            for item in self._read_state_unlocked():
                status = str(item.get("status", ""))
                if status == "queued":
                    return True
                if status == "running":
                    owner = item.get("owner")
                    if not owner or not _pid_alive(int(owner)):
                        return True  # orphaned; claimable
                    return True
        return False

    def drain(self, timeout: float = 600.0, poll: float = 0.5) -> bool:
        """Run claimed tasks synchronously until the queue is empty.

        Used by the detached drainer process. Returns True when drained,
        False on timeout.
        """
        from azzx.agent.orchestrator import register_all

        register_all()
        deadline = time.time() + max(1.0, timeout)
        while time.time() < deadline:
            task = self._claim_next()
            if task is None:
                if not self._any_active():
                    return True
                time.sleep(poll)
                continue
            try:
                from azzx.core import REGISTRY

                outcome = REGISTRY.call(task.name, dict(task.args))
                self._finish_claim(task, "done", result=outcome)
            except Exception as exc:  # noqa: BLE001
                self._finish_claim(task, "error", error=f"{type(exc).__name__}: {exc}")
        return False

    # -- persistence ---------------------------------------------------------
    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                local = {t.id: t.to_dict() for t in self._tasks.values()}
            with self._file_locked():
                # Keep tasks submitted/updated by other CLI processes. A
                # deterministic shared .tmp filename allowed concurrent
                # writers to overwrite or replace each other's temp file.
                existing = {str(i.get("id")): i for i in self._read_state_unlocked() if isinstance(i, dict) and i.get("id")}
                for task_id, item in local.items():
                    old = existing.get(task_id)
                    if old and str(old.get("owner") or "") != str(os.getpid()):
                        # Never regress a state already advanced by a detached
                        # worker. Local terminal results are authoritative.
                        if old.get("status") in {"done", "error"} and item.get("status") not in {"done", "error"}:
                            continue
                        if old.get("status") == "running" and item.get("status") == "queued":
                            continue
                    existing[task_id] = item
                data = list(existing.values())
                fd, tmp_name = tempfile.mkstemp(prefix=f".{self.state_path.name}.", suffix=".tmp", dir=str(self.state_path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        json.dump(data, fh, ensure_ascii=False, default=str)
                        fh.flush()
                        os.fsync(fh.fileno())
                    os.replace(tmp_name, self.state_path)
                finally:
                    try:
                        os.unlink(tmp_name)
                    except FileNotFoundError:
                        pass
        except OSError:
            pass

    def _read_state(self) -> list[dict[str, Any]]:
        try:
            with self._file_locked():
                if not self.state_path.exists():
                    return []
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _load(self) -> None:
        for item in self._read_state():
            try:
                task = QueuedTask(
                    id=str(item.get("id", "")),
                    kind=str(item.get("kind", "tool")),
                    name=str(item.get("name", "")),
                    args=dict(item.get("args") or {}),
                )
                task.status = str(item.get("status", "queued"))
                task.result = item.get("result")
                task.error = item.get("error")
                task.owner = item.get("owner")
                task.submitted_at = float(item.get("submitted_at") or time.time())
                if task.status in _ACTIVE_STATUSES and task.kind == "tool":
                    if not task.owner or not _safe_pid_alive(task.owner):
                        # Orphaned (previous worker died): reclaim for this process.
                        task.status = "queued"
                        task.owner = None
                        self._q.put(task)
                if task.id:
                    self._tasks[task.id] = task
            except (TypeError, ValueError):
                continue
        if self.auto_worker and not self._q.empty():
            self._ensure_worker()


_TASK_QUEUE: TaskQueue | None = None
_TASK_QUEUE_LOCK = threading.Lock()


def get_task_queue() -> TaskQueue:
    """Process-wide lazy task queue (creates no files until first submit)."""
    global _TASK_QUEUE
    if _TASK_QUEUE is None:
        with _TASK_QUEUE_LOCK:
            if _TASK_QUEUE is None:
                _TASK_QUEUE = TaskQueue()
    return _TASK_QUEUE


def run_drainer(timeout: float = 600.0) -> bool:
    """Entry point for the detached drainer process. Returns drained-ok."""
    q = TaskQueue(auto_worker=False)
    return q.drain(timeout=timeout)


def spawn_drainer() -> bool:
    """Start a fully detached drainer process (fire-and-forget).

    Returns True if the process was launched. The drainer inherits the
    current environment (including AZZX_CONFIG_HOME) and exits on its own
    once the queue is empty.
    """
    try:
        import azzx

        pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(azzx.__file__)))
        code = (
            "import sys; sys.path.insert(0, %r); "
            "from azzx.agent.tasks import run_drainer; run_drainer()" % (pkg_root,)
        )
        subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except OSError:
        return False


__all__ = ["QueuedTask", "TaskQueue", "get_task_queue", "run_drainer", "spawn_drainer"]

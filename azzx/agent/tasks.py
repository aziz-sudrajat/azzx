"""Native async task queue for AZZX (v10.4): background agent/tool work.

Submit registered tool calls (or plain callables) and poll for results.
Two execution modes:

- In-process worker thread (library/REPL/dashboard use): a daemon thread
  drains the queue FIFO while the process lives.
- Detached drainer (CLI one-shots): `spawn_drainer()` starts a fully
  detached process that claims queued tasks via a lock file and runs them
  to completion, so `azzx queue submit` truly fire-and-forgets.

Task lifecycle: queued -> running -> done | error | cancelled.
A task whose owner process died while running becomes `interrupted`
(it is *not* silently re-run — re-running could repeat side effects).
Use `resume_task()` to deliberately requeue an interrupted/error/cancelled
task after checking whether its side effects already happened.

Security: a background worker never prompts. Tool tasks whose required
permissions are not policy-`allow` need `approved=True` at submit time
(CLI: `azzx queue submit --yes`); otherwise they finish with a clear
`error` naming the capability to approve. State files are mode 0600.
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

from azzx.core import DATA_HOME, PermissionDenied, permission_policy

_ACTIVE_STATUSES = {"queued", "running"}
_TERMINAL_STATUSES = {"done", "error", "cancelled"}
_RESUMABLE_STATUSES = {"interrupted", "error", "cancelled"}


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


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


@dataclass
class QueuedTask:
    id: str
    kind: str  # "tool" | "callable"
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued | running | done | error | cancelled | interrupted
    result: Any = None
    error: str | None = None
    approved: bool = False  # user approved non-"allow" permissions at submit time
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
            "approved": self.approved,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "owner": self.owner,
        }


def check_tool_approvals(tool_name: str) -> list[str]:
    """Capabilities that would need approval before background execution.

    Returns the list of required capabilities whose policy is not "allow".
    """
    from azzx.core import REGISTRY

    spec = REGISTRY.get(tool_name)
    return [cap for cap in spec.permissions if permission_policy(cap) != "allow"]


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
    def submit_tool(self, tool_name: str, args: dict[str, Any] | None = None,
                    approved: bool = False) -> str:
        """Submit a registered tool call.

        `approved=True` records that the user already approved any
        non-"allow" permissions (CLI passes --yes). Without it, the task
        fails with a clear message naming the capability to approve.
        """
        return self._submit("tool", tool_name, args or {}, approved=approved)

    def submit(self, name: str, fn: Callable[..., Any], args: dict[str, Any] | None = None) -> str:
        task_id = uuid.uuid4().hex[:12]
        # Register the callable BEFORE the task becomes visible to workers.
        self._callables[task_id] = fn
        try:
            return self._submit("callable", name, args or {}, task_id=task_id, approved=True)
        except Exception:
            self._callables.pop(task_id, None)
            raise

    def _submit(self, kind: str, name: str, args: dict[str, Any],
                task_id: str | None = None, approved: bool = False) -> str:
        task = QueuedTask(id=task_id or uuid.uuid4().hex[:12], kind=kind, name=name,
                          args=args, approved=approved)
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

    def _refresh_from_disk(self) -> None:
        """Adopt state advanced by other processes (never regress local state)."""
        with self._lock:
            for item in self._read_state():
                tid = str(item.get("id") or "")
                if not tid:
                    continue
                disk_status = str(item.get("status") or "")
                task = self._tasks.get(tid)
                if task is None:
                    if disk_status in _TERMINAL_STATUSES:
                        # Adopt finished foreign tasks as read-only records.
                        adopted = QueuedTask(
                            id=tid, kind=str(item.get("kind") or "tool"),
                            name=str(item.get("name") or ""),
                            args=dict(item.get("args") or {}),
                        )
                        for f in ("status", "result", "error", "approved",
                                  "submitted_at", "started_at", "finished_at", "owner"):
                            setattr(adopted, f, item.get(f))
                        self._tasks[tid] = adopted
                    continue
                if task.status in _TERMINAL_STATUSES:
                    continue
                if disk_status in _TERMINAL_STATUSES:
                    for f in ("status", "result", "error", "finished_at"):
                        setattr(task, f, item.get(f))
                elif disk_status == "running" and task.status == "queued":
                    owner = item.get("owner")
                    if owner and str(owner) != str(os.getpid()) and _safe_pid_alive(owner):
                        task.status = "running"
                        task.owner = str(owner)
                        task.started_at = item.get("started_at")

    def result(self, task_id: str, timeout: float = 0.0) -> dict[str, Any] | None:
        """Return the task dict; optionally wait up to `timeout` seconds."""
        deadline = time.time() + max(0.0, timeout)
        while True:
            self._refresh_from_disk()
            snap = self.status(task_id)
            if snap is None:
                return None
            if snap["status"] in _TERMINAL_STATUSES or time.time() >= deadline:
                return snap
            time.sleep(0.05)

    def list_tasks(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.submitted_at, reverse=True)
        return [t.to_dict() for t in tasks[: max(1, limit)]]

    # -- lifecycle ----------------------------------------------------------
    def cancel(self, task_id: str) -> bool:
        """Cancel a queued task. Running tasks cannot be preempted safely.

        The worker skips cancelled tasks when it reaches them (see
        `_run_task`), so no queue surgery — and no task_done() race — is needed.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != "queued":
                return False
            task.status = "cancelled"
            task.finished_at = time.time()
            self._save()
            return True

    def resume_task(self, task_id: str) -> bool:
        """Requeue an interrupted/error/cancelled task.

        Deliberate user action: check whether the task's side effects already
        happened before resuming.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status not in _RESUMABLE_STATUSES:
                return False
            task.status = "queued"
            task.error = None
            task.owner = None
            task.started_at = None
            task.finished_at = None
            self._save()
            self._q.put(task)
        self._ensure_worker()
        return True

    # -- worker ------------------------------------------------------------
    def _ensure_worker(self) -> None:
        if not self.auto_worker:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._drain, name="azzx-task-queue", daemon=True)
        self._worker.start()

    def join(self, timeout: float = 5.0) -> None:
        """Wait for the in-process worker thread to go idle and exit.

        Useful in tests and at shutdown so no background write races
        directory cleanup.
        """
        worker = self._worker
        if worker is not None:
            worker.join(timeout=max(0.0, timeout))

    def _drain(self) -> None:
        while True:
            try:
                task = self._q.get(timeout=1.0)
            except queue.Empty:
                return  # idle: let the thread exit; resubmission restarts it
            self._run_task(task)
            self._q.task_done()

    def _claimed_elsewhere(self, task: QueuedTask) -> bool:
        """True if another live process already owns this task as running.

        Guards against double execution when an in-process worker and a
        detached drainer both see the same queued task.
        """
        with self._file_locked():
            for item in self._read_state_unlocked():
                if str(item.get("id")) != task.id:
                    continue
                if str(item.get("status")) == "running":
                    owner = item.get("owner")
                    if owner and str(owner) != str(os.getpid()) and _safe_pid_alive(owner):
                        return True
                return False
        return False

    def _execute_tool(self, task: QueuedTask) -> Any:
        """Run one tool task with approval gating (no interactive prompts)."""
        from azzx.core import REGISTRY

        if task.kind != "tool":
            raise ValueError(f"not a tool task: {task.kind}")
        if not task.approved:
            needs = check_tool_approvals(task.name)
            if needs:
                raise PermissionDenied(
                    "Background task needs approval for capability(s): "
                    + ", ".join(needs) + ". Resubmit with approved=True "
                    "(CLI: `azzx queue submit --yes`) or set the capability to "
                    "'allow' via `azzx permissions set <cap> allow`."
                )
        return REGISTRY.call(task.name, dict(task.args),
                             noninteractive=True, force_yes=task.approved)

    def _run_task(self, task: QueuedTask) -> None:
        with self._lock:
            if task.status == "cancelled":
                self._save()
                return
            task.status = "running"
            task.started_at = time.time()
            task.owner = str(os.getpid())
        self._save()
        try:
            if task.kind == "tool":
                if self._claimed_elsewhere(task):
                    # A detached drainer got there first; don't double-run.
                    with self._lock:
                        task.status = "queued"
                        task.owner = None
                        task.started_at = None
                        self._save()
                    return
                task.result = self._execute_tool(task)
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
                if task.status not in {"queued"}:  # not yielded to another worker
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
                    status == "running" and not _safe_pid_alive(owner)
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
                    approved=bool(item.get("approved", False)),
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
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.state_path.name}.", suffix=".tmp",
                dir=str(self.state_path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(items, fh, ensure_ascii=False, default=str)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, self.state_path)
                _chmod_private(self.state_path)
            finally:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
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
                    if not _safe_pid_alive(owner):
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
                outcome = self._execute_tool(task)
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
                existing = {str(i.get("id")): i for i in self._read_state_unlocked()
                            if isinstance(i, dict) and i.get("id")}
                for task_id, item in local.items():
                    old = existing.get(task_id)
                    if old and str(old.get("owner") or "") != str(os.getpid()):
                        # Never regress a state already advanced by a detached
                        # worker. Local terminal results are authoritative.
                        if old.get("status") in {"done", "error", "cancelled"} \
                                and item.get("status") not in {"done", "error", "cancelled"}:
                            continue
                        if old.get("status") == "running" and item.get("status") == "queued":
                            continue
                    existing[task_id] = item
                data = list(existing.values())
                fd, tmp_name = tempfile.mkstemp(prefix=f".{self.state_path.name}.",
                                                suffix=".tmp", dir=str(self.state_path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        json.dump(data, fh, ensure_ascii=False, default=str)
                        fh.flush()
                        os.fsync(fh.fileno())
                    os.replace(tmp_name, self.state_path)
                    _chmod_private(self.state_path)
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
                task.approved = bool(item.get("approved", False))
                task.owner = item.get("owner")
                task.submitted_at = float(item.get("submitted_at") or time.time())
                if task.status in _ACTIVE_STATUSES and task.kind == "tool":
                    if not _safe_pid_alive(task.owner):
                        # The owner died mid-run: mark interrupted. Never
                        # silently re-run — side effects may already have
                        # happened. The user resumes deliberately.
                        task.status = "interrupted"
                        task.error = (
                            "owner process died while the task was "
                            f"{item.get('status')}; use resume_task() after "
                            "checking whether side effects already happened"
                        )
                        task.owner = None
                if task.id:
                    self._tasks[task.id] = task
            except (TypeError, ValueError):
                continue
        # NOTE: interrupted tasks are intentionally NOT requeued here.


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


__all__ = [
    "QueuedTask", "TaskQueue", "get_task_queue", "run_drainer", "spawn_drainer",
    "check_tool_approvals",
    "_ACTIVE_STATUSES", "_TERMINAL_STATUSES", "_RESUMABLE_STATUSES",
]

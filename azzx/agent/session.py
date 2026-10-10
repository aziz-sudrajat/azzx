"""Session and project memory journal for AZZX multi-agent workflows.

Continuity across tasks, sessions, and projects: sessions can be ended,
resumed (restoring summary + events + project context), and stale
(interrupted) sessions can be found after a crash or restart.
Connections are always closed (try/finally) so a failed operation can never
leave the database locked.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from azzx.core import DATA_HOME

SESSION_STATUSES = {"active", "done", "abandoned", "failed"}


@dataclass
class SessionSnapshot:
    """Persisted session snapshot."""

    session_id: str
    project: str
    title: str
    summary: str
    created_at: str
    updated_at: str
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project": self.project,
            "title": self.title,
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
        }


class SessionMemoryJournal:
    """Long-lived journal for multi-agent workflows.

    Stores:
    - session metadata
    - task events per agent
    - project summaries and task memory
    - task replay data for later reasoning
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else DATA_HOME / "agent"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "sessions.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    title TEXT,
                    summary TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    task_id TEXT,
                    agent_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS project_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    task_id TEXT,
                    agent_id TEXT,
                    summary TEXT NOT NULL,
                    tags TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_project_index_project ON project_index(project)"
            )
            conn.commit()

    def start_session(self, project: str, title: str, summary: str = "") -> str:
        session_id = f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        now = self._utcnow()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, project, title, summary, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (session_id, project, title, summary, now, now),
            )
            conn.commit()
        return session_id

    def log_event(
        self,
        session_id: str,
        agent_id: str,
        stage: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO session_events (session_id, task_id, agent_id, stage, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    task_id,
                    agent_id,
                    stage,
                    message,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    self._utcnow(),
                ),
            )
            conn.commit()

    def add_project_task(
        self,
        project: str,
        summary: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO project_index (project, task_id, agent_id, summary, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project,
                    task_id,
                    agent_id,
                    summary,
                    json.dumps(tags or [], ensure_ascii=False),
                    self._utcnow(),
                ),
            )
            conn.commit()

    def get_recent_sessions(self, project: str | None = None, limit: int = 10,
                            status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions"
        clauses: list[str] = []
        params: list[Any] = []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_session_events(self, session_id: str, limit: int = 20,
                           chronological: bool = False) -> list[dict[str, Any]]:
        order = "created_at ASC, id ASC" if chronological else "created_at DESC, id DESC"
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM session_events
                WHERE session_id = ?
                ORDER BY {order} LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def touch_session(self, session_id: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (self._utcnow(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def end_session(self, session_id: str, status: str = "done",
                    summary: str = "") -> bool:
        """Close a session. Status: done | abandoned | failed."""
        status = (status or "done").strip().lower()
        if status not in SESSION_STATUSES - {"active"}:
            raise ValueError(f"Invalid end status {status!r}; use done/abandoned/failed")
        with closing(self._connect()) as conn:
            if summary:
                cur = conn.execute(
                    "UPDATE sessions SET status = ?, summary = ?, updated_at = ? WHERE session_id = ?",
                    (status, summary, self._utcnow(), session_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                    (status, self._utcnow(), session_id),
                )
            conn.commit()
            return cur.rowcount > 0

    def resume_session(self, session_id: str, event_limit: int = 50) -> dict[str, Any]:
        """Restore everything needed to continue: snapshot, events, project context."""
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        if session.get("status") != "active":
            # Re-activate explicitly: resuming is a deliberate user action.
            with closing(self._connect()) as conn:
                conn.execute(
                    "UPDATE sessions SET status = 'active', updated_at = ? WHERE session_id = ?",
                    (self._utcnow(), session_id),
                )
                conn.commit()
            session["status"] = "active"
        events = self.get_session_events(session_id, limit=event_limit, chronological=True)
        project = session.get("project") or ""
        return {
            "session": session,
            "events": events,
            "project_summary": self.build_project_summary(project) if project else "",
            "hint": (
                f"Resumed session '{session.get('title')}'. "
                f"{len(events)} prior event(s) restored; continue from the last state, "
                "do not repeat completed steps."
            ),
        }

    def find_stale(self, project: str | None = None, stale_hours: float = 24.0) -> list[dict[str, Any]]:
        """Active sessions untouched for longer than `stale_hours`.

        These are candidates for interrupted work: the process likely died
        before `end_session` was called.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat(timespec="seconds") + "Z"
        query = "SELECT * FROM sessions WHERE status = 'active' AND updated_at < ?"
        params: list[Any] = [cutoff]
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY updated_at ASC"
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text-ish search across session titles, summaries, and events.

        LIKE-based on purpose: works on every SQLite build (including Termux)
        with no FTS5 dependency.
        """
        query = (query or "").strip()
        if not query:
            return []
        like = f"%{query}%"
        with closing(self._connect()) as conn:
            session_hits = conn.execute(
                """SELECT session_id, project, title, summary, status, updated_at
                   FROM sessions
                   WHERE title LIKE ? OR summary LIKE ? OR project LIKE ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (like, like, like, int(limit)),
            ).fetchall()
            event_hits = conn.execute(
                """SELECT session_id, agent_id, stage,
                          substr(message, 1, 200) AS snippet, created_at
                   FROM session_events
                   WHERE message LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (like, int(limit)),
            ).fetchall()
        return {
            "sessions": [dict(r) for r in session_hits],
            "events": [dict(r) for r in event_hits],
        }

    def get_project_memory(self, project: str, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM project_index
                WHERE project = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (project, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def build_project_summary(self, project: str) -> str:
        entries = self.get_project_memory(project, limit=20)
        if not entries:
            return f"No previous memory for project: {project}"
        summary_lines = [f"Project memory for {project}:"]
        for entry in entries:
            summary_lines.append(f"- [{entry['agent_id'] or 'system'}] {entry['summary']}")
        return "\n".join(summary_lines)

    def update_session_summary(self, session_id: str, summary: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE sessions SET summary = ?, updated_at = ? WHERE session_id = ?",
                (summary, self._utcnow(), session_id),
            )
            conn.commit()


_DEFAULT_SESSION_JOURNAL: SessionMemoryJournal | None = None


def get_session_journal() -> SessionMemoryJournal:
    """Get the global session journal (created lazily on first use)."""
    global _DEFAULT_SESSION_JOURNAL
    if _DEFAULT_SESSION_JOURNAL is None:
        _DEFAULT_SESSION_JOURNAL = SessionMemoryJournal()
    return _DEFAULT_SESSION_JOURNAL


__all__ = ["SessionSnapshot", "SessionMemoryJournal", "get_session_journal", "SESSION_STATUSES"]

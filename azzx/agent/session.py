"""Session and project memory journal for AZZX multi-agent workflows.

This keeps Hermes-like continuity across tasks, sessions, and projects.
Connections are always closed (try/finally) so a failed operation can never
leave the database locked.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azzx.core import DATA_HOME


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

    def get_recent_sessions(self, project: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions"
        params: list[Any] = []
        if project:
            query += " WHERE project = ?"
            params.append(project)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_session_events(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM session_events
                WHERE session_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

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


__all__ = ["SessionSnapshot", "SessionMemoryJournal", "get_session_journal"]

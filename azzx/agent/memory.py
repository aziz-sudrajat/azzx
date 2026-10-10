"""SQLite-backed persistent memory for the AZZX multi-agent layer (v10.1).

Lightweight and Termux-friendly: long-term agent memory without external
ML dependencies. Connections are always closed via try/finally so a failed
operation can never leave the database locked.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from azzx.core import DATA_HOME
from azzx.agent.embeddings import SimpleEmbedder


@dataclass
class MemoryEntry:
    """Single persistent memory item for an agent."""

    id: int | None
    agent_id: str
    memory_type: str
    content: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    created_at: str = ""
    shared: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "tags": list(self.tags),
            "importance": float(self.importance),
            "created_at": self.created_at,
            "shared": bool(self.shared),
        }


class MemoryStore:
    """SQLite-backed memory layer for agent continuity.

    This is intentionally lightweight and Termux-friendly. It provides short-term
    and long-term memory storage without external ML dependencies.
    """

    def __init__(self, config_dir: str | Path | None = None, db_name: str = "azzx_memory.db") -> None:
        self.root = Path(config_dir) if config_dir is not None else DATA_HOME / "agent"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / db_name
        self._embedder = SimpleEmbedder(self.root / "tfidf.json")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    shared INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_agent ON memory_entries(agent_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(memory_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_shared ON memory_entries(shared)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    memory_id INTEGER PRIMARY KEY,
                    vector TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def store(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        tags: Iterable[str] | None = None,
        shared: bool = True,
    ) -> str:
        if not agent_id:
            agent_id = "system"
        normalized = (content or "").strip()
        if not normalized:
            raise ValueError("Memory content cannot be empty")
        tags_list = sorted({str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()})
        now = self._utcnow()
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO memory_entries (agent_id, memory_type, content, tags, importance, created_at, shared)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    memory_type,
                    normalized,
                    json.dumps(tags_list, ensure_ascii=False),
                    float(importance),
                    now,
                    1 if shared else 0,
                ),
            )
            memory_id = int(cursor.lastrowid)
            conn.commit()
        # Semantic index (outside the DB transaction; best effort).
        try:
            self._embedder.add_document(normalized)
            vector = self._embedder.embed(normalized)
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO memory_vectors (memory_id, vector) VALUES (?, ?)",
                    (memory_id, json.dumps(vector, ensure_ascii=False)),
                )
                conn.commit()
            self._embedder.save()
        except OSError:
            pass
        return str(memory_id)

    def get_recent(
        self,
        agent_id: str | None = None,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[MemoryEntry]:
        query = "SELECT * FROM memory_entries WHERE 1=1"
        params: list[Any] = []
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def search(
        self,
        query: str,
        agent_id: str | None = None,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> list[MemoryEntry]:
        query = (query or "").strip()
        if not query:
            return self.get_recent(agent_id=agent_id, limit=limit)

        terms = [part.lower() for part in query.split() if part.strip()]
        clauses: list[str] = []
        params: list[Any] = []
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        clauses.append("importance >= ?")
        params.append(float(min_importance))
        for term in terms:
            clauses.append("(LOWER(content) LIKE ? OR LOWER(tags) LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])
        where_sql = " AND ".join(clauses)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_entries WHERE {where_sql} ORDER BY importance DESC, created_at DESC LIMIT ?",
                [*params, int(limit)],
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def search_semantic(
        self,
        query: str,
        agent_id: str | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[MemoryEntry, float]]:
        """Rank memories by semantic (embedding cosine) similarity.

        Returns (entry, score) pairs ordered by score descending. Unlike
        `search()`, this finds memories about the same *meaning* even when
        they share no literal keywords.
        """
        query = (query or "").strip()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT e.*, v.vector AS vec FROM memory_entries e
                JOIN memory_vectors v ON v.memory_id = e.id
                """
            ).fetchall()
        candidates: list[tuple[int, dict[str, float]]] = []
        entries: dict[int, MemoryEntry] = {}
        for row in rows:
            if agent_id and row["agent_id"] != agent_id:
                continue
            try:
                vec = json.loads(row["vec"] or "{}")
            except (ValueError, TypeError):
                continue
            entry = self._row_to_entry(row)
            entries[int(row["id"])] = entry
            candidates.append((int(row["id"]), {str(k): float(v) for k, v in vec.items()}))
        ranked = self._embedder.most_similar(query, candidates, limit=limit)
        return [
            (entries[mid], score)
            for mid, score in ranked
            if score >= min_score and mid in entries
        ]

    def search_hybrid(
        self,
        query: str,
        agent_id: str | None = None,
        limit: int = 10,
        keyword_weight: float = 0.4,
    ) -> list[tuple[MemoryEntry, float]]:
        """Combine keyword (`search`) and semantic ranking.

        Merges both result sets; entries appearing in both get a boosted
        score. This is the recommended default for Hermes-like recall.
        """
        keyword_hits = self.search(query, agent_id=agent_id, limit=limit * 2)
        semantic_hits = self.search_semantic(query, agent_id=agent_id, limit=limit * 2)
        scores: dict[int, float] = {}
        entries: dict[int, MemoryEntry] = {}
        for rank, entry in enumerate(keyword_hits):
            eid = int(entry.id or 0)
            entries[eid] = entry
            scores[eid] = scores.get(eid, 0.0) + keyword_weight * (1.0 / (1 + rank))
        for entry, score in semantic_hits:
            eid = int(entry.id or 0)
            entries[eid] = entry
            scores[eid] = scores.get(eid, 0.0) + (1.0 - keyword_weight) * score
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]
        return [(entries[eid], score) for eid, score in ranked]

    def rebuild_vectors(self) -> int:
        """Re-embed every memory (useful after bulk imports). Returns count."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id, content FROM memory_entries").fetchall()
        count = 0
        with closing(self._connect()) as conn:
            for row in rows:
                content = row["content"] or ""
                self._embedder.add_document(content)
                vector = self._embedder.embed(content)
                conn.execute(
                    "INSERT OR REPLACE INTO memory_vectors (memory_id, vector) VALUES (?, ?)",
                    (int(row["id"]), json.dumps(vector, ensure_ascii=False)),
                )
                count += 1
            conn.commit()
        self._embedder.save()
        return count

    def get_agent_summary(self, agent_id: str, limit: int = 5) -> list[dict[str, Any]]:
        entries = self.get_recent(agent_id=agent_id, limit=limit)
        return [entry.to_dict() for entry in entries]

    def get_stats(self) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN shared = 1 THEN 1 ELSE 0 END) AS shared,
                    AVG(importance) AS avg_importance
                FROM memory_entries
                """
            ).fetchone()
        return {
            "total": int((row["total"] if row else 0) or 0),
            "shared": int((row["shared"] if row else 0) or 0),
            "avg_importance": float((row["avg_importance"] if row else 0) or 0.0),
        }

    def delete(self, memory_id: int) -> bool:
        with closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM memory_entries WHERE id = ?", (int(memory_id),))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        tags = json.loads(row["tags"] or "[]") if row["tags"] else []
        return MemoryEntry(
            id=row["id"],
            agent_id=row["agent_id"],
            memory_type=row["memory_type"],
            content=row["content"],
            tags=list(tags),
            importance=float(row["importance"]),
            created_at=row["created_at"],
            shared=bool(row["shared"]),
        )


_DEFAULT_MEMORY_STORE: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Get the global memory store (created lazily on first use)."""
    global _DEFAULT_MEMORY_STORE
    if _DEFAULT_MEMORY_STORE is None:
        _DEFAULT_MEMORY_STORE = MemoryStore(DATA_HOME / "agent")
    return _DEFAULT_MEMORY_STORE


__all__ = ["MemoryEntry", "MemoryStore", "get_memory_store"]


if __name__ == "__main__":
    store = get_memory_store()
    store.store("demo", "System is healthy and safe", memory_type="fact", importance=0.9, tags=["health", "safe"])
    print(store.search("health", limit=3))

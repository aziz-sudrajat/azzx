"""Pure-stdlib semantic embeddings for Hermes-like memory retrieval (v10.2).

No numpy / ML dependencies — intentionally Termux-friendly. Uses an
incremental TF-IDF vectorizer with L2-normalized sparse vectors and cosine
similarity. Good enough for ranking memories by meaning rather than by
literal keyword overlap.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_STOPWORDS = frozenset(
    {
        "yang", "dan", "atau", "untuk", "dengan", "dari", "ini", "itu", "saya",
        "aku", "kamu", "dia", "mereka", "kita", "adalah", "akan", "telah",
        "sudah", "belum", "juga", "saja", "the", "and", "or", "with", "from",
        "this", "that", "these", "those", "are", "was", "were", "have", "has",
        "will", "would", "could", "should", "what", "when", "where", "which",
        "how", "why", "not", "but", "for", "you", "your", "our", "their",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens without stopwords."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS]


class SimpleEmbedder:
    """Incremental TF-IDF embedder with cosine similarity.

    Document frequencies are updated on every `add_document` call and
    persisted to JSON, so the vocabulary improves over time without a
    full refit.
    """

    def __init__(self, state_path: str | Path | None = None) -> None:
        self.state_path = Path(state_path) if state_path else None
        self.doc_count: int = 0
        self.doc_freq: dict[str, int] = {}
        if self.state_path and self.state_path.exists():
            self._load()

    # -- persistence ----------------------------------------------------
    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.doc_count = int(data.get("doc_count", 0))
            self.doc_freq = {str(k): int(v) for k, v in (data.get("doc_freq") or {}).items()}
        except (OSError, ValueError):
            self.doc_count = 0
            self.doc_freq = {}

    def save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"doc_count": self.doc_count, "doc_freq": self.doc_freq}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.state_path)

    # -- fitting ---------------------------------------------------------
    def add_document(self, text: str) -> None:
        """Incorporate a document's term statistics (call on every store)."""
        terms = set(tokenize(text))
        if not terms:
            return
        self.doc_count += 1
        for term in terms:
            self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        # Smoothed IDF; unseen terms get the max (as if df=1).
        df = self.doc_freq.get(term, 0)
        return math.log((1 + self.doc_count) / (1 + df)) + 1.0

    # -- embedding --------------------------------------------------------
    def embed(self, text: str) -> dict[str, float]:
        """Return an L2-normalized sparse TF-IDF vector {term: weight}."""
        tokens = tokenize(text)
        if not tokens:
            return {}
        tf: dict[str, int] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        vec = {term: (count / len(tokens)) * self._idf(term) for term, count in tf.items()}
        norm = math.sqrt(sum(w * w for w in vec.values()))
        if norm <= 0:
            return {}
        return {term: w / norm for term, w in vec.items()}

    @staticmethod
    def similarity(a: dict[str, float], b: dict[str, float]) -> float:
        """Cosine similarity of two L2-normalized sparse vectors."""
        if not a or not b:
            return 0.0
        if len(a) > len(b):
            a, b = b, a
        return sum(w * b.get(term, 0.0) for term, w in a.items())

    def most_similar(
        self, query: str, candidates: list[tuple[Any, dict[str, float]]], limit: int = 10
    ) -> list[tuple[Any, float]]:
        """Rank (id, vector) candidates by similarity to the query."""
        qvec = self.embed(query)
        scored = [(cid, self.similarity(qvec, vec)) for cid, vec in candidates]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: max(1, limit)]


__all__ = ["SimpleEmbedder", "tokenize"]

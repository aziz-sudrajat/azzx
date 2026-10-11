"""Auto-chaining: features that invoke each other (v10.6.5).

Before v10.6.5 every command was siloed: ``azzx fix`` fixed, ``azzx learn``
learned, ``azzx recall`` recalled — the user had to run them one by one.
Now the main commands compose automatically:

- ``fix`` / ``implement`` / ``add`` / ``create`` → recall → do → learn
- ``review`` → recall → do → learn

``recall`` searches persistent memory for relevant entries and injects them
into the AI context. ``learn`` distills the run into *staged* proposals —
never auto-approved (the v10.4 trust gate is preserved).

Opt out per run: ``--no-recall``, ``--no-learn``.
Both helpers never raise: no memory / no provider → skip quietly.
"""
from __future__ import annotations

from typing import Any


def recall_block(query: str, limit: int = 5) -> str:
    """Return a memory context block relevant to query, or ''."""
    try:
        from azzx.agent.orchestrator import get_memory_store
        store = get_memory_store()
        try:
            hits = store.search_hybrid(query=query, limit=limit)
        except Exception:
            hits = []
        entries = []
        for entry, _score in hits or []:
            try:
                if float(getattr(entry, "importance", 0) or 0) < 0.5:
                    continue
                content = str(getattr(entry, "content", "") or "").strip()
                if content:
                    entries.append(content[:400])
            except Exception:
                continue
        if not entries:
            return ""
        lines = "\n".join(f"- {e}" for e in entries[:limit])
        return f"[RELEVANT MEMORY — from your past sessions]\n{lines}\n"
    except Exception:
        return ""


def auto_learn(goal: str, transcript: str) -> dict[str, Any] | None:
    """Distill learnings into staged proposals. None when skipped/failed."""
    goal = (goal or "").strip()
    transcript = (transcript or "").strip()
    if not goal or not transcript:
        return None
    try:
        from azzx.agent import learning
        return learning.distill(goal=goal, transcript=transcript)
    except Exception:
        return None


def learn_note(result: dict[str, Any] | None) -> str:
    """One-line human summary of an auto_learn result."""
    if not result:
        return "learn: skipped (no AI provider or nothing to distill)"
    n = int(result.get("memories_staged", 0) or 0) + int(result.get("skills_staged", 0) or 0)
    if n:
        return f"learn: {n} proposal(s) staged — review with `azzx learn`"
    return "learn: nothing new worth remembering"

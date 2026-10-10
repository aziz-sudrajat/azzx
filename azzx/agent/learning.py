"""Autonomous learning loop for AZZX (v10.5): distill, stage, review.

After a task (or on demand) the agent distills what it learned into:
- memory candidates  -> staged, applied to the memory store on approval
- skill ideas        -> drafted as ``skill.json`` + handler stub in a staging
                        directory, installed (untrusted + disabled, per the
                        trust-gate) only on explicit approval

Nothing is applied silently: proposals wait in
``~/.azzx/agent/learned/pending.json`` until ``azzx learn approve``.
This keeps the v10.4 trust-gate intact while giving AZZX a real learning loop.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azzx.core import AzzxError, DATA_HOME

_LEARN_CONTRACT = """\
You are a learning distiller. Given a transcript of a completed task, extract
durable lessons. Respond with a single JSON object and nothing else.
Shape:
{
  "memories": [
    {"content": "durable fact, preference, or lesson (one sentence)",
     "type": "fact|preference|lesson", "importance": 0.0-1.0, "tags": ["..."]}
  ],
  "skill_ideas": [
    {"id": "snake_case_id", "name": "Human Name",
     "description": "what it does and when to use it",
     "why": "why this deserves to become a skill"}
  ]
}
Rules:
- Only propose memories that will still be true next month. Skip trivia.
- Only propose a skill if the transcript shows a *repeatable* procedure worth
  reusing (not a one-off). Max 3 skill ideas.
- NEVER include secrets, API keys, tokens, passwords, or private paths.
- Keep content concise.
"""


def learned_dir() -> Path:
    d = Path(DATA_HOME) / "agent" / "learned"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pending_path() -> Path:
    return learned_dir() / "pending.json"


def _load_pending() -> dict[str, Any]:
    try:
        return json.loads(pending_path().read_text(encoding="utf-8"))
    except Exception:
        return {"memories": [], "skills": []}


def _save_pending(data: dict[str, Any]) -> None:
    pending_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def distill(
    goal: str,
    transcript: str,
    agent_id: str = "azzx",
    forced_provider: str | None = None,
    cancel_event: threading.Event | None = None,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    """Ask the provider to distill lessons; stage proposals for review."""
    goal = (goal or "").strip()
    transcript = (transcript or "").strip()
    if not goal or not transcript:
        raise AzzxError("distill needs a goal and a transcript")
    from azzx.agent.providers import default_router

    messages = [
        {"role": "system", "content": _LEARN_CONTRACT},
        {"role": "user", "content": (
            f"TASK GOAL: {goal}\n\nTRANSCRIPT (truncated):\n{transcript[:6000]}\n\n"
            "Distill now."
        )},
    ]
    router = default_router()
    try:
        result = router.chat(messages, forced_provider=forced_provider,
                             cancel_event=cancel_event, max_tokens=max_tokens)
    except Exception as exc:
        raise AzzxError(f"learning distill failed: {exc}")

    raw = result.text or ""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = m.group(1) if m else raw
    try:
        data = json.loads(blob)
    except Exception:
        s, e = blob.find("{"), blob.rfind("}")
        try:
            data = json.loads(blob[s : e + 1])
        except Exception:
            raise AzzxError("distiller returned unparseable output")

    pending = _load_pending()
    stamp = datetime.now(timezone.utc).isoformat()
    new_mems, new_skills = 0, 0

    for mem in (data.get("memories") or [])[:8]:
        if not isinstance(mem, dict) or not str(mem.get("content") or "").strip():
            continue
        # Secret refusal at the gate, same policy as the memory store.
        try:
            from azzx.agent.memory import find_secret_kind
            if find_secret_kind(str(mem["content"])):
                continue
        except Exception:
            pass
        try:
            importance = max(0.0, min(1.0, float(mem.get("importance", 0.6) or 0.6)))
        except (TypeError, ValueError):
            importance = 0.6
        pending["memories"].append({
            "content": str(mem["content"])[:500],
            "type": str(mem.get("type") or "lesson"),
            "importance": importance,
            "tags": [str(t)[:40] for t in (mem.get("tags") or [])][:6],
            "agent_id": agent_id,
            "from_goal": goal[:120],
            "staged_at": stamp,
            "status": "pending",
        })
        new_mems += 1

    for sk in (data.get("skill_ideas") or [])[:3]:
        if not isinstance(sk, dict):
            continue
        sid = re.sub(r"[^a-z0-9_]+", "_", str(sk.get("id") or "").lower()).strip("_")
        if not sid:
            continue
        draft_dir = learned_dir() / "skills" / sid
        draft_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "id": sid,
            "name": str(sk.get("name") or sid)[:80],
            "description": str(sk.get("description") or "")[:300],
            "version": "0.1.0",
            "handler": "handler:main",
            "permissions": [],
            "tags": ["learned"],
            "input_schema": {"type": "object", "properties": {}},
        }
        (draft_dir / "skill.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        (draft_dir / "handler.py").write_text(
            '"""Drafted by AZZX learning loop — implement before trusting."""\n\n\n'
            'def main(**kwargs):\n'
            '    raise NotImplementedError("draft skill: implement the handler first")\n',
            encoding="utf-8")
        (draft_dir / "WHY.md").write_text(
            f"# Why this skill was proposed\n\n{sk.get('why', '')}\n\nFrom goal: {goal[:200]}\n",
            encoding="utf-8")
        pending["skills"].append({
            "id": sid, "name": manifest["name"], "description": manifest["description"],
            "draft_dir": str(draft_dir), "from_goal": goal[:120],
            "staged_at": stamp, "status": "pending",
        })
        new_skills += 1

    _save_pending(pending)
    return {"memories_staged": new_mems, "skills_staged": new_skills,
            "provider": result.provider_id}


def list_pending() -> dict[str, Any]:
    return _load_pending()


def approve(kind: str, index: int, agent_id: str = "azzx") -> dict[str, Any]:
    """Approve one pending proposal: memory -> store, skill -> install (untrusted)."""
    pending = _load_pending()
    if kind == "memory":
        items = pending.get("memories", [])
    elif kind == "skill":
        items = pending.get("skills", [])
    else:
        raise AzzxError("kind must be 'memory' or 'skill'")
    pend = [p for p in items if p.get("status") == "pending"]
    if not (0 <= index < len(pend)):
        raise AzzxError(f"no pending {kind} at index {index}")
    item = pend[index]

    if kind == "memory":
        from azzx.agent.memory import get_memory_store
        store = get_memory_store()
        mid = store.store(
            agent_id=item.get("agent_id") or agent_id,
            content=item["content"],
            memory_type=item.get("type") or "lesson",
            importance=float(item.get("importance") or 0.6),
            tags=item.get("tags") or [],
            shared=True,
        )
        item["status"] = "approved"
        item["memory_id"] = mid
        _save_pending(pending)
        return {"approved": "memory", "memory_id": mid}
    else:
        from azzx.agent.skills import get_skill_registry
        reg = get_skill_registry()
        installed = reg.install(item["draft_dir"])
        sid = installed.get("installed") if isinstance(installed, dict) else str(installed)
        item["status"] = "approved"
        item["installed_id"] = sid
        _save_pending(pending)
        return {"approved": "skill", "skill_id": sid,
                "note": "installed untrusted + disabled; run "
                        f"'azzx skills trust {sid} && azzx skills enable {sid}' after review"}


def discard(kind: str, index: int) -> dict[str, Any]:
    pending = _load_pending()
    key = "memories" if kind == "memory" else ("skills" if kind == "skill" else None)
    if key is None:
        raise AzzxError("kind must be 'memory' or 'skill'")
    pend = [p for p in pending.get(key, []) if p.get("status") == "pending"]
    if not (0 <= index < len(pend)):
        raise AzzxError(f"no pending {kind} at index {index}")
    pend[index]["status"] = "discarded"
    _save_pending(pending)
    return {"discarded": kind, "index": index}

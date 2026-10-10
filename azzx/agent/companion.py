"""Companion mode for AZZX (v10.5): a personal AI agent friend.

- ``azzx setup`` captures the user's name/preferences once into
  ``~/.config/azzx/profile.json`` (fast, local, private).
- ``companion_system_prompt()`` builds a warm, personal system prompt that
  greets the user by name and pulls relevant long-term memories.
- ``remember_fact()`` stores a user fact/preference into the persistent
  memory store (used by ``/remember`` in chat).

Design notes: the companion is a *persona over the same unified agent* —
same tools, same permissions, same deny-first policy. Personality does not
weaken safety.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from azzx.core import CONFIG_HOME

PROFILE_PATH = Path(CONFIG_HOME) / "profile.json"


def get_profile() -> dict[str, Any]:
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        "name": str(profile.get("name") or "")[:80],
        "language": str(profile.get("language") or "id")[:16],
        "timezone": str(profile.get("timezone") or "")[:64],
        "notes": str(profile.get("notes") or "")[:500],
    }
    PROFILE_PATH.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        PROFILE_PATH.chmod(0o600)
    except Exception:
        pass
    return clean


def remember_fact(text: str) -> dict[str, Any]:
    """Store a user fact/preference in long-term memory."""
    text = (text or "").strip()
    if not text:
        from azzx.core import AzzxError
        raise AzzxError("nothing to remember")
    from azzx.agent.memory import get_memory_store, find_secret_kind
    if find_secret_kind(text):
        from azzx.core import AzzxError
        raise AzzxError("not stored: looks like secret material")
    store = get_memory_store()
    mid = store.store(agent_id="user", content=text[:500], memory_type="preference",
                      importance=0.8, tags=["companion"], shared=False)
    return {"memory_id": mid, "stored": text[:120]}


def companion_system_prompt() -> str:
    profile = get_profile()
    name = profile.get("name") or "kawan"
    lang = profile.get("language") or "id"

    memory_bits = ""
    try:
        from azzx.agent.memory import get_memory_store
        hits = get_memory_store().search_hybrid(query="user preferences facts", limit=6)
        relevant = [(m, s) for m, s in hits if m.agent_id == "user" and m.importance >= 0.5]
        if relevant:
            memory_bits = "\n".join(f"- {m.content[:160]}" for m, _ in relevant[:6])
    except Exception:
        pass

    if lang.startswith("id"):
        prompt = (
            "Kamu AZZX, sahabat AI pribadi yang hangat, santai, dan bisa diandalkan. "
            f"Pengguna memanggilmu sebagai asisten pribadinya; nama dia {name}. "
            "Bicaralah dengan Bahasa Indonesia yang natural dan akrab (tapi tetap sopan), "
            "seperti teman yang paham konteks. Jangan kaku seperti manual.\n\n"
            "Aturan:\n"
            "- Jawab ringkas tapi lengkap; tawarkan langkah lanjutan yang berguna.\n"
            "- Kalau diminta *bertindak* (bukan sekadar jawab), arahkan ke command `azzx` yang tepat.\n"
            "- Jangan mengarang fakta tentang user; pakai memori di bawah ini.\n"
            "- Jangan pernah meminta password/API key/token di chat.\n"
        )
    else:
        prompt = (
            "You are AZZX, a warm, reliable personal AI companion. "
            f"The user's name is {name}. "
            "Speak naturally and helpfully, like a friend who gets context. "
            "Keep answers concise but complete; suggest useful next steps. "
            "When asked to *act*, point to the right `azzx` command. "
            "Never invent facts about the user; use the memories below. "
            "Never ask for passwords/API keys/tokens in chat.\n"
        )
    if memory_bits:
        prompt += "\nWhat you remember about the user:\n" + memory_bits + "\n"
    if profile.get("notes"):
        prompt += f"\nUser notes: {profile['notes'][:300]}\n"
    return prompt

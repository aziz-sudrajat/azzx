"""Smart intent router for `azzx do` (v10.6.6).

Problem: 93 top-level commands confuse users. `azzx do "<natural language>"`
is the single front door: it detects the intent (Indonesian + English
keywords, fully offline and deterministic) and routes to the right pipeline.

Design rules:
- Keywords, not AI: routing must work offline and be predictable.
- Always transparent: `do` prints which command it runs, so users learn it.
- Safe set only: `do` never routes to destructive ops (uninstall, gateway,
  permissions, ...). Those stay explicit.
- Unknown input falls back to `ask` (AI answers directly).

Each intent entry: (keywords, target, strip_words).
``strip_words`` are leading verbs removed from the task before passing on,
so `do "perbaiki bug login"` becomes `fix "bug login"`.
"""
from __future__ import annotations

import re

# (keywords, target command, verbs to strip from the front of the task)
INTENTS: list[tuple[frozenset[str], str, frozenset[str]]] = [
    (frozenset({"perbaiki", "betulkan", "benerin", "fix", "bug", "rusak",
                "crash", "gagal", "broken", "error", "errornya", "eror"}),
     "fix",
     frozenset({"perbaiki", "betulkan", "benerin", "fix", "tolong"})),
    (frozenset({"tambah", "tambahkan", "add", "buat", "buatkan", "bikin",
                "bikinin", "implement", "fitur", "feature", "kembangkan"}),
     "implement",
     frozenset({"tambah", "tambahkan", "add", "buat", "buatkan", "bikin",
                "bikinin", "tolong"})),
    (frozenset({"review", "ulas", "periksa kode", "cek kode", "audit kode"}),
     "review",
     frozenset({"review", "tolong"})),
    (frozenset({"debug", "tracing", "telusur"}),
     "debug",
     frozenset({"debug", "tolong"})),
    (frozenset({"test", "tes", "testing", "uji"}),
     "test",
     frozenset({"test", "tes", "testing", "tolong", "jalankan", "jalanin"})),
    (frozenset({"cari", "search", "carikan", "web", "internet", "online",
                "harga", "berita", "google", "browsing"}),
     "web",
     frozenset({"cari", "carikan", "search", "tolong"})),
    (frozenset({"buka", "fetch", "ambil halaman"}),
     "fetch",
     frozenset({"buka", "bukakan", "fetch", "tolong"})),
    (frozenset({"ingat", "inget", "remember", "catat", "hafal", "simpen"}),
     "remember",
     frozenset({"ingat", "inget", "remember", "catat", "tolong", "bahwa"})),
    (frozenset({"lupa", "recall", "cari ingatan", "apa yang"}),
     "recall",
     frozenset({"recall", "tolong"})),
    (frozenset({"rencana", "plan", "rancang"}),
     "plan",
     frozenset({"rencana", "buatkan", "tolong"})),
    (frozenset({"otomatis", "auto", "kerjakan sendiri"}),
     "auto",
     frozenset({"otomatis", "tolong"})),
    (frozenset({"ringkas", "compress", "padatkan", "kecilkan"}),
     "compress",
     frozenset({"ringkas", "compress", "tolong"})),
    (frozenset({"cek kesehatan", "kesehatan sistem", "doctor", "diagnosa sistem",
                "periksa sistem"}),
     "doctor",
     frozenset({"cek", "doctor", "tolong"})),
    (frozenset({"checkpoint", "snapshot", "backup project", "cadangkan",
                "titik pulih"}),
     "checkpoint",
     frozenset({"buat", "buatkan", "checkpoint", "tolong"})),
    (frozenset({"lihat jadwal", "jadwal saya", "daftar jadwal", "list schedule"}),
     "schedule",
     frozenset({"lihat", "tolong"})),
    (frozenset({"audit", "periksa pekerjaan", "cek audit", "nilai kerja"}),
     "audit",
     frozenset({"audit", "tolong"})),
    (frozenset({"tambahkan fitur untukmu", "tambah fitur untukmu", "buatkan skill",
                "extend", "fitur baru untukmu", "upgrade dirimu",
                "tambahkan kemampuan", "skill baru"}),
     "extend",
     frozenset({"tambahkan", "tambah", "buatkan", "tolong"})),
    (frozenset({"kembangkan dirimu", "belajar dari kebiasaanku", "evolve",
                "perbaiki dirimu", "upgrade dirimu sendiri", "analisa kebiasaanku"}),
     "evolve",
     frozenset({"tolong"})),
    (frozenset({"tanya", "ask", "jelaskan", "gimana", "bagaimana", "apa itu",
                "kenapa", "mengapa"}),
     "ask",
     frozenset({"tanya", "ask", "tolong"})),
]

# Minimum score to accept a routed intent (else fall back to ask).
_MIN_SCORE = 1


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_./-]{2,}", (text or "").lower())


def _strip_leading(target: str, strip: frozenset[str], words: list[str],
                   text: str) -> tuple[str, str, int]:
    cleaned = words[:]
    while cleaned and cleaned[0] in strip:
        cleaned.pop(0)
    task = " ".join(cleaned).strip() or text
    return target, task, 99


def route(text: str) -> tuple[str, str, int]:
    """Route natural language to (target, cleaned_task, score).

    Falls back to ("ask", text, 0) when nothing matches confidently.
    """
    text = (text or "").strip()
    if not text:
        return "ask", "", 0
    words = _words(text)
    wordset = set(words)
    lowered = text.lower()
    # Multi-word phrase at the START beats single first-word matches:
    # "tambahkan fitur untukmu" -> extend, not implement.
    for keywords, target, _strip in INTENTS:
        for kw in keywords:
            if " " in kw and lowered.startswith(kw + " ") or lowered == kw:
                _, task, _ = _strip_leading(target, _strip, words, text)
                return target, task, 99
    # Explicit leading verb wins outright: "debug X" -> debug, "review X" -> review.
    # Generic maker verbs ("buatkan", "buat", ...) don't count — the object
    # decides: "buatkan rencana" -> plan, "buatkan fungsi" -> implement.
    _GENERIC = frozenset({"buat", "buatkan", "bikin", "bikinin", "tolong"})
    if words:
        first = words[0]
        if first not in _GENERIC:
            for keywords, target, _strip in INTENTS:
                if first in keywords and " " not in first:
                    _, task, _ = _strip_leading(target, _strip, words, text)
                    return target, task, 99
    best: tuple[str, frozenset[str]] | None = None
    best_key: tuple[int, int] = (0, -1)  # (score, rightmost match index)
    for keywords, target, _strip in INTENTS:
        # Multi-word keywords need substring matching.
        score = 0
        right = -1
        for kw in keywords:
            if " " in kw:
                if kw in lowered:
                    score += 3  # multi-word phrases are more specific
                    right = max(right, lowered.find(kw))
            elif kw in wordset:
                score += 2 if len(kw) > 4 else 1
                try:
                    right = max(right, len(words) - 1 - words[::-1].index(kw))
                except ValueError:
                    pass
        key = (score, right)
        # Ties break toward the intent whose keyword appears furthest right
        # (closest to the object): "buatkan rencana X" -> plan, not implement.
        if key > best_key:
            best_key = key
            best = (target, _strip)
    if best is None or best_key[0] < _MIN_SCORE:
        return "ask", text, 0
    target, strip = best
    score = best_key[0]
    # Strip leading intent verbs: "perbaiki bug login" -> "bug login".
    cleaned = words[:]
    while cleaned and cleaned[0] in strip:
        cleaned.pop(0)
    task = " ".join(cleaned).strip() or text
    return target, task, score


def describe_target(target: str) -> str:
    return {
        "fix": "AI-driven code fix (auto recall + learn)",
        "implement": "AI-driven build / add feature (auto recall + learn)",
        "review": "static code review (auto recall + learn)",
        "debug": "run a command and diagnose the failure",
        "test": "run the project's tests",
        "web": "autonomous web browsing that solves by itself",
        "fetch": "fetch a web page as readable text",
        "remember": "save a fact to long-term memory",
        "recall": "search long-term memory",
        "plan": "generate an execution plan",
        "auto": "autonomous run: plan → approve → execute → learn",
        "compress": "shrink a large file before using it as context",
        "doctor": "system health check (offline)",
        "checkpoint": "snapshot the working directory",
        "schedule": "list scheduled jobs",
        "audit": "audit the agent's recent work",
        "extend": "build a new skill/feature for itself",
        "evolve": "self-improvement: learn habits, propose upgrades",
        "ask": "ask the AI anything",
    }.get(target, target)

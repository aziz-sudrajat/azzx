"""Autonomous web agent for AZZX (v10.6): a browser that solves by itself.

``azzx webauto "<task>"`` works like a miniature version of Muse's own
browser: you give it a *task*, and it searches the web, opens pages, follows
links, and keeps going until it can answer — all by itself, in the background.

How it differs from ``azzx browse``:
- ``browse`` = one page, one shot (you drive).
- ``webauto`` = a goal-driven loop: search → read → decide → follow → answer.

Honest limits (same as the reader it is built on):
- Text web only: no JavaScript rendering, no logins behind JS, no captchas.
- Read-only: the agent never submits forms or clicks state-changing buttons.
- Search uses DuckDuckGo's static HTML endpoint; if DDG blocks the request,
  pass ``--start-url`` explicitly.

All navigation goes through the permission gate (``web.read``) and the SSRF
guard in ``webreader``.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from azzx.core import AzzxError

DECIDE_SYSTEM = """You are a web research agent. You are given a TASK and the current
page (title, URL, readable text, outbound links). Decide the next step.

Reply with JSON ONLY, one of:
{"action": "answer", "answer": "<final answer, concise but complete>"}
{"action": "follow", "url": "<one URL copied EXACTLY from the links list>", "why": "<short reason>"}

Rules:
- Only follow URLs that appear EXACTLY in the links list. Never invent URLs.
- Answer as soon as the page contains what the task needs. Quote facts.
- If the page is useless, follow the most promising link toward the task.
- If nothing leads anywhere after a few hops, answer with what you found so far."""


def _default_decider(task: str, page: dict[str, Any], trail: list[str]) -> dict[str, Any]:
    from azzx.agent.providers import default_router

    links_txt = "\n".join(f"- {l['text'][:80]} :: {l['href']}"
                          for l in page.get("links", [])[:40])
    visited = "\n".join(f"- {u}" for u in trail[-8:])
    prompt = (f"TASK: {task}\n\nCURRENT PAGE: {page.get('title')}\n"
              f"URL: {page.get('final_url')}\n\nPAGE TEXT (excerpt):\n"
              f"{page.get('text', '')[:6000]}\n\nOUTBOUND LINKS:\n{links_txt or '(none)'}\n"
              f"\nALREADY VISITED:\n{visited or '(none)'}")
    router = default_router()
    try:
        raw = router.chat([
            {"role": "system", "content": DECIDE_SYSTEM},
            {"role": "user", "content": prompt},
        ], max_tokens=600).text.strip()
    except Exception as exc:
        raise AzzxError(f"webauto needs an AI provider: {exc}")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise AzzxError(f"webauto: could not parse agent decision: {raw[:120]}")
    try:
        decision = json.loads(m.group(0))
    except Exception:
        raise AzzxError(f"webauto: invalid decision JSON: {m.group(0)[:120]}")
    if decision.get("action") not in ("answer", "follow"):
        raise AzzxError(f"webauto: unknown action: {decision.get('action')}")
    return decision


class WebAgent:
    """Goal-driven browsing loop."""

    def __init__(self, max_steps: int = 12,
                 fetcher: Callable[[str], dict[str, Any]] | None = None,
                 decider: Callable[..., dict[str, Any]] | None = None) -> None:
        from azzx.agent.webreader import fetch
        self.max_steps = max(1, min(int(max_steps), 40))
        self._fetch = fetcher or fetch
        self._decide = decider or _default_decider
        self.trail: list[str] = []

    def run(self, task: str, start_url: str | None = None) -> dict[str, Any]:
        from azzx.agent.webreader import search as web_search

        task = (task or "").strip()
        if not task:
            raise AzzxError("task required")
        if start_url:
            current = start_url
        else:
            results = web_search(task)
            if not results:
                return {"status": "no_results", "task": task, "trail": []}
            current = results[0]["href"]

        steps = 0
        while steps < self.max_steps:
            steps += 1
            page = self._fetch(current)
            self.trail.append(page.get("final_url", current))
            decision = self._decide(task, page, self.trail)
            if decision.get("action") == "answer":
                return {"status": "answered", "task": task,
                        "answer": str(decision.get("answer", ""))[:4000],
                        "steps": steps, "trail": self.trail}
            nxt = str(decision.get("url", "")).strip()
            allowed = {l["href"] for l in page.get("links", [])}
            if nxt not in allowed:
                return {"status": "blocked", "task": task,
                        "reason": "agent tried to visit a URL not on the page; stopped",
                        "steps": steps, "trail": self.trail}
            current = nxt
        return {"status": "max_steps", "task": task,
                "reason": f"gave up after {self.max_steps} pages",
                "steps": steps, "trail": self.trail}

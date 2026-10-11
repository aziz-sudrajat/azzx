"""Autonomous web agent for AZZX (v10.6): a browser that solves by itself.

``azzx webauto "<task>"`` works like a miniature version of Muse's own
browser: you give it a *task*, and it searches the web, opens pages, follows
links, and keeps going until it can answer — all by itself, in the background.

How it differs from ``azzx browse``:
- ``browse`` = one page, one shot (you drive).
- ``webauto`` = a goal-driven loop: search → read → decide → follow → answer.

Two modes (``azzx browse mode``):
- ``read`` (default): the agent never submits forms or changes state.
- ``write``: the agent may also fill + submit HTML forms (``--write``).
  HTTP-level only — no JavaScript — so server-rendered forms, not SPAs.
  Every submit goes through permission approval + audit.

Honest limits (same as the reader it is built on):
- Text web only: no JavaScript rendering, no logins behind JS, no captchas.
- Search uses DuckDuckGo's static HTML endpoint; if DDG blocks the request,
  pass ``--start-url`` explicitly.

All navigation goes through the permission gate and the SSRF guard.
"""
from __future__ import annotations

import json
import re
import time
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

DECIDE_SYSTEM_WRITE = """You are a web automation agent. You are given a TASK and the current
page (title, URL, readable text, outbound links, HTML FORMS). Decide the next step.

Reply with JSON ONLY, one of:
{"action": "answer", "answer": "<final answer, concise but complete>"}
{"action": "follow", "url": "<one URL copied EXACTLY from the links list>", "why": "<short reason>"}
{"action": "submit", "form": <form index>, "fields": {"fieldname": "value"}, "why": "<short reason>"}

Rules:
- Only follow URLs that appear EXACTLY in the links list. Never invent URLs.
- Only submit forms listed in FORMS below, using their exact field names.
  Never submit password fields unless the task explicitly provides credentials.
- Prefer read-only steps; submit only when the task requires an action.
- Answer as soon as the task is done. Quote facts."""


def _default_decider(task: str, page: dict[str, Any], trail: list[str],
                     write_mode: bool = False) -> dict[str, Any]:
    from azzx.agent.providers import default_router

    links_txt = "\n".join(f"- {l['text'][:80]} :: {l['href']}"
                          for l in page.get("links", [])[:40])
    visited = "\n".join(f"- {u}" for u in trail[-8:])
    system = DECIDE_SYSTEM_WRITE if write_mode else DECIDE_SYSTEM
    prompt = (f"TASK: {task}\n\nCURRENT PAGE: {page.get('title')}\n"
              f"URL: {page.get('final_url')}\n\nPAGE TEXT (excerpt):\n"
              f"{page.get('text', '')[:6000]}\n\nOUTBOUND LINKS:\n{links_txt or '(none)'}\n"
              f"\nALREADY VISITED:\n{visited or '(none)'}")
    if write_mode:
        forms_txt = "\n".join(
            f"- [{i}] {f['method']} {f['action']} fields: "
            f"{', '.join(inp['name'] + '(' + inp['type'] + ')' for inp in f['inputs'])}"
            for i, f in enumerate(page.get("forms", [])[:6]))
        prompt += f"\n\nFORMS ON PAGE:\n{forms_txt or '(none)'}"
    router = default_router()
    try:
        raw = router.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], max_tokens=700).text.strip()
    except Exception as exc:
        raise AzzxError(f"webauto needs an AI provider: {exc}")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise AzzxError(f"webauto: could not parse agent decision: {raw[:120]}")
    try:
        decision = json.loads(m.group(0))
    except Exception:
        raise AzzxError(f"webauto: invalid decision JSON: {m.group(0)[:120]}")
    allowed = ("answer", "follow", "submit") if write_mode else ("answer", "follow")
    if decision.get("action") not in allowed:
        raise AzzxError(f"webauto: unknown action: {decision.get('action')}")
    return decision


class WebAgent:
    """Goal-driven browsing loop."""

    def __init__(self, max_steps: int = 12,
                 fetcher: Callable[[str], dict[str, Any]] | None = None,
                 decider: Callable[..., dict[str, Any]] | None = None,
                 write_mode: bool = False,
                 noninteractive_submit: bool = False) -> None:
        from azzx.agent.webreader import fetch
        from azzx.agent.webforms import browser_mode, WRITE
        self.max_steps = max(1, min(int(max_steps), 40))
        self._fetch = fetcher or fetch
        self._decide = decider or _default_decider
        # Write mode: explicit flag OR the user's browser.mode setting.
        self.write_mode = bool(write_mode) or browser_mode() == WRITE
        self.noninteractive_submit = noninteractive_submit
        self.trail: list[str] = []

    def run(self, task: str, start_url: str | None = None) -> dict[str, Any]:
        from azzx.agent.webreader import search as web_search
        from azzx.agent import auditor

        task = (task or "").strip()
        if not task:
            raise AzzxError("task required")
        run_id = auditor.start_run(f"webauto: {task}")
        try:
            return self._run_inner(task, start_url, run_id)
        finally:
            auditor.end_run()

    def _run_inner(self, task: str, start_url: str | None, run_id: str) -> dict[str, Any]:
        from azzx.agent.webreader import search as web_search
        from azzx.agent import auditor

        if start_url:
            current = start_url
        else:
            results = web_search(task)
            if not results:
                return {"status": "no_results", "task": task, "run_id": run_id, "trail": []}
            current = results[0]["href"]

        steps = 0
        while steps < self.max_steps:
            steps += 1
            t0 = time.monotonic()
            page = self._fetch(current)
            if self.write_mode:
                # Attach parsed forms so the decider can submit them.
                try:
                    from azzx.agent.webforms import forms as _forms
                    page["forms"] = _forms(current).get("forms", [])
                except Exception:
                    page["forms"] = []
            auditor.log_custom("web.fetch", ok=True, detail=page.get("final_url", current),
                               duration_ms=int((time.monotonic() - t0) * 1000))
            self.trail.append(page.get("final_url", current))
            try:
                decision = self._decide(task, page, self.trail, self.write_mode)
            except TypeError:
                # Custom deciders with the old (task, page, trail) signature.
                decision = self._decide(task, page, self.trail)
            if decision.get("action") == "answer":
                return {"status": "answered", "task": task, "run_id": run_id,
                        "answer": str(decision.get("answer", ""))[:4000],
                        "steps": steps, "trail": self.trail}
            if decision.get("action") == "submit":
                if not self.write_mode:
                    return {"status": "blocked", "task": task, "run_id": run_id,
                            "reason": "agent tried to submit a form in read mode; stopped",
                            "steps": steps, "trail": self.trail}
                sub = self._do_submit(current, decision)
                self.trail.append(f"submit:{sub.get('final_url', current)}")
                # Continue from the submit result page.
                current = sub.get("final_url", current)
                page = {"title": "", "final_url": current,
                        "text": sub.get("body_excerpt", ""),
                        "links": [], "forms": []}
                continue
            nxt = str(decision.get("url", "")).strip()
            allowed = {l["href"] for l in page.get("links", [])}
            if nxt not in allowed:
                return {"status": "blocked", "task": task, "run_id": run_id,
                        "reason": "agent tried to visit a URL not on the page; stopped",
                        "steps": steps, "trail": self.trail}
            current = nxt
        return {"status": "max_steps", "task": task, "run_id": run_id,
                "reason": f"gave up after {self.max_steps} pages",
                "steps": steps, "trail": self.trail}

    def _do_submit(self, url: str, decision: dict[str, Any]) -> dict[str, Any]:
        """Submit a form via run_tool_call (permission + audit apply)."""
        from azzx.agent.orchestrator import run_tool_call
        fields = decision.get("fields") or {}
        if not isinstance(fields, dict):
            raise AzzxError("webauto: submit fields must be an object")
        return run_tool_call("web.submit", {
            "url": url,
            "form_index": int(decision.get("form", 0) or 0),
            "fields": {str(k): str(v) for k, v in fields.items()},
            "session": "webauto",
        }, noninteractive=self.noninteractive_submit)

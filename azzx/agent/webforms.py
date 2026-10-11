"""Browser WRITE mode for AZZX (v10.6.5): HTTP-level form automation.

Two browser modes (user setting, ``browser.mode`` in config):

- ``read`` (default) — ``web.fetch`` / ``web.links`` / ``web.search`` only.
  The agent can look but never touch.
- ``write`` — additionally ``web.forms`` (list forms on a page) and
  ``web.submit`` (fill + submit a form). HTTP-level only: **no JavaScript**,
  so this handles server-rendered forms, not SPAs. Cookie sessions persist
  per named session for multi-step flows (e.g. login → act).

Safety, even in write mode:
- Every target URL passes the SSRF guard (no loopback/private hosts).
- ``web.submit`` requires the ``browser.write`` permission (ask by default;
  explicit deny is absolute, ``-y`` cannot bypass it).
- Every submit is audit-logged via ``run_tool_call`` like any other tool.
- Switch modes only explicitly: ``azzx browse mode write``.
"""
from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from azzx.core import AzzxError

READ = "read"
WRITE = "write"

_sessions: dict[str, Any] = {}


def browser_mode() -> str:
    """Current browser mode from config ('read' default)."""
    try:
        import json
        from azzx.core import CONFIG_FILE
        if CONFIG_FILE.is_file():
            mode = str(json.loads(CONFIG_FILE.read_text()).get("browser_mode", READ))
            return WRITE if mode == WRITE else READ
    except Exception:
        pass
    return READ


def set_browser_mode(mode: str) -> str:
    """Set browser mode. Only 'read' or 'write'."""
    import json
    from azzx.core import CONFIG_FILE
    mode = (mode or "").strip().lower()
    if mode not in (READ, WRITE):
        raise AzzxError("mode must be 'read' or 'write'")
    try:
        cfg = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.is_file() else {}
    except Exception:
        cfg = {}
    cfg["browser_mode"] = mode
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    try:
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass
    return mode


def _check_write_mode() -> None:
    if browser_mode() != WRITE:
        raise AzzxError(
            "browser is in READ mode — form submission is disabled. "
            "Enable write mode explicitly: azzx browse mode write")


class _FormParser(HTMLParser):
    """Extract <form> elements: action, method, inputs."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.forms: list[dict[str, Any]] = []
        self._cur: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            action = a.get("action", "").strip()
            self._cur = {
                "action": urllib.parse.urljoin(self.base_url, action) if action else self.base_url,
                "method": a.get("method", "get").upper() or "GET",
                "inputs": [],
            }
        elif tag == "input" and self._cur is not None:
            name = a.get("name", "").strip()
            if name:
                self._cur["inputs"].append({
                    "name": name,
                    "type": a.get("type", "text").lower() or "text",
                    "value": a.get("value", ""),
                })
        elif tag in ("textarea", "select") and self._cur is not None:
            name = a.get("name", "").strip()
            if name:
                self._cur["inputs"].append({"name": name, "type": tag, "value": ""})
        elif tag == "button" and self._cur is not None:
            name = a.get("name", "").strip()
            if name:
                self._cur["inputs"].append({"name": name, "type": "submit", "value": a.get("value", "")})

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._cur is not None:
            self.forms.append(self._cur)
            self._cur = None


def forms(url: str) -> dict[str, Any]:
    """List HTML forms on a page (read-only; works in both modes)."""
    from azzx.agent.webreader import _check_url, fetch
    _check_url(url)
    page = fetch(url)
    parser = _FormParser(page.get("final_url", url))
    try:
        # Re-fetch raw HTML for form parsing (fetch() returns text only).
        import httpx
        resp = httpx.get(_check_url(url), timeout=20.0, follow_redirects=True,
                         headers={"User-Agent": "AZZX-webreader/10.6"})
        parser.feed(resp.text[:500_000])
    except Exception:
        pass
    return {"url": page.get("final_url", url), "title": page.get("title", ""),
            "forms": [
                {"index": i, "action": f["action"], "method": f["method"],
                 "inputs": f["inputs"]}
                for i, f in enumerate(parser.forms)
            ]}


def _get_session(name: str):
    import httpx
    if name not in _sessions:
        _sessions[name] = httpx.Client(
            timeout=30.0, follow_redirects=True,
            headers={"User-Agent": "AZZX-webreader/10.6"})
    return _sessions[name]


def submit(url: str, form_index: int = 0, fields: dict[str, str] | None = None,
           session: str = "default") -> dict[str, Any]:
    """Fill + submit a form. WRITE mode + browser.write permission required."""
    from azzx.agent.webreader import _check_url
    _check_write_mode()
    info = forms(url)
    flist = info["forms"]
    if not flist:
        raise AzzxError("no HTML forms found on this page")
    try:
        form = flist[int(form_index)]
    except (IndexError, ValueError, TypeError):
        raise AzzxError(f"form index out of range (0-{len(flist)-1})")
    action = _check_url(form["action"])
    data = {inp["name"]: inp.get("value", "") for inp in form["inputs"]
            if inp["type"] not in ("submit", "button", "file")}
    for k, v in (fields or {}).items():
        data[str(k)] = str(v)
    # Never submit password-looking fields without explicit field values.
    pw_names = [i["name"] for i in form["inputs"] if i["type"] == "password"]
    for pn in pw_names:
        if pn not in (fields or {}):
            raise AzzxError(
                f"form has a password field '{pn}' — pass it explicitly in fields")
    client = _get_session(session or "default")
    try:
        if form["method"] == "POST":
            resp = client.post(action, data=data)
        else:
            resp = client.get(action, params=data)
        resp.raise_for_status()
    except Exception as exc:
        raise AzzxError(f"submit failed: {exc}")
    text = resp.text[:20000]
    # Return a compact result: status, final URL, and whether the response
    # looks like a success or an error page.
    return {
        "status": resp.status_code,
        "final_url": str(resp.url),
        "method": form["method"],
        "fields_sent": sorted(data.keys()),
        "session": session or "default",
        "body_excerpt": re.sub(r"\s+", " ", text)[:1500],
    }


def close_session(session: str = "default") -> None:
    client = _sessions.pop(session or "default", None)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


def register_webform_tools() -> None:
    """Register web.forms / web.submit / web.session_close."""
    from azzx.core import REGISTRY, ToolSpec

    REGISTRY.register(ToolSpec(
        name="web.forms",
        description="List HTML forms on a page (read-only).",
        permissions=[],
        handler=lambda url: forms(url),
        schema={"url": "str (required)"},
    ))
    REGISTRY.register(ToolSpec(
        name="web.submit",
        description=("Fill + submit an HTML form (HTTP-level, no JS). "
                     "Requires browser WRITE mode; password fields must be "
                     "passed explicitly."),
        permissions=["browser.write"],
        handler=lambda url, form_index=0, fields=None, session="default": submit(
            url, int(form_index), fields or {}, session),
        schema={"url": "str (required)", "form_index": "int",
                "fields": "dict", "session": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="web.session_close",
        description="Close a named browser session (clears cookies).",
        permissions=[],
        handler=lambda session="default": (close_session(session), {"closed": session})[1],
        schema={"session": "str"},
    ))

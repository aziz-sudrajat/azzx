"""Lightweight web reader for AZZX (v10.6): browse without a browser.

Fetches pages over HTTP with httpx (already a dependency) and extracts the
readable text, title, and links using only the standard library — no
Playwright, no Chromium, no hundreds of megabytes. This is the honest
trade-off for the "runs on a potato" promise:

- CAN: read articles/docs, follow links, extract text, run in background
  (via queue/schedule), feed pages to the agent as context.
- CANNOT: render JavaScript, log in through JS-heavy flows, take screenshots,
  or drive complex web apps. For that you need Playwright (deliberately not
  bundled — it would break the lightweight guarantee).

Tools: ``web.fetch`` (full page as text) and ``web.links`` (outbound links).
"""
from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from azzx.core import AzzxError

MAX_CHARS = 30_000
MAX_LINKS = 200
_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}


class _TextExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._cur_href = ""
        self._cur_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href", "") or ""
            self._cur_href = urllib.parse.urljoin(self.base_url, href.strip())
            self._cur_text = []
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._cur_href:
            label = " ".join("".join(self._cur_text).split())
            if label and self._cur_href.startswith(("http://", "https://")):
                if len(self.links) < MAX_LINKS:
                    self.links.append({"text": label[:120], "href": self._cur_href})
            self._cur_href = ""
            self._cur_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data.strip())
            return
        chunk = data.strip()
        if not chunk:
            return
        self.text_parts.append(chunk + " ")
        if self._cur_href:
            self._cur_text.append(chunk + " ")

    def result(self) -> dict[str, Any]:
        raw = "".join(self.text_parts)
        text = re.sub(r"[ \t]+", " ", raw)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        return {
            "title": " ".join(self.title_parts).strip()[:200],
            "text": text[:MAX_CHARS],
            "truncated": len(text) > MAX_CHARS,
            "links": self.links,
        }


def _check_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise AzzxError("url required")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    host = urllib.parse.urlparse(url).hostname or ""
    # SSRF guard: refuse loopback / link-local targets.
    if host in ("localhost", "127.0.0.1", "::1") or host.startswith(("10.", "192.168.")) \
            or host.startswith("172.") or host.endswith(".local"):
        raise AzzxError(f"refusing to fetch non-public host: {host}")
    return url


def fetch(url: str, timeout: float = 20.0) -> dict[str, Any]:
    """Fetch a page and return title/text/links. Raises AzzxError on failure."""
    import httpx

    url = _check_url(url)
    headers = {"User-Agent": "AZZX-webreader/10.6 (+https://github.com/aziz-sudrajat/azzx)"}
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        # Broken proxy env (e.g. malformed no_proxy entries) breaks httpx's
        # proxy parsing; retry direct before giving up.
        if "proxy" in str(exc).lower() or "invalid port" in str(exc).lower():
            try:
                with httpx.Client(trust_env=False, timeout=timeout,
                                  follow_redirects=True, headers=headers) as client:
                    resp = client.get(url)
                resp.raise_for_status()
            except Exception as exc2:
                raise AzzxError(f"fetch failed: {exc2}")
        else:
            raise AzzxError(f"fetch failed: {exc}")
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise AzzxError(f"unsupported content-type: {ctype or 'unknown'}")
    parser = _TextExtractor(str(resp.url))
    try:
        parser.feed(resp.text[:500_000])
    except Exception:
        pass
    out = parser.result()
    out["url"] = url
    out["final_url"] = str(resp.url)
    out["status"] = resp.status_code
    return out


class _DDGParser(HTMLParser):
    """Parse DuckDuckGo's static HTML results (html.duckduckgo.com/html/)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._in_a = False
        self._href = ""
        self._text: list[str] = []
        self._in_result = False
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        cls = attrs_d.get("class", "") or ""
        if tag == "div" and "result__body" in cls:
            self._in_result = True
            self._depth = 0
        if self._in_result:
            if tag == "div":
                self._depth += 1
            if tag == "a" and "result__a" in cls:
                self._in_a = True
                self._href = attrs_d.get("href", "") or ""
                self._text = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_a and tag == "a":
            title = " ".join("".join(self._text).split()).strip()
            href = self._href
            # DDG wraps links in a redirect: //duckduckgo.com/l/?uddg=<real>
            m = re.search(r"[?&]uddg=([^&]+)", href)
            if m:
                href = urllib.parse.unquote(m.group(1))
            if title and href.startswith("http"):
                self.results.append({"title": title[:160], "href": href})
            self._in_a = False
        if self._in_result and tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self._in_result = False

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._text.append(data)


def search(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Web search via DuckDuckGo's static HTML endpoint. Raises AzzxError."""
    import httpx

    query = (query or "").strip()
    if not query:
        raise AzzxError("query required")
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    try:
        resp = httpx.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120 Safari/537.36"},
            follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        if "proxy" in str(exc).lower() or "invalid port" in str(exc).lower():
            try:
                with httpx.Client(trust_env=False, timeout=20,
                                  follow_redirects=True) as client:
                    resp = client.get(url)
                resp.raise_for_status()
            except Exception as exc2:
                raise AzzxError(f"search failed: {exc2}")
        else:
            raise AzzxError(f"search failed: {exc}")
    parser = _DDGParser()
    try:
        parser.feed(resp.text[:500_000])
    except Exception:
        pass
    return parser.results[:max(1, min(int(limit), 20))]


def register_webreader_tools() -> None:
    from azzx.core import REGISTRY, ToolSpec

    def _fetch(url: str) -> dict[str, Any]:
        page = fetch(url)
        return {"url": page["final_url"], "title": page["title"],
                "text": page["text"], "truncated": page["truncated"]}

    def _links(url: str) -> dict[str, Any]:
        page = fetch(url)
        return {"url": page["final_url"], "title": page["title"], "links": page["links"]}

    def _search(query: str, limit: int = 8) -> dict[str, Any]:
        return {"query": query, "results": search(query, limit)}

    REGISTRY.register(ToolSpec(
        name="web.fetch",
        description="Fetch a web page and return its readable text (no JS rendering).",
        permissions=["web.read"],
        handler=_fetch,
        schema={"url": "str (required)"},
    ))
    REGISTRY.register(ToolSpec(
        name="web.links",
        description="Fetch a web page and return its outbound links.",
        permissions=["web.read"],
        handler=_links,
        schema={"url": "str (required)"},
    ))
    REGISTRY.register(ToolSpec(
        name="web.search",
        description="Search the web (DuckDuckGo) and return ranked results.",
        permissions=["web.read"],
        handler=_search,
        schema={"query": "str (required)", "limit": "int"},
    ))

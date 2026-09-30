"""Network connectivity and website status."""
from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urlparse

from azzx.core import REGISTRY, ToolSpec, AzzxError, require_permission


def check_connectivity(host: str = "1.1.1.1", port: int = 443, timeout: float = 3.0) -> dict[str, Any]:
    require_permission("network.http", detail=f"connect {host}:{port}")
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.close()
        return {"host": host, "port": port, "reachable": True}
    except OSError as exc:
        return {"host": host, "port": port, "reachable": False, "error": str(exc)}


def website_status(url: str, timeout: float = 10.0) -> dict[str, Any]:
    require_permission("network.http", detail=f"GET {url}")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AzzxError("URL must be http or https")
    if not parsed.netloc:
        raise AzzxError("Invalid URL")
    try:
        import httpx
    except ImportError as exc:
        raise AzzxError("httpx is required for website_status") from exc
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
        return {
            "url": url,
            "status_code": resp.status_code,
            "ok": 200 <= resp.status_code < 400,
            "final_url": str(resp.url),
            "elapsed_ms": int(resp.elapsed.total_seconds() * 1000),
            "content_type": resp.headers.get("content-type", ""),
        }
    except Exception as exc:  # noqa: BLE001 — surface network errors cleanly
        return {"url": url, "ok": False, "error": str(exc)}


def register_network_tools() -> None:
    REGISTRY.register(ToolSpec(
        name="net.connectivity",
        description="TCP connectivity check to host:port",
        permissions=["network.http"],
        handler=check_connectivity,
        schema={"host": "str", "port": "int", "timeout": "float"},
    ))
    REGISTRY.register(ToolSpec(
        name="net.website",
        description="HTTP(S) status check for a URL",
        permissions=["network.http"],
        handler=website_status,
        schema={"url": "str", "timeout": "float"},
    ))

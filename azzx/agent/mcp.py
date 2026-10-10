"""Agent tool exposure for AZZX's existing MCP client (v10.5).

The MCP protocol machinery (``_mcp_open`` / ``_mcp_request`` with modern +
legacy protocol eras) already lives in ``azzx_cli.py`` and is reachable via
``azzx mcp list|add|remove|test|tools|call``. This module only registers the
``mcp.call`` tool so the *agent* can use configured MCP servers through the
permission-enforcing registry (capability ``mcp.execute``).

The azzx_cli import is lazy: handlers run long after CLI startup, so there
is no import cycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _agent_mcp_call(server: str, tool: str, args: dict[str, Any] | None = None) -> Any:
    import azzx_cli

    root = Path.cwd()
    servers = azzx_cli.load_mcp_servers(root)
    if server not in servers:
        from azzx.core import AzzxError
        raise AzzxError(f"MCP server not configured: {server} (see `azzx mcp add`)")
    proc, era = azzx_cli._mcp_open(root, servers[server])
    try:
        result = azzx_cli._mcp_request(proc, era, 2, "tools/call",
                                       {"name": tool, "arguments": args or {}})
    finally:
        azzx_cli._close_mcp_process(proc)
    # Normalize to text when possible.
    content = result.get("content")
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        if texts:
            return {"server": server, "tool": tool, "output": "\n".join(texts)[:8000]}
    return {"server": server, "tool": tool, "result": result}


def register_mcp_tools() -> None:
    from azzx.core import REGISTRY, ToolSpec

    REGISTRY.register(ToolSpec(
        name="mcp.call",
        description=("Call a tool on a configured MCP server "
                     "(`azzx mcp add` first). Server process is spawned per call."),
        permissions=["mcp.execute"],
        handler=_agent_mcp_call,
        schema={"server": "str (required)", "tool": "str (required)", "args": "dict"},
    ))

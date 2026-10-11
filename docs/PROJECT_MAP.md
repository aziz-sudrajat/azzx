# AZZX Project Map (v10.6.7)

> Lightweight architecture map for the autonomous improvement loop.
> Updated: 2026-10-11. See IMPROVEMENT_ROADMAP.md for backlog.

## Entry points

| File | Role |
|---|---|
| `azzx_cli.py` (6.044 lines) | Main CLI: argparse (93 commands), dispatch, `run_edit_task`, `run_review`, `run_debug`, `run_tests`, `run_ask` |
| `azzx/cli_v10.py` (1.544 lines) | v10.5+ commands: chat, GUI, browse, webauto, audit, compress, `do`, `help` |
| `azzx/core.py` | `AzzxError`, `REGISTRY`, `ToolSpec`, config paths |
| `install.sh` / `uninstall.sh` | Installer (Termux-friendly, `~/.local/share`) |

## Agent modules (`azzx/agent/`, 32 files)

| Module | Purpose |
|---|---|
| `orchestrator.py` | Tool registry, `run_tool_call` (permissions + audit), memory store |
| `providers.py` | AI providers: OpenAI-compat, Anthropic, Cohere, Ollama (local), custom |
| `intent.py` | **`azzx do` router**: offline ID/EN keyword → command (v10.6.6) |
| `autochain.py` | Auto recall-before + learn-after for fix/review/implement (v10.6.5) |
| `attachments.py` | `@file` mentions + `/add` for chat/GUI (v10.6.4) |
| `auditor.py` | Rule-based per-run audit: `denied`/`error`/`ok`, judge mode |
| `compressor.py` | Token compressor: signatures/extractive/head_tail/summarize |
| `webreader.py` | Read-only web: fetch/links/search, SSRF guard |
| `webforms.py` | **Write mode**: form parsing, submit, sessions (v10.6.5) |
| `webagent.py` | `webauto`: goal-driven browse loop (read/write) |
| `autonomy.py` | `azzx auto`: plan→approve→execute→learn, deny-first |
| `sandbox.py` | `exec run`: local/docker, Android RLIMIT_AS fix |
| `memory.py` / `learning.py` | Persistent memory, staged learnings (trust-gated) |
| `companion.py` | Chat persona, `/remember` |
| `connectors.py` | GitHub PAT, Email IMAP/SMTP |
| `planning.py` | `generate_plan`, todo tools |
| `checkpoints.py` | Honest overlay checkpoints |
| `scheduler.py` / `cronutil.py` | `azzx schedule`, cron |
| `skills.py` / `mcp.py` | Skills (git URL install), MCP client |
| `multi_agent.py` | Team runs, roles |
| `session.py` | Session journal |
| `tracer.py` / `reasoning.py` / `streaming.py` | Infra: tracing, reasoning traces, streaming |
| `message_bus.py` | Inter-agent messaging (used by multi_agent, orchestrator) |
| `tasks.py` | Background task queue |
| `vision.py` / `embeddings.py` | Vision input, embeddings |

## Key design decisions (do not regress)

- **Deny-first absolute**: `deny` permission cannot be bypassed by `-y`.
- **Trust gate**: learnings are staged, never auto-approved.
- **Kentang-first**: only `httpx` + `rich` required; lazy imports for startup speed.
- **No JS browser**: HTTP-level only (honest limit, documented).
- **Local LLM**: Ollama preset (keyless) + custom OpenAI-compat endpoints.
- **93 commands work; `--help` shows 28 curated** (v10.6.6 consolidation).
- **Audit**: `PermissionDenied` → `denied` (not `error`).

# AZZX v10.6.3 — Your Personal AI Agent

**One unified AI agent for your terminal.** Chat with it like a friend, let it plan
and execute tasks autonomously, and run it on anything from a flagship PC to a
low-end "kentang" laptop or an Android phone with Termux.

```bash
bash install.sh                 # installs to ~/.local/share, adds the `azzx` command
azzx setup                      # tell AZZX your name (stored locally, privately)
azzx chat                       # talk to your companion
azzx auto "organize my downloads folder"   # autonomous: plan → approve → execute → learn
```

[![Version](https://img.shields.io/badge/version-10.6.3-cyan)](./VERSION)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](.)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Linux-green)](.)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

> 🇮🇩 Baca versi Bahasa Indonesia di [README_ID.md](./README_ID.md).

---

## Table of contents

1. [What is AZZX?](#1-what-is-azzx)
2. [Install (2 minutes, works on low-end machines)](#2-install)
3. [Quick start](#3-quick-start)
4. [Command reference](#4-command-reference)
   - [Companion & chat](#companion--chat)
   - [Autonomous agent](#autonomous-agent)
   - [Planning & learning](#planning--learning)
   - [Memory](#memory)
   - [Sandboxed execution](#sandboxed-execution)
   - [Scheduling](#scheduling)
   - [Skills & MCP](#skills--mcp)
   - [Sessions & checkpoints](#sessions--checkpoints)
   - [Background queue](#background-queue)
   - [Coding & engineering](#coding--engineering)
   - [System toolkit](#system-toolkit)
   - [Android device](#android-device)
   - [Safety & permissions](#safety--permissions)
   - [Utilities](#utilities)
5. [How it works (architecture)](#5-how-it-works)
6. [Configuration](#6-configuration)
7. [FAQ](#7-faq)

---

## 1. What is AZZX?

AZZX is a **terminal-first personal AI agent**. Unlike a chatbot, it can *act*:
run commands in a sandbox, write a plan and execute it step by step, remember
what you teach it, distill new skills from experience, and message you from
your phone via Telegram.

**Design principles**

- **One agent, no modes.** Everything is a native command of the same agent.
- **Lightweight.** Only 2 Python dependencies (`httpx`, `rich`). The smarts come
  from your AI provider (API), so even a potato laptop runs a first-class agent.
- **Deny-first safety.** An explicit `deny` permission cannot be bypassed by
  `-y`, queues, workflows, or autonomous runs. Ever.
- **Trust-gated skills.** New skills install *untrusted and disabled*; you
  review, then `trust` + `enable`.
- **Private by default.** Memory, profile and API keys stay on your machine.

---

## 2. Install

**Requirements:** Python 3.10+, ~50 MB disk, ~100 MB RAM free. That's it.

```bash
# Recommended — installer script (venv + deps + `azzx` launcher on PATH)
bash install.sh
# Termux (Android)
pkg install python git && bash install.sh
# Manual (tanpa installer): butuh Python 3.10+
python3 -m venv .venv && . .venv/bin/activate
pip install httpx rich
python3 azzx_cli.py --version
```

Check the installation:

```bash
azzx doctor     # Python, deps, disk, memory, providers — all green?
azzx --version
```

Configure an AI provider (OpenAI-compatible, Anthropic, Cohere, or local Ollama):

```bash
azzx ai         # interactive provider setup (keys go to the secure vault)
```

> No provider yet? Most commands that don't need AI (`exec`, `checkpoint`,
> `schedule`, `doctor`, …) work offline.

---

## 3. Quick start

```bash
azzx setup
# → "Namamu siapa?" — AZZX learns your name, language, timezone.
#   Stored in ~/.config/azzx/profile.json (chmod 600, never leaves your machine).

azzx chat
# → interactive companion with slash commands:
#   /plan <goal>   /auto <goal>   /remember <fact>   /learn   /memory <q>   /quit

azzx auto "cek kesehatan sistem lalu ringkas dalam Bahasa Indonesia"
# → generates a plan, asks approval, executes via real tools,
#   checkpoints before risky steps, then distills learnings for your review.

azzx learn list
# → review what the agent learned; approve what deserves to become memory/skill.

azzx gui
# → friendly ChatGPT-like web UI at http://127.0.0.1:8766 (chat, streaming, quick actions)
```

---

## 4. Command reference

Every command below shows its purpose and one example. Run `azzx <command> --help`
for full flags.

### Companion & chat

| Command | What it does | Example |
|---|---|---|
| `azzx setup` | First-run setup: your name, language, notes (local only) | `azzx setup` |
| `azzx chat` | Interactive companion REPL with streaming + slash commands | `azzx chat` |
| `azzx gui` | Friendly ChatGPT-like web UI (streaming chat, quick actions) | `azzx gui --open` |
| `azzx gateway telegram` | Run AZZX as a Telegram bot on your phone | `azzx gateway telegram --token $TG --allow-from 123456` |

`azzx chat` slash commands: `/plan`, `/auto`, `/agent`, `/learn`,
`/remember <fact>`, `/memory <q>`, `/skills`, `/trace`, `/clear`, `/quit`.

### Autonomous agent

| Command | What it does | Example |
|---|---|---|
| `azzx auto "<goal>"` | **Plan → approve → execute → learn**, fully autonomous | `azzx auto "backup project ke /tmp/bak" -y` |
| `azzx agent "<task>"` | Multi-agent pipeline (planner → researcher → coder → reviewer → tester → security) | `azzx agent "refactor auth.py"` |
| `azzx agent --roles` | List the 6 roles and their tool allowlists | `azzx agent --roles` |

`auto` flags: `-y` (skip approval — use carefully), `--max-steps N` (default 25),
`--workdir PATH`. High-risk steps are checkpointed automatically.

### Planning & learning

| Command | What it does | Example |
|---|---|---|
| `azzx plan "<goal>"` | Generate an explicit tool-grounded plan (saved to `.azzx/plans/`) | `azzx plan "deploy ke VPS"` |
| `azzx plan "<goal>" --execute` | Show the plan, then execute it | `azzx plan "bersihkan /tmp" --execute -y` |
| `azzx learn list` | Show staged learnings (memories + skill drafts) | `azzx learn list` |
| `azzx learn approve memory 0` | Approve a staged memory into long-term memory | `azzx learn approve memory 0` |
| `azzx learn approve skill 0` | Install a drafted skill (untrusted+disabled; review first!) | `azzx learn approve skill 0` |
| `azzx learn discard <kind> <i>` | Discard a staged proposal | `azzx learn discard skill 1` |

The agent also tracks itself with `todo.add` / `todo.list` / `todo.done` /
`todo.clear` tools during autonomous runs.

### Memory

| Command | What it does | Example |
|---|---|---|
| `azzx recall search "<q>"` | Hybrid keyword+semantic search over long-term memory | `azzx recall search "preferensi deploy"` |
| `azzx recall add "<fact>"` | Store a memory manually | `azzx recall add "VPS di 192.0.2.10"` |
| `azzx recall list` | List memories | `azzx recall list --limit 20` |
| `azzx recall delete <id>` | Delete a memory | `azzx recall delete 42` |
| `azzx recall stats` | Memory statistics | `azzx recall stats` |
| `azzx remember "<note>"` | Append to *project* memory (`.azzx/memory.md`) | `azzx remember "pakai uv, bukan pip"` |

Secrets (API keys, tokens, private keys) are **refused** at the memory gate.

### Audit & compress

| Command | What it does | Example |
|---|---|---|
| `azzx audit stats` | Success rates, denials, worst tools across all runs | `azzx audit stats` |
| `azzx audit list` | Recent audited tool calls (`--run <id>` to filter) | `azzx audit list --limit 20` |
| `azzx audit report --run <id>` | Rule-based correctness report (score 0-100 + findings) | `azzx audit report --run run-abc123` |
| `azzx audit report --run <id> --judge` | Ask the AI provider to grade the run | `azzx audit report --run run-abc123 --judge` |
| `azzx compress <file>` | Shrink a big file before it enters AI context | `azzx compress big.py --budget 8000` |

Compressor strategies: `signatures` (Python AST — 70-90% savings), `extractive`
(query-focused), `head_tail`, `summarize` (LLM). `azzx ask` uses it
automatically when files exceed the context budget.

### Sandboxed execution

| Command | What it does | Example |
|---|---|---|
| `azzx exec run -- <cmd>` | Run a command in a sandbox (cwd jail, timeout, output cap, secret-scrubbed env) | `azzx exec run -- python3 script.py` |
| `azzx exec run --backend docker -- <cmd>` | Stronger isolation: Docker, `--network none`, 512 MB | `azzx exec run --backend docker -- ./build.sh` |
| `azzx exec backends` | List available backends (`local`, `docker` if installed) | `azzx exec backends` |

The agent uses the `sandbox.exec` tool for the same purpose. Honest limits:
`local` cannot block network access — use `docker` when that matters.

### Scheduling

| Command | What it does | Example |
|---|---|---|
| `azzx schedule add <tool>` | Run a registered tool every N seconds | `azzx schedule add sys.health --every 3600` |
| `azzx schedule add <tool> --cron "<expr>"` | Cron syntax (no new dependencies) | `azzx schedule add sys.health --cron "*/15 9-17 * * 1-5"` |
| `azzx schedule list` | List jobs | `azzx schedule list` |
| `azzx schedule run-due` | Execute due jobs once (call from cron/systemd) | `*/5 * * * * azzx schedule run-due` |
| `azzx schedule remove <id>` | Remove a job | `azzx schedule remove a1b2c3` |

### Skills & MCP

| Command | What it does | Example |
|---|---|---|
| `azzx skills list` | List installed skills | `azzx skills list` |
| `azzx skills install <dir\|url>` | Install from a directory **or git URL** (untrusted+disabled) | `azzx skills install https://github.com/…/my-skill` |
| `azzx skills trust <id>` | Mark a skill trusted after reviewing its code | `azzx skills trust my-skill` |
| `azzx skills enable <id>` | Enable a trusted skill (registers `skill.<id>` tool) | `azzx skills enable my-skill` |
| `azzx skills invoke <id>` | Invoke a skill directly | `azzx skills invoke my-skill --args '{}'` |
| `azzx skills find "<q>"` | Search skills | `azzx skills find "pdf"` |
| `azzx mcp list` | List configured MCP servers | `azzx mcp list` |
| `azzx mcp add <name> <cmd>` | Add an MCP server (stdio) | `azzx mcp add files npx -y @modelcontextprotocol/server-filesystem /tmp` |
| `azzx mcp tools <name>` | List a server's tools | `azzx mcp tools files` |
| `azzx mcp call <name> <tool>` | Call an MCP tool | `azzx mcp call files read_file '{"path":"/tmp/a.txt"}'` |

The agent can also call MCP tools itself via the `mcp.call` registry tool
(permission `mcp.execute`).

### Sessions & checkpoints

| Command | What it does | Example |
|---|---|---|
| `azzx session start <project> [title]` | Start a session journal | `azzx session start webku "refactor auth"` |
| `azzx session log <id> <msg>` | Log an event | `azzx session log sess_abc "selesai migrasi"` |
| `azzx session resume <id>` | Restore a session's context | `azzx session resume sess_abc` |
| `azzx session search "<q>"` | Search titles, summaries and events | `azzx session search "migrasi"` |
| `azzx session stale` | Find interrupted sessions | `azzx session stale --hours 48` |
| `azzx checkpoint create` | Snapshot the working dir (tarball, no git needed) | `azzx checkpoint create --label "sebelum refactor"` |
| `azzx checkpoint rollback <id>` | Restore a snapshot | `azzx checkpoint rollback 20261010-120000-1234` |
| `azzx checkpoint list` | List checkpoints | `azzx checkpoint list` |
| `azzx trace` | Show the recent execution timeline (debugging) | `azzx trace --limit 30` |

### Background queue

| Command | What it does | Example |
|---|---|---|
| `azzx queue add <tool>` | Enqueue a tool call for background execution | `azzx queue add sys.health --args '{}'` |
| `azzx queue list` | List queued/running/done/error jobs | `azzx queue list` |
| `azzx queue cancel <id>` | Cancel a job | `azzx queue cancel abc123` |
| `azzx queue resume <id>` | Resume an interrupted job | `azzx queue resume abc123` |

### Coding & engineering

| Command | What it does | Example |
|---|---|---|
| `azzx ask "<q>"` | Ask the AI about your project | `azzx ask "di mana bug login?"` |
| `azzx fix "<desc>"` | AI-driven code fix | `azzx fix "null pointer di handler"` |
| `azzx add "<desc>"` | Implement a feature | `azzx add "tambah retry ke client"` |
| `azzx review` | Static code review | `azzx review --focus security` |
| `azzx test` | Run tests | `azzx test` |
| `azzx debug <cmd>` | Run + diagnose a failing command | `azzx debug "python3 main.py"` |
| `azzx autodebug <cmd>` | Loop: run → fix → run | `azzx autodebug "pytest -x"` |
| `azzx implement "<desc>"` | Larger implementation task | `azzx implement "tambah caching"` |
| `azzx create "<desc>"` | Scaffold a new project | `azzx create "REST API dengan FastAPI"` |
| `azzx architect` | Architecture analysis | `azzx architect` |
| `azzx factory "<spec>"` | Spec → roadmap → sandbox team → regression → package | `azzx factory "todo app"` |
| `azzx sandbox "<task>"` | Develop in an isolated copy, validate, then merge | `azzx sandbox "tambah fitur X"` |
| `azzx develop "<goal>"` | Guided development session | `azzx develop "selesaikan issue #12"` |
| `azzx team "<goal>"` | Multi-role team run | `azzx team "audit keamanan"` |

### Web browsing (autonomous)

| Command | What it does | Example |
|---|---|---|
| `azzx webauto "<task>"` | **Goal-driven browsing that solves by itself:** searches, opens pages, follows links until it can answer (read-only) | `azzx webauto "berapa harga kopi robusta hari ini"` |
| `azzx browse search "<q>"` | Web search (DuckDuckGo) | `azzx browse search "harga kopi"` |
| `azzx browse fetch <url>` | Fetch a page as readable text (no JS rendering) | `azzx browse fetch https://example.com` |
| `azzx browse links <url>` | List a page's outbound links | `azzx browse links https://example.com` |

`webauto` flags: `--start-url URL` (skip search), `--max-steps N` (default 12).
The agent only follows links actually present on the page — hallucinated URLs
are blocked. Agent tools: `web.search`, `web.fetch`, `web.links` (permission
`web.read`). Honest limit: text web only, no JavaScript — for JS-heavy sites
use Playwright separately (deliberately not bundled).

### Connectors

| Command | What it does | Example |
|---|---|---|
| `azzx connector setup github` | Connect GitHub via personal access token (vault-stored) | `azzx connector setup github` |
| `azzx connector setup email` | Connect email via IMAP/SMTP (app password) | `azzx connector setup email` |
| `azzx connector list` | List configured connectors | `azzx connector list` |

Agent tools: `github.repos`, `github.list_issues`, `github.create_issue`,
`email.inbox`, `email.send` (permissions `connector.github` / `connector.email`).
Google Drive needs a Google Cloud OAuth2 app — deferred, documented in code.

### System toolkit

| Command | What it does | Example |
|---|---|---|
| `azzx install <app>` | Universal app installer (200+ apps, distro-aware) | `azzx install ffmpeg` / `azzx install --dry-run ffmpeg` |
| `azzx toolkit sys` | System info, health, processes, services | `azzx toolkit sys --action health` |
| `azzx toolkit net` | Network checks | `azzx toolkit net --action connectivity` |
| `azzx toolkit fs` | Filesystem operations | `azzx toolkit fs --action list --path .` |
| `azzx toolkit media` | Media utilities | `azzx toolkit media --action info --file a.mp3` |
| `azzx tools list` | List *every* registered tool | `azzx tools list` |
| `azzx tools run <tool>` | Run one registered tool directly | `azzx tools run sys.health` |
| `azzx nl "<text>"` | Natural language → tool call | `azzx nl "cek kesehatan disk"` |
| `azzx workflow …` | Deterministic multi-step workflows | `azzx workflow list` |
| `azzx dashboard` | Web dashboard | `azzx dashboard --port 8080` |

### Android device

| Command | What it does | Example |
|---|---|---|
| `azzx mirror start` | Mirror Android screen via scrcpy | `azzx mirror start --serial ABC123` |
| `azzx mirror status` | Mirror status | `azzx mirror status` |
| `azzx mirror stop` | Stop mirroring | `azzx mirror stop` |

### Safety & permissions

| Command | What it does | Example |
|---|---|---|
| `azzx permissions list` | Show the permission policy table | `azzx permissions list` |
| `azzx permissions set <cap> <allow\|prompt\|deny>` | Change a capability policy | `azzx permissions set network.http deny` |

Policies: `allow` (no prompt), `prompt` (ask), `deny` (**absolute** — no
`-y`, queue, workflow, or autonomous run can bypass it).

### Utilities

| Command | What it does | Example |
|---|---|---|
| `azzx doctor` | Health check (Python, tools, providers, disk, memory) | `azzx doctor` |
| `azzx ai` | Configure AI providers | `azzx ai` |
| `azzx config` | Show configuration | `azzx config` |
| `azzx update` | Self-update | `azzx update` |
| `azzx --version` | Version | `azzx --version` |

> Legacy shim: `azzx hermes` prints a migration guide (exit 2). There is no
> separate Hermes mode — everything is one unified agent.

---

## 5. How it works

```text
You (chat / auto / Telegram / CLI)
        ↓
Companion layer (persona, profile, long-term memory)
        ↓
Planner  →  explicit plan (`.azzx/plans/`)  →  your approval
        ↓
Autonomous runner → tool calls ONLY through the registry
        ↓                    ↓ deny-first permission gate
Tool Registry  →  sandbox.exec · sys.* · mcp.call · skill.* · todo.* …
        ↓
Checkpoint before risky steps · trace everything · distill learnings
```

**Autonomy loop:** `plan → approve → execute → checkpoint → learn`.
Learnings are *staged*, never applied silently — you review with `azzx learn`.

---

## 6. Configuration

- `~/.config/azzx/` — `config.json`, providers, `profile.json`, `mcp.json`, vault
- `~/.local/share/azzx/` — memory DB, sessions, checkpoints, learnings, queue
- `.azzx/` (per project) — plans, project memory, local skills

API keys live in the OS-appropriate secure vault, never in chat or files.

---

## 7. FAQ

**Will it run on my old laptop?**
Yes. AZZX needs Python 3.10+ and ~100 MB RAM. Intelligence comes from the AI
provider over API — your machine just runs the harness. Run `azzx doctor` to verify.

**Does it work offline?**
Non-AI commands (`exec`, `checkpoint`, `schedule`, `doctor`, …) work offline.
Provider calls need internet (or a local Ollama).

**Is it safe to let it run autonomously?**
`deny` is absolute and cannot be bypassed. Plans are shown before execution
(unless you pass `-y`). High-risk steps are checkpointed; `rollback` restores.

**How is this different from Hermes (Nous Research)?**
Honest answer in [`docs/HERMES_FEATURE_GAP_ID.md`](./docs/HERMES_FEATURE_GAP_ID.md):
Hermes is the bigger *platform* (60+ tools, 30+ messaging apps, voice, desktop).
AZZX wins on the Linux/Termux toolkit, universal installer, Android mirroring,
deterministic workflows — and now matches Hermes on the core *agent* loop:
plan, sandbox, checkpoints, learning, autonomy.

**Can AZZX drive a real browser like Playwright?**
`azzx browse` is a lightweight reader (no JS). A full Playwright bundle would
cost ~300 MB disk + lots of RAM and break the "runs on a potato" promise, so
it's deliberately excluded. If you need it, install Playwright yourself and
drive it through `azzx exec` / `sandbox.exec`.

**Which apps can it connect to?**
GitHub and email today (`azzx connector setup`). Google Drive needs a Google
Cloud OAuth2 app — that's manual console work Google requires; not yet built.

**Where do I report bugs?**
Open an issue at `https://github.com/aziz-sudrajat/azzx`.

---

*AZZX v10.6.3 — "Connected". MIT License.*

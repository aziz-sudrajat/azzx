# AZZATSSINS LITE AGENT (AZZX) v10.0.0

**Terminal-first AI engineering agent** for Termux and Linux.

AZZX works from any directory: AI coding, software factory, universal app installer, system toolkit, safe workflows, plugins, and Android screen mirroring.

```bash
cd ~/my-project
azzx
```

```text
User / Natural language
        ↓
AI Orchestrator (multi-provider coding agent)
        ↓  structured tool calls only
Tool Registry (deterministic executors)
        ↓  permission + validation
OS / workspace / Android device
```

[![Version](https://img.shields.io/badge/version-10.0.0-cyan)](./VERSION)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](.)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Linux-green)](.)

---

## Table of contents

1. [What is AZZX?](#1-what-is-azzx)
2. [Version evolution (v1 → v10)](#2-version-evolution-v1--v10)
3. [Installation](#3-installation)
4. [Upgrade from v6](#4-upgrade-from-v6)
5. [First run & AI configuration](#5-first-run--ai-configuration)
6. [Command structure](#6-command-structure)
7. [v1 — AI CLI foundation](#7-v1--ai-cli-foundation)
8. [v2 — AI coding agent](#8-v2--ai-coding-agent)
9. [v3 — Software engineer agent](#9-v3--software-engineer-agent)
10. [v4 — Software factory](#10-v4--software-factory)
11. [v5 — Advanced engineering agent](#11-v5--advanced-engineering-agent)
12. [v6 — Universal Application Installer](#12-v6--universal-application-installer)
13. [v7 — Universal Toolkit](#13-v7--universal-toolkit)
14. [v8 — Automation & device (mirror)](#14-v8--automation--device-mirror)
15. [v9 — Plugins & extensibility](#15-v9--plugins--extensibility)
16. [v10 — Universal Agent Layer](#16-v10--universal-agent-layer)
17. [AI providers](#17-ai-providers)
18. [Permissions & safety](#18-permissions--safety)
19. [Recommended workflows](#19-recommended-workflows)
20. [Troubleshooting](#20-troubleshooting)
21. [Quick command reference](#21-quick-command-reference)
22. [Project layout](#22-project-layout)
23. [Limitations](#23-limitations)
24. [License / contributing](#24-license--contributing)

---

## 1. What is AZZX?

AZZX combines:

| Area | Capabilities |
|------|----------------|
| **AI** | Chat, coding, review, debug, multi-agent roles, multi-provider fallback |
| **Engineering** | Map, tests, security, Git, checkpoints, sandbox, factory, release |
| **Apps** | Install / update / repair / uninstall via native package managers |
| **Toolkit** | Files, hash, archive, JSON, FFmpeg, network, processes, health |
| **Automation** | Workflows limited to registered tools only |
| **Device** | ADB detect, Termux API detect, scrcpy screen mirror |
| **Extensibility** | Plugins (`manifest.json`), skills, MCP |

Main executable:

```bash
azzx
```

**Do not** run the whole app as root (`sudo azzx`). Privileged package ops use `sudo`/`doas` only when needed for that step.

---

## 2. Version evolution (v1 → v10)

Versions are **cumulative** — later releases keep earlier capabilities.

```text
v1  AI CLI foundation
 ↓
v2  AI Coding Agent
 ↓
v3  Software Engineer Agent
 ↓
v4  Software Factory
 ↓
v5  Advanced Engineering (sandbox, permissions, MCP)
 ↓
v6  Universal Application Installer
 ↓
v7  Universal Toolkit (files, system, network, media)
 ↓
v8  Automation & Device (workflows, ADB, scrcpy mirror)
 ↓
v9  Extensibility (manifest plugins, tool registry hooks)
 ↓
v10 Universal Agent Layer (AI orchestrator + deterministic tools)
```

| Version | Main focus |
|---------|------------|
| v1 | AI CLI, chat, provider setup |
| v2 | Read/edit project, fix/add/implement |
| v3 | Map, review, test, debug, security, Git |
| v4 | Spec, roadmap, factory, CI, db |
| v5 | Sandbox, permissions, MCP, skills, dashboard |
| v6 | `install` / distro package managers / Application Center |
| v7 | `toolkit` / `tools` / file-system & health utilities |
| v8 | `workflow` / `mirror` (scrcpy) / ADB & Termux detect |
| v9 | Plugin `manifest.json` + install/load |
| v10 | Central tool registry; NL shortcuts; modular `azzx/` package |

---

## 3. Installation

### Requirements

- Python **3.10+**
- Linux or **Termux**
- Optional: `git`, `ffmpeg`, `scrcpy`, `adb`, `cryptography`

### Install from zip

```bash
unzip AZZATSSINS_LITE_AGENT_v10.0.zip
cd AZZATSSINS_LITE_AGENT_v10.0
chmod +x *.sh
./install.sh --check
./install.sh
```

```bash
azzx --version
# AZZATSSINS LITE AGENT 10.0.0
```

### Installer flags

| Flag | Meaning |
|------|---------|
| `--check` | Detect OS / package manager only |
| `--no-system-deps` | Skip apt/pacman/pkg system packages |
| `--no-crypto` | Skip optional encrypted vault |

**Important:** the installer must copy the `azzx/` Python package next to `azzx_cli.py`. If `azzx tools list` fails with `No module named 'azzx'`, re-run `./install.sh` from a complete extract (folder `azzx/` must exist).

### Uninstall

```bash
./uninstall.sh          # keep config & API keys
./uninstall.sh --purge  # also delete config
```

---

## 4. Upgrade from v6

Config and API keys are kept by default.

```bash
cd AZZATSSINS_LITE_AGENT_v10.0
./install.sh
# or: ./update-local.sh
azzx --version
```

| Path | On upgrade |
|------|------------|
| `~/.local/share/azzatssins-lite-agent/` | App files replaced (includes `azzx/` package) |
| `~/.config/azzatssins-lite-agent/` | **Preserved** |
| Launcher `azzx` | Updated |

---

## 5. First run & AI configuration

```bash
azzx
```

On first run, configure:

- AI provider
- API key
- model
- endpoint (if needed)
- fallback providers

Reopen AI settings anytime:

```bash
azzx ai
```

Config lives under:

```text
~/.config/azzatssins-lite-agent/
```

**Never** commit API keys to Git or hard-code them in source.

---

## 6. Command structure

```bash
azzx <command> [arguments] [options]
azzx --path /path/to/project <command>
azzx --ai <provider_id> <command>
azzx --version
azzx --help
```

| Option | Meaning |
|--------|---------|
| `--path` / `-p` | Workspace directory (default: current dir) |
| `--ai` | Force a configured provider for this run |
| `--version` | Print version |

Interactive mode:

```bash
azzx
```

Useful interactive entry points (when offered by the UI):

```text
/apps     Application Center
/ai       Provider settings
```

Prefer normal CLI commands in scripts.

---

## 7. v1 — AI CLI foundation

### Features

- AI chat from the terminal  
- First-run API key setup  
- Provider / model configuration  
- Persistent config  
- Run from any directory  

### Commands

#### `azzx` — interactive shell

```bash
azzx
```

Opens the home UI: status, workspace, menus for code and system tools.

#### `azzx ask "…"` — ask the AI about the workspace or a topic

```bash
azzx ask "Explain how this project is structured"
azzx ask "What does main.py do?"
```

**How it works:** loads limited project context (respecting max files/chars), sends your question to the configured provider, prints the answer. Does not necessarily modify files.

#### `azzx ai` — configure providers and keys

```bash
azzx ai
```

Add provider, paste API key, pick model, set priority / fallback. Keys stored under config (encrypted if `cryptography` is available).

---

## 8. v2 — AI coding agent

### Features

- Read project files with safety limits  
- Create / edit files  
- Fix bugs, add features, implement specs  
- Diff / backup / undo awareness  
- Multi-provider routing  

### Commands

#### `azzx fix "…"` — fix a bug or broken behavior

```bash
azzx fix "Fix the login error when password is empty"
azzx fix "Repair crash on file upload"
```

**How to use:** describe the bug clearly. AZZX proposes patches; in safe modes you confirm. Check `git diff` / `azzx diff` after.

#### `azzx add "…"` — add a feature

```bash
azzx add "Add dark mode toggle"
azzx add "Add health check endpoint"
```

#### `azzx implement "…"` — implement a larger description

```bash
azzx implement "Add JWT authentication with refresh tokens"
```

#### `azzx create "…"` — scaffold a new project or module

```bash
azzx create "Create a FastAPI hello-world service"
azzx create "Python CLI for CSV reports" --name csv-tools
```

`--name` creates work inside a new child directory when supported.

#### `azzx agent "…"` — general coding agent instruction

```bash
azzx agent "Analyze the project and fix obvious errors"
```

#### `azzx edit "…"` — edit existing code toward a goal

```bash
azzx edit "Refactor settings into a config module"
```

#### `azzx diff` / `azzx undo`

```bash
azzx diff          # show recent change summary / backup diff
azzx undo          # restore last backup (confirm when asked)
azzx undo --yes    # non-interactive when policy allows
```

**Tip:** use Git for real history; AZZX backups are a safety net, not a replacement for commits.

---

## 9. v3 — Software engineer agent

### Features

- Repository map & symbols  
- Debug loops  
- Tests, review, security scan  
- Dependencies, Git checkpoints  
- Project memory  

### Commands

#### `azzx map` — repository map

```bash
azzx map
```

Indexes structure / symbols to help later AI and navigation commands.

#### `azzx symbol NAME` / `azzx refs NAME`

```bash
azzx symbol UserService
azzx refs login
```

Find definitions or references by name.

#### `azzx impact TARGET` — impact analysis

```bash
azzx impact src/auth.py
azzx impact UserModel --depth 2
```

Shows files/symbols likely affected by a change.

#### `azzx debug` / `azzx autodebug`

```bash
azzx debug python main.py
azzx debug "The API crashes when uploading a file"
azzx autodebug python -m pytest
```

**debug:** run a command or describe a failure; AI helps diagnose.  
**autodebug:** repeatedly run/fix within iteration limits.

#### `azzx review` / `azzx review-range`

```bash
azzx review
azzx review security
azzx review-range HEAD~3..HEAD
```

AI review of the workspace or a Git revision range (correctness, quality, security, maintainability).

#### `azzx test` / `azzx tests`

```bash
azzx test
azzx test pytest -q
azzx tests generate
azzx tests run
```

Detect or run project tests; optionally generate focused tests.

#### `azzx security`

```bash
azzx security
azzx security --external   # also run installed external scanners if enabled
```

Static patterns (e.g. risky `shell=True`, secrets patterns) plus optional external tools.

#### `azzx deps`

```bash
azzx deps
azzx deps --install      # install requirements.txt after confirmation
```

#### `azzx remember` / `azzx memory` / `azzx index`

```bash
azzx remember "We use PostgreSQL in production, SQLite in tests"
azzx memory
azzx index
```

Store project decisions; show memory; refresh index.

#### `azzx architect`

```bash
azzx architect
```

Generate or refresh architecture notes from the codebase.

#### `azzx git` / checkpoints

```bash
azzx git status
# checkpoint helpers are used automatically before many edits when enabled
```

#### `azzx issue`

```bash
azzx issue list
azzx issue create "Login fails on empty password"
azzx issue show 1
azzx issue solve 1
```

Lightweight issue lifecycle tied to the project.

#### `azzx benchmark` / `azzx profile`

```bash
azzx benchmark python main.py
azzx profile python main.py
```

#### `azzx history` / `azzx scan` / `azzx doctor`

```bash
azzx history
azzx scan
azzx doctor
azzx doctor --online
```

Change history, workspace scan, environment health.

---

## 10. v4 — Software factory

### Features

- Spec & roadmap  
- Factory pipeline  
- CI scaffold  
- SQLite tools  
- Build / release helpers  

### Commands

#### `azzx spec`

```bash
azzx spec init
azzx spec generate "Task management API for small teams"
azzx spec show
```

Product requirements / architecture specification files in the project.

#### `azzx roadmap`

```bash
azzx roadmap generate "Ship MVP in 4 milestones"
azzx roadmap list
```

Persistent engineering milestones.

#### `azzx factory "…"`

```bash
azzx factory "Create a task management application"
```

High-level pipeline (conceptual):

```text
Requirement → Spec → Roadmap → Sandbox team work
    → Tests / security gates → Regression → Optional package
```

#### `azzx build` / `azzx release` / `azzx release-prepare`

```bash
azzx build
azzx release-prepare 1.0.0
```

Packaging / gated release candidate helpers (exact artifacts depend on project type).

#### `azzx ci`

```bash
azzx ci github
azzx ci gitlab
azzx ci local
```

Scaffold CI config.

#### `azzx db`

```bash
azzx db inspect app.db
azzx db query app.db "SELECT COUNT(*) FROM users"
azzx db explain app.db "SELECT * FROM users WHERE active=1"
```

SQLite inspect / query / explain / migrate-style helpers (write ops respect permissions).

---

## 11. v5 — Advanced engineering agent

### Features

- Sandbox-first develop  
- Permission policies  
- Multi-agent team  
- MCP, skills, plugins (command style)  
- Regression baseline  
- Local dashboard  

### Commands

#### `azzx sandbox` / `azzx develop`

```bash
azzx develop "Add CSV export"
azzx develop "Add CSV export" --direct      # skip sandbox when you intend to
azzx sandbox ...                            # isolated copy, validate, merge
```

**Recommended:** default sandbox path — changes applied in a copy, then merge after validation.

#### `azzx team "…"` / `azzx roles`

```bash
azzx team "Harden the auth module"
azzx roles
```

Specialized roles (planner, architect, coder, security, QA, …) with optional per-role providers.

#### `azzx permissions`

```bash
azzx permissions list
azzx permissions set shell.run ask
azzx permissions set package.install allow
azzx permissions reset
```

Policies: **allow** / **ask** / **deny** per capability (see [Permissions](#18-permissions--safety)).

#### `azzx regression`

```bash
azzx regression capture
azzx regression check
```

Baseline and compare to catch accidental breakages.

#### `azzx mcp`

```bash
azzx mcp list
azzx mcp add NAME COMMAND [ARGS...]
azzx mcp call NAME TOOL [JSON_ARGS]
```

Model Context Protocol clients — **only trusted servers**.

#### `azzx skill`

```bash
azzx skill list
azzx skill create my-skill
azzx skill use my-skill
```

Reusable engineering instructions for the agent.

#### `azzx plugin` (command plugins + v9 manifest plugins)

```bash
# Legacy command plugins (v5)
azzx plugin list
azzx plugin add mycmd 'echo hello'
azzx plugin run mycmd

# Manifest plugins (v9)
azzx plugin install examples/sample-plugin --force
azzx plugin load
```

#### `azzx dashboard`

```bash
azzx dashboard
azzx dashboard --host 127.0.0.1 --port 8765
```

Local **read-only** HTTP dashboard for project status. Keep bound to localhost.

#### `azzx config` / `azzx mode`

```bash
azzx config
azzx mode safe      # or normal / auto — affects autonomy
```

#### `azzx research` / `azzx docs` / `azzx env` / `azzx remote` / `azzx workspace` / `azzx clone`

```bash
azzx research "FastAPI dependency injection"
azzx docs https://docs.python.org/3/library/asyncio.html "How does gather work?"
azzx env
azzx env --tools
azzx clone https://github.com/org/repo.git
```

---

## 12. v6 — Universal Application Installer

### Features

- OS / distro / arch detection  
- Native package managers  
- Plan / dry-run / isolated installs  
- Update, repair, uninstall, history  
- Application Center  

### Installation flow

```text
azzx install APP
  → detect OS / distro / arch / package manager
  → resolve alias / recipe
  → prefer native package
  → show plan / confirm (unless --yes)
  → install via PM
  → verify executable
  → record history
```

AZZX does **not** run arbitrary AI-invented install scripts.

### Supported managers

| Environment | Manager |
|-------------|---------|
| Termux | `pkg` |
| Debian / Ubuntu / Mint / Kali / Pop!_OS | `apt` |
| Arch / Manjaro / EndeavourOS | `pacman` |
| Fedora | `dnf` |
| RHEL-family | `dnf` / `yum` |
| openSUSE | `zypper` |
| Alpine | `apk` |
| Void | `xbps` |
| Gentoo | `emerge` |

### Commands

#### `azzx install APP`

```bash
azzx install ffmpeg
azzx install git
azzx install python
azzx install nodejs
azzx install metasploit
```

#### Plan & dry-run (recommended first)

```bash
azzx install metasploit --plan
azzx install metasploit --dry-run
```

No system changes on `--plan` / `--dry-run`.

#### Other install flags

```bash
azzx install httpie --isolated   # AZZX-managed venv for supported PyPI apps
azzx install APP --yes           # non-interactive (still respects deny policy)
azzx install APP --force
```

#### Lifecycle

```bash
azzx installed              # history tracked by AZZX
azzx update ffmpeg
azzx update --all
azzx repair ffmpeg
azzx uninstall ffmpeg       # safe for tracked native / isolated installs
```

#### Discovery

```bash
azzx app search video
azzx app info ffmpeg
azzx app recipes
azzx app system             # detected OS / manager summary
```

#### Application Center (interactive)

```bash
azzx
# then: /apps
```

Menus for install, search, installed, repair, update, uninstall, recipes.

### Metasploit note

Native package first; official Rapid7 script only on **trusted Linux** environments — **not** auto-forced on Termux.

---

## 13. v7 — Universal Toolkit

Deterministic tools (no AI required). Listed in the central registry.

### `azzx tools`

```bash
azzx tools              # same as list
azzx tools list         # table of all registered tools
azzx tools run sys.health --args '{}'
azzx tools run fs.largest --args '{"path":".","limit":10}'
```

### `azzx toolkit` — shortcuts

| Command | What it does |
|---------|----------------|
| `azzx toolkit health` | Disk, load, basic health |
| `azzx toolkit info` | OS / CPU / memory summary |
| `azzx toolkit processes` | Process list |
| `azzx toolkit git-status` | `git status` porcelain summary |
| `azzx toolkit connectivity` | TCP check (default 1.1.1.1:443) |
| `azzx toolkit website --url URL` | HTTP(S) status |
| `azzx toolkit search --path . --pattern '*.py'` | Find files |
| `azzx toolkit largest --path . --limit 15` | Largest files |
| `azzx toolkit duplicates --path .` | Duplicate files by hash |
| `azzx toolkit hash --path FILE --algorithm sha256` | Checksum |

Examples:

```bash
azzx toolkit health
azzx toolkit largest --path . --limit 20
azzx toolkit hash --path README.md --algorithm sha256
azzx toolkit website --url https://example.com
```

### Archives & JSON (via tools registry)

```bash
azzx tools run archive.create --args '{"src":".","dest":"backup.tar.gz","fmt":"tar.gz"}'
azzx tools run archive.extract --args '{"archive":"backup.tar.gz","dest":"./out"}'
azzx tools run json.validate --args '{"path":"config.json"}'
```

Extract **blocks** `../` path traversal.

### Media (FFmpeg)

```bash
azzx tools run media.probe --args '{"path":"video.mp4"}'
azzx tools run media.convert --args '{"src":"in.mov","dest":"out.mp4","fmt":"mp4"}'
```

Formats whitelisted: `mp4`, `webm`, `mp3`, `wav`, `gif`, `mkv`. Requires `ffmpeg` installed (`azzx install ffmpeg`).

### `azzx nl` — natural language → safe tool only

```bash
azzx nl "show system health"
azzx nl "git status"
azzx nl "largest files"
azzx nl "start screen mirror"
azzx nl "check https://example.com"
```

If there is **no safe mapping**, AZZX refuses (e.g. `rm -rf /`) instead of running shell.

---

## 14. v8 — Automation & device (mirror)

### Workflows (registered tools only)

```bash
# Create
azzx workflow create daily --steps \
  '[{"tool":"sys.health","args":{}},{"tool":"git.status","args":{"path":"."}}]'

azzx workflow list
azzx workflow show daily
azzx workflow run daily
azzx workflow run daily -y    # non-interactive if policy allows / -y force_yes path
azzx workflow delete daily
```

**Rule:** each step `tool` must exist in the registry. Unknown tools → error. No arbitrary shell steps.

### ADB & Termux detection

```bash
azzx mirror detect          # scrcpy + adb + Termux API presence
azzx mirror devices         # adb devices (needs device.adb permission)
```

No free-form `adb shell` from the agent layer.

### Android screen mirror (scrcpy)

Realistic **desktop mirroring** — not a full on-device Samsung DeX OS mode.

**Needs on the computer:** `adb`, `scrcpy`, phone with USB/wireless debugging.

```bash
azzx install scrcpy --plan
azzx install scrcpy

azzx mirror detect
azzx mirror devices
azzx mirror start --dry-run
azzx mirror start --max-size 1280
azzx mirror start --serial DEVICE_ID --fullscreen
azzx mirror status
azzx mirror stop
```

| Option | Meaning |
|--------|---------|
| `--serial` | Device serial |
| `--max-size` | Max dimension (64–4096) |
| `--bit-rate` | Bitrate range limited |
| `--fullscreen` | Fullscreen window |
| `--dry-run` | Print planned argv only |

---

## 15. v9 — Plugins & extensibility

### Manifest plugin layout

```text
my-plugin/
  manifest.json
  plugin.py
```

`manifest.json` example:

```json
{
  "id": "sample-echo",
  "name": "Sample Echo Plugin",
  "version": "1.0.0",
  "description": "Example plugin",
  "tools": ["sample.echo"],
  "permissions": [],
  "entrypoint": "plugin.py",
  "enabled": true
}
```

Banned manifest fields include `shell`, `install_script`, `command` (no arbitrary install hooks).

### Commands

```bash
azzx plugin install examples/sample-plugin --force
azzx plugin list
azzx plugin load
```

Plugins register tools on the shared registry; **execution still uses permission checks**.

---

## 16. v10 — Universal Agent Layer

### Architecture

```text
                    AZZX v10
                       │
          ┌────────────┴────────────┐
          │                         │
     AI ENGINE                 TOOL ENGINE
          │                         │
   Providers, roles,         Registry: tools /
   memory, factory           workflow / device /
                             plugins
```

- **AI** plans and calls structured tools when using NL shortcuts / agent flows.  
- **Tools** perform side effects with validation + permissions.  
- Coding + installer features from v1–v6 remain in the main CLI.

### Modular package

```text
azzx/
  core.py       # registry, permissions, config
  agent/        # orchestrator, NL map
  tools/        # v7 toolkit
  workflow/     # v8 workflows
  device/       # adb, mirror, termux
  plugins/      # v9 loader
  cli_v10.py    # CLI handlers
```

---

## 17. AI providers

Configure with `azzx ai`. Adapters include OpenAI-compatible endpoints, Anthropic, Cohere, and templates such as Gemini, Groq, Qwen (depending on release templates).

Example strategy:

```text
Primary: Groq → fallback Gemini → fallback OpenAI
```

Rate limits (429) and quotas still apply; enable fallback in config.

---

## 18. Permissions & safety

```bash
azzx permissions list
azzx permissions set device.mirror ask
azzx permissions set shell.run deny
```

| Capability | Typical default |
|------------|-----------------|
| `filesystem.read` / `filesystem.write` | allow |
| `shell.run` | ask |
| `package.install` | ask |
| `git.commit` | ask |
| `git.push` | deny |
| `network.http` | allow |
| `device.adb` / `device.mirror` | ask |
| `workflow.run` / `plugin.install` | ask |
| `process.inspect` | allow |
| `archive.write` | ask |
| `release.publish` | deny |

### Safety rules of thumb

1. Prefer `azzx install APP --plan` before new packages.  
2. Prefer sandbox/`develop` for large code changes.  
3. Use Git commits, not only AZZX undo.  
4. Never commit secrets.  
5. Do not `sudo azzx` for normal work.

---

## 19. Recommended workflows

### Everyday coding

```bash
cd ~/project
azzx map
azzx review
azzx test
azzx fix "Fix the broken login flow"
git diff
azzx test
```

### Large feature

```bash
azzx factory "Add CSV export and reporting"
# or
azzx develop "Add CSV export and reporting"
```

### Install software

```bash
azzx app search ffmpeg
azzx install ffmpeg --plan
azzx install ffmpeg
azzx installed
```

### System check + git

```bash
azzx toolkit health
azzx nl "git status"
```

### Phone mirror on desktop

```bash
azzx mirror detect
azzx mirror start --max-size 1280
```

### Scheduled-style automation (manual/cron)

```bash
azzx workflow run daily -y
```

---

## 20. Troubleshooting

### `azzx: command not found`

```bash
which azzx
echo "$PATH"
./install.sh
```

### `ModuleNotFoundError: No module named 'azzx'`

Installer missed the `azzx/` package:

```bash
cd ~/AZZATSSINS_LITE_AGENT_v10.0   # full extract
cp -a azzx ~/.local/share/azzatssins-lite-agent/
# or reinstall:
./install.sh
```

### AI 401 / missing key

```bash
azzx ai
```

### AI 429

Rate limit — wait or switch fallback provider in `azzx ai`.

### Package install needs admin

Use `azzx install APP` (not `sudo azzx`); grant sudo only for the package manager step when prompted.

### Mirror fails

Install `scrcpy` + `adb`, enable USB debugging, check `azzx mirror devices`.

### GitHub push: password not supported / 403

Use a **Personal Access Token** with `repo` scope, or SSH keys — GitHub rejects account passwords for `git push`.

---

## 21. Quick command reference

### Core

```bash
azzx
azzx --version
azzx ai
azzx ask "..."
azzx config
azzx mode safe
azzx permissions list
```

### Coding

```bash
azzx fix "..."
azzx add "..."
azzx implement "..."
azzx create "..."
azzx agent "..."
azzx edit "..."
azzx develop "..."
azzx diff
azzx undo
```

### Engineering

```bash
azzx map
azzx review
azzx test
azzx debug ...
azzx security
azzx architect
azzx impact PATH
azzx symbol NAME
azzx deps
azzx remember "..."
azzx team "..."
azzx sandbox ...
azzx factory "..."
azzx spec ...
azzx roadmap ...
azzx regression capture|check
azzx mcp ...
azzx skill ...
azzx dashboard
```

### Applications (v6)

```bash
azzx install APP [--plan|--dry-run|--isolated]
azzx update APP | --all
azzx repair APP
azzx uninstall APP
azzx installed
azzx app search|info|recipes|system
```

### Toolkit (v7)

```bash
azzx tools list
azzx tools run TOOL --args '{...}'
azzx toolkit health|largest|duplicates|hash|website|...
azzx nl "show system health"
```

### Workflow & device (v8)

```bash
azzx workflow create|list|show|run|delete ...
azzx mirror detect|devices|start|stop|status
```

### Plugins (v9)

```bash
azzx plugin install DIR [--force]
azzx plugin list
azzx plugin load
```

---

## 22. Project layout

```text
AZZATSSINS_LITE_AGENT_v10.0/
├── azzx_cli.py           # Main CLI (v1–v6 surfaces + wiring)
├── azzx/                 # v7–v10 modules (required at install)
│   ├── core.py
│   ├── agent/
│   ├── tools/
│   ├── workflow/
│   ├── device/
│   ├── plugins/
│   └── cli_v10.py
├── tests/
├── examples/
│   ├── sample-plugin/
│   └── workflow-health.json
├── install.sh
├── uninstall.sh
├── update-local.sh
├── requirements.txt
├── VERSION
├── CHANGELOG.md
└── README.md
```

Dependencies: `rich`, `httpx` (optional `cryptography`).

---

## 23. Limitations

- Screen mirror is **scrcpy on a host**, not a full Samsung DeX environment on the phone.  
- Install success depends on distro repos and architecture; AZZX stops if no trusted method exists.  
- Workflows cannot run arbitrary shell by design.  
- Always verify with `azzx --help` and `azzx <cmd> --help` on your installed build.

---

## 24. License / contributing

Add a `LICENSE` file before publishing (e.g. MIT).  

Contributions that fit the design: new **deterministic** registry tools, safer recipes, tests, docs.  

Avoid: free-form shell from AI/workflows, unsigned remote plugin install, silent privilege escalation.

---

## Credits

- Termux & major Linux distros  
- [scrcpy](https://github.com/Genymobile/scrcpy) for mirroring when installed  
- [Rich](https://github.com/Textualize/rich) · [httpx](https://github.com/encode/httpx)

```bash
azzx --version
# AZZATSSINS LITE AGENT 10.0.0
```

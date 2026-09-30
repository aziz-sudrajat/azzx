# AZZATSSINS LITE AGENT (AZZX) v10.0.0

**Terminal-first AI engineering agent** for Termux and Linux — with a Universal Application Installer, deterministic toolkit, safe workflows, local plugins, and realistic Android screen mirroring.

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

- [Highlights](#highlights)
- [Feature history (v1 → v10)](#feature-history-v1--v10)
- [Architecture (v10)](#architecture-v10)
- [Install](#install)
- [Upgrade from v6](#upgrade-from-v6)
- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [Security model](#security-model)
- [Permissions](#permissions)
- [Configuration](#configuration)
- [Plugins](#plugins)
- [Android screen mirror](#android-screen-mirror)
- [Development & tests](#development--tests)
- [Project layout](#project-layout)
- [Limitations](#limitations)
- [License / contributing](#license--contributing)

---

## Highlights

| Area | What you get |
|------|----------------|
| **AI coding agent** | Multi-provider (OpenAI-compatible, Anthropic, Cohere, Gemini, Groq, …), project context, review, debug, multi-agent roles |
| **Software factory** | Sandboxed develop, checkpoint/undo, regression gates, release prepare |
| **App installer** | Distro-aware install/update/repair/uninstall via native package managers |
| **Toolkit** | Files, hash, archive, JSON, FFmpeg, network, processes, git, system health |
| **Workflows** | Automate **only** registered tools — never arbitrary shell |
| **Device** | ADB detect, Termux API detect, **scrcpy** screen mirror |
| **Plugins** | Local plugins with `manifest.json` + declared permissions |
| **Safety** | Permissions (`allow` / `ask` / `deny`), plan/dry-run, input validation |

---

## Feature history (v1 → v10)

### v1 — Lite foundation
- Terminal CLI shell for a lightweight agent
- Basic project-aware prompts
- Simple config under user home

### v2 — Provider & secrets
- Multiple AI provider configuration
- Local API-key storage (file-protected / optional encryption)
- Richer terminal UI (status, panels)

### v3 — AI programmer / repository-aware agent
- Workspace file reading with safety limits
- Instruction → code changes with backup / diff / undo
- Project memory (`remember` / `memory`)
- Repository index & basic navigation
- Chat / ask / edit / implement flows

### v4 — Software engineering layer
- Architecture generation (`architect`)
- Dependency report (`deps`)
- Test runner integration (`test`)
- Git helpers & checkpoints
- Debug loop against a failing command
- Security-oriented static review patterns
- Impact / symbol-oriented analysis beginnings

### v5 — Sandboxed software factory
- **Sandbox develop** — changes isolated before merge
- **Multi-agent roles** — planner, architect, coder, backend, frontend, database, security, QA, reviewer, tester
- **Permissions policy** — `allow` / `ask` / `deny` per capability
- Spec & roadmap generation
- Regression baseline / check
- Release prepare / factory develop
- MCP client (Model Context Protocol servers)
- Skills, plugins (command-style), issues, CI scaffold
- Dashboard (local read-only HTTP)
- Task auto-review, smart provider routing

### v6 — Universal system / application agent
- **Universal Application Installer** — `azzx install APP`
- OS / distro / arch detection (Termux, Debian, Arch, Fedora, openSUSE, Alpine, Void, Gentoo, WSL, …)
- Native package managers: `pkg`, `apt`, `pacman`, `dnf`/`yum`, `zypper`, `apk`, `xbps`, `emerge`
- Modes: `--plan`, `--dry-run`, `--yes`, `--force`, `--isolated` (PyPI venv)
- Lifecycle: `installed`, `update`, `repair`, `uninstall`
- `app search` / `app info` / `app recipes` / `app system`
- Trusted recipes; custom recipes = package aliases only (no shell inject)
- Metasploit: native package first; official Rapid7 script only on trusted Linux (never auto on Termux)
- Application Center UI (`/apps`), responsive Termux/desktop layout
- Live package-manager output panels

### v7 — Universal Toolkit *(shipped in v10)*
- File search, largest files, duplicate finder
- Hash / checksum (`md5`, `sha1`, `sha256`, `sha512`, `blake2b`)
- Archive create / extract (blocks path traversal)
- JSON format & validate
- FFmpeg convert / probe (whitelisted formats only)
- Network connectivity & website HTTP status
- Process list, systemd service status, git status
- System info & health (disk, load)
- CLI: `azzx toolkit …`, `azzx tools list|run`, `azzx nl "…"`

### v8 — Automation & device *(shipped in v10)*
- **Workflow engine** — create / list / show / run / delete
- Workflow steps = **registered tools only** (no free-form shell)
- ADB detection & device list (no free-form `adb shell`)
- Termux:API capability detection
- **Android screen mirroring via scrcpy** — `azzx mirror`
  - `detect` / `devices` / `start` / `stop` / `status` / `--dry-run`
  - Whitelisted scrcpy arguments (size, bitrate, fullscreen, …)

### v9 — Extensibility *(shipped in v10)*
- Local plugin system
- Required `manifest.json` (id, version, tools, permissions, entrypoint)
- Permission declaration validated against known capabilities
- Banned fields: `shell`, `install_script`, `command`, …
- `azzx plugin install|list|load` (alongside legacy command-plugins)

### v10 — Universal Agent Layer
- Central **Tool Registry** (`azzx.core.REGISTRY`)
- AI as **orchestrator**; deterministic tools as **executors**
- Natural-language shortcuts mapped to safe tools only
- Modular package layout under `azzx/`
- All v3–v6 coding, factory, installer, and security features retained
- Expanded permissions: `device.adb`, `device.mirror`, `workflow.run`, `plugin.install`, `process.inspect`, `archive.write`, `filesystem.read`

---

## Architecture (v10)

```text
┌─────────────────────────────────────────────────────────┐
│  azzx_cli.py                                            │
│  Interactive UI · coding agent · app installer · CLI    │
└───────────────────────────┬─────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ azzx.agent    │   │ Tool Registry │   │ v6 surfaces   │
│ NL → tool map │──▶│ REGISTRY.call │   │ develop, git, │
│ orchestrator  │   │ + permissions │   │ install, MCP… │
└───────────────┘   └───────┬───────┘   └───────────────┘
                            │
     ┌──────────┬───────────┼───────────┬──────────┐
     ▼          ▼           ▼           ▼          ▼
  tools/    workflow/    device/    plugins/    (OS)
  v7 kit    v8 flows     mirror     v9 load
```

**Design rule:** side effects go through registered tools + permission checks. The AI does not invent shell installers or free-form `adb shell` commands.

---

## Install

### Requirements

- Python **3.10+**
- Linux or **Termux**
- Optional: `ffmpeg`, `scrcpy`, `adb`, `git`, `cryptography`

### From release zip

```bash
unzip AZZATSSINS_LITE_AGENT_v10.0.zip
cd AZZATSSINS_LITE_AGENT_v10.0
chmod +x *.sh
./install.sh --check
./install.sh
```

Then open a new terminal if needed:

```bash
azzx --version
# AZZATSSINS LITE AGENT 10.0.0
```

### Installer flags

| Flag | Meaning |
|------|---------|
| `--check` | Detect OS / package manager only |
| `--no-system-deps` | Do not install system packages via apt/pacman/pkg/… |
| `--no-crypto` | Skip optional Fernet encryption dependency |

### Supported environments (app installer)

| Environment | Package manager |
|-------------|-----------------|
| Termux | `pkg` |
| Debian / Ubuntu / Mint / Kali / Pop!_OS | `apt` |
| Arch / Manjaro / EndeavourOS | `pacman` |
| Fedora | `dnf` |
| RHEL-family | `dnf` / `yum` |
| openSUSE | `zypper` |
| Alpine | `apk` |
| Void | `xbps` |
| Gentoo | `emerge` |

---

## Upgrade from v6

**You do not need to uninstall first.** Config and API keys are kept.

```bash
cd AZZATSSINS_LITE_AGENT_v10.0
./install.sh
# or: ./update-local.sh   # same as install --no-system-deps
azzx --version
```

| Path | On upgrade |
|------|------------|
| `~/.local/share/azzatssins-lite-agent/` | Replaced with v10 app files |
| `~/.config/azzatssins-lite-agent/` | **Preserved** (providers, secrets, permissions) |
| `~/.local/bin/azzx` (or Termux `$PREFIX/bin/azzx`) | Updated launcher |

Clean reinstall (optional):

```bash
./uninstall.sh          # keep config
./uninstall.sh --purge  # also delete config & API keys
./install.sh
```

---

## Quick start

```bash
# Interactive home
azzx

# AI coding (requires configured provider)
azzx ask "jelaskan struktur project ini"
azzx develop "tambah endpoint health check"

# System toolkit
azzx toolkit health
azzx toolkit largest --path . --limit 15
azzx nl "git status"

# Apps
azzx install ffmpeg --plan
azzx install scrcpy

# Mirror Android → desktop (needs adb + scrcpy + device)
azzx mirror detect
azzx mirror start --dry-run
azzx mirror start --max-size 1280

# Workflow
azzx workflow create daily --steps '[{"tool":"sys.health","args":{}},{"tool":"git.status","args":{"path":"."}}]'
azzx workflow run daily -y
```

---

## Command reference

### AI & engineering (v3–v5, retained)

| Command | Description |
|---------|-------------|
| `azzx` | Interactive mode |
| `azzx ask …` | Question about the workspace |
| `azzx edit …` / `implement …` | Apply AI-guided changes |
| `azzx develop …` | Sandboxed or direct develop |
| `azzx create …` | Scaffold a new project |
| `azzx review [focus]` | AI code review |
| `azzx debug CMD` / `autodebug CMD` | Run / auto-fix failing command |
| `azzx test [CMD]` | Run tests |
| `azzx architect` | Architecture notes |
| `azzx map` / `symbol` / `impact` | Repo map & impact |
| `azzx security [--external]` | Static security review |
| `azzx team …` / multi-agent roles | Role-based engineering |
| `azzx sandbox` / factory / release | Factory pipeline |
| `azzx mcp …` | MCP servers |
| `azzx skill …` | Engineering skills |
| `azzx git …` / `diff` / `undo` | Git & change history |
| `azzx remember` / `memory` | Project memory |
| `azzx research` / `docs` | Research helpers |
| `azzx ci` / `benchmark` / `profile` / `db` | Engineering utilities |
| `azzx permissions list\|set\|reset` | Capability policies |

### Application installer (v6)

| Command | Description |
|---------|-------------|
| `azzx install APP` | Install via native PM / recipe |
| `azzx install APP --plan` | Show plan only |
| `azzx install APP --dry-run` | Simulate |
| `azzx install APP --isolated` | Isolated Python/PyPI env |
| `azzx update APP` / `update --all` | Update |
| `azzx repair APP` | Repair |
| `azzx uninstall APP` | Safe uninstall (tracked) |
| `azzx installed` | History |
| `azzx app search\|info\|recipes\|system` | Discovery |

### Toolkit (v7)

| Command | Description |
|---------|-------------|
| `azzx tools list` | List registry |
| `azzx tools run NAME --args '{…}'` | Run one tool |
| `azzx toolkit health\|info\|processes\|…` | Shortcuts |
| `azzx toolkit search\|largest\|duplicates` | Files |
| `azzx toolkit hash --path FILE` | Checksum |
| `azzx toolkit website --url URL` | HTTP status |
| `azzx toolkit connectivity` | TCP check |
| `azzx nl "phrase"` | Safe NL → tool |

### Workflows (v8)

| Command | Description |
|---------|-------------|
| `azzx workflow list` | List workflows |
| `azzx workflow create NAME --steps '[{…}]'` | Create |
| `azzx workflow show\|run\|delete NAME` | Manage / execute |

### Device / mirror (v8)

| Command | Description |
|---------|-------------|
| `azzx mirror detect` | scrcpy + adb + Termux detect |
| `azzx mirror devices` | `adb devices` |
| `azzx mirror start [--serial] [--max-size] [--dry-run]` | Start scrcpy |
| `azzx mirror stop` / `status` | Stop / status |

### Plugins (v9)

| Command | Description |
|---------|-------------|
| `azzx plugin list` | Installed plugins |
| `azzx plugin install DIR [--force]` | Install from folder with `manifest.json` |
| `azzx plugin load` | Load enabled entrypoints |
| `azzx plugin add\|remove\|run` | Legacy command-plugins (v5) |

---

## Security model

1. **Native package manager first** — dependencies resolved by the distro, not by AI-generated shell.
2. **Recipes** — user recipes may only map package names + verifiers; no arbitrary install scripts.
3. **Vendor scripts** — only built-in trusted HTTPS hosts, still behind permissions.
4. **Tool registry** — workflows and NL shortcuts cannot call unregistered tools.
5. **No free-form device shell** — ADB/scrcpy use allowlisted argv lists.
6. **Archives** — extract rejects `..` and absolute member paths.
7. **FFmpeg** — only preset output formats (`mp4`, `webm`, `mp3`, `wav`, `gif`, `mkv`).
8. **Plugins** — manifest permissions must be from the known capability list; banned shell hooks.

AZZX prefers to **stop safely** rather than execute an untrusted installer command.

---

## Permissions

```bash
azzx permissions list
azzx permissions set device.mirror ask
azzx permissions set package.install allow
azzx permissions reset
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

Use `-y` / `--yes` only after you understand the plan; non-interactive runs still respect `deny`.

---

## Configuration

| Location | Purpose |
|----------|---------|
| `~/.config/azzatssins-lite-agent/config.json` | Mode, limits, permissions, roles |
| `~/.config/azzatssins-lite-agent/providers.json` | AI providers |
| `~/.config/azzatssins-lite-agent/secrets.enc` or `secrets.json` | API keys |
| `~/.local/share/azzatssins-lite-agent/` | App install, venv, workflows, plugins, mirror state |

Configure providers interactively:

```bash
azzx
# open AI / provider menu
```

---

## Plugins

Example manifest (`examples/sample-plugin/manifest.json`):

```json
{
  "id": "sample-echo",
  "name": "Sample Echo Plugin",
  "version": "1.0.0",
  "description": "Example v9 plugin",
  "tools": ["sample.echo"],
  "permissions": [],
  "entrypoint": "plugin.py",
  "enabled": true
}
```

```bash
azzx plugin install examples/sample-plugin --force
azzx plugin list
azzx plugin load
```

Plugins register tools on the shared registry; **calls still go through permission checks**.

---

## Android screen mirror

This is **realistic desktop mirroring** (scrcpy), **not** a full on-device Samsung DeX environment.

**Desktop side needs:**

1. `adb` (platform-tools)
2. `scrcpy`
3. USB debugging or wireless ADB on the phone

```bash
azzx install scrcpy --plan
azzx install scrcpy
azzx mirror devices
azzx mirror start --max-size 1280 --dry-run
azzx mirror start --max-size 1280
azzx mirror status
azzx mirror stop
```

---

## Development & tests

```bash
cd AZZATSSINS_LITE_AGENT_v10.0
python3 -m unittest tests.test_v10 -v
```

`tests/test_v10.py` covers registry tools, archive traversal block, workflow rejection of unknown tools, NL mapping, plugin manifest validation, mirror dry-run structure, and more.

---

## Project layout

```text
AZZATSSINS_LITE_AGENT_v10.0/
├── azzx_cli.py              # Main CLI (coding agent + installer + v10 commands)
├── azzx/
│   ├── core.py              # Config, permissions, ToolRegistry
│   ├── agent/               # Orchestrator, NL → tool
│   ├── tools/               # v7 toolkit
│   ├── workflow/            # v8 workflows
│   ├── device/              # ADB, scrcpy mirror, Termux
│   ├── plugins/             # v9 plugin loader
│   └── cli_v10.py           # Handlers for new subcommands
├── tests/
├── examples/
│   ├── sample-plugin/
│   └── workflow-health.json
├── install.sh
├── uninstall.sh
├── update-local.sh
├── selftest.sh
├── requirements.txt         # rich, httpx
├── VERSION
├── CHANGELOG.md
└── README.md
```

Python deps (minimal):

```text
rich>=13.7,<15
httpx>=0.27,<1
```

Optional: `cryptography` (encrypted secret vault).

---

## Limitations

- **Not a full Samsung DeX clone** — mirroring uses scrcpy on a desktop host.
- Install success depends on distro repos, architecture, and licenses; AZZX stops when no trusted method exists.
- Real package installs and live device mirroring are environment-dependent; CI emphasizes plan/dry-run, validation, and unit tests.
- Coding-agent core still largely lives in `azzx_cli.py`; toolkit/device/workflow are modular under `azzx/`.

---

## License / contributing

This project is distributed as **AZZATSSINS LITE AGENT**. Add a `LICENSE` file before publishing (e.g. MIT / Apache-2.0).

**Contributing ideas that fit the design:**

- New **deterministic** tools registered in the registry
- Safer package aliases / recipes (no arbitrary shell)
- Tests for permission and path validation
- Documentation in `README_ID.md` (Bahasa Indonesia)

**Please avoid:**

- Free-form shell execution from AI or workflows
- Remote plugin install without checksum/signature
- Silent privilege escalation paths

---

## Credits

- Built for **Termux** and major **Linux** distributions
- Screen mirroring uses [scrcpy](https://github.com/Genymobile/scrcpy) when installed on the host
- UI: [Rich](https://github.com/Textualize/rich) · HTTP: [httpx](https://github.com/encode/httpx)

---

```bash
azzx --version
# AZZATSSINS LITE AGENT 10.0.0
```

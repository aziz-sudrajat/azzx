# AZZATSSINS LITE AGENT v10.0

**AZZX** is a terminal-first AI engineering agent with a **Universal Agent Layer**:

```text
User / Natural language
        ↓
AI Orchestrator (multi-provider coding agent — retained from v6)
        ↓  structured tool calls only
Tool Registry (deterministic executors)
        ↓  permission + audit
OS / workspace / Android device
```

## What's new in v10

| Layer | Features |
|-------|----------|
| **v7 Toolkit** | File search, largest files, duplicates, hash, archive, JSON, FFmpeg convert, network/website status, processes, services, git status, system health, NL shortcuts |
| **v8 Automation** | Workflow engine (create/list/run) — **only registered tools**, never arbitrary shell; ADB + Termux API detection |
| **v8 Device / Mirror** | Realistic Android screen mirroring via **scrcpy** (start/stop/status/dry-run). Not a full Samsung DeX clone |
| **v9 Plugins** | Local plugins with `manifest.json`, declared permissions, validation, install from directory |
| **v10 Agent** | Unified tool registry; AI as orchestrator; deterministic tools as executors |
| **v6 retained** | Coding agent, multi-provider AI, sandbox/factory, Universal App Installer, permissions, MCP, git, review |

## Install

```bash
unzip AZZATSSINS_LITE_AGENT_v10.0.zip
cd AZZATSSINS_LITE_AGENT_v10.0
chmod +x *.sh
./install.sh --check
./install.sh
```

```bash
azzx --version   # 10.0.0
```

Dependencies: `rich`, `httpx` (optional: `cryptography`, `ffmpeg`, `scrcpy`, `adb`).

## Quick commands

### Toolkit (v7)

```bash
azzx toolkit health
azzx toolkit largest --path . --limit 15
azzx toolkit duplicates --path .
azzx toolkit hash --path README.md --algorithm sha256
azzx toolkit website --url https://example.com
azzx toolkit connectivity
azzx tools list
azzx tools run sys.health --args '{}'
azzx nl "show system health"
azzx nl "largest files"
```

### Workflows (v8)

```bash
azzx workflow create daily --steps '[{"tool":"sys.health","args":{}},{"tool":"git.status","args":{"path":"."}}]'
azzx workflow list
azzx workflow run daily
```

### Android mirror (realistic DeX-like)

```bash
azzx mirror detect
azzx mirror devices          # requires adb + device.adb permission
azzx mirror start --dry-run
azzx mirror start --max-size 1280
azzx mirror status
azzx mirror stop
```

Requires [scrcpy](https://github.com/Genymobile/scrcpy) and `adb` on the **desktop** side. This mirrors and controls the Android screen on your computer — it does **not** turn the phone into a full desktop environment like Samsung DeX.

### Plugins (v9)

```bash
azzx plugin install examples/sample-plugin
azzx plugin list
azzx plugin load
```

### App installer & coding agent (v6 foundation)

```bash
azzx install ffmpeg
azzx install scrcpy --plan
azzx develop "add logging middleware"
azzx permissions list
```

## Security model

- Package names validated before package managers
- Custom app recipes cannot inject shell installers
- Workflows may **only** call tools in the registry
- scrcpy/ADB arguments are whitelisted (no free-form `adb shell`)
- Plugins must declare permissions from a fixed capability list
- Archive extract blocks path traversal (`../`)
- FFmpeg only allows known output format presets

## Architecture packages

```text
azzx/
  core.py           # config, permissions, ToolRegistry
  tools/            # v7 deterministic toolkit
  workflow/         # v8 workflow engine
  device/           # ADB, scrcpy mirror, Termux detect
  plugins/          # v9 manifest loader
  agent/            # v10 orchestrator helpers
  cli_v10.py        # CLI handlers for new commands
azzx_cli.py         # main entry (coding agent + installer + v10 commands)
```

## License / project

See project docs. Review `REVIEW_REPORT_v10.md` for automated checks performed on this release.

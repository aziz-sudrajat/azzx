# Changelog

## v10.0.0

### Universal Agent Layer
- Tool registry central (`azzx.core.REGISTRY`)
- AI orchestrator helpers + natural-language shortcuts for safe toolkit ops
- Coding agent, multi-provider AI, sandbox/factory, MCP retained from v6

### v7 Universal Toolkit
- `azzx toolkit` / `azzx tools` / `azzx nl`
- File search, largest files, duplicate finder
- Hash/checksum, archive create/extract (path-traversal safe)
- JSON format/validate
- FFmpeg convert with format whitelist
- Network connectivity + website status
- Process list, service status, git status, system health

### v8 Automation & Device
- Workflow engine: create/list/show/run/delete
- Workflows restricted to registered tools only
- ADB detection + device list (no free-form adb shell)
- Termux API capability detection
- **Screen mirroring via scrcpy** (`azzx mirror`): start/stop/status/detect/devices/dry-run

### v9 Extensibility
- Local plugin system with `manifest.json`
- Permission declaration + validation
- Plugin install from directory, list, load

### Safety
- New permission capabilities: device.adb, device.mirror, workflow.run, plugin.install, process.inspect, archive.write, filesystem.read
- Archive member path validation
- scrcpy argument whitelist
- Plugin manifests cannot declare shell/install_script hooks

## v6.0.0
- Universal Application Installer and prior engineering features (see v6 notes)

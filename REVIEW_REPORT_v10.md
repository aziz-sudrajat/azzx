# AZZX v10.3.0 Review Report

## Scope

Review of the v10.3.0 Universal Agent Layer and reliability/scheduler upgrade with modular packages:

- `azzx/core.py` — registry, permissions
- `azzx/tools/*` — v7 toolkit
- `azzx/workflow/*` — v8 workflows
- `azzx/device/*` — ADB + scrcpy mirror + Termux
- `azzx/plugins/*` — v9 plugins
- `azzx/agent/*` — orchestrator
- `azzx_cli.py` — v6 coding/installer surface + v10 commands

## Security review

| Control | Status |
|---------|--------|
| Workflow cannot call unregistered tools | Pass (validated in engine + tests) |
| No arbitrary shell in workflow steps | Pass |
| Archive path traversal blocked | Pass (test + extract guards) |
| scrcpy args whitelist | Pass (list argv, ranges on size/bitrate) |
| Plugin unknown permissions rejected | Pass |
| Plugin banned fields (shell, install_script) | Pass |
| FFmpeg format whitelist | Pass |
| Package installer path (from v6) | Retained |

## Known limitations

- Full Samsung DeX desktop mode on-device is **not** implemented (by design)
- scrcpy/adb must be installed on the host for mirroring
- Real device mirroring not exercised in CI (dry-run + detect covered)
- v6 coding-agent paths still live primarily in `azzx_cli.py` (gradual modularization)

## v10.3.0 changes

- Task queue persists submissions before dispatch and synchronizes terminal state with the durable snapshot.
- Queue state uses unique temporary files, fsync, atomic replacement, and protection against stale-state regression.
- Added malformed PID recovery and regression coverage for many fast tasks.
- Added persistent interval scheduling for registered tools only. It is a one-shot runner intended for cron/systemd, not a resident service.
- Added GitHub Actions CI matrix for Python 3.10–3.13 and contribution/security guidance.

## Known limitations

- Scheduler is single-host/local-profile oriented; it is not a distributed scheduler.
- The task queue still uses JSON state and is not intended for high-volume multi-process workloads.
- Plugin manifests do not sandbox trusted Python plugin code.
- Installer compatibility is not proven for every supported distro by the offline test suite.

## Test plan executed

See `tests/test_v10.py` and legacy `tests/test_core.py`.

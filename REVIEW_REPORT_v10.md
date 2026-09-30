# AZZX v10 Review Report

## Scope

Upgrade from v6 monolith to v10 Universal Agent Layer with modular packages:

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

## Test plan executed

See `tests/test_v10.py` and legacy `tests/test_core.py`.

# Next Actions (autonomous loop state)

> Updated: 2026-10-11 07:20 WIB. v10.6.8 in worktree, NOT pushed.

## Last completed
- v10.6.8: `do` router expanded to 17 intents (added doctor/checkpoint/
  schedule/audit). 209 tests pass on 3.10/3.11/3.12/3.14.
- Knowledge base created: PROJECT_MAP.md, IMPROVEMENT_ROADMAP.md, this file.

## Next (in priority order)
1. **P2 — GUI depth**: `chat.html` needs conversation history + file picker
   for `@file`. Incremental; keep stdlib-only constraint.
2. **P3 — Startup performance**: baseline `import azzx_cli` time, then lazy-load.
3. **P4 — Connectors**: only on explicit user request (maintenance cost).

## Push checklist for v10.6.8
- [x] Tests pass (209, all Python versions)
- [x] CHANGELOG + roadmap updated
- [ ] ZIP rebuilt + SHA (do before push)
- [ ] User pushes via Termux (never push from here)

## Session notes
- Worktree is NOT a git repo; user pushes from Termux via ZIP.
- `message_bus.py` is LIVE — never delete (subagent was wrong once).
- `do` router: never route consequential actions (install, schedule-add).

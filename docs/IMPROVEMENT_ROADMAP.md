# AZZX Improvement Roadmap

> Prioritized backlog for the autonomous improvement loop.
> Updated: 2026-10-11 (v10.6.7). Priority order: security → crashes →
> reliability → performance → capabilities → maintainability → UX.

## Done (v10.6.x)

- [x] v10.6.4: `@file` attachments for chat/GUI; local LLM docs (Ollama)
- [x] v10.6.5: auto-chaining (recall+learn); browser read/write modes
- [x] v10.6.6: `azzx do` smart router; `--help` consolidation (93→28)
- [x] v10.6.7: dead code removal (7 methods, 15 imports); full audit clean

## Backlog (prioritized)

### P1 — `do` router coverage gaps
The router covers ~13 intents; 93 commands exist. Missing high-value intents:
- `schedule`: "jadwalkan X tiap jam", "ingatkan saya"
- `checkpoint`: "backup project", "snapshot"
- `doctor`: "cek kesehatan sistem"
- `install`: "install ffmpeg" (consequential — keep confirmation)
- `audit`: "audit pekerjaan terakhir"
Status: **DONE** in v10.6.8 (17 intents; schedule-add/install intentionally excluded)

### P2 — GUI depth
`chat.html` is 151 lines; no conversation history, no markdown tables,
no file picker for `@file`. Incremental additions only.

### P3 — Startup performance
Measure `import azzx_cli` time; lazy-load heavy modules. Needs baseline first.

### P4 — Connector coverage
Only GitHub + Email. Candidates: Telegram send (gateway exists), RSS.
Each connector = permanent maintenance; add only on user request.

### P5 — `webauto` robustness
More sites are JS-heavy; document Playwright escape hatch better.
No JS engine will be bundled (kentang constraint).

## Technical debt (accepted)

- `azzx_cli.py` is 6.044 lines / 228 functions (monolith). Splitting is
  high-risk, low immediate value — deferred until a concrete need arises.
- Provider re-export block in `azzx_cli.py` (~line 458) kept for backwards compat.
- `message_bus.py` is live (multi_agent + orchestrator use it) — do not delete.

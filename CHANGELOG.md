# Changelog

## v10.6.16 — Bugfix: self-update tarball validation

`azzx self-update` failed with `unexpected tarball entry: azzx-main`:
the root directory entry in GitHub tarballs has no trailing slash,
so the prefix check rejected it. Now accepts the root entry itself,
plus an explicit `..` traversal check for Python 3.10/3.11.


## v10.6.15 — Bugfix: GUI chat hung after first message

Reported: first GUI chat submit displayed a response, but subsequent
submits did nothing.

Root cause: the SSE endpoint (`/api/chat/stream`) sent
`Connection: keep-alive` and never closed the connection after `[DONE]`.
The browser waited forever for more data, so the JS `busy` flag never
reset and blocked every later submit.

Fix (server): removed the `keep-alive` header, set `close_connection = True`,
flush after `[DONE]` — the client now detects completion via close.
Fix (client): `[DONE]` now breaks the outer read loop too, and the reader
is cancelled after the stream ends (defense in depth).


## v10.6.14 — NEW: `azzx self-update`

Update AZZX itself from GitHub without reinstalling manually:

- `azzx self-update --check` — compare local vs GitHub VERSION, no changes.
- `azzx self-update` — shows changelog, asks confirmation, backs up the
  current install (last 3 kept), downloads the main-branch tarball,
  replaces program files (same set as install.sh), verifies VERSION +
  syntax, auto-rolls back on failure. User data and venv untouched.
- `azzx do "update azzx"` routes to a check-only preview.
- Named `self-update` to avoid clashing with the existing
  `azzx update <app>` (application updates).


## v10.6.13 — Security hardening + docs (review round 3)

Security audit of the self-modification pipeline:

1. Regex-based code scanner replaced with AST-based `scan_handler`:
   now catches `getattr(os, 'system')` indirection, `import os as o`
   aliasing, and `from os import system` — all bypassed the old regex.
2. NEW `scan_patch`: `evolve approve` now AST-scans ADDED diff lines
   before applying (previously unscanned — user review was the only gate).
3. README (EN + ID) now documents `extend`/`evolve` — previously undiscoverable.


## v10.6.12 — Bugfix: extend/evolve robustness (review round 2)

Deep review + end-to-end verification found 3 more bugs:

1. Skill IDs with hyphens (e.g. `word-count`) crashed on `skills enable`:
   `register_skill_tools` registered `skill.word-count` which fails tool
   name validation. Now sanitized to `skill.word_count` (skill ID unchanged
   for trust/enable/invoke). Pre-existing bug — affected ALL hyphenated skills.
2. `evolve propose` crashed on malformed AI output (proposals not a list,
   non-dict entries, unparseable JSON). Now hardened with type checks.
3. `evolve approve` crashed if `changes` contained non-dict entries.
   Now filtered safely.

Verified end-to-end with mocked AI: generate → validate → install
(untrusted) → trust → enable → invoke all work.


## v10.6.11 — Bugfix: self-extension & evolve hardening

Review audit of v10.6.9/v10.6.10 found and fixed 5 bugs:

1. `forced_provider` silently ignored in `extend`, `evolve propose`,
   and patch generation — now threaded through to the AI router.
2. JSON extraction regex broke on nested objects — replaced with
   robust `_extract_json` (fenced block + outermost braces).
3. `_apply_diff` never verified context/removed lines — a stale AI diff
   could silently corrupt files. Now raises on any mismatch.
4. `evolve approve` patched relative to the user's cwd instead of the
   AZZX installation — now resolves via `azzx_install_root()`.
5. `input()` confirmation crashed with EOFError in non-interactive
   mode — now fails safe (patch skipped, hint to use --yes).


## v10.6.10 — Self-improvement loop: `azzx evolve`

AZZX now observes itself, learns user habits, and repairs its own code:

- `azzx evolve analyze` — reads the audit trail: top tools (habits),
  failure hotspots, repeated sequences, denied permissions.
- `azzx evolve propose` — AI turns observations into staged proposals
  (habit / fix / feature). Max 5, low-risk preferred.
- `azzx evolve proposals` — review staged proposals.
- `azzx evolve approve <id>` — checkpoint → AI generates unified diff →
  user confirms each diff → apply → syntax check. Auto-rollback on failure.
  `--yes` skips per-diff confirmation.
- `azzx evolve reject <id>` — discard a proposal.
- Self-protection: proposals touching permissions.py / auditor.py /
  evolve.py are rejected unless --force. Nothing auto-applies — the user
  is always the gate.
- `azzx do "kembangkan dirimu"` routes to evolve.


## v10.6.9 — Self-extension: AZZX builds its own features

- NEW `azzx extend "<request>"`: AI generates a NEW SKILL from a feature
  request. Generated code goes through the EXISTING trust infrastructure:
  manifest validation (bans exec/eval/install hooks), syntax check,
  dangerous-pattern scan (subprocess/os.system/socket/eval), then install
  as UNTRUSTED + DISABLED. User reviews code, then explicitly runs
  `azzx skills trust <id>` + `azzx skills enable <id>`. AI can never
  silently activate code.
- `azzx do "tambahkan fitur untukmu X"` routes to extend.
- Router fix: multi-word phrases score higher (3) and leading phrases
  beat single first-word matches.


## v10.6.8 — `do` router expansion (P1)

- `azzx do` now routes 4 more intents (17 total): `doctor` ("cek kesehatan
  sistem"), `checkpoint` ("buatkan checkpoint"), `schedule` ("lihat jadwal"),
  `audit` ("audit pekerjaan terakhir"). All are read-only or snapshot-only;
  consequential actions (`schedule add`, `install`) intentionally NOT routed.
- Fixed verb-stripping for the new intents.

## v10.6.7 — "Clean & Lean" (dead code removal)

Full static audit of all 56 script files: no dispatch bugs, no circular
imports, no secrets, no TODO debt. The audit found dead code — removed:

- 7 dead methods (verified zero call sites): `add_project_task`,
  `update_session_summary` (session.py); `get_agent_summary`,
  `purge_orphan_vectors` (memory.py); `iter_events` (streaming.py);
  `search_memory` (multi_agent.py); `thoughts` (reasoning.py)
- 15 unused imports: 12 in azzx_cli.py (`base64`, `getpass`, `textwrap`,
  `uuid`, `Iterable`, `Optional`, 6× `rich.progress`), 3 in cli_v10.py
- Kept deliberately: `message_bus.py` (live — used by multi_agent +
  orchestrator), the provider re-export block in azzx_cli.py (backwards compat)

Less code = faster startup on kentang machines. Zero behavior change.

## v10.6.6 — command consolidation: fewer commands, same power

- New `azzx do "<tugas>"`: the smart front door. Describe the task in plain
  Indonesian/English, AZZX routes it to the right pipeline (fix, implement,
  review, debug, test, web, remember, recall, plan, auto, compress, ask).
  Offline keyword routing (deterministic, predictable); always prints which
  command it runs; `--dry-run` to preview. New `azzx/agent/intent.py`.
- New `azzx help`: curated grouped command guide (the simple view).
- `--help` now shows 28 curated commands instead of 93 (usage line is
  `<command>`). All 93 commands keep working — only the help display changed.
- Added missing help texts for ask/fix/implement/review/debug/test/
  remember/ai/doctor/config so the curated view is complete.

## v10.6.5 — auto-chaining + browser two modes

- Auto-chaining (v10.6.5): `fix`/`add`/`implement`/`review` now automatically
  **recall** relevant memory before the AI runs and **learn** (distill into
  staged proposals, never auto-approved) after. Opt out per run with
  `--no-recall` / `--no-learn`. New `azzx/agent/autochain.py`.
- Browser two modes: `azzx browse mode [read|write]`. `read` (default) is the
  old behavior. `write` enables `web.forms` (list forms), `web.submit`
  (fill + submit, HTTP-level, no JS), cookie sessions, and
  `azzx webauto --write` (agent may submit forms to complete tasks).
  Write mode is explicit opt-in; every submit needs `browser.write`
  permission (ask by default, explicit deny is absolute), passes the SSRF
  guard, and is audit-logged. New `azzx/agent/webforms.py`.
- Fixed wrong `ToolSpec` import in webforms (would have broken tool registration).

## v10.6.4 — file attachments for chat/GUI + local LLM docs

- Fixed: `azzx chat` and `azzx gui` never sent project files to the AI, so
  "analisa file X" always failed. Now: `@path/to/file` mentions in any
  message attach the file (read + auto-compressed), and `/add <file>`
  keeps files attached for the session (`/added`, `/unadd`). Paths are
  jailed to the workspace (`@../secret` refused); binaries/>2MiB skipped.
- New `azzx/agent/attachments.py`; wired into `cmd_chat` and the GUI
  server (`_chat_once`/`_chat_stream`); GUI placeholder hints @file.
- Documented local LLM support: Ollama preset (keyless,
  `http://127.0.0.1:11434/v1`) + Custom OpenAI-compatible endpoints
  (e.g. LM Studio) via `azzx ai`.
- Fixed `/add` duplicate-list bug found during testing.

## v10.6.3 — Termux/Android sandbox fix

- Fixed `sandbox.exec` (local backend) on Termux/Android: the 512 MiB
  `RLIMIT_AS` address-space cap in `preexec_fn` made Bionic abort every
  child process with SIGABRT (exit -6) — even `echo hello`. The cap is now
  skipped on Android (detected via `ANDROID_ROOT`/`PREFIX`/build.prop);
  `RLIMIT_CPU` + the wall-clock timeout still apply. Desktop behavior
  unchanged. Added `SandboxAndroidTest` regression tests.

## v10.6.2 — auditor + compressor

### Auditor agent (`azzx audit`)
- Every tool call through `run_tool_call` is now recorded (tool, redacted
  args, duration, outcome) to `agent/audit/audit.jsonl` — the auditor only
  observes, never blocks. `AutonomousRunner` and `webauto` group calls under
  run ids (`azzx audit report --run <id>`).
- `azzx audit list|stats` — what happened, success rates, worst tools.
- `azzx audit report --run <id>` — rule-based findings: repeated failures,
  permission denials, high-risk tools, slow calls, timeouts; rule score 0-100.
- `azzx audit report --run <id> --judge` — an LLM judge grades the run
  against its goal (score, verdict, issues, suggestions).

### Token compressor (`azzx compress`)
- `azzx compress <file> [--budget N] [--strategy auto|signatures|extractive|
  head_tail|summarize] [--query ...]` — shrink big files before they enter
  AI context, with stats (chars/tokens before→after, ratio, strategy used).
- `signatures`: AST-based Python condensing (signatures + docstrings only,
  70-90% savings); `extractive`: query-focused line selection; `head_tail`;
  `summarize`: LLM summary for prose.
- `azzx ask` now uses smart compression instead of crude truncation when
  files exceed the context budget. Agent tool: `context.compress`.

## v10.6.1 — patch

- Fix README install instructions: `pip install ./azzx` was wrong (no
  packaging metadata exists) — the real install is `bash install.sh`
  (venv + deps + `azzx` launcher), with a manual venv alternative documented.
- Fix README version badge (was stuck on 10.5.0).
- Audit fixes: monotonic todo IDs after clear, defensive learning-distill
  importance parsing, honest checkpoint rollback semantics (overlay +
  pre-rollback safety checkpoint), Telegram `/auto` plan preview + `/autoy`
  confirm (no `input()` hang on headless gateways), SMTP port 465 support,
  GUI auto-run list capped at 50, `/clear` actually clears chat history,
  `azzx setup --name/--language/--timezone/--notes` flags, missing
  `webagent`/`cronutil` package exports.

## v10.6.0 — "Connected"

### GUI
- `azzx gui` — friendly ChatGPT/Muse-like web chat UI (single HTML file, no
  build step, no CDN — works offline on low-end machines). Sidebar with quick
  actions, streaming responses via SSE (`/api/chat/stream`), autonomous runs
  via `/api/auto`. Stdlib `http.server` only, localhost by default.

### Web reader + autonomous browsing (browser-lite)
- `azzx browse fetch|links <url>`, `azzx browse search "<q>"`, and `web.fetch` /
  `web.links` / `web.search` agent tools — httpx + stdlib HTML parsing, SSRF
  guard refuses non-public hosts.
- `azzx webauto "<task>"` — goal-driven browsing loop that solves by itself:
  searches, opens pages, follows links (only URLs actually on the page;
  hallucinated URLs are blocked), answers when it finds what it needs.
  Read-only; `--start-url`, `--max-steps`.
- Honest limit: no JavaScript rendering (Playwright would cost ~300 MB + RAM
  and break the lightweight promise).

### Connectors
- `azzx connector setup|list|remove` + framework in `azzx/agent/connectors.py`
  (config in `connectors.json`, secrets in the vault).
- GitHub via personal access token: `github.repos`, `github.list_issues`,
  `github.create_issue` tools (permission `connector.github`).
- Email via stdlib IMAP/SMTP: `email.inbox`, `email.send` tools
  (permission `connector.email`). No new dependencies.
- Google Drive deliberately deferred: needs a Google Cloud OAuth2 app.

## v10.5.0 — "Autonomous Companion"

Closes the agent-capability gap with Hermes (Nous Research) — see
`docs/HERMES_FEATURE_GAP_ID.md` for the honest feature-by-feature accounting
(what was matched, what was deliberately deferred, and why).

### Autonomous agent core
- `azzx auto "<goal>"` — plan → approve → execute → learn. Steps run through
  the permission-enforcing registry (deny-first stays absolute); high-risk
  steps are checkpointed automatically; one replan on failure; learnings are
  staged for review, never applied silently.
- `azzx plan "<goal>" [--execute]` — explicit tool-grounded plans saved to
  `.azzx/plans/`; `--execute` runs them through the autonomy runner.
- `todo.add/list/done/clear` tools so the agent tracks its own checklist.

### Learning loop
- `azzx/agent/learning.py` + `azzx learn list|approve|discard` — post-task
  distillation into staged memory/skill proposals. Secrets refused at the gate;
  skill drafts install untrusted + disabled (trust-gate preserved).

### Sandbox
- `azzx exec run -- <cmd>` (+ `--backend local|docker`, `--timeout`,
  `--allow-network`) and the `sandbox.exec` agent tool — cwd jail, timeout,
  output cap, secret-scrubbed env, RLIMIT guards on POSIX; Docker backend with
  `--network none` and 512 MB for real isolation.

### Checkpoints
- `azzx checkpoint create|list|rollback|prune` — tarball snapshots with
  manifests; no git dependency (works on Termux); archives are
  path-traversal-checked on restore.

### Companion
- `azzx setup` — first-run profile (name, language, timezone, notes), local only.
- `azzx chat` — interactive REPL with companion persona, streaming, memory
  context, and slash commands (`/plan /auto /agent /learn /remember /memory
  /skills /trace /clear /quit`).
- `azzx gateway telegram` — minimal Telegram bot gateway (httpx long-polling,
  no new deps) with `--allow-from` chat allowlist and `/auto /plan /remember`.

### Scheduling, skills, sessions, MCP
- `azzx schedule add --cron "*/5 * * * *"` — cron expressions via a
  dependency-free parser (`azzx/agent/cronutil.py`).
- `azzx skills install <git-url>` — shallow-clone + manifest validation.
- `azzx session search "<q>"` — LIKE-based search over the session journal.
- `mcp.call` tool exposes AZZX's existing MCP client to the agent
  (permission `mcp.execute`); the pre-existing `azzx mcp` CLI is unchanged.
- `azzx doctor` gains disk + memory rows (existing command, extended).

### Docs
- README.md + README_ID.md rewritten: task-oriented, every command with an
  example. `docs/HERMES_FEATURE_GAP_ID.md` documents the Hermes comparison.

### Lightweight promise
- Zero new required dependencies (still `httpx` + `rich` only); lazy imports
  throughout; new modules degrade gracefully without `rich`.

## v10.4.0 — Unified native agent (no separate modes)

**Design correction:** the separate `azzx hermes` mode/product is removed.
All advanced agent capabilities are now native parts of AZZX's existing
architecture and normal workflows — one unified agent. `azzx hermes`
prints a migration table (`hermes think` → `azzx agent`, `hermes memory` →
`azzx recall`, `hermes trace` → `azzx trace`, `hermes queue` → `azzx queue`,
`hermes schedule` → `azzx schedule`, `hermes stream` → `azzx ask --stream`).
Dashboard `/api/hermes/*` renamed to `/api/agent/*`. `HERMES_COMPARISON.md`
deleted.

### AI orchestration (`azzx/agent/providers.py`)
- Provider layer extracted from the CLI monolith into a native module
  (`azzx_cli` re-exports for backwards compatibility).
- Typed error taxonomy: authentication, rate limit, timeout, malformed
  response, provider outage, misconfiguration — each with an actionable hint.
- Bounded retries with exponential backoff + jitter for retryable errors
  (never infinite); non-retryable errors fail over immediately.
- Cooperative cancellation via `threading.Event` (between attempts + streaming).
- `MockAdapter` for deterministic offline tests. API keys never logged.

### Multi-agent (`azzx agent`)
- Roles planner/researcher/coder/reviewer/tester/security now delegate to the
  **configured AI provider** — the hardcoded canned responses are gone.
- Each role has a role prompt, a tool allowlist, and returns a structured
  result (summary/findings/actions/tool_requests/needs) chained to the next agent.
- Orchestrator executes allowed tool requests through the permission-enforcing
  registry; disallowed tools are refused visibly. One follow-up round max.
- Sequential by default; `--parallel` only for read-only roles; `--fail-fast`;
  provider failures are reported per agent, never hidden. `azzx agent --roles`.

### Memory (`azzx recall`)
- Exact-duplicate suppression (content hash); secrets refused at write time
  (API keys, tokens, private keys, credential assignments) without echoing values.
- Shared/private boundaries enforced in search; project scoping; importance
  clamped to [0,1]; validated memory types; schema migration for old DBs.
- `delete()` removes semantic vectors too; `rebuild` re-embeds from scratch;
  `stats` reports index health (`verify_index`/`purge_orphan_vectors`).

### Tasks (`azzx queue`) and sessions (`azzx session`)
- New states: `cancelled`, `interrupted` (owner died — never silently re-run;
  deliberate `queue resume` after checking side effects).
- Background tool runs are approval-gated: non-`allow` permissions need `-y`
  at submit; state files are mode 0600; malformed owners can't crash claims;
  in-process worker never double-runs a drainer-claimed task; `queue result
  --wait` refreshes across processes.
- Sessions: `end` (done/abandoned/failed), `resume` (restores snapshot +
  events + project context), `stale` (find interrupted sessions).

### Skills (`azzx skills`)
- Native skill registry: validated `skill.json` (id, semver, input schema,
  handler, permissions), argument validation, trust-gated lifecycle
  (install → trust → enable → invoke). Third-party code never runs untrusted.
- Enabled skills exposed as `skill.<id>` tools through the same permission
  checks (queue/workflows included). Example: `examples/sample-skill/`.

### Security
- `deny` is now absolute: `force_yes`/`-y`/workflows/queue can no longer
  bypass an explicit deny (regression-tested).
- Tracer redacts secret-looking keys in span attributes/events; trace log is
  mode 0600. Scheduler state is mode 0600.

### Compatibility
- `azzx.core.detect_runtime()` probes OS/distro/Termux/systemd/sudo/package
  manager without assuming any of them exist.
- `install.sh --check` covers Termux detection (unchanged).

## v10.3.0 — Queue reliability and persistent tool scheduling

- Fixed task submission race by persisting tasks before workers can consume them.
- Synchronized terminal task status with durable state writes so polling cannot observe completion before persistence.
- Replaced shared `.tmp` queue snapshots with unique, fsynced temporary files and atomic replacement.
- Merged state snapshots without regressing a detached worker's active/terminal task state.
- Hardened stale/malformed PID recovery.
- Added `azzx hermes schedule list|add|remove|run-due`, a persistent interval scheduler limited to registered tools.
- Added regression coverage for fast task execution and schedule lifecycle.
- Added GitHub Actions offline test workflow and contributor guidance.


## v10.2.0 — Hermes-like agent features

### Semantic memory
- New `azzx/agent/embeddings.py`: pure-stdlib incremental TF-IDF embedder
  (no numpy/ML deps, Termux-friendly) with cosine similarity
- `MemoryStore` now embeds every memory on write (`memory_vectors` table);
  new `search_semantic()`, `search_hybrid()` (keyword + semantic), and
  `rebuild_vectors()` for re-embedding after bulk imports
- `assemble_memory_prompt()` uses hybrid recall by default

### Chain-of-thought reasoning
- New `azzx/agent/reasoning.py`: `ReasoningTrace` with explicit
  thought → plan → act → observe → reflect → conclusion steps,
  renderable in terminal or dashboard
- `MultiAgentOrchestrator.delegate()` now builds a reasoning trace for every
  delegation; `run_task()` routes through `delegate()` so the whole pipeline
  is reasoned and traced

### Observability
- New `azzx/agent/tracer.py`: nested spans (task/tool/agent/memory), timing,
  error capture, JSONL timeline persisted under `~/.azzx/agent/trace.jsonl`
- Tool execution via `run_tool_call()` is traced; new CLI `azzx hermes trace`
  and dashboard endpoint `/api/hermes/timeline`

### Async task queue
- New `azzx/agent/tasks.py`: FIFO background queue with daemon worker,
  `submit_tool()`/`submit()`, `status()`/`result()`/`list_tasks()`,
  JSON state that survives restarts
- CLI: `azzx hermes queue submit|list|status|result`; dashboard `/api/hermes/queue`

### Token streaming
- `BaseAdapter.stream_chat()` (single-chunk fallback) and real SSE streaming
  in `OpenAICompatibleAdapter`; `AIRouter.stream()` with provider fallback
- CLI: `azzx ask --stream`, `azzx hermes stream`; `TokenStream` accumulator

### Multimodal (vision)
- New `azzx/agent/vision.py`: image → base64 data-URL, `is_vision_model()`
  heuristic, OpenAI-style multimodal content builder
- CLI: `azzx ask --image foto.png` / `azzx hermes stream --image ...`
  (warns gracefully when the active model is not vision-capable)

### Dashboard
- New read endpoints: `/api/hermes/timeline`, `/api/hermes/queue`,
  `/api/hermes/memory?q=`

## v10.1.0

### Agent layer reconstruction
- Reconstructed the intended v10.1 agent modules from the damaged Phase-1 commit:
  new `azzx/agent/memory.py` (SQLite memory + `get_memory_store`), new
  `azzx/agent/streaming.py` (`StreamEvent`/`AgentStream`), restored
  `azzx/agent/message_bus.py`, new `azzx/agent/__init__.py` exports
- `multi_agent.py`: `AgentProfile` personas, `delegate()`/`collaborate()` with
  message-bus integration
- `orchestrator.py`: added `get_message_bus()` and `stream_multi_agent_task()`;
  fixed infinite recursion in the drafted `get_memory_store()`/`get_message_bus()`
- Fixed import-time side effects: global singletons (memory store, session
  journal, multi-agent orchestrator) are now created lazily — importing
  `azzx.agent` no longer writes to the filesystem
- SQLite connections always closed via try/finally (no more leaked locks)
- `datetime.utcnow()` replaced with timezone-aware `now(timezone.utc)`

### Permission & tool fixes
- Removed double permission prompts: `ToolRegistry.call()` is now the single
  enforcement point (archive, media, network, system handlers no longer
  re-ask for the same capability)
- `json.format`/`json.validate`: non-UTF-8 files now produce clean errors
  instead of raw `UnicodeDecodeError`
- tar extraction on Python <3.12: symlink/hardlink members are now rejected
  explicitly in the no-filter fallback

### Tests & packaging
- Fixed stale `test_core.py` version assertion (now tracks `VERSION`)
- `selftest.sh`: version check reads the `VERSION` file and matches the
  installer's `vX.Y.Z` banner format
- Bumped version to 10.1.0 everywhere (`VERSION`, package, CLI, installer)

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

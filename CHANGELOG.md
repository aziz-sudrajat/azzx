# Changelog

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

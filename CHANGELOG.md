# Changelog

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

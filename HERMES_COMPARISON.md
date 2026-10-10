# AZZX vs Hermes Agent — Capability Snapshot

> Updated for AZZX 10.3.0. This is a project-local engineering comparison, not a claim of feature parity. Verify current Hermes capabilities against its official documentation before making release decisions.

## Current AZZX capabilities

| Area | Status in AZZX 10.3.0 | Notes / limitations |
|---|---|---|
| Coding and engineering CLI | Implemented | Commands for review, debug, tests, Git, release, sandbox and project workflows. Results depend on configured provider/tool support. |
| Registered tool system | Implemented | Central registry and capability permission checks. Keep untrusted plugins disabled until reviewed. |
| Multi-agent roles | Implemented, lightweight | Role-based delegation exists; it is not proof of independent agents or guaranteed better reasoning. |
| Persistent memory | Implemented | SQLite store with keyword + lightweight TF-IDF retrieval; not neural embeddings. |
| Session journal/message bus | Implemented | Local persistence and inter-agent messaging primitives. |
| Task queue | Implemented and hardened | In-process queue plus detached registered-tool drainer. Callable tasks are process-local and cannot be resumed in a separate process. |
| Interval scheduler | New in 10.3.0 | Persistent registered-tool jobs, run once via `run-due`; requires cron/systemd or manual invocation. Not a resident daemon. |
| Streaming | Partial | OpenAI-compatible SSE parser and provider fallback; actual streaming behavior depends on provider endpoint. |
| Vision | Partial | Image encoding and request construction exist; live vision support depends on model/provider. |
| Tracing | Implemented, lightweight | Local JSONL spans/timeline; not a full distributed tracing system. |
| Plugins and MCP | Implemented with caveats | Manifest validation and integrations exist; plugins remain executable code and must be treated as trusted software. |
| Universal system toolkit | Implemented | Files, archive, JSON, media, network, system and device tools; actual OS package installation is not covered by unit tests. |
| Web/voice/messaging/API service | Not established as feature parity | Do not claim parity with Hermes for browser automation, voice, messaging gateways, always-on services or advanced runtime backends without a separate implementation and tests. |

## Architecture

```text
CLI / Dashboard
      ↓
Agent orchestration + persistent memory + trace
      ↓
Permission-aware registered tool registry
      ↓
Local OS / project files / Android device / external provider
```

## v10.3.0 reliability changes

- Persist a submitted task before a worker can consume it.
- Synchronize terminal status with the final durable snapshot.
- Use unique temporary files, `fsync`, and atomic replacement for queue state.
- Avoid stale snapshots regressing detached worker state.
- Recover safely from malformed/stale PID values.
- Add a persistent scheduler that calls registered tools only.
- Add offline regression tests and GitHub Actions CI.

## Roadmap

1. **10.3.x — Reliability/security:** cross-process queue stress tests, scheduler concurrency tests, permission auditing, plugin isolation guidance, secret-redaction tests and dashboard bind-scope review.
2. **10.4 — Bounded agent loop:** explicit plan → tool call → observation → stop criteria, iteration/tool budgets, cancellation, and deterministic mock-provider tests. No hidden/unbounded autonomy.
3. **10.5 — Memory quality:** memory retention/deletion controls, provenance, deduplication, session summaries and retrieval evaluation. Keep TF-IDF labeled accurately unless a real embedding provider is integrated.
4. **10.6 — Integrations:** tested provider adapters, safe browser/search integration where configured, robust retries and rate-limit handling.
5. **10.7 — Skills:** versioned skill manifests, explicit trust/permissions, install/update/rollback and reproducible tests.
6. **10.8 — Multimodal:** verify image requests against actual provider APIs and add document/image fixtures without committing sensitive data.
7. **10.9 — Plugins/runtime:** compatibility checks, signature/hash metadata, isolated execution options and a plugin security checklist.
8. **11.0 — Unified agent:** integrate the proven features behind a consistent CLI, API and dashboard contract; publish a capability matrix and test coverage.

## Release gates

- Offline tests pass on supported Python versions.
- No API keys or personal data in source, fixtures, logs or release artifacts.
- Queue/scheduler concurrency and crash recovery are tested.
- Permissions are checked for every mutating tool path.
- Installer smoke tests run in clean Termux/Linux environments before claiming broad distro support.
- Live provider tests are opt-in and use user-supplied credentials; never required for CI.

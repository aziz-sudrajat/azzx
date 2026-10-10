# AZZX v10.4.0 — Audit Report

Date: 2026-10-10
Baseline: v10.3.0 (`AZZX_v10_SOURCE_2_9j8g.zip`)
Result: v10.4.0 — "Unified native agent"

This report covers the full Stage A–L handover: inspection findings, what was
changed, security improvements, test results, and known limitations.

---

## 1. Critical findings (fixed)

### 1.1 Multi-agent collaboration was simulated, not real — FIXED
`MultiAgentOrchestrator._generate_agent_output()` returned **hardcoded canned
strings per role**. No AI provider was ever called; "collaboration" was five
static paragraphs. Every delegation now calls the configured AI provider with
a role-specific system prompt, memory context, and tool contract, returning a
structured, chained result. If no provider is configured the command fails
with an actionable message instead of pretending.

### 1.2 Separate `azzx hermes` mode — REMOVED (per user correction)
v10.2/10.3 shipped a parallel `azzx hermes {think,memory,trace,queue,stream}`
surface plus `/api/hermes/*` dashboard endpoints and `HERMES_COMPARISON.md`.
All capabilities are now native: `azzx agent`, `azzx queue`, `azzx schedule`,
`azzx recall`, `azzx trace`, `azzx session`, `azzx skills`. `azzx hermes`
prints a migration table (exit 2). No second CLI, no competing subsystem.

### 1.3 `force_yes` bypassed `deny` — FIXED (security)
`require_permission()` evaluated `force_yes` *before* the deny check, so `-y`,
workflows, and background workers could override an explicit `deny` policy
(e.g. `git.push`, `release.publish`). Deny is now absolute and evaluated
first. Regression-tested through direct calls and the workflow engine.

### 1.4 Provider layer trapped in the CLI monolith — FIXED
`BaseAdapter`/`AIRouter`/etc. lived inside the 6000-line `azzx_cli.py`, so the
agent layer could not use the configured provider without importing the CLI
script. Extracted to `azzx/agent/providers.py`; `azzx_cli` re-exports the
names for backwards compatibility (existing `from azzx_cli import ...`
imports keep working).

### 1.5 Flat provider errors, no retries, no cancellation — FIXED
One `ProviderError` for everything; no retries; no cancellation. Now: typed
taxonomy (`AuthenticationError`, `RateLimitError`, `ProviderTimeoutError`,
`MalformedResponseError`, `ProviderOutageError`, `ProviderConfigError`) each
with an actionable hint; bounded retries (default 2) with exponential
backoff+jitter for retryable errors only; cooperative cancellation via
`threading.Event`.

## 2. Other findings (fixed)

| # | Finding | Fix |
|---|---|---|
| 2.1 | Memory stored exact duplicates indefinitely | Content-hash dedup; `store()` returns the existing id |
| 2.2 | Memory accepted API keys / private keys silently | Secret-pattern scan refuses storage without echoing values |
| 2.3 | `shared` flag existed but search ignored the boundary | Visibility clause: own memories always; others' only if shared (explicit `include_private` override) |
| 2.4 | No project scoping in memory | `project` column + filters (with migration for old DBs) |
| 2.5 | `delete()` left orphan vectors; `rebuild_vectors()` didn't reset | Delete removes vectors; rebuild drops + refits the index; `verify_index()`/`purge_orphan_vectors()` |
| 2.6 | Task queue: no cancel/interrupted states | `cancel()`, `interrupted` (owner died), deliberate `resume_task()` — never silently re-runs side effects |
| 2.7 | Background tool tasks ignored approval UX | `approved` flag at submit (`-y`); otherwise a clear error naming the capability |
| 2.8 | In-process worker could double-run drainer-claimed tasks | Pre-execution claim check under the file lock |
| 2.9 | `_claim_next` crashed on malformed owner (`int(owner)`) | Safe PID check everywhere |
| 2.10 | Queue/scheduler/trace state files world-readable | Mode 0600 on all agent state files |
| 2.11 | Tracer logged raw tool args (secret leak into `trace.jsonl`) | Key-based redaction of credential-like attributes/events |
| 2.12 | Session journal: no end/resume/stale; event order ties | `end_session`, `resume_session` (bundle), `find_stale`, `id`-tiebroken ordering |
| 2.13 | No native skill registry (raw plugins only, unvalidated) | `azzx/agent/skills.py`: manifest+schema validation, trust-gated lifecycle, `skill.<id>` tool exposure |
| 2.14 | `queue result --wait` polled a stale in-memory snapshot | Cross-process refresh from disk |
| 2.15 | `azzx agent --roles` triggered the interactive AI setup wizard | Wizard only for commands that actually need a provider |
| 2.16 | No central runtime detection | `azzx.core.detect_runtime()` (OS/distro/Termux/systemd/sudo/package manager probes) |

## 3. Files changed / added

**New:** `azzx/agent/providers.py`, `azzx/agent/skills.py`, `tests/test_native.py`
(61 tests), `examples/sample-skill/`, `AUDIT_REPORT.md`, `GITHUB_PUSH_GUIDE.md`.

**Rewritten:** `azzx/agent/multi_agent.py` (real delegation), `azzx/agent/memory.py`,
`azzx/agent/tasks.py`, `azzx/cli_v10.py` (native command handlers).

**Modified:** `azzx_cli.py` (provider import; parser: removed `hermes`, added
`agent/queue/schedule/recall/trace/session/skills`; dashboard `/api/agent/*`;
needs-ai gating), `azzx/agent/__init__.py`, `orchestrator.py` (skill tool
registration), `session.py`, `scheduler.py` (0600), `tracer.py` (redaction,
0600), `core.py` (deny-first, `detect_runtime`), `tests/test_native.py`
(replaces `test_hermes.py`), `selftest.sh`, `.github/workflows/ci.yml`,
`README.md`, `README_ID.md`, `CHANGELOG.md`, `VERSION`/package/CLI/installer
→ 10.4.0.

**Deleted:** `HERMES_COMPARISON.md`, `tests/test_hermes.py`.

## 4. Security improvements

- Deny-first permission evaluation (see 1.3).
- Secret redaction in traces; 0600 agent state files.
- Memory refuses secret-looking content.
- Skill trust gate: installed skills are untrusted+disabled; enabling
  requires explicit trust; args schema-validated; permissions enforced.
- Background tasks never prompt; approval recorded at submit.
- Interrupted tasks never auto-rerun.
- No new network listeners; no elevated privileges; no vendored secrets.

## 5. Test results

| Suite | Result |
|---|---|
| `python -m py_compile` (all sources) | PASS |
| `unittest discover` — 108 tests (test_core, test_v10, test_native) | **108 passed** |
| `tests/integration_mock_ai.py` (local mock provider server) | PASS |
| `selftest.sh` (7 steps: compile, CLI parser, shell syntax, unit, mock AI, secret grep) | PASS |
| CLI smoke (`agent --roles`, `queue`, `schedule`, `recall`, `trace`, `session`, `skills`, `hermes` migration) | PASS |

Environment note: the sandbox exports proxy variables (including bracketed-IPv6
`no_proxy` entries) that break httpx's localhost connections in
`integration_mock_ai.py` — a pre-existing environment quirk, not repo logic.
`selftest.sh` and CI unset proxy vars for that step only.

## 6. Known limitations

1. Cancelling an in-flight non-streaming HTTP call relies on the provider
   timeout (httpx has no mid-request abort); the cancel event is honored
   between attempts and during streaming.
2. Skill handlers run in-process (no sandbox); the trust gate is the control.
3. `fcntl` locks are Linux/Termux-only; other OSes untested (not targeted).
4. Parallel multi-agent fan-out is restricted to read-only roles by design.
5. Installer tested via `--check` (incl. Termux simulation), not on real
   Termux/Arch/Debian hardware in this environment.
6. `azzx agent` requires a configured AI provider (`azzx ai`); without one it
   errors clearly rather than simulating.

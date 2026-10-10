"""Auditor agent for AZZX (v10.6.1): record everything, judge correctness.

Every tool call flowing through ``orchestrator.run_tool_call`` is recorded:
tool name, redacted args, duration, outcome (ok / error / denied). The audit
log lives at ``DATA_HOME/agent/audit/audit.jsonl`` (0600, append-only).

``azzx audit`` answers "did the agent do it right?":
- ``list`` / ``stats`` — what happened, success rates, top failures
- ``report --run <id>`` — rule-based findings for one run:
  repeated failures, permission denials, high-risk tools, slow calls
- ``report --run <id> --judge`` — an LLM judge grades the run against its
  goal and returns a score + verdict + issues + suggestions

Runs are grouped by an explicit run id: ``AutonomousRunner`` and ``webauto``
set one via ``start_run()``; ad-hoc tool calls are logged under "adhoc".
The auditor never blocks or changes tool execution — it only observes.
"""
from __future__ import annotations

import contextlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from azzx.core import DATA_HOME

AUDIT_DIR = Path(DATA_HOME) / "agent" / "audit"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"
MAX_FILE_BYTES = 10 * 1024 * 1024  # rotate at 10 MiB

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|private[_-]?key|credential|"
    r"auth|bearer|session|cookie)", re.IGNORECASE)

_local = threading.local()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_run(goal: str = "") -> str:
    """Begin grouping subsequent tool calls under a run id. Returns the id."""
    import uuid
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    _local.run_id = run_id
    _local.run_goal = (goal or "")[:200]
    _append({"ts": _utcnow(), "kind": "run_start", "run_id": run_id,
             "goal": _local.run_goal})
    return run_id


def current_run_id() -> str:
    return getattr(_local, "run_id", "adhoc")


def end_run(status: str = "") -> None:
    run_id = current_run_id()
    _append({"ts": _utcnow(), "kind": "run_end", "run_id": run_id,
             "status": status[:40]})
    _local.run_id = "adhoc"
    _local.run_goal = ""


def _redact_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        ks = str(k)
        if _SECRET_KEY_RE.search(ks):
            out[ks] = "[redacted]"
            continue
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        out[ks] = s if len(s) <= 300 else s[:300] + f"…[{len(s) - 300} chars cut]"
    return out


def _append(entry: dict[str, Any]) -> None:
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        if AUDIT_FILE.exists() and AUDIT_FILE.stat().st_size > MAX_FILE_BYTES:
            AUDIT_FILE.rename(AUDIT_DIR / f"audit-{int(time.time())}.jsonl")
        with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        try:
            AUDIT_FILE.chmod(0o600)
        except Exception:
            pass
    except Exception:
        pass  # auditing must never break the agent


@contextlib.contextmanager
def audit_call(tool: str, args: dict[str, Any]) -> Iterator[None]:
    """Context manager: record one tool call. Never raises."""
    start = time.monotonic()
    outcome: dict[str, Any] = {"ok": True}
    try:
        yield
    except Exception as exc:
        outcome = {"ok": False, "error_kind": _classify_error(exc),
                   "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        raise
    finally:
        try:
            _append({
                "ts": _utcnow(), "kind": "tool_call",
                "run_id": current_run_id(), "tool": tool,
                "args": _redact_args(args),
                "duration_ms": int((time.monotonic() - start) * 1000),
                **outcome,
            })
        except Exception:
            pass


def log_custom(tool: str, ok: bool = True, detail: str = "",
               duration_ms: int = 0) -> None:
    """Manually record a non-registry action (e.g. webauto page visits)."""
    _append({
        "ts": _utcnow(), "kind": "tool_call", "run_id": current_run_id(),
        "tool": tool, "args": {"detail": detail[:300]},
        "duration_ms": duration_ms, "ok": ok,
    })


def _classify_error(exc: BaseException) -> str:
    name = type(exc).__name__
    msg = str(exc).lower()
    if "permissiondenied" in name or "denied" in msg or "not allowed" in msg:
        return "denied"
    if "timeout" in name.lower() or "timed out" in msg:
        return "timeout"
    if "not found" in msg or "no such" in msg:
        return "not_found"
    if "azzxerror" in name:
        return "azzx_error"
    return "error"


def _iter_entries() -> Iterator[dict[str, Any]]:
    if not AUDIT_FILE.is_file():
        return
    try:
        with open(AUDIT_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return


def recent_calls(limit: int = 30, run_id: str = "") -> list[dict[str, Any]]:
    out = [e for e in _iter_entries()
           if e.get("kind") == "tool_call" and (not run_id or e.get("run_id") == run_id)]
    return out[-max(1, limit):]


def stats() -> dict[str, Any]:
    calls = [e for e in _iter_entries() if e.get("kind") == "tool_call"]
    total = len(calls)
    ok = sum(1 for c in calls if c.get("ok"))
    by_tool: dict[str, dict[str, int]] = {}
    by_error: dict[str, int] = {}
    denied = 0
    total_ms = 0
    for c in calls:
        t = by_tool.setdefault(str(c.get("tool")), {"calls": 0, "ok": 0})
        t["calls"] += 1
        if c.get("ok"):
            t["ok"] += 1
        else:
            ek = str(c.get("error_kind", "error"))
            by_error[ek] = by_error.get(ek, 0) + 1
            if ek == "denied":
                denied += 1
        total_ms += int(c.get("duration_ms", 0) or 0)
    worst = sorted(by_tool.items(), key=lambda kv: kv[1]["calls"] - kv[1]["ok"],
                   reverse=True)[:5]
    return {
        "total_calls": total,
        "success_rate": round(ok / total, 3) if total else 1.0,
        "denied": denied,
        "avg_duration_ms": int(total_ms / total) if total else 0,
        "by_error": by_error,
        "worst_tools": [{"tool": k, **v} for k, v in worst if v["calls"] > v["ok"]],
    }


def report(run_id: str) -> dict[str, Any]:
    """Rule-based audit report for one run. No LLM needed."""
    calls = recent_calls(limit=10000, run_id=run_id)
    if not calls:
        from azzx.core import AzzxError
        raise AzzxError(f"no audit entries for run: {run_id}")
    total = len(calls)
    failed = [c for c in calls if not c.get("ok")]
    findings: list[str] = []

    # Repeated failures of the same tool.
    fails_by_tool: dict[str, int] = {}
    for c in failed:
        fails_by_tool[c["tool"]] = fails_by_tool.get(c["tool"], 0) + 1
    for tool, n in sorted(fails_by_tool.items(), key=lambda kv: -kv[1]):
        if n >= 3:
            findings.append(f"REPEATED FAILURE: '{tool}' failed {n}x — "
                            "the agent may be repeating a wrong approach.")

    denied = [c for c in failed if c.get("error_kind") == "denied"]
    if denied:
        tools = sorted({c["tool"] for c in denied})
        findings.append(f"PERMISSION DENIALS: {len(denied)} denied call(s) "
                        f"({', '.join(tools)}) — the agent tried capabilities it may not use.")

    risky = {"filesystem.write", "filesystem.delete", "sandbox.exec", "sys.service"}
    used_risky = sorted({c["tool"] for c in calls if c["tool"] in risky})
    if used_risky:
        findings.append(f"HIGH-RISK TOOLS USED: {', '.join(used_risky)}.")

    slow = [c for c in calls if int(c.get("duration_ms", 0) or 0) > 30_000]
    if slow:
        findings.append(f"SLOW CALLS: {len(slow)} call(s) took >30s "
                        f"({', '.join(sorted({c['tool'] for c in slow}))}).")

    timeouts = [c for c in failed if c.get("error_kind") == "timeout"]
    if timeouts:
        findings.append(f"TIMEOUTS: {len(timeouts)} call(s) timed out.")

    score = 100
    score -= min(40, len(failed) * 8)
    score -= min(20, len(denied) * 10)
    score = max(0, score)
    verdict = "pass" if score >= 80 else ("needs_work" if score >= 50 else "fail")

    return {
        "run_id": run_id,
        "calls": total,
        "ok": total - len(failed),
        "failed": len(failed),
        "success_rate": round((total - len(failed)) / total, 3),
        "rule_score": score,
        "rule_verdict": verdict,
        "findings": findings,
        "failures": [{"tool": c["tool"], "error_kind": c.get("error_kind"),
                      "error": c.get("error", "")[:160]} for c in failed[:10]],
    }


_JUDGE_CONTRACT = """You are an auditor grading an AI agent's work.
Given the GOAL and the tool-call TRANSCRIPT, reply with JSON ONLY:
{"score": 0-100, "verdict": "pass|needs_work|fail",
 "did_it_right": true|false,
 "issues": ["concrete problem 1"],
 "suggestions": ["concrete fix 1"]}
Be strict but fair: a working outcome with minor inefficiency is "pass".
Mark "fail" only if the goal was not achieved or the agent acted unsafely."""


def judge(run_id: str, goal: str = "") -> dict[str, Any]:
    """LLM judge: grade a run against its goal. Needs a configured provider."""
    from azzx.agent.providers import default_router

    calls = recent_calls(limit=200, run_id=run_id)
    if not calls:
        from azzx.core import AzzxError
        raise AzzxError(f"no audit entries for run: {run_id}")
    lines = []
    for c in calls:
        status = "OK" if c.get("ok") else f"FAIL({c.get('error_kind')})"
        argstr = ", ".join(f"{k}={v}" for k, v in (c.get("args") or {}).items())[:120]
        lines.append(f"- {c['tool']}({argstr}) -> {status}")
    router = default_router()
    try:
        raw = router.chat([
            {"role": "system", "content": _JUDGE_CONTRACT},
            {"role": "user", "content":
             f"GOAL: {goal or '(unknown)'}\n\nTRANSCRIPT:\n" + "\n".join(lines[:150])},
        ], max_tokens=800).text.strip()
    except Exception as exc:
        from azzx.core import AzzxError
        raise AzzxError(f"judge needs an AI provider: {exc}")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        from azzx.core import AzzxError
        raise AzzxError("judge returned unparseable output")
    try:
        data = json.loads(m.group(0))
    except Exception:
        from azzx.core import AzzxError
        raise AzzxError("judge returned invalid JSON")
    data["run_id"] = run_id
    return data

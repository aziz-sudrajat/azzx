"""Autonomous task execution for AZZX (v10.5): plan -> approve -> execute -> learn.

``AutonomousRunner.run()``:
  1. generates an explicit tool-grounded plan (``planning.generate_plan``),
  2. asks for approval unless ``auto_approve`` (``-y``),
  3. executes steps sequentially through ``run_tool_call`` — the same
     permission-enforcing entry point as everything else, so ``deny`` stays
     absolute and background-style runs never silently bypass policy,
  4. snapshots a checkpoint before high-risk steps,
  5. replans once if a step fails,
  6. distills learnings into staged proposals (``learning.distill``).

Guardrails: bounded steps, per-run todo tracking, cooperative cancellation,
no hidden prompts in non-interactive mode (missing approvals fail loudly).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from azzx.core import AzzxError

RISKY_TOOLS = {"filesystem.write", "filesystem.delete", "sandbox.exec", "sys.service"}


class AutonomousRunner:
    def __init__(
        self,
        workdir: str = ".",
        max_steps: int = 25,
        auto_approve: bool = False,
        forced_provider: str | None = None,
        namespace: str = "auto",
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.workdir = str(Path(workdir or ".").expanduser().resolve())
        self.max_steps = max(1, min(int(max_steps or 25), 100))
        self.auto_approve = bool(auto_approve)
        self.forced_provider = forced_provider
        self.namespace = namespace
        self.on_event = on_event
        self.cancel_event = threading.Event()

    def _emit(self, kind: str, **fields: Any) -> None:
        if self.on_event:
            try:
                self.on_event({"kind": kind, **fields})
            except Exception:
                pass

    def cancel(self) -> None:
        self.cancel_event.set()

    # -- main ----------------------------------------------------------
    def run(self, goal: str, context: str = "") -> dict[str, Any]:
        from azzx.agent import planning
        from azzx.agent import checkpoints
        from azzx.agent import learning
        from azzx.agent import auditor
        from azzx.agent.orchestrator import run_tool_call
        from azzx.agent.tracer import get_tracer

        goal = (goal or "").strip()
        if not goal:
            raise AzzxError("auto needs a goal")
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        tracer = get_tracer()
        todos = planning.get_todo_list(self.namespace)
        transcript: list[str] = []
        checkpoint_ids: list[str] = []
        started = datetime.now(timezone.utc).isoformat()

        run_id = auditor.start_run(goal)
        with tracer.span("auto.run", kind="task", goal=goal[:120]):
            self._emit("plan_start", goal=goal, run_id=run_id)
            plan = planning.generate_plan(
                goal, context=context, project_root=self.workdir,
                forced_provider=self.forced_provider,
                cancel_event=self.cancel_event,
            )
            self._emit("plan_ready", plan=plan)

            if plan.get("needs_clarification") and not self.auto_approve:
                auditor.end_run("needs_clarification")
                return {"status": "needs_clarification", "plan": plan,
                        "run_id": run_id,
                        "questions": plan["needs_clarification"]}

            if not self.auto_approve and not self._ask_approve(plan):
                auditor.end_run("aborted")
                return {"status": "aborted", "plan": plan, "run_id": run_id,
                        "reason": "user did not approve the plan"}

            for s in plan.get("steps", []):
                todos.add(f"[{s['id']}] {s['title']}")

            steps = list(plan.get("steps", []))
            completed, failed = 0, 0
            replanned = False
            idx = 0
            while idx < len(steps) and completed < self.max_steps:
                if self.cancel_event.is_set():
                    transcript.append("CANCELLED by user")
                    break
                step = steps[idx]
                idx += 1
                sid, tool, args = step["id"], step.get("tool", ""), step.get("args") or {}
                self._emit("step_start", step=step)

                if tool == "ask_user":
                    transcript.append(f"{sid}: BLOCKED — {step.get('title')} needs the user")
                    failed += 1
                    break

                # Checkpoint before risky work.
                if (step.get("risk") == "high" or tool in RISKY_TOOLS) and self.workdir:
                    try:
                        cp = checkpoints.create(self.workdir, label=f"auto:{sid}")
                        checkpoint_ids.append(cp["id"])
                        self._emit("checkpoint", id=cp["id"], step=sid)
                    except Exception as exc:
                        transcript.append(f"{sid}: checkpoint failed ({exc}); continuing")

                with tracer.span(f"auto.step:{sid}", kind="tool", tool=tool):
                    try:
                        outcome = run_tool_call(
                            tool, args,
                            noninteractive=self.auto_approve,
                            force_yes=self.auto_approve,
                        )
                        summary = _summarize(outcome)
                        transcript.append(f"{sid} [{tool}] OK: {summary}")
                        self._mark_todo_done(todos, sid)
                        completed += 1
                        self._emit("step_ok", step=step, summary=summary)
                    except Exception as exc:
                        err = f"{type(exc).__name__}: {exc}"
                        transcript.append(f"{sid} [{tool}] FAILED: {err[:300]}")
                        failed += 1
                        self._emit("step_failed", step=step, error=err)
                        if not replanned and idx < len(steps):
                            replanned = True
                            try:
                                steps[idx:] = self._replan(
                                    goal, steps[idx:], step, err, plan)
                                transcript.append("replanned remaining steps after failure")
                                self._emit("replanned")
                                continue
                            except Exception as rexc:
                                transcript.append(f"replan failed: {rexc}")
                        break

            status = "ok" if failed == 0 else ("partial" if completed else "failed")
            learned: dict[str, Any] = {}
            if transcript:
                try:
                    learned = learning.distill(
                        goal, "\n".join(transcript), agent_id="auto",
                        forced_provider=self.forced_provider,
                        cancel_event=self.cancel_event,
                    )
                except Exception as exc:
                    learned = {"error": str(exc)[:200]}

            auditor.end_run(status)
            return {
                "status": status,
                "goal": goal,
                "run_id": run_id,
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "steps_completed": completed,
                "steps_failed": failed,
                "checkpoints": checkpoint_ids,
                "plan_path": plan.get("path"),
                "todos": todos.list(),
                "learned": learned,
                "audit": f"azzx audit report --run {run_id}",
            }

    # -- helpers ---------------------------------------------------------
    def _ask_approve(self, plan: dict[str, Any]) -> bool:
        try:
            from azzx.agent.planning import render_plan_text
            print(render_plan_text(plan))
            ans = input("Execute this plan? [y/N] ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def _mark_todo_done(self, todos: Any, sid: str) -> None:
        try:
            for item in todos.list():
                if sid in item.get("title", "") and not item.get("done"):
                    todos.done(item["id"])
                    break
        except Exception:
            pass

    def _replan(
        self, goal: str, remaining: list[dict[str, Any]],
        failed_step: dict[str, Any], error: str, plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from azzx.agent.providers import default_router

        messages = [
            {"role": "system", "content":
             "You revise a failed plan. Respond with a single JSON object "
             "{\"steps\": [{\"id\":..., \"title\":..., \"tool\":..., \"args\":{}, "
             "\"why\":..., \"risk\":\"low|medium|high\"}]} and nothing else. "
             "Avoid repeating the failed approach."},
            {"role": "user", "content": (
                f"GOAL: {goal}\nFAILED STEP: {json.dumps(failed_step)[:800]}\n"
                f"ERROR: {error[:400]}\n"
                f"REMAINING STEPS: {json.dumps(remaining)[:2000]}\n"
                "Propose revised remaining steps."
            )},
        ]
        router = default_router()
        result = router.chat(messages, forced_provider=self.forced_provider,
                             cancel_event=self.cancel_event, max_tokens=1000)
        import re as _re
        m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result.text or "", _re.DOTALL)
        blob = m.group(1) if m else (result.text or "")
        data = json.loads(blob[blob.find("{"): blob.rfind("}") + 1])
        steps = data.get("steps") if isinstance(data, dict) else None
        if not steps:
            raise AzzxError("replan produced no steps")
        return steps


def _summarize(outcome: Any) -> str:
    try:
        text = outcome if isinstance(outcome, str) else json.dumps(outcome, ensure_ascii=False)
    except Exception:
        text = str(outcome)
    text = (text or "").strip().replace("\n", " ")
    return text[:300] + ("…" if len(text) > 300 else "")

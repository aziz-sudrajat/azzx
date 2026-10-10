"""Explicit planning for AZZX (v10.5): plans, todos, clarification.

- ``generate_plan()`` asks the configured provider for a structured,
  tool-grounded plan and saves it under ``.azzx/plans/``.
- ``TodoList`` is the agent's working checklist, also exposed as
  ``todo.add`` / ``todo.list`` / ``todo.done`` / ``todo.clear`` tools so
  autonomous runs can track themselves through the permission-enforcing
  registry.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azzx.core import AzzxError, DATA_HOME

_PLAN_CONTRACT = """\
You are a planner. Respond with a single JSON object and nothing else.
Shape:
{
  "goal": "restated goal",
  "steps": [
    {"id": "s1", "title": "short title", "tool": "<registered tool name or 'ask_user'>",
     "args": {}, "why": "one line", "risk": "low|medium|high"}
  ],
  "risks": ["overall risk 1"],
  "needs_clarification": ["question 1"]
}
Rules:
- "tool" must be a real AZZX tool the orchestrator can call (e.g. sys.health,
  sandbox.exec, filesystem.read). Use "ask_user" only when you genuinely cannot
  proceed without the user.
- Prefer read-only steps first; put destructive steps last and mark risk high.
- Keep steps small: 3-8 steps. No shell one-liners outside sandbox.exec.
"""

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_plan(text: str) -> dict[str, Any]:
    m = _JSON_BLOCK_RE.search(text or "")
    raw = m.group(1) if m else (text or "")
    try:
        data = json.loads(raw)
    except Exception:
        # Last resort: find the outermost braces
        start, end = raw.find("{"), raw.rfind("}")
        try:
            data = json.loads(raw[start : end + 1])
        except Exception:
            raise AzzxError("planner returned unparseable output")
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise AzzxError("planner output missing 'steps'")
    steps = []
    for i, s in enumerate(data["steps"][:12], 1):
        if not isinstance(s, dict):
            continue
        steps.append({
            "id": str(s.get("id") or f"s{i}"),
            "title": str(s.get("title") or f"step {i}")[:160],
            "tool": str(s.get("tool") or "ask_user"),
            "args": s.get("args") if isinstance(s.get("args"), dict) else {},
            "why": str(s.get("why") or "")[:300],
            "risk": str(s.get("risk") or "low").lower(),
        })
    return {
        "goal": str(data.get("goal") or "")[:300],
        "steps": steps,
        "risks": [str(r)[:200] for r in (data.get("risks") or [])][:6],
        "needs_clarification": [str(q)[:200] for q in (data.get("needs_clarification") or [])][:5],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def plans_dir(project_root: str | None = None) -> Path:
    root = Path(project_root or ".").expanduser().resolve()
    d = root / ".azzx" / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_plan(
    goal: str,
    context: str = "",
    project_root: str | None = None,
    forced_provider: str | None = None,
    cancel_event: threading.Event | None = None,
    max_tokens: int = 1500,
) -> dict[str, Any]:
    """Ask the provider for a structured plan; save it; return it."""
    goal = (goal or "").strip()
    if not goal:
        raise AzzxError("plan needs a goal")
    from azzx.agent.providers import default_router

    try:
        from azzx.agent.orchestrator import describe_tools_for_ai
        tool_catalog = describe_tools_for_ai()[:4000]
    except Exception:
        tool_catalog = "(tool catalog unavailable)"

    messages = [
        {"role": "system", "content": _PLAN_CONTRACT},
        {"role": "user", "content": (
            f"GOAL: {goal}\n\n"
            f"AVAILABLE TOOLS (name — description):\n{tool_catalog}\n\n"
            + (f"CONTEXT:\n{context[:2000]}\n\n" if context else "")
            + "Produce the plan JSON now."
        )},
    ]
    router = default_router()
    try:
        result = router.chat(messages, forced_provider=forced_provider,
                             cancel_event=cancel_event, max_tokens=max_tokens)
    except Exception as exc:
        raise AzzxError(f"planner failed: {exc}")
    plan = _parse_plan(result.text)
    plan["provider"] = result.provider_id
    plan["model"] = result.model

    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:40] or "plan"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = plans_dir(project_root) / f"{stamp}-{slug}.json"
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    plan["path"] = str(path)
    return plan


def load_plan(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_file():
        raise AzzxError(f"plan not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def render_plan_text(plan: dict[str, Any]) -> str:
    lines = [f"Goal: {plan.get('goal', '')}", ""]
    for s in plan.get("steps", []):
        args = json.dumps(s.get("args") or {}, ensure_ascii=False)
        lines.append(f"  [{s['id']}] {s['title']}  (risk: {s.get('risk', 'low')})")
        lines.append(f"        tool: {s.get('tool')}  args: {args}")
        if s.get("why"):
            lines.append(f"        why: {s['why']}")
    if plan.get("risks"):
        lines += ["", "Risks:"] + [f"  - {r}" for r in plan["risks"]]
    if plan.get("needs_clarification"):
        lines += ["", "Needs clarification:"] + [f"  ? {q}" for q in plan["needs_clarification"]]
    return "\n".join(lines)


# -- agent todo list ---------------------------------------------------
@dataclass
class TodoItem:
    id: str
    title: str
    done: bool = False


class TodoList:
    """The agent's working checklist, persisted under DATA_HOME."""

    def __init__(self, namespace: str = "default") -> None:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", namespace).strip("-") or "default"
        self.path = Path(DATA_HOME) / "agent" / "todos" / f"{safe}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: list[TodoItem] = []
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = [TodoItem(str(i.get("id")), str(i.get("title")),
                                    bool(i.get("done"))) for i in raw if isinstance(i, dict)]
        except Exception:
            self._items = []

    def _save(self) -> None:
        self.path.write_text(json.dumps(
            [{"id": i.id, "title": i.title, "done": i.done} for i in self._items],
            indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, title: str) -> dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise AzzxError("todo title must not be empty")
        # Monotonic ids: len()-based ids collide after clear(); use max+1.
        nxt = max(
            (int(i.id[1:]) for i in self._items
             if i.id.startswith("t") and i.id[1:].isdigit()),
            default=0) + 1
        item = TodoItem(id=f"t{nxt}", title=title[:200])
        self._items.append(item)
        self._save()
        return {"id": item.id, "title": item.title}

    def list(self) -> list[dict[str, Any]]:
        return [{"id": i.id, "title": i.title, "done": i.done} for i in self._items]

    def done(self, item_id: str) -> dict[str, Any]:
        for i in self._items:
            if i.id == item_id:
                i.done = True
                self._save()
                return {"id": i.id, "done": True}
        raise AzzxError(f"todo not found: {item_id}")

    def clear(self, done_only: bool = True) -> dict[str, Any]:
        before = len(self._items)
        self._items = [i for i in self._items if not (i.done or not done_only)]
        self._save()
        return {"removed": before - len(self._items)}


_TODOS: dict[str, TodoList] = {}


def get_todo_list(namespace: str = "default") -> TodoList:
    if namespace not in _TODOS:
        _TODOS[namespace] = TodoList(namespace)
    return _TODOS[namespace]


def register_planning_tools() -> None:
    from azzx.core import REGISTRY, ToolSpec

    def _add(title: str, namespace: str = "default") -> dict[str, Any]:
        return get_todo_list(namespace).add(title)

    def _list(namespace: str = "default") -> dict[str, Any]:
        return {"items": get_todo_list(namespace).list()}

    def _done(item_id: str, namespace: str = "default") -> dict[str, Any]:
        return get_todo_list(namespace).done(item_id)

    def _clear(namespace: str = "default", done_only: bool = True) -> dict[str, Any]:
        return get_todo_list(namespace).clear(done_only=bool(done_only))

    REGISTRY.register(ToolSpec(
        name="todo.add", description="Add an item to the agent's working checklist.",
        permissions=[], handler=_add, schema={"title": "str (required)", "namespace": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="todo.list", description="List the agent's checklist items.",
        permissions=[], handler=_list, schema={"namespace": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="todo.done", description="Mark a checklist item done.",
        permissions=[], handler=_done, schema={"item_id": "str (required)", "namespace": "str"},
    ))
    REGISTRY.register(ToolSpec(
        name="todo.clear", description="Remove done (or all) checklist items.",
        permissions=[], handler=_clear, schema={"namespace": "str", "done_only": "bool"},
    ))

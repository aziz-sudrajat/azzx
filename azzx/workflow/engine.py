"""Workflow engine: ordered steps of registered tools only."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azzx.core import (
    AzzxError,
    DATA_HOME,
    REGISTRY,
    ToolSpec,
    load_json,
    require_permission,
    save_json,
    sanitize_id,
    setup_homes,
)

WORKFLOW_DIR = DATA_HOME / "workflows"
NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def _store_path(name: str) -> Path:
    if not NAME_RE.match(name):
        raise AzzxError(f"Invalid workflow name: {name!r}")
    return WORKFLOW_DIR / f"{name}.json"


class WorkflowStore:
    def __init__(self) -> None:
        setup_homes()
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return _store_path(name)

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def load(self, name: str) -> dict[str, Any]:
        p = self.path(name)
        if not p.exists():
            raise AzzxError(f"Workflow not found: {name}")
        data = load_json(p, {})
        if not isinstance(data, dict) or "steps" not in data:
            raise AzzxError(f"Corrupt workflow: {name}")
        return data

    def save(self, name: str, data: dict[str, Any]) -> Path:
        p = self.path(name)
        save_json(p, data)
        return p

    def list_names(self) -> list[str]:
        return sorted(p.stem for p in WORKFLOW_DIR.glob("*.json"))

    def delete(self, name: str) -> None:
        p = self.path(name)
        if not p.exists():
            raise AzzxError(f"Workflow not found: {name}")
        p.unlink()


def _validate_steps(steps: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise AzzxError("Workflow must have a non-empty steps list")
    clean: list[dict[str, Any]] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise AzzxError(f"Step {i} must be an object")
        tool = str(step.get("tool") or "").strip()
        if not tool:
            raise AzzxError(f"Step {i} missing tool")
        # Must be a registered tool — no shell escape hatch
        try:
            REGISTRY.get(tool)
        except AzzxError as exc:
            raise AzzxError(
                f"Step {i}: {exc}. Workflows may only call registered AZZX tools."
            ) from exc
        args = step.get("args") or {}
        if not isinstance(args, dict):
            raise AzzxError(f"Step {i} args must be an object")
        # Reject any attempt to inject shell
        for banned in ("shell", "command", "cmd", "script", "eval"):
            if banned in args:
                raise AzzxError(f"Step {i} contains forbidden argument: {banned}")
        clean.append({"tool": tool, "args": args})
    return clean


def create_workflow(
    name: str,
    steps: list[dict[str, Any]],
    description: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    store = WorkflowStore()
    if store.exists(name) and not overwrite:
        raise AzzxError(f"Workflow already exists: {name} (use overwrite)")
    clean_steps = _validate_steps(steps)
    data = {
        "name": name,
        "description": description,
        "created": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "steps": clean_steps,
    }
    store.save(name, data)
    return data


def list_workflows() -> list[dict[str, Any]]:
    store = WorkflowStore()
    result = []
    for name in store.list_names():
        try:
            data = store.load(name)
            result.append({
                "name": name,
                "description": data.get("description", ""),
                "steps": len(data.get("steps") or []),
                "created": data.get("created", ""),
            })
        except AzzxError:
            result.append({"name": name, "error": "corrupt"})
    return result


def show_workflow(name: str) -> dict[str, Any]:
    return WorkflowStore().load(name)


def delete_workflow(name: str) -> None:
    WorkflowStore().delete(name)


def run_workflow(name: str, noninteractive: bool = False) -> dict[str, Any]:
    require_permission("workflow.run", detail=f"run workflow {name}", noninteractive=noninteractive, force_yes=noninteractive)
    data = WorkflowStore().load(name)
    steps = _validate_steps(data.get("steps") or [])
    results = []
    for i, step in enumerate(steps):
        tool = step["tool"]
        args = dict(step.get("args") or {})
        try:
            out = REGISTRY.call(tool, args, noninteractive=noninteractive, force_yes=noninteractive)
            results.append({"step": i, "tool": tool, "ok": True, "result": out})
        except Exception as exc:  # noqa: BLE001
            results.append({"step": i, "tool": tool, "ok": False, "error": str(exc)})
            return {
                "workflow": name,
                "ok": False,
                "failed_at": i,
                "results": results,
            }
    return {"workflow": name, "ok": True, "results": results}


def register_workflow_tools() -> None:
    """Optional: expose workflow ops as tools for meta-automation (still no shell)."""
    REGISTRY.register(ToolSpec(
        name="workflow.list",
        description="List saved workflows",
        permissions=["workflow.run"],
        handler=lambda: {"workflows": list_workflows()},
        schema={},
    ))

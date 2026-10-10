#!/usr/bin/env python3
"""v10.4 native agent tests (unittest, offline, no paid API calls).

Covers: provider error taxonomy + bounded retries + cancellation,
multi-agent delegation via a mock provider (roles, tool allowlists,
failure visibility), persistent memory (restarts, hybrid search, delete,
shared/private, dedup, secret refusal, projects), session continuity,
task queue recovery, the skill registry, and security regressions.
"""
import base64
import json
import os
import re
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TD = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = str(Path(_TD.name) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_TD.name) / "data")


def _allow_all_permissions():
    from azzx.core import load_config, save_config
    cfg = load_config()
    perms = cfg.get("permissions") or {}
    for cap in list(perms.keys()):
        perms[cap] = "allow"
    cfg["permissions"] = perms
    save_config(cfg)


_allow_all_permissions()

from azzx.agent.orchestrator import register_all  # noqa: E402
register_all()


# ---------------------------------------------------------------------------
# Providers: taxonomy, retries, cancellation
# ---------------------------------------------------------------------------

class ProviderTaxonomyTest(unittest.TestCase):
    def test_classify_http_errors(self):
        from azzx.agent.providers import (
            AuthenticationError, MalformedResponseError, ProviderError,
            ProviderOutageError, RateLimitError, classify_http_error,
        )
        self.assertIsInstance(classify_http_error(401, "bad"), AuthenticationError)
        self.assertIsInstance(classify_http_error(403, "bad"), AuthenticationError)
        self.assertIsInstance(classify_http_error(429, "slow"), RateLimitError)
        self.assertIsInstance(classify_http_error(503, "down"), ProviderOutageError)
        self.assertIsInstance(classify_http_error(418, "tea"), ProviderError)
        self.assertTrue(classify_http_error(429, "x").retryable)
        self.assertTrue(classify_http_error(500, "x").retryable)
        self.assertFalse(classify_http_error(401, "x").retryable)
        self.assertIn("API key", classify_http_error(401, "x").hint)

    def test_malformed_response_classification(self):
        from azzx.agent.providers import MalformedResponseError, OpenAICompatibleAdapter
        import httpx

        class FakeResp:
            is_success = True
            status_code = 200
            def json(self):
                return {"choices": []}  # no usable content

        class FakeClient:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, *a, **k): return FakeResp()

        real = httpx.Client
        httpx.Client = FakeClient
        try:
            ad = OpenAICompatibleAdapter({"base_url": "http://x"}, "k", 5)
            with self.assertRaises(MalformedResponseError):
                ad.chat([{"role": "user", "content": "hi"}], "m")
        finally:
            httpx.Client = real

    def test_openai_sse_parsing(self):
        import httpx
        from azzx.agent.providers import OpenAICompatibleAdapter

        lines = [
            'data: {"choices":[{"delta":{"content":"Halo"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":" dunia"}}]}',
            "data: [DONE]",
        ]

        class FakeStream:
            is_success = True
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def iter_lines(self): return iter(lines)

        class FakeClient:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def stream(self, *a, **k): return FakeStream()

        real = httpx.Client
        httpx.Client = FakeClient
        try:
            ad = OpenAICompatibleAdapter({"base_url": "http://x", "name": "t"}, api_key="k", timeout=5)
            self.assertEqual(
                list(ad.stream_chat([{"role": "user", "content": "hi"}], "m")),
                ["Halo", " dunia"],
            )
        finally:
            httpx.Client = real

    def _router(self, adapter, **cfg_over):
        from azzx.agent.providers import AIRouter
        cfg = {"timeout_seconds": 5, "provider_max_retries": 2}
        cfg.update(cfg_over)
        providers = {"mock": {"name": "mock", "kind": "openai", "model": "m",
                              "requires_key": False}}
        return AIRouter(cfg, providers, None,
                        adapter_factory=lambda p, k, t: adapter)

    def test_retryable_errors_retry_then_succeed(self):
        from azzx.agent.providers import MockAdapter, RateLimitError
        adapter = MockAdapter(script={
            0: RateLimitError("slow down"),
            1: RateLimitError("slow down"),
            2: "finally ok",
        })
        router = self._router(adapter)
        result = router.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(result.text, "finally ok")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(adapter.calls), 3)

    def test_non_retryable_fails_fast(self):
        from azzx.agent.providers import AuthenticationError, MockAdapter
        from azzx.core import AzzxError
        adapter = MockAdapter(fail_with=AuthenticationError("bad key"))
        router = self._router(adapter)
        with self.assertRaises(AzzxError) as ctx:
            router.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(len(adapter.calls), 1)  # no retries for auth errors
        self.assertIn("API key", str(ctx.exception))

    def test_retries_are_bounded(self):
        from azzx.agent.providers import MockAdapter, ProviderOutageError
        from azzx.core import AzzxError
        adapter = MockAdapter(fail_with=ProviderOutageError("down"))
        router = self._router(adapter, provider_max_retries=2)
        with self.assertRaises(AzzxError):
            router.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(len(adapter.calls), 3)  # 1 + 2 retries, never infinite

    def test_cancellation_between_attempts(self):
        from azzx.agent.providers import CancelledError, MockAdapter, ProviderOutageError
        adapter = MockAdapter(fail_with=ProviderOutageError("down"))
        router = self._router(adapter, provider_max_retries=5)
        event = threading.Event()
        event.set()  # already cancelled
        with self.assertRaises(CancelledError):
            router.chat([{"role": "user", "content": "hi"}], cancel_event=event)

    def test_no_providers_configured_message(self):
        from azzx.agent.providers import AIRouter
        from azzx.core import AzzxError
        router = AIRouter({"timeout_seconds": 5}, {}, None)
        with self.assertRaises(AzzxError) as ctx:
            router.chat([{"role": "user", "content": "hi"}])
        self.assertIn("azzx ai", str(ctx.exception))

    def test_stream_cancel(self):
        from azzx.agent.providers import CancelledError, MockAdapter
        adapter = MockAdapter(script={"default": "one two three"})
        router = self._router(adapter)
        event = threading.Event()
        gen = router.stream([{"role": "user", "content": "hi"}], cancel_event=event)
        pid, first = next(gen)
        self.assertEqual(pid, "mock")
        event.set()
        with self.assertRaises(CancelledError):
            list(gen)


# ---------------------------------------------------------------------------
# Multi-agent: real delegation through a mock provider
# ---------------------------------------------------------------------------

class _RoleMock:
    """MockAdapter subclass answering per role with structured JSON."""

    def __init__(self):
        from azzx.agent.providers import MockAdapter

        class M(MockAdapter):
            def _next(inner_self, messages, model):
                inner_self.calls.append({"messages": messages, "model": model})
                system = messages[0]["content"] if messages else ""
                m = re.search(r"You are the ([A-Z ]+) of", system)
                role = m.group(1).strip().lower() if m else "agent"
                tools = [{"tool": "sys.health", "args": {}}] if role == "tester" else []
                return json.dumps({
                    "summary": f"{role}: done via provider",
                    "findings": [f"{role} finding"],
                    "actions": [f"{role} action"],
                    "tool_requests": tools,
                    "needs": [],
                })

        self.impl = M()
        self.calls = self.impl.calls

    def chat(self, messages, model, max_tokens=None, cancel_event=None):
        return self.impl.chat(messages, model, max_tokens=max_tokens, cancel_event=cancel_event)

    def stream_chat(self, messages, model, cancel_event=None):
        return self.impl.stream_chat(messages, model, cancel_event=cancel_event)


def _mock_router(mock, **cfg_over):
    from azzx.agent.providers import AIRouter
    cfg = {"timeout_seconds": 5, "provider_max_retries": 0}
    cfg.update(cfg_over)
    providers = {"mock": {"name": "mock", "kind": "openai", "model": "m", "requires_key": False}}
    return AIRouter(cfg, providers, None, adapter_factory=lambda p, k, t: mock)


class MultiAgentTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        from azzx.agent.multi_agent import MultiAgentOrchestrator
        self.mock = _RoleMock()
        self.orch = MultiAgentOrchestrator(memory_dir=self.td.name,
                                           router=_mock_router(self.mock))

    def tearDown(self):
        self.td.cleanup()

    def test_roles_have_tool_allowlists(self):
        for name in ("planner", "researcher", "coder", "reviewer", "tester", "security"):
            p = self.orch.get_profile(name)
            self.assertIsNotNone(p, name)
            self.assertTrue(p.system_prompt)
        self.assertEqual(self.orch.get_profile("planner").allowed_tools, [])
        self.assertTrue(self.orch.get_profile("tester").tool_allowed("sys.health"))
        self.assertFalse(self.orch.get_profile("planner").tool_allowed("sys.health"))

    def test_delegate_calls_provider_and_runs_allowed_tools(self):
        res = self.orch.delegate("check system health", "tester", noninteractive=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["provider"], "mock")
        self.assertIn("tester: done via provider", res["summary"])
        self.assertEqual(len(res["tool_calls"]), 1)
        self.assertTrue(res["tool_calls"][0]["ok"])
        self.assertIn("platform", json.dumps(res["tool_calls"][0]["result"]))
        kinds = [s["kind"] for s in res["reasoning"]["steps"]]
        for expected in ("thought", "plan", "act", "observe", "reflect", "conclusion"):
            self.assertIn(expected, kinds)

    def test_tool_allowlist_denial_is_visible(self):
        denied = self.orch._execute_tool_requests(
            self.orch.get_profile("planner"),
            [{"tool": "sys.health", "args": {}}],
            noninteractive=True, force_yes=True,
        )
        self.assertFalse(denied[0]["ok"])
        self.assertIn("not in planner", denied[0]["error"])

    def test_provider_failure_is_visible_not_hidden(self):
        from azzx.agent.providers import MockAdapter, ProviderOutageError
        from azzx.agent.multi_agent import MultiAgentOrchestrator
        failing = MockAdapter(fail_with=ProviderOutageError("provider down"))
        orch = MultiAgentOrchestrator(memory_dir=tempfile.mkdtemp(),
                                      router=_mock_router(failing))
        res = orch.delegate("anything", "coder")
        self.assertEqual(res["status"], "error")
        self.assertIn("provider down", res["error"])

    def test_run_task_chains_context_and_reports(self):
        out = self.orch.run_task("summarize repo health",
                                 agent_order=["planner", "tester"], noninteractive=True)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["agents_used"], ["planner", "tester"])
        self.assertEqual(out["failed_agents"], [])
        self.assertTrue(out["final_summary"])

    def test_run_task_fail_fast(self):
        from azzx.agent.providers import MockAdapter, ProviderOutageError
        from azzx.agent.multi_agent import MultiAgentOrchestrator
        failing = MockAdapter(fail_with=ProviderOutageError("boom"))
        orch = MultiAgentOrchestrator(memory_dir=tempfile.mkdtemp(),
                                      router=_mock_router(failing))
        out = orch.run_task("x", agent_order=["planner", "coder"], fail_fast=True)
        self.assertEqual(out["status"], "failed")
        self.assertEqual(out["agents_used"], ["planner"])
        self.assertEqual(out["failed_agents"], ["planner"])

    def test_parallel_refused_for_state_changing_roles(self):
        from azzx.agent.multi_agent import AgentProfile
        from azzx.core import AzzxError
        self.orch.profiles["writer"] = AgentProfile(
            name="writer", role="writer", description="writes",
            system_prompt="You are the WRITER of the team.",
            allowed_tools=[], read_only=False,
        )
        with self.assertRaises(AzzxError):
            self.orch.run_task("x", agent_order=["writer"], parallel=True)
        with self.assertRaises(AzzxError):
            self.orch.collaborate(["writer"], "x")

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            self.orch.delegate("x", "nope")


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        from azzx.agent.memory import MemoryStore
        self.store = MemoryStore(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_persists_across_restarts(self):
        from azzx.agent.memory import MemoryStore
        mid = self.store.store("planner", "restart persistence check", importance=0.9)
        store2 = MemoryStore(self.td.name)
        entry = store2.get(int(mid))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.content, "restart persistence check")

    def test_exact_duplicates_not_stored_twice(self):
        from azzx.agent.memory import MemoryStore
        a = self.store.store("a", "same content here")
        b = self.store.store("a", "same content here")
        self.assertEqual(a, b)
        store2 = MemoryStore(self.td.name)
        self.assertEqual(store2.get_stats()["total"], 1)

    def test_secrets_refused(self):
        # NOTE: fake credential below is intentionally shaped to trigger the
        # store's secret detector while NOT matching selftest.sh's release
        # grep for real leaked keys.
        with self.assertRaises(ValueError) as ctx:
            self.store.store("a", 'api_key = "fake-test-value-123456"')
        self.assertNotIn("fake-test-value", str(ctx.exception))
        with self.assertRaises(ValueError):
            self.store.store("a", "-----BEGIN RSA PRIVATE KEY-----\nx")
        self.assertEqual(self.store.get_stats()["total"], 0)

    def test_shared_private_boundaries(self):
        self.store.store("coder", "coder private note", shared=False)
        self.store.store("coder", "coder shared note", shared=True)
        # another agent sees only the shared one
        hits = self.store.search("note", agent_id="reviewer")
        contents = [h.content for h in hits]
        self.assertIn("coder shared note", contents)
        self.assertNotIn("coder private note", contents)
        # owner sees both
        own = self.store.search("note", agent_id="coder")
        self.assertEqual(len(own), 2)
        # explicit override
        all_hits = self.store.search("note", include_private=True)
        self.assertEqual(len(all_hits), 2)

    def test_project_scoping(self):
        self.store.store("a", "alpha deploy notes", project="web")
        self.store.store("a", "beta deploy notes", project="api")
        hits = self.store.search("deploy", project="web")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].project, "web")

    def test_importance_clamped_and_type_validated(self):
        mid = self.store.store("a", "clamp me", importance=99.0)
        self.assertEqual(self.store.get(int(mid)).importance, 1.0)
        with self.assertRaises(ValueError):
            self.store.store("a", "bad type", memory_type="Not A Type!")

    def test_delete_removes_semantic_vectors(self):
        mid = self.store.store("a", "kucing saya suka makan ikan setiap pagi")
        self.assertTrue(self.store.search_semantic("kucing makan"))
        self.assertTrue(self.store.delete(int(mid)))
        self.assertFalse(self.store.search_semantic("kucing makan"))
        self.assertTrue(self.store.verify_index()["healthy"])

    def test_rebuild_and_verify(self):
        self.store.store("a", "satu dua tiga")
        n = self.store.rebuild_vectors()
        self.assertEqual(n, 1)
        self.assertTrue(self.store.search_semantic("satu"))
        idx = self.store.verify_index()
        self.assertEqual(idx["entries"], 1)
        self.assertTrue(idx["healthy"])

    def test_hybrid_ranking(self):
        self.store.store("a", "database postgres backup otomatis tiap malam")
        hits = self.store.search_hybrid("backup database", limit=3)
        self.assertTrue(hits)
        entry, score = hits[0]
        self.assertIn("backup", entry.content)
        self.assertGreaterEqual(score, 0.0)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class SessionTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        from azzx.agent.session import SessionMemoryJournal
        self.journal = SessionMemoryJournal(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_start_log_end_resume(self):
        sid = self.journal.start_session("web", "deploy work", "initial")
        self.journal.log_event(sid, "planner", "plan", "decided blue-green")
        self.journal.log_event(sid, "coder", "act", "edited deploy.py")
        bundle = self.journal.resume_session(sid)
        self.assertEqual(bundle["session"]["session_id"], sid)
        self.assertEqual(len(bundle["events"]), 2)
        # chronological order
        self.assertEqual(bundle["events"][0]["agent_id"], "planner")
        self.assertIn("continue from the last state", bundle["hint"])
        self.assertTrue(self.journal.end_session(sid, status="done", summary="shipped"))
        resumed = self.journal.resume_session(sid)  # re-activates deliberately
        self.assertEqual(resumed["session"]["status"], "active")

    def test_stale_detection(self):
        import sqlite3
        sid = self.journal.start_session("web", "old work")
        # backdate updated_at
        con = sqlite3.connect(self.journal.db_path)
        con.execute("UPDATE sessions SET updated_at = '2020-01-01T00:00:00Z' WHERE session_id = ?",
                    (sid,))
        con.commit()
        con.close()
        stale = self.journal.find_stale(stale_hours=1)
        self.assertTrue(any(s["session_id"] == sid for s in stale))
        fresh = self.journal.find_stale(project="other-project", stale_hours=1)
        self.assertFalse(any(s["session_id"] == sid for s in fresh))

    def test_end_invalid_status(self):
        sid = self.journal.start_session("web", "t")
        with self.assertRaises(ValueError):
            self.journal.end_session(sid, status="exploded")


# ---------------------------------------------------------------------------
# Task queue
# ---------------------------------------------------------------------------

class TaskQueueTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        from azzx.agent.tasks import TaskQueue
        self.state = os.path.join(self.td.name, "q.json")
        self.q = TaskQueue(self.state)

    def tearDown(self):
        self.q.join(timeout=5.0)
        self.td.cleanup()

    def test_tool_roundtrip(self):
        tid = self.q.submit_tool("sys.info", {})
        snap = self.q.result(tid, timeout=15)
        self.assertEqual(snap["status"], "done")
        self.assertIsInstance(snap["result"], dict)

    def test_callable_roundtrip(self):
        tid = self.q.submit("adder", lambda x, y: x + y, {"x": 2, "y": 3})
        snap = self.q.result(tid, timeout=10)
        self.assertEqual(snap["status"], "done")
        self.assertEqual(snap["result"], 5)

    def test_failed_task_reports_error(self):
        tid = self.q.submit_tool("no.such.tool", {})
        snap = self.q.result(tid, timeout=10)
        self.assertEqual(snap["status"], "error")
        self.assertTrue(snap["error"])

    def test_cancel_queued_task(self):
        q2_state = os.path.join(self.td.name, "q2.json")
        from azzx.agent.tasks import TaskQueue
        q2 = TaskQueue(q2_state, auto_worker=False)
        tid = q2.submit_tool("sys.info", {})
        self.assertTrue(q2.cancel(tid))
        self.assertEqual(q2.status(tid)["status"], "cancelled")
        self.assertFalse(q2.cancel(tid))  # already terminal
        self.assertFalse(q2.resume_task("nope"))

    def test_interrupted_marked_not_silently_rerun(self):
        import json as _json
        from azzx.agent.tasks import TaskQueue
        st = os.path.join(self.td.name, "q3.json")
        q = TaskQueue(st, auto_worker=False)
        tid = q.submit_tool("sys.info", {})
        items = _json.loads(open(st).read())
        items[0]["status"] = "running"
        items[0]["owner"] = "99999999"  # dead pid
        open(st, "w").write(_json.dumps(items))
        q2 = TaskQueue(st, auto_worker=False)
        snap = q2.status(tid)
        self.assertEqual(snap["status"], "interrupted")
        self.assertTrue(q2.resume_task(tid))
        self.assertEqual(q2.status(tid)["status"], "queued")

    def test_malformed_owner_does_not_crash(self):
        import json as _json
        from azzx.agent.tasks import TaskQueue
        st = os.path.join(self.td.name, "q4.json")
        q = TaskQueue(st, auto_worker=False)
        tid = q.submit_tool("sys.info", {})
        items = _json.loads(open(st).read())
        items[0]["status"] = "running"
        items[0]["owner"] = "not-a-pid"
        open(st, "w").write(_json.dumps(items))
        q2 = TaskQueue(st, auto_worker=False)  # must not raise
        self.assertEqual(q2.status(tid)["status"], "interrupted")

    def test_unapproved_background_tool_needs_approval(self):
        from azzx.core import load_config, save_config
        from azzx.agent.tasks import TaskQueue
        cfg = load_config()
        original = dict(cfg.get("permissions") or {})
        try:
            cfg["permissions"]["network.http"] = "ask"
            save_config(cfg)
            st = os.path.join(self.td.name, "q5.json")
            q = TaskQueue(st)
            tid = q.submit_tool("net.connectivity", {"host": "127.0.0.1", "port": 9})
            snap = q.result(tid, timeout=10)
            self.assertEqual(snap["status"], "error")
            self.assertIn("needs approval", snap["error"])
            tid2 = q.submit_tool("net.connectivity", {"host": "127.0.0.1", "port": 9},
                                approved=True)
            snap2 = q.result(tid2, timeout=10)
            self.assertEqual(snap2["status"], "done")
        finally:
            cfg["permissions"] = original
            save_config(cfg)

    def test_state_file_is_private(self):
        self.q.submit_tool("sys.info", {})
        mode = stat.S_IMODE(os.stat(self.state).st_mode)
        self.assertEqual(mode, 0o600)

    def test_drainer_claims_and_completes(self):
        from azzx.agent.tasks import TaskQueue
        st = os.path.join(self.td.name, "q6.json")
        q = TaskQueue(st, auto_worker=False)
        tid = q.submit_tool("sys.info", {})
        self.assertTrue(q.drain(timeout=20))
        snap = TaskQueue(st, auto_worker=False).status(tid)
        self.assertEqual(snap["status"], "done")

    def test_result_refreshes_from_disk(self):
        import json as _json
        from azzx.agent.tasks import TaskQueue
        st = os.path.join(self.td.name, "q7.json")
        q = TaskQueue(st, auto_worker=False)
        tid = q.submit_tool("sys.info", {})
        # another process finishes it
        items = _json.loads(open(st).read())
        items[0]["status"] = "done"
        items[0]["result"] = {"ok": True}
        items[0]["finished_at"] = 1.0
        open(st, "w").write(_json.dumps(items))
        snap = q.result(tid, timeout=2)
        self.assertEqual(snap["status"], "done")


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def _make_skill_dir(root, skill_id="greet", bad_manifest=False):
    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    if bad_manifest:
        manifest = {"id": "BAD ID!", "version": "1.0.0", "handler": "h:m"}
    else:
        manifest = {
            "id": skill_id, "name": "Greeter", "description": "Says hello",
            "version": "1.0.0", "handler": "handler:main", "permissions": [],
            "tags": ["demo"],
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 1}},
                "required": ["name"],
                "additionalProperties": False,
            },
        }
    with open(os.path.join(src, "skill.json"), "w") as fh:
        json.dump(manifest, fh)
    with open(os.path.join(src, "handler.py"), "w") as fh:
        fh.write("def main(name):\n    return {'hello': name}\n")
    return src


class SkillsTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        from azzx.agent.skills import SkillRegistry
        self.reg = SkillRegistry(os.path.join(self.td.name, "skills"))
        self.reg.install(_make_skill_dir(self.td.name))

    def tearDown(self):
        self.td.cleanup()

    def test_install_defaults_untrusted_disabled(self):
        meta = next(m for m in self.reg.list() if m["id"] == "greet")
        self.assertFalse(meta["trusted"])
        self.assertFalse(meta["enabled"])

    def test_untrusted_skill_refused(self):
        from azzx.agent.skills import SkillError
        with self.assertRaises(SkillError):
            self.reg.invoke("greet", {"name": "x"})
        with self.assertRaises(SkillError):
            self.reg.enable("greet")

    def test_trust_enable_invoke(self):
        self.reg.trust("greet")
        self.reg.enable("greet")
        out = self.reg.invoke("greet", {"name": "Shiki"})
        self.assertEqual(out, {"hello": "Shiki"})

    def test_arg_validation(self):
        from azzx.agent.skills import SkillError
        self.reg.trust("greet")
        self.reg.enable("greet")
        with self.assertRaises(SkillError):
            self.reg.invoke("greet", {})
        with self.assertRaises(SkillError):
            self.reg.invoke("greet", {"name": "x", "extra": 1})
        with self.assertRaises(SkillError):
            self.reg.invoke("greet", {"name": ""})  # minLength

    def test_bad_manifest_rejected(self):
        from azzx.agent.skills import SkillError
        with self.assertRaises(SkillError):
            self.reg.install(_make_skill_dir(self.td.name + "-bad", bad_manifest=True))

    def test_untrust_disables(self):
        self.reg.trust("greet")
        self.reg.enable("greet")
        self.reg.untrust("greet")
        meta = next(m for m in self.reg.list() if m["id"] == "greet")
        self.assertFalse(meta["trusted"])
        self.assertFalse(meta["enabled"])

    def test_find(self):
        hits = self.reg.find("hello")
        self.assertTrue(any(h["id"] == "greet" for h in hits))

    def test_skill_tool_registered_after_enable(self):
        from azzx.core import REGISTRY
        self.reg.trust("greet")
        self.reg.enable("greet")
        spec = REGISTRY.get("skill.greet")
        self.assertTrue(spec.description.startswith("[skill"))
        out = REGISTRY.call("skill.greet", {"name": "via-tool"})
        self.assertEqual(out, {"hello": "via-tool"})


# ---------------------------------------------------------------------------
# Security regressions
# ---------------------------------------------------------------------------

class SecurityRegressionTest(unittest.TestCase):
    def test_deny_enforced_on_direct_call(self):
        from azzx.core import PermissionDenied, REGISTRY, load_config, save_config
        cfg = load_config()
        original = dict(cfg.get("permissions") or {})
        try:
            cfg["permissions"]["network.http"] = "deny"
            save_config(cfg)
            with self.assertRaises(PermissionDenied):
                REGISTRY.call("net.connectivity", {"host": "127.0.0.1", "port": 9},
                              noninteractive=True)
        finally:
            cfg["permissions"] = original
            save_config(cfg)

    def test_deny_enforced_through_workflow(self):
        from azzx.core import PermissionDenied, load_config, save_config
        from azzx.workflow.engine import create_workflow, run_workflow, delete_workflow
        cfg = load_config()
        original = dict(cfg.get("permissions") or {})
        try:
            cfg["permissions"]["network.http"] = "deny"
            save_config(cfg)
            create_workflow("sec-test",
                            [{"tool": "net.connectivity", "args": {"host": "127.0.0.1", "port": 9}}],
                            overwrite=True)
            result = run_workflow("sec-test", noninteractive=True)
            self.assertFalse(result["ok"])
            self.assertIn("Permission denied", result["results"][0]["error"])
        finally:
            delete_workflow("sec-test")
            cfg["permissions"] = original
            save_config(cfg)

    def test_tracer_redacts_secrets(self):
        from azzx.agent.tracer import Tracer, redact_sensitive
        out = redact_sensitive({"api_key": "sk-secret", "name": "x",
                                "nested": {"token": "abc"}})
        self.assertEqual(out["api_key"], "***REDACTED***")
        self.assertEqual(out["name"], "x")
        self.assertEqual(out["nested"]["token"], "***REDACTED***")
        with tempfile.TemporaryDirectory() as td:
            tr = Tracer(log_path=os.path.join(td, "t.jsonl"))
            with tr.span("tool:x", kind="tool", args={"password": "hunter2", "ok": 1}):
                pass
            items = tr.recent_from_log(5)
            self.assertEqual(items[0]["attributes"]["args"]["password"], "***REDACTED***")
            raw = open(os.path.join(td, "t.jsonl")).read()
            self.assertNotIn("hunter2", raw)

    def test_scheduler_state_is_private(self):
        from azzx.agent.scheduler import ToolScheduler
        with tempfile.TemporaryDirectory() as td:
            sched = ToolScheduler(os.path.join(td, "sched.json"))
            sched.add("sys.info", {}, every_seconds=60)
            mode = stat.S_IMODE(os.stat(os.path.join(td, "sched.json")).st_mode)
            self.assertEqual(mode, 0o600)

    def test_memory_secret_scan(self):
        from azzx.agent.memory import find_secret_kind
        self.assertIsNotNone(find_secret_kind('token = "abc123xyz"'))
        self.assertIsNone(find_secret_kind("the meeting is at noon"))


# ---------------------------------------------------------------------------
# Misc: embeddings, reasoning, streaming, vision
# ---------------------------------------------------------------------------

class EmbeddingsTest(unittest.TestCase):
    def test_tokenize_basic(self):
        from azzx.agent.embeddings import tokenize
        toks = tokenize("The cat sat on the mat, dan kucing itu duduk")
        self.assertIn("cat", toks)
        self.assertIn("kucing", toks)
        self.assertNotIn("the", toks)
        self.assertNotIn("dan", toks)

    def test_similarity_orders_by_meaning(self):
        from azzx.agent.embeddings import SimpleEmbedder
        emb = SimpleEmbedder()
        docs = [
            "kucing makan ikan di dapur",
            "anjing menggonggong di halaman rumah",
            "resep ikan bakar bumbu dapur",
        ]
        for d in docs:
            emb.add_document(d)
        scored = emb.most_similar("kucing peliharaan makan",
                                  [(i, emb.embed(d)) for i, d in enumerate(docs)], limit=3)
        order = [i for i, _ in scored]
        self.assertLess(order.index(0), order.index(1))
        self.assertGreater(scored[0][1], 0.0)


class ReasoningTest(unittest.TestCase):
    def test_trace_lifecycle(self):
        from azzx.agent.reasoning import ReasoningTrace
        t = ReasoningTrace(task="fix bug", agent="coder")
        t.think("bug ada di parser")
        t.plan("tambah test lalu perbaiki")
        t.act("menjalankan tool")
        t.observe("test gagal di baris 42")
        t.reflect("asumsi salah, cek ulang")
        t.conclude("diperbaiki")
        d = t.to_dict()
        self.assertEqual(len(d["steps"]), 6)
        self.assertEqual(d["steps"][0]["kind"], "thought")
        self.assertIn("CONCLUSION", t.render())

    def test_invalid_kind_raises(self):
        from azzx.agent.reasoning import ReasoningTrace
        with self.assertRaises(ValueError):
            ReasoningTrace(task="x").add("daydream", "...")


class SchedulerTest(unittest.TestCase):
    def test_schedule_lifecycle_and_due_execution(self):
        from azzx.agent.scheduler import ToolScheduler
        with tempfile.TemporaryDirectory() as td:
            scheduler = ToolScheduler(os.path.join(td, "schedules.json"))
            job = scheduler.add("sys.info", {}, every_seconds=60, name="health check")
            self.assertEqual(len(scheduler.list()), 1)
            result = scheduler.run_due(now=job["next_run"] + 1)
            self.assertEqual(result["executed"], 1)
            self.assertEqual(scheduler.list()[0]["last_status"], "done")
            self.assertTrue(scheduler.remove(job["id"]))
            self.assertEqual(scheduler.list(), [])

    def test_schedule_rejects_too_frequent_interval(self):
        from azzx.agent.scheduler import ToolScheduler
        from azzx.core import AzzxError
        with tempfile.TemporaryDirectory() as td:
            scheduler = ToolScheduler(os.path.join(td, "schedules.json"))
            with self.assertRaises(AzzxError):
                scheduler.add("sys.info", {}, every_seconds=1)


class CLIParserTest(unittest.TestCase):
    def test_new_command_parsers(self):
        import azzx_cli as a
        p = a.build_parser()
        self.assertEqual(p.parse_args(["queue", "list"]).queue_action, "list")
        self.assertEqual(p.parse_args(["queue", "submit", "sys.info"]).tool, "sys.info")
        self.assertEqual(p.parse_args(["schedule", "run-due"]).schedule_action, "run-due")
        self.assertEqual(p.parse_args(["recall", "search", "x"]).recall_action, "search")
        self.assertEqual(p.parse_args(["trace", "--limit", "5"]).limit, 5)
        self.assertEqual(p.parse_args(["session", "stale"]).session_action, "stale")
        self.assertEqual(p.parse_args(["skills", "list"]).skill_action, "list")
        ns = p.parse_args(["agent", "--roles"])
        self.assertTrue(ns.roles)
        ns = p.parse_args(["agent", "do", "things", "--agents", "planner,tester"])
        self.assertEqual(ns.text, ["do", "things"])
        self.assertEqual(ns.agents, "planner,tester")

    def test_hermes_shim_parses(self):
        import azzx_cli as a
        p = a.build_parser()
        ns = p.parse_args(["hermes", "think", "x"])
        self.assertEqual(ns.command, "hermes")


class RuntimeDetectTest(unittest.TestCase):
    def test_detect_runtime(self):
        from azzx.core import detect_runtime
        info = detect_runtime()
        self.assertIn("os", info)
        self.assertIn("python", info)
        self.assertIn("termux", info)
        self.assertIsInstance(info["termux"], bool)


if __name__ == "__main__":
    unittest.main()

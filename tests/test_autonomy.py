"""Tests for AZZX v10.5 autonomous agent: sandbox, planning, learning,
checkpoints, autonomy loop, and the new CLI commands.

Provider-dependent paths use MockAdapter (offline, deterministic).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


def _tmp():
    return Path(tempfile.mkdtemp(prefix="azzx-auto-test-"))


def _mock_router(adapter):
    from azzx.agent.providers import AIRouter
    cfg = {"timeout_seconds": 5, "provider_max_retries": 1}
    providers = {"mock": {"name": "mock", "kind": "openai", "model": "m",
                          "requires_key": False}}
    return AIRouter(cfg, providers, None,
                    adapter_factory=lambda p, k, t: adapter)


def _patch_router(testcase, adapter):
    import azzx.agent.providers as providers_mod
    router = _mock_router(adapter)
    orig = providers_mod.default_router
    providers_mod.default_router = lambda *a, **k: router
    testcase.addCleanup(setattr, providers_mod, "default_router", orig)
    return router


PLAN_JSON = json.dumps({
    "goal": "check system health",
    "steps": [
        {"id": "s1", "title": "read system health", "tool": "sys.health",
         "args": {}, "why": "baseline", "risk": "low"},
        {"id": "s2", "title": "record a todo", "tool": "todo.add",
         "args": {"title": "follow-up review"}, "why": "tracking", "risk": "low"},
    ],
    "risks": [],
    "needs_clarification": [],
})

DISTILL_JSON = json.dumps({
    "memories": [
        {"content": "system health checks run via sys.health",
         "type": "fact", "importance": 0.6, "tags": ["ops"]},
        {"content": "api_key = 'supersecretvalue123'",
         "type": "fact", "importance": 0.9, "tags": []},
    ],
    "skill_ideas": [
        {"id": "health_check", "name": "Health Check",
         "description": "Run sys.health and summarize",
         "why": "repeatable ops procedure"},
    ],
})


class SandboxTest(unittest.TestCase):
    def test_local_echo(self):
        from azzx.agent.sandbox import get_sandbox_executor
        r = get_sandbox_executor().run("echo hello", timeout=10, backend="local")
        self.assertTrue(r.ok)
        self.assertIn("hello", r.stdout)

    def test_timeout_kills(self):
        from azzx.agent.sandbox import get_sandbox_executor
        r = get_sandbox_executor().run("sleep 10", timeout=1, backend="local")
        self.assertTrue(r.timed_out)
        self.assertFalse(r.ok)

    def test_cwd_jail(self):
        from azzx.agent.sandbox import get_sandbox_executor
        wd = _tmp()
        r = get_sandbox_executor().run("pwd", workdir=str(wd), timeout=10, backend="local")
        self.assertTrue(r.ok)
        self.assertEqual(r.stdout.strip(), str(wd.resolve()))

    def test_env_secrets_scrubbed(self):
        from azzx.agent.sandbox import get_sandbox_executor
        os.environ["AZZX_TEST_API_KEY"] = "super-secret-value-123"
        try:
            r = get_sandbox_executor().run("env", timeout=10, backend="local")
        finally:
            del os.environ["AZZX_TEST_API_KEY"]
        self.assertTrue(r.ok)
        self.assertNotIn("super-secret-value-123", r.stdout)

    def test_empty_command_rejected(self):
        from azzx.agent.sandbox import get_sandbox_executor
        with self.assertRaises(ValueError):
            get_sandbox_executor().run("   ", backend="local")

    def test_backends_lists_local(self):
        from azzx.agent.sandbox import get_sandbox_executor
        self.assertIn("local", get_sandbox_executor().backends())

    def test_sandbox_tool_registered(self):
        from azzx.agent.orchestrator import register_all
        from azzx.core import REGISTRY
        register_all()
        spec = REGISTRY.get("sandbox.exec")
        self.assertIn("sandbox.execute", spec.permissions)


class PlanningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        import azzx.agent.planning as planning_mod
        self._orig_home = planning_mod.DATA_HOME
        planning_mod.DATA_HOME = self.tmp / "data"
        planning_mod._TODOS.clear()
        self.addCleanup(setattr, planning_mod, "DATA_HOME", self._orig_home)
        self.addCleanup(planning_mod._TODOS.clear)

    def test_generate_plan_parses_and_saves(self):
        from azzx.agent.providers import MockAdapter
        import azzx.agent.planning as planning_mod
        _patch_router(self, MockAdapter(script={0: PLAN_JSON}))
        plan = planning_mod.generate_plan("check system health",
                                          project_root=str(self.tmp))
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["steps"][0]["tool"], "sys.health")
        self.assertTrue(Path(plan["path"]).is_file())

    def test_todo_crud(self):
        import azzx.agent.planning as planning_mod
        todos = planning_mod.get_todo_list("unittest-ns")
        item = todos.add("write more tests")
        self.assertEqual(len(todos.list()), 1)
        todos.done(item["id"])
        self.assertTrue(todos.list()[0]["done"])
        todos.clear()
        self.assertEqual(todos.list(), [])

    def test_todo_tools_registered(self):
        from azzx.agent.orchestrator import register_all, run_tool_call
        from azzx.core import REGISTRY
        register_all()
        for name in ("todo.add", "todo.list", "todo.done", "todo.clear"):
            REGISTRY.get(name)
        out = run_tool_call("todo.add", {"title": "t", "namespace": "unittest-toolns"},
                            noninteractive=True, force_yes=True)
        self.assertIn("id", out)


class LearningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        import azzx.agent.learning as learning_mod
        import azzx.agent.memory as memory_mod
        self._patches = []
        for mod, attr in ((learning_mod, "DATA_HOME"), (memory_mod, "DATA_HOME")):
            self._patches.append((mod, attr, getattr(mod, attr)))
            setattr(mod, attr, self.tmp / "data")
        memory_mod._DEFAULT_MEMORY_STORE = None
        self.addCleanup(self._restore)

    def _restore(self):
        import azzx.agent.memory as memory_mod
        for mod, attr, val in self._patches:
            setattr(mod, attr, val)
        memory_mod._DEFAULT_MEMORY_STORE = None

    def test_distill_stages_and_skips_secrets(self):
        from azzx.agent.providers import MockAdapter
        from azzx.agent import learning
        _patch_router(self, MockAdapter(script={0: DISTILL_JSON}))
        out = learning.distill("check health", "s1 [sys.health] OK: {...}")
        # 1 memory staged (the secret one must be refused), 1 skill staged
        self.assertEqual(out["memories_staged"], 1)
        self.assertEqual(out["skills_staged"], 1)
        pending = learning.list_pending()
        self.assertEqual(len([m for m in pending["memories"] if m["status"] == "pending"]), 1)
        self.assertNotIn("supersecretvalue123", json.dumps(pending))

    def test_approve_memory_lands_in_store(self):
        from azzx.agent.providers import MockAdapter
        from azzx.agent import learning
        from azzx.agent.memory import get_memory_store
        _patch_router(self, MockAdapter(script={0: DISTILL_JSON}))
        learning.distill("check health", "s1 ok")
        res = learning.approve("memory", 0, agent_id="tester")
        self.assertIn("memory_id", res)
        hits = get_memory_store().search("system health checks", agent_id="tester")
        self.assertTrue(any("sys.health" in h.content for h in hits))

    def test_discard(self):
        from azzx.agent.providers import MockAdapter
        from azzx.agent import learning
        _patch_router(self, MockAdapter(script={0: DISTILL_JSON}))
        learning.distill("check health", "s1 ok")
        res = learning.discard("skill", 0)
        self.assertEqual(res["discarded"], "skill")
        pending = learning.list_pending()
        self.assertEqual(pending["skills"][0]["status"], "discarded")


class CheckpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        import azzx.agent.checkpoints as cp_mod
        self._orig = cp_mod.DATA_HOME
        cp_mod.DATA_HOME = self.tmp / "data"
        self.addCleanup(setattr, cp_mod, "DATA_HOME", self._orig)
        self.work = self.tmp / "work"
        self.work.mkdir()
        (self.work / "app.txt").write_text("v1")

    def test_create_and_rollback(self):
        from azzx.agent import checkpoints
        cp = checkpoints.create(str(self.work), label="before change")
        (self.work / "app.txt").write_text("v2-broken")
        (self.work / "new.txt").write_text("junk")
        res = checkpoints.rollback(cp["id"])
        self.assertEqual((self.work / "app.txt").read_text(), "v1")
        self.assertTrue(res["restored_files"] >= 1)

    def test_list_and_prune(self):
        from azzx.agent import checkpoints
        checkpoints.create(str(self.work))
        checkpoints.create(str(self.work))
        self.assertEqual(len(checkpoints.list_checkpoints()), 2)
        out = checkpoints.prune(keep=1)
        self.assertEqual(out["removed"], 1)


class AutonomyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        self.work = self.tmp / "work"
        self.work.mkdir()
        import azzx.agent.planning as planning_mod
        import azzx.agent.learning as learning_mod
        import azzx.agent.checkpoints as cp_mod
        import azzx.agent.memory as memory_mod
        self._mods = []
        for mod in (planning_mod, learning_mod, cp_mod, memory_mod):
            self._mods.append((mod, getattr(mod, "DATA_HOME")))
            mod.DATA_HOME = self.tmp / "data"
        planning_mod._TODOS.clear()
        memory_mod._DEFAULT_MEMORY_STORE = None
        self.addCleanup(self._restore)

    def _restore(self):
        import azzx.agent.planning as planning_mod
        import azzx.agent.memory as memory_mod
        for mod, val in self._mods:
            mod.DATA_HOME = val
        planning_mod._TODOS.clear()
        memory_mod._DEFAULT_MEMORY_STORE = None

    def test_auto_run_happy_path(self):
        from azzx.agent.providers import MockAdapter
        from azzx.agent.autonomy import AutonomousRunner
        _patch_router(self, MockAdapter(script={0: PLAN_JSON, 1: DISTILL_JSON}))
        runner = AutonomousRunner(workdir=str(self.work), max_steps=10,
                                  auto_approve=True, namespace="auto-test")
        result = runner.run("check system health")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["steps_completed"], 2)
        self.assertEqual(result["steps_failed"], 0)
        self.assertEqual(result["learned"]["memories_staged"], 1)

    def test_auto_deny_is_absolute(self):
        from azzx.agent.providers import MockAdapter
        from azzx.agent.autonomy import AutonomousRunner
        from azzx.core import load_config, save_config
        deny_plan = json.dumps({
            "goal": "run something sandboxed",
            "steps": [{"id": "s1", "title": "run in sandbox", "tool": "sandbox.exec",
                       "args": {"command": "touch PWNED", "workdir": str(self.work)},
                       "why": "test", "risk": "high"}],
            "risks": [], "needs_clarification": [],
        })
        _patch_router(self, MockAdapter(script={0: deny_plan, 1: DISTILL_JSON}))
        cfg = load_config()
        original = dict(cfg.get("permissions") or {})
        try:
            cfg["permissions"]["sandbox.execute"] = "deny"
            save_config(cfg)
            runner = AutonomousRunner(workdir=str(self.work), max_steps=10,
                                      auto_approve=True, namespace="auto-deny-test")
            result = runner.run("run something sandboxed")
        finally:
            cfg["permissions"] = original
            save_config(cfg)
        # -y must NOT bypass deny: step fails, file never created
        self.assertNotEqual(result["status"], "ok")
        self.assertFalse((self.work / "PWNED").exists())

    def test_auto_ask_user_tool_stops(self):
        from azzx.agent.providers import MockAdapter
        from azzx.agent.autonomy import AutonomousRunner
        stuck_plan = json.dumps({
            "goal": "do the impossible",
            "steps": [{"id": "s1", "title": "ask the human", "tool": "ask_user",
                       "args": {}, "why": "blocked", "risk": "low"}],
            "risks": [], "needs_clarification": [],
        })
        _patch_router(self, MockAdapter(script={0: stuck_plan, 1: DISTILL_JSON}))
        runner = AutonomousRunner(workdir=str(self.work), auto_approve=True,
                                  namespace="auto-stuck-test")
        result = runner.run("do the impossible")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["steps_failed"], 1)


class NewCommandsParserTest(unittest.TestCase):
    def test_new_parsers(self):
        import azzx_cli as a
        p = a.build_parser()
        for argv in (["auto", "do stuff"], ["plan", "do stuff"], ["learn", "list"],
                     ["checkpoint", "list"], ["exec", "backends"], ["chat"]):
            args = p.parse_args(argv)
            self.assertTrue(args.command in ("auto", "plan", "learn", "checkpoint", "exec", "chat"),
                            argv)


if __name__ == "__main__":
    unittest.main()


class AuditFixesTest(unittest.TestCase):
    def test_todo_ids_monotonic_after_clear(self):
        from azzx.agent.planning import TodoList
        import tempfile
        from pathlib import Path
        # Use an isolated namespace per test run
        import time as _t
        ns = f"audit-{int(_t.time()*1000)}"
        todos = TodoList(namespace=ns)
        a = todos.add("first")["id"]
        b = todos.add("second")["id"]
        todos.done(a)
        todos.clear()  # removes done "first"
        c = todos.add("third")["id"]
        ids = [i["id"] for i in todos.list()]
        self.assertEqual(len(ids), len(set(ids)), "todo ids collided after clear")
        self.assertIn(c, ids)

    def test_checkpoint_rollback_keeps_new_files_and_pre_snapshots(self):
        from azzx.agent import checkpoints as C
        from pathlib import Path
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="azzx-ckpt-"))
        (tmp / "a.txt").write_text("v1")
        # isolate checkpoint storage (patch the name as imported in checkpoints)
        orig = C.DATA_HOME
        C.DATA_HOME = Path(tempfile.mkdtemp(prefix="azzx-ckpt-data-"))
        try:
            cp = C.create(str(tmp), label="t1")
            (tmp / "a.txt").write_text("v2")
            (tmp / "new.txt").write_text("created after checkpoint")
            res = C.rollback(cp["id"])
            self.assertEqual((tmp / "a.txt").read_text(), "v1")
            # overlay semantics: new files are kept, not deleted
            self.assertTrue((tmp / "new.txt").is_file())
            # pre-rollback checkpoint exists so rollback is reversible
            self.assertIn("pre_rollback_checkpoint", res)
            C.get(res["pre_rollback_checkpoint"])
        finally:
            C.DATA_HOME = orig


class SandboxAndroidTest(unittest.TestCase):
    def test_android_skips_rlimit_as(self):
        import resource
        import azzx.agent.sandbox as sbx
        calls = []
        real_setrlimit = resource.setrlimit
        real_is_android = sbx._is_android
        try:
            resource.setrlimit = lambda *a: calls.append(a)  # type: ignore
            sbx._is_android = lambda: True  # type: ignore
            sbx._posix_limits(10)()
            kinds = [c[0] for c in calls]
            self.assertIn(resource.RLIMIT_CPU, kinds)
            self.assertNotIn(resource.RLIMIT_AS, kinds)
        finally:
            resource.setrlimit = real_setrlimit  # type: ignore
            sbx._is_android = real_is_android  # type: ignore

    def test_desktop_applies_rlimit_as(self):
        import resource
        import azzx.agent.sandbox as sbx
        calls = []
        real_setrlimit = resource.setrlimit
        real_is_android = sbx._is_android
        try:
            resource.setrlimit = lambda *a: calls.append(a)  # type: ignore
            sbx._is_android = lambda: False  # type: ignore
            sbx._posix_limits(10)()
            kinds = [c[0] for c in calls]
            self.assertIn(resource.RLIMIT_CPU, kinds)
            self.assertIn(resource.RLIMIT_AS, kinds)
        finally:
            resource.setrlimit = real_setrlimit  # type: ignore
            sbx._is_android = real_is_android  # type: ignore

    def test_is_android_detection(self):
        import azzx.agent.sandbox as sbx
        real_prefix = os.environ.get("PREFIX")
        real_root = os.environ.get("ANDROID_ROOT")
        try:
            os.environ.pop("ANDROID_ROOT", None)
            os.environ["PREFIX"] = "/data/data/com.termux/files/usr"
            self.assertTrue(sbx._is_android())
        finally:
            if real_prefix is None:
                os.environ.pop("PREFIX", None)
            else:
                os.environ["PREFIX"] = real_prefix
            if real_root is not None:
                os.environ["ANDROID_ROOT"] = real_root

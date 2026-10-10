"""Tests for AZZX v10.5 companion wave: cron, companion profile, session
search, telegram gateway logic, scheduler cron jobs, mcp.call tool."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="azzx-cmp-test-"))


class CronUtilTest(unittest.TestCase):
    def test_parse_fields(self):
        from azzx.agent.cronutil import parse_cron
        spec = parse_cron("*/15 9-17 * * 1-5")
        self.assertEqual(spec["minute"], {0, 15, 30, 45})
        self.assertEqual(spec["hour"], set(range(9, 18)))
        self.assertEqual(spec["day-of-week"], {1, 2, 3, 4, 5})

    def test_parse_star(self):
        from azzx.agent.cronutil import parse_cron
        spec = parse_cron("* * * * *")
        self.assertEqual(len(spec["minute"]), 60)

    def test_bad_expressions_rejected(self):
        from azzx.agent.cronutil import parse_cron
        from azzx.core import AzzxError
        for bad in ("bad", "* * * *", "61 * * * *", "*/0 * * * *", "* * * * 8"):
            with self.assertRaises(AzzxError, msg=bad):
                parse_cron(bad)

    def test_next_time_every_minute(self):
        from azzx.agent.cronutil import next_cron_time
        nxt = next_cron_time("* * * * *")
        self.assertGreater(nxt, time.time())
        self.assertLess(nxt - time.time(), 130)

    def test_next_time_specific(self):
        from azzx.agent.cronutil import next_cron_time
        # Next midnight: between 1 min and 24h+ away.
        nxt = next_cron_time("0 0 * * *")
        delta = nxt - time.time()
        self.assertGreater(delta, 0)
        self.assertLess(delta, 25 * 3600)


class SchedulerCronTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        import azzx.agent.scheduler as sched_mod
        self._orig = sched_mod.DATA_HOME
        sched_mod.DATA_HOME = self.tmp
        from azzx.agent.orchestrator import register_all
        register_all()
        self.addCleanup(setattr, sched_mod, "DATA_HOME", self._orig)

    def test_add_cron_job(self):
        from azzx.agent.scheduler import ToolScheduler
        sched = ToolScheduler(path=self.tmp / "schedules.json")
        job = sched.add("sys.health", {}, 3600, name="cron-test", cron="*/5 * * * *")
        self.assertEqual(job["cron"], "*/5 * * * *")
        self.assertGreater(job["next_run"], time.time())

    def test_add_bad_cron_rejected(self):
        from azzx.agent.scheduler import ToolScheduler
        from azzx.core import AzzxError
        sched = ToolScheduler(path=self.tmp / "schedules.json")
        with self.assertRaises(AzzxError):
            sched.add("sys.health", {}, 3600, cron="not a cron")

    def test_run_due_advances_cron(self):
        from azzx.agent.scheduler import ToolScheduler
        sched = ToolScheduler(path=self.tmp / "schedules.json")
        job = sched.add("sys.health", {}, 3600, cron="* * * * *")
        # Force it due now.
        import json
        jobs = json.loads((self.tmp / "schedules.json").read_text())
        jobs[0]["next_run"] = time.time() - 1
        (self.tmp / "schedules.json").write_text(json.dumps(jobs))
        report = sched.run_due()
        self.assertEqual(report["executed"], 1)
        jobs = json.loads((self.tmp / "schedules.json").read_text())
        self.assertGreater(jobs[0]["next_run"], time.time())


class CompanionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        import azzx.agent.companion as comp_mod
        import azzx.agent.memory as memory_mod
        self._orig_profile = comp_mod.PROFILE_PATH
        comp_mod.PROFILE_PATH = self.tmp / "profile.json"
        self._orig_data = memory_mod.DATA_HOME
        memory_mod.DATA_HOME = self.tmp / "data"
        memory_mod._DEFAULT_MEMORY_STORE = None
        self.addCleanup(self._restore)

    def _restore(self):
        import azzx.agent.companion as comp_mod
        import azzx.agent.memory as memory_mod
        comp_mod.PROFILE_PATH = self._orig_profile
        memory_mod.DATA_HOME = self._orig_data
        memory_mod._DEFAULT_MEMORY_STORE = None

    def test_profile_roundtrip(self):
        from azzx.agent.companion import get_profile, save_profile
        self.assertEqual(get_profile(), {})
        saved = save_profile({"name": "Budi", "language": "id", "timezone": "", "notes": "suka kopi"})
        self.assertEqual(saved["name"], "Budi")
        self.assertEqual(get_profile()["name"], "Budi")

    def test_prompt_uses_name(self):
        from azzx.agent.companion import save_profile, companion_system_prompt
        save_profile({"name": "Budi", "language": "id", "timezone": "", "notes": ""})
        prompt = companion_system_prompt()
        self.assertIn("Budi", prompt)

    def test_remember_fact(self):
        from azzx.agent.companion import remember_fact
        from azzx.agent.memory import get_memory_store
        res = remember_fact("user suka kopi tubruk")
        self.assertIn("memory_id", res)
        hits = get_memory_store().search("kopi", agent_id="user")
        self.assertTrue(hits)

    def test_remember_refuses_secrets(self):
        from azzx.agent.companion import remember_fact
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            remember_fact("api_key = 'supersecretvalue123'")


class SessionSearchTest(unittest.TestCase):
    def test_search_finds_sessions_and_events(self):
        from azzx.agent.session import SessionMemoryJournal
        tmp = _tmp()
        journal = SessionMemoryJournal(root=tmp)
        sid = journal.start_session("demo", "cron test title")
        journal.log_event(sid, "user", "note", "testing the new scheduler")
        journal.start_session("other", "unrelated")
        res = journal.search("scheduler")
        self.assertEqual(len(res["sessions"]), 0)  # title has no "scheduler"
        self.assertEqual(len(res["events"]), 1)
        res2 = journal.search("cron test")
        self.assertEqual(len(res2["sessions"]), 1)

    def test_empty_query(self):
        from azzx.agent.session import SessionMemoryJournal
        journal = SessionMemoryJournal(root=_tmp())
        self.assertEqual(journal.search(""), [])


class TelegramGatewayTest(unittest.TestCase):
    def _gw(self, **kw):
        from azzx.gateway.telegram import TelegramGateway
        kw.setdefault("token", "123456:ABCDEF-test-token")
        return TelegramGateway(**kw)

    def test_bad_token_rejected(self):
        from azzx.gateway.telegram import TelegramGateway
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            TelegramGateway("not-a-token")

    def test_help_response_offline(self):
        gw = self._gw()
        reply = gw._respond("/help")
        self.assertIn("/auto", reply)
        self.assertIn("/autoy", reply)

    def test_unauthorized_chat_ignored(self):
        gw = self._gw(allow_from={111})
        calls = []
        orig_send = gw._send
        gw._send = lambda cid, text: calls.append((cid, text))
        try:
            gw._handle_update(
                {"update_id": 1,
                 "message": {"chat": {"id": 999}, "text": "hello"}},
                lambda m: None)
        finally:
            gw._send = orig_send
        self.assertEqual(calls, [])


class McpToolRegisteredTest(unittest.TestCase):
    def test_mcp_call_registered(self):
        from azzx.agent.orchestrator import register_all
        from azzx.core import REGISTRY
        register_all()
        spec = REGISTRY.get("mcp.call")
        self.assertIn("mcp.execute", spec.permissions)


if __name__ == "__main__":
    unittest.main()

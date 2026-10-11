"""Tests for AZZX v10.6.5: auto-chaining + browser two modes."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class WebFormsTest(unittest.TestCase):
    def test_form_parser(self):
        from azzx.agent.webforms import _FormParser
        html = '''
        <html><body>
        <form action="/search" method="get">
          <input type="text" name="q" value="">
          <input type="hidden" name="src" value="web">
          <input type="submit" value="Go">
        </form>
        <form action="https://x.example/login" method="POST">
          <input type="text" name="user">
          <input type="password" name="pw">
        </form>
        </body></html>'''
        p = _FormParser("https://s.example/page")
        p.feed(html)
        self.assertEqual(len(p.forms), 2)
        self.assertEqual(p.forms[0]["action"], "https://s.example/search")
        self.assertEqual(p.forms[0]["method"], "GET")
        names = [i["name"] for i in p.forms[0]["inputs"]]
        self.assertIn("q", names)
        self.assertIn("src", names)
        self.assertEqual(p.forms[1]["method"], "POST")
        pw = [i for i in p.forms[1]["inputs"] if i["name"] == "pw"][0]
        self.assertEqual(pw["type"], "password")

    def test_mode_roundtrip(self):
        import azzx.agent.webforms as WF
        import azzx.core as core
        tmp = Path(tempfile.mkdtemp()) / "config.json"
        real = core.CONFIG_FILE
        core.CONFIG_FILE = tmp
        # webforms imported CONFIG_FILE at call time via azzx.core, so patch there
        try:
            self.assertEqual(WF.browser_mode(), "read")  # default, no file
            WF.set_browser_mode("write")
            self.assertEqual(WF.browser_mode(), "write")
            self.assertEqual(json.loads(tmp.read_text())["browser_mode"], "write")
            WF.set_browser_mode("read")
            self.assertEqual(WF.browser_mode(), "read")
            with self.assertRaises(Exception):
                WF.set_browser_mode("nonsense")
        finally:
            core.CONFIG_FILE = real

    def test_submit_blocked_in_read_mode(self):
        import azzx.agent.webforms as WF
        import azzx.core as core
        tmp = Path(tempfile.mkdtemp()) / "config.json"
        real = core.CONFIG_FILE
        core.CONFIG_FILE = tmp
        try:
            WF.set_browser_mode("read")
            with self.assertRaises(Exception) as cm:
                WF.submit("https://s.example/", 0, {})
            self.assertIn("READ mode", str(cm.exception))
        finally:
            core.CONFIG_FILE = real

    def _has_tool(self, name):
        from azzx.agent.orchestrator import REGISTRY
        try:
            REGISTRY.get(name)
            return True
        except Exception:
            return False

    def test_tools_registered(self):
        from azzx.agent.orchestrator import register_all, REGISTRY
        register_all()
        for name in ("web.forms", "web.submit", "web.session_close"):
            self.assertTrue(self._has_tool(name), name)

    def test_submit_tool_needs_write_permission(self):
        from azzx.agent.orchestrator import register_all, REGISTRY
        register_all()
        spec = REGISTRY.get("web.submit")
        self.assertIn("browser.write", spec.permissions)

    def test_webauto_parsers(self):
        import azzx_cli as a
        p = a.build_parser()
        args = p.parse_args(["webauto", "do thing", "--write", "-y"])
        self.assertTrue(args.write)
        self.assertTrue(args.yes)
        args = p.parse_args(["browse", "mode", "write"])
        self.assertEqual(args.value, "write")
        args = p.parse_args(["browse", "forms", "https://x.example/"])
        self.assertEqual(args.url, "https://x.example/")
        args = p.parse_args(["browse", "submit", "https://x.example/",
                             "--form", "1", "--field", "q=hi", "--field", "p=2"])
        self.assertEqual(args.form, 1)
        self.assertEqual(args.field, ["q=hi", "p=2"])


class AutochainTest(unittest.TestCase):
    def test_learn_note(self):
        from azzx.agent.autochain import learn_note
        self.assertIn("skipped", learn_note(None))
        self.assertIn("3 proposal", learn_note({"memories_staged": 2, "skills_staged": 1}))
        self.assertIn("nothing new", learn_note({"memories_staged": 0, "skills_staged": 0}))

    def test_recall_empty_never_raises(self):
        from azzx.agent.autochain import recall_block
        # No memory configured in test env -> must return "" not raise.
        out = recall_block("some random query xyz")
        self.assertIsInstance(out, str)

    def test_auto_learn_no_provider_skipped(self):
        from azzx.agent.autochain import auto_learn
        # Empty transcript -> None without touching the provider.
        self.assertIsNone(auto_learn("goal", ""))

    def test_fix_parsers_have_flags(self):
        import azzx_cli as a
        p = a.build_parser()
        for cmd in ("fix", "add", "implement", "review"):
            argv = [cmd, "x"] if cmd != "review" else [cmd]
            args = p.parse_args(argv)
            self.assertTrue(hasattr(args, "no_recall"), cmd)
            self.assertTrue(hasattr(args, "no_learn"), cmd)


if __name__ == "__main__":
    unittest.main()

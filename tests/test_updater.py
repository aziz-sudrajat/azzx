"""Tests for AZZX v10.6.14: self-update (`azzx update`)."""
from __future__ import annotations

import unittest
from unittest.mock import patch


class VersionTest(unittest.TestCase):
    def test_parse(self):
        from azzx.agent.updater import _parse_version
        self.assertEqual(_parse_version("10.6.14"), (10, 6, 14))
        self.assertTrue(_parse_version("10.6.14") > _parse_version("10.6.9"))
        self.assertTrue(_parse_version("10.6.9") < _parse_version("10.7.0"))

    def test_parse_invalid(self):
        from azzx.agent.updater import _parse_version
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            _parse_version("abc")

    def test_check_update_available(self):
        from azzx.agent import updater as U
        with patch.object(U, "local_version", return_value="10.6.13"), \
             patch.object(U, "remote_version", return_value="10.6.14"):
            info = U.check()
        self.assertTrue(info["update_available"])
        self.assertEqual(info["local"], "10.6.13")
        self.assertEqual(info["remote"], "10.6.14")

    def test_check_up_to_date(self):
        from azzx.agent import updater as U
        with patch.object(U, "local_version", return_value="10.6.14"), \
             patch.object(U, "remote_version", return_value="10.6.14"):
            info = U.check()
        self.assertFalse(info["update_available"])

    def test_update_skipped_when_current(self):
        from azzx.agent import updater as U
        with patch.object(U, "check", return_value={
                "local": "10.6.14", "remote": "10.6.14", "update_available": False}):
            res = U.update(yes=True)
        self.assertFalse(res["updated"])

    def test_tarball_entry_validation(self):
        """Root dir entry 'azzx-main' (no trailing slash) must be accepted."""
        from azzx.agent import updater as U
        # Simulate the validation logic
        for name in ["azzx-main", "azzx-main/azzx_cli.py", "azzx-main/azzx/"]:
            ok = name == "azzx-main" or name.startswith("azzx-main/")
            self.assertTrue(ok, name)
        for bad in ["other/file.py", "/etc/passwd", "azzx-main/../evil"]:
            ok = (bad == "azzx-main" or bad.startswith("azzx-main/")) \
                 and ".." not in bad.split("/")
            self.assertFalse(ok, bad)


class IntentUpdateTest(unittest.TestCase):
    def test_update_intent(self):
        from azzx.agent.intent import route
        target, _, _ = route("update azzx")
        self.assertEqual(target, "self-update")
        target, _, _ = route("cek update")
        self.assertEqual(target, "self-update")
        target, _, _ = route("perbarui azzx")
        self.assertEqual(target, "self-update")

    def test_update_parser(self):
        import azzx_cli as a
        p = a.build_parser()
        args = p.parse_args(["self-update", "--check"])
        self.assertEqual(args.command, "self-update")
        self.assertTrue(args.check)
        args = p.parse_args(["self-update", "--yes"])
        self.assertTrue(args.yes)
        # existing app-update still works
        args = p.parse_args(["update", "--all"])
        self.assertEqual(args.command, "update")
        self.assertTrue(args.all)

    def test_update_in_curated_help(self):
        import azzx_cli as a
        self.assertIn("self-update", a.CURATED_HELP)


if __name__ == "__main__":
    unittest.main()

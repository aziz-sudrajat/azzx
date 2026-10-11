"""Tests for AZZX v10.6.10: self-improvement loop (`azzx evolve`)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch


class AnalyzeTest(unittest.TestCase):
    def test_empty_audit(self):
        from azzx.agent import evolve as E
        with patch("azzx.agent.auditor._iter_entries", return_value=[]):
            f = E.analyze()
        self.assertEqual(f["total_calls"], 0)
        self.assertIn("note", f)

    def test_habits_and_failures(self):
        from azzx.agent import evolve as E
        entries = []
        # habit: web.fetch 5x ok
        for _ in range(5):
            entries.append({"kind": "tool_call", "tool": "web.fetch", "ok": True})
        # failure hotspot: web.submit 3x error
        for _ in range(3):
            entries.append({"kind": "tool_call", "tool": "web.submit",
                            "ok": False, "error_kind": "timeout"})
        # sequence: fetch -> submit repeated 4x
        seq = []
        for _ in range(4):
            seq.append({"kind": "tool_call", "tool": "a", "ok": True})
            seq.append({"kind": "tool_call", "tool": "b", "ok": True})
        with patch("azzx.agent.auditor._iter_entries", return_value=entries + seq):
            f = E.analyze()
        self.assertEqual(f["top_tools"][0]["tool"], "web.fetch")
        hot = {h["tool"]: h for h in f["failure_hotspots"]}
        self.assertIn("web.submit", hot)
        self.assertEqual(hot["web.submit"]["total"], 3)
        seqs = {(s["first"], s["then"]) for s in f["common_sequences"]}
        self.assertIn(("a", "b"), seqs)


class ProposalLifecycleTest(unittest.TestCase):
    def _tmp_proposals(self, tmp):
        from azzx.agent import evolve as E
        import azzx.agent.evolve as Em
        orig = Em.PROPOSALS_FILE
        Em.PROPOSALS_FILE = tmp / "proposals.json"
        return E, Em, orig

    def test_reject_unknown(self):
        import tempfile
        from pathlib import Path
        from azzx.core import AzzxError
        with tempfile.TemporaryDirectory() as td:
            E, Em, orig = self._tmp_proposals(Path(td))
            try:
                with self.assertRaises(AzzxError):
                    E.reject("nope1234")
            finally:
                Em.PROPOSALS_FILE = orig

    def test_protected_files_blocked(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            E, Em, orig = self._tmp_proposals(Path(td))
            try:
                items = [{
                    "id": "abc123", "type": "fix", "title": "t",
                    "description": "d", "changes": [{"file": "x/permissions.py", "kind": "patch"}],
                    "risk": "high", "test": "", "status": "pending", "created": 0,
                }]
                Em._save_proposals(items)
                from azzx.core import AzzxError
                with self.assertRaises(AzzxError):
                    E.approve("abc123")
                # still pending after blocked approve
                self.assertEqual(Em.list_proposals()[0]["status"], "pending")
                # reject works
                E.reject("abc123")
                self.assertEqual(Em.list_proposals(), [])
            finally:
                Em.PROPOSALS_FILE = orig


class DiffApplierTest(unittest.TestCase):
    def test_apply_simple_diff(self):
        import tempfile
        from pathlib import Path
        from azzx.agent.evolve import _apply_diff
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "x.py"
            f.write_text("a = 1\nb = 2\nc = 3\n")
            diff = (
                "--- a/x.py\n+++ b/x.py\n"
                "@@ -1,3 +1,3 @@\n"
                " a = 1\n"
                "-b = 2\n"
                "+b = 20\n"
                " c = 3\n"
            )
            _apply_diff(f, diff)
            self.assertEqual(f.read_text(), "a = 1\nb = 20\nc = 3\n")

    def test_apply_add_line(self):
        import tempfile
        from pathlib import Path
        from azzx.agent.evolve import _apply_diff
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "x.py"
            f.write_text("a = 1\n")
            diff = (
                "--- a/x.py\n+++ b/x.py\n"
                "@@ -1 +1,2 @@\n"
                " a = 1\n"
                "+b = 2\n"
            )
            _apply_diff(f, diff)
            self.assertEqual(f.read_text(), "a = 1\nb = 2\n")


class IntentEvolveTest(unittest.TestCase):
    def test_evolve_intent(self):
        from azzx.agent.intent import route
        target, _, _ = route("kembangkan dirimu")
        self.assertEqual(target, "evolve")
        target, _, _ = route("belajar dari kebiasaanku")
        self.assertEqual(target, "evolve")

    def test_evolve_parser(self):
        import azzx_cli as a
        p = a.build_parser()
        args = p.parse_args(["evolve", "analyze"])
        self.assertEqual(args.command, "evolve")
        self.assertEqual(args.evolve_action, "analyze")
        args = p.parse_args(["evolve", "approve", "abc123"])
        self.assertEqual(args.proposal_id, "abc123")


if __name__ == "__main__":
    unittest.main()

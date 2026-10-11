"""Tests for AZZX v10.6.1: auditor agent + token compressor."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="azzx-ac-test-"))


class AuditorTest(unittest.TestCase):
    def setUp(self):
        import azzx.agent.auditor as A
        import azzx.core as core
        self._orig_data = A.DATA_HOME
        self._orig_file = A.AUDIT_FILE
        self._orig_dir = A.AUDIT_DIR
        tmp = _tmp()
        A.DATA_HOME = tmp
        A.AUDIT_DIR = tmp / "agent" / "audit"
        A.AUDIT_FILE = A.AUDIT_DIR / "audit.jsonl"
        self.A = A

    def tearDown(self):
        A = self.A
        A.DATA_HOME = self._orig_data
        A.AUDIT_FILE = self._orig_file
        A.AUDIT_DIR = self._orig_dir

    def test_run_lifecycle(self):
        A = self.A
        rid = A.start_run("test goal")
        self.assertTrue(rid.startswith("run-"))
        self.assertEqual(A.current_run_id(), rid)
        with A.audit_call("demo.tool", {"x": 1}):
            pass
        try:
            with A.audit_call("demo.tool", {"x": 2}):
                raise ValueError("boom")
        except ValueError:
            pass
        A.end_run("done")
        self.assertEqual(A.current_run_id(), "adhoc")
        calls = A.recent_calls(run_id=rid)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0]["ok"])
        self.assertFalse(calls[1]["ok"])
        self.assertEqual(calls[1]["error_kind"], "error")

    def test_secret_redaction(self):
        A = self.A
        rid = A.start_run("redact")
        with A.audit_call("demo.tool", {"api_key": "supersecretvalue123",
                                        "note": "hello"}):
            pass
        A.end_run()
        calls = A.recent_calls(run_id=rid)
        self.assertEqual(calls[0]["args"]["api_key"], "[redacted]")
        self.assertEqual(calls[0]["args"]["note"], "hello")

    def test_report_findings(self):
        A = self.A
        rid = A.start_run("findings")
        for _ in range(3):
            try:
                with A.audit_call("flaky.tool", {}):
                    raise RuntimeError("nope")
            except RuntimeError:
                pass
        A.end_run()
        rep = A.report(rid)
        self.assertEqual(rep["calls"], 3)
        self.assertEqual(rep["failed"], 3)
        self.assertTrue(any("REPEATED FAILURE" in f for f in rep["findings"]))
        self.assertNotEqual(rep["rule_verdict"], "pass")
        self.assertLess(rep["rule_score"], 100)

    def test_report_no_entries(self):
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            self.A.report("run-nonexistent")

    def test_stats(self):
        A = self.A
        rid = A.start_run("stats")
        with A.audit_call("good.tool", {}):
            pass
        A.end_run()
        s = A.stats()
        self.assertEqual(s["total_calls"], 1)
        self.assertEqual(s["success_rate"], 1.0)

    def test_audit_never_breaks(self):
        # audit_call must not raise even if logging fails
        A = self.A
        A.AUDIT_DIR = Path("/proc/cannot-write-here")
        A.AUDIT_FILE = A.AUDIT_DIR / "audit.jsonl"
        with A.audit_call("demo.tool", {}):
            pass  # should not raise


class CompressorTest(unittest.TestCase):
    def test_signatures_python(self):
        from azzx.agent.compressor import compress_text
        src = '''"""Module doc."""
import os

def alpha(a, b):
    """Does alpha."""
    x = 1
    y = 2
    return x + y

class Beta:
    """Beta class."""
    def gamma(self, q):
        """Does gamma."""
        return [i for i in range(1000)]
'''
        res = compress_text(src * 30, 2000, "signatures", filename="m.py")
        self.assertEqual(res["strategy"], "signatures")
        self.assertIn("def alpha(a, b):", res["text"])
        self.assertIn("class Beta:", res["text"])
        self.assertIn("def gamma(self, q):", res["text"])
        self.assertNotIn("range(1000)", res["text"])  # body dropped
        self.assertLess(res["compressed_chars"], res["original_chars"])

    def test_head_tail(self):
        from azzx.agent.compressor import compress_text
        text = "\n".join(f"line {i}" for i in range(1000))
        res = compress_text(text, 500, "head_tail")
        self.assertIn("line 0", res["text"])
        self.assertIn("line 999", res["text"])
        self.assertLessEqual(len(res["text"]), 600)

    def test_extractive_query(self):
        from azzx.agent.compressor import compress_text
        text = "apple banana\n" * 50 + "IMPORTANT: the vault password policy\n" + "cherry date\n" * 50
        res = compress_text(text, 600, "extractive", query="vault password policy")
        self.assertIn("vault password policy", res["text"])

    def test_auto_python(self):
        from azzx.agent.compressor import compress_text
        src = "def f():\n    return 1\n" * 200
        res = compress_text(src, 1000, "auto", filename="x.py")
        self.assertEqual(res["strategy"], "signatures")

    def test_already_fits(self):
        from azzx.agent.compressor import compress_text
        res = compress_text("short", 8000)
        self.assertEqual(res["strategy"], "none (already fits)")
        self.assertEqual(res["text"], "short")

    def test_compress_file(self):
        from azzx.agent.compressor import compress_file
        tmp = _tmp() / "big.py"
        tmp.write_text("def f():\n    pass\n" * 500)
        res = compress_file(tmp, 1000)
        self.assertEqual(res["file"], str(tmp))
        self.assertLess(res["compressed_chars"], res["original_chars"])

    def test_compress_file_missing(self):
        from azzx.agent.compressor import compress_file
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            compress_file("/no/such/file.py")

    def test_estimate_tokens(self):
        from azzx.agent.compressor import estimate_tokens
        self.assertEqual(estimate_tokens("a" * 400), 100)

    def test_bad_strategy(self):
        from azzx.agent.compressor import compress_text
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            compress_text("x" * 2000, 800, "nope")


class NewParsersTest(unittest.TestCase):
    def test_parsers(self):
        import azzx_cli as a
        p = a.build_parser()
        for argv in (["audit", "stats"], ["audit", "list"],
                     ["compress", "README.md"]):
            args = p.parse_args(argv)
            self.assertIn(args.command, ("audit", "compress"), argv)
        args = p.parse_args(["audit", "report", "--run", "run-abc", "--judge"])
        self.assertTrue(args.judge)


if __name__ == "__main__":
    unittest.main()


class AuditorClassifyTest(unittest.TestCase):
    def test_permission_denied_classified(self):
        from azzx.agent.auditor import _classify_error
        from azzx.core import PermissionDenied, AzzxError
        self.assertEqual(_classify_error(PermissionDenied("nope")), "denied")
        self.assertEqual(_classify_error(AzzxError("denied by policy")), "denied")
        self.assertEqual(_classify_error(ValueError("boom")), "error")
        self.assertEqual(_classify_error(TimeoutError("timed out")), "timeout")


class AttachmentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(_tmp())
        (self.tmp / "main.py").write_text("def hello():\n    return 1\n" * 40)
        (self.tmp / "notes.txt").write_text("hello notes\n" * 10)

    def test_mention_attaches(self):
        from azzx.agent.attachments import resolve_mentions
        msg, ctx = resolve_mentions("analisa @main.py", self.tmp)
        self.assertIn("def hello", ctx)
        self.assertIn("@main.py", msg)

    def test_escape_blocked(self):
        from azzx.agent.attachments import resolve_mentions
        _, ctx = resolve_mentions("baca @../secret", self.tmp)
        self.assertIn("outside workspace", ctx)

    def test_missing_is_skip_note(self):
        from azzx.agent.attachments import resolve_mentions
        _, ctx = resolve_mentions("baca @nope.py", self.tmp)
        self.assertIn("SKIP", ctx)

    def test_resolve_in_root(self):
        from azzx.agent.attachments import resolve_in_root
        self.assertIsNotNone(resolve_in_root(self.tmp, "notes.txt"))
        self.assertIsNone(resolve_in_root(self.tmp, "../x"))
        self.assertIsNone(resolve_in_root(self.tmp, "nope.txt"))

    def test_session_attachments(self):
        from azzx.agent.attachments import session_attachments
        ctx = session_attachments([self.tmp / "notes.txt"], self.tmp)
        self.assertIn("hello notes", ctx)
        self.assertEqual(session_attachments([], self.tmp), "")

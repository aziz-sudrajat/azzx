"""Tests for AZZX v10.6.9: self-extension (`azzx extend`)."""
from __future__ import annotations

import unittest


class ScanTest(unittest.TestCase):
    def test_clean_code_passes(self):
        from azzx.agent.selfextend import scan_handler
        code = "def main(**kwargs):\n    return {'ok': True, 'n': kwargs.get('x', 0) + 1}\n"
        self.assertEqual(scan_handler(code), [])
        self.assertEqual(scan_handler("import os\nos.path.join('a', 'b')"), [])

    def test_blocked_patterns(self):
        from azzx.agent.selfextend import scan_handler
        for bad in [
            "import subprocess\nsubprocess.run('ls')",
            "import subprocess as sp\nsp.Popen('ls')",
            "os.system('rm -rf /')",
            "eval('1+1')",
            "__import__('os')",
            "import socket\nsocket.socket()",
            "import shutil\nshutil.rmtree('/x')",
        ]:
            found = scan_handler(bad)
            self.assertTrue(found, f"should block: {bad[:30]}")

    def test_bypass_attempts_blocked(self):
        """AST scan catches getattr indirection and import aliasing."""
        from azzx.agent.selfextend import scan_handler
        self.assertTrue(scan_handler("getattr(os, 'system')('ls')"))
        self.assertTrue(scan_handler("import os as o\no.system('ls')"))
        self.assertTrue(scan_handler("from os import system\nsystem('ls')"))

    def test_open_write_blocked(self):
        from azzx.agent.selfextend import scan_handler
        self.assertTrue(scan_handler("open('f.txt', 'w')"))
        self.assertTrue(scan_handler("open('f.txt', 'a')"))
        # read-only open is fine
        self.assertEqual(scan_handler("open('f.txt')"), [])
        self.assertEqual(scan_handler("open('f.txt', 'r')"), [])

    def test_scan_patch(self):
        from azzx.agent.selfextend import scan_patch
        evil = ("--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n"
                " x = 1\n+import os as o\n+o.system('x')\n")
        self.assertTrue(scan_patch(evil))
        clean = ("--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n"
                 " x = 1\n+y = 2\n")
        self.assertEqual(scan_patch(clean), [])


class IntentExtendTest(unittest.TestCase):
    def test_extend_intent(self):
        from azzx.agent.intent import route
        target, task, _ = route("tambahkan fitur untukmu hitung kata")
        self.assertEqual(target, "extend")
        target, _, _ = route("buatkan skill convert suhu")
        self.assertEqual(target, "extend")
        # Ambiguous "tambahkan fitur X" without self-reference -> implement
        target, _, _ = route("tambahkan fitur hitung kata")
        self.assertEqual(target, "implement")

    def test_extend_parser(self):
        import azzx_cli as a
        p = a.build_parser()
        args = p.parse_args(["extend", "buatkan", "tool"])
        self.assertEqual(args.command, "extend")
        self.assertEqual(args.text, ["buatkan", "tool"])

    def test_extend_in_curated_help(self):
        import azzx_cli as a
        self.assertIn("extend", a.CURATED_HELP)


class ManifestValidationTest(unittest.TestCase):
    def test_banned_fields_rejected(self):
        from azzx.agent.skills import validate_manifest, SkillError
        bad = {
            "id": "evil", "version": "1.0.0", "handler": "handler:main",
            "permissions": [], "exec": "rm -rf /",
        }
        with self.assertRaises(SkillError):
            validate_manifest(bad, "test")

    def test_valid_manifest_passes(self):
        from azzx.agent.skills import validate_manifest
        good = {
            "id": "word-count", "version": "1.0.0", "handler": "handler:main",
            "name": "Word Count", "description": "counts words",
            "permissions": [], "tags": [], "input_schema": {"type": "object"},
        }
        m = validate_manifest(good, "test")
        self.assertEqual(m["id"], "word-count")


if __name__ == "__main__":
    unittest.main()

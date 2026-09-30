#!/usr/bin/env python3
"""v10 unit tests: toolkit, workflow safety, mirror dry-run, plugins, NL mapping."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolated XDG dirs
_TD = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = str(Path(_TD.name) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_TD.name) / "data")

from azzx.agent.orchestrator import map_nl_to_tool, register_all, run_tool_call, describe_tools_for_ai
from azzx.core import AzzxError, PermissionDenied, REGISTRY, load_config, save_config
from azzx.workflow.engine import create_workflow, run_workflow, list_workflows, delete_workflow
from azzx.plugins.loader import validate_manifest, install_plugin, list_plugins
from azzx.device.mirror import mirror_start, detect_scrcpy
from azzx.tools.archive import archive_create, archive_extract
from azzx.tools.hashutil import file_checksum
from azzx.tools.filesystem import file_search, largest_files


class V10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Allow permissions for noninteractive tests
        cfg = load_config()
        perms = cfg.get("permissions") or {}
        for cap in list(perms.keys()):
            perms[cap] = "allow"
        # also set new caps
        for cap in (
            "device.adb", "device.mirror", "workflow.run", "plugin.install",
            "process.inspect", "archive.write", "filesystem.read", "filesystem.write",
            "network.http", "shell.run",
        ):
            perms[cap] = "allow"
        cfg["permissions"] = perms
        save_config(cfg)
        register_all()

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_registry_has_core_tools(self):
        names = {t.name for t in REGISTRY.list_tools()}
        for required in (
            "fs.search", "fs.largest", "fs.duplicates", "hash.file",
            "sys.health", "git.status", "net.connectivity",
            "device.mirror.status", "device.adb.detect", "archive.create",
        ):
            self.assertIn(required, names)

    def test_file_search_and_largest(self):
        (self.root / "a.txt").write_text("hi")
        (self.root / "b.bin").write_bytes(b"x" * 5000)
        r = file_search(str(self.root), "*.txt", limit=10)
        self.assertGreaterEqual(r["count"], 1)
        big = largest_files(str(self.root), limit=5)
        self.assertTrue(any(f["path"].endswith("b.bin") for f in big["files"]))

    def test_checksum(self):
        f = self.root / "x.txt"
        f.write_text("hello")
        h = file_checksum(str(f), "sha256")
        self.assertEqual(len(h["hash"]), 64)

    def test_archive_path_traversal_blocked(self):
        import tarfile
        evil = self.root / "evil.tar"
        with tarfile.open(evil, "w") as tf:
            import io
            info = tarfile.TarInfo(name="../outside.txt")
            data = b"pwn"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        dest = self.root / "out"
        dest.mkdir()
        with self.assertRaises(AzzxError):
            archive_extract(str(evil), str(dest))

    def test_archive_roundtrip(self):
        src = self.root / "data"
        src.mkdir()
        (src / "f.txt").write_text("ok")
        arc = self.root / "p.tar.gz"
        archive_create(str(src), str(arc), "tar.gz")
        self.assertTrue(arc.is_file())
        out = self.root / "extracted"
        out.mkdir()
        archive_extract(str(arc), str(out))
        self.assertTrue(any(out.rglob("f.txt")))

    def test_workflow_rejects_unknown_tool(self):
        with self.assertRaises(AzzxError):
            create_workflow("bad", [{"tool": "shell.run_anything", "args": {}}])

    def test_workflow_run_registered(self):
        create_workflow("healthcheck", [{"tool": "sys.info", "args": {}}], overwrite=True)
        result = run_workflow("healthcheck", noninteractive=True)
        self.assertTrue(result["ok"])
        delete_workflow("healthcheck")

    def test_nl_mapping_safe(self):
        m = map_nl_to_tool("show system health")
        self.assertIsNotNone(m)
        self.assertEqual(m["tool"], "sys.health")
        m2 = map_nl_to_tool("rm -rf /")
        self.assertIsNone(m2)

    def test_mirror_dry_run(self):
        # Should not require a real device for dry_run structure validation
        # May fail if scrcpy missing — accept either structured result or AzzxError about scrcpy
        try:
            r = mirror_start(dry_run=True, max_size=1024)
            self.assertTrue(r.get("dry_run"))
            self.assertIn("command", r)
            # command must be a list, not a shell string
            self.assertIsInstance(r["command"], list)
        except AzzxError as exc:
            self.assertIn("scrcpy", str(exc).lower())

    def test_plugin_manifest_validation(self):
        ok = validate_manifest({
            "id": "demo-tools",
            "version": "1.0.0",
            "tools": ["demo.hello"],
            "permissions": ["filesystem.read"],
            "entrypoint": "plugin.py",
        })
        self.assertEqual(ok["id"], "demo-tools")
        with self.assertRaises(AzzxError):
            validate_manifest({"id": "x", "permissions": ["root.everything"]})
        with self.assertRaises(AzzxError):
            validate_manifest({"id": "x", "shell": "rm -rf /"})

    def test_plugin_install_local(self):
        src = self.root / "myplug"
        src.mkdir()
        (src / "manifest.json").write_text(json.dumps({
            "id": "sampleplug",
            "version": "0.1.0",
            "tools": [],
            "permissions": [],
            "entrypoint": "plugin.py",
            "description": "test",
        }))
        (src / "plugin.py").write_text("def register(registry):\n    pass\n")
        r = install_plugin(str(src), force=True)
        self.assertEqual(r["installed"], "sampleplug")
        ids = [p.get("id") for p in list_plugins()]
        self.assertIn("sampleplug", ids)

    def test_describe_tools_for_ai(self):
        tools = describe_tools_for_ai()
        self.assertGreater(len(tools), 10)
        self.assertTrue(all("name" in t and "schema" in t for t in tools))


if __name__ == "__main__":
    unittest.main()

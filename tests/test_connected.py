"""Tests for AZZX v10.6 'Connected': GUI server, web reader, connectors,
autonomous web agent."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="azzx-conn-test-"))


class GUIServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from azzx.gui.server import GUIHandler
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 18911), GUIHandler)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _get(self, path):
        with urlopen(f"http://127.0.0.1:18911{path}") as r:
            return r.status, r.read()

    def test_index_serves_chat(self):
        code, body = self._get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"AZZX", body)
        self.assertIn(b"/api/chat/stream", body)

    def test_health(self):
        code, body = self._get("/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_tools(self):
        code, body = self._get("/api/tools")
        self.assertEqual(code, 200)
        self.assertIn("tools", json.loads(body))

    def test_404(self):
        try:
            self._get("/nope")
            self.fail("expected HTTPError")
        except Exception as exc:
            self.assertIn("404", str(exc))


class WebReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (b"<html><head><title>T</title></head><body>"
                b"<script>evil()</script><p>Hello <b>world</b></p>"
                b'<a href="/x">Next</a></body></html>')

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(html)
            def log_message(self, *a):
                pass

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 18912), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_fetch_parses(self):
        import azzx.agent.webreader as wr
        orig = wr._check_url
        wr._check_url = lambda u: u  # bypass SSRF guard for localhost test
        try:
            page = wr.fetch("http://127.0.0.1:18912/")
        finally:
            wr._check_url = orig
        self.assertEqual(page["title"], "T")
        self.assertIn("Hello world", page["text"])
        self.assertNotIn("evil()", page["text"])
        self.assertEqual(page["links"][0]["href"], "http://127.0.0.1:18912/x")

    def test_ssrf_guard(self):
        from azzx.agent.webreader import fetch
        from azzx.core import AzzxError
        with self.assertRaises(AzzxError):
            fetch("http://127.0.0.1:18912/")

    def test_tools_registered(self):
        from azzx.agent.orchestrator import register_all
        from azzx.core import REGISTRY
        register_all()
        self.assertIn("web.read", REGISTRY.get("web.fetch").permissions)
        REGISTRY.get("web.links")


class ConnectorToolsTest(unittest.TestCase):
    def test_tools_registered(self):
        from azzx.agent.orchestrator import register_all
        from azzx.core import REGISTRY
        register_all()
        for name, perm in (("github.repos", "connector.github"),
                           ("github.list_issues", "connector.github"),
                           ("github.create_issue", "connector.github"),
                           ("email.inbox", "connector.email"),
                           ("email.send", "connector.email")):
            self.assertIn(perm, REGISTRY.get(name).permissions)

    def test_github_without_token_fails_cleanly(self):
        import azzx_cli
        from azzx.agent import connectors as C
        from azzx.core import AzzxError
        # Point vault at a temp config home
        import os
        old_cfg, old_data = os.environ.get("XDG_CONFIG_HOME"), os.environ.get("XDG_DATA_HOME")
        tmp = str(_tmp())
        os.environ["XDG_CONFIG_HOME"] = tmp
        os.environ["XDG_DATA_HOME"] = tmp
        try:
            # Fresh vault in temp home: no github_pat
            with self.assertRaises(AzzxError):
                C.github_repos()
        finally:
            if old_cfg is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old_cfg
            if old_data is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_data



class NewParsersTest(unittest.TestCase):
    def test_parsers(self):
        import azzx_cli as a
        p = a.build_parser()
        for argv in (["gui"], ["browse", "fetch", "https://example.com"],
                     ["connector", "list"], ["connector", "list"]):
            args = p.parse_args(argv)
            self.assertIn(args.command, ("gui", "browse", "connector"), argv)


if __name__ == "__main__":
    unittest.main()


class WebSearchParserTest(unittest.TestCase):
    def test_ddg_parser(self):
        from azzx.agent.webreader import _DDGParser
        html = (b'<html><body>'
                b'<div class="result"><div class="result__body">'
                b'<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&amp;rut=x">Example Title</a>'
                b'</div></div>'
                b'<div class="result"><div class="result__body">'
                b'<a class="result__a" href="https://direct.example/y">Direct</a>'
                b'</div></div></body></html>')
        p = _DDGParser()
        p.feed(html.decode())
        self.assertEqual(len(p.results), 2)
        self.assertEqual(p.results[0]["href"], "https://example.com/page")
        self.assertEqual(p.results[0]["title"], "Example Title")
        self.assertEqual(p.results[1]["href"], "https://direct.example/y")

    def test_search_tool_registered(self):
        from azzx.agent.orchestrator import register_all
        from azzx.core import REGISTRY
        register_all()
        self.assertIn("web.read", REGISTRY.get("web.search").permissions)


class WebAgentLoopTest(unittest.TestCase):
    def _pages(self):
        return {
            "https://s.example/start": {
                "final_url": "https://s.example/start",
                "title": "Start", "text": "nothing here",
                "links": [{"text": "Next page", "href": "https://s.example/answer"}]},
            "https://s.example/answer": {
                "final_url": "https://s.example/answer",
                "title": "Answer", "text": "The capital is Jakarta.",
                "links": []},
        }

    def test_loop_follows_and_answers(self):
        from azzx.agent.webagent import WebAgent
        pages = self._pages()
        calls = []

        def fake_fetch(url):
            return pages[url]

        def fake_decide(task, page, trail):
            calls.append(page["final_url"])
            if "capital" in page["text"]:
                return {"action": "answer", "answer": "Jakarta"}
            return {"action": "follow", "url": "https://s.example/answer"}

        agent = WebAgent(max_steps=5, fetcher=fake_fetch, decider=fake_decide)
        res = agent.run("what is the capital?", start_url="https://s.example/start")
        self.assertEqual(res["status"], "answered")
        self.assertEqual(res["answer"], "Jakarta")
        self.assertEqual(res["steps"], 2)
        self.assertEqual(len(calls), 2)

    def test_blocks_hallucinated_url(self):
        from azzx.agent.webagent import WebAgent
        pages = self._pages()

        def evil_decide(task, page, trail):
            return {"action": "follow", "url": "https://evil.example/"}

        agent = WebAgent(max_steps=5, fetcher=lambda u: pages[u], decider=evil_decide)
        res = agent.run("x", start_url="https://s.example/start")
        self.assertEqual(res["status"], "blocked")

    def test_max_steps(self):
        from azzx.agent.webagent import WebAgent
        pages = self._pages()
        # answer page links back to start -> genuine loop through listed links
        pages["https://s.example/answer"]["links"] = [
            {"text": "Back", "href": "https://s.example/start"}]

        def loop_decide(task, page, trail):
            nxt = [l["href"] for l in page["links"]][0]
            return {"action": "follow", "url": nxt}

        agent = WebAgent(max_steps=3, fetcher=lambda u: pages[u], decider=loop_decide)
        res = agent.run("x", start_url="https://s.example/start")
        self.assertEqual(res["status"], "max_steps")
        self.assertEqual(res["steps"], 3)

    def test_webauto_parser(self):
        import azzx_cli as a
        p = a.build_parser()
        args = p.parse_args(["webauto", "cari harga kopi", "--max-steps", "5"])
        self.assertEqual(args.command, "webauto")
        self.assertEqual(args.max_steps, 5)
        args = p.parse_args(["browse", "search", "kopi"])
        self.assertEqual(args.browse_action, "search")

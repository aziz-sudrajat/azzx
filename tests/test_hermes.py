"""Unit tests for v10.2 Hermes-like features (unittest, offline)."""
import base64
import json
import os
import tempfile
import unittest

os.environ.setdefault("AZZX_CONFIG_HOME", tempfile.mkdtemp(prefix="azzx-test-home-"))


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
        q = "kucing peliharaan makan"
        scored = emb.most_similar(q, [(i, emb.embed(d)) for i, d in enumerate(docs)], limit=3)
        # Doc 0 (cat) must outrank doc 1 (dog); doc 2 shares "ikan/dapur" weakly.
        order = [i for i, _ in scored]
        self.assertLess(order.index(0), order.index(1))
        self.assertGreater(scored[0][1], 0.0)

    def test_embedder_persists(self):
        from azzx.agent.embeddings import SimpleEmbedder
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "tfidf.json")
            emb = SimpleEmbedder(p)
            emb.add_document("hello world test")
            emb.save()
            emb2 = SimpleEmbedder(p)
            self.assertEqual(emb2.doc_count, 1)
            self.assertGreater(emb2.similarity(emb2.embed("hello"), emb2.embed("hello world")), 0.5)


class SemanticMemoryTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        from azzx.agent.memory import MemoryStore
        self.store = MemoryStore(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_semantic_finds_paraphrase(self):
        self.store.store(agent_id="a", content="kucing saya suka makan ikan setiap pagi", memory_type="fact")
        self.store.store(agent_id="a", content="jadwal meeting proyek hari senin jam sembilan", memory_type="fact")
        self.store.store(agent_id="a", content="anjing tetangga menggonggong sepanjang malam", memory_type="fact")
        hits = self.store.search_semantic("hewan peliharaan kucing makan", limit=3)
        self.assertTrue(hits)
        top_entry, top_score = hits[0]
        self.assertIn("kucing", top_entry.content)
        self.assertGreater(top_score, 0.0)

    def test_hybrid_returns_scores(self):
        self.store.store(agent_id="a", content="database postgres backup otomatis tiap malam", memory_type="fact")
        hits = self.store.search_hybrid("backup database", limit=3)
        self.assertTrue(hits)
        entry, score = hits[0]
        self.assertIn("backup", entry.content)
        self.assertGreaterEqual(score, 0.0)

    def test_rebuild_vectors(self):
        self.store.store(agent_id="a", content="satu dua tiga", memory_type="fact")
        n = self.store.rebuild_vectors()
        self.assertEqual(n, 1)
        hits = self.store.search_semantic("satu", limit=1)
        self.assertTrue(hits)


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
        rendered = t.render()
        self.assertIn("fix bug", rendered)
        self.assertIn("CONCLUSION", rendered)

    def test_invalid_kind_raises(self):
        from azzx.agent.reasoning import ReasoningTrace
        t = ReasoningTrace(task="x")
        with self.assertRaises(ValueError):
            t.add("daydream", "...")


class TracerTest(unittest.TestCase):
    def test_nested_spans_and_timeline(self):
        from azzx.agent.tracer import Tracer
        tr = Tracer(log_path=os.path.join(tempfile.mkdtemp(), "trace.jsonl"))
        with tr.span("outer", kind="task"):
            with tr.span("inner", kind="tool", tool="sys.info"):
                pass
        tl = tr.timeline()
        self.assertEqual(len(tl), 2)
        kinds = {s["kind"] for s in tl}
        self.assertEqual(kinds, {"task", "tool"})
        inner = next(s for s in tl if s["name"] == "inner")
        outer = next(s for s in tl if s["name"] == "outer")
        self.assertEqual(inner["parent_id"], outer["id"])
        self.assertGreaterEqual(inner["duration_ms"], 0)

    def test_error_span(self):
        from azzx.agent.tracer import Tracer
        tr = Tracer(log_path=os.path.join(tempfile.mkdtemp(), "trace.jsonl"))
        with self.assertRaises(RuntimeError):
            with tr.span("boom", kind="tool"):
                raise RuntimeError("kablam")
        tl = tr.timeline()
        self.assertEqual(tl[0]["status"], "error")
        self.assertIn("kablam", tl[0]["error"])

    def test_global_tracer_singleton(self):
        from azzx.agent.tracer import get_tracer
        self.assertIs(get_tracer(), get_tracer())


class TaskQueueTest(unittest.TestCase):
    def test_callable_roundtrip(self):
        from azzx.agent.tasks import TaskQueue
        with tempfile.TemporaryDirectory() as td:
            q = TaskQueue(os.path.join(td, "q.json"))
            tid = q.submit("adder", lambda x, y: x + y, {"x": 2, "y": 3})
            snap = q.result(tid, timeout=10)
            self.assertEqual(snap["status"], "done")
            self.assertEqual(snap["result"], 5)

    def test_tool_roundtrip(self):
        from azzx.agent.orchestrator import register_all
        from azzx.agent.tasks import TaskQueue
        register_all()
        with tempfile.TemporaryDirectory() as td:
            q = TaskQueue(os.path.join(td, "q.json"))
            tid = q.submit_tool("sys.info", {})
            snap = q.result(tid, timeout=15)
            self.assertEqual(snap["status"], "done")
            self.assertIsInstance(snap["result"], dict)

    def test_failed_task_reports_error(self):
        from azzx.agent.tasks import TaskQueue
        with tempfile.TemporaryDirectory() as td:
            q = TaskQueue(os.path.join(td, "q.json"))
            tid = q.submit_tool("no.such.tool", {})
            snap = q.result(tid, timeout=10)
            self.assertEqual(snap["status"], "error")
            self.assertTrue(snap["error"])

    def test_drainer_claims_and_completes(self):
        from azzx.agent.orchestrator import register_all
        from azzx.agent.tasks import TaskQueue
        register_all()
        with tempfile.TemporaryDirectory() as td:
            state = os.path.join(td, "q.json")
            q = TaskQueue(state, auto_worker=False)
            tid = q.submit_tool("sys.info", {})
            ok = q.drain(timeout=20)
            self.assertTrue(ok)
            snap = TaskQueue(state, auto_worker=False).status(tid)
            self.assertEqual(snap["status"], "done")
            self.assertIsInstance(snap["result"], dict)


class StreamingTest(unittest.TestCase):
    def test_token_stream_accumulates(self):
        from azzx.agent.streaming import TokenStream
        ts = TokenStream()
        ts.feed("halo ")
        ts.feed("dunia")
        self.assertEqual(ts.text, "halo dunia")
        self.assertFalse(ts.finished)
        ts.finish(provider_id="p", model="m")
        self.assertTrue(ts.finished)
        self.assertEqual(ts.provider_id, "p")

    def test_openai_sse_parsing(self):
        import httpx
        from azzx_cli import OpenAICompatibleAdapter

        lines = [
            'data: {"choices":[{"delta":{"content":"Halo"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":" dunia"}}]}',
            "data: [DONE]",
        ]

        class FakeStream:
            is_success = True
            status_code = 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def iter_lines(self):
                return iter(lines)

        class FakeClient:
            def __init__(self, *a, **k):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def stream(self, *a, **k):
                return FakeStream()

        real_client = httpx.Client
        httpx.Client = FakeClient
        try:
            adapter = OpenAICompatibleAdapter(
                {"base_url": "http://x", "name": "t"}, api_key="k", timeout=5
            )
            tokens = list(adapter.stream_chat([{"role": "user", "content": "hi"}], "m"))
        finally:
            httpx.Client = real_client
        self.assertEqual(tokens, ["Halo", " dunia"])


class VisionTest(unittest.TestCase):
    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAA"
        "AABJRU5ErkJggg=="
    )

    def _png(self, td):
        p = os.path.join(td, "t.png")
        with open(p, "wb") as fh:
            fh.write(base64.b64decode(self.PNG_B64))
        return p

    def test_is_vision_model(self):
        from azzx.agent.vision import is_vision_model
        self.assertTrue(is_vision_model("gpt-4o"))
        self.assertTrue(is_vision_model("claude-3-5-sonnet-20241022"))
        self.assertFalse(is_vision_model("llama-3-8b-instruct"))
        self.assertFalse(is_vision_model(""))

    def test_encode_and_content(self):
        from azzx.agent.vision import encode_image, to_vision_content
        with tempfile.TemporaryDirectory() as td:
            p = self._png(td)
            payload = encode_image(p)
            self.assertTrue(payload["data_url"].startswith("data:image/png;base64,"))
            parts = to_vision_content("describe", [p])
            self.assertEqual(parts[0]["type"], "text")
            self.assertEqual(parts[1]["type"], "image_url")

    def test_missing_image_raises(self):
        from azzx.agent.vision import encode_image
        with self.assertRaises(FileNotFoundError):
            encode_image("/tmp/azzx-no-such-image.png")


class MultiAgentReasoningIntegrationTest(unittest.TestCase):
    def test_delegate_includes_reasoning_and_spans(self):
        from azzx.agent.multi_agent import MultiAgentOrchestrator
        from azzx.agent.tracer import get_tracer
        with tempfile.TemporaryDirectory() as td:
            orch = MultiAgentOrchestrator(memory_dir=td)
            result = orch.delegate("tulis fungsi tambah", "coder")
            reasoning = result.get("reasoning") or {}
            kinds = [s["kind"] for s in reasoning.get("steps", [])]
            for expected in ("thought", "plan", "act", "observe", "reflect", "conclusion"):
                self.assertIn(expected, kinds)
            tl = get_tracer().timeline(limit=50, kind="agent")
            self.assertTrue(any(s["name"] == "delegate:coder" for s in tl))


if __name__ == "__main__":
    unittest.main()

class SchedulerTest(unittest.TestCase):
    def test_schedule_lifecycle_and_due_execution(self):
        from azzx.agent.orchestrator import register_all
        from azzx.agent.scheduler import ToolScheduler
        register_all()
        with tempfile.TemporaryDirectory() as td:
            scheduler = ToolScheduler(os.path.join(td, "schedules.json"))
            job = scheduler.add("sys.info", {}, every_seconds=60, name="health check")
            self.assertEqual(len(scheduler.list()), 1)
            result = scheduler.run_due(now=job["next_run"] + 1)
            self.assertEqual(result["executed"], 1)
            self.assertEqual(result["results"][0]["id"], job["id"])
            self.assertEqual(scheduler.list()[0]["last_status"], "done")
            self.assertTrue(scheduler.remove(job["id"]))
            self.assertEqual(scheduler.list(), [])

    def test_schedule_rejects_too_frequent_interval(self):
        from azzx.agent.orchestrator import register_all
        from azzx.agent.scheduler import ToolScheduler
        from azzx.core import AzzxError
        register_all()
        with tempfile.TemporaryDirectory() as td:
            scheduler = ToolScheduler(os.path.join(td, "schedules.json"))
            with self.assertRaises(AzzxError):
                scheduler.add("sys.info", {}, every_seconds=1)

class TaskQueueRaceRegressionTest(unittest.TestCase):
    def test_terminal_status_is_persisted_for_many_fast_tasks(self):
        from azzx.agent.tasks import TaskQueue
        with tempfile.TemporaryDirectory() as td:
            state = os.path.join(td, "queue.json")
            q = TaskQueue(state)
            ids = [q.submit("identity", lambda value: value, {"value": i}) for i in range(40)]
            for i, task_id in enumerate(ids):
                result = q.result(task_id, timeout=10)
                self.assertEqual(result["status"], "done")
                self.assertEqual(result["result"], i)
            with open(state, encoding="utf-8") as handle:
                persisted = json.load(handle)
            by_id = {item["id"]: item for item in persisted}
            for task_id in ids:
                self.assertEqual(by_id[task_id]["status"], "done")

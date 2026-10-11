"""AZZX GUI server (v10.6): a friendly ChatGPT/Muse-like web chat.

Stdlib ``http.server`` only — no new dependencies, runs fine on low-end
machines. Serves a single-file chat UI (``azzx/gui/static/chat.html``) plus a
small JSON API:

    GET  /                    chat UI
    GET  /api/health          {"ok": true, "version": ...}
    POST /api/chat            {"message": "..."} -> {"reply": "..."}
    GET  /api/chat/stream?message=...   SSE token stream
    GET  /api/tools           registered tool names
    POST /api/auto            {"goal": "..."} -> {"run_id": ...}
    GET  /api/auto/<run_id>   poll autonomous run status

Binds localhost by default. Binding beyond localhost prints a warning:
there is no authentication.
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

STATIC_DIR = Path(__file__).parent / "static"

_AUTO_RUNS: dict[str, dict[str, Any]] = {}
_AUTO_LOCK = threading.Lock()


class GUIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # quiet
        return

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(),
                   "application/json")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            return {}

    # -- routes ------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            html = (STATIC_DIR / "chat.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/health":
            from azzx.core import VERSION
            self._json(200, {"ok": True, "version": VERSION})
            return
        if path == "/api/tools":
            try:
                from azzx.agent.orchestrator import register_all, describe_tools_for_ai
                register_all()
                self._json(200, {"tools": describe_tools_for_ai()})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return
        if path == "/api/chat/stream":
            qs = urllib.parse.parse_qs(parsed.query)
            message = (qs.get("message") or [""])[0]
            self._stream_chat(message)
            return
        if path.startswith("/api/auto/"):
            run_id = path.rsplit("/", 1)[-1]
            with _AUTO_LOCK:
                run = _AUTO_RUNS.get(run_id)
            if not run:
                self._json(404, {"error": "run not found"})
                return
            self._json(200, {k: v for k, v in run.items() if k != "thread"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/chat":
            data = self._read_json()
            message = str(data.get("message", "")).strip()
            if not message:
                self._json(400, {"error": "message required"})
                return
            try:
                reply = _chat_once(message)
                self._json(200, {"reply": reply})
            except Exception as exc:
                self._json(500, {"error": str(exc)[:300]})
            return
        if path == "/api/auto":
            data = self._read_json()
            goal = str(data.get("goal", "")).strip()
            if not goal:
                self._json(400, {"error": "goal required"})
                return
            import uuid
            run_id = uuid.uuid4().hex[:8]
            record: dict[str, Any] = {"id": run_id, "goal": goal,
                                      "status": "running", "result": None}
            with _AUTO_LOCK:
                _AUTO_RUNS[run_id] = record
                # Bound memory: keep only the 50 most recent runs.
                while len(_AUTO_RUNS) > 50:
                    oldest = next(iter(_AUTO_RUNS))
                    if oldest == run_id:
                        break
                    _AUTO_RUNS.pop(oldest, None)

            def _bg() -> None:
                try:
                    from azzx.agent.autonomy import AutonomousRunner
                    runner = AutonomousRunner(auto_approve=True, namespace=f"gui-{run_id}")
                    record["result"] = runner.run(goal)
                    record["status"] = record["result"].get("status", "done")
                except Exception as exc:  # noqa: BLE001
                    record["status"] = "error"
                    record["result"] = {"error": str(exc)[:300]}

            thread = threading.Thread(target=_bg, daemon=True)
            record["thread"] = thread
            thread.start()
            self._json(200, {"run_id": run_id, "status": "running"})
            return
        self._json(404, {"error": "not found"})

    # -- SSE streaming -------------------------------------------------------
    def _stream_chat(self, message: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # NB: no "Connection: keep-alive" — this is a FINITE stream; the
        # client detects completion via connection close. keep-alive here
        # caused clients to wait forever after [DONE] (bug: 2nd+ chat
        # submit hung because `busy` never reset).
        self.close_connection = True
        self.end_headers()
        try:
            for token in _chat_stream(message):
                chunk = "data: " + json.dumps({"token": token}) + "\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            chunk = "data: " + json.dumps({"error": str(exc)[:200]}) + "\n\n"
            try:
                self.wfile.write(chunk.encode("utf-8"))
            except Exception:
                pass
        try:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass


def _with_attachments(message: str) -> str:
    """Append @file mention contents (v10.6.4). Root = server working dir."""
    from pathlib import Path
    from azzx.agent.orchestrator import assemble_memory_prompt
    from azzx.agent import attachments as AT

    message, mention_ctx = AT.resolve_mentions(message, Path.cwd())
    prompt = assemble_memory_prompt(message)
    if mention_ctx:
        prompt = prompt + "\n" + mention_ctx
    return prompt


def _chat_once(message: str) -> str:
    from azzx.agent.companion import companion_system_prompt
    from azzx.agent.providers import default_router

    router = default_router()
    messages = [
        {"role": "system", "content": companion_system_prompt()},
        {"role": "user", "content": _with_attachments(message)},
    ]
    return router.chat(messages, max_tokens=1000).text.strip()


def _chat_stream(message: str):
    from azzx.agent.companion import companion_system_prompt
    from azzx.agent.providers import default_router

    router = default_router()
    messages = [
        {"role": "system", "content": companion_system_prompt()},
        {"role": "user", "content": _with_attachments(message)},
    ]
    for _pid, token in router.stream(messages):
        yield token


def run_gui(host: str = "127.0.0.1", port: int = 8766, open_browser: bool = False) -> None:
    import webbrowser
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: GUI is being bound beyond localhost. It has no authentication.")
    server = ThreadingHTTPServer((host, port), GUIHandler)
    url = f"http://{host}:{port}/"
    print(f"AZZX GUI: {url}  (Ctrl+C to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

"""Regression test for GUI chat bug (v10.6.15): SSE stream must close.

Symptom: first chat submit displayed a response, but subsequent submits
hung — the JS `busy` flag never reset because the server never closed
the SSE connection after [DONE] (it sent `Connection: keep-alive`).
"""
from __future__ import annotations

import socket
import threading
import time
import unittest
from http.server import ThreadingHTTPServer


class StreamCloseTest(unittest.TestCase):
    def test_stream_closes_after_done(self):
        from azzx.gui.server import GUIHandler
        import azzx.gui.server as S

        orig = S._chat_stream
        S._chat_stream = lambda msg: iter(["halo ", "dunia"])  # noqa: E731
        server = ThreadingHTTPServer(("127.0.0.1", 18769), GUIHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        try:
            for i in range(3):
                s = socket.create_connection(("127.0.0.1", 18769), timeout=5)
                s.sendall(f"GET /api/chat/stream?message=hi{i} HTTP/1.0\r\n"
                          f"Host: x\r\n\r\n".encode())
                s.settimeout(5)
                data = b""
                closed = False
                try:
                    while True:
                        chunk = s.recv(4096)
                        if not chunk:
                            closed = True
                            break
                        data += chunk
                except socket.timeout:
                    pass
                finally:
                    s.close()
                self.assertTrue(closed, f"request {i+1}: connection never closed")
                self.assertIn(b"[DONE]", data, f"request {i+1}: missing [DONE]")
                self.assertNotIn(b"keep-alive", data.lower(),
                                 f"request {i+1}: keep-alive header present")
        finally:
            S._chat_stream = orig
            server.shutdown()


if __name__ == "__main__":
    unittest.main()

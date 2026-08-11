"""Local-only HTTP server for tests/fixtures/*.html.

Serves static fixture pages on an ephemeral 127.0.0.1 port so browser
executor tests can drive a real Playwright browser session without ever
reaching a real insurer domain or making an off-localhost request. Two
pieces of dynamic behaviour beyond plain file serving:

- `/flaky.html` returns HTTP 500 on its first request and 200 (serving the
  file's real content) on every request after that, for retry tests.
- a path can have a placeholder string swapped for a per-test value via
  `set_placeholder`, used by the rendered-text-redaction test to inject a
  sentinel value into summary_plaintext.html without hardcoding it into the
  fixture file.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FixtureServer:
    def __init__(self) -> None:
        self._flaky_hits: dict[str, int] = {}
        self._placeholders: dict[str, tuple[str, str]] = {}
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:  # quiet test output
                pass

            def do_GET(self) -> None:  # noqa: N802 - http.server's naming convention
                path = self.path.split("?", 1)[0]
                if path == "/flaky.html":
                    hits = server._flaky_hits.get(path, 0) + 1
                    server._flaky_hits[path] = hits
                    if hits == 1:
                        body = b"<html><body>Internal Server Error</body></html>"
                        self.send_response(500)
                        self.send_header("Content-Type", "text/html")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return

                file_path = FIXTURES_DIR / path.lstrip("/")
                if not file_path.is_file():
                    self.send_response(404)
                    self.end_headers()
                    return

                text = file_path.read_text()
                if path in server._placeholders:
                    placeholder, value = server._placeholders[path]
                    text = text.replace(placeholder, value)
                body = text.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address
        return f"http://127.0.0.1:{port}"

    def url_for(self, name: str) -> str:
        return f"{self.base_url}/{name}"

    def set_placeholder(self, path: str, placeholder: str, value: str) -> None:
        """Substitute `placeholder` for `value` the next time `path` is served."""
        self._placeholders[path] = (placeholder, value)

    def reset_flaky(self, path: str = "/flaky.html") -> None:
        self._flaky_hits.pop(path, None)

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)

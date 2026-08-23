"""GET-only reverse proxy for the small, read-only CPG contract."""
from __future__ import annotations

import http.client
import os
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

CPG_URL = os.getenv("CPG_URL", "https://127.0.0.1:5000")
_ALLOWED = (
    re.compile(r"^/healthz$"),
    re.compile(r"^/v1/api/iserver/auth/status$"),
    re.compile(r"^/v1/api/iserver/accounts$"),
    re.compile(r"^/v1/api/portfolio/accounts$"),
    re.compile(r"^/v1/api/portfolio/[^/]+/(?:summary|ledger|positions/\d+)$"),
)

def allowed(method: str, path: str) -> bool:
    return method == "GET" and any(rule.fullmatch(path) for rule in _ALLOWED)

class Guard(BaseHTTPRequestHandler):
    server_version = "ibkr-cpg-guard"
    def do_GET(self) -> None: self._proxy()
    def do_POST(self) -> None: self._reject()
    def do_PUT(self) -> None: self._reject()
    def do_PATCH(self) -> None: self._reject()
    def do_DELETE(self) -> None: self._reject()
    def do_OPTIONS(self) -> None: self._reject()
    def log_message(self, *_: object) -> None: pass
    def _reject(self) -> None:
        self.send_error(403, "read-only CPG guard")
    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        if not allowed(self.command, parsed.path) or parsed.query:
            return self._reject()
        if parsed.path == "/healthz":
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')
            return
        target = urlsplit(CPG_URL)
        # CPG's local TLS certificate is self-signed; traffic never leaves the
        # loopback interface and the public guard remains plain internal HTTP.
        conn = http.client.HTTPSConnection(target.hostname, target.port or 443, timeout=20,
                                           context=ssl._create_unverified_context())
        try:
            conn.request(
                "GET",
                parsed.path,
                headers={"Accept": "application/json", "User-Agent": "ibkr-cpg-guard/1.0"},
            )
            response = conn.getresponse(); body = response.read()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        except OSError:
            self.send_error(502, "CPG unavailable")
        finally: conn.close()

if __name__ == "__main__":
    ThreadingHTTPServer((os.getenv("GUARD_HOST", "0.0.0.0"), 8080), Guard).serve_forever()

"""Private, token-protected IBKR Gateway login control API."""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from sidecar.login import login

MAX_BODY = 4096
LOGIN_TTL = float(os.getenv("LOGIN_TIMEOUT_SECONDS", "300"))
TOKEN_FILE = Path(os.getenv("CONTROL_TOKEN_FILE", "/run/ibkr-secrets/control-token"))
State = Literal["authenticating", "awaiting_approval", "authenticated", "failed", "expired"]


@dataclass
class Attempt:
    id: str
    state: State
    created: float
    cancelled: threading.Event = field(default_factory=threading.Event)


class LoginManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempt: Attempt | None = None

    def start(self, username: str, password: str) -> str | None:
        with self._lock:
            if self._attempt and self._state(self._attempt) in {"authenticating", "awaiting_approval"}:
                return None
            attempt = Attempt(uuid.uuid4().hex, "authenticating", time.monotonic())
            self._attempt = attempt
        threading.Thread(target=self._run, args=(attempt, username, password), daemon=True).start()
        return attempt.id

    def _run(self, attempt: Attempt, username: str, password: str) -> None:
        def waiting() -> None:
            with self._lock:
                if self._attempt is attempt and attempt.state == "authenticating":
                    attempt.state = "awaiting_approval"

        try:
            authenticated = login(
                username,
                password,
                timeout=LOGIN_TTL,
                on_waiting=waiting,
                cancelled=attempt.cancelled.is_set,
            )
        except Exception:
            authenticated = False
        finally:
            username = password = ""  # drop references; never log them
        with self._lock:
            if self._attempt is attempt and attempt.state not in {"expired", "failed"}:
                attempt.state = "authenticated" if authenticated else "failed"

    def status(self, attempt_id: str) -> State:
        with self._lock:
            if self._attempt is None or not hmac.compare_digest(self._attempt.id, attempt_id):
                return "expired"
            return self._state(self._attempt)

    def cancel(self, attempt_id: str) -> State:
        with self._lock:
            if self._attempt is None or not hmac.compare_digest(self._attempt.id, attempt_id):
                return "expired"
            if self._attempt.state in {"authenticating", "awaiting_approval"}:
                self._attempt.state = "expired"
                self._attempt.cancelled.set()
            return self._attempt.state

    @staticmethod
    def _state(attempt: Attempt) -> State:
        if attempt.state in {"authenticating", "awaiting_approval"} and time.monotonic() - attempt.created >= LOGIN_TTL:
            attempt.state = "expired"
        return attempt.state


MANAGER = LoginManager()


def _token_valid(header: str | None) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    try:
        expected = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(expected) and hmac.compare_digest(expected, header.removeprefix("Bearer "))


class Control(BaseHTTPRequestHandler):
    server_version = "ibkr-cpg-control"

    def log_message(self, *_: object) -> None:
        pass

    def do_POST(self) -> None: self._route()
    def do_GET(self) -> None: self._route()
    def do_PUT(self) -> None: self._method_not_allowed()
    def do_PATCH(self) -> None: self._method_not_allowed()
    def do_DELETE(self) -> None: self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "not found"})

    def _route(self) -> None:
        if not _token_valid(self.headers.get("Authorization")):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        path = urlsplit(self.path)
        if path.query:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if self.command == "POST" and path.path == "/control/v1/login":
            payload = self._json_body()
            if payload is None:
                return
            if set(payload) != {"username", "password"} or not all(isinstance(payload[key], str) and payload[key] for key in payload):
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid request"})
                return
            if len(payload["username"]) > 256 or len(payload["password"]) > 1024:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid request"})
                return
            attempt_id = MANAGER.start(payload["username"], payload["password"])
            if attempt_id is None:
                self._send(HTTPStatus.CONFLICT, {"error": "login already active"})
                return
            self._send(HTTPStatus.ACCEPTED, {"login_id": attempt_id})
            return
        parts = path.path.split("/")
        if len(parts) == 5 and parts[:4] == ["", "control", "v1", "login"] and _valid_id(parts[4]) and self.command == "GET":
            self._send(HTTPStatus.OK, {"login_id": parts[4], "state": MANAGER.status(parts[4])})
            return
        if len(parts) == 6 and parts[:4] == ["", "control", "v1", "login"] and _valid_id(parts[4]) and parts[5] == "cancel" and self.command == "POST":
            self._send(HTTPStatus.OK, {"login_id": parts[4], "state": MANAGER.cancel(parts[4])})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _json_body(self) -> dict[str, object] | None:
        try: length = int(self.headers.get("Content-Length", ""))
        except ValueError: length = -1
        if length < 2 or length > MAX_BODY or self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid request"}); return None
        try: value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid request"}); return None
        if not isinstance(value, dict):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid request"}); return None
        return value

    def _send(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)


def _valid_id(value: str) -> bool:
    return len(value) == 32 and all(character in "0123456789abcdef" for character in value)


def serve() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((os.getenv("CONTROL_HOST", "0.0.0.0"), int(os.getenv("CONTROL_PORT", "8081"))), Control)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

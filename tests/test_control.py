from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from sidecar import control


def _request(server: control.ThreadingHTTPServer, method: str, path: str, token: str | None, body: object | None = None) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body)
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=data, headers=headers)
    response = connection.getresponse()
    return response.status, json.loads(response.read())


def test_control_requires_token_and_strict_login_payload(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "control-token"
    token_file.write_text("token-value\n")
    monkeypatch.setattr(control, "TOKEN_FILE", token_file)
    control.MANAGER = control.LoginManager()
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Control)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _request(server, "POST", "/control/v1/login", None, {"username": "u", "password": "p"})[0] == 401
        assert _request(server, "POST", "/control/v1/login", "wrong", {"username": "u", "password": "p"})[0] == 401
        assert _request(server, "POST", "/control/v1/login", "token-value", {"username": "u", "password": "p", "totp": "x"})[0] == 400
    finally:
        server.shutdown(); server.server_close()


def test_control_rejects_concurrent_login_and_allows_cancel(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "control-token"
    token_file.write_text("token-value\n")
    monkeypatch.setattr(control, "TOKEN_FILE", token_file)
    control.MANAGER = control.LoginManager()
    started = threading.Event()
    release = threading.Event()

    def fake_login(*_args, on_waiting, **_kwargs) -> bool:
        on_waiting(); started.set(); release.wait(2); return False

    monkeypatch.setattr(control, "login", fake_login)
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Control)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = _request(server, "POST", "/control/v1/login", "token-value", {"username": "u", "password": "p"})
        assert status == 202
        login_id = str(body["login_id"])
        assert started.wait(1)
        assert _request(server, "POST", "/control/v1/login", "token-value", {"username": "other", "password": "p"})[0] == 409
        assert _request(server, "GET", f"/control/v1/login/{login_id}", "token-value")[1]["state"] == "awaiting_approval"
        assert _request(server, "POST", f"/control/v1/login/{login_id}/cancel", "token-value")[1]["state"] == "expired"
    finally:
        release.set(); server.shutdown(); server.server_close()

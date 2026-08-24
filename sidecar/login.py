"""One-shot CPG browser login, with credentials kept only in process memory."""
from __future__ import annotations

import json
import ssl
import time
from collections.abc import Callable
from urllib.request import Request, urlopen

CPG_URL = "https://127.0.0.1:5000"


def _authenticated() -> bool:
    request = Request(f"{CPG_URL}/v1/api/iserver/auth/status", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5, context=ssl._create_unverified_context()) as response:
            return bool(json.load(response).get("authenticated"))
    except Exception:  # Provider details are deliberately not exposed or logged.
        return False


def login(
    username: str,
    password: str,
    *,
    timeout: float,
    on_waiting: Callable[[], None],
    cancelled: Callable[[], bool],
) -> bool:
    """Submit the first factor and wait for IB Key approval; no TOTP branch exists."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    deadline = time.monotonic() + timeout
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        try:
            page.goto(CPG_URL, wait_until="domcontentloaded", timeout=30_000)
            page.get_by_label("Username").fill(username)
            page.get_by_label("Password").fill(password)
            page.get_by_role("button", name="Log In").click()
            on_waiting()
            while time.monotonic() < deadline:
                if cancelled():
                    return False
                if _authenticated():
                    return True
                if page.get_by_text("denied", exact=False).count() or page.get_by_text("rejected", exact=False).count():
                    return False
                page.wait_for_timeout(1_000)
            return False
        except PlaywrightTimeoutError:
            return False
        finally:
            context.close()
            browser.close()

"""One-shot CPG browser login with Challenge-Response 2FA support."""
from __future__ import annotations

import json
import logging
import re
import ssl
import sys
import time
import urllib.request
from collections.abc import Callable

CPG_URL = "https://127.0.0.1:5000"
PUSH_DEVICE = re.compile(r"(?:ib\s*key|mobile|push)", re.IGNORECASE)
logger = logging.getLogger(__name__)

_TLS = ssl.create_default_context()
_TLS.check_hostname = False
_TLS.verify_mode = ssl.CERT_NONE


def _log(msg: str) -> None:
    print(f"[IBKR-LOGIN] {msg}", file=sys.stderr, flush=True)


def _cpg_is_authenticated() -> bool:
    try:
        req = urllib.request.Request(f"{CPG_URL}/v1/api/iserver/auth/status")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5, context=_TLS) as resp:
            body = json.loads(resp.read())
            return isinstance(body, dict) and bool(body.get("authenticated"))
    except Exception:
        return False


def _init_brokerage_session(page: object) -> bool:
    """Initialize brokerage session inside browser after SSO succeeds."""
    try:
        return bool(page.evaluate("""
            async () => {
                for (let i = 0; i < 6; i++) {
                    try { await fetch('/v1/api/sso/validate'); } catch {}
                    try {
                        await fetch('/v1/api/iserver/auth/ssodh/init', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({publish: true, compete: true}),
                        });
                    } catch {}
                    try {
                        const r = await fetch('/v1/api/iserver/auth/status', {headers: {Accept: 'application/json'}});
                        if (r.ok) {
                            const body = await r.json();
                            if (body && body.authenticated) return true;
                        }
                    } catch {}
                    await new Promise(res => setTimeout(res, 2000));
                }
                return false;
            }
        """))
    except Exception:
        return False


def login(
    username: str,
    password: str,
    *,
    timeout: float,
    on_waiting: Callable[[str | None], None],
    get_response: Callable[[float], str | None],
    cancelled: Callable[[], bool],
) -> bool:
    from playwright.sync_api import TimeoutError as PwTimeout
    from playwright.sync_api import sync_playwright

    deadline = time.monotonic() + timeout
    _log(f"Starting browser login (timeout={timeout}s)")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--allow-running-insecure-content",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = browser.new_context(
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()

        page.on("console", lambda msg: _log(f"[Browser Console] {msg.type}: {msg.text[:120]}"))
        page.on("pageerror", lambda err: _log(f"[Browser PageError] {err}"))
        page.on("response", lambda resp: _log(f"[Network] {resp.status} {resp.url[:90]}") if any(k in resp.url for k in ["sso", "auth", "iserver", "tickle", "validate", "Dispatcher"]) else None)

        stage = "open_login"
        try:
            _log("Navigating to CPG URL...")
            page.goto(CPG_URL, wait_until="domcontentloaded", timeout=30_000)

            stage = "submit_first_factor"
            _log("Filling credentials...")
            page.get_by_label("Username").fill(username)
            page.get_by_label("Password").fill(password)
            _log("Clicking submit button...")
            page.locator("form.xyzform-username button").click(
                force=True, no_wait_after=True, timeout=10_000,
            )

            stage = "find_push_device"
            _log("Checking for push device selector...")
            push_opt = (
                page.locator("select option").filter(has_text=PUSH_DEVICE).first
            )
            try:
                push_opt.wait_for(state="attached", timeout=10_000)
            except PwTimeout:
                _log("No push selector found, proceeding directly")
            else:
                value = push_opt.get_attribute("value")
                if value:
                    _log(f"Selecting push device option: {value}")
                    page.locator("select").select_option(value=value)

            # Switch to Challenge/Response mode
            page.wait_for_timeout(1000)
            page.evaluate("""() => {
                const el = document.querySelector('a.xyz-showchallenge') || document.querySelector('.xyz-showchallenge');
                if (el) el.click();
            }""")
            page.wait_for_timeout(1000)

            # Extract challenge code
            challenge_str: str | None = None
            try:
                challenge_el = page.locator(".xyz-goldchallenge")
                if challenge_el.count() > 0:
                    challenge_str = challenge_el.first.inner_text().strip()
                    _log(f"Extracted Challenge Code: {challenge_str}")
            except Exception as e:
                _log(f"Failed to extract challenge code: {e}")

            stage = "await_approval"
            _log(f"Notifying waiting state (challenge={challenge_str})...")
            on_waiting(challenge_str)

            # Wait for response code from user
            remaining = max(0.0, deadline - time.monotonic())
            _log(f"Waiting up to {remaining:.1f}s for 2FA response code from user...")
            response_code = get_response(remaining)

            if cancelled():
                _log("Login cancelled by user")
                return False

            if not response_code:
                _log("No response code received within timeout")
                return False

            _log("Submitting response code into CPG...")
            submit_result = page.evaluate("""(code) => {
                const input = document.querySelector('.xyz-gold-response') || document.querySelector('#xyz-field-gold-response');
                const form = document.querySelector('form.xyzform-gold');
                const btn = form ? form.querySelector('button[type="submit"]') : null;
                if (!input || !btn) return false;
                input.value = code;
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));
                btn.click();
                return true;
            }""", response_code)

            if not submit_result:
                _log("Failed to locate gold form input or submit button")
                return False

            _log("Response code submitted! Waiting for authentication result...")
            page.wait_for_timeout(2000)

            # Check for failure error message
            body_text = page.locator("body").inner_text()
            if "Authentication failed" in body_text:
                _log("CPG reported: Authentication failed (invalid response code)")
                return False

            # Initialize brokerage session
            if _init_brokerage_session(page) or _cpg_is_authenticated():
                _log("Brokerage session successfully authenticated! 🎉")
                return True

            # Final check
            if _cpg_is_authenticated():
                _log("CPG authenticated check confirmed!")
                return True

            _log("Brokerage session initialization did not succeed after submission")
            return False

        except PwTimeout:
            _log(f"Browser timeout at stage: {stage}")
            return False
        finally:
            ctx.close()
            browser.close()

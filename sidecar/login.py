"""One-shot CPG browser login, with credentials kept only in process memory."""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

CPG_URL = "https://127.0.0.1:5000"
PUSH_DEVICE = re.compile(r"(?:ib\s*key|mobile|push)", re.IGNORECASE)
logger = logging.getLogger(__name__)


def _authenticated(page: object) -> bool:
    """Check via the browser context so CPG session cookies are included."""
    try:
        return bool(page.evaluate("""
            async () => {
                const response = await fetch('/v1/api/iserver/auth/status', {
                    headers: {Accept: 'application/json'},
                });
                if (!response.ok) return false;
                return Boolean((await response.json()).authenticated);
            }
        """))
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
        stage = "open_login"
        try:
            page.goto(CPG_URL, wait_until="domcontentloaded", timeout=30_000)
            stage = "submit_first_factor"
            page.get_by_label("Username").fill(username)
            page.get_by_label("Password").fill(password)
            # The CPG widget can leave a transparent loading layer over this
            # button after its static page has loaded.  Dispatch the ordinary
            # button click without Playwright's visibility/actionability wait;
            # CPG's own submit handler still performs the SRP first factor.
            page.locator("form.xyzform-username button").click(force=True, no_wait_after=True, timeout=10_000)

            # CPG presents the available second-factor devices only after the
            # first factor is submitted.  Select an IB Key push-capable device
            # if it is offered; deliberately never interact with code/card
            # fields.  Some CPG versions proceed straight to the IB Key page,
            # so the absence of a selector is not itself a failure.
            stage = "find_push_device"
            push_option = page.locator("select option").filter(has_text=PUSH_DEVICE).first
            try:
                push_option.wait_for(state="attached", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            else:
                value = push_option.get_attribute("value")
                if value:
                    # The CPG front end sends the IB Key push from the select
                    # change handler.  It then hides the first-factor form, so
                    # clicking its old Log In button would only time out.
                    page.locator("select").select_option(value=value)

            stage = "await_approval"
            on_waiting()
            while time.monotonic() < deadline:
                if cancelled():
                    return False
                if _authenticated(page):
                    return True
                if page.get_by_text("denied", exact=False).count() or page.get_by_text("rejected", exact=False).count():
                    logger.warning("IBKR login worker failed: reason=second_factor_rejected")
                    return False
                page.wait_for_timeout(1_000)
            logger.warning("IBKR login worker failed: reason=approval_timeout")
            return False
        except PlaywrightTimeoutError:
            logger.warning("IBKR login worker failed: reason=browser_timeout stage=%s", stage)
            return False
        finally:
            context.close()
            browser.close()

"""Local-only Playwright login hook; credentials are read exclusively from files."""
from pathlib import Path
import pyotp
ROOT = Path("/run/ibkr-secrets")
def secret(name: str) -> str: return (ROOT / name).read_text().strip()
def main() -> int:
    # Site selectors are intentionally isolated here: CPG deployments may need
    # a maintained selector update as IBKR changes its sign-in page.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(); page.goto("https://127.0.0.1:5000", wait_until="domcontentloaded")
        page.get_by_label("Username").fill(secret("username"))
        page.get_by_label("Password").fill(secret("password"))
        page.get_by_role("button", name="Log In").click()
        page.get_by_label("Security code").fill(pyotp.TOTP(secret("totp")).now())
        page.get_by_role("button", name="Continue").click()
        page.wait_for_timeout(1000); browser.close()
    return 0
if __name__ == "__main__": raise SystemExit(main())

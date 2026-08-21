"""Interactive-only secret initializer. Never reads environment variables."""
from __future__ import annotations
import getpass
from pathlib import Path
ROOT = Path("/run/ibkr-secrets")
for name, prompt in (("username", "IBKR username"), ("password", "IBKR password"), ("totp", "TOTP secret")):
    value = getpass.getpass(f"{prompt}: ").strip()
    if not value: raise SystemExit(f"{name} must not be empty")
    target = ROOT / name; target.write_text(value + "\n"); target.chmod(0o600)

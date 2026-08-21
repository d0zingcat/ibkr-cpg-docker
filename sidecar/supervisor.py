"""Keep a CPG session alive; lock after four consecutive recovery failures."""
from __future__ import annotations
import json, os, time
from urllib.request import Request, urlopen

BASE = os.getenv("CPG_URL", "https://127.0.0.1:5000")
INTERVAL = 60
def get(path: str) -> dict:
    request = Request(BASE + path, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response: return json.load(response)
def recover() -> bool:
    # Login is intentionally a local-only executable; it owns credentials/TOTP.
    return os.system("/usr/local/bin/ibkr-login") == 0
def main() -> None:
    failures = 0
    while failures < 4:
        try:
            status = get("/v1/api/iserver/auth/status")
            if not status.get("authenticated", False) and not recover(): failures += 1
            else:
                get("/v1/api/tickle")
                failures = 0
        except Exception:
            failures += 1
        time.sleep(INTERVAL)
    print("CPG supervisor locked after four consecutive failures", flush=True)
    while True: time.sleep(3600)
if __name__ == "__main__": main()

# Security design

- CPG is only reachable on `127.0.0.1` inside the container.
- The guard is an explicit GET allowlist; it rejects query strings and all
  mutation methods, so it cannot be repurposed for order entry.
- The only mounted secret is the 0600 `control-token` file. The application
  compares it in constant time for every `:8081` request; it is never an
  environment variable, image layer, log value, or browser-visible value.
- IBKR usernames and passwords exist only in a control request and the
  Playwright worker's memory. They are never written to a volume or used for
  TOTP, IB Key challenge-response, or background recovery.
- Run with a non-root UID, read-only root filesystem, dropped capabilities,
  `no-new-privileges`, and a tmpfs `/tmp`.
- The control API permits one login browser at a time, expires/cancels it
  after a bounded wait, and closes the browser worker. It does not attempt to
  keep a session alive or automatically reauthenticate.
- Tests use fake CPG responses and fake browser pages. Never commit real
  credentials, cookies, TOTP seeds, or account numbers.

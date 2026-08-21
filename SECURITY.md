# Security design

- CPG is only reachable on `127.0.0.1` inside the container.
- The guard is an explicit GET allowlist; it rejects query strings and all
  mutation methods, so it cannot be repurposed for order entry.
- Credentials exist only as three 0600 files mounted at `/run/ibkr-secrets`.
  No secret is an environment variable, image layer, log value, or example.
- Run with a non-root UID, read-only root filesystem, dropped capabilities,
  `no-new-privileges`, and a tmpfs `/tmp`.
- The supervisor tickles once a minute. It makes at most four consecutive
  recovery attempts, then locks and stops retrying.
- Tests use fake CPG responses and fake browser pages. Never commit real
  credentials, cookies, TOTP seeds, or account numbers.

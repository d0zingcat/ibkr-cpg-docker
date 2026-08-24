# IBKR CPG Sidecar

Apache-2.0 licensed, read-only sidecar for Interactive Brokers Client Portal
Gateway (CPG). It downloads only a pinned official CPG archive verified with a
SHA-256, keeps the raw CPG loopback-only, and exposes a narrow GET-only guard
on port 8080.

The first pinned archive is the official 2023-04-25 distribution, SHA-256
`2f2d380b2f9424520ff5f9c11fe45e82ef39459329ac056258a3274bea6f76f9`.

Every push and pull request builds the image foundation in GitHub Actions. A
`vX.Y.Z` release tag builds the complete `runtime` image, attaches an SBOM and
provenance, and publishes it to GHCR using that same version tag.

This is not an Interactive Brokers product and automated authentication is not
officially supported by IBKR. CPG has no refresh token that replaces daily
authentication; use it only if your account policy permits it. See the [IBKR
CPG FAQ](https://www.interactivebrokers.com/docs/web-api/authentication/cpgw/client-portal-gateway-faq).

## Contract

Only these requests reach CPG: `GET /v1/api/iserver/auth/status`,
`/iserver/accounts`, `/portfolio/accounts`, `/portfolio/{account}/summary`,
`ledger`, and `positions/{page}`. `GET /healthz` is served by the guard.
Queries, every non-GET method, `/tickle`, login, and all trading endpoints are
rejected or remain internal.

## Authentication control API

Port `8081` is a separate private control API. It accepts a first-factor
username/password and drives the local CPG page with Playwright; the account
holder must approve the IB Key push in the mobile app. It implements no TOTP,
IB Key challenge-response, password persistence, or background relogin.

Every request needs `Authorization: Bearer <control-token>`, where
`control-token` is a read-only file in `/run/ibkr-secrets` shared only with the
trusted calling application. The API is intended for the Docker private network
or a host-loopback SSH tunnel, not public ingress. One attempt can run at a
time; it expires after five minutes by default (`LOGIN_TIMEOUT_SECONDS`).

```text
POST /control/v1/login                    {"username":"…","password":"…"} → 202 {"login_id":"…"}
GET  /control/v1/login/{login_id}          → authenticating | awaiting_approval | authenticated | failed | expired
POST /control/v1/login/{login_id}/cancel   → closes a pending attempt
```

Credentials exist only in the HTTP request and the browser worker's memory.
They are not written to logs, volumes, environment variables, response bodies,
or error messages. The GET-only `:8080` data guard remains unchanged and
continues to reject every POST.

## Releases

Release tags publish GHCR images, SBOM, and provenance. Deploy using the exact
release tag (for example `:v0.1.4`), never `latest`.

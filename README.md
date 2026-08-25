# IBKR CPG Sidecar

Apache-2.0 licensed, read-only sidecar for Interactive Brokers Client Portal
Gateway (CPG). It downloads only a pinned official CPG archive verified with a
SHA-256, keeps the raw CPG loopback-only, and exposes a narrow GET-only guard
on port 8080.

The pinned archive is the official 2023-04-25 distribution, SHA-256
`2f2d380b2f9424520ff5f9c11fe45e82ef39459329ac056258a3274bea6f76f9`.

Every push and pull request builds the image foundation in GitHub Actions. A
`vX.Y.Z` release tag builds the complete `runtime` image, attaches an SBOM and
provenance, and publishes it to GHCR using that same version tag.

This is not an Interactive Brokers product and automated authentication is not
officially supported by IBKR. CPG has no refresh token that replaces daily
authentication; use it only if your account policy permits it. See the [IBKR
CPG FAQ](https://www.interactivebrokers.com/docs/web-api/authentication/cpgw/client-portal-gateway-faq).

---

## ⚠️ Important Limitations & Findings for IB Key (5.2a) Accounts

Extensive network packet analysis and reverse engineering of the CPG 2023 SSO bundle have established that **CPG headless authentication cannot establish persistent sessions for accounts bound to IB Key (`5.2a`)**:

```text
                    IBKR 账户认证路径
                           │
      ┌────────────────────┴────────────────────┐
      ▼                                         ▼
【有 TOTP / SMS 权限】                    【绑定 IB Key (5.2a)】
  • IBeam 可用 Playwright 自动填 6 位码       • 官方禁止降级或开启 TOTP
  • CPG 可正常自动化                         • CPG 无头 Push 因 2023 SSO Cookie 作用域失效
                                            • CPG 离线应答码因 5.2a 服务端不校验而失效
                                            ─────────────────────────────
                                            👉 推荐转向官方标准：
                                               【ibkr-gateway-docker (TWS API)】
```

### Root Cause Breakdown

1. **CPG 2023 Package Frozen**:
   - The official `clientportal.gw.zip` distributed by IBKR has not been updated since **April 24, 2023**.
2. **SSO Cookie Scope Isolation**:
   - When a user approves an IB Key push notification on their phone, IBKR's cloud SSO server issues a session cookie (`JSESSIONID`) scoped strictly to `Path=/sso`.
   - CPG's Vert.x reverse proxy for `/v1/api/*` endpoints cannot inherit or forward this cookie, causing `/v1/api/sso/validate` and `/v1/api/iserver/auth/ssodh/init` to return `401 Unauthorized`.
3. **Server-Side Rejection of Offline Challenge-Response**:
   - When device type is `5.2a` (IB Key), IBKR's SLS cloud server marks the session as online push-only (`"push_sent": true, "qrcode_url": "..."`).
   - Submitting an offline challenge response code (even when correctly calculated from the mobile app's security token) to `COMPLETETWOFACT` receives an explicit rejection:
     ```json
     {"reached_max_login": false, "auth_res": "false", "error": "failed"}
     ```
   - The server does not perform offline HMAC verification for `5.2a` devices.

### Recommended Alternative
If your account is bound to IB Key and requires real-time account data or algorithmic trading, use **[`ibkr-gateway-docker`](https://github.com/d0zingcat/ibkr-gateway-docker)** (IB Gateway + IBC / TWS API), which uses IBKR's native binary socket protocol and requires 2FA approval only once per week on Monday.

---

## Contract

Only these requests reach CPG: `GET /v1/api/iserver/auth/status`,
`/iserver/accounts`, `/portfolio/accounts`, `/portfolio/{account}/summary`,
`ledger`, and `positions/{page}`. `GET /healthz` is served by the guard.
Queries, every non-GET method, `/tickle`, login, and all trading endpoints are
rejected or remain internal.

## Authentication control API

Port `8081` is a separate private control API. It accepts a first-factor
username/password and drives the local CPG page with Playwright.

Every request needs `Authorization: Bearer <control-token>`, where
`control-token` is a read-only file in `/run/ibkr-secrets` shared only with the
trusted calling application. The API is intended for the Docker private network
or a host-loopback SSH tunnel, not public ingress. One attempt can run at a
time; it expires after five minutes by default (`LOGIN_TIMEOUT_SECONDS`).

```text
POST /control/v1/login                    {"username":"…","password":"…"} → 202 {"login_id":"…"}
GET  /control/v1/login/{login_id}          → {"state": "…", "challenge": "…"}
POST /control/v1/login/{login_id}/response {"response":"…"} → 202 {"status":"ok"}
POST /control/v1/login/{login_id}/cancel   → closes a pending attempt
```

Credentials exist only in the HTTP request and the browser worker's memory.
They are not written to logs, volumes, environment variables, response bodies,
or error messages. The GET-only `:8080` data guard remains unchanged and
continues to reject every POST.

## Releases

Release tags publish GHCR images, SBOM, and provenance. Deploy using the exact
release tag (for example `:v0.1.4`), never `latest`.

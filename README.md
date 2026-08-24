# IBKR CPG Sidecar

Apache-2.0 licensed, read-only sidecar for Interactive Brokers Client Portal
Gateway (CPG). It downloads only a pinned official CPG archive verified with a
SHA-256, keeps the raw CPG loopback-only, and exposes a narrow GET-only guard
on port 8080.

The first pinned archive is the official 2023-04-25 distribution, SHA-256
`2f2d380b2f9424520ff5f9c11fe45e82ef39459329ac056258a3274bea6f76f9`.

Every push and pull request builds the image foundation in GitHub Actions. A
`vX.Y.Z` release tag builds the complete `runtime` image, attaches an SBOM and
provenance, and publishes it to GHCR using only the short commit SHA as its
image tag.

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

## Secrets

Create a private named volume, then run the initializer attached to a terminal:

`docker run --rm -it -v ibkr-secrets:/run/ibkr-secrets ghcr.io/d0zingcat/ibkr-cpg-docker@sha256:... python /opt/sidecar/init_secrets.py`

It prompts without echo for username, password, and TOTP, and writes mode 0600
files. The image never accepts those values through environment variables.

## Releases

Release tags publish GHCR images, SBOM, provenance, and a digest. Deploy using
the exact `short-sha@sha256:digest` form, never `latest`.

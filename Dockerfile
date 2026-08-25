FROM python:3.12-slim AS cpg
ARG CPG_VERSION=2023-04-25
ARG CPG_SHA256=2f2d380b2f9424520ff5f9c11fe45e82ef39459329ac056258a3274bea6f76f9
ARG CPG_URL=https://download2.interactivebrokers.com/portal/clientportal.gw.zip
RUN test -n "$CPG_SHA256" && test -n "$CPG_URL" \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/* \
 && curl --fail --location --proto '=https' --tlsv1.2 "$CPG_URL" -o /tmp/cpg.zip \
 && echo "$CPG_SHA256  /tmp/cpg.zip" | sha256sum -c - \
 && unzip -q /tmp/cpg.zip -d /opt/cpg

FROM python:3.12-slim AS base
RUN useradd --system --uid 10001 --create-home sidecar

FROM base AS runtime
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY requirements.txt /tmp/
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && playwright install --with-deps chromium
COPY --from=cpg /opt/cpg /opt/cpg
RUN mkdir -p /opt/cpg/logs /tmp/vertx-cache && chown -R 10001:10001 /opt/cpg /tmp/vertx-cache
COPY sidecar /opt/sidecar
RUN chmod 0555 /opt/sidecar/*.py
USER 10001
EXPOSE 8080 8081
ENTRYPOINT ["python", "/opt/sidecar/start.py"]

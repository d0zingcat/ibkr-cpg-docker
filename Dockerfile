FROM python:3.12-slim AS cpg
ARG CPG_VERSION=10.19.2
ARG CPG_SHA256
ARG CPG_URL
RUN test -n "$CPG_SHA256" && test -n "$CPG_URL" \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/* \
 && curl --fail --location --proto '=https' --tlsv1.2 "$CPG_URL" -o /tmp/cpg.zip \
 && echo "$CPG_SHA256  /tmp/cpg.zip" | sha256sum -c - \
 && unzip -q /tmp/cpg.zip -d /opt/cpg

FROM python:3.12-slim
RUN useradd --system --uid 10001 --create-home sidecar
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt && playwright install --with-deps chromium
COPY --from=cpg /opt/cpg /opt/cpg
COPY sidecar /opt/sidecar
RUN chmod 0555 /opt/sidecar/*.py && ln -s /opt/sidecar/login.py /usr/local/bin/ibkr-login
USER 10001
EXPOSE 8080
ENTRYPOINT ["python", "/opt/sidecar/start.py"]

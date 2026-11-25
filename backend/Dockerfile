# JobDots API and worker image (local Compose now; Render later).
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# WeasyPrint (resume PDFs) needs Pango/HarfBuzz; fonts so PDFs render text everywhere.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libharfbuzz0b \
        libharfbuzz-subset0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Tectonic compiles the master .tex resume (plan Day 4). Static musl build, pinned by checksum.
# It downloads its TeX bundle on first use and caches it in the user's home directory.
ADD --checksum=sha256:dfb82876f2986862996e564fa507a9e576e0c1e3bee63c2c1bd677c2543e6407 \
    https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz \
    /tmp/tectonic.tar.gz
RUN tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic && rm /tmp/tectonic.tar.gz && tectonic --version

WORKDIR /app

COPY requirements.lock .
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 uv pip install --system --no-deps -r requirements.lock && pip check

COPY . .

ENV FILE_STORAGE_DIR=/app/data/files
RUN useradd --create-home --uid 10001 jobpilot \
    && mkdir -p /app/data/files \
    && chown -R jobpilot:jobpilot /app/data
USER jobpilot

# Render (and most hosts) pass the port in $PORT.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]

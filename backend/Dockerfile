# JobPilot API — production image (Render, Railway, Fly, any Docker host).
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

WORKDIR /app

COPY requirements.lock .
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 uv pip install --system --no-deps -r requirements.lock && pip check

COPY . .

ENV MINILM_CACHE_PATH=/opt/jobpilot-models/minilm \
    CHROMA_PATH=/tmp/jobpilot-chroma \
    HF_HUB_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2
ENV FILE_STORAGE_DIR=/app/data/files
RUN python scripts/prepare_models.py --minilm \
    && useradd --create-home --uid 10001 jobpilot \
    && mkdir -p /tmp/jobpilot-chroma /app/data/files \
    && chown -R jobpilot:jobpilot /tmp/jobpilot-chroma /app/data
USER jobpilot

# Render (and most hosts) pass the port in $PORT.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]

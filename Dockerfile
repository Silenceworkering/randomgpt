# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install -r requirements.lock; \
    else pip install -r requirements.lock; fi
COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY dedlainych ./dedlainych
COPY scripts ./scripts
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-deps .; \
    else pip install --no-deps .; fi
RUN useradd --create-home --uid 10001 bot && chown -R bot:bot /app
USER bot
CMD ["sh", "scripts/start.sh"]

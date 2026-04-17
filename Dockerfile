# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Stage 1: build the React/Vite frontend
# -----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2: Python runtime + GitHub Copilot CLI + FastAPI app
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Install Node.js (needed for the @github/copilot CLI that the Copilot SDK
# talks to) plus a few OS essentials.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @github/copilot@latest \
    && npm cache clean --force

# Non-root user for the app + writable state dir.
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app /data \
    && chown -R app:app /app /data

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[web]"

# Bring in the built frontend from stage 1.
COPY --from=frontend-build --chown=app:app /build/dist /app/static

USER app

# Persisted config (Copilot PAT, Garmin tokens) lives here. Mount a volume
# on /data in production so a container restart doesn't wipe setup.
ENV TEXT_TO_GARMIN_STATE_DIR=/data \
    GARMINTOKENS=/data/garmin_tokens.json \
    TEXT_TO_GARMIN_STATIC_DIR=/app/static \
    PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# Shell form so $PORT is interpolated at runtime (Azure Container Apps
# overrides this via targetPort).
CMD uvicorn text_to_garmin.webapi:app --host 0.0.0.0 --port ${PORT}

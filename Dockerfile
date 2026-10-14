# syntax=docker/dockerfile:1

# Stage 1: Build frontend
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime with dependencies
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files and source (hatchling needs app/ and README.md)
COPY pyproject.toml uv.lock README.md ./
COPY app/ app/
COPY alembic.ini ./
COPY alembic/ alembic/

# Install dependencies from lockfile (frozen = respect uv.lock exactly)
RUN uv sync --frozen --no-dev --no-editable

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist frontend/dist

RUN chown -R app:app /app
USER app

ENV APP_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
# Trust proxy headers from Docker internal network (Caddy container)
ENV FORWARDED_ALLOW_IPS="172.16.0.0/12,192.168.0.0/16,10.0.0.0/8"

EXPOSE 8000

# Use proxy-headers to trust X-Forwarded-* from Caddy
# --forwarded-allow-ips controls which source IPs are trusted to set these headers
CMD ["sh", "-c", "fastapi run --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]

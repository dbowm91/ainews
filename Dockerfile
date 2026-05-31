# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

# System dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies (layer cached unless lockfile changes)
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev --no-install-project

# Install granian (not in core dependencies)
RUN uv pip install --system "granian>=1.0.0,<2"

# Stage 2: Runtime image
FROM python:3.12-slim AS runtime

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libffi8 \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy Python environment from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy application code
COPY . .

# Create non-root user
RUN groupadd --gid 1000 ainews \
    && useradd --uid 1000 --gid 1000 --create-home ainews \
    && chown -R ainews:ainews /app

# Create data directories
RUN mkdir -p /app/instance /app/backups \
    && chown -R ainews:ainews /app/instance /app/backups

USER ainews

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "5000", "--workers", "4", "--threads", "4", "--access-log", "--log-level", "info", "run:app"]

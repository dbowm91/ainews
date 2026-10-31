# Stage 1: Builder - install dependencies with build tools
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Install the ASGI server into the project venv (not --system) so the
# runtime stage can run everything from a single PATH entry. This must run
# AFTER the final `uv sync`: an exact sync prunes packages that are not in
# the lockfile, which would remove granian again.
RUN uv pip install --python /app/.venv/bin/python "granian>=1.0.0,<2"

# Stage 2: Runtime - minimal image without build tools
FROM python:3.12-slim AS runtime

# Runtime libraries for lxml and trafilatura (no dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

ENV AINEWS_RUNNING_IN_DOCKER=1

# Dependencies live in the project venv (created by `uv sync` in the
# builder stage and copied over with /app). Put it first on PATH so both
# `python` and the venv-installed `granian` resolve inside the image.
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY --from=builder /app /app

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

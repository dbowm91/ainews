FROM python:3.12-slim AS base

# System dependencies for lxml, trafilatura, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer cached unless requirements change)
# Dependencies are defined in pyproject.toml; requirements.txt mirrors them for Docker caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir granian

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

CMD ["granian", "--interface", "wsgi", "--host", "0.0.0.0", "--port", "5000", "--workers", "2", "--blocking-threads", "2", "--access-log", "--log-level", "info", "--no-ws", "run:app"]

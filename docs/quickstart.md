# Quick Start Guide

Get ainews running locally for development in under 10 minutes.

## Prerequisites

| Tool | Required | Install |
|------|----------|---------|
| Python 3.12+ | Yes | [python.org](https://python.org) |
| Redis | Yes | See below |
| Ollama | Recommended | [ollama.ai](https://ollama.ai) |

### Install Redis

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install redis-server
sudo systemctl enable --now redis-server
```

**Verify:**
```bash
redis-cli ping   # Should return PONG
```

### Install Ollama (for local LLM)

```bash
# macOS / Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Start the Ollama server
ollama serve &

# Pull a model (qwen3:8b is recommended for this project)
ollama pull qwen3:8b
```

> **Alternative:** Skip Ollama and use OpenAI or Anthropic APIs instead. See [LLM Providers](#llm-providers) below.

## Setup

### 1. Clone and install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or pip.

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum, set these:

```bash
# Generate a secret key
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">

# Hash your admin password (recommended)
# Run: python scripts/hash_password.py
ADMIN_PASSWORD=<hashed password from script output>
```

Redis defaults (`redis://localhost:6379/0`) work out of the box.

### 3. Start everything

```bash
bash scripts/dev.sh
```

This starts:
- **Flask** at `http://localhost:5000`
- **Celery worker** for background tasks
- **Celery beat** for scheduled jobs

**Stop everything:**
```bash
bash scripts/dev.sh stop
```

**Check status:**
```bash
bash scripts/dev.sh status
```

## Verify

```bash
# Health check
curl http://localhost:5000/health

# Homepage
open http://localhost:5000

# Admin dashboard
open http://localhost:5000/admin/login
```

## Trigger a crawl

From the admin dashboard, click **Trigger Crawl**, or:

```bash
celery -A celery_app:celery_app call tasks.crawl.run_all_sources
```

## LLM Providers

### Ollama (default, local)

Already configured in `providers.yaml`:

```yaml
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      host: "http://localhost:11434"
      model: "qwen3:8b"
```

### OpenAI

Edit `providers.yaml`:
```yaml
- id: openai
  type: openai
  enabled: true        # Change to true
  config:
    api_key: "${OPENAI_API_KEY}"
    model: "gpt-4o-mini"
```

Add to `.env`:
```bash
OPENAI_API_KEY=sk-...
```

### Anthropic

Edit `providers.yaml`:
```yaml
- id: anthropic
  type: anthropic
  enabled: true        # Change to true
  config:
    api_key: "${ANTHROPIC_API_KEY}"
    model: "claude-sonnet-4-5-20250929"
```

Add to `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### Disable Ollama

If using OpenAI or Anthropic instead of Ollama, disable the Ollama provider and set the `default_provider`:

```yaml
default_provider: openai  # or anthropic
```

## Running Tests

```bash
bash scripts/test.sh
```

With coverage:
```bash
bash scripts/test.sh --cov
```

Filter tests:
```bash
bash scripts/test.sh --pattern test_routes
```

## Manual Service Management

If you prefer running services in separate terminals instead of `dev.sh`:

**Terminal 1 — Flask:**
```bash
source .venv/bin/activate
flask run --reload
```

**Terminal 2 — Celery Worker:**
```bash
source .venv/bin/activate
celery -A celery_app:celery_app worker -l info
```

**Terminal 3 — Celery Beat:**
```bash
source .venv/bin/activate
celery -A celery_app:celery_app beat -l info
```

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Secrets, SMTP, LLM API keys |
| `pipeline.yaml` | AI processing pipeline settings |
| `sources.yaml` | RSS/API feed sources |
| `topics.yaml` | Topic categories |
| `providers.yaml` | LLM provider configuration |

See [configuration.md](configuration.md) for the full reference.

## Docker Alternative

If you prefer Docker over local setup:

```bash
cp .env.example .env
# Edit .env
docker compose up -d
```

## Troubleshooting

### Redis connection error

```bash
redis-cli ping           # Should return PONG
brew services start redis   # macOS
sudo systemctl start redis-server   # Linux
```

### Ollama not responding

```bash
curl http://localhost:11434/api/tags   # Should list models
ollama serve                           # Start if not running
```

### Celery tasks not executing

```bash
# Check worker is connected
celery -A celery_app:celery_app inspect ping

# Check logs
tail -f .pids/celery-worker.log
```

### Database locked

SQLite with WAL mode prevents most locking issues. If you see locked errors:
- Ensure only one Flask process writes to the database
- Check `instance/` directory permissions

### Port 5000 already in use

```bash
# Find what's using port 5000
lsof -i :5000

# Or use a different port
flask run --reload --port 5001
```

## Next Steps

- [Configuration Reference](configuration.md) — All config files explained
- [Deployment Guide](deployment.md) — Deploy to production
- Customize `sources.yaml` with your RSS feeds
- Configure SMTP in `.env` for newsletter delivery

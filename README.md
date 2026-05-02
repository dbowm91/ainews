# ainews

AI-powered news aggregation and newsletter platform. Automatically discovers, summarizes, and curates news articles from configurable RSS sources using large language models.

## Quick Start (Docker)

```bash
git clone https://github.com/yourorg/ainews.git
cd ainews
cp .env.example .env
# Edit .env — set SECRET_KEY and at least one LLM provider
docker compose up -d
```

App is running at `http://localhost:5000`. Admin login at `http://localhost:5000/admin/login`.

## Quick Start (bare metal)

Requires Python 3.12+, Redis, and optionally Ollama for local LLM inference.

```bash
git clone https://github.com/yourorg/ainews.git
cd ainews
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Edit .env
redis-server &                # Start Redis
bash scripts/dev.sh           # Start Flask + Celery
```

See [docs/quickstart.md](docs/quickstart.md) for full setup instructions.

## Architecture

```
Nginx → Granian (WSGI) → Flask
                          │
                    ┌─────┴──────┐
                    │            │
               Celery Worker   SQLite (WAL)
                    │
                  Redis (broker)
                    │
               LLM (Ollama / OpenAI / Anthropic)
```

**Pipeline:** `pending → researching → writing → editing → publish`

## Features

- **Automated RSS/API Ingestion** — Configurable source feeds with scheduled polling
- **AI-Powered Processing** — Selection, research, writing, and editing stages via LLM
- **Topic Classification** — Automatic categorization using configurable topic definitions
- **Newsletter Generation** — Curated newsletters from aggregated content
- **Full-Text Search** — SQLite FTS5-powered article search
- **Admin Dashboard** — Web UI for managing sources, articles, topics, and newsletters
- **RSS Output** — Published feed at `/feed` for downstream consumption

## Endpoints

| Path | Description |
|------|-------------|
| `/` | Homepage with latest articles |
| `/topic/<category>` | Topic-filtered feed |
| `/article/<id>` | Article detail page |
| `/tag/<slug>` | Tag-filtered feed |
| `/feed` | RSS feed of published articles |
| `/feed/<category>` | Topic-specific RSS feed |
| `/sitemap.xml` | XML sitemap for crawlers |
| `/health` | Public health check |
| `/subscribe` | Newsletter subscription |
| `/unsubscribe/<token>` | Unsubscribe |
| `/admin/login` | Admin dashboard |
| `/admin/api/health` | Authenticated health check |

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Environment variables (secrets, SMTP, LLM keys) |
| `pipeline.yaml` | Processing pipeline settings (roles, models, prompts) |
| `sources.yaml` | RSS/API source definitions |
| `topics.yaml` | Topic classification categories |
| `providers.yaml` | LLM provider settings |

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/dev.sh` | Start local development (Flask + Celery + Beat) |
| `scripts/test.sh` | Run test suite |
| `scripts/backup.sh` | Backup SQLite database |
| `scripts/install.sh` | Production installation (bare metal) |
| `scripts/deploy.sh` | Production deployment update |

## Tech Stack

- Python 3.12 / Flask / Celery
- SQLite (WAL mode) / SQLAlchemy
- Redis (broker + cache)
- Granian (WSGI server)
- Ollama / OpenAI / Anthropic (LLM providers)

## Documentation

- [Quick Start](docs/quickstart.md) — Local development setup
- [Configuration](docs/configuration.md) — All config files and env vars
- [Deployment](docs/deployment.md) — Production deployment (Docker or bare metal)

## License

See [LICENSE](LICENSE) for details.

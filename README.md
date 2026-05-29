# ainews

AI-powered news aggregation and newsletter platform. Automatically discovers, summarizes, and curates news articles from configurable RSS/API sources using a multi-stage LLM pipeline with quality gates, subagent tool calling, and trend memory.

## Quick Start (Docker)

```bash
git clone https://github.com/davidbowman/ainews.git
cd ainews
cp .env.example .env
# Edit .env — set SECRET_KEY and at least one LLM provider
docker compose up -d
```

App is running at `http://localhost:5000`. Admin login at `http://localhost:5000/admin/login`.

## Quick Start (bare metal)

Requires Python 3.12+, Redis, and optionally Ollama for local LLM inference.

```bash
git clone https://github.com/davidbowman/ainews.git
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

- **Multi-Provider LLM Pipeline** — Select, research, write, and edit stages via configurable LLM providers with automatic fallback
- **Subagent Tool Calling** — Contextualization tools (topic notes, related articles, trend memory, web search) available to LLM stages
- **Quality Gates & Review Routing** — Degenerate drafts, low confidence selections, and validation failures route to manual review
- **Trend Memory & Topic Notes** — LLM-judged editorial memory with importance tiers (LOW/MEDIUM/HIGH) and per-topic context notes
- **Webhook Events** — article.published, article.failed, newsletter.sent, newsletter.failed with HMAC signatures and retry
- **Hybrid Search** — SQLite FTS5 + vector similarity (sentence transformers) for article search with weighted ranking
- **Metrics, Health & Cost Endpoints** — Prometheus metrics, public/admin health checks, per-article cost tracking
- **Admin API Tokens & 2FA** — Programmmatic API access with token expiry, and TOTP 2FA with backup codes for admin login
- **Newsletter Generation** — Curated daily newsletters with per-subscriber topic filtering and delivery tracking
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
| `/api/v1/health` | Authenticated health check |
| `/api/v1/newsletters/stats` | Newsletter statistics |
| `/api/v1/articles/<id>` | Article CRUD (API token auth) |

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
- [Pipeline](docs/pipeline.md) — Stages, state transitions, review routing, retry behavior
- [Subagents](docs/subagent.md) — Subagent config, tools, how to add tools
- [Search](docs/search.md) — FTS, hybrid vector search, embedding backfill
- [Operations](docs/operations.md) — Health, metrics, Celery workers, failure recovery
- [Quality](docs/quality.md) — Quality report model, scoring, citation verification

## License

See [LICENSE](LICENSE) for details.

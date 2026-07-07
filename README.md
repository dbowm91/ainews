# ainews

AI-powered news aggregation and newsletter platform. Discovers, summarizes, and curates articles from configurable RSS/API sources using a multi-stage LLM pipeline with quality gates, subagent tool calling, and trend memory.

> **Status:** Alpha / experimental but functional. Designed for single-node self-hosted use.

## Quick Start

### Docker (fastest)

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
cp .env.example .env
# Edit .env — set SECRET_KEY and at least one LLM provider
docker compose up -d
```

App at `http://localhost:5000`. Admin at `http://localhost:5000/admin/login`.

### Bare Metal

Requires Python 3.12+, Redis, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
uv sync
cp .env.example .env          # Edit .env
redis-server &                # Start Redis
bash scripts/dev.sh           # Start Flask + Celery
```

For local LLM inference, install [Ollama](https://ollama.ai) and pull a model:
```bash
ollama pull qwen3:8b
```

See [docs/quickstart.md](docs/quickstart.md) for full setup instructions.

## Architecture

```
Nginx → Granian (ASGI) → Flask
                          │
                    ┌─────┴──────┐
                    │            │
               Celery Worker   SQLite (WAL)
                    │
                  Redis (broker)
                    │
               LLM (Ollama / OpenAI / Anthropic)
```

**Pipeline:** `pending → selected → researching → writing → editing → done`

## Features

- **Multi-Provider LLM Pipeline** — Select, research, write, and edit stages with automatic fallback across providers
- **Subagent Tool Calling** — Contextualization tools (topic notes, related articles, trend memory, web search) available to LLM stages
- **Quality Gates & Review Routing** — Degenerate drafts, low confidence selections, and validation failures route to manual review
- **Trend Memory & Topic Notes** — LLM-judged editorial memory with importance tiers and per-topic context notes
- **Webhook Events** — article.published, article.failed, newsletter.sent, newsletter.failed with HMAC signatures and retry
- **Hybrid Search** — SQLite FTS5 + vector similarity (sentence transformers) for article search
- **Metrics, Health & Cost** — Prometheus metrics, public/admin health checks, per-article cost tracking
- **Admin API & 2FA** — API tokens (`ak_<prefix>.<secret>`) with expiry and revocation, TOTP 2FA with backup codes
- **Newsletter Generation** — Daily newsletters with per-subscriber topic filtering and delivery tracking
- **RSS Output** — Published feed at `/feed` for downstream consumption

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Secrets, SMTP, LLM API keys ([example](.env.example)) |
| `pipeline.yaml` | Processing pipeline settings (roles, models, prompts) |
| `sources.yaml` | RSS/API feed sources |
| `topics.yaml` | Topic classification categories |
| `providers.yaml` | LLM provider configuration |

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Known Limitations

- Requires Redis for background task processing
- SQLite is suitable for single-node deployments; multi-node may need a different DB strategy
- LLM quality depends on provider/model configuration
- Human editorial review is recommended before publishing generated content
- SMTP is required for newsletter delivery but not for app startup

## Documentation

| Doc | Description |
|-----|-------------|
| [Quick Start](docs/quickstart.md) | Local development setup |
| [Configuration](docs/configuration.md) | All config files and env vars |
| [Deployment](docs/deployment.md) | Production deployment (Docker or bare metal) |
| [Pipeline](docs/pipeline.md) | Stages, state transitions, review routing, retry |
| [Subagents](docs/subagent.md) | Subagent config, tools, how to add tools |
| [Search](docs/search.md) | FTS, hybrid vector search, embedding backfill |
| [Operations](docs/operations.md) | Health, metrics, Celery workers, failure recovery |
| [Quality](docs/quality.md) | Quality report model, scoring, citation verification |
| [Responsible Use](docs/responsible-use.md) | Source rights, attribution, AI content guidance |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and PR process.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

See [LICENSE](LICENSE) for details.

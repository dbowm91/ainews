# ainews

AI-powered news aggregation and newsletter platform. Discovers, summarizes, and curates articles from configurable RSS/API sources using a multi-stage LLM pipeline with quality gates, subagent tool calling, and trend memory.

> **Status:** Release candidate. Designed for single-node self-hosted use. See [Release Checklist](docs/release_checklist.md) for validation requirements.

## Quick Start

### Docker (fastest)

1. Clone and enter the repo:
   ```bash
   git clone https://github.com/dbowm91/ainews.git && cd ainews
   ```

2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

3. Generate a `SECRET_KEY` (64-char hex):
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Paste the output into `SECRET_KEY=` in `.env`.

4. Generate a hashed `ADMIN_PASSWORD`:
   ```bash
   python scripts/hash_password.py
   ```
   Paste the output into `ADMIN_PASSWORD=` in `.env`.

5. Generate a `CELERY_TASK_SECRET`:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Paste the output into `CELERY_TASK_SECRET=` in `.env`.

6. Ensure these are set in `.env` (defaults work for local development):
   - `FLASK_CONFIG=production`
   - `CELERY_BROKER_URL=redis://localhost:6379/0`
   - `CELERY_RESULT_BACKEND=redis://localhost:6379/1`
   - `DATABASE_URL=sqlite:///instance/ainews.db`

7. Configure at least one LLM provider and set `default_provider` in `providers.yaml`. For cloud providers, add the API key to `.env`.

8. Start services:
   ```bash
   docker compose up -d
   ```

9. Verify the app is running:
   ```bash
   curl http://localhost:5000/health
   ```

10. Log in at `http://localhost:5000/admin/login` (username: `admin`).

> **Ollama in Docker:** The default Ollama provider at `localhost:11434` does not work from inside Docker containers. See [Deployment Guide](docs/deployment.md#docker-with-ollama) for Docker-compatible Ollama setup.

### Bare Metal

Requires Python 3.12+, Redis, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/dbowm91/ainews.git && cd ainews
uv sync
cp .env.example .env          # Edit .env (see steps 3-6 above)
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
- **Safe Fetch Client** — First-party SSRF-protected HTTP client with manual redirect validation, streaming byte limits, and content-type allowlist
- **Newsletter Generation** — Daily newsletters with per-subscriber topic filtering and delivery tracking
- **RSS Output** — Published feed at `/feed` for downstream consumption
- **Themeable Frontend** — 48 packaged Halloy-compatible themes under `resources/themes/` with manifest, code-defined emergency fallback, and operator-configurable external custom directory. Themes are parsed once at startup; immutable `ThemeRegistry` exposes deterministic lookup for later CSS delivery phases. See [Halloy Theme Contract](docs/halloy-theme-contract.md) §12.

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

- Docker containers cannot reach `localhost` on the host machine — use `host.docker.internal` or run Ollama as a Compose service (see `docker-compose.ollama.yml`)
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
| [Frontend](docs/frontend.md) | UI structure, asset builds, accessibility conventions |
| [Theme Inventory](docs/themes-inventory.md) | Halloy theme collection inventory & provenance |
| [Halloy Theme Contract](docs/halloy-theme-contract.md) | Supported source schema and translation rules |
| [Security Triage](docs/security_triage.md) | Vulnerability triage, suppression policy, license review, container scanning |

## Release Validation

Run one command to validate your changes match CI gates:

```bash
bash scripts/validate_release.sh          # Full: lint + tests + smoke + Docker + Compose
bash scripts/validate_release.sh --fast   # Quick: ruff + targeted smoke tests
bash scripts/validate_release.sh --security  # pip-audit + secret scanning
```

Or via Make:

```bash
make validate-release          # Full validation
make validate-release-fast     # Quick validation
```

See [docs/deployment.md#release-validation](docs/deployment.md#release-validation) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and PR process.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

See [LICENSE](LICENSE) for details.

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

## Quick Start (Release 2)

### Docker (fastest)

1. Clone and enter the repo:
   ```bash
   git clone https://github.com/dbowm91/ainews.git && cd ainews
   ```

2. Install the CLI:
   ```bash
   pip install -e .
   ```

3. Run interactive onboarding:
   ```bash
   ainews onboard
   ```

   The onboarding wizard will:
   - Select a deployment profile (docker-local, docker-lan, reverse-proxy, bare-metal)
   - Generate secure secrets (SECRET_KEY, CELERY_TASK_SECRET, admin password)
   - Configure your LLM provider (Ollama, OpenAI, Anthropic, Gemini, EggPool, or generic OpenAI-compatible)
   - Discover available models
   - Apply pipeline and source profiles
   - Validate and start services

4. Or use a bootstrap file for unattended setup:
   ```bash
   ainews onboard --non-interactive --config-file bootstrap.yaml --start
   ```

5. Verify the app is running:
   ```bash
   curl http://localhost:5000/health
   ```

### Bare Metal

Requires Python 3.12+, Redis, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/dbowm91/ainews.git && cd ainews
uv sync
ainews onboard  # Interactive setup
```

## Operator CLI

ainews includes a command-line interface for onboarding, provider management, service lifecycle, and diagnostics:

```bash
# Onboarding
ainews onboard                           # Interactive first-run setup
ainews onboard --config-file boot.yaml   # Declarative bootstrap
ainews onboard --dry-run                 # Preview without changes

# Provider management
ainews providers-list                    # Show configured providers
ainews providers-add                     # Add a provider interactively
ainews providers-test [ID]              # Test provider connectivity
ainews providers-models ID              # List available models
ainews providers-set-default ID         # Set default provider
ainews providers-assign ID MODEL [ROLES]  # Assign to pipeline roles
ainews providers-remove ID              # Remove a provider

# Service lifecycle
ainews start                             # Start all services
ainews stop                              # Stop services
ainews restart                           # Restart services
ainews status                            # Show service status
ainews logs [SERVICE]                    # View logs
ainews health                            # Check health endpoints
ainews smoke                             # Post-deploy smoke checks

# Configuration
ainews config path                       # Show resolved config paths
ainews config show                       # Show effective config (secrets redacted)
ainews config check                      # Validate configuration
ainews config get KEY                    # Get a config value
ainews config set KEY VALUE             # Set a config value
ainews config set-secret KEY            # Set a secret (reads from stdin)
ainews config unset KEY                  # Remove an override
ainews config diff                       # Compare with defaults
ainews config rollback --list           # List rollback snapshots

# Diagnostics
ainews doctor                            # Full system diagnostics
ainews doctor --quick                    # Basic checks only
ainews doctor --network                  # Include connectivity checks
ainews version                           # Show version info
```

See [CLI Reference](docs/cli-reference.md) for full documentation.

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

### Themes

ainews ships with 48 built-in themes (6 light, 42 dark) derived from Halloy IRC themes (Catppuccin, Dracula, Gruvbox, Nord, Rose Pine, Solarized, etc.). Application layout CSS is permanent; theme CSS provides palette variables only. Operators can add custom themes via `THEMES_CUSTOM_DIR`. See [Theme Authoring Guide](docs/theme-authoring.md) for creating compatible themes.

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
- **Themeable Frontend** — 48 packaged Halloy-compatible themes under `resources/themes/` with manifest, code-defined emergency fallback, and operator-configurable external custom directory. Themes are parsed once at startup; immutable `ThemeRegistry` exposes deterministic lookup for later CSS delivery phases. Application CSS is permanent; generated theme CSS contains only palette variables. See [Halloy Theme Contract](docs/halloy-theme-contract.md) §12.

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Secrets, SMTP, LLM API keys ([example](.env.example)) |
| `pipeline.yaml` | Processing pipeline settings (roles, models, prompts) |
| `sources.yaml` | RSS/API feed sources |
| `topics.yaml` | Topic classification categories |
| `providers.yaml` | LLM provider configuration |
| [CLI Reference](docs/cli-reference.md) | Operator CLI commands |

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
| [CLI Reference](docs/cli-reference.md) | Operator CLI reference |
| [Onboarding](docs/onboarding.md) | First-run setup, profiles, bootstrap schema |
| [Provider CLI](docs/providers-cli.md) | Provider management, testing, model discovery |

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

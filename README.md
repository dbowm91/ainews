# ainews

AI-powered news aggregation and newsletter platform. Discovers, summarizes, and curates articles from configurable RSS/API sources using a multi-stage LLM pipeline with quality gates, subagent tool calling, and trend memory.

> **Status:** Release 5 in progress.

## Release Status

Release 5 (Configuration/CLI Closure) is in progress. The full operator CLI is available:
- `ainews onboard` — interactive setup
- `ainews providers` — LLM provider management
- `ainews sources` — content source administration
- `ainews topics` — topic management
- `ainews pipeline` — pipeline configuration
- `ainews start/stop/restart` — service lifecycle
- `ainews config` — configuration management
- `ainews backup/restore` — backup and recovery
- `ainews update` — in-place updates
- `ainews doctor` — system diagnostics
- `ainews service` — systemd service management

See `docs/cli-reference.md` for the complete command reference.

## Quick Start

### Installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
ainews onboard
ainews start
```

Channel selection:
```bash
AINEWS_CHANNEL=stable ./scripts/install.sh
AINEWS_CHANNEL=prerelease ./scripts/install.sh
AINEWS_CHANNEL=main ./scripts/install.sh
```

Non-interactive flow:
```bash
AINEWS_BOOTSTRAP_ADMIN_PASSWORD_FILE=/run/secrets/ainews-admin \
  ./scripts/install.sh --non-interactive --bootstrap ./bootstrap.yaml --start
```

### Docker (alternative)

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

### Bare Metal / Development

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

## Development Setup

For developers who want to work from a repository checkout:

### Docker

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

## Installation

### Supported Platforms

| Platform | Architecture | Status |
|----------|-------------|--------|
| Linux | x86_64 | Supported |
| Linux | arm64 | Supported |
| macOS | arm64 | Supported |
| Windows | x86_64 | WSL only |

### Installation Modes

**User installation** (default) — no root required:
```
~/.local/share/ainews/app/
~/.config/ainews/
~/.local/state/ainews/
~/.local/bin/ainews
```

**System installation** — requires explicit `--system` flag and root privileges:
```
/opt/ainews/
/etc/ainews/
/var/lib/ainews/
/var/log/ainews/
/usr/local/bin/ainews
```

### Channel Selection

| Channel | Description |
|---------|-------------|
| `stable` (default) | Latest non-prerelease GitHub release with checksum verification |
| `prerelease` | Latest GitHub prerelease |
| `main` | Exact commit SHA for development/evaluation |

### Install Metadata

The installer writes versioned metadata (channel, version, checksums, paths) to the canonical state directory for later update, rollback, and uninstall support. See [Release 3 Closure](docs/config-cli-release-3-closure.md) for details.

### Deferred Setup (Docker Absent)

If Docker is not available during installation, the installer completes the file extraction and metadata write but defers service startup. You can complete setup later when Docker is installed:

```bash
# Install without starting services
./scripts/install.sh --channel stable

# Later, after Docker is available:
ainews onboard
ainews start
```

The installer output clearly distinguishes three states: **installed** (files on disk), **configured** (onboarding complete), and **running** (services active). Re-running the installer after Docker becomes available does not replace existing configuration or secrets.

### Integrity Verification

The installer automatically verifies artifact integrity before extraction:

1. Downloads the `SHA256SUMS` file from the same release URL as the tarball
2. Computes SHA-256 of the downloaded artifact
3. Compares against the expected checksum
4. Aborts with a clear error on mismatch

The checksum is also recorded in `install-metadata.json` for auditability. To manually verify:

```bash
sha256sum -c SHA256SUMS
```

### Proxy / Firewall Considerations

The installer downloads release artifacts from `github.com`. If your environment requires a proxy:

```bash
# Set proxy for curl
export https_proxy=http://proxy.example.com:8080
export http_proxy=http://proxy.example.com:8080

# Or configure git proxy (for source installation)
git config --global http.proxy http://proxy.example.com:8080
```

Firewall rules must allow outbound HTTPS (port 443) to `github.com` and `api.github.com`. The installer also contacts Docker Hub for container images during `ainews start`.

If the installer cannot reach GitHub, it will fail with a clear error message. Use `--download-only` to test connectivity without installing.

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Checksum mismatch` | Corrupted download | Delete cached artifact, re-run installer |
| `Platform not supported` | OS/arch not in release matrix | Use WSL on Windows; check [supported platforms](#supported-platforms) |
| `Docker not found` | Docker daemon not running | Install Docker, or use `--no-start` to defer |
| `Permission denied` | System install without root | Use `--user` (default) or run with `sudo` |
| `Config already exists` | Re-running onboard | Use `ainews config set` to modify, or delete `~/.config/ainews/` |
| `Provider connection failed` | LLM provider unreachable | Check provider config with `ainews providers-test` |
| `Redis connection refused` | Redis not running | Start Redis: `redis-server &` or check `CELERY_BROKER_URL` |

### Updating

```bash
ainews update check                         # Check for available updates
ainews update plan                          # Detailed update plan with migration detection
ainews update apply                         # Apply update (auto-rollback on failure)
ainews update rollback                      # Rollback to previous version
ainews update status                        # Show current update operation status
```

Updates are channel-aware, integrity-verified, and migration-aware. A pre-update backup is created automatically before any activation. If health checks fail after activation, the update rolls back automatically.

### Channel Management

```bash
ainews channel show                         # Show current channel and version
ainews channel set stable                   # Switch to stable channel
ainews channel set prerelease               # Switch to prerelease (requires confirmation)
ainews channel set main --apply             # Switch and immediately update
ainews channel set stable --version 1.2.3   # Pin to a specific version
```

### Uninstalling

```bash
ainews uninstall                            # Remove app files, preserve config/data/backups
ainews uninstall --remove-app-only          # Remove only the application directory
ainews uninstall --purge --yes              # Remove everything (config, data, backups)
ainews uninstall --dry-run                  # Preview what would be deleted
```

By default, uninstall preserves configuration, database, backups, and operator-created state. Only application files, CLI shims, and service definitions are removed. Use `--purge` to remove everything — a final verified backup is created automatically before purge.

### Windows (WSL)

Windows native installation is not supported. Use Windows Subsystem for Linux (WSL) with a supported Linux distribution. See [Deployment Guide](docs/deployment.md) for details.

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

# Source management
ainews sources-list                      # Show configured sources
ainews sources-add --type rss            # Add a source interactively
ainews sources-test [ID]                # Test source connectivity
ainews sources-import-opml FILE          # Import from OPML
ainews sources-export-opml -o feeds.opml # Export to OPML

# Topic management
ainews topics-list                       # Show configured topics
ainews topics-add --name "AI"            # Add a topic

# Pipeline administration
ainews pipeline-show                     # Show role assignments
ainews pipeline-validate                 # Validate configuration
ainews pipeline-set-profile balanced     # Apply a named profile

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

# Updates & Channels
ainews update check                      # Check for available updates
ainews update plan                       # Detailed update plan
ainews update apply                      # Apply update (auto-rollback on failure)
ainews update rollback                   # Rollback to previous version
ainews update status                     # Show current operation status
ainews channel show                      # Show current channel
ainews channel set stable                # Switch channel

# Uninstall
ainews uninstall                         # Remove app, preserve config/data
ainews uninstall --purge --yes           # Remove everything
ainews uninstall --dry-run               # Preview without changes
```

### Service Management
- `ainews service render/install/validate/status/restart/remove` — systemd unit management
- `ainews logrotate configure-rotation/validate-rotation/remove-rotation` — logrotate management

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
| `~/.config/ainews/` | User config directory (installer-managed) |
| `~/.local/state/ainews/` | State directory including install metadata |
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
| [CLI Reference](docs/cli-reference.md) | Operator CLI commands |
| [Onboarding](docs/onboarding.md) | First-run setup, profiles, bootstrap schema |
| [Provider CLI](docs/providers-cli.md) | Provider management, testing, model discovery |
| [Release 3 Closure](docs/config-cli-release-3-closure.md) | Release 3 evidence and gate audit |
| [Release 4C Closure](docs/config-cli-release-4c-closure.md) | Update, channel, and uninstall evidence |

## Release Validation

Run one command to validate your changes match CI gates:

```bash
bash scripts/validate_release.sh          # Full: lint + tests + smoke + Docker + Compose
bash scripts/validate_release.sh --fast   # Quick: ruff + targeted smoke tests
bash scripts/validate_release.sh --security  # pip-audit + secret scanning
bash scripts/validate_artifact.sh ainews-X.Y.Z-linux-x86_64.tar.gz  # Artifact validation
```

Installer tests:

```bash
bash tests/test_install.sh               # 137 tests
bash tests/installer_e2e.sh              # 28 end-to-end tests with fault injection
pytest tests/test_cli_json_contracts.py  # 24 JSON contract tests for CLI output
```

Clean-host CI (`.github/workflows/installer-smoke.yml`) validates:
- Linux x86_64 full install + lifecycle
- Linux aarch64 native ARM
- macOS arm64
- Deferred prerequisite (no Docker)
- Docker unavailable graceful degradation

Release artifacts are built by `.github/workflows/release.yml` on `v*` tag pushes. The workflow produces platform-specific tarballs (`linux-x86_64`, `linux-aarch64`, `macos-x86_64`, `macos-aarch64`) with SHA256SUMS checksums and creates a GitHub Release.

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

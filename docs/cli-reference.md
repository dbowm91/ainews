# CLI Reference

The `ainews` operator CLI provides configuration management and system diagnostics. It is independent of the Flask application and works outside the repository directory.

## Installation

```bash
pip install -e .
```

This registers the `ainews` console command via `pyproject.toml` `[project.scripts]`.

## Global Options

| Option | Description |
|--------|-------------|
| `--verbose`, `-v` | Verbose output |
| `--quiet`, `-q` | Suppress non-error output |
| `--json`, `-j` | Output in JSON format |
| `--no-color` | Disable colored output |

## Commands

### `ainews version`

Show package version, Python version, and git commit (when available).

**Output:** Human-readable version info, or JSON with `version`, `python`, `git_commit` fields.

---

### `ainews config path`

Show all resolved configuration paths with provenance, existence, and writability.

**Output:** Table with columns: Path, Provenance, Exists, Writable.

**Provenance values:**
- `explicit` — CLI option override
- `environment` — Environment variable
- `install_metadata` — Install metadata file
- `platform_default` — OS canonical location
- `development` — Repository-local fallback

---

### `ainews config show`

Show effective configuration values grouped by file. Secrets are redacted by default.

**Options:**
- `--show-secrets` — Reveal secret values (unsafe, not recommended)

---

### `ainews config check`

Run offline syntax, schema, semantic, and production-policy validation.

**Options:**
- `--production` — Include production-specific checks
- `--json` — Machine-readable output

**Exit codes:**
- `0` — All checks passed
- `3` — Validation errors found

---

### `ainews config get KEY`

Return a typed value by dotted key. Secrets are redacted.

**Arguments:**
- `KEY` — Configuration key in dotted notation (e.g., `pipeline.writer.model`)

**Exit codes:**
- `0` — Value found and displayed
- `5` — Key not found

---

### `ainews config set KEY VALUE`

Set a configuration value. Parses through the field registry, stages the change, validates, and commits atomically.

**Arguments:**
- `KEY` — Configuration key in dotted notation
- `VALUE` — New value (parsed according to field type)

**Options:**
- `--dry-run` — Show what would change without writing

**Exit codes:**
- `0` — Value set successfully
- `2` — Configuration error
- `7` — Lock acquisition failed

---

### `ainews config set-secret KEY`

Set a secret configuration value. Reads from stdin or prompts interactively.

**Arguments:**
- `KEY` — Configuration key in dotted notation

**Note:** Do not pass secret values as command arguments — they would appear in shell history.

---

### `ainews config unset KEY`

Remove an optional configuration override, restoring the default.

**Arguments:**
- `KEY` — Configuration key in dotted notation

**Exit codes:**
- `0` — Override removed
- `2` — Attempted to remove a required value

---

### `ainews config diff`

Compare current configuration with packaged defaults.

**Options:**
- `--baseline SNAPSHOT` — Compare with a specific rollback snapshot

**Output:** Diff showing added, changed, and removed values (secrets redacted).

---

### `ainews config rollback`

List available rollback snapshots or restore a specific one.

**Options:**
- `--list` — List all available snapshots
- `--restore TRANSACTION_ID` — Restore a specific snapshot

---

### `ainews doctor`

Run system and configuration diagnostics. Three tiers of checks based on flags.

**Options:**
- `--production` — Include production-specific checks (strict `.env` permissions)
- `--quick` — Only basic checks (version, paths, config parsing)
- `--network` — Add connectivity checks (may contact external providers)

**Status model:** Each check returns one of four statuses:
- `PASS` — Check succeeded
- `WARN` — Non-blocking issue detected
- `FAIL` — Blocking failure requiring attention
- `SKIP` — Check was not applicable (e.g., Docker not installed)

**Checks performed (default):**
- Package version, schema version
- Resolved path existence, directory writability
- YAML config file parsing, cross-file validation
- Secret file permissions, database directory writability
- Python/uv availability

**Additional checks (standard):**
- Port availability
- Docker/Compose availability
- Placeholder value detection in configs
- Redis connection, database access, migration status

**Production checks:**
- Strict `.env` permissions (no world/group writability)

**Network checks:**
- Flask liveness (`/health`)
- Readiness probe
- Celery worker ping
- Provider auth validation
- SMTP connectivity
- Docker Compose service health
- Port conflict detection
- Source connectivity (adapter-specific URL extraction)

**JSON output:** Includes `all_passed` (bool), `passed_count`, `warn_count`, `failed_count`, `skipped_count`, and per-check `status` field.

**Exit codes:**
- `0` — No blocking failures (all checks PASS, WARN, or SKIP)
- `1` — One or more checks have FAIL status

## Exit Codes

| Code | Name | Description |
|------|------|-------------|
| `0` | `SUCCESS` | Command completed successfully |
| `1` | `GENERAL_ERROR` | Unrecoverable error |
| `2` | `CONFIG_ERROR` | Configuration file error |
| `3` | `VALIDATION_ERROR` | Configuration validation failed |
| `4` | `IO_ERROR` | File system error |
| `5` | `NOT_FOUND` | Requested resource not found |
| `6` | `PERMISSION_ERROR` | Insufficient permissions |
| `7` | `LOCK_ERROR` | Could not acquire configuration lock |
| `8` | `ROLLBACK_ERROR` | Rollback operation failed |

## Configuration Precedence

The CLI resolves configuration through this precedence chain:

1. **Explicit CLI options** (highest priority)
2. **Environment variables** (e.g., `AINEWS_CONFIG_DIR`)
3. **Install metadata** (`install-metadata.json`)
4. **Platform canonical location** (`~/.config/ainews/` on Linux)
5. **Repository-local fallback** (development mode, when `.git` detected)

## Secret Handling

- Secrets are redacted in all output by default (`***` or `****xxxx`)
- `config set-secret` reads from stdin to avoid shell history exposure
- `--show-secrets` is not available in Release 1
- Secret file permissions (`.env`) are checked by `doctor`

---

## Onboarding

### `ainews onboard`

Interactive first-run onboarding or reconfiguration. Walks through deployment profile selection, secret generation, admin setup, LLM provider configuration, model discovery, pipeline/source profile application, and optional service start.

**Options:**
- `--config-file`, `-c` — Bootstrap YAML file for non-interactive setup
- `--non-interactive`, `-n` — Non-interactive mode (requires `--config-file`)
- `--dry-run` — Show what would change without writing
- `--start` — Start services after onboarding completes
- `--reset` — Reset onboarding state and start over
- `--rotate-secrets` — Regenerate all application secrets

**Modes:**
- **Interactive** (default): Prompts for each decision with sensible defaults
- **Non-interactive**: Requires `--config-file` with a bootstrap YAML
- **Dry-run**: Validates configuration without writing any files

**State persistence:** Onboarding state is saved to `onboarding-state.json` in the config directory, allowing resume after interruption.

---

### Bootstrap YAML Schema

The bootstrap file provides declarative, unattended onboarding. Current schema version: `1`.

```yaml
version: 1

deployment:
  profile: docker-local          # docker-local | docker-lan | reverse-proxy | bare-metal | custom
  port: 5000
  site_url: http://localhost:5000

admin:
  username: admin
  password_env: ADMIN_PASSWORD   # Read password from env var
  # OR
  password_file: /run/secrets/admin_password  # Read password from file

provider:
  type: ollama                   # ollama | openai | anthropic | gemini | eggpool | generic
  id: ollama-local
  base_url: http://localhost:11434/v1
  api_key_env: ""                # Env var name for API key (not the key itself)
  default_model: auto

pipeline:
  profile: balanced              # lightweight-local | balanced | quality | low-cost | custom

sources:
  profile: minimal               # minimal | ai-general | ai-security | comprehensive | existing-defaults | custom

newsletter:
  enabled: false

start: false                     # Start services after onboarding
```

**Validation rules:**
- Schema version must be `1`
- `admin.password_env` or `admin.password_file` is required (no embedded passwords)
- Sensitive env var patterns (`SECRET_KEY`, `CELERY_TASK_SECRET`, `ADMIN_PASSWORD`, `SMTP_PASSWORD`) are rejected as inline values
- `${ENV_VAR}` references are resolved from the environment at validation time

**Example:**
```bash
# Validate without executing
ainews onboard --config-file bootstrap.yaml --dry-run

# Full unattended setup
export ADMIN_PASSWORD="my-secure-password"
ainews onboard --non-interactive --config-file bootstrap.yaml --start
```

---

### Deployment Profiles

| Profile | Description | Docker Required |
|---------|-------------|-----------------|
| `docker-local` | Docker Compose on localhost — development | Yes |
| `docker-lan` | Docker Compose exposed on LAN — internal network | Yes |
| `reverse-proxy` | Behind nginx/Caddy — production deployments | Yes |
| `bare-metal` | No Docker, foreground commands | No |
| `custom` | Full control over all values | No |

Each profile sets environment variable defaults for Redis URLs, database URL, and Flask config. Interactive profiles prompt for additional values (e.g., `site_url`, `trusted_proxies`).

### Pipeline Profiles

| Profile | Description |
|---------|-------------|
| `lightweight-local` | Conservative concurrency, smaller token limits, bounded timeouts |
| `balanced` | Production-like defaults, moderate concurrency and token limits |
| `quality` | Larger budgets, quality-oriented — increased latency and cost |
| `low-cost` | Smaller models, lower concurrency, reduced token ceilings |
| `custom` | Preserve current values, prompt for individual assignments |

### Source Profiles

| Profile | Description |
|---------|-------------|
| `minimal` | Single AI news RSS feed for quick setup |
| `ai-general` | General AI news sources — broad coverage |
| `ai-security` | AI safety and security focused sources |
| `comprehensive` | Full coverage — AI, security, industry, and research |
| `existing-defaults` | Keep existing sources.yaml — do not modify |
| `custom` | Start with empty sources configuration |

---

## Provider Management

### `ainews providers-list`

Show all configured providers with type, endpoint, enabled status, default flag, and pipeline role assignments.

**Options:**
- `--json`, `-j` — Output in JSON format

---

### `ainews providers-add`

Add a new LLM provider. Without `--type`, lists available adapter types. With `--type`, enters interactive field collection and optional connectivity probe.

**Options:**
- `--type`, `-t` — Provider type (`ollama`, `openai`, `anthropic`, `gemini`, `eggpool`, `generic`)
- `--skip-probe` — Skip connectivity probe after configuration
- `--json`, `-j` — Output in JSON format

**Adapter types:**
| Type | Display Name | Auth |
|------|-------------|------|
| `ollama` | Ollama | None (local) |
| `openai` | OpenAI | API key |
| `anthropic` | Anthropic | API key |
| `gemini` | Google Gemini | API key |
| `eggpool` | EggPool | API key |
| `generic` | Generic OpenAI-compatible | API key (optional) |

Each adapter implements the `ProviderSetupAdapter` protocol: `fields()`, `normalize_endpoint()`, `build_definition()`, `probe()`, `discover_models()`, `remediation()`.

**Probe behavior:** By default, a connectivity probe runs after field collection. Use `--skip-probe` to suppress. Probe results show latency and endpoint resolution status.

---

### `ainews providers-test [ID]`

Test provider connectivity and authentication. Without an argument, tests all configured providers.

**Arguments:**
- `ID` — Provider ID to test (optional, tests all if omitted)

**Options:**
- `--json`, `-j` — Output in JSON format

**Exit codes:**
- `0` — All tested providers passed
- `1` — One or more providers failed

---

### `ainews providers-models ID`

List available models for a configured provider. Discovers models via the provider's API (e.g., Ollama `/api/tags`, OpenAI `/v1/models`).

**Arguments:**
- `ID` — Provider ID (required)

**Options:**
- `--json`, `-j` — Output in JSON format

**Output:** Table with model ID, display name, context window size, and tool support indicator. Provenance shows whether models were discovered from the API, loaded from a catalog, or from configuration.

---

### `ainews providers-set-default ID`

Set a provider as the default for the pipeline fallback chain.

**Arguments:**
- `ID` — Provider ID (required)

**Exit codes:**
- `0` — Default updated
- `5` — Provider not found

---

### `ainews providers-assign ID MODEL [ROLES]`

Assign a provider and model to pipeline roles. Without `--roles`, assigns to all four roles (selector, researcher, writer, editor).

**Arguments:**
- `ID` — Provider ID (required)
- `MODEL` — Model name to assign (required)

**Options:**
- `--roles`, `-r` — Comma-separated roles (`selector`, `researcher`, `writer`, `editor`)

**Exit codes:**
- `0` — Assignment committed
- `5` — Provider not found

---

### `ainews providers-remove ID`

Remove a provider from configuration. If the provider is assigned to pipeline roles, requires `--reassign-to` to reassign those roles first.

**Arguments:**
- `ID` — Provider ID to remove (required)

**Options:**
- `--reassign-to` — Reassign roles to this provider before removal

**Exit codes:**
- `0` — Provider removed
- `5` — Provider not found
- `3` — Provider in use without reassignment

---

## Service Lifecycle

### `ainews start`

Start all ainews services (Docker Compose or bare metal). Runs `doctor` checks first unless `--skip-doctor`. Applies database migrations unless `--skip-migrations`.

**Options:**
- `--skip-doctor` — Skip prerequisite doctor checks
- `--skip-migrations` — Skip database migrations
- `--no-wait` — Don't wait for health check after start
- `--timeout` — Timeout in seconds (default: 120)
- `--json` — Output in JSON format

**Exit codes:**
- `0` — Services started successfully
- `1` — Start failed (doctor checks failed or services didn't start)

---

### `ainews stop`

Stop all ainews services.

**Options:**
- `--json` — Output in JSON format

---

### `ainews restart`

Restart all ainews services. Runs `doctor` checks first unless `--skip-doctor`.

**Options:**
- `--skip-doctor` — Skip prerequisite doctor checks
- `--timeout` — Timeout in seconds (default: 120)
- `--json` — Output in JSON format

---

### `ainews status`

Show the status of all services, including web URL, Redis, database, Celery, and pending migrations.

**Options:**
- `--json` — Output in JSON format

**Output:** Table of service states (running/stopped/failed), plus summary of infrastructure health.

---

### `ainews logs [SERVICE]`

View service logs. Without an argument, shows logs from all services.

**Arguments:**
- `SERVICE` — Service name (optional)

**Options:**
- `--tail` — Number of lines to show (default: 100)
- `--follow`, `-f` — Follow log output (live tail)
- `--timestamps`, `-t` — Show timestamps
- `--raw` — Raw passthrough without formatting

---

### `ainews health`

Check service health endpoint. Returns status (ok/degraded/error) and response time.

**Options:**
- `--timeout` — Timeout in seconds (default: 10)
- `--json` — Output in JSON format

---

### `ainews smoke`

Run post-deploy smoke checks. Tests critical endpoints and service connectivity.

**Options:**
- `--timeout` — Timeout in seconds (default: 30)
- `--json` — Output in JSON format

**Exit codes:**
- `0` — All smoke checks passed
- `1` — One or more checks failed

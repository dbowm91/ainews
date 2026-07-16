# CLI Reference

The `ainews` operator CLI provides configuration management and system diagnostics. It is independent of the Flask application and works outside the repository directory.

## Installation

```bash
pip install -e .
```

This registers the `ainews` console command via `pyproject.toml` `[project.scripts]`.

## Installer

The one-liner installer downloads and installs pre-built release artifacts. It does **not** configure the application — delegate to `ainews onboard` afterward.

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
```

**Options:**

| Option | Description |
|--------|-------------|
| `--channel CHANNEL` | Release channel: `stable` (default), `prerelease`, `main` |
| `--version VERSION` | Pin to a specific version tag (e.g. `1.4.0`) |
| `--commit SHA` | Pin to an exact commit (used with `--channel main`) |
| `--user` | User-owned paths under `~/.local/share/ainews` (default) |
| `--system` | System-wide paths under `/opt/ainews` (requires root) |
| `--prefix PATH` | Override base directory for all paths |
| `--non-interactive` | Never prompt; use defaults |
| `--yes` | Accept defaults at prompts |
| `--dry-run` | Show what would happen without executing |
| `--download-only` | Download and verify only; do not install |
| `--bootstrap PATH` | Run `ainews onboard --non-interactive --config-file PATH` after install |
| `--start` | Run `ainews start` after onboarding |
| `--no-onboard` | Skip the onboarding prompt entirely |
| `--help` | Show help and exit |

**Channel resolution:** `stable` fetches the latest GitHub release. `prerelease` includes pre-release tags. `main` builds from the branch HEAD. A `--version` or `--commit` pin overrides channel resolution.

**Environment variable mirrors:** `AINEWS_CHANNEL` (mirrors `--channel`, CLI takes precedence), `AINEWS_GITHUB_TOKEN` (GitHub API auth to avoid rate limits), `HTTPS_PROXY` / `HTTP_PROXY` (download proxy).

**Install paths:**

| Mode | Base directory |
|------|----------------|
| `user` (default) | `~/.local/share/ainews/` |
| `system` | `/opt/ainews/` |
| `--prefix` | Custom path |

**Metadata:** An `install-metadata.json` file is written to the config directory with schema version, install type, channel, and installed version. This file is read by `ainews config path` and `ainews version` to determine provenance.

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

**Options:**
- `--json`, `-j` — Output in JSON format

**JSON fields:**
- `version` — Package version (from `importlib.metadata`)
- `python` — Python interpreter version
- `git` — Short git commit hash (omitted when not in a repo)
- `config_schema` — Field registry schema version (e.g. `1.0.80`)
- `install_channel` — `stable`, `prerelease`, `main`, or `development` (when no install metadata exists)

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

**JSON output:** Uses the structured `DoctorReport` schema:

```json
{
  "schema_version": 1,
  "command": "doctor",
  "mode": {"quick": false, "production": false, "network": false},
  "outcome": "passed",
  "counts": {"pass": 12, "warn": 1, "fail": 0, "skip": 2},
  "checks": [
    {
      "name": "config_paths",
      "status": "pass",
      "passed": true,
      "message": "All paths resolved",
      "duration_ms": 4.2
    },
    {
      "name": "source_connectivity",
      "status": "fail",
      "passed": false,
      "message": "Source 'ai-news' unreachable",
      "blocking": true,
      "reason_code": "http_error",
      "details": {"url": "https://example.com/feed"}
    }
  ]
}
```

Each check may include a `reason_code` field for machine-readable failure classification (e.g. `http_error`, `dns_failure`, `timeout`, `ssrf_blocked`, `connection_failed`, `content_type_rejected`). The `--json` flag controls whether output uses this structured format or the human-readable table.

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
| `9` | `BACKUP_ERROR` | Backup/restore operation failed |
| `10` | `UPDATE_ERROR` | Update operation failed |
| `11` | `UNINSTALL_ERROR` | Uninstall operation failed |

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

## Source Management

### `ainews sources-list`

Show all configured sources with type, enabled status, endpoint, and schedule.

**Options:**
- `--json`, `-j` — Output in JSON format

---

### `ainews sources-show SOURCE_ID`

Show details for a specific source including configuration and topic matching.

**Arguments:**
- `SOURCE_ID` — Source ID to show (required)

**Exit codes:**
- `0` — Source found
- `5` — Source not found

---

### `ainews sources-add`

Add a new source interactively or from flags. Without `--type`, lists available adapter types. With `--type`, enters interactive field collection.

**Options:**
- `--type`, `-t` — Source type (`rss`, `api`, `web`)
- `--dry-run` — Show what would change without writing

**Adapter types:**
| Type | Display Name | OPML Support | Key Fields |
|------|-------------|--------------|------------|
| `rss` | RSS Feed | Yes | `feed_url` |
| `api` | REST API | No | `list_url`, `api_key` |
| `web` | Web Scraper | No | `listing_url`, `card_selector`, `link_selector` |

Each adapter implements the `SourceSetupAdapter` protocol: `fields()`, `build_definition()`, `test_source()`, `opml_repr()`, `from_opml()`.

---

### `ainews sources-update SOURCE_ID`

Update basic fields of an existing source.

**Arguments:**
- `SOURCE_ID` — Source ID to update (required)

**Options:**
- `--name` — New display name
- `--schedule` — New schedule interval in minutes (5-1440)
- `--url` — New endpoint URL

**Exit codes:**
- `0` — Source updated
- `5` — Source not found

---

### `ainews sources-enable SOURCE_ID`

Enable a disabled source.

**Arguments:**
- `SOURCE_ID` — Source ID to enable (required)

**Exit codes:**
- `0` — Source enabled or already enabled
- `5` — Source not found

---

### `ainews sources-disable SOURCE_ID`

Disable a source without removing it.

**Arguments:**
- `SOURCE_ID` — Source ID to disable (required)

**Exit codes:**
- `0` — Source disabled or already disabled
- `5` — Source not found

---

### `ainews sources-remove SOURCE_ID`

Remove a source from configuration. Associated articles and historical data are preserved.

**Arguments:**
- `SOURCE_ID` — Source ID to remove (required)

**Options:**
- `--force`, `-f` — Skip confirmation prompt

**Exit codes:**
- `0` — Source removed
- `5` — Source not found

---

### `ainews sources-test [SOURCE_ID]`

Test source connectivity and configuration using the shared safe-probe layer. Without an argument, tests all configured sources.

**Arguments:**
- `SOURCE_ID` — Source ID to test (optional, tests all if omitted)

**Options:**
- `--json`, `-j` — Output in JSON format

**Test layers:**
1. Schema validity
2. URL and SSRF safety
3. Connectivity and authentication
4. Bounded response retrieval

**Outcomes:** `reachable`, `degraded`, `blocked`, `unreachable`

---

### `ainews sources-import-opml FILE`

Import sources from an OPML file. Defaults to dry-run preview.

**Arguments:**
- `FILE` — Path to OPML file (required)

**Options:**
- `--conflict` — Conflict strategy: `skip` (default), `merge`, `replace`, `rename`
- `--no-dry-run` — Actually apply changes (default is dry-run)

**Safety features:**
- Maximum file size: 1 MB
- Maximum outline depth: 10
- Maximum outline count: 500
- XML entity declarations (XXE) rejected
- Only `http://` and `https://` URLs accepted

**Exit codes:**
- `0` — Import completed
- `4` — File I/O error

---

### `ainews sources-export-opml`

Export sources to an OPML file. Only exports enabled RSS sources with valid `feed_url`. Credentials are never included.

**Options:**
- `--output`, `-o` — Output file path (stdout if omitted)
- `--all` — Export all sources (not just enabled)

**Exit codes:**
- `0` — Export completed
- `4` — File I/O error

---

## Topic Management

### `ainews topics-list`

Show all configured topics with display name, color, and description.

**Options:**
- `--json`, `-j` — Output in JSON format

---

### `ainews topics-show TOPIC_ID`

Show details for a specific topic.

**Arguments:**
- `TOPIC_ID` — Topic ID to show (required)

**Exit codes:**
- `0` — Topic found
- `5` — Topic not found

---

### `ainews topics-add`

Add a new topic interactively or from flags.

**Options:**
- `--name` — Topic display name
- `--description` — Topic description
- `--color` — Topic color (default: `blue`)
- `--query` — Search query for matching

**Behavior:**
- Topic ID is auto-generated from the display name (lowercase, underscores)
- Duplicate IDs are rejected

---

### `ainews topics-update TOPIC_ID`

Update an existing topic's fields.

**Arguments:**
- `TOPIC_ID` — Topic ID to update (required)

**Options:**
- `--name` — New display name
- `--description` — New description
- `--color` — New color
- `--query` — New search query

**Exit codes:**
- `0` — Topic updated
- `5` — Topic not found

---

### `ainews topics-remove TOPIC_ID`

Remove a topic from configuration.

**Arguments:**
- `TOPIC_ID` — Topic ID to remove (required)

**Options:**
- `--force`, `-f` — Skip confirmation prompt

**Exit codes:**
- `0` — Topic removed
- `5` — Topic not found

---

## Pipeline Administration

### `ainews pipeline-show`

Show current pipeline role assignments (selector, researcher, writer, editor).

**Options:**
- `--json`, `-j` — Output in JSON format

---

### `ainews pipeline-validate`

Validate pipeline configuration: provider existence, model specification, enabled state.

**Options:**
- `--json`, `-j` — Output in JSON format

**Exit codes:**
- `0` — Configuration valid
- `3` — Validation errors found

---

### `ainews pipeline-set-profile`

Apply a named pipeline profile overlaying provider/model assignments.

**Options:**
- `--profile`, `-p` — Profile name: `balanced`, `fast`, `cheap` (required)

**Profiles:**
| Profile | Description |
|---------|-------------|
| `balanced` | qwen3:8b for all roles |
| `fast` | qwen3:4b for all roles |
| `cheap` | Mixed smaller models |

**Exit codes:**
- `0` — Profile applied
- `3` — Unknown profile

---

### `ainews pipeline-assign ROLE PROVIDER/MODEL`

Assign a provider/model to a pipeline role.

**Arguments:**
- `ROLE` — Pipeline role: `selector`, `researcher`, `writer`, `editor` (required)
- `PROVIDER/MODEL` — Provider and model in format `provider_id/model_name` (required)

**Exit codes:**
- `0` — Assignment committed
- `3` — Invalid role or format
- `5` — Provider not found

---

### `ainews pipeline-unassign ROLE`

Remove provider/model assignment from a pipeline role.

**Arguments:**
- `ROLE` — Pipeline role to unassign (required)

**Exit codes:**
- `0` — Unassigned
- `3` — Invalid role
- `5` — No assignment found

---

### `ainews pipeline-diff`

Show differences from a baseline pipeline configuration.

**Options:**
- `--baseline` — Baseline profile or `defaults`

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

---

## Backup and Restore

### `ainews backup create`

Create a point-in-time backup of configuration files and database.

**Options:**
- `--include-logs` — Include application log files in the backup
- `--tag TAG` — Add a human-readable tag to the backup

**Output:** Backup ID, manifest path, total size.

**Exit codes:**
- `0` — Backup created successfully
- `9` — Backup error

---

### `ainews backup list`

List available backups with creation time, version, tag, and size.

**Options:**
- `--json`, `-j` — Output in JSON format

**Output fields (text):** ID, Created, Version, Tag, Size, Verified.
**JSON fields:** `id`, `created_at`, `app_version`, `tag`, `total_bytes`, `verified`.

---

### `ainews backup show BACKUP_ID`

Show detailed information about a specific backup including section checksums and sizes.

**Arguments:**
- `BACKUP_ID` — Backup ID (required)

**Exit codes:**
- `0` — Backup found
- `5` — Backup not found

---

### `ainews backup verify BACKUP_ID`

Verify backup integrity without modifying it. Checks manifest schema, section checksums, SQLite integrity, config tarball parseability, and version compatibility.

**Arguments:**
- `BACKUP_ID` — Backup ID (required)

**Options:**
- `--json`, `-j` — Output in JSON format

**Output fields:** Status (pass/fail), sections checked, reason codes for failures.

**Reason codes:** `backup_not_found`, `manifest_missing`, `manifest_corrupt`, `manifest_invalid`, `schema_too_new`, `version_incompatible`, `section_missing`, `unsafe_path`, `file_missing`, `size_mismatch`, `checksum_mismatch`, `db_corrupt`, `config_tar_corrupt`, `config_parse_error`.

**Exit codes:**
- `0` — Backup verified successfully
- `1` — Verification failed
- `5` — Backup not found

---

### `ainews backup prune`

Remove old backups respecting retention policy (default: 10 backups, 90 days). Pinned backups are never pruned. The last verified backup is never deleted.

**Options:**
- `--max-count N` — Maximum number of backups to keep (default: 10)
- `--max-age-days N` — Maximum age in days (default: 90)
- `--dry-run` — Show which backups would be pruned without deleting

**Output:** Number of backups pruned, list of pruned backup IDs.

**Exit codes:**
- `0` — Prune completed
- `9` — Backup error

---

### `ainews restore BACKUP_ID`

Restore configuration and/or database from a verified backup. Creates an automatic pre-restore safety backup before applying changes.

**Arguments:**
- `BACKUP_ID` — Backup ID to restore from (required)

**Options:**
- `--config-only` — Restore configuration files only (skip database)
- `--data-only` — Restore database only (skip configuration files)
- `--dry-run` — Show restore plan without applying changes
- `-y`, `--yes` — Skip confirmation prompt

**Exit codes:**
- `0` — Restore completed successfully
- `1` — Restore failed
- `5` — Backup not found
- `9` — Backup error

---

### `ainews migrations status`

Show current database migration status: applied migrations, pending migrations, and current schema version.

**Options:**
- `--json`, `-j` — Output in JSON format

---

### `ainews migrations plan`

Plan pending migrations without applying them. Shows migration IDs and dependency order.

**Options:**
- `--json`, `-j` — Output in JSON format

---

### `ainews migrations apply`

Apply pending database migrations. Runs preflight checks before applying.

**Options:**
- `--dry-run` — Show migrations that would be applied without executing
- `-y`, `--yes` — Skip confirmation prompt

**Exit codes:**
- `0` — Migrations applied successfully
- `1` — Migration failed

---

## Update Commands

### `ainews update check`

Check for available updates (non-mutating). Resolves the configured channel through the same GitHub API path as the installer.

**Options:**
- `-c`, `--channel CHANNEL` — Override release channel (stable, main, prerelease)
- `-j`, `--json` — Output in JSON format

**Output includes:** Current version, latest version, channel, whether update is available, upgrade/downgrade/reinstall classification.

---

### `ainews update plan`

Show detailed update plan (non-mutating). Includes artifact size, checksum, migration steps, downtime estimate, and blockers.

**Options:**
- `-c`, `--channel CHANNEL` — Override release channel
- `-j`, `--json` — Output in JSON format

---

### `ainews update apply`

Apply an available update. Detects incomplete operations and offers resume/rollback. Creates pre-update backup, downloads artifact, verifies checksum, stops services, activates update, runs migrations, starts services, and runs health check.

**Options:**
- `-c`, `--channel CHANNEL` — Override release channel
- `--dry-run` — Show what would happen without applying
- `-y`, `--yes` — Skip confirmation prompts
- `-j`, `--json` — Output in JSON format

**Exit codes:**
- `0` — Update completed successfully
- `1` — Update failed
- `7` — Lock error (concurrent operation)
- `8` — Rollback error
- `10` — Update error

---

### `ainews update rollback`

Rollback a failed or incomplete update. Restores previous app version from backup or staging.

**Options:**
- `-y`, `--yes` — Skip confirmation prompts
- `-j`, `--json` — Output in JSON format

**Exit codes:**
- `0` — Rollback completed successfully
- `1` — Rollback failed
- `8` — Rollback error

---

### `ainews update status`

Show current update operation status. Reports phase, operation details, and incomplete operations.

**Options:**
- `-j`, `--json` — Output in JSON format

---

## Channel Commands

### `ainews channel show`

Show the current release channel, version, commit, and installation metadata.

**Options:**
- `-j`, `--json` — Output in JSON format

---

### `ainews channel set CHANNEL`

Set the release channel. Validates channel, requires confirmation for risky channels (prerelease, main). Does NOT trigger an implicit update.

**Arguments:**
- `CHANNEL` — New channel: stable, prerelease, or main

**Options:**
- `--dry-run` — Show what would change without writing
- `-y`, `--yes` — Skip confirmation prompt
- `-j`, `--json` — Output in JSON format

---

## Uninstall Command

### `ainews uninstall`

Remove ainews application files while preserving operator-owned state. By default removes only application files (binaries, code). Use `--purge` to remove config, data, and backups.

**Options:**
- `--remove-app-only` — Only remove application files, keep config/data/backups
- `--purge` — Remove everything including config, data, and backups (requires `--yes` in non-interactive mode)
- `-y`, `--yes` — Skip confirmation prompts
- `--dry-run` — Show what would be deleted without deleting
- `-j`, `--json` — Output in JSON format

**Safety:**
- Requires install metadata to determine what to remove
- Validates path ownership against approved roots
- Rejects unsafe paths (root, home, empty, unresolved variables)
- Stops services before removal

**Exit codes:**
- `0` — Uninstall completed successfully
- `1` — Uninstall failed
- `5` — Not found (no install metadata)
- `11` — Uninstall error

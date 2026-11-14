# Onboarding

`ainews onboard` provides an interactive or bootstrap-file workflow for collecting and validating deployment choices. **It does not currently write the staged environment or YAML configuration, apply migrations, start services, or verify service health.** A successful summary means the selections passed the onboarding checks, not that the installation is ready to run. Use [Configuration](configuration.md) to apply settings and [Deployment](deployment.md) to start services.

## Modes

### Interactive

```bash
ainews onboard
```

Prompts for deployment, administrator, provider, pipeline, and source choices. The command records stage status and failure details in `onboarding-state.json`, but a later invocation starts from the first stage rather than resuming the saved stage list.

### Bootstrap file

```bash
ainews onboard --non-interactive --config-file bootstrap.yaml --dry-run
```

Bootstrap files use schema version `1`. Dry-run validates the file and summarizes the selected values without writing configuration. Without `--dry-run`, the command records onboarding state and install metadata, but still does not apply the staged environment or YAML values. `--start` is accepted but service startup is deferred.

### Reset

```bash
ainews onboard --reset
```

After confirmation, this removes onboarding progress only. It does not delete or change application configuration, data, or services.

## Workflow stages

The CLI iterates through these 16 stages:

| # | Stage | Current behavior |
|---|---|---|
| 1 | `resolve_paths` | Records configuration and install paths |
| 2 | `select_deployment_profile` | Selects profile defaults in memory |
| 3 | `initialize_directories` | Creates the configuration and install directories |
| 4 | `configure_admin` | Validates and hashes the administrator password in memory |
| 5 | `generate_secrets` | Generates application secrets in memory |
| 6 | `configure_database_and_redis` | Records database and Redis URLs in memory |
| 7 | `configure_provider` | Records one provider definition in memory |
| 8 | `select_models` | Records the default model; no live model discovery is performed |
| 9 | `select_pipeline_profile` | Records a pipeline profile in memory |
| 10 | `select_source_profile` | Records a source profile in memory |
| 11 | `configure_optional_newsletter` | Records the newsletter choice |
| 12 | `validate_staged_configuration` | Validates the staged values across files |
| 13 | `apply_database_migrations` | Defers migrations to service start |
| 14 | `optionally_start` | Defers service startup |
| 15 | `verify_health` | Defers health checks to service start |
| 16 | `write_completion_record` | Writes `install-metadata.json`, not the staged configuration |

The state file records completed stages and failure details. It does not contain passwords or generated secret values. The CLI currently does not load that saved state when starting a new onboarding invocation.

## Deployment profiles

| Profile | Description | Docker required |
|---|---|---|
| `docker-local` | Compose on localhost for development or a single-machine demo | Yes |
| `docker-lan` | Compose exposed on a LAN; warns that traffic is unencrypted | Yes |
| `reverse-proxy` | Compose behind a TLS-terminating proxy | Yes |
| `bare-metal` | Foreground services on a host or VM | No |
| `custom` | Prompts for deployment values | No |

Profiles provide suggested `FLASK_CONFIG`, Redis URLs, database URL, and Docker environment defaults. The Compose file can override these values. The `reverse-proxy` profile asks for a site URL and trusted proxy settings. The `bare-metal` profile does not install systemd units; use the service CLI for that.

## Bootstrap YAML

This example shows the accepted schema. It is not a completed deployment recipe because onboarding currently stages but does not apply these values.

```yaml
version: 1

deployment:
  profile: docker-local
  port: 5000
  site_url: http://localhost:5000

admin:
  username: admin
  password_env: ADMIN_PASSWORD

provider:
  type: ollama
  id: ollama-local
  base_url: http://localhost:11434/v1
  api_key_env: ""
  default_model: qwen3:8b

pipeline:
  profile: balanced

sources:
  profile: ai-general

newsletter:
  enabled: false

start: false
```

Validation rules:

- `version` must be `1`.
- Set an administrator password with `password_env` or `password_file`. Inline passwords are rejected.
- Sensitive values must be supplied through environment references or password files, not embedded in YAML.
- Profile names must match the supported values below.
- Deployment port must be between 1 and 65535.

Validate a file without writing configuration:

```bash
export ADMIN_PASSWORD='use-a-strong-password'
ainews onboard --non-interactive --config-file bootstrap.yaml --dry-run
```

The onboarding password policy requires at least 8 characters and rejects common placeholder passwords. The standalone `scripts/hash_password.py` helper has a stricter policy; see [Configuration](configuration.md#generate-a-hashed-admin-password).

## Pipeline profiles

| Profile | Concurrency | Token limits by role | Subagents | Crawl interval |
|---|---|---|---|---|
| `lightweight-local` | 1 per role | Selector 512; others 4096 | Disabled | 60 min |
| `balanced` | 2 per role | Selector 512; others 4096 to 8192 | Unchanged | 30 min |
| `quality` | 1 to 2 per role | Selector 512; others 8192 to 16384 | Enabled | 30 min |
| `low-cost` | 1 per role | Selector 512; others 2048 | Disabled | 60 min |
| `custom` | Current values | Current values | Current values | Current value |

These values are recorded by onboarding but are not written to `pipeline.yaml`.

## Source profiles

| Profile | Sources | Topics | Note |
|---|---:|---:|---|
| `minimal` | 1 | 1 | Uses `blog.example.com`; replace this placeholder with a real public feed |
| `ai-general` | 4 | 2 | OpenAI, Google, Hugging Face, and arXiv feeds |
| `ai-security` | 2 | 2 | Alignment Forum and Anthropic feeds |
| `comprehensive` | 6 | 3 | Broader AI, research, and safety coverage |
| `existing-defaults` | Existing | Existing | Requests no source changes; the current workflow does not load existing values |
| `custom` | 0 | 0 | Starts with empty source and topic values |

The source profiles are staged in memory and do not replace `sources.yaml` or `topics.yaml`.

## Provider and secret handling

The workflow accepts Ollama, OpenAI, Anthropic, Gemini, EggPool, and generic OpenAI-compatible providers. It records one provider configuration but does not perform live model discovery or write `providers.yaml`.

Application secrets are generated in memory. Administrator passwords are hashed with Werkzeug and are not written to `.env` by onboarding. The state file stores stage metadata and profile identifiers only, not secret values. Configure the values in `.env` and the YAML files using [Configuration](configuration.md).

## Reconfiguration and troubleshooting

Use `ainews config set`, `ainews config unset`, or edit the appropriate YAML file for targeted changes. Validate with:

```bash
ainews config check
ainews config check --production
```

`onboarding-state.json` contains the last recorded failure code and message. Common codes include `MISSING_INPUT`, `INVALID_PROFILE`, `VALIDATION_FAILED`, and `IO_ERROR`. A new `ainews onboard` invocation starts a fresh in-memory workflow; it does not resume from the state file.

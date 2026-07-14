# Onboarding

The `ainews onboard` command provides a guided first-run setup for new installations. It walks through deployment profile selection, secret generation, LLM provider configuration, pipeline tuning, and optional service start.

## Modes

### Interactive (default)

```bash
ainews onboard
```

Prompts for each decision with sensible defaults. State is saved after each stage, so interrupted onboarding can be resumed.

### Non-interactive (declarative)

```bash
ainews onboard --non-interactive --config-file bootstrap.yaml
```

Requires a bootstrap YAML file. All values come from the file and environment — no prompts. Add `--start` to start services after completion.

### Dry-run

```bash
ainews onboard --dry-run
```

Validates configuration without writing any files. Useful for verifying a bootstrap file before deployment.

### Reset

```bash
ainews onboard --reset
```

Erases all onboarding progress and starts fresh.

## Onboarding Stages

The onboarding pipeline executes 16 stages in order:

| # | Stage | Description |
|---|-------|-------------|
| 1 | `resolve_paths` | Resolve configuration and data directory paths |
| 2 | `select_deployment_profile` | Choose deployment target (docker-local, bare-metal, etc.) |
| 3 | `initialize_directories` | Create config and data directories |
| 4 | `configure_admin` | Set admin username and password |
| 5 | `generate_secrets` | Generate SECRET_KEY and CELERY_TASK_SECRET |
| 6 | `configure_database_and_redis` | Set database and Redis URLs |
| 7 | `configure_provider` | Configure LLM provider connection |
| 8 | `select_models` | Choose default models for pipeline roles |
| 9 | `select_pipeline_profile` | Apply pipeline configuration profile |
| 10 | `select_source_profile` | Apply source and topic configuration |
| 11 | `configure_optional_newsletter` | Optionally enable newsletter |
| 12 | `validate_staged_configuration` | Cross-file validation of all staged config |
| 13 | `apply_database_migrations` | Run Alembic migrations |
| 14 | `optionally_start` | Start services if requested |
| 15 | `verify_health` | Verify service health endpoint |
| 16 | `write_completion_record` | Write install metadata |

Stages are tracked in `onboarding-state.json`. Failed stages record `last_failure_code` and `last_failure_message` for diagnosis.

## Deployment Profiles

| Profile | Description | Docker Required |
|---------|-------------|-----------------|
| `docker-local` | Docker Compose on localhost — development and single-machine demo | Yes |
| `docker-lan` | Docker Compose exposed on LAN — internal network access | Yes |
| `reverse-proxy` | Behind nginx/Caddy — production deployments with TLS termination | Yes |
| `bare-metal` | No Docker, foreground commands via process manager | No |
| `custom` | Full control — prompts for all values | No |

Each profile sets environment variable defaults:
- `FLASK_CONFIG` (development for docker-local, production for others)
- `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (Docker service names vs localhost)
- `DATABASE_URL` (SQLite path)
- `AINEWS_RUNNING_IN_DOCKER` (set to `1` for Docker profiles)

### Docker Networking Notes

- **docker-local**: Services communicate via Docker network. Redis host is `redis`.
- **docker-lan**: Same as docker-local but warns about unencrypted traffic.
- **reverse-proxy**: Requires TLS termination in front. Prompts for `site_url` and `trusted_proxies`.
- **bare-metal**: Uses localhost for all services. Requires Redis running locally.

## Bootstrap YAML Schema

The bootstrap file enables unattended setup. Schema version: `1`.

### Full Example

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
  default_model: auto

pipeline:
  profile: balanced

sources:
  profile: ai-general

newsletter:
  enabled: false

start: true
```

### Validation Rules

- **Schema version**: Must be `1`
- **Admin password**: Use `password_env` (env var name) or `password_file` (path). Embedded passwords are rejected.
- **Sensitive patterns**: Values matching `SECRET_KEY`, `CELERY_TASK_SECRET`, `ADMIN_PASSWORD`, or `SMTP_PASSWORD` must use `${ENV_VAR}` references.
- **Profile names**: Must be one of the known profiles (see tables above).
- **Port**: Must be an integer between 1 and 65535.

### Environment Variable References

Use `${VAR_NAME}` syntax to reference environment variables:

```yaml
admin:
  password_env: ADMIN_PASSWORD  # reads $ADMIN_PASSWORD at runtime
```

```bash
export ADMIN_PASSWORD="my-secure-password"
ainews onboard --non-interactive --config-file bootstrap.yaml
```

## Provider Setup

The onboarding wizard configures one LLM provider. The provider adapter handles endpoint normalization, credential validation, and model discovery.

### Adapter Types

| Type | Auth | Default Endpoint | Notes |
|------|------|------------------|-------|
| `ollama` | None | `http://localhost:11434/v1` | Local inference only |
| `openai` | API key | `https://api.openai.com/v1` | Cloud API |
| `anthropic` | API key | `https://api.anthropic.com` | Cloud API |
| `gemini` | API key | `https://generativelanguage.googleapis.com` | Cloud API |
| `eggpool` | API key | Custom | Managed inference |
| `generic` | Optional | Custom | Any OpenAI-compatible endpoint |

### Model Discovery

After provider configuration, the wizard discovers available models:
- **Ollama**: Queries `/api/tags` for locally pulled models
- **OpenAI/Anthropic/Gemini**: Lists models from the API
- **Generic**: Falls back to configured defaults

Models are assigned to pipeline roles (selector, researcher, writer, editor) based on the selected pipeline profile.

## Pipeline Profiles

| Profile | Concurrency | Token Limits | Subagents | Crawl Interval |
|---------|------------|--------------|-----------|----------------|
| `lightweight-local` | 1 per role | 2K-4K | Disabled | 60 min |
| `balanced` | 2 per role | 2K-8K | Enabled | 30 min |
| `quality` | 1-2 per role | 4K-16K | Enabled | 30 min |
| `low-cost` | 1 per role | 1K-2K | Disabled | 60 min |
| `custom` | User-defined | User-defined | User-defined | User-defined |

## Source Profiles

| Profile | Sources | Topics |
|---------|---------|--------|
| `minimal` | 1 feed | 1 topic |
| `ai-general` | 4 feeds (OpenAI, Google, HuggingFace, arXiv) | 2 topics |
| `ai-security` | 2 feeds (Alignment Forum, Anthropic) | 2 topics |
| `comprehensive` | 6 feeds | 3 topics |
| `existing-defaults` | Preserve existing | Preserve existing |
| `custom` | Empty | Empty |

## Secret Handling

- **Generation**: `SECRET_KEY` and `CELERY_TASK_SECRET` are generated as 64-char hex strings
- **Admin password**: Hashed with werkzeug `generate_password_hash()` (pbkdf2:sha256)
- **Password policy**: Minimum 8 characters, no known placeholder values
- **Non-interactive**: Passwords read from env vars (`password_env`) or files (`password_file`)
- **No embedded secrets**: Bootstrap validation rejects inline secret values
- **Not persisted in state**: Secrets (passwords, keys) are never written to `onboarding-state.json`. State tracks stage completion and failure metadata only — secret values are written directly to config files and never stored in the resume state.

## Reconfiguration

To reconfigure an existing installation:

1. **Re-run onboarding**: `ainews onboard` — detects existing state and resumes from incomplete stages
2. **Reset first**: `ainews onboard --reset` then `ainews onboard` — starts fresh
3. **Targeted changes**: Use `ainews config set/unset` for individual values

## Troubleshooting

### Onboarding failed at stage X

Check `onboarding-state.json` in the config directory for `last_failure_code` and `last_failure_message`. Common issues:
- `MISSING_INPUT`: Required value not provided in non-interactive mode
- `INVALID_PROFILE`: Unknown profile name
- `VALIDATION_FAILED`: Cross-file configuration errors
- `IO_ERROR`: Permission denied on config directory

### Bootstrap validation errors

Run `ainews onboard --config-file bootstrap.yaml --dry-run` to see validation errors without writing files.

### Resuming after interruption

Onboarding state is saved after each stage. Re-run `ainews onboard` to resume from the last incomplete stage.

### Provider probe failed

The probe checks connectivity but doesn't block onboarding. Use `ainews providers-test <ID>` after onboarding to diagnose. Common causes:
- Wrong endpoint URL
- Missing API key
- Network/firewall blocking access
- Ollama not running (for local inference)

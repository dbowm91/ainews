# Bootstrap Automation

This document describes the declarative bootstrap schema for unattended ainews setup.

## Bootstrap YAML Schema

The bootstrap YAML file enables fully automated, non-interactive onboarding. It follows schema version 1.

### Schema Version

```yaml
version: 1
```

Only version 1 is currently supported. Unknown versions are rejected.

### Deployment Section

```yaml
deployment:
  profile: docker-local  # docker-local, docker-lan, reverse-proxy, bare-metal, custom
  port: 5000
  site_url: http://localhost:5000
```

### Admin Section

```yaml
admin:
  username: admin
  password_env: AINEWS_BOOTSTRAP_ADMIN_PASSWORD  # Reference env var (recommended)
  # OR
  password_file: /path/to/password.txt           # Reference file (alternative)
```

**Security:** Embedded plaintext passwords are rejected by default. Always use `password_env` or `password_file` references.

### Provider Section

```yaml
provider:
  type: ollama          # ollama, openai, anthropic, gemini, eggpool, generic
  id: ollama-local
  base_url: http://localhost:11434/v1
  api_key_env: OPENAI_API_KEY  # Optional: env var reference for API key
  default_model: auto
```

### Pipeline Section

```yaml
pipeline:
  profile: balanced     # lightweight-local, balanced, quality, low-cost, custom
```

### Sources Section

```yaml
sources:
  profile: ai-general   # minimal, ai-general, ai-security, comprehensive, existing-defaults, custom
```

### Newsletter Section

```yaml
newsletter:
  enabled: false
```

### Start Section

```yaml
start: true  # Start services after onboarding completes
```

## Complete Example

```yaml
version: 1

deployment:
  profile: docker-local
  port: 5000
  site_url: http://localhost:5000

admin:
  username: admin
  password_env: AINEWS_BOOTSTRAP_ADMIN_PASSWORD

provider:
  type: eggpool
  id: eggpool
  base_url: http://eggpool:11300/v1
  api_key_env: EGGPOOL_API_KEY
  default_model: auto

pipeline:
  profile: balanced

sources:
  profile: ai-general

newsletter:
  enabled: false

start: true
```

## Commands

### Non-interactive Setup

```bash
# Set required environment variables
export AINEWS_BOOTSTRAP_ADMIN_PASSWORD="your-secure-password"
export EGGPOOL_API_KEY="your-api-key"

# Run bootstrap
ainews onboard --non-interactive --config-file bootstrap.yaml
```

### Dry Run

Preview changes without writing:

```bash
ainews onboard --dry-run --config-file bootstrap.yaml
ainews onboard --dry-run --config-file bootstrap.yaml --json
```

### Interactive Setup

```bash
ainews onboard
```

## Secret Rotation

Rotate secrets after initial setup:

```bash
# Rotate admin password only
ainews onboard --rotate-admin-password

# Rotate application secrets only
ainews onboard --rotate-application-secrets

# Rotate everything
ainews onboard --rotate-all-secrets
```

**Important:** Services must be restarted after secret rotation.

## Reconfiguration

Re-running onboarding on an existing installation enters reconfiguration mode:

- Completed stages are skipped
- Existing secrets are preserved (unless rotation flags are used)
- Existing provider definitions are preserved
- Custom YAML fields are not discarded

## Reset

Erase all onboarding progress and start fresh:

```bash
ainews onboard --reset
```

Requires confirmation (or use `--reset` with piped input).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Validation error |
| 4 | Not found |
| 5 | Lock error |
| 6 | Rollback error |

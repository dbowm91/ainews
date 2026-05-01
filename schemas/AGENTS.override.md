# Schemas Conventions

Contextual conventions for agents working in the `schemas/` directory.

## Environment Variables

Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders in configuration schemas.
- For required config (api keys, secrets), use `resolve_env_var(val, required=True)` to fail fast on missing vars.
- For optional config with defaults, use `resolve_env_var(val, required=False)` which returns empty string on missing.
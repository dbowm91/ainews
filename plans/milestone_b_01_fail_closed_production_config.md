# Milestone B.1: Fail-Closed Production Configuration

## Objective

Make production startup fail deterministically when required security or deployment configuration is missing, weak, malformed, or internally inconsistent. Development and testing can remain permissive, but `FLASK_CONFIG=production` must never start a half-configured service that appears healthy while critical controls are disabled.

## Current risk

Production validation already checks several security-sensitive values, but the earlier review found that parts of provider validation can log and continue after invalid enabled provider configuration. This weakens production startup guarantees. Milestone B.1 should make production validation explicit, structured, and test-covered.

## Affected files

Likely files:

- `config.py`
- `app.py`
- `schemas/llm.py`
- `schemas/common.py`
- `tests/`
- `.env.example`
- `docs/deployment.md`
- `docs/configuration.md`

## Required production invariants

For production config, enforce at minimum:

- `DEBUG` must be false.
- `SECRET_KEY` must be present and strong according to the project policy.
- Session cookies must be secure.
- `ADMIN_PASSWORD` must be present and must be a supported password hash.
- `CELERY_TASK_SECRET` must be present and strong enough for task-signing usage.
- `DATABASE_URL` must be valid and writable for the deployment path.
- Redis/Celery broker/result URLs must be present when Redis/Celery is required.
- At least one LLM provider must be enabled and valid.
- `default_provider` must identify an enabled, valid provider.
- Required provider env vars must resolve to non-empty values.

## Implementation plan

### Step 1: Normalize validation errors

Introduce a structured validation error approach for production config.

Recommended shape:

```python
@dataclass
class ConfigValidationIssue:
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"
```

Or use a simple list of strings if the project prefers minimal dependencies and simple control flow.

The important behavior is that production validation accumulates actionable errors and raises one `RuntimeError` containing all blocking issues.

### Step 2: Split validation into focused helpers

Refactor `ProductionConfig.validate()` into small helpers:

- `_validate_debug_disabled()`
- `_validate_secret_key()`
- `_validate_admin_password()`
- `_validate_celery_task_secret()`
- `_validate_cookie_security()`
- `_validate_database_url()`
- `_validate_redis_urls()`
- `_validate_provider_config()`

Keep helper names private unless they are useful for tests.

### Step 3: Avoid broad exception swallowing

Audit current production validation for broad `except` blocks around provider/config loading. In production:

- Missing files should fail unless an explicit documented fallback exists.
- Invalid YAML should fail.
- Unknown provider types should fail if enabled.
- Missing required API keys should fail if the provider is enabled.
- Pydantic validation errors should fail if the provider is enabled.

Development mode can log warnings. Production should fail closed.

### Step 4: Use environment-aware messaging

Error messages should say exactly what the operator must fix.

Examples:

- `SECRET_KEY must be a 64-character hex string; generate one with: python -c 'import secrets; print(secrets.token_hex(32))'`
- `ADMIN_PASSWORD must be a Werkzeug password hash; run: python scripts/hash_password.py`
- `CELERY_TASK_SECRET must be set to at least 32 random characters`
- `default_provider 'ollama-local' is enabled but host http://localhost:11434 is not valid inside Docker unless Ollama runs in the same container/network namespace`

Do not log secrets or resolved API keys.

### Step 5: Add production validation tests

Create tests that instantiate or exercise production validation with monkeypatched env vars and temporary provider configs.

Required tests:

- Missing `SECRET_KEY` fails.
- Weak or wrong-format `SECRET_KEY` fails.
- Missing `ADMIN_PASSWORD` fails.
- Plaintext `ADMIN_PASSWORD` fails.
- Missing `CELERY_TASK_SECRET` fails.
- Short `CELERY_TASK_SECRET` fails.
- `DEBUG=True` fails.
- Secure cookie config regression fails.
- No enabled provider fails.
- Enabled provider with missing API key fails.
- `default_provider` missing fails.
- `default_provider` disabled fails.
- Invalid provider YAML fails.
- Valid minimal production config passes.

### Step 6: Wire app factory smoke behavior

Add a production app factory smoke test that uses a generated valid config. This should prove `create_app("production")` fails when expected and succeeds under a minimal valid production config without needing external network calls.

Use provider settings that do not require live network access during validation. For example, validate shape and required env only; do not perform real provider health checks in app startup.

## Test strategy

Targeted tests:

```bash
uv run pytest tests/ -k "production and config" -q
```

Full tests:

```bash
uv run pytest tests/ -q
```

Lint:

```bash
uv run ruff check .
```

## Acceptance criteria

- Production validation raises a blocking error for every required missing or invalid setting.
- Provider configuration errors are not swallowed in production.
- Error messages are actionable and do not leak secrets.
- Development/testing behavior remains usable.
- Tests cover both failure and success paths.

## Handoff cautions

- Avoid live provider calls during startup validation; validate configuration, not service availability.
- Do not weaken the existing strict `SECRET_KEY` policy without an explicit product decision.
- Keep production validation deterministic. Startup should not depend on transient external network state.
- Ensure tests isolate env vars and do not depend on the developer's real `.env`.

# Milestone B.5: CI and Deployment Smoke Gates

## Objective

Extend CI beyond lint/unit/security checks so it proves production-relevant startup paths still work. The release candidate should not merge changes that break app factory startup, migrations, Celery import/configuration, Docker image build, or the documented Compose health path.

## Current risk

The current CI baseline is useful, but a green unit suite does not guarantee a deployable service. Milestone B should add smoke gates that exercise the exact failure modes likely to affect public self-hosters:

- invalid production config behavior,
- migration failures on SQLite,
- Celery app import/startup issues,
- Docker image build issues,
- Compose boot and `/health` availability,
- docs/env drift around required settings.

## Affected files

Likely files:

- `.github/workflows/ci.yml`
- `scripts/ci_smoke_app.py` or similar
- `scripts/ci_smoke_migrations.py` or similar
- `scripts/ci_smoke_celery.py` or similar
- `docker-compose.yml`
- optional `docker-compose.ci.yml`
- `tests/`
- `.env.example`
- docs check scripts if added

## CI smoke layers

### Layer 1: Production config validation smoke

Goal: Prove production app factory fails when config is invalid and succeeds under a generated minimal valid config.

Implementation options:

- Python test file under `tests/`.
- Script invoked in CI.

Recommended test cases:

- `create_app("production")` fails with missing production secrets.
- `create_app("production")` succeeds with generated valid secrets and a valid local/dummy provider config.
- Invalid enabled provider fails production validation.
- Disabled invalid provider does not fail if config file shape remains valid.

Avoid live network calls.

### Layer 2: Migration smoke

Goal: Prove migrations apply cleanly to a fresh SQLite DB.

Implementation options:

- CI script that sets `DATABASE_URL=sqlite:////tmp/ainews-ci.db` and runs `flask db upgrade`.
- Pytest that uses Alembic command APIs.

Recommended CI command:

```bash
DATABASE_URL=sqlite:////tmp/ainews-ci.db \
FLASK_CONFIG=production \
SECRET_KEY=<generated> \
ADMIN_PASSWORD=<generated_hash> \
CELERY_TASK_SECRET=<generated> \
uv run flask db upgrade
```

If provider validation blocks this, provide a test provider config file/env for CI.

### Layer 3: Celery import/config smoke

Goal: Prove `celery_app:celery_app` imports and configures with the app context.

Suggested script:

```bash
uv run python - <<'PY'
from celery_app import celery_app
print(celery_app.main)
print(celery_app.conf.broker_url)
PY
```

Better script:

- Imports Celery app.
- Lists registered task names.
- Verifies broker/result URLs are configured.
- Does not require Redis to be live unless running Compose integration.

### Layer 4: Docker image build smoke

Goal: Prove the Dockerfile builds on CI.

Existing Docker build job may already cover this. Keep it as a required gate.

Recommended enhancements:

- Use Docker BuildKit.
- Optionally use `docker build --target runtime` if named stages exist.
- Validate image can print Python version or import app module.

Example:

```bash
docker build -t ainews:ci .
docker run --rm --entrypoint python ainews:ci -c "import run; print('ok')"
```

### Layer 5: Docker Compose config smoke

Goal: Prove Compose files are syntactically valid.

Commands:

```bash
docker compose config
```

If adding an Ollama override:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config
```

This is cheap and should be in required CI.

### Layer 6: Docker Compose boot smoke

Goal: Prove the documented stack boots and `/health` responds.

Suggested approach:

- Generate `.env.ci` with valid production secrets.
- Use a CI-specific provider config that does not require live external LLM calls or use a disabled provider only if app health does not require provider availability.
- Start Redis, migration, web, worker, beat as needed.
- Wait for `/health` with timeout.
- Dump service logs on failure.
- Tear down volumes after test.

Example flow:

```bash
cp .env.example .env.ci
# script writes generated required values
COMPOSE_ENV_FILE=.env.ci docker compose up -d --build
./scripts/wait_for_health.sh http://localhost:5000/health 60
curl -fsS http://localhost:5000/health
COMPOSE_ENV_FILE=.env.ci docker compose down -v
```

Adapt to actual Compose env-file support. If Compose cannot use `COMPOSE_ENV_FILE`, use `--env-file .env.ci` where supported.

### Layer 7: Docs/env consistency smoke

Goal: Catch drift between runtime-required env vars and docs.

Possible simple test:

- `tests/test_docs_env_consistency.py` reads `.env.example`, README, and docs and checks required production variable names appear.
- Do not overfit docs wording; check presence and section headings.

## Workflow design

Recommended CI job structure:

1. `lint-test`: ruff and pytest.
2. `production-config-smoke`: generated env, production config tests.
3. `migration-smoke`: fresh SQLite upgrade.
4. `celery-smoke`: import/config check.
5. `docker-build`: existing build job, required.
6. `compose-smoke`: `docker compose config`; optional full boot if CI time is acceptable.
7. `security`: pip-audit, Trivy, Gitleaks.

If CI time is a concern, make full Compose boot required only on `main` and PRs that touch Docker/config/deployment files, but keep `docker compose config` always required.

## Generated CI secrets

Use generated throwaway values in CI:

```bash
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
CELERY_TASK_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
ADMIN_PASSWORD=$(python scripts/hash_password.py --password ci-password)  # if script supports noninteractive mode
```

If `hash_password.py` is interactive only, add a noninteractive mode:

```bash
python scripts/hash_password.py --password "$ADMIN_PLAINTEXT"
```

or a CI-only helper that calls Werkzeug directly without exposing the password in logs.

## Test plan

Local validation commands after implementation:

```bash
uv run ruff check .
uv run pytest tests/ -q
uv run pytest tests/ -k "production or provider or deployment or migration or celery" -q
docker compose config
docker build -t ainews:ci .
```

If Compose boot smoke is implemented:

```bash
./scripts/ci_compose_smoke.sh
```

## Acceptance criteria

- CI fails when production app startup is broken.
- CI fails when fresh SQLite migration is broken.
- CI fails when Celery app import/config is broken.
- CI fails when Docker image build is broken.
- CI validates Compose syntax.
- Full Compose boot smoke is either required or explicitly documented as a staged follow-up with a script ready to run locally.
- Failure logs are actionable.

## Handoff cautions

- Do not call live LLM APIs in CI smoke.
- Do not require a GPU or model download in required CI.
- Do not print generated secrets in logs.
- Do not make smoke jobs depend on a developer's local `.env`.
- Keep scripts idempotent and ensure Compose teardown runs on failure.

## Closure Note

**Status: COMPLETE** (2026-07-08)

Milestone B corrective work is done. The following gaps have been addressed:

- **Migration smoke** (`tests/test_smoke_migrations.py`): Now runs real `flask db upgrade` via subprocess against a fresh SQLite DB, verifies `alembic_version` table and schema (including `api_tokens` columns).
- **Production app-factory smoke** (`tests/test_smoke_production_config.py`): `TestIntegratedProductionAppFactory` exercises `create_app("production")` via subprocess with real provider validation (no noop patching).
- **Ollama healthcheck** (`docker-compose.ollama.yml`): Changed from `curl -sf http://localhost:11434/api/tags` to `["CMD", "ollama", "list"]` since the ollama image ships the `ollama` binary but not `curl`.
- **CI docker-build** (`.github/workflows/ci.yml`): Added "Production mode image smoke" step that uses `FLASK_CONFIG=production` with proper secrets and `tests/fixtures/providers.ci.yaml`.
- **Compose boot smoke** (`scripts/ci_compose_smoke.sh`): Hardened (password hashing, web log dumping, `.env.ci` cleanup in trap, password validation). Remains a manual gate — requires a Docker daemon and is not wired into CI.

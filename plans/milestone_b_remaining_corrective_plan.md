# Milestone B Remaining Corrective Plan

**Status: COMPLETE** — All six workstreams have been implemented and verified. See `plans/milestone_b_05_ci_deployment_smoke.md` closure note for details.

## Purpose

This plan closes the remaining Milestone B gaps found after the first production-startup/deployment implementation pass. The repo now has substantially stronger production validation, recursive env-var resolution, Docker/Ollama guidance, docs alignment, and CI smoke jobs. The remaining work is narrower: ensure the smoke tests prove the intended deployment paths rather than approximating them, verify the Ollama Compose healthcheck, and add one integrated production app-factory path that does not bypass provider validation.

## Current state summary

Implemented since the Milestone B plans:

- `ProductionConfig.validate()` now uses structured validation issues and fail-closed aggregation.
- Production secret validation is stricter and includes actionable fix hints.
- Enabled provider validation checks provider type, provider config, API key env placeholders, and default-provider consistency.
- `schemas.common.resolve_env_vars()` now resolves nested dict/list env placeholders.
- Docker runtime and Compose services set `AINEWS_RUNNING_IN_DOCKER=1`.
- Docker/Ollama config now warns about `localhost` inside containers.
- `docker-compose.ollama.yml` was added.
- `.env.example`, README, deployment docs, troubleshooting, and security docs were updated.
- CI now validates Compose syntax, Docker build, app factory import in the image, production config smoke tests, Celery smoke tests, migration smoke tests, and docs consistency tests.
- `scripts/ci_compose_smoke.sh` and `scripts/wait_for_health.sh` were added.

Remaining issues:

1. `tests/test_smoke_migrations.py` does not run real Alembic migrations; it creates a testing app and relies on `db.create_all()` behavior.
2. `scripts/ci_compose_smoke.sh` exists but is not wired into CI.
3. `docker-compose.ollama.yml` uses a `curl` healthcheck inside the `ollama/ollama` container; that may fail if the image lacks `curl`.
4. The production app-factory smoke test currently patches provider validation to a noop, so it does not prove the integrated valid-provider path.
5. CI image smoke uses testing config only; production image startup is partially covered by pytest but not by a real container production startup path.

## Workstream 1: Replace migration smoke with real Alembic upgrade

### Problem

Current migration smoke checks that tables exist after `create_app("testing")`, but testing mode creates tables via SQLAlchemy rather than proving Alembic migrations apply cleanly. This misses migration-script errors, SQLite batch-mode mistakes, revision-chain issues, and env-dependent migration failures.

### Target behavior

The migration smoke should run the same migration mechanism used in deployment:

```bash
flask db upgrade
```

against a fresh temporary SQLite database.

### Implementation options

#### Option A: Subprocess smoke test

Use `subprocess.run()` from pytest to invoke Flask CLI in a clean env.

Suggested test shape:

```python
def test_flask_db_upgrade_fresh_sqlite(tmp_path):
    db_path = tmp_path / "smoke.db"
    env = os.environ.copy()
    env.update({
        "FLASK_CONFIG": "production",
        "SECRET_KEY": "a" * 64,
        "ADMIN_PASSWORD": generate_password_hash("ci-password"),
        "CELERY_TASK_SECRET": "b" * 32,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "CELERY_BROKER_URL": "redis://localhost:6379/15",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/15",
        "LLM_PROVIDERS_FILE": str(valid_providers_yaml),
    })
    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

This is closest to deployment behavior.

#### Option B: Alembic command API

Use Alembic directly from pytest:

```python
from alembic import command
from alembic.config import Config as AlembicConfig

cfg = AlembicConfig(str(ROOT / "migrations" / "alembic.ini"))
command.upgrade(cfg, "head")
```

This can be cleaner but may require correctly wiring Flask-Migrate config paths. Use only if the project already has reliable Alembic config fixtures.

Recommended: Option A, because deployment uses the Flask CLI path.

### Required checks after upgrade

After `flask db upgrade` succeeds:

- Connect to the SQLite DB.
- Assert `alembic_version` exists.
- Assert key tables exist: `articles`, `sources`, `admin_users`, `api_tokens`, `pipeline_runs`, `newsletters`, `tags`.
- Assert `api_tokens` contains `token_hash` and `revoked_at` columns.
- Assert `token_hash` type/size is compatible where introspection allows.

### Acceptance criteria

- Migration smoke fails if Alembic revision chain is broken.
- Migration smoke fails if SQLite-incompatible migration operations are introduced.
- Migration smoke no longer depends on `db.create_all()`.
- CI runs the real migration smoke.

## Workstream 2: Add integrated production app-factory smoke without provider-validation bypass

### Problem

Some app-factory smoke tests patch `_validate_llm_providers` to a noop. This is useful for isolating app startup, but it does not prove a complete valid production config path with provider validation enabled.

### Target behavior

Add at least one test that:

- Creates a temporary providers YAML file.
- Sets env vars for required secrets and provider credentials.
- Points the app/config loader at the temporary providers YAML.
- Calls `create_app("production")` without patching `_validate_llm_providers`.
- Does not perform live LLM/network calls.

### Implementation steps

1. Create a temporary provider config with one enabled provider and valid config.
2. Prefer an Ollama provider if validation does not perform live calls:

```yaml
default_provider: ollama-local
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      host: http://ollama:11434
      model: qwen3:8b
```

3. Or use an OpenAI-compatible provider with a fake but non-empty API key if validation only checks shape/env presence:

```yaml
default_provider: openai
providers:
  - id: openai
    type: openai
    enabled: true
    config:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4o
```

4. Set `OPENAI_API_KEY=sk-test-not-real` in the test env if using the cloud-provider path.
5. Ensure no live API call is made during startup.
6. Call `create_app("production")` and assert key config values.

### Caveat: class attribute env capture

`ProductionConfig` class attributes are evaluated at import time. Tests may need to monkeypatch class attributes directly, reload `config`, or run a subprocess with env set before import. A subprocess smoke is often cleaner for integrated config tests.

### Acceptance criteria

- At least one production app factory test exercises provider validation without a noop patch.
- The test is deterministic and performs no network calls.
- Failure messages clearly identify production config or provider validation problems.

## Workstream 3: Verify and fix Ollama Compose healthcheck

### Problem

`docker-compose.ollama.yml` uses:

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:11434/api/tags || exit 1"]
```

The `ollama/ollama` image may not include `curl`. If not, the service will remain unhealthy and `web`/`celery-worker` dependencies will never start when using the override.

### Verification steps

Run locally or in CI:

```bash
docker run --rm ollama/ollama:latest sh -lc 'command -v curl || command -v wget || command -v ollama'
```

Also validate:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config
```

and, if acceptable:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d ollama
```

### Fix options

#### Option A: Use an Ollama CLI healthcheck

If the image includes the `ollama` CLI and it can query the local server:

```yaml
healthcheck:
  test: ["CMD", "ollama", "list"]
```

Verify this works before committing.

#### Option B: Use `wget` if present

```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://localhost:11434/api/tags >/dev/null || exit 1"]
```

Only use if `wget` is present.

#### Option C: Remove the healthcheck dependency

If the image lacks suitable tooling, remove the Ollama healthcheck and do not make `web` depend on `ollama: condition: service_healthy`. Instead:

- Start Ollama as a best-effort service.
- Document that first LLM requests may fail until Ollama is ready/model is pulled.
- Optionally add a host-side script to wait for `http://localhost:11434/api/tags` from outside the container.

#### Option D: Build a tiny custom Ollama wrapper image

Not recommended for this milestone. It increases maintenance and build time.

### Recommended path

Try Option A first. If `ollama list` is reliable as a healthcheck, use it. If not, prefer Option C over a brittle dependency on `curl`.

### Acceptance criteria

- `docker-compose.ollama.yml` healthcheck uses a command available in the image, or the healthcheck is removed.
- `docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet` passes.
- The docs accurately describe readiness/model-pull requirements.
- The override does not expose Ollama beyond localhost unless explicitly changed.

## Workstream 4: Wire Compose boot smoke into CI or explicitly stage it

### Problem

`scripts/ci_compose_smoke.sh` is substantial and useful, but CI currently does not execute it. CI validates Compose syntax and Docker build, but not the real `db-migrate -> web -> /health` path.

### Preferred implementation

Add a CI step or job that runs:

```bash
bash scripts/ci_compose_smoke.sh
```

in the Docker/Compose job after image build, or in a separate `compose-smoke` job.

### Practical CI constraints

The script starts Redis, db-migrate, and web. It does not start worker/beat. That is acceptable for a first required smoke gate. If it is too slow for every PR, gate it on file changes or run it on `main` plus PRs touching deployment-sensitive files.

Suggested deployment-sensitive paths:

- `Dockerfile`
- `docker-compose*.yml`
- `config.py`
- `app.py`
- `celery_app.py`
- `migrations/**`
- `requirements` / `pyproject.toml` / `uv.lock`
- `scripts/ci_compose_smoke.sh`
- `.github/workflows/ci.yml`

### Required script hardening before CI

Check script behavior before wiring into CI:

1. `scripts/hash_password.py ci-test-password-123` must be noninteractive and must output the expected `ADMIN_PASSWORD=` line.
2. The generated `.env.ci` must satisfy production provider validation.
3. If the default provider is Ollama but the main Compose file does not include an Ollama service, production validation must not fail due to Docker-localhost warning severity. If runtime calls are not made during `/health`, this is acceptable.
4. The script should dump web logs on health failure, not only db-migrate logs.
5. The script should remove `.env.ci` on cleanup or document that it is disposable and ignored by Git.
6. The script should use `docker compose --env-file` consistently.

### Add web log dumping

On health timeout/failure, include:

```bash
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs web
```

Also dump Redis/db-migrate logs if relevant.

### Acceptance criteria

- CI executes a Compose boot smoke or the repo contains an explicit follow-up note explaining why it is manual only.
- The script generates valid throwaway production config.
- Smoke failure logs are actionable.
- The smoke path proves db migration service completes and web responds on `/health`.

## Workstream 5: Strengthen production image smoke

### Problem

The Docker image smoke currently runs `create_app` under `FLASK_CONFIG=testing`. That proves imports work in the image, but not production validation behavior in the container.

### Target behavior

Add a production-mode image smoke that:

- Uses generated valid production secrets.
- Uses a temp or mounted provider config that validates without network calls.
- Imports `create_app("production")` or starts a short-lived app factory check.
- Does not require Redis/network unless intentionally testing Compose.

### Implementation option

Use a `docker run` command with env vars and a mounted temporary provider file if necessary. If mounting from CI is awkward, add a minimal `providers.ci.yaml` under `tests/fixtures/` with non-secret fake values and point to it via `LLM_PROVIDERS_FILE`.

Example:

```bash
docker run --rm \
  -e FLASK_CONFIG=production \
  -e SECRET_KEY=<generated 64 hex> \
  -e ADMIN_PASSWORD=<generated hash> \
  -e CELERY_TASK_SECRET=<generated secret> \
  -e DATABASE_URL=sqlite:////tmp/prod-smoke.db \
  -e CELERY_BROKER_URL=redis://localhost:6379/0 \
  -e CELERY_RESULT_BACKEND=redis://localhost:6379/1 \
  -e LLM_PROVIDERS_FILE=/app/tests/fixtures/providers.ci.yaml \
  ainews-ci \
  python -c "from app import create_app; create_app('production'); print('Production app factory OK')"
```

### Acceptance criteria

- Docker image smoke covers production config path, not only testing config.
- The smoke remains deterministic and does not require live LLM API calls.
- Secrets are generated or fake non-sensitive values and are not printed unnecessarily.

## Workstream 6: Update docs/plans after closure

### Required doc updates

If Compose boot smoke is wired into CI:

- Update `plans/milestone_b_05_ci_deployment_smoke.md` with a closure note.
- Update `.opencode/skills/testing/SKILL.md` or AGENTS guidance if it now names the smoke command.
- Update `docs/troubleshooting.md` with any new failure modes discovered.

If Compose boot smoke remains manual:

- Document exactly why it is manual.
- Add a release checklist item requiring manual run before tagging.

### Acceptance criteria

- Milestone B docs do not overstate CI coverage.
- Release checklist distinguishes required CI gates from manual pre-release validation.

## Suggested execution order

1. Fix `tests/test_smoke_migrations.py` to run real `flask db upgrade`.
2. Add integrated production app-factory test without provider-validation noop.
3. Verify and fix `docker-compose.ollama.yml` healthcheck.
4. Harden `scripts/ci_compose_smoke.sh` failure logging and generated config.
5. Wire Compose boot smoke into CI, or explicitly stage it as manual with rationale.
6. Add production-mode Docker image smoke.
7. Update docs/plans/checklists.
8. Run targeted and full validation.

## Validation commands

Targeted smoke tests:

```bash
uv run pytest tests/test_smoke_migrations.py tests/test_smoke_production_config.py tests/test_smoke_celery.py tests/test_docs_env_consistency.py -q
```

Full tests:

```bash
uv run pytest tests/ -q
```

Lint:

```bash
uv run ruff check .
```

Compose syntax:

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet
```

Docker image smoke:

```bash
docker build -t ainews-ci .
```

Compose boot smoke:

```bash
bash scripts/ci_compose_smoke.sh
```

Ollama healthcheck verification:

```bash
docker run --rm ollama/ollama:latest sh -lc 'command -v curl || command -v wget || command -v ollama'
```

## Final acceptance criteria

This corrective pass is complete when:

- Migration smoke runs real Alembic/Flask migration commands against a fresh SQLite DB.
- Integrated production app-factory smoke exercises provider validation without a noop patch.
- Ollama Compose healthcheck is verified or removed/reworked.
- Compose boot smoke is executed in CI or explicitly marked as a manual pre-release gate with rationale.
- Docker image smoke includes a production-mode app factory check.
- Failure logs from smoke scripts are actionable.
- Docs and plans accurately describe what CI proves.
- Targeted smoke tests, full tests, ruff, Compose config validation, Docker build, and Compose smoke pass locally or in CI.

## Non-goals

This plan does not cover SSRF-safe fetching, public release status/version cleanup, full external provider health checks, model download automation, GPU scheduling, or production observability. Those remain in later milestones.

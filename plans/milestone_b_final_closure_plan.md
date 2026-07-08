# Milestone B Final Closure Plan

## Purpose

This is the final Milestone B closure handoff. The prior corrective pass resolved the substantive implementation gaps: real Alembic migration smoke now exists, integrated production app-factory validation runs without provider-validation bypass, production-mode Docker image smoke is in CI, the Ollama healthcheck was changed from `curl` to `ollama list`, and the Compose smoke script was hardened with better generated config and failure logs.

One release-process decision remains: whether the full Docker Compose boot smoke (`redis -> db-migrate -> web -> /health`) must run in GitHub Actions or remain a documented manual pre-release gate. This plan closes that final decision and captures the final verification steps for Milestone B.

## Current state summary

Implemented and inspected:

- `tests/test_smoke_migrations.py` now runs real `python -m flask db upgrade` against a fresh SQLite database.
- Migration smoke verifies core tables, `alembic_version`, and `api_tokens.revoked_at` / `api_tokens.token_hash` columns.
- Migration smoke runs upgrade twice to check idempotency.
- App startup during migration no longer tries to seed `share_configs` before the table exists.
- A new root migration creates previously missing model tables required by later migration/index scripts.
- `tests/test_smoke_production_config.py` includes an integrated production app-factory subprocess test with real provider validation.
- `tests/fixtures/providers.ci.yaml` provides a deterministic CI provider config.
- CI includes a production-mode Docker image smoke.
- `docker-compose.ollama.yml` now uses `ollama list` for healthcheck instead of `curl`.
- `scripts/ci_compose_smoke.sh` now validates hashed admin password generation and dumps web logs on failures.

Remaining issue:

- CI does not appear to run `scripts/ci_compose_smoke.sh`. The script exists and is useful, but the workflow currently proves Compose syntax, Docker build, production image app-factory startup, migration smoke, Celery smoke, and docs consistency—not the full Compose boot path.

## Final decision required

Choose one of these two release policies.

### Option A: Required CI Compose boot smoke

Make `scripts/ci_compose_smoke.sh` a required CI gate.

Recommended if:

- GitHub Actions runtime is acceptable.
- Docker Compose is reliable enough in the CI environment.
- We want PRs touching deployment-sensitive paths to fail before merge if the full Compose boot path is broken.

### Option B: Manual pre-release Compose boot smoke

Keep `scripts/ci_compose_smoke.sh` as a required manual command before tagging/releasing, and document it clearly.

Recommended if:

- CI runtime or flakiness is a concern.
- Compose boot is too slow for every PR.
- The existing CI gates are considered sufficient for normal PRs, with full boot smoke reserved for release candidates.

Preferred default: Option A for `main` and deployment-sensitive PRs, or Option B only if CI proves too slow/flaky after attempting Option A.

## Workstream 1: Wire Compose boot smoke into CI or document it as manual

### Option A implementation steps

Add a `compose-smoke` job to `.github/workflows/ci.yml` or extend `docker-build`.

Suggested separate job:

```yaml
compose-smoke:
  runs-on: ubuntu-latest
  needs: docker-build
  steps:
    - uses: actions/checkout@v4
    - name: Run Docker Compose boot smoke
      run: bash scripts/ci_compose_smoke.sh
```

Potential optimization:

- Run on `push` to `main` always.
- Run on PRs only when deployment-sensitive paths change.
- Keep `docker compose config --quiet` always required.

Deployment-sensitive paths:

- `Dockerfile`
- `docker-compose*.yml`
- `.github/workflows/ci.yml`
- `config.py`
- `app.py`
- `celery_app.py`
- `extensions.py`
- `migrations/**`
- `scripts/ci_compose_smoke.sh`
- `scripts/wait_for_health.sh`
- `pyproject.toml`
- `uv.lock`

If path-filtering is added, use a well-maintained action or keep it simple and run the job unconditionally until runtime is measured.

### Option B implementation steps

If CI does not run the script, update docs and agent guidance so this is explicit:

- Add a release checklist section to `docs/deployment.md` or a dedicated `docs/release_checklist.md`.
- Add `bash scripts/ci_compose_smoke.sh` as a mandatory pre-release command.
- Note that CI validates production app-factory, migrations, Docker image, Compose syntax, Celery smoke, and docs consistency, while manual release validation verifies the full Compose boot path.
- Update `plans/milestone_b_05_ci_deployment_smoke.md` with a closure note saying which policy was chosen.
- Update `AGENTS.md` / `.opencode/skills/testing/SKILL.md` so coding agents do not claim CI runs full Compose boot if it remains manual.

### Acceptance criteria

One of these is true:

- CI runs `bash scripts/ci_compose_smoke.sh`, or
- release docs explicitly require manual `bash scripts/ci_compose_smoke.sh` before public release/tagging and state that CI does not run full Compose boot.

## Workstream 2: Verify the hardened Compose smoke locally

Run:

```bash
bash scripts/ci_compose_smoke.sh
```

Expected behavior:

- Generates `.env.ci` if absent.
- Generates valid 64-hex `SECRET_KEY`.
- Generates hashed `ADMIN_PASSWORD`.
- Generates valid `CELERY_TASK_SECRET`.
- Validates Compose config.
- Builds images unless `--skip-build` is used.
- Starts Redis and `db-migrate`.
- Waits for `db-migrate` to exit successfully.
- Starts `web`.
- Waits for `/health`.
- Dumps useful logs if migration or web startup fails.
- Tears down containers and volumes on exit.

If this fails, fix the script or Compose file before marking Milestone B closed.

Potential failure points to check:

- `scripts/hash_password.py ci-test-password-123` output format.
- `LLM_PROVIDERS_FILE` / provider config resolution inside Compose.
- `providers.yaml` default provider using localhost Ollama in Docker.
- migration chain problems from the new root migration.
- read-only container filesystem and writable volume paths.
- `/health` response shape.

## Workstream 3: Verify Ollama override healthcheck

Although `ollama list` is a better healthcheck than `curl`, verify it in the actual image.

Run:

```bash
docker run --rm ollama/ollama:latest sh -lc 'command -v ollama && ollama list >/dev/null 2>&1; echo $?'
```

Then run:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet
```

If acceptable for local validation:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d ollama
```

If `ollama list` exits nonzero before the daemon is ready or cannot talk to the daemon in healthcheck context, choose one:

- increase `start_period`,
- use an image-supported local HTTP check if tooling exists,
- remove the `condition: service_healthy` dependency and document readiness behavior,
- or keep the override as manual/experimental until verified.

Acceptance criteria:

- The Ollama healthcheck command exists in the image.
- The healthcheck reaches healthy on a fresh start, or the override no longer depends on it.
- Docs do not claim the override is fully validated unless it has been run.

## Workstream 4: Confirm migration-chain compatibility policy

The corrective pass added a new root migration and rewired `001_initial` to depend on it. This is acceptable for a pre-release project, but it can be unsafe for already-deployed databases.

Implementation steps:

1. Decide whether existing deployed DB compatibility is required.
2. If no deployed DB compatibility is required, document that migration history was normalized before public release.
3. If compatibility is required, replace root-history rewrite with a forward-only migration that creates missing tables conditionally.
4. Ensure `flask db upgrade` passes from a fresh DB and from a DB at the previous `head`.

Acceptance criteria:

- The repo has an explicit stance on migration-history rewrite before public release.
- Fresh DB migration smoke passes.
- If existing deployment compatibility matters, upgrade-from-prior-head smoke also passes.

## Workstream 5: Final CI and local validation matrix

Run the targeted smoke set:

```bash
uv run pytest tests/test_smoke_migrations.py tests/test_smoke_production_config.py tests/test_smoke_celery.py tests/test_docs_env_consistency.py -q
```

Run the broader production/config set:

```bash
uv run pytest tests/test_production_config.py tests/test_docs_alignment.py tests/test_docs_env_consistency.py -q
```

Run the full test suite:

```bash
uv run pytest tests/ -q
```

Run lint:

```bash
uv run ruff check .
```

Run Docker/Compose checks:

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet
docker build -t ainews-ci .
```

Run production-mode image smoke if not already covered by CI:

```bash
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
HASHED_PW=$(python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('ci-test-password-123'))")
CELERY_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
docker run --rm \
  -e FLASK_CONFIG=production \
  -e SECRET_KEY="$SECRET_KEY" \
  -e ADMIN_PASSWORD="$HASHED_PW" \
  -e CELERY_TASK_SECRET="$CELERY_SECRET" \
  -e DATABASE_URL=sqlite:////tmp/prod-smoke.db \
  -e CELERY_BROKER_URL=redis://localhost:6379/0 \
  -e CELERY_RESULT_BACKEND=redis://localhost:6379/1 \
  -e LLM_PROVIDERS_FILE=/app/tests/fixtures/providers.ci.yaml \
  ainews-ci \
  python -c "from app import create_app; create_app('production'); print('Production app factory OK')"
```

Run full Compose boot smoke:

```bash
bash scripts/ci_compose_smoke.sh
```

## Final Milestone B acceptance criteria

Milestone B is closed when all of the following are true:

- Production config validation fails closed on missing/weak secrets and invalid enabled providers.
- `default_provider` must exist, be enabled, and validate.
- Nested env-var placeholders resolve correctly.
- Docker/Ollama deployment path is documented and Compose config validates.
- Real Alembic migration smoke runs against fresh SQLite.
- Integrated production app-factory smoke runs without provider-validation bypass.
- Production-mode Docker image smoke runs in CI.
- Full Compose boot smoke is either CI-required or explicitly documented as a manual pre-release gate.
- Ollama override healthcheck is verified or changed to avoid unverified `service_healthy` dependency.
- CI and docs accurately state what is automated versus manual.

## Non-goals

This closure plan does not address SSRF-safe fetching, public release version/status cleanup, external LLM API health checks, model download automation, full observability, or release announcement polish. Those remain in later milestones.

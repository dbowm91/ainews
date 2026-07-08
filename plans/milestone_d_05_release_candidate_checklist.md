# Milestone D.5: Release Candidate Checklist

## Objective

Create a concrete release-candidate checklist that ties together the hardening work from Milestones A-D. The checklist should be usable by a human maintainer or coding agent to decide whether the repo is ready for public release.

## Deliverable

Add `docs/release_checklist.md` or a release section in `docs/deployment.md` containing commands, expected results, and failure handling.

## Checklist sections

### 1. Source tree state

- Confirm working tree clean.
- Confirm branch is `main` or release branch.
- Confirm version/status values are intentional.
- Confirm `README.md` release maturity language matches package metadata.

Commands:

```bash
git status --short
git branch --show-current
git log --oneline -5
```

### 2. Python/test validation

```bash
uv run ruff check .
uv run pytest tests/ -q
uv run pytest tests/test_smoke_production_config.py tests/test_smoke_migrations.py tests/test_smoke_celery.py tests/test_docs_env_consistency.py -q
```

Include scoped type gate if Milestone D.4 adds it.

### 3. Security validation

```bash
uv run pip-audit
trivy fs .
gitleaks detect --source .
```

If image scanning is adopted:

```bash
docker build -t ainews-rc .
trivy image ainews-rc
```

### 4. Docker/deployment validation

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet
docker build -t ainews-rc .
bash scripts/ci_compose_smoke.sh
```

Confirm:

- db-migrate exits 0,
- web starts,
- `/health` responds with expected status,
- logs do not show production config validation errors,
- no real provider API keys are required.

### 5. Migration validation

Fresh DB:

```bash
uv run pytest tests/test_smoke_migrations.py -q
```

If existing deployments matter, add upgrade-from-prior-head validation:

- create DB at previous release migration head,
- run current `flask db upgrade`,
- inspect tables/columns.

### 6. Safe-fetch validation

```bash
uv run pytest tests/test_safe_fetch.py tests/test_url_security.py tests/test_content_extractor_safe_fetch.py -q
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

Every direct network call must be reviewed.

### 7. Documentation validation

- README quickstart works for Docker path.
- `.env.example` aligns with production validation.
- provider config examples match Docker/Ollama behavior.
- security docs reflect bearer/CSRF and safe-fetch behavior.
- troubleshooting docs cover common startup, migration, Celery, and safe-fetch errors.

Commands if docs tests exist:

```bash
uv run pytest tests/test_docs_alignment.py tests/test_docs_env_consistency.py -q
```

### 8. Release artifact/version validation

- Confirm `pyproject.toml` version.
- Confirm package metadata classifiers and maturity status.
- Confirm changelog/release notes exist if project uses them.
- Confirm Docker tag naming if images are published.

### 9. Rollback/restore readiness

For public self-hosted release, docs should describe:

- database backup before upgrade,
- how to rollback code,
- how to restore DB from backup,
- how to inspect logs,
- how to run migrations manually.

### 10. Final human signoff

Require a final note with:

- commit SHA,
- CI run link/status,
- local validation command used,
- known waivers/deferred items,
- release decision.

## Acceptance criteria

- Checklist exists in docs.
- Commands are copy-pasteable.
- Known optional/advisory gates are labeled as such.
- Checklist does not require live paid provider keys.
- Agents are instructed to reference checklist status before claiming release readiness.

## Handoff cautions

- Do not bury release blockers in prose; use explicit pass/fail checklist items.
- Do not claim public release readiness without green required gates or documented waivers.
- Do not include real secrets in release notes or CI logs.

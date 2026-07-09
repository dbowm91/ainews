# Release Checklist

This document defines the checklist for evaluating release candidacy. Agents MUST reference this checklist before claiming release readiness.

## 1. Source Tree State

Confirm working tree clean, branch correct, version intentional.

```bash
git status --short
git branch --show-current
git log --oneline -5
```

- [ ] Working tree is clean (no uncommitted changes)
- [ ] Branch is `main` or release branch
- [ ] Version in `pyproject.toml` matches intended release
- [ ] `README.md` release maturity language matches package metadata
- [ ] `CHANGELOG.md` includes entry for this version

## 2. Python/Test Validation

```bash
uv run ruff check .
uv run pytest tests/ -q
uv run pytest tests/test_smoke_production_config.py tests/test_smoke_migrations.py tests/test_smoke_celery.py tests/test_docs_env_consistency.py -q
```

- [ ] Ruff lint passes with zero errors
- [ ] Full test suite passes (pre-existing failures documented and waived)
- [ ] Smoke tests pass (production config, migrations, Celery, docs/env consistency)

### Optional: Type Checking

```bash
uv run mypy . --exclude .venv
```

Mypy is advisory until Milestone D.4 type-coverage goals are set. **[Optional gate]**

## 3. Security Validation

```bash
uv run pip-audit
gitleaks detect --source .
```

```bash
trivy fs .
```

If image scanning is adopted:

```bash
docker build -t ainews-rc .
trivy image ainews-rc
```

- [ ] No known critical/high dependency vulnerabilities (`pip-audit`)
- [ ] No leaked secrets (`gitleaks`)
- [ ] Filesystem scan clean (`trivy`)
- [ ] Container image scan clean, no HIGH/CRITICAL findings **[if image scanning adopted]**
- [ ] License review — no prohibited licenses (AGPL prohibited, LGPL/GPL require documented approval). See [Security Triage Policy](security_triage.md#license-review).

## 4. Docker/Deployment Validation

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet
docker build -t ainews-rc .
bash scripts/ci_compose_smoke.sh
```

Confirm:

- [ ] `db-migrate` exits 0
- [ ] `web` starts successfully
- [ ] `/health` responds with `"status": "ok"` or `"degraded"`
- [ ] No production config validation errors in logs
- [ ] No real provider API keys required for smoke test (throwaway `.env.ci` used)

## 5. Migration Validation

Fresh DB:

```bash
uv run pytest tests/test_smoke_migrations.py -q
```

If existing deployments matter, add upgrade-from-prior-head validation:

- [ ] Create DB at previous release migration head
- [ ] Run current `flask db upgrade`
- [ ] Inspect tables/columns match expected schema

## 6. Safe-Fetch Validation

```bash
uv run pytest tests/test_safe_fetch.py tests/test_url_security.py tests/test_content_extractor_safe_fetch.py -q
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

- [ ] Safe-fetch tests pass (SSRF, redirects, limits, content-type, timeouts)
- [ ] No direct network calls outside `safe_fetch_url()` — every direct network call must be reviewed
- [ ] Grep results for direct network calls reviewed and justified

## 7. Documentation Validation

- [ ] README quickstart works for Docker path
- [ ] `.env.example` aligns with `ProductionConfig.validate()` requirements
- [ ] Provider config examples match Docker/Ollama behavior
- [ ] Security docs reflect bearer/CSRF and safe-fetch behavior
- [ ] Troubleshooting docs cover common startup, migration, Celery, and safe-fetch errors

Commands if docs tests exist:

```bash
uv run pytest tests/test_docs_alignment.py tests/test_docs_env_consistency.py -q
```

## 8. Release Artifact/Version Validation

- [ ] `pyproject.toml` version matches intended release (currently `1.0.0`)
- [ ] Package metadata classifiers and maturity status are correct
- [ ] Changelog/release notes exist for this version
- [ ] Docker tag naming follows convention (if images are published)

## 9. Rollback/Restore Readiness

For self-hosted releases, docs should describe:

- [ ] Database backup before upgrade (see `scripts/backup.sh`)
- [ ] How to rollback code (git revert or checkout previous tag)
- [ ] How to restore DB from backup
- [ ] How to inspect logs (`docker compose logs`, application logs)
- [ ] How to run migrations manually (`flask db upgrade`)

## 10. Final Human Signoff

Require a final note with:

- [ ] Commit SHA
- [ ] CI run link/status
- [ ] Local validation command used (e.g., `bash scripts/validate_release.sh`)
- [ ] Known waivers/deferred items
- [ ] Release decision (proceed / block)

---

## One-Command Local Validation

`scripts/validate_release.sh` replicates most CI gates locally:

| Mode | Steps |
|------|-------|
| `--full` (default) | ruff lint → pytest → smoke tests → Docker build → Compose boot |
| `--fast` | ruff lint → production config smoke → docs/env consistency |
| `--security` | pip-audit → gitleaks → trivy → license report |
| `--with-mypy` | Include advisory mypy (non-blocking) |

```bash
bash scripts/validate_release.sh              # Full validation
bash scripts/validate_release.sh --fast       # Quick pre-push check
bash scripts/validate_release.sh --security   # Security gates only
bash scripts/validate_release.sh --with-mypy  # Include mypy
```

## Required CI Gates

The following jobs must pass on `main` before any release. These are configured as required status checks in GitHub branch protection.

| Job | What it covers |
|-----|---------------|
| `lint-and-test` | ruff lint, pytest suite, coverage report |
| `pip-audit` | Known dependency vulnerabilities |
| `trivy` | Filesystem vulnerability scan |
| `docker-build` | Image build, testing/prod app-factory smoke |
| `smoke-tests` | Production config, Celery import, Alembic migration, docs/env consistency |
| `compose-smoke` | Full Docker Compose boot + `/health` endpoint |
| `gitleaks` | Secret scanning |

### Advisory Checks

| Job | Status | Notes |
|-----|--------|-------|
| `mypy` | Allow-fail (`\|\| true`) | Advisory until Milestone D.4 type-coverage goals are set |

## Post-Deployment Verification

1. **Health check** — `curl https://your-domain/health` returns `"status": "ok"` or `"degraded"`
2. **Admin login** — verify admin panel accessible
3. **Pipeline status** — check `/admin/pipeline` for any stuck articles
4. **Newsletter delivery** — confirm next scheduled newsletter sends successfully

## Handoff Cautions

- Do not bury release blockers in prose; use explicit pass/fail checklist items
- Do not claim public release readiness without green required gates or documented waivers
- Do not include real secrets in release notes or CI logs
- Agents must not claim release readiness without `--full` mode passing on `scripts/validate_release.sh`

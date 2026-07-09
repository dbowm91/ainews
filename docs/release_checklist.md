# Release Checklist

This document defines the CI gates and manual verification steps required before releasing to production.

## Required CI Checks

The following jobs must pass on `main` before any release. These are configured as required status checks in GitHub branch protection.

| Job | What it covers | Failure action |
|-----|---------------|----------------|
| `lint-and-test` | ruff lint, pytest suite, coverage report | Fix lint/test failures |
| `pip-audit` | Known dependency vulnerabilities | Update vulnerable packages |
| `trivy` | Filesystem vulnerability scan | Review and patch CVEs |
| `docker-build` | Image build, testing/prod app-factory smoke | Fix build or import errors |
| `smoke-tests` | Production config, Celery import, Alembic migration, docs/env consistency | Fix validation or config issues |
| `compose-smoke` | Full Docker Compose boot + `/health` endpoint | Fix compose config or runtime issues |
| `gitleaks` | Secret scanning | Remove leaked secrets |

### Advisory Checks

| Job | Status | Notes |
|-----|--------|-------|
| `mypy` | Allow-fail (`\|\| true`) | Advisory until Milestone D.4 type-coverage goals are set |

## Branch Protection Configuration

In GitHub repository settings → Branches → Add rule for `main`:

1. **Require a pull request before merging** — prevents direct pushes
2. **Require status checks to pass** — add all 7 required jobs listed above
3. **Require branches to be up to date** — ensures CI runs against latest `main`
4. **Require conversation resolution** — prevents merging unresolved threads
5. **Require linear history** — enforces squash or rebase merges

### Required Status Check Names

These are the exact job names to add in the branch protection rule:

```
lint-and-test
pip-audit
trivy
docker-build
smoke-tests
compose-smoke
gitleaks
```

## Pre-Release Manual Verification

After CI passes and before deploying:

1. **Run local release validation** — `bash scripts/validate_release.sh` (replicates CI gates locally)
2. **Review deployment docs** — confirm `docs/deployment.md` matches current config
3. **Check Docker Compose config** — `docker compose config --quiet`
4. **Verify provider config** — `providers.yaml` has correct enabled providers
5. **Review changelog** — all notable changes documented
6. **Dependency license review** — `uv run pip-licenses --format=markdown` and verify no prohibited licenses (AGPL). See [Security Triage Policy](security_triage.md#license-review).
7. **Security scan review** — `bash scripts/validate_release.sh --security` passes. Review any suppressions in `SECURITY_SUPPRESSIONS.md` for expiration.
8. **Container image scan** (for releases) — `docker build -t ainews-ci . && trivy image ainews-ci` — no HIGH/CRITICAL findings

## Post-Deployment Verification

1. **Health check** — `curl https://your-domain/health` returns `"status": "ok"` or `"degraded"`
2. **Admin login** — verify admin panel accessible
3. **Pipeline status** — check `/admin/pipeline` for any stuck articles
4. **Newsletter delivery** — confirm next scheduled newsletter sends successfully

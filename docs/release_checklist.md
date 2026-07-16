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
uv run mypy . --exclude .venv
uv run pytest tests/test_smoke_production_config.py tests/test_smoke_migrations.py tests/test_smoke_celery.py tests/test_docs_env_consistency.py -q
```

- [ ] Ruff lint passes with zero errors
- [ ] Full test suite passes (pre-existing failures documented and waived)
- [ ] Mypy type-checking passes (legacy modules have `ignore_errors = true` overrides)
- [ ] Smoke tests pass (production config, migrations, Celery, docs/env consistency)

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

## 6. Backup/Restore Validation

```bash
ainews backup create
ainews backup list
ainews backup verify BACKUP_ID
ainews backup prune --dry-run
ainews restore BACKUP_ID --dry-run
ainews migrations status
```

- [ ] Backup creation succeeds with valid manifest
- [ ] Backup verification passes all checks
- [ ] Restore dry-run shows correct plan
- [ ] Migration status reports correctly
- [ ] Prune dry-run shows correct candidates

## 7. Safe-Fetch Validation

```bash
uv run pytest tests/test_safe_fetch.py tests/test_url_security.py tests/test_content_extractor_safe_fetch.py -q
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

- [ ] Safe-fetch tests pass (SSRF, redirects, limits, content-type, timeouts)
- [ ] No direct network calls outside `safe_fetch_url()` — every direct network call must be reviewed
- [ ] Grep results for direct network calls reviewed and justified

> **Note**: The direct-network-call grep must be run locally with `rg` — GitHub code search does not support the exact regex semantics needed. See `AGENTS.md` for the exact pattern.

## 8. Documentation Validation

- [ ] README quickstart works for Docker path
- [ ] `.env.example` aligns with `ProductionConfig.validate()` requirements
- [ ] Provider config examples match Docker/Ollama behavior
- [ ] Security docs reflect bearer/CSRF and safe-fetch behavior
- [ ] Troubleshooting docs cover common startup, migration, Celery, and safe-fetch errors

Commands if docs tests exist:

```bash
uv run pytest tests/test_docs_alignment.py tests/test_docs_env_consistency.py -q
```

## 9. Release Artifact/Version Validation

- [ ] `pyproject.toml` version matches intended release (currently `1.0.0`)
- [ ] Package metadata classifiers and maturity status are correct
- [ ] Changelog/release notes exist for this version
- [ ] Docker tag naming follows convention (if images are published)
- [ ] Release workflow (`.github/workflows/release.yml`) produces platform tarballs for `v*` tags
- [ ] Tarballs contain expected files (source, venv, compose manifests, migrations, themes, wrapper script)
- [ ] SHA256SUMS checksums are generated and attached to the release
- [ ] Artifact safety validation passes (no absolute paths, no traversal entries)
- [ ] Installer tests pass: `bash tests/test_install.sh`
- [ ] Update/uninstall tests pass: `pytest tests/test_update_uninstall.py`

## 10. Rollback/Restore Readiness

For self-hosted releases, docs should describe:

- [ ] Pre-update backup created automatically by `ainews update apply`
- [ ] How to rollback a failed update: `ainews update rollback`
- [ ] How to create and verify backups: `ainews backup create` / `ainews backup verify`
- [ ] How to restore from backup: `ainews restore BACKUP_ID`
- [ ] How to inspect logs (`ainews logs`, `docker compose logs`)
- [ ] How to check migration status: `ainews migrations status`
- [ ] Update dry-run works: `ainews update plan`
- [ ] Uninstall dry-run works: `ainews uninstall --dry-run`

## 11. Final Human Signoff

Require a final note with:

- [ ] Commit SHA
- [ ] CI run link/status
- [ ] Local validation command used (e.g., `bash scripts/validate_release.sh`)
- [ ] Known waivers/deferred items
- [ ] Release decision (proceed / block)

### Validation Evidence Template

Copy and fill this template for each release. Do not commit actual transient validation logs unless useful and sanitized.

```
## Release Validation Record

- **Commit SHA**:
- **Date/Time**:
- **CI Run URL**:
- **CI Status**: (pass/fail)
- **Local Command**: `bash scripts/validate_release.sh --full`
- **Local Result**: (pass/fail — include failed steps if any)
- **Safe-Fetch Tests**: (pass/fail)
- **Direct Network Call Audit**: (clean / justified exceptions listed)
- **Known Waivers**:
- **Release Decision**: (proceed / block)
```

> **Important**: Code inspection alone is insufficient for release readiness claims. Actual validation evidence from CI or local runs is required.

---

## One-Command Local Validation

`scripts/validate_release.sh` replicates most CI gates locally:

| Mode | Steps |
|------|-------|
| `--full` (default) | ruff lint → mypy → pytest → smoke tests → Docker build → Compose boot |
| `--fast` | ruff lint → production config smoke → docs/env consistency |
| `--security` | pip-audit → gitleaks → trivy → license report |

```bash
bash scripts/validate_release.sh              # Full validation (includes mypy)
bash scripts/validate_release.sh --fast       # Quick pre-push check (no mypy)
bash scripts/validate_release.sh --security   # Security gates only
```

## Required CI Gates

The following jobs must pass on `main` before any release. These are configured as required status checks in GitHub branch protection.

| Job | What it covers |
|-----|---------------|
| `lint-and-test` | ruff lint + mypy type-check + pytest with coverage |
| `pip-audit` | Known dependency vulnerabilities |
| `trivy` | Filesystem vulnerability scan |
| `docker-build` | Image build, testing/prod app-factory smoke |
| `smoke-tests` | Production config, Celery import, Alembic migration, docs/env consistency |
| `compose-smoke` | Full Docker Compose boot + `/health` endpoint |
| `gitleaks` | Secret scanning |

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

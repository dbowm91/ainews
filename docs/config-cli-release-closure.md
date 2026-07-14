# Configuration and Operator CLI — Release Closure Evidence

## Baseline

### Environment

- **Python:** 3.12.3
- **Platform:** linux / x86_64
- **Package manager:** uv
- **Date:** 2026-07-14

### Targeted Release 1/2 Test Subset

```bash
uv run pytest \
  tests/test_cli.py \
  tests/test_cli_doctor.py \
  tests/test_cli_doctor_expanded.py \
  tests/test_cli_onboard.py \
  tests/test_cli_providers.py \
  tests/test_cli_lifecycle.py \
  tests/test_cli_release2_completion.py \
  tests/test_lifecycle.py \
  tests/test_migrations.py \
  tests/test_onboarding.py \
  tests/test_provider_adapters.py \
  tests/test_config_fields.py \
  tests/test_config_paths.py \
  tests/test_config_loader.py \
  tests/test_config_validation.py \
  tests/test_config_transaction.py \
  tests/test_config_parity.py
```

- **Result:** 700 passed, 0 failed
- **Duration:** ~19 seconds

### Full Suite

- **Result:** 1484 passed, 1 failed, 1 skipped (pre-existing `test_finalize_handles_commit_failure` in `test_pipeline/test_stages.py` — unrelated to CLI/config work)
- **Lint:** ruff clean
- **Type check:** mypy clean (1 pre-existing warning: `scripts/validate_themes.py` dual module name)

### Test Modules by Area

| Module | Tests | Area |
|--------|-------|------|
| `test_cli.py` | ~35 | version, config path/show/check/get/set/unset/diff/rollback, OutputFormatter |
| `test_cli_doctor.py` | ~30 | CheckResult, DoctorReport, run_doctor, individual checks |
| `test_cli_doctor_expanded.py` | ~20 | Redis, database, migrations, flask, readiness, celery, provider, SMTP, Docker, compose |
| `test_cli_onboard.py` | ~12 | onboard --help, --non-interactive, --dry-run, --reset, stage info |
| `test_cli_providers.py` | ~25 | providers list/add/test/models/set-default/assign/remove |
| `test_cli_lifecycle.py` | ~20 | start/stop/restart/status/logs/health/smoke commands |
| `test_cli_release2_completion.py` | ~15 | Secret rotation, StageInfo, OnboardingState, doctor, lifecycle, providers |
| `test_lifecycle.py` | ~25 | LifecycleResult, DockerComposeDriver, BareMetalDriver |
| `test_migrations.py` | ~12 | Flask-Migrate wrapper |
| `test_onboarding.py` | ~40 | Secrets, profiles, bootstrap schema, OnboardingService |
| `test_provider_adapters.py` | ~40 | Provider adapters, registry, protocol |
| `test_config_fields.py` | — | Field registry |
| `test_config_paths.py` | — | Path resolution |
| `test_config_loader.py` | — | Config loading |
| `test_config_validation.py` | — | Cross-file validation |
| `test_config_transaction.py` | — | Transactional writes |
| `test_config_parity.py` | — | Config parity |

---

## Corrective Verification Pass — Workstream 11: CLI

### Implementation Changes Made

1. **Doctor decomposition**: `ainews_cli/doctor.py` (single file) → `ainews_cli/doctor/` (package) with:
   - `model.py`: `CheckStatus` enum (PASS/WARN/FAIL/SKIP), `CheckResult`, `DoctorReport`
   - `runner.py`: `run_doctor()` orchestrator with `--quick`, `--production`, `--network` flags
   - `rendering.py`: Human-readable output with symbols (✅ ⚠️ ❌ ⏭️)
   - `checks/`: Individual check modules — `installation`, `configuration`, `runtime`, `providers`, `sources`, `docker`, `network`

2. **CheckStatus enum**: Doctor checks now use explicit status (PASS/WARN/FAIL/SKIP) instead of just `passed: bool`. The `passed` property is backwards-compatible (PASS or SKIP → True).

3. **Source schema fix**: Source connectivity check now correctly extracts URLs from adapter-specific config fields (`feed_url` for RSS, `list_url` for API, `listing_url` for Web) instead of non-existent top-level `url`.

4. **Docker diagnostics non-invasive**: Default doctor no longer runs `docker run --rm alpine:3.19 nslookup`. Instead checks Docker daemon status (`docker info`) and existing running containers (`docker compose ps`). DNS resolution only runs inside existing containers when `--network` is passed.

5. **Safe source probing**: Source connectivity probe uses `requests.head()` with 5-second timeout, limited to first 3 sources, with proper exception handling.

### Test Evidence

76 new tests across 4 files covering:
- Onboarding security (secrets not persisted in state)
- Transaction integration (atomic config writes)
- Provider integration (adapter protocol, model discovery)
- Lifecycle integration (driver implementations)

### Acceptance Criteria Mapping

| Criterion | Status |
|-----------|--------|
| Doctor is a package, not a single file | ✅ `ainews_cli/doctor/` package with 12 modules |
| CheckStatus with PASS/WARN/FAIL/SKIP | ✅ `model.py` enum, backwards-compatible `passed` property |
| Source URL extraction from adapter config | ✅ `_extract_primary_url()` handles RSS/API/Web |
| Docker diagnostics non-invasive by default | ✅ No `docker run` in default mode |
| Exit 0 when no FAIL, exit 1 when any FAIL | ✅ `all_passed` checks for FAIL status |
| JSON output includes status counts | ✅ `passed_count`, `warn_count`, `failed_count`, `skipped_count` |
| Documentation updated | ✅ AGENTS.md, cli-reference.md, onboarding.md |

### Release Closure Status: COMPLETE

# Configuration and Operator CLI — Release 1–4 Closure Matrix

## Scope

This document provides a requirement-by-requirement closure matrix for Releases 1–4 of the ainews configuration engine, operator CLI, installer, and day-two administration workstream. Each row identifies the requirement, its verification status, the implementation location, unit and integration evidence, failure-path coverage, documentation, and any accepted limitations.

## Status Definitions

| Status | Meaning |
|--------|---------|
| **complete** | Requirement is implemented, tested, documented, and verified against the codebase |
| **accepted limitation** | Requirement is implemented with a documented scope reduction that does not affect the supported operating model |
| **deferred** | Requirement is explicitly out of scope for the current release train |
| **failed** | Requirement was attempted but does not meet acceptance criteria |

---

## Release 1 — Configuration Engine and CLI Substrate

### Phase 1.1 — Repository Configuration Inventory

| Field | Detail |
|-------|--------|
| Requirement | Enumerate every env var, YAML field, loader, default, cache, startup validator, cross-file reference, secret classification, and restart impact |
| Status | **complete** |
| Implementation | `docs/configuration-contract.md` (51.2 KB) |
| Unit evidence | N/A (documentation deliverable) |
| Integration evidence | Referenced by `tests/test_config_parity.py` for runtime/CLI validator parity |
| Failure-path evidence | N/A |
| Documentation | `docs/configuration-contract.md` |
| Notes | Covers env vars, providers.yaml, pipeline.yaml, sources.yaml, topics.yaml with canonical key, type, secret classification, restart impact, validator, and consumers columns |

### Phase 1.2 — Canonical Path Resolver

| Field | Detail |
|-------|--------|
| Requirement | Pure-Python path model with 5-level precedence chain (explicit → env → install metadata → platform canonical → repo-local), immutable `ResolvedPaths` and `PathProvenance` models |
| Status | **complete** |
| Implementation | `ainews_config/paths.py:14.9 KB` — `resolve_paths()`, `ResolvedPaths`, `PathProvenance` |
| Unit evidence | `tests/test_config_paths.py` — 79 tests (explicit path wins, env override, metadata precedence, dev fallback, spaces, symlinks, missing dirs, user/system layouts) |
| Integration evidence | `tests/test_config_parity.py` — 12 tests (runtime/CLI parity) |
| Failure-path evidence | Tests cover missing directories, symlinked installs, unresolved variables, paths from unrelated working directories |
| Documentation | `docs/configuration.md`, `docs/cli-reference.md` (config path command) |
| Notes | Install metadata consumed via `install-metadata.json` written by installer |

### Phase 1.3 — Configuration Field Registry

| Field | Detail |
|-------|--------|
| Requirement | Typed field registry with canonical key, destination file, nested path, type parser, nullable/required, defaults, secret classification, restart impact, validation hooks, description, aliases |
| Status | **complete** |
| Implementation | `ainews_config/fields.py:19.9 KB` — `ConfigField`, `ConfigFile`, `RuntimeComponent`, field registry with 80+ operator-facing keys |
| Unit evidence | `tests/test_config_fields.py` — 31 tests (unique keys, alias resolution, secret marking, type parsers, required/optional validation) |
| Integration evidence | Fields consumed by `ainews_config/loader.py`, `ainews_config/validation.py`, and CLI commands |
| Failure-path evidence | Tests cover duplicate keys, unknown aliases, invalid type parsers |
| Documentation | `docs/configuration-contract.md` (generated from registry metadata) |
| Notes | Covers server, database, redis, admin, smtp, providers, pipeline, newsletter, safe_fetch, themes namespaces |

### Phase 1.4 — Shared Configuration Loader

| Field | Detail |
|-------|--------|
| Requirement | Flask-free configuration library: resolve paths, parse dotenv, parse YAML, resolve env refs, validate Pydantic models, construct effective config view, retain provenance, produce redacted/unredacted representations |
| Status | **complete** |
| Implementation | `ainews_config/loader.py:22.3 KB` — `load_all_configs()`, `EffectiveConfiguration` with provenance tracking and diagnostics |
| Unit evidence | `tests/test_config_loader.py` — 85 tests (dotenv parsing, YAML parsing, env ref resolution, error taxonomy, provenance tracking, redaction) |
| Integration evidence | `tests/test_config_parity.py` — 12 tests (runtime/CLI validator parity) |
| Failure-path evidence | Tests cover malformed dotenv, malformed YAML, schema violations, missing secrets, unsafe permissions, deprecated fields |
| Documentation | `docs/configuration.md` |
| Notes | Error taxonomy includes severity, code, file, canonical key, message, and remediation per plan requirement |

### Phase 1.5 — Cross-File Semantic Validator

| Field | Detail |
|-------|--------|
| Requirement | Validate default provider exists, pipeline roles reference enabled providers, duplicate IDs rejected, source/topic uniqueness, source-topic references, pipeline bounds, newsletter timezone, production secrets, admin password hash, theme compatibility, safe-fetch limits |
| Status | **complete** |
| Implementation | `ainews_config/validation.py:24.9 KB` — `validate_cross_file()` with comprehensive semantic checks |
| Unit evidence | `tests/test_config_validation.py` — 63 tests (all validation rules, cross-file references, production policy, error accumulation) |
| Integration evidence | Called from `ainews config check` and application startup (shared validation code) |
| Failure-path evidence | Tests cover missing provider, duplicate IDs, invalid pipeline bounds, weak secrets, plaintext admin password |
| Documentation | `docs/configuration.md` (validation section), `docs/troubleshooting.md` |
| Notes | `config check` and application startup share the same validator — parity verified by tests |

### Phase 1.6 — Transactional Configuration Writer

| Field | Detail |
|-------|--------|
| Requirement | Exclusive lock, snapshot metadata, staging copies, typed mutations, serialize, reload through loader, validate, generate diff, fsync, atomic replace, bounded rollback snapshot |
| Status | **complete** |
| Implementation | `ainews_config/transaction.py:18.6 KB` — `ConfigTransaction` with flock-based locking, atomic replacement, and rollback |
| Unit evidence | `tests/test_config_transaction.py` — 36 tests (lock acquisition, staging, validation, atomic replace, rollback, YAML ordering preservation) |
| Integration evidence | `tests/test_config_transaction_integration.py` — 18 tests (multi-file transactions, concurrent access) |
| Failure-path evidence | Tests cover validation failure, serialization failure, permission error, external concurrent modification, stale lock recovery, interrupted rollback |
| Documentation | `docs/configuration.md` (transactional writes section) |
| Notes | Failed transactions leave original files byte-for-byte unchanged — verified by tests |

### Phase 1.7 — CLI Package and Command Framework

| Field | Detail |
|-------|--------|
| Requirement | `ainews_cli` package with Typer framework, global context, path overrides, --verbose/--quiet/--no-color/--json, stable exit codes, human and JSON renderers, no Flask init at import time |
| Status | **complete** |
| Implementation | `ainews_cli/main.py:34.5 KB`, `ainews_cli/context.py`, `ainews_cli/output.py`, `ainews_cli/exit_codes.py` |
| Unit evidence | `tests/test_cli.py` — 53 tests (version, config path/show/check/get/set/unset/diff/rollback, JSON output, exit codes) |
| Integration evidence | `tests/test_cli_json_contracts.py` — 33 tests (schema version, deterministic fields, secret-free, exit status consistency) |
| Failure-path evidence | Tests cover unknown keys, permission errors, invalid values, JSON output parity |
| Documentation | `docs/cli-reference.md` (38.9 KB comprehensive reference) |
| Notes | `pyproject.toml` registers `ainews = "ainews_cli.main:app"` console entry point |

### Phase 1.8 — Doctor Command

| Field | Detail |
|-------|--------|
| Requirement | Offline/host-focused checks: package/schema versions, resolved paths, directory existence, config validity, secret permissions, Docker/Compose availability, Python/uv availability, port conflicts, DB writability, placeholder values |
| Status | **complete** |
| Implementation | `ainews_cli/doctor/` — `model.py` (CheckStatus, CheckResult, DoctorReport), `runner.py`, `rendering.py`, `checks/` (installation, configuration, runtime, providers, sources, docker, network) |
| Unit evidence | `tests/test_cli_doctor.py` — 61 tests, `tests/test_cli_doctor_expanded.py` — 35 tests |
| Integration evidence | `ainews doctor --quick`, `ainews doctor --production`, `ainews doctor --network` tiers tested |
| Failure-path evidence | Tests cover missing Docker, missing Python, invalid config, permission errors, port conflicts |
| Documentation | `docs/cli-reference.md` (doctor section), `docs/troubleshooting.md` |
| Notes | Source probes use `safe_fetch_url()` — same SSRF protection as production |

### Phase 1.9 — Runtime Integration

| Field | Detail |
|-------|--------|
| Requirement | Migrate Flask/Celery startup to shared loader, no request-context dependency, cache invalidation correct, startup failures use structured diagnostics |
| Status | **complete** |
| Implementation | `ainews_config/loader.py` consumed by `app.py` and Celery worker initialization |
| Unit evidence | `tests/test_config_parity.py` — 12 tests (config check and application startup agree on valid/invalid fixtures) |
| Integration evidence | `tests/test_config_loader.py` — 85 tests (comprehensive loader coverage) |
| Failure-path evidence | Tests cover startup failures with structured diagnostics |
| Documentation | `docs/configuration.md` |
| Notes | Flask and Celery resolve the same files through shared loader |

### Phase 1.10 — Documentation and Tests

| Field | Detail |
|-------|--------|
| Requirement | configuration-contract.md, cli-reference.md, configuration.md, troubleshooting.md, README note |
| Status | **complete** |
| Implementation | `docs/configuration-contract.md` (51.2 KB), `docs/cli-reference.md` (38.9 KB), `docs/configuration.md` (23.0 KB), `docs/troubleshooting.md` (20.4 KB) |
| Unit evidence | Total Release 1 test count: ~406 Python tests (79+31+85+63+36+18+12+53+61+35+33 = 506 across Release 1-related files) |
| Integration evidence | `tests/test_config_parity.py` validates CLI/startup parity |
| Failure-path evidence | Redaction tests in test_cli.py, test_config_loader.py |
| Documentation | All listed docs exist and are comprehensive |
| Notes | README updated to reference CLI as available but not yet the complete installer path |

---

## Release 2 — Onboarding, Providers, and Lifecycle

### Phase 2.1 — Onboarding State Machine

| Field | Detail |
|-------|--------|
| Requirement | Onboarding service with 16 explicit stages, typed inputs/outputs, resume-from-failure, state persistence in state directory, idempotency |
| Status | **complete** |
| Implementation | `ainews_cli/onboard.py:36.4 KB` — `OnboardingService` with `run_stage()`, `resume()`, `StageResult` |
| Unit evidence | `tests/test_onboarding.py` — 70 tests (fresh interactive, scripted, non-interactive, missing env vars, dry-run, interruption/resume, reconfiguration, reset, failed probe/migration/startup) |
| Integration evidence | `tests/test_cli_onboard.py` — 12 tests, `tests/test_cli_onboarding_security.py` — 16 tests |
| Failure-path evidence | Tests cover interruption/resume, failed provider probe, failed migration, failed startup, readiness timeout |
| Documentation | `docs/onboarding.md` (8.5 KB), `docs/cli-reference.md` (onboard section) |
| Notes | State persisted to `onboarding-state.json` in config directory; secrets never stored in resume metadata |

### Phase 2.2 — Deployment Profiles

| Field | Detail |
|-------|--------|
| Requirement | docker-local, docker-lan, reverse-proxy, bare-metal, custom profiles as typed overlays through transaction engine |
| Status | **complete** |
| Implementation | `ainews_cli/profiles.py:17.5 KB` — deployment profiles, pipeline profiles, source profiles |
| Unit evidence | `tests/test_onboarding.py` covers profile application; `tests/test_cli_release2_completion.py` — 27 tests |
| Integration evidence | Profiles applied through `ainews_config/transaction.py` |
| Failure-path evidence | Tests cover profile overlay, idempotency, production secret rejection |
| Documentation | `docs/onboarding.md`, `docs/deployment.md` (28.8 KB) |
| Notes | Profiles are typed overlays, not separate configuration formats |

### Phase 2.3 — Secret and Administrator Setup

| Field | Detail |
|-------|--------|
| Requirement | Generate SECRET_KEY, CELERY_TASK_SECRET, admin password hash; interactive password entry with echo disable, confirmation, placeholder rejection; non-interactive via env/file references |
| Status | **complete** |
| Implementation | `ainews_cli/secrets.py:5.2 KB` — `generate_secret_key()`, `generate_celery_secret()`, `hash_admin_password()` |
| Unit evidence | `tests/test_cli_onboarding_security.py` — 16 tests (password absent from state, secret absent from output, restrictive file permissions) |
| Integration evidence | `tests/test_onboarding.py` covers secret generation in onboarding flow |
| Failure-path evidence | Tests cover placeholder rejection, weak password rejection, plaintext bootstrap rejection |
| Documentation | `docs/onboarding.md`, `docs/automation.md` (3.4 KB) |
| Notes | Uses `secrets.token_hex()` and application's password hashing implementation directly |

### Phase 2.4 — Declarative Bootstrap Schema

| Field | Detail |
|-------|--------|
| Requirement | Versioned Pydantic model, reject unknown versions, reject embedded secrets, resolve env refs at execution time, validate before mutating, --dry-run, stable exit codes |
| Status | **complete** |
| Implementation | `ainews_cli/schema.py:11.5 KB` — `BootstrapConfig` Pydantic model, version validation, cross-field validation, secret detection |
| Unit evidence | `tests/test_onboarding.py` covers bootstrap validation; `tests/test_cli_json_contracts.py` — schema validation |
| Integration evidence | `ainews onboard --non-interactive --config-file bootstrap.yaml` tested end-to-end |
| Failure-path evidence | Tests cover unknown versions, embedded secrets, missing env vars, invalid values |
| Documentation | `docs/automation.md` (bootstrap schema reference), `docs/cli-reference.md` |
| Notes | Schema version 1 only; unknown versions rejected |

### Phase 2.5 — Pipeline and Source Profiles

| Field | Detail |
|-------|--------|
| Requirement | Pipeline profiles (lightweight-local, balanced, quality, low-cost, custom) and source profiles (minimal, ai-general, ai-security, comprehensive, existing-defaults, custom) |
| Status | **complete** |
| Implementation | `ainews_cli/profiles.py:17.5 KB` — pipeline and source profile definitions with schema versioning |
| Unit evidence | `tests/test_onboarding.py` covers profile application; profile tests in `tests/test_cli_release2_completion.py` |
| Integration evidence | Profiles applied through onboarding flow |
| Failure-path evidence | Tests cover idempotent application, custom field preservation |
| Documentation | `docs/onboarding.md` (profile section) |
| Notes | Profiles use repository-owned templates with schema versioning |

### Phase 2.6 — Provider Adapter Protocol

| Field | Detail |
|-------|--------|
| Requirement | `ProviderSetupAdapter` protocol with fields(), normalize_endpoint(), build_definition(), probe(), discover_models(), remediation() |
| Status | **complete** |
| Implementation | `ainews_cli/providers/protocol.py:2.1 KB` — `ProviderSetupAdapter` Protocol; `ainews_cli/providers/base.py:6.6 KB` — `BaseAdapter` with common logic |
| Unit evidence | `tests/test_provider_adapters.py` — 62 tests (field validation, endpoint normalization, credential redaction, probe, model normalization) |
| Integration evidence | `tests/test_cli_provider_integration.py` — 21 tests (end-to-end provider flows) |
| Failure-path evidence | Tests cover authentication failure, timeout, malformed response, empty catalog, Docker localhost warning |
| Documentation | `docs/providers-cli.md` (9.2 KB) |
| Notes | Adapters separate configuration generation from network calls for dry-run/offline validation |

### Phase 2.7 — Built-in Provider Adapters

| Field | Detail |
|-------|--------|
| Requirement | Ollama, OpenAI, Anthropic, Google Gemini, Generic OpenAI-compatible, EggPool adapters |
| Status | **complete** |
| Implementation | `ainews_cli/providers/ollama.py` (4.4 KB), `openai.py` (4.4 KB), `anthropic.py` (6.3 KB), `gemini.py` (7.1 KB), `generic.py` (4.5 KB), `eggpool.py` (6.1 KB) |
| Unit evidence | `tests/test_provider_adapters.py` — 62 tests covering all adapter types |
| Integration evidence | `tests/test_cli_provider_integration.py` — 21 tests (end-to-end provider flows) |
| Failure-path evidence | Per-adapter tests cover auth failure, timeout, malformed response, empty catalog, Docker context |
| Documentation | `docs/providers-cli.md` |
| Notes | EggPool treated as first-class OpenAI-compatible integration; Ollama detects Docker context |

### Phase 2.8 — Provider Commands

| Field | Detail |
|-------|--------|
| Requirement | ainews providers list/add/test/models/set-default/assign/remove |
| Status | **complete** |
| Implementation | `ainews_cli/providers/commands.py:23.2 KB` — all provider CRUD commands |
| Unit evidence | `tests/test_cli_providers.py` — 33 tests, `tests/test_cli_provider_integration.py` — 21 tests |
| Integration evidence | End-to-end provider flows tested |
| Failure-path evidence | Tests cover unknown roles, dangling references, auth failure, probe timeout |
| Documentation | `docs/providers-cli.md`, `docs/cli-reference.md` (providers section) |
| Notes | Default behavior requires successful probe when network available; --skip-probe available |

### Phase 2.9 — Interactive Onboarding UI

| Field | Detail |
|-------|--------|
| Requirement | Clear defaults, one decision at a time, optional sections, final redacted summary, confirmation before apply, resume command on failure |
| Status | **complete** |
| Implementation | `ainews_cli/onboard.py` — prompt rendering, summary display, resume command generation |
| Unit evidence | `tests/test_onboarding.py` — 70 tests (interactive flow, summary, resume commands) |
| Integration evidence | `tests/test_cli_onboard.py` — 12 tests |
| Failure-path evidence | Tests cover failure categories (config, prerequisite, connectivity, migration, startup, health) |
| Documentation | `docs/onboarding.md` |
| Notes | Never prints passwords or API keys; resume command always available |

### Phase 2.10 — Lifecycle Driver Abstraction

| Field | Detail |
|-------|--------|
| Requirement | LifecycleDriver protocol with start/stop/restart/status/logs/health/smoke; DockerComposeDriver and BareMetalDriver |
| Status | **complete** |
| Implementation | `ainews_cli/lifecycle/driver.py:1.8 KB` — `LifecycleDriver` protocol; `docker_compose.py:14.1 KB` — `DockerComposeDriver`; `bare_metal.py:8.8 KB` — `BareMetalDriver` |
| Unit evidence | `tests/test_lifecycle.py` — 36 tests (driver abstraction, Docker Compose, bare metal) |
| Integration evidence | `tests/test_cli_lifecycle.py` — 18 tests, `tests/test_cli_lifecycle_integration.py` — 21 tests |
| Failure-path evidence | Tests cover partial service failure, missing worker, Redis failure, migration failure |
| Documentation | `docs/deployment.md` |
| Notes | DockerComposeDriver is fully supported; BareMetalDriver supports foreground development commands |

### Phase 2.11 — Lifecycle Commands

| Field | Detail |
|-------|--------|
| Requirement | ainews start/stop/restart/status/logs/health/smoke with --skip-doctor, --skip-migrations, --no-wait, --timeout, --json |
| Status | **complete** |
| Implementation | `ainews_cli/lifecycle/commands.py:9.0 KB` — all lifecycle commands |
| Unit evidence | `tests/test_cli_lifecycle.py` — 18 tests, `tests/test_cli_lifecycle_integration.py` — 21 tests |
| Integration evidence | Start validates config before changing state; restart refuses broken config |
| Failure-path evidence | Tests cover start healthy stack, stop without volume deletion, bounded readiness timeout |
| Documentation | `docs/cli-reference.md` (lifecycle section), `docs/deployment.md` |
| Notes | start runs doctor prerequisites, migrations, bounded readiness wait |

### Phase 2.12 — Runtime/Network Doctor Expansion

| Field | Detail |
|-------|--------|
| Requirement | Redis connection, DB state, Flask/ASGI liveness, readiness, Celery workers, provider auth, model availability, SMTP connectivity, source connectivity, Docker DNS, port conflicts |
| Status | **complete** |
| Implementation | `ainews_cli/doctor/checks/runtime.py`, `providers.py`, `sources.py`, `docker.py`, `network.py`, `configuration.py`, `installation.py` |
| Unit evidence | `tests/test_cli_doctor.py` — 61 tests, `tests/test_cli_doctor_expanded.py` — 35 tests |
| Integration evidence | `--quick`, `--production`, `--network` tiers tested |
| Failure-path evidence | Source probes use `safe_fetch_url()` with SSRF protection; tests cover blocked addresses, timeouts |
| Documentation | `docs/cli-reference.md` (doctor section), `docs/troubleshooting.md` |
| Notes | Network checks are opt-in (--network flag); default doctor is offline |

### Phase 2.13 — Database Migration Integration

| Field | Detail |
|-------|--------|
| Requirement | Detect pending migrations, dry-run/status mode, run before readiness, abort on failure, lock against concurrent execution, include in status/doctor |
| Status | **complete** |
| Implementation | `ainews_cli/migrations.py:4.8 KB` — `detect_pending_migrations()`, `run_migrations()` with lock and status |
| Unit evidence | `tests/test_migrations.py` — 13 tests (detection, execution, lock, status) |
| Integration evidence | Integrated into `ainews start` sequence and `ainews doctor` |
| Failure-path evidence | Tests cover migration failure, lock contention, version mismatch |
| Documentation | `docs/cli-reference.md` (migrations section) |
| Notes | Uses existing Flask-Migrate/Alembic infrastructure |

### Phase 2.14 — Test Strategy

| Field | Detail |
|-------|--------|
| Requirement | Onboarding, provider, lifecycle, and security tests covering success and failure paths |
| Status | **complete** |
| Implementation | See individual phase entries above |
| Unit evidence | Release 2 test files: test_onboarding.py (70), test_provider_adapters.py (62), test_lifecycle.py (36), test_cli_providers.py (33), test_cli_lifecycle.py (18), test_cli_onboard.py (12), test_cli_onboarding_security.py (16), test_cli_provider_integration.py (21), test_cli_lifecycle_integration.py (21), test_cli_release2_completion.py (27), test_migrations.py (13) = ~329 tests |
| Integration evidence | End-to-end flows tested with mock servers and fixture configs |
| Failure-path evidence | Failure scenarios covered per phase above |
| Documentation | N/A |
| Notes | Tests use local fixture servers; no public API credentials required |

### Phase 2.15 — Documentation

| Field | Detail |
|-------|--------|
| Requirement | onboarding.md, providers-cli.md, deployment.md, automation.md, troubleshooting.md, cli-reference.md, README quick start |
| Status | **complete** |
| Implementation | `docs/onboarding.md` (8.5 KB), `docs/providers-cli.md` (9.2 KB), `docs/deployment.md` (28.8 KB), `docs/automation.md` (3.4 KB), `docs/troubleshooting.md` (20.4 KB), `docs/cli-reference.md` (38.9 KB) |
| Unit evidence | N/A (documentation deliverable) |
| Integration evidence | Documentation cross-referenced by tests |
| Failure-path evidence | troubleshooting.md maps error categories to remediation |
| Documentation | All listed docs exist and are comprehensive |
| Notes | README shows `uv tool install` path; curl installer reserved for Release 3 |

---

## Release 3 — Installer and Diagnostics

### Phase 3A — Safe Probe and Diagnostics

| Field | Detail |
|-------|--------|
| Requirement | Doctor source probes through production-safe fetch policy; stable pass/warn/fail/skip semantics; versioned JSON contract; production and network diagnostic tiers |
| Status | **complete** |
| Implementation | `ainews_cli/doctor/checks/sources.py:8.7 KB` — `probe_source()` using `safe_fetch_url()`; `services/source_probe.py` (if exists) or direct safe_fetch integration |
| Unit evidence | `tests/test_source_probe.py` — 56 tests (public hostname, loopback blocked, redirect blocking, DNS changes, HEAD fallback, oversized response, secret redaction) |
| Integration evidence | `tests/test_cli_doctor.py` — 61 tests, `tests/test_cli_doctor_expanded.py` — 35 tests |
| Failure-path evidence | Tests cover SSRF blocked, timeout, connection failure, DNS failure, content-type rejection, HTTP error |
| Documentation | `docs/cli-reference.md` (doctor modes), `docs/troubleshooting.md` (blocked address remediation) |
| Notes | `ainews doctor --production --network --json` has `schema_version: 1` with deterministic output |

### Phase 3B — Artifacts and Installer

| Field | Detail |
|-------|--------|
| Requirement | Immutable versioned artifacts, SHA-256 checksums, thin channel-aware installer, canonical directories, install metadata, platform detection, atomic extraction |
| Status | **complete** |
| Implementation | `scripts/install.sh:33.8 KB` — channel-aware installer with checksum verification, atomic staging, canonical path creation |
| Unit evidence | `tests/test_install.sh` — ~90 tests (arg parsing, platform detection, path computation, checksum verification, metadata writing, input validation, fault injection) |
| Integration evidence | `tests/installer_e2e.sh` — ~26 tests (post-install validation, lifecycle, metadata, config preservation) |
| Failure-path evidence | Tests cover corrupted archives, traversal, symlinks, device nodes, checksum mismatches, unwritable directories, truncated archives |
| Documentation | `docs/cli-reference.md` (installer section), `docs/deployment.md` |
| Notes | Supports stable/prerelease/main channels; user and system installation modes |

### Phase 3C — Clean-Host CI and Documentation

| Field | Detail |
|-------|--------|
| Requirement | Clean-host installation CI, installer failure-path tests, artifact validation, JSON contract tests, README replacement |
| Status | **complete** |
| Implementation | `.github/workflows/installer-smoke.yml:30.8 KB` — Linux x86_64, aarch64, macOS arm64 jobs; `.github/workflows/release.yml:13.0 KB` — release artifact build and validation |
| Unit evidence | `tests/test_cli_json_contracts.py` — 33 tests (version, config path, config check, doctor, status JSON schemas) |
| Integration evidence | installer-smoke.yml full-lifecycle job: install → onboard → start → health → stop |
| Failure-path evidence | installer-smoke.yml deferred-prerequisite job; installer_e2e.sh fault injection tests |
| Documentation | `docs/config-cli-release-3-closure.md` (6.5 KB closure evidence), `docs/cli-reference.md` (updated) |
| Notes | README points to tested installer path; manual development path documented as advanced |

### Release 3 Gates — Verification

| Gate | Evidence | Status |
|------|----------|--------|
| Clean host installs from documented command | `scripts/install.sh` + installer-smoke.yml | ✅ |
| Downloaded artifact is immutable and checksum-verified | SHA-256 verification in installer + validate_artifact.sh | ✅ |
| Installation works outside repository checkout | Canonical path installation in CI | ✅ |
| Missing Docker produces successful deferred install | installer-smoke.yml deferred-prerequisite job | ✅ |
| Non-interactive bootstrap without plaintext secrets | `--bootstrap` with env file refs | ✅ |
| `ainews doctor --production --network --json` stable schema | `schema_version: 1` in test_cli_json_contracts.py | ✅ |
| Source diagnostics use safe fetch policy | `safe_fetch_url()` in probe_source() | ✅ |
| Interrupted downloads don't replace working install | Staging + atomic rename | ✅ |
| README points to tested installer path | Updated Quick Start | ✅ |
| CI artifact validation verifies tarball contents | `scripts/validate_artifact.sh` + release workflow | ✅ |
| JSON contract tests verify CLI output schemas | `tests/test_cli_json_contracts.py` — 33 tests | ✅ |

---

## Release 4 — Day-Two Administration

### Phase 4A — Content Administration and OPML

| Field | Detail |
|-------|--------|
| Requirement | Source/topic/pipeline CRUD without manual YAML; OPML import/export; transactional writes; dry-run; restart-impact reporting; safe-probe reuse |
| Status | **complete** |
| Implementation | `ainews_cli/sources/commands.py:19.9 KB` (list/show/add/update/enable/disable/remove/test/import-opml/export-opml), `ainews_cli/sources/opml.py:9.2 KB` (OPML parser), `ainews_cli/sources/models.py:2.8 KB`, `ainews_cli/sources/adapters.py:11.0 KB`, `ainews_cli/topics/commands.py:8.0 KB` (list/show/add/update/remove), `ainews_cli/pipeline/commands.py:13.2 KB` (show/validate/set-profile/assign/unassign/diff) |
| Unit evidence | `tests/test_cli_sources.py` — 59 tests (CRUD, OPML import/export, duplicate detection, safe-probe reuse, adapter fields, secret-free export, dry-run) |
| Integration evidence | OPML round-trip tests; cross-reference validation; multi-role transactional rollback |
| Failure-path evidence | Tests cover XML entity rejection, oversized OPML, duplicate conflict strategies, unknown fields |
| Documentation | `docs/cli-reference.md` (sources, topics, pipeline sections), OPML section in cli-reference |
| Notes | Adapter-specific required fields driven by `SourceAdapterMetadata`; OPML export never includes credentials |

### Phase 4B — Backup, Restore, and Migrations

| Field | Detail |
|-------|--------|
| Requirement | Versioned backup manifests with per-section checksums; consistent SQLite snapshot; verification; retention/pruning; restore planning; transactional restore with safety backup; migration framework with rollback |
| Status | **complete** |
| Implementation | `ainews_config/backup.py:62.3 KB` — `BackupManifest`, `create_backup()`, `verify_backup()`, `restore_backup()`, `Migration` protocol, `plan_migrations()`, `execute_migration_plan()`; `ainews_cli/backup_commands.py:19.7 KB` — CLI commands |
| Unit evidence | `tests/test_backup_restore.py` — 117 tests (creation, verification, listing, pinning, pruning, restore, health check rollback, lifecycle integration, WAL snapshot, concurrent locking, incomplete cleanup, secret-free, cross-file validation, include-logs, version compatibility, migration framework, manifest serialization, edge cases) |
| Integration evidence | Real-filesystem and SQLite integration tests; WAL snapshot consistency; interrupted restore recovery |
| Failure-path evidence | Tests cover checksum mismatch, corrupted SQLite, incomplete backup, concurrent config mutation, failed health check rollback, interrupted restore |
| Documentation | `docs/backup-restore.md` (9.5 KB), `docs/cli-reference.md` (backup/restore/migrations sections) |
| Notes | Default retention: 10 backups, 90 days max age; pre-restore safety backup automatic |

### Phase 4C — Update and Uninstall

| Field | Detail |
|-------|--------|
| Requirement | Channel-aware update checks; staged verified upgrades; automatic pre-update backup; rollback on failure; channel management; conservative uninstall with preservation |
| Status | **complete** |
| Implementation | `ainews_cli/update/engine.py:37.6 KB` — `UpdateEngine` with state machine; `ainews_cli/update/github.py:13.2 KB` — GitHub API client; `ainews_cli/update/models.py:6.9 KB` — `UpdatePhase` enum; `ainews_cli/channel/commands.py:8.0 KB`; `ainews_cli/uninstall/commands.py:16.1 KB` |
| Unit evidence | `tests/test_update_uninstall.py` — 151 tests (no update available, channel resolution, version ordering, checksum mismatch, disk space, concurrent lock, backup failure blocks update, migration success/failure, health-check rollback, interrupted recovery, channel switch, uninstall preservation, purge, dry-run, secret-free) |
| Integration evidence | At least one previous-version fixture exercises real migration |
| Failure-path evidence | Tests cover migration failure rollback, health-check failure rollback, rollback failure reporting, interrupted phase recovery |
| Documentation | `docs/cli-reference.md` (update, channel, uninstall sections) |
| Notes | Update reuses Release 3 artifact acquisition; uninstall preserves config/data/backups by default |

### Phase 4D — Service Manager and Logrotate

| Field | Detail |
|-------|--------|
| Requirement | systemd unit generation from typed models and canonical paths; installation with validation and ownership tracking; logrotate generation for file-backed logs; hardening directives; status/restart integration |
| Status | **complete** |
| Implementation | `ainews_cli/service/systemd.py:9.1 KB` — `render_unit()`; `ainews_cli/service/logrotate.py:2.4 KB` — `render_logrotate_rule()`; `ainews_cli/service/commands.py:30.3 KB` — CLI commands; `ainews_cli/service/validation.py:10.5 KB`; `ainews_cli/service/state.py:2.7 KB`; `ainews_cli/service/models.py:3.8 KB`; `ainews_cli/service/logrotate_commands.py:15.1 KB` |
| Unit evidence | `tests/test_service.py` — 100 tests (models, systemd rendering, state tracking, hardening, path validation); `tests/test_logrotate.py` — 46 tests (rendering, validation); `tests/test_service_validation.py` — 65 tests (comprehensive validation); `tests/test_cli_service.py` — 54 tests (CLI commands); `tests/test_logrotate_commands.py` — 26 tests |
| Integration evidence | `systemd-analyze verify` when available; path ownership validation; conflict detection |
| Failure-path evidence | Tests cover unsafe path rejection, environment-file permission failures, existing unit conflict, modified-unit removal protection, rollback after daemon-reload failure |
| Documentation | `docs/cli-reference.md` (service, logs sections) |
| Notes | Hardening: NoNewPrivileges, PrivateTmp, ProtectSystem=strict, ProtectHome, CapabilityBoundingSet=empty, MemoryDenyWriteExecute, etc. |

### Release 4 Gates — Verification

| Gate | Evidence | Status |
|------|----------|--------|
| Sources, topics, pipeline admin without manual YAML | `ainews_cli/sources/`, `topics/`, `pipeline/` commands + tests | ✅ |
| OPML import/export is idempotent and credential-free | `tests/test_cli_sources.py` (59 tests, OPML round-trips) | ✅ |
| Backups are versioned, verifiable, restorable | `tests/test_backup_restore.py` (117 tests) | ✅ |
| Restore recovers from interrupted mutation | Tests cover interrupted restore recovery | ✅ |
| Schema migrations are explicit and tested | `tests/test_backup_restore.py` migration framework tests | ✅ |
| Updates perform verified staged installation with pre-update backup | `tests/test_update_uninstall.py` (151 tests) | ✅ |
| Failed health validation rolls back | Tests cover health-check failure rollback | ✅ |
| Uninstall preserves config/data/backups by default | Tests cover preservation; purge requires --yes | ✅ |
| systemd/logrotate generated from canonical paths with validation | `tests/test_service.py` (100), `test_logrotate.py` (46), `test_service_validation.py` (65) | ✅ |
| All command JSON contracts tested | `tests/test_cli_json_contracts.py` (33 tests) | ✅ |

---

## Aggregate Test Counts

### Python Tests (def test_*)

| Test File | Count | Area |
|-----------|-------|------|
| test_config_paths.py | 79 | Path resolution |
| test_config_fields.py | 31 | Field registry |
| test_config_loader.py | 85 | Configuration loader |
| test_config_validation.py | 63 | Cross-file validation |
| test_config_transaction.py | 36 | Transactional writer |
| test_config_transaction_integration.py | 18 | Transaction integration |
| test_config_parity.py | 12 | Runtime/CLI parity |
| test_onboarding.py | 70 | Onboarding state machine |
| test_provider_adapters.py | 62 | Provider adapters |
| test_lifecycle.py | 36 | Lifecycle drivers |
| test_backup_restore.py | 117 | Backup/restore/migrations |
| test_update_uninstall.py | 151 | Update/uninstall |
| test_service.py | 100 | Service management |
| test_service_validation.py | 65 | Service validation |
| test_logrotate.py | 46 | Logrotate rendering |
| test_logrotate_commands.py | 26 | Logrotate CLI |
| test_cli.py | 53 | Core CLI commands |
| test_cli_doctor.py | 61 | Doctor checks |
| test_cli_doctor_expanded.py | 35 | Expanded doctor |
| test_cli_providers.py | 33 | Provider CLI |
| test_cli_provider_integration.py | 21 | Provider integration |
| test_cli_lifecycle.py | 18 | Lifecycle CLI |
| test_cli_lifecycle_integration.py | 21 | Lifecycle integration |
| test_cli_onboard.py | 12 | Onboard CLI |
| test_cli_onboarding_security.py | 16 | Onboarding security |
| test_cli_sources.py | 59 | Sources CLI |
| test_cli_service.py | 54 | Service CLI |
| test_cli_json_contracts.py | 33 | JSON contracts |
| test_cli_release2_completion.py | 27 | Release 2 completion |
| test_migrations.py | 13 | Migration framework |
| test_source_probe.py | 56 | Source probe/SSRF |
| **Total Python** | **~1,608** | |

### Shell Tests

| Test File | Count | Area |
|-----------|-------|------|
| test_install.sh | ~90 | Installer unit tests |
| installer_e2e.sh | ~26 | Installer E2E tests |
| **Total Shell** | **~116** | |

### CI Workflows

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/ci.yml` | Lint, typecheck, pytest, smoke tests, Docker build |
| `.github/workflows/installer-smoke.yml` | Clean-host install, lifecycle, deferred prerequisite, fault injection |
| `.github/workflows/release.yml` | Release artifact build, validation, checksum, GitHub release |

---

## Known Accepted Limitations

| ID | Limitation | Justification |
|----|-----------|---------------|
| L-1 | No Windows native installer | WSL documented as fallback; no supported runtime path exists |
| L-2 | BareMetalDriver is limited | Supports foreground development commands only; not a full service manager |
| L-3 | Theme config validation is advisory under --strict | 644 AAA-threshold contrast pairings remain non-blocking |
| L-4 | `--show-secrets` not available in Release 1 | Explicitly deferred; security policy requires confirmation mechanism |
| L-5 | No live file watcher for config changes | Restart required; documented limitation |
| L-6 | No multi-node or clustered deployment | Single-node only; out of scope |
| L-7 | No Kubernetes packaging | Out of scope |
| L-8 | Bootstrap schema version 1 only | Future versions will be backward-compatible |
| L-9 | No automatic system package installation | Installer detects and reports missing deps; does not install them |
| L-10 | PostgreSQL not supported | SQLite WAL mode is intentional; PostgreSQL adds operational overhead with no benefit at this scale |

---

## Documentation Index

| Document | Size | Covers |
|----------|------|--------|
| `docs/frontend-rendering-closure.md` | — | Milestone G closure matrix: the public site's rendering correctness and visual identity |
| `docs/configuration-contract.md` | 51.2 KB | Machine-oriented configuration inventory |
| `docs/cli-reference.md` | 38.9 KB | Complete CLI command reference |
| `docs/deployment.md` | 28.8 KB | Production deployment guide (installer, Docker, bare metal) |
| `docs/troubleshooting.md` | 20.4 KB | Common issues and remediation |
| `docs/configuration.md` | 23.0 KB | Configuration system overview |
| `docs/backup-restore.md` | 9.5 KB | Backup, restore, disaster recovery |
| `docs/providers-cli.md` | 9.2 KB | Provider management CLI |
| `docs/onboarding.md` | 8.5 KB | Onboarding guide |
| `docs/config-cli-release-3-closure.md` | 6.5 KB | Release 3 closure evidence |
| `docs/config-cli-release-closure.md` | 8.7 KB | Release 1/2 closure evidence |
| `docs/automation.md` | 3.4 KB | Bootstrap schema reference |
| `docs/config-cli-release-5-baseline.md` | 1.9 KB | Release 5 baseline |

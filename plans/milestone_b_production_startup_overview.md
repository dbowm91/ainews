# Milestone B Overview: Production Startup and Deployment Reliability

## Purpose

Milestone B turns the current release-readiness work from auth/token closure into reliable production startup and deployment behavior. Milestone A made the admin/API control plane much safer. Milestone B should make production boot fail closed when configuration is invalid, make the documented Docker path executable, and add enough smoke coverage that future changes cannot silently break deployment.

The primary release question for this milestone is simple: can a self-hosted operator follow the documented setup path and either get a working service or receive a precise, actionable startup error before unsafe or half-configured behavior occurs?

## Scope

Milestone B includes five detailed workstreams:

- `plans/milestone_b_01_fail_closed_production_config.md`
- `plans/milestone_b_02_provider_default_validation.md`
- `plans/milestone_b_03_docker_ollama_deployment_path.md`
- `plans/milestone_b_04_env_docs_alignment.md`
- `plans/milestone_b_05_ci_deployment_smoke.md`

## Current concerns to resolve

The earlier inspection identified these production-startup and deployment-readiness concerns:

1. Production provider validation can warn and continue after misconfigured enabled providers instead of failing closed.
2. `default_provider` needs validation against enabled providers and provider config validity.
3. The default `providers.yaml` points `ollama-local` at `http://localhost:11434`, which is usually wrong from inside the app container unless Ollama is running in the same network namespace.
4. `.env.example`, README, and deployment docs do not consistently describe all required production variables, especially `ADMIN_PASSWORD`, `SECRET_KEY`, `CELERY_TASK_SECRET`, Redis, database URL, and provider settings.
5. CI builds and tests code but does not yet prove the production app factory, migration path, Celery import, or Docker Compose health path.

## Desired final behavior

Production startup should be deterministic:

- Invalid production secrets fail startup.
- Missing `ADMIN_PASSWORD` fails startup.
- Missing or weak `CELERY_TASK_SECRET` fails startup.
- No enabled LLM provider fails startup.
- Misconfigured enabled LLM providers fail startup.
- A `default_provider` that is absent, disabled, or invalid fails startup.
- Docker/Ollama defaults are explicit and container-aware.
- Deployment docs and `.env.example` match runtime validation.
- CI has smoke coverage for app startup, migrations, Celery import, Docker build, and optionally Compose health.

## Recommended execution order

1. Tighten production config validation.
2. Refactor provider/default-provider validation so it returns structured errors.
3. Fix Docker/Ollama deployment semantics and docs.
4. Reconcile `.env.example`, README, deployment, configuration, and security docs.
5. Add smoke tests/scripts and wire them into CI.
6. Run a final fresh-install and upgrade-path validation.

## Affected files

Expected implementation files:

- `config.py`
- `schemas/llm.py`
- `schemas/common.py`
- `providers.yaml`
- `.env.example`
- `docker-compose.yml`
- `docker-compose.prod.yml` if present
- `Dockerfile` if runtime smoke needs adjustment
- `celery_app.py`
- `app.py`
- `.github/workflows/ci.yml`
- `scripts/` smoke helpers, if added
- `tests/`

Expected documentation files:

- `README.md`
- `docs/deployment.md`
- `docs/configuration.md`
- `docs/security.md`
- `docs/api.md` if provider/API auth behavior is documented there
- `AGENTS.md` and skill files if agent guidance needs deployment constraints

## Milestone exit criteria

Milestone B is complete when all of the following are true:

- Production config validation is fail-closed and test-covered.
- Enabled provider validation cannot silently swallow missing required env vars or invalid provider configs.
- `default_provider` is validated as present, enabled, and valid.
- Docker quickstart has a known-working LLM-provider path or a precise documented required action.
- `.env.example` names every production-required variable and does not hide required values under optional sections.
- README/deployment docs match runtime validation.
- CI includes app startup, migration, Celery import, and Docker/Compose smoke gates or an explicitly staged approximation.
- All targeted Milestone B tests pass.

## Non-goals

Milestone B does not implement SSRF-safe fetch hardening, release status/version cleanup, broader operational health dashboards, or public announcement polish. Those remain in later milestones unless a Milestone B change exposes a direct deployment blocker.

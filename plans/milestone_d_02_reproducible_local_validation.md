# Milestone D.2: Reproducible Local Validation

## Objective

Provide one documented local command path that closely mirrors CI and release-candidate validation. Contributors and coding agents should be able to run the same gate set before pushing or tagging.

## Problem

CI is valuable but insufficient if local validation is scattered across docs and plans. The repo should provide a repeatable local entrypoint that runs lint, tests, production smoke, Docker checks, and Compose smoke in a predictable order with actionable output.

## Recommended deliverable

Add one of:

- `scripts/validate_release.sh`, or
- `make validate-release`, with a script behind it.

Prefer a script because the repo is Python-centric and already uses shell scripts for deployment/Compose smoke.

## Proposed script behavior

`scripts/validate_release.sh` should run:

```bash
set -euo pipefail

uv run ruff check .
uv run pytest tests/ -q
uv run pytest tests/test_smoke_production_config.py tests/test_smoke_migrations.py tests/test_smoke_celery.py tests/test_docs_env_consistency.py -q
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config --quiet
docker build -t ainews-ci .
bash scripts/ci_compose_smoke.sh
```

Optionally include:

```bash
uv run mypy . --exclude .venv
uv run pip-audit
```

If mypy remains advisory, make that explicit:

```bash
scripts/validate_release.sh --with-mypy
```

## Modes

Support practical modes:

- `--fast`: ruff + targeted smoke tests, no Docker build.
- `--full`: full suite + Docker build + Compose smoke.
- `--security`: pip-audit + gitleaks/trivy equivalents if available locally.
- default: full release validation.

Keep mode count small. Avoid a complex CLI.

## Environment handling

The script should:

- not require real provider API keys,
- use CI fixtures for provider config where appropriate,
- generate throwaway secrets,
- clean up `.env.ci` or clearly preserve it with `chmod 600`,
- print which environment files it is reading,
- refuse to run destructive `docker compose down -v` unless using CI/test project names or explicit prompt/flag.

## Docker isolation

Use a project name to avoid colliding with a developer's running deployment:

```bash
COMPOSE_PROJECT_NAME=ainews-validation
```

Ensure cleanup targets only that project.

## Docs updates

Document in:

- `README.md` developer/release section,
- `docs/deployment.md` release validation section,
- `AGENTS.md` agent workflow section.

Agents should run or recommend the targeted validation command associated with their change. They should not claim release readiness without the full validation command passing.

## Acceptance criteria

- One command runs release-equivalent local validation.
- The command avoids live external LLM/API calls.
- Docker/Compose resources are isolated from normal dev deployments.
- Failures print actionable context.
- Docs and agent instructions point to the command.

## Validation commands

After implementation:

```bash
bash scripts/validate_release.sh --fast
bash scripts/validate_release.sh --full
```

If security mode is implemented:

```bash
bash scripts/validate_release.sh --security
```

## Handoff cautions

- Do not make the script silently skip Docker checks when Docker is unavailable unless the skip is explicit and visible.
- Do not reuse production `.env` secrets for validation.
- Do not delete developer volumes outside the validation Compose project.

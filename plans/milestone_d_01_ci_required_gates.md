# Milestone D.1: CI Required Gates

## Objective

Make CI release-grade by clearly defining required jobs, reducing ambiguity around allow-fail behavior, and ensuring every deployment-sensitive path is covered by an automated gate or explicitly documented manual release gate.

## Current CI baseline

The workflow currently includes jobs/steps for:

- ruff,
- pytest with coverage,
- mypy allow-fail,
- pip-audit,
- Trivy filesystem scan,
- Docker Compose config validation,
- Ollama Compose override config validation,
- Docker build,
- testing-mode image smoke,
- production-mode image smoke,
- production config smoke tests,
- Celery smoke tests,
- migration smoke tests,
- docs consistency smoke tests,
- full Compose boot smoke,
- gitleaks.

## Required work

### 1. Define required checks

Create a documented required-check matrix. Suggested required for protected `main`:

- `lint-and-test`
- `pip-audit`
- `trivy`
- `docker-build`
- `smoke-tests`
- `compose-smoke`
- `gitleaks`

If mypy remains allow-fail inside `lint-and-test`, document that type checking is advisory until Milestone D.4 closes.

### 2. Split long jobs only if useful

If CI runtime is acceptable, keep current structure. If failures are hard to triage, split into clearer jobs:

- `lint`
- `unit-tests`
- `coverage`
- `production-smoke`
- `docker-build`
- `compose-smoke`
- `security-scans`

Do not split merely for aesthetics; each job should improve failure visibility or required-check policy.

### 3. Ensure each gate is deterministic

Audit for:

- external internet dependency beyond dependency install and scanner DB updates,
- live LLM/API calls,
- public DNS assumptions,
- timing-sensitive local server tests,
- race-prone tests,
- leftover environment state between tests.

Safe-fetch tests in particular should not rely on external DNS or public websites.

### 4. Add concurrency control if needed

Consider adding workflow concurrency:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

This avoids stale PR runs consuming resources. For `main`, decide whether cancel-in-progress is acceptable.

### 5. Artifacts and diagnostics

On test failure, upload or print:

- pytest output,
- coverage summary,
- Docker Compose logs for compose smoke,
- db-migrate logs,
- web logs,
- pip-audit/Trivy reports if generated.

The existing compose script already dumps some logs; ensure CI preserves them in failure output.

### 6. Branch protection documentation

Add docs stating the intended required checks for GitHub branch protection. If branch protection cannot be configured in-repo, document manual settings.

Suggested doc location:

- `docs/release_checklist.md`, or
- `docs/development.md`, or
- `docs/deployment.md` release section.

## Acceptance criteria

- Required CI jobs are documented.
- CI job names are stable enough for branch protection.
- No release-critical smoke path is hidden in an allow-fail step.
- Compose boot smoke is either required in CI or explicitly manual; current desired state is required in CI.
- Failure logs are sufficient for handoff debugging.

## Validation commands

No code command fully substitutes for GitHub Actions, but local equivalent should exist by Milestone D.2. For this plan, inspect:

```bash
git grep -n "mypy .*|| true\|continue-on-error\|allow" .github/workflows docs AGENTS.md
```

and ensure any allow-fail behavior is intentional and documented.

## Handoff cautions

- Do not make CI depend on live OpenAI/Anthropic/Ollama model availability.
- Do not make Trivy/pip-audit failures silently ignored without a triage policy.
- Do not rename required jobs casually after branch protection is configured.

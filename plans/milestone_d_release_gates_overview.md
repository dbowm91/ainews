# Milestone D Overview: Release Gates, CI Hardening, and Reproducible Validation

## Purpose

Milestone D converts the current production-readiness work into repeatable release gates. Milestones A-C hardened auth, production startup/deployment behavior, and safe fetching. Milestone D should ensure those properties stay true through CI, local validation scripts, static analysis policy, dependency/security scans, and documented release-candidate procedures.

The repo already has meaningful CI jobs and smoke checks. This milestone tightens them into a public-release-quality gate set: deterministic, well-documented, actionable on failure, and aligned with the exact deployment paths documented for users.

## Scope

Detailed plans in this milestone:

- `plans/milestone_d_01_ci_required_gates.md`
- `plans/milestone_d_02_reproducible_local_validation.md`
- `plans/milestone_d_03_security_dependency_scanning.md`
- `plans/milestone_d_04_static_analysis_type_policy.md`
- `plans/milestone_d_05_release_candidate_checklist.md`

## Current baseline

Existing useful gates include:

- ruff check,
- full pytest with coverage,
- mypy currently allow-fail,
- pip-audit,
- Trivy filesystem scan,
- Docker Compose config validation,
- Ollama Compose override config validation,
- Docker image build,
- testing-mode image smoke,
- production-mode image smoke,
- production config smoke tests,
- Celery smoke tests,
- real Alembic migration smoke tests,
- docs/env consistency tests,
- full Docker Compose boot smoke,
- gitleaks.

Milestone D should not duplicate Milestone B. It should make these checks reliable, required, documented, and reproducible.

## Goals

- Establish which CI jobs are mandatory for merge/release.
- Make local validation match CI as closely as practical.
- Ensure security/dependency scans are actionable and not noisy placeholders.
- Decide how mypy/type checks graduate from allow-fail to scoped enforcement.
- Add release-candidate and rollback checklists tied to actual commands.
- Produce clear failure diagnostics for common CI/smoke failures.
- Avoid live external LLM/API dependencies in CI.

## Non-goals

Milestone D does not add new product features, rewrite architecture, add browser rendering, or complete public-release copy polish. Those belong to later release/documentation milestones.

## Exit criteria

Milestone D is complete when:

- Required CI checks are explicit and documented.
- Local validation script or Make target reproduces the CI gate set.
- Security/dependency scans have a triage policy.
- Type/static-analysis policy is explicit and incrementally enforceable.
- Release-candidate checklist is documented with commands, expected outputs, and failure handling.
- Agents are instructed not to claim release readiness unless these gates are green or explicitly waived.

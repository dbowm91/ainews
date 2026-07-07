# Release Readiness Roadmap

## Context

This roadmap converts the current repository inspection into an execution plan for getting `ainews` ready for deployment and public release. The inspection found that the repository has a coherent production-oriented skeleton: Docker Compose, Celery/Redis background processing, migrations, CI, security documentation, health checks, and a public-facing README. The blocking gaps are concentrated in authentication registration, API-token semantics, production validation, SSRF-safe fetching, CI smoke coverage, and documentation/runtime drift.

The release objective is a self-hosted, single-node news aggregation and AI-assisted newsletter platform that can be deployed by an external user with clear expectations, reproducible setup steps, and defensible security defaults.

## Release posture decision

Before tagging or announcing a public release, decide whether the project is truly `1.0.0` or still pre-stable. The repository currently advertises alpha/experimental status while `pyproject.toml` declares `version = "1.0.0"`. That mismatch should be resolved early because it affects user expectations, support posture, compatibility promises, and packaging semantics.

Recommended posture:

- Use a release-candidate track until the blockers below are closed.
- Keep the public README honest about single-node/self-hosted scope.
- Promote to `1.0.0` only after the minimum release gate passes.

Minimum public-release gate:

- Admin and API-token routes are demonstrably protected.
- API-token expiry/revocation semantics are correct.
- Production config fails closed on invalid provider/default-provider setup.
- Article fetching rejects private/reserved/redirected internal targets through the real fetch path.
- Docker Compose boots in CI and serves `/health` with a generated test `.env`.
- Documentation no longer contradicts runtime behavior.

## Milestone A — Auth, token, and CSRF blocker closure

Milestone A is the first execution target because it contains public-release blockers. The immediate risk is that some admin API routes may be registered with Flask before auth wrappers are applied. The API-token implementation also has misleading token semantics and does not enforce expiration. Finally, session-authenticated mutating JSON routes need a route-by-route CSRF audit.

Detailed handoff files:

- `plans/milestone_a_auth_token_csrf_overview.md`
- `plans/milestone_a_01_admin_route_auth_registration.md`
- `plans/milestone_a_02_api_token_redesign.md`
- `plans/milestone_a_03_csrf_mutating_route_audit.md`
- `plans/milestone_a_04_auth_token_csrf_tests.md`

Exit criteria:

- Unauthenticated access to admin and admin API routes fails consistently.
- Decorator order cannot accidentally expose admin endpoints.
- API tokens use a conventional `prefix.secret` or equivalent model.
- Expired, revoked, malformed, and wrong-secret tokens fail verification.
- Cookie/session-authenticated mutating JSON routes require CSRF.
- Bearer-token-authenticated API requests are explicitly exempt from CSRF and tested as such.
- Route coverage tests enumerate the registered Flask URL map.

## Milestone B — Production startup and deployment reliability

Make production startup fail closed and make the documented deployment path executable.

Scope:

- Tighten provider validation in `config.py`.
- Validate that `default_provider` points to an enabled provider.
- Ensure enabled providers resolve required env vars in production.
- Fix the Docker/Ollama default story. `localhost:11434` inside the app container does not refer to a host Ollama daemon.
- Reconcile `.env.example`, README, `docs/configuration.md`, and `docs/deployment.md` for required production variables.
- Add production-config smoke tests.

Acceptance criteria:

- Missing API keys for enabled cloud providers fail production startup.
- Invalid provider types/configs fail production startup.
- Missing or disabled default provider fails production startup.
- Docker deployment docs describe a working LLM provider configuration.
- A generated test `.env` can boot the stack or fails with an intentional, documented error.

## Milestone C — SSRF-safe fetch hardening

Replace the current validate-then-fetch pattern with a hardened fetch path. Current URL validation is useful but not sufficient because the actual fetch operation performs its own DNS resolution later.

Scope:

- Introduce a controlled HTTP fetch layer for article retrieval.
- Validate schemes and hostnames.
- Reject private, loopback, link-local, multicast, reserved, IPv4-mapped IPv6, and otherwise unsafe targets.
- Validate every redirect target.
- Enforce connect/read/total timeouts.
- Enforce response-size limits.
- Integrate with article extraction so `trafilatura` processes already-fetched bytes/content rather than performing independent network fetches.

Acceptance criteria:

- Tests reject direct private IP URLs.
- Tests reject hostnames resolving to private IPs.
- Tests reject redirect-to-private targets.
- Tests cover IPv6 loopback/link-local and IPv4-mapped IPv6.
- Fetch timeout and content-size behavior is bounded.

## Milestone D — CI and deployment smoke gates

CI should prove that the project builds, tests, migrates, imports Celery, and boots in a containerized deployment path.

Scope:

- Keep ruff, pytest, coverage, pip-audit, Trivy, Docker build, and Gitleaks.
- Decide whether mypy is a required gate or an explicitly non-blocking advisory job.
- Add `flask db upgrade` smoke testing against a temp DB.
- Add app factory production startup smoke with generated secrets.
- Add Celery import/config smoke.
- Add Docker Compose boot smoke that waits for `/health`.

Acceptance criteria:

- Required CI jobs cannot silently fail.
- Compose boot reaches a healthy web service.
- Migrations apply from a fresh database.
- Celery app imports without requiring an undeclared runtime service.

## Milestone E — Documentation correctness and public-release polish

Clean up all user-facing docs after the behavioral fixes land.

Scope:

- README quickstart.
- `.env.example` comments.
- `docs/quickstart.md`.
- `docs/configuration.md`.
- `docs/deployment.md`.
- `docs/security.md`.
- `SECURITY.md`.
- `CONTRIBUTING.md`.
- release notes/changelog.

Known documentation drift to correct:

- README says only `SECRET_KEY` and an LLM provider are required, while production validation also requires hashed `ADMIN_PASSWORD` and `CELERY_TASK_SECRET`.
- Deployment docs show an HTTP Basic health check pattern, but inspected auth appears session/API-token based.
- Security docs should not claim CSRF coverage beyond what code and tests enforce.
- Docker and bare-metal SQLite paths differ and need explicit explanation.
- Ollama defaults need container-aware documentation.

Acceptance criteria:

- A new user can follow quickstart without guessing required secrets.
- Production docs match actual auth behavior.
- Security docs match actual code and test coverage.
- Status/version language is internally consistent.

## Milestone F — Schema, migrations, and operational hardening

After the security blockers and deployment gates are closed, verify long-term operational correctness.

Scope:

- Review column sizes and constraints, especially auth/token fields.
- Ensure migrations exist for all schema changes.
- Test fresh install and upgrade path.
- Verify backup/restore instructions.
- Clarify SQLite WAL behavior and disk-space considerations.
- Improve health/readiness checks for DB, Redis, Celery, and provider availability.

Acceptance criteria:

- Fresh DB migration succeeds.
- Upgrade migration succeeds from the last known schema.
- Backup/restore commands are validated.
- Health checks are actionable for operators.

## Recommended execution order

1. Milestone A: Auth, token, and CSRF blocker closure.
2. Milestone B: Production config and deploy reliability.
3. Milestone C: SSRF-safe fetch hardening.
4. Milestone D: CI smoke gates.
5. Milestone E: Documentation and release polish.
6. Milestone F: Schema and operational hardening.

Milestones A through D are the minimum engineering gate for a release candidate. Milestone E is the minimum public-announcement gate. Milestone F can be split before or immediately after the public release depending on how much deployment surface is promised.

## General implementation constraints

- Prefer small, reviewable commits.
- Add regression tests before or alongside each fix.
- Keep self-hosted/single-node assumptions explicit.
- Do not weaken existing security checks to make tests pass.
- Do not hide release blockers behind documentation language.
- Keep public docs conservative where behavior depends on operator configuration.

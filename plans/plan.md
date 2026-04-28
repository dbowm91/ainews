# Implementation Plan - Consolidated

**Date:** April 28, 2026
**Status:** Draft - Consolidated from plans 2-9
**Last Updated:** April 28, 2026 (verified against codebase)

---

## Overview

Consolidated from: plan2.md, plan3.md, plan4.md, plan5.md, plan6.md, plan7.md, plan8.md, plan9.md

**Total Items:** 85+ across all plans (after removing confirmed-not-issues)
**Estimated Total Effort:** 40-60+ hours across all items

### Priority Summary

| Priority | Count | Source Plans |
|----------|-------|--------------|
| P0 / Critical | 6 | Plan 3 (2), Plan 5 (2), Plan 6 (2) |
| High / Tier 1 | 18 | Plans 2, 3, 4, 5, 6, 7, 8 |
| Medium / Tier 2 | 35 | Plans 2, 4, 5, 6, 7, 8, 9 |
| Low / Tier 3 | 15 | Plans 2, 4, 5, 6, 7, 8, 9 |

### Verified NOT Bugs (Removed from plan)

These items were described as bugs but verified working correctly:

| Item | Description | Verification |
|------|-------------|--------------|
| N1 | DUPLICATE_DETECTION_LIMIT (1000→200) | Already 200 in services/article.py:54 |
| N2 | Badge Color Contrast (WCAG AA) | All badges pass AA (4.5:1), some fail AAA only |
| N3 | CSS token drift (critical.css vs variables.css) | All shared tokens match exactly |
| N4 | DNS Cache TTL alignment | TTL is consistent (60s configurable) |
| N5 | Pipeline state machine violations | VALID_TRANSITIONS properly defined in constants.py:40-49 |
| N6 | Static volume mount | Intentional per AGENTS.md for Nginx serving |

---

## Wave 1: Critical Bugs (Must Fix First)

These items cause runtime crashes or security vulnerabilities. Fix before any other work.

### P0 - Fail-Open Bugs

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 1 | Fix `_acquire_stage_lock` fail-open bug (returns `True` on RedisError instead of raising) | **tasks/pipeline.py:108-117** | 5 min | Plan 3 |
| 2 | Fix `generate_daily_newsletters` fail-open (same inconsistency) | tasks/newsletter.py:414-417 | 5 min | Plan 3 |

### P0 - Security Critical

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 3 | Fix unsafe `.env` sourcing in `deploy.sh` (security risk) | scripts/deploy.sh:183 | 15 min | Plan 5 |
| 4 | Fix file permissions (777 on sensitive files) | scripts/*.sh, config files | 15 min | Plan 8 |
| 5 | Redis security - no password in Docker Compose | docker-compose.yml | 10 min | Plan 8 |

### P0 - Runtime Bugs

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 6 | Fix Version Creation Order in Edit Pipeline (version created AFTER modification, not before) | tasks/edit.py:333 | 30 min | Plan 6 |
| 7 | Fix providers.yaml Environment Variable Resolution (resolve_env_vars NOT called) | **schemas/llm.py:58-59** | 1 hr | Plan 6 |

---

## Wave 2: High Priority (Security, Observability)

### P1 - High Priority Security

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 8 | Fix Wrong Celery Healthcheck in docker-compose.yml (uses redis-cli ping instead of Celery ping) | docker-compose.yml:55-60, 77-82 | 15 min | Plan 5 |
| 9 | Replace placeholder GitHub URL (10 occurrences across 8 files) | 8 files | 30 min | Plan 5 |
| 10 | Add file permission validation at startup | services/*.py | 1 hr | Plan 8 |
| 11 | Update `install.sh` to set proper permissions | scripts/install.sh | 30 min | Plan 8 |
| 12 | Embed Lua script for atomic lock release | routes/admin/__init__.py | 1 hr | Plan 8 |

### P1 - Observability

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 13 | Fix Prometheus Histogram Metrics | services/metrics.py | 1 hr | Plan 6 |
| 14 | Configure OpenTelemetry Exporter | services/logging_utils.py | 1 hr | Plan 6 |
| 15 | Add Missing Database Indexes (migration 030) | migrations/*, models.py | 1 hr | Plan 7 |
| 16 | Fix N+1 Query: Article.metrics | routes/admin/dashboard.py | 30 min | Plan 7 |
| 17 | Remove unused query in Newsletter tasks | tasks/newsletter.py | 15 min | Plan 7 |

### P1 - Documentation Fixes

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 18 | Fix `docs/development.md` lines 182-207 (wrong LLM provider path: adapters/ → services/llm/) | docs/development.md | 15 min | Plan 2 |
| 19 | Fix `docs/development.md` lines 208-225 (wrong Celery decorator: @celery_app.task → @shared_task) | docs/development.md | 15 min | Plan 2 |
| 20 | Fix `docs/pipeline.md` lines 72-79 (wrong "After 3 failures route to review" - actual: marks failed) | docs/pipeline.md | 15 min | Plan 2 |
| 21 | Fix `docs/pipeline.md` Valid Transitions table (remove invalid transitions) | docs/pipeline.md | 15 min | Plan 2 |
| 22 | Fix `docs/api.md` authentication section (says HTTP Basic, actual: session-based) | docs/api.md | 15 min | Plan 2 |
| 23 | Fix `docs/api.md` Public Endpoint URLs (multiple URL errors) | docs/api.md | 15 min | Plan 2 |

---

## Wave 3: Frontend / Accessibility

### Phase 1 - Critical Accessibility

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 24 | Fix Skip-Link Focus Visibility (`.skip-link:focus { outline: none; }` removes focus ring) | static/css/critical.css:100-103 | 30 min | Plan 4 |
| 25 | Admin Logout Hidden on Mobile (`.nav-meta { display: none; }` in critical.css:369-371, layout.css:200-201) | static/css/*.css | 30 min | Plan 4 |
| 26 | Mobile Hamburger Menu Keyboard Accessibility (missing `role="button"`, `tabindex`, `aria-expanded`, Escape handler) | static/js/app.js, templates/base.html:38-41 | 1 hr | Plan 4 |

### Phase 2 - Major UX

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 27 | Search Input Focus Loss (HTMX swaps replace search form) | routes/public/*.py, templates | 1 hr | Plan 4 |
| 28 | Search UX Improvements (min length, tooltip, spinner visibility) | static/css/articles.css, templates | 1 hr | Plan 4 |
| 29 | Share Dropdown Keyboard Navigation (arrow keys + Tab trapping work, but **missing Escape handler**) | static/js/app.js:229-289 | 1 hr | Plan 4 |
| 30 | Article Card Focus Styles (add `:focus-within`) | static/css/articles.css | 30 min | Plan 4 |

### Phase 3 - Accessibility Continued

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 31 | Category Badge Color Contrast (Security/Other fail AAA but pass AA - lower priority) | static/css/variables.css | 1 hr | Plan 4 |
| 32 | Content-Visibility + Animation Interaction (mitigated via JS animation on swap) | static/css/articles.css:11-12 | 30 min | Plan 4 |

---

## Wave 4: Documentation Additions

### Tier 2 - High-Value Additions

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 33 | Add Cost Tracking section to `docs/configuration.md` | docs/configuration.md | 30 min | Plan 2 |
| 34 | Add Experiments (A/B testing) section to `docs/configuration.md` | docs/configuration.md | 30 min | Plan 2 |
| 35 | Rewrite README.md Features section with operational context | README.md | 1 hr | Plan 2 |
| 36 | Fix README.md Pipeline Flow diagram | README.md | 30 min | Plan 2 |
| 37 | Fix README.md Architecture Diagram (Granian is ASGI, not WSGI) | README.md | 30 min | Plan 2 |

### Tier 3 - Missing Documentation

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 38 | Create `docs/share-config.md` (new file) | docs/share-config.md | 1 hr | Plan 2 |
| 39 | Expand `docs/analytics.md` with ArticleMetric and SearchQuery sections | docs/analytics.md | 1 hr | Plan 2 |
| 40 | Expand `docs/security.md` with AuditLog and CSP sections | docs/security.md | 1 hr | Plan 2 |
| 41 | Add Workflow Guidance to `docs/api.md` | docs/api.md | 30 min | Plan 2 |
| 42 | Add Admin Article Search documentation to `docs/api.md` | docs/api.md | 30 min | Plan 2 |
| 43 | Create `docs/components/pagination.md` (new file) | docs/components/pagination.md | 30 min | Plan 2 |
| 44 | Create `docs/components/search-container.md` (new file) | docs/components/search-container.md | 30 min | Plan 2 |
| 45 | Remove duplicate sections in `docs/api.md` (Worker Health, Task Status appear twice) | docs/api.md | 15 min | Plan 2 |
| 46 | Add "What to Do" column to Pipeline Status table in `docs/pipeline.md` | docs/pipeline.md | 15 min | Plan 2 |
| 47 | Fix component docs dead references (`share-a11y.js`, `share_button.html`) | docs/components/*.md | 30 min | Plan 2 |
| 48 | Fix beat schedule count ("9 tasks" → "12 tasks") in 3 files | 3 files | 15 min | Plan 2 |
| 49 | Fix PWA Service Worker | static/js/service-worker.js | 1 hr | Plan 6 |

---

## Wave 5: Backend / Docker Improvements

### Medium Priority

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 50 | Convert Dockerfile to Multi-Stage Build (currently single-stage with `AS base` naming only) | Dockerfile | 2 hrs | Plan 5 |
| 51 | Add Resource Limits to docker-compose.yml (no mem/cpu constraints defined) | docker-compose.yml | 30 min | Plan 5 |
| 52 | Fix Plaintext Password Fallback in `install.sh` (stores plaintext if hashing fails) | scripts/install.sh | 30 min | Plan 5 |
| 53 | Add Validation Checks to `install.sh` (masked failures via `|| true`) | scripts/install.sh | 30 min | Plan 5 |
| 54 | Align Granian Worker Count (Dockerfile has 2, systemd has 4) | Dockerfile, systemd/ainews-web.service | 15 min | Plan 5 |
| 55 | Add `stop_grace_period` to docker-compose.yml | docker-compose.yml | 15 min | Plan 5 |
| 56 | Add `deploy` Target to Makefile (`scripts/deploy.sh` has no Makefile target) | Makefile | 15 min | Plan 5 |
| 57 | Fix `backup.sh` Fallback Method (race condition between checkpoint and copy) | scripts/backup.sh | 1 hr | Plan 5 |
| 58 | Update `verify_backup.sh` Tables (only checks 5 tables, should check all 18) | scripts/verify_backup.sh | 30 min | Plan 5 |
| 59 | Add Logging Driver Config to docker-compose.yml (no log rotation) | docker-compose.yml | 15 min | Plan 5 |
| 60 | Fix `deploy.sh` Hardcoded Health Check Port (uses 5000 instead of `$PORT`) | scripts/deploy.sh | 15 min | Plan 5 |
| 61 | Add Rollback Validation in `deploy.sh` (no validation of commit hash) | scripts/deploy.sh | 30 min | Plan 5 |
| 62 | Fix `deploy.sh` Remote Origin Assumption (hardcodes "origin" as remote name) | scripts/deploy.sh | 15 min | Plan 5 |

### Low Priority

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 63 | Consolidate Documentation (duplicated Nginx config and LLM provider setup) | docs/*.md | 1 hr | Plan 5 |
| 64 | REPO_URL default value validation (fail early) | scripts/*.sh | 30 min | Plan 8 |

---

## Wave 6: Performance Improvements

### Critical Performance

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 65 | Fix Cache Invalidation Gaps (uses `"pub:rss"` but actual keys are `"pub:rss_feed:*"`) | routes/admin/articles.py:290, routes/admin/review.py:94 | 1 hr | Plan 7 |
| 66 | Fix Sitemap TTL Mismatch | routes/public/feeds.py | 30 min | Plan 7 |

### High Performance

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 67 | Fix Dashboard Sources Query + Bug | routes/admin/dashboard.py | 1 hr | Plan 7 |
| 68 | Add Stampede Protection to ConfigCache (missing SET NX EX distributed lock) | services/config_cache.py:97-147 | 1 hr | Plan 7 |
| 69 | Fix Missing Eager Loading | routes/admin/*.py | 30 min | Plan 7 |
| 70 | Add Date Filter to `find_related_articles_dicts()` (missing 30-day filter present in `find_related_articles()`) | services/related.py:159-168 | 30 min | Plan 7 |
| 71 | Fix ThreadPoolExecutor Thread Leak in timeout.py | services/timeout.py | 1 hr | Plan 7 |
| 72 | Add ThreadPoolExecutor Shutdown Handlers | services/*.py | 1 hr | Plan 7 |
| 73 | Tune ThreadPoolExecutor Default Sizes | services/*.py | 30 min | Plan 7 |
| 74 | Persist Circuit Breaker State | services/circuit_breaker.py | 2 hrs | Plan 6 |

### Low Priority Performance

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 75 | Add L1 Cache Monitoring | services/*.py | 1 hr | Plans 6, 7 |
| 76 | Add SQLite WAL Checkpoint Management | services/*.py | 2 hrs | Plan 6 |

---

## Wave 7: Code Quality / Type Safety

### High Priority

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 77 | Type Stub Installation | pyproject.toml | 30 min | Plan 9 |
| 78 | Fix Implicit Optional Parameters | services/*.py | 30 min | Plan 9 |
| 79 | Fix `models.py` Type Errors | models.py | 1 hr | Plan 9 |

### Medium Priority

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 80 | Fix config.py Type Annotations | config.py | 2 hrs | Plan 9 |
| 81 | Fix content_extractor.py Union Type Errors | services/content_extractor.py | 1 hr | Plan 9 |
| 82 | Fix Adapter Type Mismatches | services/llm/*.py | 2 hrs | Plan 9 |
| 83 | Refactor `tasks/pipeline.py:run_stage` | tasks/pipeline.py | 3 hrs | Plan 9 |
| 84 | Refactor `services/subagent.py:_evaluate_condition` (fix bitwise AND/OR bug: uses `operator.and_` for logical operations with >2 operands - should use `all()` and `any()`) | services/subagent.py:1015 | 4 hrs | Plan 9 |
| 85 | Refactor `tasks/research.py:research_article` | tasks/research.py | 2 hrs | Plan 9 |
| 86 | Refactor `app.py:create_app` | app.py | 2 hrs | Plan 9 |
| 87 | Fix Silent Exception Handling | services/*.py, routes/*.py | 1 hr | Plan 6 |
| 88 | Add Missing A/B Experiment Tests | tests/*.py | 2 hrs | Plan 6 |
| 89 | Add Experiment Result Tracking | services/llm/*.py | 1 hr | Plan 6 |
| 90 | Add CSRF Tests | tests/test_csrf.py | 2 hrs | Plan 6 |
| 91 | Refactor `models.py` into Package | models/ | 3 hrs | Plan 6 |
| 92 | Fix `_COMPILED_PATTERNS` Dead Code | services/*.py | 30 min | Plan 6 |
| 93 | Standardize PipelineLogger %-formatting | services/logging_utils.py | 1 hr | Plan 6 |
| 94 | Make Services Framework-Agnostic | services/*.py | 2 hrs | Plan 6 |

### Low Priority

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 95 | Add Dependency Vulnerability Scanning | pyproject.toml | 1 hr | Plan 9 |
| 96 | Add `/offline/` Route (duplicate of PWA fix in item 49) | routes/public/*.py | 30 min | Plan 6 |
| 97 | Populate `docs/` Directory | docs/ | 2 hrs | Plan 6 |

---

## Wave 8: AI Agent / Pipeline Improvements (Longer Lead Time)

These items are designed but need more planning before implementation.

### P2 - Medium Priority

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 98 | Dynamic stage lists in pipeline_monitor.py (hardcoded stage list) | services/pipeline_monitor.py | 30 min | Plan 3 |
| 99 | Cache subagent tool registry (rebuilt every call) | services/subagent.py | 1 hr | Plan 3 |
| 100 | Document CircuitBreaker multi-worker limitation (in-memory only) | docs/*.md | 15 min | Plan 3 |
| 101 | Add `SUBAGENT_WORKERS` to `.env.example` | .env.example | 5 min | Plan 3 |
| 102 | Error-type-specific retry strategies (differentiate rate_limit vs timeout vs server_error) | services/*.py | 2 hrs | Plan 3 |
| 103 | Latency tracking for adaptive timeouts (P99-based) | services/*.py | 4 hrs | Plan 3 |
| 104 | Dead letter root cause aggregation | services/pipeline_monitor.py | 3 hrs | Plan 3 |
| 105 | Enhance subagent chain conditions (allow pre-computed values) | services/subagent.py | 3 hrs | Plan 3 |

### P2 - High Impact (Need Design)

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 106 | Pipeline health scoring system (composite 0-100 score) | services/pipeline_monitor.py | 1 wk | Plan 3 |
| 107 | Per-stage timeout configuration | services/config_unified.py | 4 hrs | Plan 3 |
| 108 | Priority-based queue system | tasks/*.py | 1-2 wks | Plan 3 |
| 109 | Failure pattern learning system | services/*.py | 1 wk | Plan 3 |

### P2 - Very High Impact (Significant Effort)

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 110 | Batch API integration (50% cost reduction potential) | services/llm/*.py | 2-3 wks | Plan 3 |
| 111 | Cost-tier model routing (60-85% cost reduction potential) | services/llm/*.py | 2-3 wks | Plan 3 |

### P3 - Cleanup

| ID | Item | Files | Effort | Source |
|----|------|-------|--------|--------|
| 112 | Refactor `degradation_count` duplication | services/pipeline_degradation.py | 1 hr | Plan 3 |
| 113 | Convert `PipelineStatus` to StrEnum | constants.py | 2-3 hrs | Plan 3 |

---

## Implementation Waves Summary

| Wave | Focus | Parallelizable | Items | Est. Effort |
|------|-------|----------------|-------|------------|
| 1 | Critical Bugs | No (sequential) | 7 | 2-3 hrs |
| 2 | Security/Observability | Yes | 24 | 5-7 hrs |
| 3 | Frontend/Accessibility | Yes | 9 | 4-5 hrs |
| 4 | Documentation | Yes | 17 | 4-5 hrs |
| 5 | Backend/Docker | Yes | 15 | 4-5 hrs |
| 6 | Performance | Yes | 12 | 6-8 hrs |
| 7 | Code Quality | Yes | 21 | 15-20 hrs |
| 8 | AI Agent/Pipeline | Partial | 16 | 4-6 wks |

### Items That Can Run in Parallel

**Wave 2 items (can run concurrently in subagents):**
- Items 8, 9, 10, 11, 12 (security/ops fixes)
- Items 13, 14, 15, 16, 17 (observability)
- Items 18, 19, 20, 21, 22, 23 (documentation fixes)

**Wave 3 items (all frontend - can run concurrently):**
- Items 24, 25, 26, 27, 28, 29, 30, 31, 32

**Wave 4 items (documentation - can run concurrently):**
- Items 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49

---

## Deferred Items (from previous plan.md)

These items are intentionally deferred. Do not implement without further analysis.

| Item | Description | Reason |
|------|-------------|--------|
| D1 | Degradation routing threshold change | Current `>= 2` behavior is intentional design. |
| D2 | CSS architecture refactor | Intentional duplication for first-paint performance. |
| D3 | Session cookie `__Secure-` prefix | Requires HTTPS in all environments. |
| D4 | HSTS `include_subdomains` | May break subdomains. |
| D5 | Redis-backed sessions | Current cookie sessions adequate. |
| D6 | Pipeline query parallelization | <1% savings, not worth complexity. |
| D7 | JS bundling | ~16KB custom JS, bundling adds complexity with no benefit. |
| D8 | CSS token sync (critical.css) | Working as intended. |
| D9 | Queue depth backpressure | Significant new feature needing design discussion. |

---

## Verification Commands

```bash
# Full lint check
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Type check
.venv/bin/python -m mypy . --exclude .venv
```

---

*Last updated: April 28, 2026*

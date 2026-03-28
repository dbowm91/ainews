# Completed Items from Plan.md (Phases 6-9)

All items from phases 6-9 have been completed.

## Phase 6: Observability

### 6.1 Request Correlation IDs
**Status:** Already implemented.
**Implementation:** `logging_config.py` has `RequestIDMiddleware` with `request_id_var` context var. `celery_app.py` passes `X-Request-ID` header to Celery tasks via `inject_request_id`.

### 6.2 Enhanced Logging (JSON + Request Timing)
**Status:** Already implemented.
**Implementation:** `logging_config.py` has `JSONFormatter`, `PlainFormatter`, and `RequestIDMiddleware` that logs request timing.

### 6.3 Celery Worker Health Check
**Status:** Already implemented.
**Implementation:** `routes/public.py:295-330` health endpoint checks Celery workers via `inspect.ping()`.

## Phase 7: Maintainability & Cleanup

### 7.1 Extract Common Newsletter Logic
**Status:** Already implemented.
**Implementation:** `services/newsletter.py` has `_generate_newsletter()` private method used by both `generate_main_newsletter` and `generate_topic_newsletter`.

### 7.2 Hardcoded Download Timeout
**Status:** Already implemented.
**Implementation:** `services/content_extractor.py` reads timeout from `CONTENT_EXTRACTOR_TIMEOUT` env var with default of 30.

### 7.3 Missing Type Hints on Key Services
**Status:** Already implemented.
**Implementation:** `services/url.py`, `services/prompts.py`, `services/utils.py` all have type annotations on public functions.

## Phase 8: Testing

### 8.1 XML Escaping Tests
**Status:** Already exists.
**Implementation:** `tests/test_prompts.py` (66 lines) covers `esc_xml_text()` and `esc_xml_attr()`.

### 8.2 URL Validation Test Coverage
**Status:** Already exists.
**Implementation:** `tests/test_url_validate.py` (142 lines) covers localhost with port, public URLs with ports, mixed case hostname.

### 8.3 Auth Lockout Tests
**Status:** Completed.
**Implementation:** Created `tests/test_admin_auth.py` with 19 tests covering memory fallback, Redis lockout, login endpoint behavior, and lockout cleanup.

### 8.4 Concurrent Access Tests
**Status:** Completed.
**Implementation:** Expanded `tests/test_concurrent_access.py` with comprehensive threading tests for ConfigCache (concurrent reads/writes/invalidate/Redis failure) and metrics singleton (uniqueness, counter increments, gauge sets, histogram observations, Prometheus export).

### 8.5 Migration Testing
**Status:** Completed.
**Implementation:** Created `tests/test_migrations.py` verifying database schema matches SQLAlchemy models (table existence, column presence, indexes).

## Phase 9: Optional / Low ROI

### 9.1 Cost Tracking
**Status:** Completed.
**Implementation:** Created `services/cost_tracker.py` with per-model cost estimation from LLM token metrics. Added `GET /admin/api/costs` endpoint in `routes/admin/api.py`. Created `tests/test_cost_tracker.py`.

### 9.2 Metrics Endpoint (Prometheus Format)
**Status:** Already implemented.
**Implementation:** `services/metrics.py` has `get_prometheus()` method. `routes/admin/api.py:134-141` exposes `GET /admin/api/metrics/prometheus`.

### 9.3 Rate Limit Configuration Review
**Status:** Completed.
**Implementation:** Changed default rate limit from 200/minute to 60/minute in `extensions.py:35`. Already configurable via `RATELIMIT_DEFAULT` env var.

## Summary

**All 14 deferred items are now completed.** 10 were already implemented in previous phases. 4 required new code:
- `tests/test_admin_auth.py` (new file, 19 tests)
- `tests/test_concurrent_access.py` (expanded, 12 tests)
- `tests/test_migrations.py` (new file, 11 tests)
- `services/cost_tracker.py` (new file + admin endpoint + tests)

All 417 tests pass. Ruff check clean.

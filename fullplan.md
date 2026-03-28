# ainews Full Improvement Plan

Consolidated remaining items from plan2, plan3, plan4, and plan5. Items from plan.md (Phases 1–9) are confirmed complete and excluded. Deduplicated across sources. Organized by priority and dependency.

**Pre-commit checks (run after every item):**
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Phase 10: Bug Fixes & Correctness

### ✅ 10.1 Unguarded db.session.commit() in reprocess_article

**Location:** `routes/admin/articles.py:296, 309, 321`

**Problem:** Three bare `db.session.commit()` calls without try/except or rollback.

**Status:** Completed — all three locations wrapped with try/except SQLAlchemyError/rollback.

---

### ✅ 10.2 Bare Exception Audit (Selective)

**Location:** `services/pipeline_monitor.py`, `services/config_cache.py`, `routes/public.py`, `routes/admin/review.py`

**Status:** Completed — `services/pipeline_monitor.py` changed to `from redis.exceptions import RedisError`. `services/config_cache.py` already correct. `routes/public.py` and `routes/admin/review.py` reviewed — all bare catches are intentionally broad for graceful degradation (topic loading, Celery health check, email sending).

---

## Phase 11: Security Hardening

### ✅ 11.1 Admin Password Hash Validation at Startup

**Location:** `config.py:108-114`

**Status:** Completed — `ProductionConfig.validate()` now calls `_is_password_hash()` and raises RuntimeError if ADMIN_PASSWORD is not hashed.

---

### 11.2 Content Security Policy Audit

**Location:** `app.py`, `templates/**/*.html`

**Problem:** Current CSP allows `'unsafe-inline'` for styles. Can be tightened.

**Fix:**
1. Audit all inline styles in templates
2. Move inline styles to CSS files where possible
3. Use nonce-based CSP for remaining inline styles
4. Add `frame-ancestors 'self'` and `base-uri 'self'`

**Files:** `app.py`, templates, `static/css/`

**Estimated time:** 3 hours

**Sources:** plan4 item 15.1

---

### ✅ 11.3 SQL Injection Audit

**Location:** All files with raw SQL

**Status:** Completed — all raw SQL uses parameterized queries via SQLAlchemy `text()` with `:param` placeholders. `services/article.py` FTS queries verified safe. `tasks/pipeline.py` uses SQLAlchemy table objects. No issues found.

---

### ✅ 11.4 Request Size Validation

**Location:** `routes/public.py`, `routes/admin/`

**Status:** Completed — added `limit_content_length` decorator. Subscribe endpoint limited to 1KB, admin login limited to 1KB. Global `MAX_CONTENT_LENGTH=64KB` remains as fallback.

---

## Phase 12: Pipeline & Configuration

### ✅ 12.1 Make Pipeline Retry Constants Configurable

**Location:** `tasks/pipeline.py:11-12`

**Status:** Completed — added `MAX_STAGE_RETRIES` and `MAX_TOTAL_RETRIES` to `Config` class in `config.py` (read from env vars). `tasks/pipeline.py` now uses `_get_max_stage_retries()` and `_get_max_total_retries()` helpers that read from Flask config with fallback defaults.

---

### ✅ 12.2 ModelLimiter Release Failure Metrics

**Location:** `services/limiter.py:49-54`

**Status:** Completed — added `metrics.counter_inc("limiter.release_failure")` in the release() except block.

---

### 12.3 Config Cache Hash Validation

**Location:** `services/config_cache.py`

**Problem:** `invalidate_if_stale()` relies on filesystem `mtime`, which is unreliable in containers, network filesystems, and CI/CD.

**Fix:**
1. Add SHA256 hash-based change detection as alternative to mtime
2. Add `CONFIG_CACHE_STRATEGY=mtime|hash` env var

**Files:** `services/config_cache.py`

**Estimated time:** 1–2 hours

**Sources:** plan5 item 3

---

### ✅ 12.4 YAML Config Startup Validation

**Location:** All YAML config files

**Status:** Completed — confirmed Pydantic validation runs on config load at startup. All schema files (`schemas/llm.py`, `schemas/source.py`, `schemas/topic.py`, `schemas/pipeline.py`) validate via Pydantic model construction. `_validate_llm_providers()` in `config.py` validates at startup. Was already implemented per the "Already Implemented" section.

---

## Phase 13: Source Monitoring

### ✅ 13.1 Source Crawl Failure Tracking

**Location:** `models.py`, `services/crawling.py`

**Status:** Completed:
- Added columns to `Source` model: `consecutive_failures`, `last_success_at`, `last_error`, `disabled_at`
- Created migration `009_source_health_tracking.py`
- Added `record_crawl_success()` and `record_crawl_failure()` to `services/crawling.py`
- Auto-disables source after 10 consecutive failures
- Added `GET /admin/api/sources/health` endpoint
- Created sources management page at `/admin/sources` with enable/disable buttons

---

### 13.2 Source Crawl History Logging

**Location:** New `CrawlAttempt` model, `services/crawling.py`

**Problem:** No historical log of crawl attempts for debugging source issues.

**Fix:**
1. Add `CrawlAttempt` model (source_id, started_at, finished_at, status, articles_fetched, articles_new, error_message)
2. Log each crawl attempt
3. Add admin view: `/admin/sources/<id>/history`
4. Retention: cleanup attempts older than 30 days

**Files:** `models.py`, `services/crawling.py`, `routes/admin/sources.py`, `tasks/cleanup.py`, new migration

**Estimated time:** 4 hours

**Sources:** plan4 item 10.2

---

## Phase 14: Newsletter Improvements

### 14.1 Newsletter Delivery Status Tracking

**Location:** `models.py`, `services/email.py`, `tasks/newsletter.py`

**Problem:** No tracking of delivery success/failure per subscriber. Can't identify bounces.

**Fix:**
1. Add `NewsletterDelivery` model (newsletter_id, subscriber_id, status, sent_at, error_message)
2. Log each send attempt in `services/email.py`
3. Flag subscribers with multiple bounces
4. Add admin delivery stats view

**Files:** `models.py`, `services/email.py`, `tasks/newsletter.py`, `routes/admin/newsletters.py`, new migration

**Estimated time:** 3 hours

**Sources:** plan4 item 11.1

---

### ✅ 14.2 Newsletter Preview Endpoint

**Location:** `routes/admin/newsletters.py`

**Status:** Completed — added `POST /admin/api/newsletter/preview` endpoint that generates executive summary and newsletter HTML without sending emails. Returns JSON with subject, article_count, and sanitized HTML.

---

### 14.3 Newsletter Pipeline Versioning

**Location:** `services/newsletter_pipeline.py`

**Problem:** Newsletter pipeline doesn't track intermediate results per stage, making debugging failures difficult.

**Fix:**
1. Add `NewsletterVersion` model (newsletter_id, stage, content, created_at)
2. Save version after each stage in `generate_executive_summary()`
3. Include version info in API responses

**Files:** `models.py`, `services/newsletter_pipeline.py`, `routes/admin/newsletters.py`, new migration

**Estimated time:** 2–3 hours

**Sources:** plan5 item 2

---

## Phase 15: Performance

### ✅ 15.1 Database Index Audit

**Location:** `models.py`

**Status:** Completed — added `ix_articles_category_status` composite index on `(category, pipeline_status)` to `Article.__table_args__`. Other indexes (`ix_articles_status_created`, `ix_articles_published`, `ix_articles_impact`) already existed. Indexes for `crawl_attempts` and `newsletter_deliveries` deferred until those models are created.

---

### ✅ 15.2 Response Cache Headers

**Location:** `routes/public.py`

**Status:** Completed — added `Cache-Control: public, max-age=300, stale-while-revalidate=600` and `Last-Modified` header to article pages. Updated both feed endpoints to include `stale-while-revalidate=600`.

---

### ✅ 15.3 Article List Prefetch Optimization

**Location:** `services/article.py`

**Status:** Completed — added `joinedload(Article.source)`, `joinedload(Article.tags)`, `joinedload(Article.metrics)` to both the standard query path and the FTS search path in `get_articles_paginated()`.

---

## Phase 16: Admin UX

### ✅ 16.1 Bulk Article Operations

**Location:** `routes/admin/articles.py`, `routes/admin/api.py`

**Status:** Completed — added `POST /admin/api/articles/bulk` endpoint supporting three actions: `delete`, `set_status`, `set_category`. Limits to 500 articles per operation. Uses proper transaction handling with rollback.

---

### ✅ 16.2 Article Search Improvements

**Location:** `services/article.py`, `routes/admin/articles.py`

**Status:** Completed — added URL search (detects URL-like queries and searches `original_url`), source filter (`source_id` param), and date range filter (`date_from`, `date_to` params). Sources list passed to templates for filter dropdown.

---

### 16.3 Pipeline Run Details Page

**Location:** New `routes/admin/pipelines.py`

**Problem:** Pipeline view shows logs but no detailed timeline or stage breakdown.

**Fix:**
1. Create detailed view with stage-by-stage timing, error summary, article list with per-article status
2. Add "retry failed articles" button

**Files:** `routes/admin/pipelines.py`, new `templates/admin/pipeline_detail.html`

**Estimated time:** 2.5 hours

**Sources:** plan4 item 13.3

---

## Phase 17: Multi-User & Auth

### 17.1 Multi-User Admin Support

**Location:** `routes/admin/__init__.py`, `models.py`

**Problem:** Single admin password via env var. No RBAC, no accountability, no delegation.

**Fix:**
1. Create `AdminUser` model (username, password_hash, role, created_at, last_login)
2. Migrate `ADMIN_PASSWORD` to seed initial admin
3. Add roles: admin, editor, reviewer
4. Update `@require_auth` to check role permissions
5. Add admin action audit logging

**Files:** `models.py`, `routes/admin/__init__.py`, new `routes/admin/auth.py`, new migration

**Estimated time:** 4–6 hours

**Sources:** plan5 item 1

---

## Phase 18: Observability & Monitoring

### ✅ 18.1 Celery Worker Health Admin Endpoint

**Location:** `routes/admin/api.py`

**Status:** Completed — added `GET /admin/api/workers/health` endpoint that reports worker status, active tasks count, reserved tasks count, and worker pool stats.

---

### 18.2 Search Correlation ID Propagation

**Location:** `services/search/`

**Problem:** Web search calls don't carry correlation IDs, making research failure debugging difficult.

**Fix:**
1. Modify `BaseSearchProvider` to accept `request_id` parameter
2. Pass `X-Correlation-ID` header in search provider requests

**Files:** `services/search/base.py`, `services/search/duckduckgo.py`, `services/search/google.py`, `services/search/searxng.py`

**Estimated time:** 1 hour

**Sources:** plan5 item 4

---

### 18.3 Database Backup Strategy

**Problem:** SQLite WAL mode is used but no automated backup mechanism.

**Fix:**
1. Add daily backup script using `.backup` API or `sqlite3 .backup`
2. Configure retention policy
3. Document restore procedure

**Files:** New `scripts/backup_db.sh`, deployment config

**Estimated time:** 2 hours

**Sources:** plan3 item 4.3

---

## Phase 19: Testing

### 19.1 Redis Unavailability Tests

**Problem:** Limited test coverage for Redis failure scenarios.

**Fix:** Add tests for rate limiter fail-closed behavior, login lockout memory fallback, ConfigCache behavior when Redis is down.

**Files:** `tests/test_limiter.py`, `tests/test_admin_auth.py`

**Estimated time:** 2 hours

**Sources:** plan3 item 5.1

---

### 19.2 Content Extractor Timeout Tests

**Problem:** No explicit tests for timeout handling in `services/content_extractor.py`.

**Fix:** Add tests for timeout scenarios, partial content extraction, malformed HTML.

**Files:** `tests/test_content_extractor.py`

**Estimated time:** 1.5 hours

**Sources:** plan3 item 5.2

---

### 19.3 URL Normalization Edge Case Tests

**Problem:** Limited coverage for URL edge cases.

**Fix:** Add tests for international domain names, fragments, auth info, URL encoding/decoding.

**Files:** `tests/test_url.py`

**Estimated time:** 1.5 hours

**Sources:** plan3 item 5.3

---

## Phase 20: Developer Experience

### 20.1 API Documentation (OpenAPI)

**Problem:** Admin API endpoints lack documentation.

**Fix:** Create OpenAPI 3.0 spec, add Swagger UI at `/admin/api/docs` (protected by auth).

**Files:** New `docs/api/openapi.yaml`, `templates/admin/api_docs.html`

**Estimated time:** 3 hours

**Sources:** plan4 item 14.1

---

### 20.2 Development Seed Data Script

**Problem:** New developers have empty database with no quick way to populate test data.

**Fix:** Create `scripts/seed_dev.py` that generates sources, articles, tags, subscribers, newsletters. Use factories from `tests/factories.py`. Add `--reset` flag.

**Files:** New `scripts/seed_dev.py`

**Estimated time:** 2 hours

**Sources:** plan4 item 14.2

---

### 20.3 Environment Validation Script

**Problem:** Environment misconfigurations cause runtime errors with no pre-flight check.

**Fix:** Create `scripts/validate_env.py` that checks required env vars, Redis connection, SQLite writable, LLM providers reachable, ports available.

**Files:** New `scripts/validate_env.py`

**Estimated time:** 1.5 hours

**Sources:** plan4 item 14.3

---

### 20.4 Type Hints on Key Services

**Location:** `services/url.py`, `services/prompts.py`, `services/utils.py`

**Problem:** Several public functions lack return type annotations.

**Fix:** Add return type annotations to all public functions in these files.

**Files:** `services/url.py`, `services/prompts.py`, `services/utils.py`

**Estimated time:** 1 hour

**Sources:** plan3 item 6.1, plan5 item 13

---

### 20.5 Documentation

**Problem:** Complex functions lack docstrings. README lacks architecture overview.

**Fix:** Add docstrings to public APIs, document exception behavior, add architecture diagram to README.

**Files:** Various, `README.md`

**Estimated time:** 3 hours

**Sources:** plan3 item 6.2

---

## Summary

| Phase | Items | Completed | Deferred |
|-------|-------|-----------|----------|
| 10. Bug Fixes | 2 | ✅ 2 | 0 |
| 11. Security | 4 | ✅ 3 | 1 (11.2 CSP) |
| 12. Pipeline & Config | 4 | ✅ 3 | 1 (12.3 Hash) |
| 13. Source Monitoring | 2 | ✅ 1 | 1 (13.2 History) |
| 14. Newsletter | 3 | ✅ 1 | 2 (14.1, 14.3) |
| 15. Performance | 3 | ✅ 3 | 0 |
| 16. Admin UX | 3 | ✅ 2 | 1 (16.3 Details) |
| 17. Multi-User | 1 | 0 | 1 (17.1) |
| 18. Observability | 3 | ✅ 1 | 2 (18.2, 18.3) |
| 19. Testing | 3 | 0 | 3 (19.1–19.3) |
| 20. Dev Experience | 5 | 0 | 5 (20.1–20.5) |
| **Total** | **33** | **✅ 16** | **17** |

## Already Implemented (from source plans, confirmed via code review)

These items appeared in plan2–5 but are verified complete in the codebase:

| Item | Evidence |
|------|----------|
| Celery task timeouts | All tasks have `soft_time_limit=300, time_limit=360` |
| Subscriber soft delete | `models.py:166` has `deleted_at` column + `get_active()` classmethod |
| Dev config password warning | `config.py:86-88` logs warning when ADMIN_PASSWORD unset |
| LLM provider startup validation | `config.py:117-146` validates keys/models, raises on missing |
| Config hot-reload validation | `routes/admin/api.py:88-122` validates before clearing caches |
| Newsletter pipeline fallbacks | Metrics counters + `used_fallback`/`fallback_stages` in response |
| Content extractor timeout config | `os.environ.get("CONTENT_EXTRACTOR_TIMEOUT", "30")` |
| YAML config Pydantic validation | Schemas validate on load |
| Request ID middleware | `logging_config.py` + `app.py` |
| Pipeline status constants | `constants.py:27-37` `PipelineStatus` class |
| Pipeline monitor | `services/pipeline_monitor.py` with Redis minute-bucket counters |
| DNS cache thread safety | `services/url.py` with `threading.Lock` |
| ConfigCache thread safety | `services/config_cache.py` with `threading.RLock` |
| Metrics singleton safety | `services/metrics.py` with double-checked locking |
| Login attempt memory cleanup | `routes/admin/__init__.py:25-47` `_cleanup_stale_entries()` |

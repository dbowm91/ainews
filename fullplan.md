# ainews Full Improvement Plan

Consolidated remaining items from plan2, plan3, plan4, and plan5. Items from plan.md (Phases 1–9) are confirmed complete and excluded. Deduplicated across sources. Organized by priority and dependency.

**Pre-commit checks (run after every item):**
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Phase 10: Bug Fixes & Correctness

### 10.1 Unguarded db.session.commit() in reprocess_article

**Location:** `routes/admin/articles.py:296, 309, 321`

**Problem:** Three bare `db.session.commit()` calls without try/except or rollback. Confirmed still broken in codebase.

**Fix:**
```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    logger.exception("Failed to reprocess article %s", article_id)
    return jsonify({"message": "Failed to reprocess article"}), 500
select_article.delay(article.id)
```
Apply to all three locations.

**Files:** `routes/admin/articles.py`

**Estimated time:** 15 minutes

**Sources:** plan2 item 1, plan5 item 5

---

### 10.2 Bare Exception Audit (Selective)

**Location:** `services/pipeline_monitor.py`, `services/config_cache.py`, `routes/public.py`, `routes/admin/review.py`

**Problem:** Some catches use bare `Exception` where specific types are appropriate. Note: many bare catches in LLM/content_extractor code are intentional for graceful degradation — do not change those.

**Fix:**
1. Audit `services/pipeline_monitor.py` and `services/config_cache.py` — replace with `redis.exceptions.RedisError` for Redis ops, `SQLAlchemyError` for DB ops
2. Add comments where broad catches are intentional
3. In routes, replace bare `Exception` with specific types where appropriate

**Files:** `services/pipeline_monitor.py`, `services/config_cache.py`, `routes/public.py`, `routes/admin/review.py`

**Estimated time:** 1–2 hours

**Sources:** plan3 item 2.1, plan.md item 5.2 (was marked complete but plan3 identifies more locations)

---

## Phase 11: Security Hardening

### 11.1 Admin Password Hash Validation at Startup

**Location:** `config.py:108-114`

**Problem:** `ProductionConfig.validate()` checks that `ADMIN_PASSWORD` is set but doesn't verify it's a proper hash. A plaintext password passes startup validation and only fails at login time. Confirmed missing — `_is_password_hash()` helper exists at `routes/admin/__init__.py:73-75` but isn't called from validation.

**Fix:** Add to `ProductionConfig.validate()`:
```python
from routes.admin import _is_password_hash
if not _is_password_hash(self.ADMIN_PASSWORD):
    raise RuntimeError("ADMIN_PASSWORD must be a hashed password. Run: python scripts/hash_password.py")
```

**Files:** `config.py`

**Estimated time:** 30 minutes

**Sources:** plan3 item 1.2

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

### 11.3 SQL Injection Audit

**Location:** All files with raw SQL

**Problem:** While SQLAlchemy provides protection, raw SQL strings should be verified.

**Fix:**
1. Search for raw SQL strings in codebase
2. Verify all use parameterized queries
3. Add bandit/semgrep rule to prevent regressions

**Files:** Various

**Estimated time:** 2 hours

**Sources:** plan4 item 15.3

---

### 11.4 Request Size Validation

**Location:** `routes/public.py`, `routes/admin/`

**Problem:** `MAX_CONTENT_LENGTH` is 64KB globally but some routes need different limits.

**Fix:** Add per-route size limits via decorators for article edit (32KB), subscribe (1KB), admin login (1KB).

**Files:** `routes/public.py`, `routes/admin/`

**Estimated time:** 1.5 hours

**Sources:** plan4 item 15.2

---

## Phase 12: Pipeline & Configuration

### 12.1 Make Pipeline Retry Constants Configurable

**Location:** `tasks/pipeline.py:11-12`

**Problem:** `MAX_STAGE_RETRIES = 3` and `MAX_TOTAL_RETRIES = 10` are hardcoded. Confirmed still hardcoded.

**Fix:**
1. Move to `config.py` or environment variables: `MAX_STAGE_RETRIES`, `MAX_TOTAL_RETRIES`
2. Import from config in `tasks/pipeline.py`

**Files:** `tasks/pipeline.py`, `config.py`

**Estimated time:** 30 minutes

**Sources:** plan3 item 3.1

---

### 12.2 ModelLimiter Release Failure Metrics

**Location:** `services/limiter.py:49-54`

**Problem:** `release()` logs warnings on Redis errors but doesn't increment metrics counters. Confirmed missing.

**Fix:** Add `metrics.counter_inc("limiter.release_failure")` in the except block.

**Files:** `services/limiter.py`

**Estimated time:** 15 minutes

**Sources:** plan3 item 2.2

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

### 12.4 YAML Config Startup Validation

**Location:** All YAML config files

**Problem:** Verify that Pydantic validation runs on config load at startup.

**Fix:** Confirm that `schemas/llm.py`, `schemas/source.py`, `schemas/topic.py`, `schemas/pipeline.py` validate on load. Add startup check that all required configs load successfully.

**Files:** Schema files, `config.py`

**Estimated time:** 30 minutes

**Sources:** plan5 item 14

---

## Phase 13: Source Monitoring

### 13.1 Source Crawl Failure Tracking

**Location:** `models.py`, `services/crawling.py`

**Problem:** Sources can silently fail over time with no health tracking or auto-disable.

**Fix:**
1. Add columns to `Source` model: `consecutive_failures`, `last_success_at`, `last_error`, `disabled_at`
2. Update `services/crawling.py` to track failures/successes
3. Auto-disable after 10 consecutive failures
4. Add `GET /admin/api/sources/health` endpoint
5. Add sources management page with health indicators

**Files:** `models.py`, `services/crawling.py`, `routes/admin/api.py`, new `routes/admin/sources.py`, `templates/admin/sources.html`, new migration

**Estimated time:** 4 hours

**Sources:** plan4 item 10.1

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

### 14.2 Newsletter Preview Endpoint

**Location:** `routes/admin/newsletters.py`

**Problem:** No way to preview newsletter content before sending.

**Fix:**
1. Add `POST /admin/api/newsletter/preview` endpoint
2. Generate newsletter HTML without sending
3. Return HTML for preview display

**Files:** `routes/admin/newsletters.py`, `services/newsletter_pipeline.py`

**Estimated time:** 2 hours

**Sources:** plan4 item 11.2

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

### 15.1 Database Index Audit

**Location:** `models.py`

**Problem:** Some queries may be slow due to missing indexes.

**Fix:**
1. Analyze query patterns with `EXPLAIN QUERY PLAN`
2. Add indexes: `(pipeline_status, created_at)` on articles, `(category, pipeline_status)` on articles, `(source_id, started_at)` on crawl_attempts, `(newsletter_id, status)` on newsletter_deliveries

**Files:** `models.py`, new migration

**Estimated time:** 2 hours

**Sources:** plan4 item 12.1

---

### 15.2 Response Cache Headers

**Location:** `routes/public.py`

**Problem:** Article pages and RSS feeds lack optimal cache headers for CDN/browser caching.

**Fix:**
1. Add `Cache-Control: public, max-age=300, stale-while-revalidate=600` to article pages
2. Add `ETag` support for conditional requests on feeds
3. Add `Last-Modified` header for article pages

**Files:** `routes/public.py`

**Estimated time:** 1.5 hours

**Sources:** plan4 item 12.2

---

### 15.3 Article List Prefetch Optimization

**Location:** `services/article.py`

**Problem:** `get_articles_paginated()` may cause N+1 queries for source, tags, metrics.

**Fix:** Add `joinedload` for `Article.source`, `Article.tags`, `Article.metrics`.

**Files:** `services/article.py`

**Estimated time:** 1.5 hours

**Sources:** plan4 item 12.3

---

## Phase 16: Admin UX

### 16.1 Bulk Article Operations

**Location:** `routes/admin/articles.py`, `templates/admin/articles.html`

**Problem:** No bulk approve/reject/tag operations. Time-consuming for admins.

**Fix:**
1. Add checkboxes to article list UI
2. Add `POST /admin/api/articles/bulk` endpoint
3. Support bulk approve, reject, add tags, change category
4. Use Celery task for large selections

**Files:** `routes/admin/articles.py`, `routes/admin/api.py`, `templates/admin/articles.html`

**Estimated time:** 3 hours

**Sources:** plan4 item 13.1

---

### 16.2 Article Search Improvements

**Location:** `services/article.py`, `routes/admin/articles.py`

**Problem:** Admin search is basic — no URL search, limited filters.

**Fix:**
1. Add URL search (match `original_url` if query looks like URL)
2. Add date range, status, and source filters
3. Improve FTS5 ranking with `bm25()`

**Files:** `services/article.py`, `routes/admin/articles.py`

**Estimated time:** 2 hours

**Sources:** plan4 item 13.2

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

### 18.1 Celery Worker Health Admin Endpoint

**Location:** `routes/admin/api.py`

**Problem:** No dedicated admin endpoint for worker health monitoring.

**Fix:** Add `GET /admin/api/workers/health` that pings workers and reports status. Note: `/health` endpoint already includes Celery worker check — this adds a more detailed admin-only view.

**Files:** `routes/admin/api.py`

**Estimated time:** 1 hour

**Sources:** plan3 item 4.2

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

| Phase | Items | Est. Time | Priority |
|-------|-------|-----------|----------|
| 10. Bug Fixes | 2 | ~2h | **High** |
| 11. Security | 4 | ~7h | **High** |
| 12. Pipeline & Config | 4 | ~3h | **High** |
| 13. Source Monitoring | 2 | ~8h | **High** |
| 14. Newsletter | 3 | ~7.5h | Medium |
| 15. Performance | 3 | ~5h | Medium |
| 16. Admin UX | 3 | ~7.5h | Medium |
| 17. Multi-User | 1 | ~5h | Medium |
| 18. Observability | 3 | ~4h | Medium |
| 19. Testing | 3 | ~5h | Medium |
| 20. Dev Experience | 5 | ~10.5h | Low |
| **Total** | **33** | **~64h** | |

## Recommended Implementation Order

1. **10.1** Unguarded commits — quick bug fix, 15 min
2. **11.1** Password hash validation — security, 30 min
3. **12.1** Pipeline retry config — quick config change, 30 min
4. **12.2** Limiter release metrics — quick instrumentation, 15 min
5. **10.2** Bare exception audit — correctness, 1–2h
6. **13.1** Source failure tracking — production critical, 4h
7. **15.3** Article list prefetch — user-facing perf, 1.5h
8. **15.1** Database index audit — performance foundation, 2h
9. **14.2** Newsletter preview — quick admin win, 2h
10. **16.1** Bulk article operations — high admin value, 3h
11. **13.2** Source crawl history — complements 13.1, 4h
12. **14.1** Newsletter delivery tracking — email reliability, 3h
13. **15.2** Response cache headers — easy perf gain, 1.5h
14. **16.2** Article search improvements — admin productivity, 2h
15. **14.3** Newsletter versioning — debugging aid, 2.5h
16. **18.1** Worker health endpoint — monitoring, 1h
17. **11.4** Request size validation — security, 1.5h
18. **17.1** Multi-user support — if needed, 5h
19. **19.1–19.3** Tests — confidence, 5h
20. **11.2–11.3** CSP & SQL injection audit — security hardening, 5h
21. **12.3–12.4** Config cache hash & YAML validation — reliability, 2h
22. **18.2–18.3** Search correlation IDs & DB backup — observability, 3h
23. **16.3** Pipeline run details — debugging, 2.5h
24. **20.1–20.5** Dev experience — onboarding, 10.5h

---

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

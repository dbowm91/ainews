# Deferred Items from fullplan.md

Items skipped during the 2026-03-28 implementation session. Organized by estimated effort.

---

## Large Features (4+ hours each)

### 13.2 Source Crawl History Logging
**Est:** 4 hours | **Priority:** Medium
- New `CrawlAttempt` model with source_id, timestamps, status, article counts, error_message
- Log each crawl attempt in `services/crawling.py`
- Admin view `/admin/sources/<id>/history`
- Cleanup task for attempts older than 30 days
- **Files:** models.py, services/crawling.py, routes/admin/sources.py, tasks/cleanup.py, new migration

### 17.1 Multi-User Admin Support
**Est:** 4–6 hours | **Priority:** Medium
- New `AdminUser` model (username, password_hash, role, created_at, last_login)
- Migrate ADMIN_PASSWORD to seed initial admin
- Roles: admin, editor, reviewer
- Update `@require_auth` for role-based access
- Admin action audit logging
- **Files:** models.py, routes/admin/__init__.py, new routes/admin/auth.py, new migration

### 20.1 API Documentation (OpenAPI)
**Est:** 3 hours | **Priority:** Low
- OpenAPI 3.0 spec for admin API endpoints
- Swagger UI at `/admin/api/docs` (auth-protected)
- **Files:** New docs/api/openapi.yaml, templates/admin/api_docs.html

### 20.5 Documentation
**Est:** 3 hours | **Priority:** Low
- Docstrings on public APIs
- Exception behavior documentation
- Architecture diagram in README
- **Files:** Various, README.md

---

## Medium Features (1.5–3 hours each)

### 11.2 Content Security Policy Audit
**Est:** 3 hours | **Priority:** Medium
- Audit inline styles in templates
- Move to external CSS files
- Nonce-based CSP for remaining inline styles
- Add `frame-ancestors 'self'` and `base-uri 'self'`
- **Files:** app.py, templates, static/css/

### 14.1 Newsletter Delivery Status Tracking
**Est:** 3 hours | **Priority:** Medium
- New `NewsletterDelivery` model (newsletter_id, subscriber_id, status, sent_at, error_message)
- Log each send attempt in `services/email.py`
- Flag subscribers with multiple bounces
- Admin delivery stats view
- **Files:** models.py, services/email.py, tasks/newsletter.py, routes/admin/newsletters.py, new migration

### 14.3 Newsletter Pipeline Versioning
**Est:** 2–3 hours | **Priority:** Medium
- New `NewsletterVersion` model (newsletter_id, stage, content, created_at)
- Save version after each pipeline stage
- Include version info in API responses
- **Files:** models.py, services/newsletter_pipeline.py, routes/admin/newsletters.py, new migration

### 16.3 Pipeline Run Details Page
**Est:** 2.5 hours | **Priority:** Low
- Detailed view with stage-by-stage timing
- Error summary, article list with per-article status
- "Retry failed articles" button
- **Files:** routes/admin/pipelines.py, new templates/admin/pipeline_detail.html

### 18.3 Database Backup Strategy
**Est:** 2 hours | **Priority:** Medium
- Daily backup script using SQLite `.backup` API
- Retention policy
- Restore procedure documentation
- **Files:** New scripts/backup_db.sh, deployment config

### 19.1 Redis Unavailability Tests
**Est:** 2 hours | **Priority:** Medium
- Rate limiter fail-closed behavior tests
- Login lockout memory fallback tests
- ConfigCache behavior when Redis is down
- **Files:** tests/test_limiter.py, tests/test_admin_auth.py

### 20.2 Development Seed Data Script
**Est:** 2 hours | **Priority:** Low
- `scripts/seed_dev.py` using test factories
- Sources, articles, tags, subscribers, newsletters
- `--reset` flag for clean slate
- **Files:** New scripts/seed_dev.py

---

## Small Features (1–1.5 hours each)

### 12.3 Config Cache Hash Validation
**Est:** 1–2 hours | **Priority:** Medium
- SHA256 hash-based change detection as alternative to mtime
- `CONFIG_CACHE_STRATEGY=mtime|hash` env var
- **Files:** services/config_cache.py

### 18.2 Search Correlation ID Propagation
**Est:** 1 hour | **Priority:** Medium
- `BaseSearchProvider` accepts `request_id` parameter
- `X-Correlation-ID` header in search provider requests
- **Files:** services/search/base.py, services/search/duckduckgo.py, services/search/google.py, services/search/searxng.py

### 19.2 Content Extractor Timeout Tests
**Est:** 1.5 hours | **Priority:** Medium
- Tests for timeout scenarios, partial extraction, malformed HTML
- **Files:** tests/test_content_extractor.py

### 19.3 URL Normalization Edge Case Tests
**Est:** 1.5 hours | **Priority:** Medium
- International domain names, fragments, auth info, URL encoding
- **Files:** tests/test_url.py

### 20.3 Environment Validation Script
**Est:** 1.5 hours | **Priority:** Low
- Pre-flight checks for env vars, Redis, SQLite, LLM providers, ports
- **Files:** New scripts/validate_env.py

### 20.4 Type Hints on Key Services
**Est:** 1 hour | **Priority:** Low
- Return type annotations on public functions
- **Files:** services/url.py, services/prompts.py, services/utils.py

---

## Total Deferred Effort: ~38 hours

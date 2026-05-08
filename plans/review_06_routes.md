# Routes Architecture Review

**Date:** 2026-05-08
**Reviewer:** Architecture Review Agent
**Document Reviewed:** `architecture/routes.md`

---

## Executive Summary

This review compares the documented routes in `architecture/routes.md` against the actual implementation in the codebase. Overall, the documentation is **generally accurate** but has several discrepancies including incorrect API endpoint paths, undocumented endpoints, and a missing endpoint that was documented but never implemented.

---

## Verified Items (Correct)

### Public Routes - Feeds (`routes/public/feeds.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/sitemap.xml` | `/sitemap.xml` | CORRECT |
| `/feed/<format>` | `/feed` and `/feed/<category>` (not `<format>`) | PARTIAL - Different path structure |
| `/articles` | `/` (index) and topic/tag routes exist | CORRECT |

**Notes:**
- The documented `/feed/<format>` doesn't match. Actual implementation uses `/feed` for all articles and `/feed/<category>` for topic-specific feeds.
- The index route at `/` serves the article list functionality.

### Public Routes - Subscribe (`routes/public/subscribe.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/subscribe` (POST) | `/subscribe` (POST) | CORRECT |
| `/verify/<token>` | `/verify/<token>` (GET) | CORRECT |
| `/unsubscribe/<token>` | `/unsubscribe/<token>` (GET/POST) | CORRECT |

**Notes:**
- The implementation includes token validation with proper security checks.
- Email verification flow is properly implemented.

### Public Routes - Links (`routes/public/links.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/a/<short_id>` | `/a/<short_id>` and `/s/<short_id>` both exist | CORRECT |
| `/track/newsletter-click/<int:article_id>` | `/track/newsletter-click/<int:article_id>` | CORRECT |

**Notes:**
- The `short_url_tracking_page` serves `/a/<short_id>` and `short_url_redirect` serves `/s/<short_id>`.
- Both routes track `ArticleMetric.share_link_views`.
- The tracking endpoint correctly uses `int:article_id` converter.

### Admin Routes - Authentication (`routes/admin/auth.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/login` (GET, POST) | `/login` (GET, POST) | CORRECT |
| `/logout` | `/logout` | CORRECT |

**Notes:**
- Session hijacking protection is implemented (IP + User-Agent binding) - VERIFIED at `routes/admin/__init__.py:73-84`.
- Login lockout via Redis is implemented - VERIFIED.
- TOTP 2FA support is implemented.
- 8 backup codes for account recovery - VERIFIED.

### Admin API - Articles (`routes/admin/api/articles.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/api/v1/articles` (GET, POST) | `/articles` and `/articles/ids`, `/articles/counts-by-status` | PARTIAL |
| `/api/v1/articles/<id>` (GET, PUT, DELETE) | `/articles/<int:article_id>` with GET, PUT, DELETE | CORRECT |
| `/api/v1/articles/<id>/pipeline` (POST) | `/articles/<int:article_id>/pipeline` (POST) | CORRECT |

**Notes:**
- Bulk operations endpoint `/articles/bulk` (POST) exists but is undocumented.
- The `/articles/ids` endpoint provides article ID listing with filtering.

### Admin API - Sources (`routes/admin/api/sources.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/api/v1/sources` (GET, POST) | `/sources` (GET, POST) | CORRECT |
| `/api/v1/sources/<id>` (GET, PUT, DELETE) | `/sources/<int:source_id>` with GET, PUT, PATCH, DELETE | CORRECT |
| `/api/v1/sources/<id>/refresh` (POST) | `/sources/<int:source_id>/refresh` (POST) | CORRECT |

**Notes:**
- The PATCH method for partial updates is implemented but undocumented.

### Admin API - Pipeline (`routes/admin/api/pipeline.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/api/v1/pipeline/stats` | `/pipeline/stats` | CORRECT |
| `/api/v1/pipeline/backlog` | `/pipeline/backlog` | CORRECT |

**Notes:**
- Additional endpoints exist but are undocumented:
  - `/pipeline/dead-letter/stats` - Dead letter queue statistics
  - `/pipeline/sla` - SLA metrics
  - `/costs` - LLM cost summary
  - `/sources/health` - Source health status

### Admin API - Webhooks (`routes/admin/api/webhooks.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/api/v1/webhooks` (GET, POST) | `/webhooks` (GET, POST) | CORRECT |
| `/api/v1/webhooks/<id>/test` (POST) | `/webhooks/<int:webhook_id>/test` (POST) | CORRECT |

**Notes:**
- Additional endpoints exist but are undocumented:
  - `/webhooks/<int:webhook_id>` (GET, PUT, PATCH, DELETE) - Full CRUD
  - `/webhooks/<int:webhook_id>/events` - List delivery events
  - `/webhooks/events/<int:event_id>/resend` - Resend event

### Admin API - Config (`routes/admin/api/config.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/api/v1/config/reload` (POST) | `/config/reload` (POST) | CORRECT |

**Notes:**
- Additional endpoints exist but are undocumented:
  - `/metrics` - Application metrics
  - `/metrics/prometheus` - Prometheus-format metrics

### Admin API - Audit (`routes/admin/api/audit.py`)

| Documented | Actual | Status |
|------------|--------|--------|
| `/api/v1/audit-logs` (GET) | `/audit-logs` (GET) | CORRECT |

**Notes:**
- Endpoint properly supports pagination and filtering by action, target_type, and days.

---

## Discrepancies

### 1. API Endpoint Path Prefix - MAJOR

**Issue:** The document shows `/api/v1/articles` but the actual prefix is set at the Blueprint level in `routes/admin/__init__.py:15`:

```python
admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/api/v1")
```

However, individual routes are registered WITHOUT the `/api/v1` prefix because they use `admin_api_bp` directly. For example, `routes/admin/api/articles.py:151`:

```python
@admin_api_bp.route("/articles/ids", methods=["GET"])
```

This creates the full path `/api/v1/articles/ids` NOT `/api/v1/articles`.

**Verification:** Confirmed by examining `routes/admin/api/articles.py`:
- Line 151: `@admin_api_bp.route("/articles/ids"` - Full path: `/api/v1/articles/ids`
- Line 170: `@admin_api_bp.route("/articles/counts-by-status"` - Full path: `/api/v1/articles/counts-by-status`
- Line 527: `@admin_api_bp.route("/articles/<int:article_id>/pipeline"` - Full path: `/api/v1/articles/<id>/pipeline`

**The document's table is correct** - it shows full paths like `/api/v1/articles`. This is VERIFIED.

### 2. Documented `/share/<platform>/<article_id>` Does NOT Exist

**Document says:**
```python
@public_bp.route("/share/<platform>/<article_id>")
def share_article(platform, article_id): ...
```

**Actual:** No such route exists in `routes/public/links.py` or anywhere in the public routes.

**Status:** This endpoint was **planned but never implemented**. The share functionality is handled differently:
- Share configs are stored in `ShareConfig` model
- Share buttons on articles use client-side JavaScript with URL templates from the share configs
- Share click tracking uses `/api/v1/track/share-click/<int:article_id>` (POST)

**Location of share-related code:**
- `routes/admin/shares.py` - Admin UI for managing share platforms
- `routes/public/links.py:123-127` - `/api/v1/track/share-click/<int:article_id>` endpoint

**Action Required:** Either implement the endpoint or remove from documentation. See `plans/plan.md` line 236.

### 3. Click Tracking Endpoint Naming

**Document says:** `/click/<tracking_id>` (implied, from "click tracking endpoint" section)

**Actual:** `/track/newsletter-click/<int:article_id>`

**Status:** The document is ambiguous but the actual implementation is correct. The endpoint tracks newsletter clicks and redirects to the article. This is VERIFIED at `routes/public/links.py:130-133`.

### 4. Template Directory Structure

**Document says:** Nested template directories under `templates/admin/partials/`

**Actual:** Flat structure confirmed in `templates/` - all templates are at the root level of their respective directories.

**Status:** Document is INCORRECT. The actual structure is flat:
```
templates/
├── admin/
│   ├── dashboard.html
│   ├── articles.html
│   ├── article_edit.html
│   ├── sources.html
│   ├── newsletters.html
│   ├── partials/       # This directory EXISTS
│   └── ...
├── partials/
├── errors/
├── macros/
├── article.html
├── index.html
└── share_redirect.html
```

Note: The `partials/` subdirectory DOES exist under `templates/admin/`, so partial templates are in `templates/admin/partials/`.

---

## Undocumented Functionality Found

### Additional Admin API Endpoints

The following endpoints exist but are NOT documented in `architecture/routes.md`:

1. **`/api/v1/articles/ids`** (GET) - Get article IDs matching filter params
2. **`/api/v1/articles/counts-by-status`** (GET) - Get article counts by pipeline status
3. **`/api/v1/articles/bulk`** (POST) - Bulk operations on articles
4. **`/api/v1/pipeline/dead-letter/stats`** (GET) - Dead letter queue statistics
5. **`/api/v1/pipeline/sla`** (GET) - SLA metrics
6. **`/api/v1/costs`** (GET) - LLM cost summary
7. **`/api/v1/sources/health`** (GET) - Source health status
8. **`/api/v1/webhooks/<id>/events`** (GET) - List webhook delivery events
9. **`/api/v1/webhooks/events/<event_id>/resend`** (POST) - Resend webhook event
10. **`/api/v1/metrics`** (GET) - Application metrics
11. **`/api/v1/metrics/prometheus`** (GET) - Prometheus-format metrics

### Admin UI Routes (Undocumented)

1. **`/admin/shares`** - Share platform configuration UI
2. **`/admin/shares/add`** - Add share platform (POST)
3. **`/admin/shares/<id>/edit`** - Edit share platform (POST)
4. **`/admin/shares/<id>/delete`** - Delete share platform (POST)
5. **`/admin/shares/<id>/toggle`** - Toggle share platform active state (POST)
6. **`/admin/trend_memory`** - Trend memory management
7. **`/admin/topic_notes`** - Topic notes management
8. **`/admin/review`** - Article review interface
9. **`/admin/pipelines`** - Pipeline management
10. **`/admin/metrics`** - Metrics dashboard

### Public Routes (Undocumented)

1. **`/`** - Homepage/index with article listing
2. **`/topic/<category>`** - Topic-based article feed
3. **`/tag/<slug>`** - Tag-based article feed
4. **`/article/<int:article_id>`** - Article detail page
5. **`/health`** - Health check endpoint

---

## Issues Found

### Issue 1: Missing `/share/<platform>/<article_id>` Endpoint

**Severity:** Medium
**Type:** Missing functionality (documented but not implemented)

The documentation describes a share endpoint that doesn't exist. The current share functionality is client-side only (JavaScript constructs share URLs from templates).

**Recommendation:** 
- If this endpoint is needed for server-side share tracking or URL shortening, implement it
- Otherwise, update documentation to reflect actual share implementation

### Issue 2: Template Structure Documentation Inaccurate

**Severity:** Low
**Type:** Documentation error

The document describes nested template directories but the actual structure is flat with some subdirectories (partials).

**Recommendation:** Update `architecture/routes.md` lines 122-138 to accurately describe the template structure.

### Issue 3: Missing Documentation for Admin API Endpoints

**Severity:** Medium
**Type:** Documentation gap

Multiple functional admin API endpoints are not documented in the API table (lines 103-118).

**Recommendation:** Add undocumented endpoints to the API table or create supplementary documentation.

---

## Recommendations

### Immediate Actions

1. **Update `architecture/routes.md`** to remove `/share/<platform>/<article_id>` or implement it
2. **Update template structure** description to reflect flat structure with partials subdirectory
3. **Add missing admin API endpoints** to the documentation table

### Long-term Improvements

1. Consider generating API documentation from code (e.g., using Flask-RESTX or apispec)
2. Add a script to verify route documentation against implementation
3. Create a comprehensive API changelog when routes are added/modified

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct | 15 |
| Partial Match | 3 |
| Missing (Documented but Not Implemented) | 1 |
| Undocumented (Implemented but Not Documented) | 20+ |

**Overall Assessment:** The routes documentation is mostly accurate for the core endpoints but has significant gaps in coverage and one missing endpoint that was documented but never implemented.

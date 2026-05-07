# Routes Architecture Review (2026-05-07)

Date: 2026-05-07
Review of: `architecture/routes.md`
Type: Follow-up review (previous review: plans/06_routes.md dated 2026-05-06)

## Executive Summary

The previous architecture review (2026-05-06) identified several missing API endpoints and discrepancies. This follow-up review finds that **most critical gaps have been addressed** - the Article CRUD endpoints, pipeline trigger, and source refresh endpoints now exist. However, some documentation vs. implementation mismatches remain.

## Verification of Previous "Not Found" Items

| Item (from plans/06_routes.md) | Status | Actual Location |
|--------------------------------|--------|----------------|
| `GET/PUT/DELETE /api/articles/<id>` | **NOW EXISTS** | `routes/admin/api/articles.py:596-702` |
| `POST /api/articles/<id>/pipeline` | **NOW EXISTS** | `routes/admin/api/articles.py:527-593` |
| `POST /api/sources/<id>/refresh` | **NOW EXISTS** | `routes/admin/api/sources.py:342-382` |

**Conclusion**: The high-priority items from the previous review have been implemented.

---

## Current Discrepancies

### 1. Public Feeds Routes

| Route | Documented | Actual | Status |
|-------|------------|--------|--------|
| `/sitemap.xml` | Yes | `GET /sitemap.xml` | VERIFIED |
| `/feed/<format>` | Yes (atom, rss, json) | Only `/feed` and `/feed/<category>` (RSS only) | DISCREPANCY |
| `/articles` | Yes | Does not exist | DISCREPANCY |

**Evidence** (`routes/public/feeds.py`):
- Lines 222-256: `feed_all()` at `/feed`
- Lines 259-305: `feed_topic(category)` at `/feed/<category>`
- No `/feed/<format>` variant exists
- No `/articles` route exists (articles are shown on `/` index or topic/tag pages)

### 2. Links Routes

| Route | Documented | Actual | Status |
|-------|------------|--------|--------|
| `/a/<short_id>` | Yes | `GET /a/<short_id>` | VERIFIED |
| `/share/<platform>/<article_id>` | Yes | NOT FOUND | DISCREPANCY |
| `/click/<tracking_id>` | Yes | NOT FOUND | DISCREPANCY |

**Actual Implementation** (`routes/public/links.py`):
- Line 94-100: `/s/<short_id>` - Short URL redirect (not `/a/<short_id>`)
- Line 103-115: `/a/<short_id>` - Short URL tracking page
- Line 123-127: `/api/v1/track/share-click/<int:article_id>` (POST)
- Line 130-133: `/track/newsletter-click/<int:article_id>` (GET)

### 3. Template Directory Structure

| Documented | Actual | Status |
|------------|--------|--------|
| `templates/admin/articles/list.html` | `templates/admin/articles.html` | DISCREPANCY |
| `templates/admin/articles/edit.html` | `templates/admin/article_edit.html` | DISCREPANCY |
| `templates/admin/sources/list.html` | `templates/admin/sources.html` | DISCREPANCY |
| `templates/admin/sources/edit.html` | NOT FOUND | DISCREPANCY |
| `templates/admin/newsletters/list.html` | `templates/admin/newsletters.html` | DISCREPANCY |
| `templates/admin/newsletters/view.html` | NOT FOUND | DISCREPANCY |

**Evidence**: `ls templates/admin/` shows flat structure with no subdirectories.

### 4. API Endpoint Path Discrepancies

| Documented | Actual | Status |
|------------|--------|--------|
| `GET /api/articles` | `GET /api/v1/articles/ids` | DISCREPANCY (different resource) |
| `GET /api/pipeline/runs` | NOT FOUND | DISCREPANCY |
| `GET /api/pipeline/runs/<id>` | NOT FOUND | DISCREPANCY |
| `POST /api/pipeline/trigger` | NOT FOUND | DISCREPANCY |
| `GET /api/audit` | `GET /api/v1/audit-logs` | DISCREPANCY (different URL) |

**Note**: The admin API blueprint prefix is `/api/v1` (`routes/admin/__init__.py:15`):
```python
admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/api/v1")
```

The docs show `/api/articles` but actual paths are `/api/v1/articles`. This is a version prefix discrepancy.

### 5. Authentication Discrepancies

| Route | Documented | Actual | Status |
|-------|------------|--------|--------|
| `/logout` | No method specified | `POST /admin/logout` only | DISCREPANCY |

**Evidence** (`routes/admin/auth.py:188-196`):
```python
@admin_bp.route("/logout", methods=["POST"])
def logout() -> Response:
```

---

## Bugs and Issues

### Bug 1: API Version Prefix Mismatch (Low Severity)

**File**: `architecture/routes.md` lines 108-122

The documented API paths show `/api/articles` but the actual blueprint uses `/api/v1` prefix.

**Fix**: Update documentation to show `/api/v1/articles`, `/api/v1/sources`, etc.

### Bug 2: Short URL Route Discrepancy (Medium Severity)

**File**: `architecture/routes.md` lines 68-69

Documented: `/a/<short_id>` for short URL redirect
Actual: `/s/<short_id>` is the redirect, `/a/<short_id>` is the tracking page

**Evidence** (`routes/public/links.py`):
- Lines 94-100: `/s/<short_id>` redirects to `/article/{id}`
- Lines 103-115: `/a/<short_id>` renders share_redirect.html

### Bug 3: Missing `/articles` Public Route (Low Severity)

**File**: `architecture/routes.md` lines 40-41

The documented `/articles` public route does not exist. Articles are on `/`, `/topic/<category>`, or `/tag/<slug>`.

---

## Verified Implementations (Documentation Accurate)

### Public Routes
- `/subscribe` (POST) - `routes/public/subscribe.py:31-134` VERIFIED
- `/verify/<token>` - `routes/public/subscribe.py:183-227` VERIFIED
- `/unsubscribe/<token>` - `routes/public/subscribe.py:137-180` VERIFIED (GET and POST)
- `/sitemap.xml` - `routes/public/feeds.py:308-342` VERIFIED

### Admin Authentication
- `/login` (GET/POST) - `routes/admin/auth.py:43-94` VERIFIED
- `/logout` (POST) - `routes/admin/auth.py:188-196` VERIFIED
- `/verify-2fa` (GET/POST) - `routes/admin/auth.py:97-148` VERIFIED
- `/setup-2fa` (GET/POST) - `routes/admin/auth.py:151-185` VERIFIED
- Session hijacking protection - `routes/admin/__init__.py:71-84` VERIFIED
- Login lockout via Redis - `routes/admin/__init__.py:226-249` VERIFIED

### Admin API Endpoints
- `GET /api/v1/articles/<id>` - `routes/admin/api/articles.py:596-616` VERIFIED
- `PUT /api/v1/articles/<id>` - `routes/admin/api/articles.py:619-669` VERIFIED
- `DELETE /api/v1/articles/<id>` - `routes/admin/api/articles.py:672-702` VERIFIED
- `POST /api/v1/articles/<id>/pipeline` - `routes/admin/api/articles.py:527-593` VERIFIED
- `GET/POST /api/v1/sources` - `routes/admin/api/sources.py:16-120` VERIFIED
- `GET/PUT/PATCH/DELETE /api/v1/sources/<id>` - `routes/admin/api/sources.py:123-339` VERIFIED
- `POST /api/v1/sources/<id>/refresh` - `routes/admin/api/sources.py:342-382` VERIFIED
- `GET/POST /api/v1/webhooks` - `routes/admin/api/webhooks.py:56-162` VERIFIED
- `POST /api/v1/webhooks/<id>/test` - `routes/admin/api/webhooks.py:297-318` VERIFIED
- `POST /api/v1/config/reload` - `routes/admin/api/config.py:13-49` VERIFIED
- `GET /api/v1/audit-logs` - `routes/admin/api/audit.py:11-66` VERIFIED
- `GET /api/v1/search/analytics` - `routes/admin/api/search.py:9-54` VERIFIED

### Additional API Endpoints (Not in Documentation)

| Endpoint | Location |
|----------|----------|
| `GET /api/v1/articles/ids` | `routes/admin/api/articles.py:151-167` |
| `GET /api/v1/articles/counts-by-status` | `routes/admin/api/articles.py:170-184` |
| `POST /api/v1/articles/bulk` | `routes/admin/api/articles.py:469-524` |
| `GET /api/v1/pipeline/stats` | `routes/admin/api/pipeline.py:13-45` |
| `GET /api/v1/pipeline/dead-letter/stats` | `routes/admin/api/pipeline.py:48-84` |
| `GET /api/v1/pipeline/backlog` | `routes/admin/api/pipeline.py:87-132` |
| `GET /api/v1/pipeline/sla` | `routes/admin/api/pipeline.py:187-258` |
| `GET /api/v1/costs` | `routes/admin/api/pipeline.py:135-158` |
| `GET /api/v1/sources/health` | `routes/admin/api/pipeline.py:161-184` |
| `GET /api/v1/metrics` | `routes/admin/api/config.py:52-57` |
| `GET /api/v1/metrics/prometheus` | `routes/admin/api/config.py:60-66` |
| `GET /api/v1/webhooks/<id>/events` | `routes/admin/api/webhooks.py:321-360` |
| `POST /api/v1/webhooks/events/<id>/resend` | `routes/admin/api/webhooks.py:363-398` |

---

## Recommendations

### Priority 1: Documentation Fixes

1. **Update API version prefix**: Change all `/api/` references to `/api/v1/`
   - Affected: lines 108-122 of `architecture/routes.md`
   - Also affects: `AGENTS.md` line 42

2. **Update template paths**: Document flat structure instead of nested
   - Change `templates/admin/articles/list.html` to `templates/admin/articles.html`
   - Change `templates/admin/articles/edit.html` to `templates/admin/article_edit.html`
   - Remove references to non-existent subdirectories

3. **Document actual logout behavior**: Note that `/logout` requires POST method

4. **Document missing share/click routes**: Either implement or remove from docs
   - Option A: Add routes at `/share/<platform>/<article_id>` and `/click/<tracking_id>`
   - Option B: Update docs to show actual routes

### Priority 2: Implementation (Optional)

5. **Add `/feed/<format>` support** if multi-format feeds are needed (atom, rss, json)
   - Current: only RSS at `/feed` and `/feed/<category>`
   - Location: `routes/public/feeds.py`

6. **Add `/articles` public listing route** if intended
   - Location: `routes/public/feeds.py`

### Priority 3: Add Undocumented Endpoints to Documentation

7. Document the following existing but undocumented API endpoints:
   - `/api/v1/articles/ids` - Get article IDs matching filters
   - `/api/v1/articles/counts-by-status` - Get counts by pipeline status
   - `/api/v1/articles/bulk` - Bulk article operations
   - `/api/v1/pipeline/stats` - Pipeline stage statistics
   - `/api/v1/pipeline/dead-letter/stats` - Dead letter queue stats
   - `/api/v1/pipeline/backlog` - Current processing backlog
   - `/api/v1/pipeline/sla` - SLA metrics
   - `/api/v1/costs` - LLM cost summary
   - `/api/v1/sources/health` - Source health status
   - `/api/v1/webhooks/<id>/events` - Webhook delivery events
   - `/api/v1/webhooks/events/<id>/resend` - Resend webhook event
   - `/api/v1/metrics` - Application metrics
   - `/api/v1/metrics/prometheus` - Prometheus-format metrics

---

## Summary

| Category | Count |
|----------|-------|
| Previously "Not Found" - Now Verified | 3 |
| Documentation Errors (API paths) | 6+ |
| Documentation Errors (Template paths) | 6 |
| Undocumented but Implemented | 14+ |

**Overall Status**: The codebase is more complete than the previous review indicated. The main issue is **outdated documentation** rather than missing implementation. The architecture document needs updating to reflect:
1. The `/api/v1/` prefix (not `/api/`)
2. The actual flat template structure
3. The actual implemented routes (some different from docs)
4. The additional undocumented API endpoints

---

## Files Referenced

- `/home/sugarwookie/projects/ainews/architecture/routes.md` - Documentation reviewed
- `/home/sugarwookie/projects/ainews/routes/public/feeds.py` - Public feed routes
- `/home/sugarwookie/projects/ainews/routes/public/links.py` - Link tracking routes
- `/home/sugarwookie/projects/ainews/routes/public/subscribe.py` - Subscription routes
- `/home/sugarwookie/projects/ainews/routes/admin/__init__.py` - Admin blueprint and auth
- `/home/sugarwookie/projects/ainews/routes/admin/auth.py` - Login/logout/2FA
- `/home/sugarwookie/projects/ainews/routes/admin/api/articles.py` - Article API (CRUD + pipeline)
- `/home/sugarwookie/projects/ainews/routes/admin/api/sources.py` - Source API + refresh
- `/home/sugarwookie/projects/ainews/routes/admin/api/pipeline.py` - Pipeline stats/monitoring
- `/home/sugarwookie/projects/ainews/routes/admin/api/webhooks.py` - Webhook API
- `/home/sugarwookie/projects/ainews/routes/admin/api/config.py` - Config API
- `/home/sugarwookie/projects/ainews/routes/admin/api/audit.py` - Audit log API
- `/home/sugarwookie/projects/ainews/routes/admin/api/search.py` - Search analytics

# Routes Module Architecture Review

## Summary

Most document claims are **accurate**. Verified against codebase with minor discrepancies noted below.

---

## Verified Claims

### ✅ Blueprint Registration (app.py:188-197)
- `public_bp` registered at `/` — **Correct**
- `admin_bp` registered at `/admin` — **Correct**
- `admin_api_bp` registered at `/api/v1` — **Correct**
- `api_tokens_bp` registered at `/api-tokens` — **Correct**

### ✅ Blueprint Structure (routes/admin/__init__.py:14-15)
- `admin_bp = Blueprint("admin", __name__, url_prefix="/admin")` — **Correct**
- `admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/api/v1")` — **Correct**

### ✅ Public Routes
- `public/feeds.py` index, topic, tag, RSS, sitemap — **Correct** (routes/public/feeds.py:73-342)
- `public/subscribe.py` subscribe/unsubscribe/verify — **Correct** (routes/public/subscribe.py)
- `public/links.py` article detail, short URLs, tracking — **Correct** (routes/public/links.py)

### ✅ Admin Routes
- All admin HTML routes present in `routes/admin/` — **Correct**
- API endpoints at `/api/v1/*` via `admin_api_bp` — **Correct**

### ✅ API Token Authentication (routes/admin/__init__.py:18-44, 47-101)
- Bearer token support via `verify_api_token()` — **Correct**
- Session-based auth with hijacking protection — **Correct**
- TOTP 2FA support — **Correct**
- Login lockout via Redis (with in-memory fallback) — **Correct**

### ✅ CSRF Protection
- `validate_csrf_json` decorator for JSON endpoints — **Correct** (routes/decorators.py:10-32)
- `limit_content_length` for size limits — **Correct**

---

## Discrepancies & Issues

### MED: `articles/ids` Endpoint Missing GET List (routes/admin/api/articles.py:152-168)

**Document says:** `GET /api/v1/articles` - List articles (supports status filter)

**Actual Code:** The document shows two separate endpoints:
- `GET /api/v1/articles` - List articles
- `GET /api/v1/articles/ids` - Batch article ID lookup

The `routes/admin/api/articles.py` file has:
- `get_article_ids()` at line 152 (GET `/articles/ids`) — returns IDs only
- `get_article_counts_by_status()` at line 171 (GET `/articles/counts-by-status`)
- `bulk_article_operations()` at line 470 (POST `/articles/bulk`)

**There is NO `GET /api/v1/articles` endpoint** for listing articles. The document lists it but it doesn't exist. The closest is `articles/ids` which returns only IDs.

**Impact:** API consumers expecting a full article list at `GET /api/v1/articles` will get 404.

---

### MED: `newsletters` API Endpoints Partially Correct

**Document says:** At lines 197-198:
```
- `GET /api/v1/newsletters/stats` - Newsletter delivery stats
- `POST /api/v1/newsletter/preview` - Preview newsletter
```

**Actual Code:** Both endpoints exist in `routes/admin/newsletters.py`:
- Line 177: `@admin_api_bp.route("/newsletters/stats")` — correct URL `/api/v1/newsletters/stats`
- Line 221: `@admin_api_bp.route("/newsletter/preview")` — correct URL `/api/v1/newsletter/preview`

Both match the document. Previously I incorrectly noted this as missing.

**However:** The document doesn't list the `/api/v1/newsletter/preview` endpoint in the API table at line 265-293, only in the earlier bullet list. This is a documentation consistency issue.

---

### MED: `trend-memory/semantic-search` Wrong URL Prefix

**Document says** (line 292): `GET /api/v1/trend-memory/semantic-search` - Semantic search in trend memory

**Actual Code** (routes/admin/trend_memory.py:117):
```python
@admin_bp.route("/api/trend-memory/semantic-search", methods=["GET"])
@require_auth
def trend_memory_semantic_search():
```

The endpoint exists but is registered on `admin_bp` (prefix `/admin`), so the actual URL is:
- **Document says:** `/api/v1/trend-memory/semantic-search`
- **Actual URL:** `/admin/api/trend-memory/semantic-search`

**Impact:** API consumers using documented URL will get 404.

---

### LOW: `/admin/articles/<id>/original` Duplicated in Document

**Document says** (lines 44-47):
```
- `/admin/articles/<id>/original` - Original article view
- `/admin/articles/<id>/versions` - Article version history
- `/admin/articles/<id>/versions/<version_id>/rollback` - Rollback article to version
- `/admin/articles/<id>/original` - Original article view  ← DUPLICATE
```

The `/admin/articles/<id>/original` appears twice (lines 44 and 47).

---

### LOW: Document Lists `/admin/shares` Routes But Code Uses Different Pattern

**Document says** (lines 72-78):
```
- `/admin/shares` - Share config management
- `/admin/shares/<id>/edit-form` - Edit share config form
- `/admin/shares/<id>/row` - Share config row
...
```

**Actual Code** (routes/admin/shares.py):
- `GET /admin/shares` — list share configs (correct)
- `POST /admin/shares/<id>/edit` — edit (not "edit-form")
- `POST /admin/shares/<id>/row` — row update (not "edit-form" or "row" as separate)
- `POST /admin/shares/add` — add (not separate route)
- `POST /admin/shares/<id>/edit` — edit
- `POST /admin/shares/<id>/delete` — delete
- `POST /admin/shares/<id>/toggle` — toggle

The routes exist but with slightly different naming. Not a functional issue, just documentation drift.

---

## Security Review

### ✅ Session Hijacking Protection (routes/admin/__init__.py:75-86)
- IP + User-Agent binding on each request — **Correct**

### ✅ Login Lockout (routes/admin/__init__.py:104-303)
- Redis-based with atomic Lua script — **Correct**
- In-memory fallback when Redis unavailable — **Correct**

### ✅ CSRF on JSON Endpoints (routes/decorators.py:10-32)
- `validate_csrf_json` validates `X-CSRFToken` header — **Correct**

### ✅ API Token Storage
- Tokens stored as `prefix + hash` (not plaintext) — **Correct** (routes/admin/api_tokens.py:38-47)

---

## Layering Violations

### HIGH: `api_tokens.py` Imports from `routes.admin` (routes/admin/api_tokens.py:7)

```python
from routes.admin import require_auth
```

`api_tokens.py` is in `routes/admin/` but is a separate blueprint (`api_tokens_bp`). This imports the `require_auth` decorator from `routes.admin/__init__.py`.

This is a **circular dependency risk** — `routes/admin/__init__.py` imports all submodules at lines 308-352, including `api_tokens`. If the import order changes or if `require_auth` depends on something that hasn't initialized yet, this could break.

**Current behavior:** Works because imports happen after all module-level code runs, but fragile.

**Recommendation:** Move `require_auth` to `routes/decorators.py` or create `routes/admin/auth.py` for auth utilities.

---

## Performance Notes

### ✅ Cache Headers on Public Feeds (routes/public/feeds.py:252-256, 338-341)
```
Cache-Control: public, max-age=600, stale-while-revalidate=1200
```
— Properly set on RSS feeds and sitemap.

### ✅ HTMX Partial Rendering (routes/public/__init__.py:29-35)
- `_render_feed_or_page()` returns different templates for HTMX vs full page — **Correct**
- Reduces payload for paginated navigation

---

## Recommendations

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| HIGH | Layering: `api_tokens.py` imports `require_auth` from parent module | `routes/admin/api_tokens.py:7` | Move `require_auth` to `routes/decorators.py` |
| MED | Missing `GET /api/v1/articles` list endpoint | `routes/admin/api/articles.py` | Add article list endpoint or clarify doc |
| MED | `trend-memory/semantic-search` wrong URL prefix | `routes/admin/trend_memory.py:117` - doc says `/api/v1/` but actual is `/admin/api/` | Move endpoint to `admin_api_bp` or update doc |
| LOW | Duplicate `/admin/articles/<id>/original` in doc | `architecture/routes.md:44,47` | Fix typo in documentation |
| LOW | `shares` routes differ slightly between doc and code | `routes/admin/shares.py` vs doc | Update documentation to match actual routes |
| LOW | Newsletter endpoints not in API table at lines 265-293 | `architecture/routes.md` | Add missing entries to API table |

---

## File Inventory Verified

| Document Path | Actual Path | Status |
|---------------|-------------|--------|
| `routes/public/feeds.py` | `routes/public/feeds.py` | ✅ |
| `routes/public/subscribe.py` | `routes/public/subscribe.py` | ✅ |
| `routes/public/links.py` | `routes/public/links.py` | ✅ |
| `routes/admin/__init__.py` | `routes/admin/__init__.py` | ✅ |
| `routes/admin/auth.py` | `routes/admin/auth.py` | ✅ |
| `routes/admin/api_tokens.py` | `routes/admin/api_tokens.py` | ✅ |
| `routes/admin/api/articles.py` | `routes/admin/api/articles.py` | ✅ |
| `routes/admin/api/sources.py` | `routes/admin/api/sources.py` | ✅ |
| `routes/admin/api/pipeline.py` | `routes/admin/api/pipeline.py` | ✅ |
| `routes/admin/api/webhooks.py` | `routes/admin/api/webhooks.py` | ✅ |
| `routes/admin/api/config.py` | `routes/admin/api/config.py` | ✅ |
| `routes/admin/api/audit.py` | `routes/admin/api/audit.py` | ✅ |
| `routes/admin/api/search.py` | `routes/admin/api/search.py` | ✅ |
| `routes/admin/api/health.py` | `routes/admin/api/health.py` | ✅ |
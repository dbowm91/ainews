# Routes Architecture Review Plan

## Verified Claims

### Structure
- **CONFIRMED**: routes/public/ contains feeds.py, subscribe.py, links.py ✓
- **CONFIRMED**: routes/admin/ contains auth.py, api_tokens.py, and admin API sub-modules ✓
- **CONFIRMED**: routes/admin/api/ contains articles.py, sources.py, pipeline.py, webhooks.py, audit.py, config.py, search.py ✓

### Public Routes
- **CONFIRMED**: `/sitemap.xml` route exists in feeds.py (line 308) ✓
- **CONFIRMED**: `/feed/<format>` route exists in feeds.py (line 222) — actually `/feed` and `/feed/<category>` for atom/rss/json feeds ✓
- **CONFIRMED**: `/articles` route exists in feeds.py (line 73) ✓
- **CONFIRMED**: `/subscribe` POST route in subscribe.py (line 31) ✓
- **CONFIRMED**: `/verify/<token>` route in subscribe.py (line 183) ✓
- **CONFIRMED**: `/unsubscribe/<token>` route in subscribe.py (lines 137, 153) ✓
- **CONFIRMED**: `/a/<short_id>` and `/s/<short_id>` routes in links.py (lines 94, 103) ✓
- **CONFIRMED**: `/track/newsletter-click/<int:article_id>` route in links.py (line 130) ✓

### Admin Routes API Endpoints at Root Level
- **CONFIRMED**: `admin_api_bp` is registered with `url_prefix="/api/v1"` (routes/admin/__init__.py line 15)
- **CONFIRMED**: Articles CRUD at `/api/v1/articles` with GET, POST, PUT, DELETE ✓
- **CONFIRMED**: `/api/v1/articles/<id>/pipeline` POST for pipeline trigger ✓
- **CONFIRMED**: `/api/v1/articles/bulk` POST for bulk operations ✓
- **CONFIRMED**: Sources CRUD at `/api/v1/sources` with GET, POST, PUT, PATCH, DELETE ✓
- **CONFIRMED**: `/api/v1/sources/<id>/refresh` POST for source refresh ✓
- **CONFIRMED**: `/api/v1/pipeline/stats` GET ✓
- **CONFIRMED**: `/api/v1/pipeline/backlog` GET ✓
- **CONFIRMED**: `/api/v1/pipeline/dead-letter/stats` GET ✓
- **CONFIRMED**: `/api/v1/pipeline/sla` GET ✓
- **CONFIRMED**: Webhooks CRUD at `/api/v1/webhooks` ✓
- **CONFIRMED**: `/api/v1/webhooks/<id>/test` POST ✓
- **CONFIRMED**: `/api/v1/webhooks/<id>/events` GET ✓
- **CONFIRMED**: `/api/v1/config/reload` POST ✓
- **CONFIRMED**: `/api/v1/audit-logs` GET ✓
- **CONFIRMED**: `/api/v1/metrics` GET ✓

### Security Features
- **CONFIRMED**: TOTP 2FA support in auth.py (verify_token, verify_backup_code, generate_backup_codes) ✓
- **CONFIRMED**: 8 backup codes implementation via generate_backup_codes() in auth.py (line 165) ✓
- **CONFIRMED**: Session hijacking protection (IP + User-Agent binding) in require_auth (routes/admin/__init__.py lines 73-84) ✓
- **CONFIRMED**: Login lockout via Redis with in-memory fallback (routes/admin/__init__.py lines 102-301) ✓
- **CONFIRMED**: CSRF protection via validate_csrf_json decorator on admin API endpoints ✓
- **CONFIRMED**: Rate limiting on login endpoints via `@limiter.limit("10 per minute")` (auth.py lines 44, 98) ✓

### Template Structure
- **CONFIRMED**: Flat template structure under templates/admin/ for admin pages ✓

## Discrepancies

### API Path Prefix Discrepancy
**HIGH**: The architecture doc states (line 107):
> "Note: Endpoints are registered at root level (e.g., `/articles`, not `/api/v1/articles`)."

But the actual implementation registers `admin_api_bp` with `url_prefix="/api/v1"` (routes/admin/__init__.py line 15).
- Actual endpoints are at `/api/v1/articles`, `/api/v1/sources`, etc.
- This is a significant discrepancy between documented and actual behavior.

### Missing `/articles` Root-Level Endpoint
The architecture doc mentions:
- `/articles` - List/create articles (root level)
- `/articles/<id>` - Article CRUD (root level)
- `/articles/<id>/pipeline` - Trigger pipeline stage (root level)

But there are no routes registered at root level for these in `admin_api_bp`. The doc appears to describe intended behavior that doesn't match implementation.

### `/metrics/prometheus` Endpoint Missing from Doc
**MEDIUM**: The actual implementation has `/api/v1/metrics/prometheus` (config.py line 60-62) which is not documented in the architecture.

### `/-webhooks/<id>/events` Has Additional `resend` Endpoint
**LOW**: Documented webhooks endpoints include `/webhooks/<id>/events` GET but not the `resend` endpoint at `/webhooks/events/<int:event_id>/resend` POST (webhooks.py line 363).

### `/-search/analytics` Not Documented
**LOW**: The `/api/v1/search/analytics` endpoint exists (search.py line 9) but is not in the architecture doc.

### `/-costs` Endpoint Not Documented  
**MEDIUM**: The `/api/v1/costs` endpoint exists (pipeline.py line 135) but is not in the architecture doc.

### `/-sources/health` Endpoint Not Documented
**MEDIUM**: The `/api/v1/sources/health` endpoint exists (pipeline.py line 161) but is not in the architecture doc.

### Additional API Endpoints Not in Architecture Doc
**MEDIUM**: Several additional admin API endpoints exist but are not documented:
- `/api/v1/articles/ids` (articles.py line 151)
- `/api/v1/articles/counts-by-status` (articles.py line 170)
- `/api/v1/webhooks/events/<int:event_id>/resend` (webhooks.py line 363)

## Discrepancies - Template Structure

### Document Mentions `/share/<platform>/<article_id>` as Not Implemented
**CONFIRMED**: The note at line 75 in the doc correctly states this is not implemented as a server endpoint — social sharing is handled client-side.

### Template Files Not Listed
The doc mentions these templates but they were not verified against actual files:
- `admin/dashboard.html`, `admin/articles.html`, `admin/article_edit.html`
- `admin/sources.html`, `admin/newsletters.html`
- `admin/partials/`, `partials/`, `errors/`, `macros/`
- `article.html`, `index.html`, `share_redirect.html`
- Verification would require filesystem access

## Improvement Recommendations

1. **[HIGH]** Update architecture doc to accurately reflect that admin API endpoints use `/api/v1` prefix. The current claim that endpoints are "at root level" is incorrect.

2. **[HIGH]** Document all actual API endpoints in the architecture, including:
   - `/api/v1/costs`
   - `/api/v1/sources/health`
   - `/api/v1/metrics/prometheus`
   - `/api/v1/articles/ids`
   - `/api/v1/articles/counts-by-status`
   - `/api/v1/search/analytics`
   - `/api/v1/webhooks/events/<id>/resend`

3. **[MEDIUM]** Add missing endpoints to the architecture or add a note that these routes exist but are not documented. Decide if they should be part of the official API surface.

4. **[MEDIUM]** Consider whether root-level admin endpoints (without `/api/v1` prefix) should exist for browser-based admin access. If so, document which routes are available at root level vs under `/api/v1/`.

5. **[LOW]** Add a section explaining the blueprint structure — `admin_bp` at `/admin` for HTML pages, `admin_api_bp` at `/api/v1` for JSON API endpoints.

6. **[LOW]** Document the `@require_auth` decorator behavior — it supports both session-based and token-based authentication.

## Bugs Found

### 1. API Token Registration Bug
**File**: `routes/admin/api_tokens.py` lines 9, 13, 30, 66
**Severity**: MEDIUM
**Description**: The `api_tokens_bp` blueprint is created with `url_prefix=None` (implicit), but the routes use absolute paths like `/api-tokens`. However, the blueprint is never registered with the Flask app in `app.py`'s `_register_blueprints()` function. Only `admin_bp` and `admin_api_bp` are registered.

```python
api_tokens_bp = Blueprint("api_tokens", __name__)  # No url_prefix
# Routes like "/api-tokens" are absolute paths
```

This means:
- `GET /api-tokens` → 404 (not found)
- `POST /api-tokens` → 404 (not found)
- `DELETE /api-tokens/<id>` → 404 (not found)

The routes are defined but never accessible because the blueprint was never registered in `_register_blueprints()`.

### 2. API Token Uses Different Auth Mechanism
**File**: `routes/admin/api_tokens.py`
**Severity**: LOW
**Description**: The `api_tokens_bp` uses `@require_auth` decorator which redirects to login page (HTML) for unauthenticated requests. This is inappropriate for API token management which should return JSON 401 responses. Compare with `admin_api_bp` routes which properly return `{"error": "Invalid API token"}` for token auth failures.

### 3. Missing URL Validation in subscribe.py
**File**: `routes/public/subscribe.py`
**Severity**: LOW
**Description**: The subscribe route accepts `newsletter_type` from request form without URL validation. While there's sanitization, the architecture doc mentions SSRF protection at the adapter layer, but subscribe doesn't use `services.url.validate_url_safe`. However, since this is subscription email handling (not URL fetching), this may be intentional.

### 4. Token Format Validation Present But Auth Endpoint Missing
**File**: `routes/public/subscribe.py`
**Severity**: LOW
**Description**: Token format validation exists (`_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")`) for unsubscribe/verify tokens, but there's no endpoint to actually generate or manage these tokens from the public API. The tokens are generated server-side only.

## Layer Violations

### No Major Layer Violations Found

The routes module follows proper layering:
- Routes import from `routes/` (shared utilities) and `routes/admin/` (blueprint definitions)
- Routes import from `models/` for database access
- Routes import from `services/` for business logic (email, audit, etc.)
- Routes import from `schemas/` for validation (pydantic models)
- Routes import from `extensions/` for db, csrf, limiter
- Adapters are not imported by routes (proper direction)

### Minor Observations

1. **`routes/admin/__init__.py` imports sub-modules at bottom of file** (lines 306-350): This is a workaround to avoid circular imports since the sub-modules need to import `admin_bp` and `admin_api_bp` from `routes.admin`. This pattern is acceptable given the circular dependency structure.

2. **`routes/admin/api/__init__.py`** imports all API sub-modules to register routes with the blueprint. This is correct — the `admin_api_bp` is created in `routes/admin/__init__.py` and then sub-modules import it to add their routes.

3. **`services.url.validate_url_safe` is imported by admin API routes** (e.g., sources.py line 71, webhooks.py line 111): This is correct usage — SSRF protection utility is appropriately used in admin API for validating user-provided URLs.

## Summary

The routes module implementation is largely correct and follows the documented architecture with the following exceptions:
1. **Critical bug**: `api_tokens_bp` is never registered in app.py
2. **High discrepancy**: Admin API uses `/api/v1/` prefix but doc claims root-level
3. **Missing documentation**: Several actual endpoints are not documented

The security features (TOTP, session hijacking protection, login lockout, CSRF) are all properly implemented as documented.

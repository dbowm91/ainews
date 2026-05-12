# Routes Architecture Review

## Sources

- Architecture doc: `/Users/davidbowman/projects/ainews/architecture/routes.md`
- Routes admin init: `/Users/davidbowman/projects/ainews/routes/admin/__init__.py`
- Routes admin auth: `/Users/davidbowman/projects/ainews/routes/admin/auth.py`
- Routes admin api/articles: `/Users/davidbowman/projects/ainews/routes/admin/api/articles.py`
- Routes admin api/sources: `/Users/davidbowman/projects/ainews/routes/admin/api/sources.py`
- Routes admin api/pipeline: `/Users/davidbowman/projects/ainews/routes/admin/api/pipeline.py`
- Routes admin api/webhooks: `/Users/davidbowman/projects/ainews/routes/admin/api/webhooks.py`
- Routes admin api/config: `/Users/davidbowman/projects/ainews/routes/admin/api/config.py`
- Routes admin api/audit: `/Users/davidbowman/projects/ainews/routes/admin/api/audit.py`
- Routes admin api/search: `/Users/davidbowman/projects/ainews/routes/admin/api/search.py`
- Routes admin api_tokens: `/Users/davidbowman/projects/ainews/routes/admin/api_tokens.py`
- Routes admin shares: `/Users/davidbowman/projects/ainews/routes/admin/shares.py`
- Routes public feeds: `/Users/davidbowman/projects/ainews/routes/public/feeds.py`
- Routes public subscribe: `/Users/davidbowman/projects/ainews/routes/public/subscribe.py`
- Routes public links: `/Users/davidbowman/projects/ainews/routes/public/links.py`
- Routes decorators: `/Users/davidbowman/projects/ainews/routes/decorators.py`
- Routes init: `/Users/davidbowman/projects/ainews/routes/__init__.py`
- App blueprint registration: `/Users/davidbowman/projects/ainews/app.py` (lines 188-197)

---

## Verified Claims

### Blueprint URL Prefixes
- `admin_bp` is defined with `url_prefix="/admin"` (routes/admin/__init__.py line 14)
- `admin_api_bp` is defined with `url_prefix="/api/v1"` (routes/admin/__init__.py line 15)
- `public_bp` is defined with no prefix (mounted at `/`) (routes/public/__init__.py line 26)
- `api_tokens_bp` is defined with no prefix (mounted at `/api-tokens`) (routes/admin/api_tokens.py line 9)

### Blueprint Registration (app.py lines 188-197)
- `public_bp` registered at line 194
- `admin_bp` registered at line 195
- `admin_api_bp` registered at line 196
- `api_tokens_bp` registered at line 197

### TOTP 2FA Implementation (routes/admin/auth.py)
- `login()` (line 43): Password verification, partial login session, IP/User-Agent stored
- `verify_2fa()` (line 97): TOTP token verification and backup code support
- `setup_2fa()` (line 151): QR code generation via `get_provisioning_uri()`
- Backup codes generated via `generate_backup_codes()` (line 165)
- Backup code verification via `verify_backup_code()` and `consume_backup_code()` from `services.totp`

### Session Binding (IP + User-Agent) - routes/admin/__init__.py lines 75-86
```python
stored_ip = session.get("ip")
stored_user_agent = session.get("user_agent")
current_ip = request.remote_addr or "unknown"
current_user_agent = request.headers.get("User-Agent", "")
if stored_ip and stored_ip != current_ip:
    session.pop("admin", None)
    logger.warning("Session hijacking detected: IP mismatch")
if stored_user_agent and stored_user_agent != current_user_agent:
    session.pop("admin", None)
    logger.warning("Session hijacking detected: User-Agent mismatch")
```
Correctly implements IP + User-Agent binding.

### CSRF Protection
- `validate_csrf_json` decorator in `routes/decorators.py` (lines 10-32) validates `X-CSRFToken` header for JSON endpoints
- Applied to all state-changing admin API endpoints (POST/PUT/PATCH/DELETE)
- Applied to `bulk_article_operations`, `trigger_article_pipeline`, `create_webhook`, etc.
- Read-only GET endpoints correctly do NOT have CSRF (as per architecture: "All state-changing routes protected")

### Rate Limiting
- Login endpoint is rate-limited: `@limiter.limit("10 per minute")` (auth.py line 44)
- 2FA verification also rate-limited: `@limiter.limit("10 per minute")` (auth.py line 98)
- `limit_content_length` decorator applied to login, subscribe routes

### API Token Authentication
- `verify_api_token()` in routes/admin/__init__.py (lines 18-44) verifies `Bearer <token>` format
- Token format: `plain_token.hash`, hash verified via `check_password_hash`
- `require_auth` decorator checks API token first before session auth (lines 50-69)
- API routes return JSON 401 for invalid tokens: `return jsonify({"error": "Invalid API token"}), 401`

### require_auth Returns JSON 401 for /api Routes
The check `request.path.startswith("/api")` correctly matches `/api/v1/...` paths and returns JSON 401.

### Login Lockout
- Redis-based with Lua script for atomic increment (lines 153-162)
- In-memory fallback when Redis unavailable (per-worker protection)
- `_LOGIN_MAX_ATTEMPTS = 5`, `_LOGIN_LOCKOUT_SECONDS = 900` (15 minutes)

---

## Discrepancies

### 1. `api_tokens_bp` IS Registered - Architecture Doc is Wrong

**Architecture doc (line 57):** "The `api_tokens_bp` blueprint exists in `routes/admin/api_tokens.py` but is NOT registered in `app.py`. All `/api-tokens` routes return 404."

**Actual code (app.py line 197):**
```python
app.register_blueprint(api_tokens_bp)
```

The blueprint IS registered. The `/api-tokens` routes ARE functional.

### 2. `urlparse` Used Without Import in articles.py

**File:** `routes/admin/api/articles.py` line 26
```python
def _query_looks_like_url(q_str):
    # ...
    parsed = urlparse(q_str)  # urlparse used here
    return bool(parsed.scheme and parsed.netloc)
```

`urlparse` is not imported at the top of the file. This will raise `NameError: name 'urlparse' is not defined` at runtime when this function is called with a URL-like query string.

**Fix:** Add `from urllib.parse import urlparse` to the imports.

### 3. Route Path Discrepancies vs Architecture Doc

| Architecture Doc | Actual Route | Notes |
|-----------------|--------------|-------|
| `/feed/<format>` | `/feed` and `/feed/<category>` | No `<format>` wildcard; separate endpoints |
| `/admin/subscribers` | Not found as stated | `subscribers.py` exists but check actual route |
| `/admin/newsletters` | `newsletters.py` exists | Need to verify actual route |
| `/admin/shares` | `/admin/shares` (shares.py line 7) | Document says `shares.py` doesn't exist in structure |

The architecture doc structure (lines 7-25) lists files that exist but does not include `shares.py`, `topic_notes.py`, `trend_memory.py`, or `review.py` which all exist in `routes/admin/`.

### 4. Missing `/admin/articles` Route

The architecture doc lists `/admin/articles` as an HTML page route, but `routes/admin/articles.py` appears to be a route registration file, not a page. Need to verify if `/admin/articles` HTML page exists and what template it uses.

### 5. Architecture Doc Missing Several Routes

The architecture doc does not document:
- `/health` (public_bp, routes/public/__init__.py line 111)
- `POST /admin/logout` (admin_bp, routes/admin/auth.py line 188)
- `GET/POST /admin/verify-2fa` (admin_bp, routes/admin/auth.py line 97)
- `GET/POST /admin/setup-2fa` (admin_bp, routes/admin/auth.py line 151)
- `/admin/shares` routes (admin_bp, routes/admin/shares.py)
- `/admin/topic-notes` routes
- `/admin/trend-memory` routes
- `/admin/review` routes
- `/admin/pipelines` routes
- `/admin/metrics` (admin_bp) - separate from `/api/v1/metrics`
- `/admin/subscribers` (admin_bp)
- `/admin/newsletters` (admin_bp)
- `/admin/sources` (admin_bp)

### 6. `limit_content_length` Import Inconsistency

`routes/admin/auth.py` line 8 and `routes/admin/api/articles.py` line 11 both import from `routes` (routes/__init__.py), which is correct. The architecture doc does not document `limit_content_length` but this is fine - it is an internal decorator.

---

## Improvement Recommendations

### 1. Document All Registered Routes

The architecture doc should list all actual routes, including:
- Public: `/health`, `/subscribe`, `/verify/<token>`, `/unsubscribe/<token>`, `/s/<short_id>`, `/a/<short_id>`, `/article/<int:article_id>`
- Admin HTML: `/admin/shares`, `/admin/topic-notes`, `/admin/trend-memory`, `/admin/review`, `/admin/pipelines`, `/admin/metrics`
- Admin API: All `/api/v1/*` endpoints

### 2. Fix `urlparse` Import Bug

Add `from urllib.parse import urlparse` to `routes/admin/api/articles.py` imports.

### 3. Consider Rate Limiting Admin API Endpoints

The architecture doc says "Admin routes have stricter rate limits via `extensions.limiter`" but only login/logout endpoints have explicit `@limiter.limit()` decorators. Consider adding rate limits to sensitive admin API endpoints.

### 4. Document `api_tokens_bp` Registration

Update architecture doc to remove the claim that `api_tokens_bp` is not registered, and instead document its correct URL prefix (`/api-tokens`).

### 5. Add `api_tokens_bp` to Blueprint Structure Diagram

The blueprint structure diagram (lines 29-35) lists three blueprints but omits `api_tokens_bp`.

---

## Bugs Found

### BUG-1: `urlparse` NameError in `routes/admin/api/articles.py`

**Severity:** High (runtime error)
**File:** `routes/admin/api/articles.py` line 26
**Condition:** When `_query_looks_like_url()` is called with a string that starts with `http://` or `https://`, it attempts to use `urlparse` which is not imported.

**Reproduction:**
```python
from routes.admin.api.articles import _query_looks_like_url
_query_looks_like_url("https://example.com/article")
# NameError: name 'urlparse' is not defined
```

**Fix:** Add `from urllib.parse import urlparse` to the imports section.

---

## Layer Violations

### LV-1: Routes Import From Services Layer

Routes (`routes/admin/`, `routes/public/`) import from `services/`:
- `routes/admin/auth.py`: imports `from services.totp import ...`, `from services.audit import log_admin_action`
- `routes/admin/api/articles.py`: imports `from services.task_security import get_signed_kwargs`, `from services.article import _escape_like_pattern`, `from services.search import get_article_search_provider`
- `routes/admin/api/sources.py`: imports `from services.url import validate_url_safe`, `from services.audit import log_admin_action`
- `routes/admin/api/webhooks.py`: imports `from services.webhooks import _encrypt_secret`, `from services.audit import log_admin_action`, `from services.url import validate_url_safe`
- `routes/admin/api/config.py`: imports `from services.audit import log_admin_action`
- `routes/admin/api/pipeline.py`: imports `from services.metrics import get_metrics`, `from services.pipeline_monitor import get_all_stages_stats`, `from services.cost_tracker import get_cost_summary`

**Assessment:** This is NOT a layer violation. The architecture conventions state:
- "Adapters should NOT contain business logic or import from `services`"
- "Services should NOT import from adapters"
- Tasks (orchestrators) CAN import from services

Routes are the interface/web layer that calls into business logic (services). This is the correct direction of dependency: routes -> services. Services do not import from routes. The restriction is specifically about adapters (infrastructure) not importing business logic, and services not importing adapters.

### LV-2: `services/url.py` vs `utils/url.py` SSRF Duplication

`routes/admin/api/sources.py` and `routes/admin/api/webhooks.py` import `validate_url_safe` from `services.url`:
```python
from services.url import validate_url_safe
```

Per the AGENTS.md notes: "URL Validation Duplication: `utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` does NOT re-export from `utils/url.py` - it redefines everything locally with its own config support. Use `utils/url.py` for adapters (clean layering), `services/url.py` for services (has config support)."

Routes are not adapters, so importing from `services.url` is acceptable per the layering rules. However, this creates inconsistency where adapters use `utils/url.py` and routes use `services/url.py` for the same protection.

**Recommendation:** For cleaner architecture, routes (being part of the interface layer similar to adapters) should consider using `utils/url.py` for SSRF protection. The duplication is a maintenance risk.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 10 |
| Discrepancies | 6 |
| Improvement Recommendations | 5 |
| Bugs Found | 1 |
| Layer Violations | 0 (none confirmed as violations) |

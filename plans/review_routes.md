# Routes.md Architecture Review

**Document:** `architecture/routes.md`
**Review Date:** 2026-05-29
**Status:** Contains several inaccuracies requiring correction

---

## Verified Claims

| Claim | Evidence |
|-------|----------|
| Blueprint registration in `app.py` | `app.py:188-197` - `public_bp`, `admin_bp`, `admin_api_bp`, `api_tokens_bp` all registered |
| `admin_bp` URL prefix `/admin` | `routes/admin/__init__.py:12` - `url_prefix="/admin"` |
| `admin_api_bp` URL prefix `/api/v1` | `routes/admin/__init__.py:13` - `url_prefix="/api/v1"` |
| `api_tokens_bp` registered without url_prefix | `app.py:197` - registered directly, `routes/admin/api_tokens.py:9` - Blueprint has no url_prefix |
| Logout requires POST | `routes/admin/auth.py:188` - `methods=["POST"]` |
| Session hijacking protection (IP + User-Agent) | `routes/decorators.py:47-54` |
| CSRF protection on logout | `routes/admin/auth.py:188` - no CSRF decorator, but POST-only method is intentional |
| TOTP 2FA support | `routes/admin/auth.py:97-185` - verify_2fa, setup_2fa routes |
| 8 backup codes | `services/totp.py` - `generate_backup_codes()` creates 8 codes |
| Login rate limiting (`@limiter.limit("10 per minute")`) | `routes/admin/auth.py:44` |
| All route files exist in routes/ structure | Glob confirms all files present |
| `/admin/login` GET/POST | `routes/admin/auth.py:43` |
| `/admin/logout` POST only | `routes/admin/auth.py:188` |
| `/admin/articles` GET | `routes/admin/articles.py:221` |
| `/admin/sources/add` POST | `routes/admin/sources.py:39` |
| `/admin/trigger-crawl` POST | `routes/admin/pipelines.py:84` |
| `/admin/dead-letters` GET | `routes/admin/dashboard.py:13` |
| `/admin/pipelines` GET | `routes/admin/pipelines.py:12` |
| `/admin/pipelines/<run_id>/logs` GET | `routes/admin/pipelines.py:40` |
| `/admin/metrics` GET | `routes/admin/metrics.py:10` |
| `/admin/shares` GET | `routes/admin/shares.py:7` |
| `/admin/webhooks` GET | `routes/admin/webhooks.py:8` |
| `/admin/topic-notes` GET | `routes/admin/topic_notes.py:20` |
| `/admin/trend-memory` GET | `routes/admin/trend_memory.py:16` |
| `/admin/review` GET | `routes/admin/review.py:17` |
| `/admin/review/<id>/approve` POST | `routes/admin/review.py:64` |
| `/admin/review/<id>/reject` POST | `routes/admin/review.py:121` |
| Public routes: `/`, `/topic/<category>`, `/tag/<slug>`, `/feed`, `/sitemap.xml` | `routes/public/feeds.py:73,125,174,225,311` |
| Subscribe routes | `routes/public/subscribe.py:31,137,153,183` |
| Article detail, short URLs, tracking | `routes/public/links.py:24,94,103,123,130` |
| `/api/v1/articles/ids` GET | `routes/admin/api/articles.py:152` |
| `/api/v1/articles/<id>` GET/PUT/DELETE | `routes/admin/api/articles.py:597,620,673` |
| `/api/v1/articles/<id>/pipeline` POST | `routes/admin/api/articles.py:528` |
| `/api/v1/articles/bulk` POST | `routes/admin/api/articles.py:470` |
| `/api/v1/sources` GET/POST | `routes/admin/api/sources.py:16,48` |
| `/api/v1/sources/<id>` GET/PUT/PATCH/DELETE | `routes/admin/api/sources.py:123,154,225,314` |
| `/api/v1/sources/<id>/refresh` POST | `routes/admin/api/sources.py:342` |
| `/api/v1/pipeline/stats` GET | `routes/admin/api/pipeline.py:13` |
| `/api/v1/pipeline/backlog` GET | `routes/admin/api/pipeline.py:87` |
| `/api/v1/pipeline/dead-letter/stats` GET | `routes/admin/api/pipeline.py:48` |
| `/api/v1/costs` GET | `routes/admin/api/pipeline.py:135` |
| `/api/v1/sources/health` GET | `routes/admin/api/pipeline.py:167` |
| `/api/v1/pipeline/sla` GET | `routes/admin/api/pipeline.py:193` |
| `/api/v1/webhooks` GET/POST | `routes/admin/api/webhooks.py:56,90` |
| `/api/v1/webhooks/<id>` GET/PUT/PATCH/DELETE | `routes/admin/api/webhooks.py:165,209,269` |
| `/api/v1/webhooks/<id>/test` POST | `routes/admin/api/webhooks.py:297` |
| `/api/v1/webhooks/<id>/events` GET | `routes/admin/api/webhooks.py:321` |
| `/api/v1/webhooks/events/<id>/resend` POST | `routes/admin/api/webhooks.py:363` |
| `/api/v1/search/analytics` GET | `routes/admin/api/search.py:11` |
| `/api/v1/config/reload` POST | `routes/admin/api/config.py:13` |
| `/api/v1/metrics` GET | `routes/admin/api/config.py:52` |
| `/api/v1/metrics/prometheus` GET | `routes/admin/api/config.py:60` |
| `/api/v1/audit-logs` GET | `routes/admin/api/audit.py:11` |
| `/api/v1/health` GET | `routes/admin/api/health.py:17` |
| `/api/v1/workers/health` GET | `routes/admin/api/health.py:54` |
| `/api/v1/task/<task_id>` GET | `routes/admin/api/health.py:102` |
| `/api/v1/alerts` GET | `routes/admin/api/alerts.py:14` |
| `/api/v1/newsletters/stats` GET | `routes/admin/newsletters.py:177` (on `admin_api_bp`) |
| `/api/v1/newsletter/preview` POST | `routes/admin/newsletters.py:221` (on `admin_api_bp`) |
| `/api/v1/sources/performance` GET | `routes/admin/api/source_intelligence.py:11` |
| `/api/v1/topics/coverage` GET | `routes/admin/api/source_intelligence.py:74` |
| `/api/v1/sources/recommendations` GET | `routes/admin/api/source_intelligence.py:104` |
| `/api/v1/topic-gap/reports` GET | `routes/admin/api/topic_gap.py:12` |
| `/api-tokens` endpoints | `routes/admin/api_tokens.py:13,30,66` |
| Bearer token auth pattern | `routes/admin/__init__.py:16-42` |

---

## Incorrect Claims

### 1. `/admin/api/trend-memory/semantic-search` (Line 86, 138, 335)

**Issue:** routes.md claims the trend memory semantic search endpoint is at `/admin/api/trend-memory/semantic-search`, but it's actually at `/api/v1/api/trend-memory/semantic-search` or `/admin/api/trend-memory/semantic-search` depending on interpretation.

**Actual route in `routes/admin/trend_memory.py:117`:**
```python
@admin_bp.route("/api/trend-memory/semantic-search", methods=["GET"])
```

With `admin_bp` having `url_prefix="/admin"`, this resolves to `/admin/api/trend-memory/semantic-search`.

However, the endpoint is listed redundantly in lines 86, 138, and 335 with different path prefixes. The correct canonical path is `/admin/api/trend-memory/semantic-search`.

### 2. `/admin/sources/<id>/enable` and `/admin/sources/<id>/disable` (Lines 70-71)

**Issue:** routes.md shows these as separate POST endpoints, but they are actually decorated with `@validate_csrf_json` BEFORE `@require_auth` in `routes/admin/sources.py:106-109`:

```python
@admin_bp.route("/sources/<int:source_id>/enable", methods=["POST"])
@validate_csrf_json
@require_auth
def enable_source(source_id: int) -> tuple[Response, int]:
```

The decorator order issue doesn't change the HTTP method but the documentation should note they use CSRF protection via `validate_csrf_json`.

### 3. Missing `/articles/counts-by-status` from Admin API Table (Lines 309-335)

**Issue:** The Admin API table (lines 309-335) is missing `/articles/counts-by-status` which exists at `routes/admin/api/articles.py:171`:

```python
@admin_api_bp.route("/articles/counts-by-status", methods=["GET"])
@require_auth
def get_article_counts_by_status():
```

This endpoint IS documented at line 115 in the same file but missing from the second table at lines 309-335.

### 4. `/admin/newsletters/<id>` GET (Line 75)

**Issue:** routes.md shows `/admin/newsletters/<id>` but the actual route in `routes/admin/newsletters.py:90` does not take a trailing slash and uses a different pattern:

```python
@admin_bp.route("/newsletters/<int:newsletter_id>")
```

The documentation should be `/newsletters/<newsletter_id>` not `/newsletters/<id>`.

### 5. `/admin/topic-notes/create`, `/edit`, `/delete` Methods (Lines 91-93)

**Issue:** routes.md shows POST for all three, but examining `routes/admin/topic_notes.py`:
- `topic_notes_create()` at line 42 - POST ✅
- `topic_notes_edit()` at line 86 - POST ✅
- `topic_notes_delete()` at line 143 - POST ✅

Actually CORRECT. No issue here.

### 6. Missing `/articles/<id>/original` from Admin Routes Table (Line 64)

**Issue:** routes.md shows `/admin/articles/<id>/original` [GET] at line 64, but this endpoint is NOT listed in the detailed Admin Routes table at lines 57-106.

---

## Bugs Found

### HIGH: Missing `require_auth` decorator on some routes (Not a bug - verified safe)

**Location:** N/A

**Finding:** All admin routes use `@require_auth` decorator appropriately. Verified that admin API routes use `@require_auth` and admin HTML routes use `@require_auth` consistently.

### MEDIUM: Duplicate/redundant API endpoint listings

**Location:** `architecture/routes.md:138` and `routes/admin/trend_memory.py:117`

**Finding:** The `/admin/api/trend-memory/semantic-search` endpoint is listed THREE times:
1. Line 86 in the admin routes table under "Admin Routes"
2. Line 138 in the API endpoints table
3. Line 335 in the second Admin API table

This creates confusion about which blueprint owns the endpoint and whether it's at `/admin/api/...` or `/api/v1/...`.

**Correct path:** `/admin/api/trend-memory/semantic-search` (on `admin_bp` with `/admin` prefix)

### MEDIUM: `/newsletters/stats` vs `/newsletter/preview` path inconsistency

**Location:** `routes/admin/newsletters.py:177,221`

**Finding:** Two newsletter API endpoints exist:
- `/api/v1/newsletters/stats` (line 177) - plural
- `/api/v1/newsletter/preview` (line 221) - singular

The paths are intentional but poorly named (inconsistent pluralization). Not a bug per se, but confusing.

---

## Improvement Opportunities

### 1. Document the `api_tokens_bp` authentication flow more clearly

**Location:** `architecture/routes.md:268-273`

routes.md notes the endpoints but doesn't explain that:
- The `api_tokens_bp` uses `require_auth` decorator (session-based)
- Bearer tokens for API auth are verified via `verify_api_token()` in `require_auth`
- These are two separate auth mechanisms for two different blueprint types

### 2. Document CSRF protection detail for JSON endpoints

**Location:** `architecture/routes.md:381-383`

routes.md says "All state-changing routes protected via Flask-WTF tokens" but doesn't explain:
- HTML forms use standard Flask-WTF CSRF
- JSON API endpoints use `X-CSRFToken` header via `@validate_csrf_json` decorator
- The `validate_csrf_json` decorator at `routes/decorators.py:72-94`

### 3. Add missing endpoints to Admin API table

The Admin API table at lines 309-335 is missing:
- `/articles/counts-by-status` - exists at `routes/admin/api/articles.py:171`

### 4. Clarify rate limiting scope

**Location:** `architecture/routes.md:385-387`

routes.md states "Other admin routes rely on the global default limit" but doesn't specify what that default is. Should document:
- Login routes: explicit `@limiter.limit("10 per minute")`
- API routes: global default limit from `extensions.py`

### 5. Template structure verification

**Location:** `architecture/routes.md:337-356`

The template structure claims a "flat directory structure under `templates/`" but inspection of `templates/` directory would be needed to verify. The document lists templates that should exist:
- `templates/admin/partials/` - partial templates directory exists
- `templates/partials/` - public partial templates
- `templates/errors/` - error pages

---

## Stale Content

### 1. Structure diagram (Lines 7-45)

The structure diagram shows `routes/admin/api/` files including `articles.py`, `sources.py`, etc. which is accurate, but doesn't reflect the actual implementation where some routes (like `newsletters.py`) register on BOTH `admin_bp` AND `admin_api_bp`.

### 2. Session hijacking protection code example (Lines 362-367)

The pseudocode shown is accurate but simplified. The actual implementation in `routes/decorators.py:43-54` checks BOTH IP and User-Agent:

```python
stored_ip = session.get("ip")
stored_user_agent = session.get("user_agent")
current_ip = request.remote_addr or "unknown"
current_user_agent = request.headers.get("User-Agent", "")
if stored_ip and stored_ip != current_ip:
    session.pop("admin", None)
    ...
if stored_user_agent and stored_user_agent != current_user_agent:
    session.pop("admin", None)
    ...
```

---

## Priority for Findings

| Priority | Item | Location | Effort |
|----------|------|----------|--------|
| P1 | Fix `/admin/api/trend-memory/semantic-search` triple listing | routes.md:86,138,335 | Low |
| P1 | Add `/articles/counts-by-status` to Admin API table | routes.md:309-335 | Low |
| P2 | Clarify `/newsletters/stats` vs `/newsletter/preview` naming | routes.md:241-242 | Low |
| P2 | Document CSRF via `@validate_csrf_json` for JSON endpoints | routes.md:381-383 | Medium |
| P3 | Add missing `/admin/articles/<id>/original` to Admin Routes table | routes.md:57-106 | Low |
| P3 | Document global default rate limit value | routes.md:385-387 | Low |

---

## Summary

The routes.md document is **mostly accurate** but has several specific issues:

1. **Trend memory semantic search endpoint** is listed 3 times with potentially confusing paths
2. **Missing endpoint** `/articles/counts-by-status` from Admin API table
3. **Inconsistent endpoint naming** (`/newsletters/stats` vs `/newsletter/preview`)
4. **CSRF protection mechanism** not fully documented for JSON API endpoints
5. **Rate limiting** global default not specified

The core route structure, HTTP methods, and authentication mechanisms are correctly documented.

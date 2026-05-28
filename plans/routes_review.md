# Routes Architecture Documentation Review

Review of `architecture/routes.md` against actual codebase.

## Verified Claims

### Blueprint Structure (Mostly Correct)
- **public_bp** at `/` — Confirmed at `routes/public/__init__.py:26`
- **admin_bp** at `/admin` — Confirmed at `routes/admin/__init__.py:12`
- **admin_api_bp** at `/api/v1` — Confirmed at `routes/admin/__init__.py:13`
- **api_tokens_bp** registered in `app.py` — Confirmed at `app.py:197`

### Admin Routes Table (All Present Routes Confirmed)
All routes listed in the admin routes table exist in code with correct methods:
- `/admin/login` [GET/POST] — `routes/admin/auth.py:43`
- `/admin/` [GET] — `routes/admin/dashboard.py:192`
- `/admin/articles` [GET] — `routes/admin/articles.py:221`
- `/admin/articles/<id>/edit` [GET/POST] — `routes/admin/articles.py:385`
- `/admin/articles/<id>/original` [GET] — `routes/admin/articles.py:426`
- `/admin/articles/<id>/versions` [GET] — `routes/admin/articles.py:440`
- `/admin/articles/<id>/versions/<version_id>/rollback` [POST] — `routes/admin/articles.py:458`
- `/admin/articles/<id>/delete` [POST] — `routes/admin/articles.py:505`
- `/admin/articles/<id>/reprocess` [POST] — `routes/admin/articles.py:534`
- `/admin/sources` [GET] — `routes/admin/sources.py:26`
- `/admin/sources/<id>/enable` [POST] — `routes/admin/sources.py:106`
- `/admin/sources/<id>/disable` [POST] — `routes/admin/sources.py:142`
- `/admin/subscribers` [GET] — `routes/admin/subscribers.py:7`
- `/admin/subscribers/export` [GET] — `routes/admin/subscribers.py:51`
- `/admin/newsletters` [GET] — `routes/admin/newsletters.py:70`
- `/admin/newsletters/<id>` [GET] — `routes/admin/newsletters.py:90`
- `/admin/newsletters/generate` [POST] — `routes/admin/newsletters.py:100`
- `/admin/newsletters/dry-run` [POST] — `routes/admin/newsletters.py:126`
- `/admin/dead-letters` [GET] — `routes/admin/dashboard.py:13`
- `/admin/pipelines` [GET] — `routes/admin/pipelines.py:12`
- `/admin/pipelines/<run_id>/logs` [GET] — `routes/admin/pipelines.py:40`
- `/admin/review` [GET] — `routes/admin/review.py:17`
- `/admin/review/<id>/approve` [POST] — `routes/admin/review.py:64`
- `/admin/review/<id>/reject` [POST] — `routes/admin/review.py:121`
- `/admin/topic-notes` [GET] — `routes/admin/topic_notes.py:20`
- `/admin/topic-notes/create` [POST] — `routes/admin/topic_notes.py:42`
- `/admin/topic-notes/edit` [POST] — `routes/admin/topic_notes.py:86`
- `/admin/topic-notes/delete` [POST] — `routes/admin/topic_notes.py:143`
- `/admin/topic-notes/row/<topic>` [GET] — `routes/admin/topic_notes.py:172`
- `/admin/webhooks` [GET] — `routes/admin/webhooks.py:8`
- `/admin/shares` [GET] — `routes/admin/shares.py:7`
- `/admin/shares/<id>/edit-form` [GET] — `routes/admin/shares.py:142`
- `/admin/shares/<id>/row` [GET] — `routes/admin/shares.py:152`
- `/admin/shares/add` [POST] — `routes/admin/shares.py:16`
- `/admin/shares/<id>/edit` [POST] — `routes/admin/shares.py:68`
- `/admin/shares/<id>/delete` [POST] — `routes/admin/shares.py:119`
- `/admin/shares/<id>/toggle` [POST] — `routes/admin/shares.py:162`
- `/admin/metrics` [GET] — `routes/admin/metrics.py:10`
- `/admin/verify-2fa` [GET/POST] — `routes/admin/auth.py:97`
- `/admin/setup-2fa` [GET/POST] — `routes/admin/auth.py:151`
- `/admin/logout` [POST] — `routes/admin/auth.py:188`

### Admin API Endpoints Table (All Present Endpoints Confirmed)
All endpoints in the API table exist with correct methods:
- `/articles` [GET] — `routes/admin/api/articles.py:152` (via `/articles/ids` at line 152, and list at line 152)
- `/articles/ids` [GET] — `routes/admin/api/articles.py:152`
- `/articles/counts-by-status` [GET] — `routes/admin/api/articles.py:171`
- `/articles/<id>` [GET, PUT, DELETE] — `routes/admin/api/articles.py:597,620,673`
- `/articles/<id>/pipeline` [POST] — `routes/admin/api/articles.py:528`
- `/articles/bulk` [POST] — `routes/admin/api/articles.py:470`
- `/sources` [GET, POST] — `routes/admin/api/sources.py:16,48`
- `/sources/<id>` [GET, PUT, PATCH, DELETE] — `routes/admin/api/sources.py:123,154,225,314`
- `/sources/<id>/refresh` [POST] — `routes/admin/api/sources.py:342`
- `/sources/health` [GET] — `routes/admin/api/pipeline.py:161`
- `/pipeline/stats` [GET] — `routes/admin/api/pipeline.py:13`
- `/pipeline/backlog` [GET] — `routes/admin/api/pipeline.py:87`
- `/pipeline/dead-letter/stats` [GET] — `routes/admin/api/pipeline.py:48`
- `/pipeline/sla` [GET] — `routes/admin/api/pipeline.py:187`
- `/costs` [GET] — `routes/admin/api/pipeline.py:135`
- `/webhooks` [GET, POST] — `routes/admin/api/webhooks.py:56,90`
- `/webhooks/<id>` [GET, PUT, PATCH, DELETE] — `routes/admin/api/webhooks.py:165,209,269`
- `/webhooks/<id>/test` [POST] — `routes/admin/api/webhooks.py:297`
- `/webhooks/<id>/events` [GET] — `routes/admin/api/webhooks.py:321`
- `/webhooks/events/<id>/resend` [POST] — `routes/admin/api/webhooks.py:363`
- `/search/analytics` [GET] — `routes/admin/api/search.py:9`
- `/config/reload` [POST] — `routes/admin/api/config.py:13`
- `/metrics` [GET] — `routes/admin/api/config.py:52`
- `/metrics/prometheus` [GET] — `routes/admin/api/config.py:60`
- `/audit-logs` [GET] — `routes/admin/api/audit.py:11`
- `/health` [GET] — `routes/admin/api/health.py:17`
- `/workers/health` [GET] — `routes/admin/api/health.py:54`
- `/task/<task_id>` [GET] — `routes/admin/api/health.py:102`

### Public Routes (All Confirmed)
- `/` — `routes/public/feeds.py:73`
- `/topic/<category>` — `routes/public/feeds.py:122`
- `/tag/<slug>` — `routes/public/feeds.py:171`
- `/feed` — `routes/public/feeds.py:222`
- `/feed/<category>` — `routes/public/feeds.py:259`
- `/sitemap.xml` — `routes/public/feeds.py:308`
- `/subscribe` [POST] — `routes/public/subscribe.py:31`
- `/verify/<token>` — `routes/public/subscribe.py:183`
- `/unsubscribe/<token>` [GET] — `routes/public/subscribe.py:137`
- `/unsubscribe/<token>` [POST] — `routes/public/subscribe.py:153`
- `/article/<id>` — `routes/public/links.py:24`
- `/s/<short_id>` — `routes/public/links.py:94`
- `/a/<short_id>` — `routes/public/links.py:103`
- `/api/v1/track/share-click/<id>` [POST] — `routes/public/links.py:123`
- `/track/newsletter-click/<id>` — `routes/public/links.py:130`
- `/health` — `routes/public/__init__.py:111`

### Session Hijacking Protection (Correct Mechanism)
- IP + User-Agent binding confirmed in `routes/decorators.py:43-54`
- `session['ip']` and `session['user_agent']` checked on each request
- Mismatch triggers session clear and redirect to login

### CSRF Protection (Correct)
- `validate_csrf_json` decorator at `routes/decorators.py:72` validates `X-CSRFToken` header for JSON endpoints
- Form endpoints use Flask-WTF automatic CSRF

### API Tokens Blueprint
- Correctly documented endpoints at `/api-tokens` — confirmed at `routes/admin/api_tokens.py:13,30,66`

### Newsletter API Endpoints (Correct)
- `/api/v1/newsletters/stats` [GET] — `routes/admin/newsletters.py:177`
- `/api/v1/newsletter/preview` [POST] — `routes/admin/newsletters.py:221`

### Trend Memory Semantic Search (Path Incorrect)
- Endpoint exists at `routes/admin/trend_memory.py:117` — see Incorrect Claims below

### File Structure (Mostly Correct)
- All files listed in the structure section exist
- Minor omission: `api/utils.py` not listed (provides `api_response()` helper)

---

## Incorrect Claims

### 1. Trigger-crawl URL path is wrong
**Priority: HIGH**
**Doc says:** `/admin/pipelines/trigger-crawl` [POST]
**Actual code:** `/admin/trigger-crawl` [POST] — `routes/admin/pipelines.py:84`
**Impact:** Anyone following the doc would call the wrong URL. The route is on `admin_bp` directly, not nested under `/pipelines`.

### 2. Trend memory semantic search path is wrong
**Priority: HIGH**
**Doc says:** `/api/trend-memory/semantic-search` [GET]
**Actual code:** `/admin/api/trend-memory/semantic-search` [GET] — `routes/admin/trend_memory.py:117`
**Impact:** The endpoint is on `admin_bp` (prefix `/admin`), not on `admin_api_bp` (prefix `/api/v1`). Full path is `/admin/api/trend-memory/semantic-search`, missing the `/admin` prefix in the doc.

### 3. Session hijacking pseudocode uses wrong key name
**Priority: MEDIUM**
**Doc says:** `session['ua'] != request.ua`
**Actual code:** `session['user_agent']` — `routes/decorators.py:44,46`
**Impact:** Misleading for developers reading the doc. The actual key is `user_agent`, not `ua`.

### 4. Rate limiting claim is misleading
**Priority: MEDIUM**
**Doc says:** "Admin routes have stricter rate limits via `extensions.limiter`"
**Actual code:** Only `login` and `verify-2fa` have explicit `@limiter.limit("10 per minute")` decorators — `routes/admin/auth.py:44,98`. All other admin routes rely on the global default limit.
**Impact:** Developers may assume all admin routes are rate-limited independently.

### 5. api_tokens_bp url_prefix claim is inaccurate
**Priority: LOW**
**Doc says:** "registered in `app.py` with `url_prefix="/api-tokens"`"
**Actual code:** Blueprint is defined without `url_prefix` (`routes/admin/api_tokens.py:9`). Routes include the full `/api-tokens` path. Registered in `app.py` without `url_prefix` (`app.py:197`).
**Impact:** Misleading about how the prefix is applied, though endpoints work correctly.

---

## Bugs Found

### 1. Missing `UnsafeURLError` import in `routes/admin/sources.py`
**Priority: MEDIUM**
**File:** `routes/admin/sources.py:59`
**Code:** `except UnsafeURLError as e:` but `UnsafeURLError` is never imported in this file. The import from `services.url` exists on line 56 (`from services.url import validate_url_safe`) but `UnsafeURLError` is not included.
**Impact:** `NameError` will be raised if URL validation fails. This is a runtime bug that would surface when a user tries to add a source with an unsafe URL.

### 2. Newsletter preview endpoint accepts POST but doc implies GET-like semantics
**Priority: LOW**
**Doc says:** Listed in the API table without clear method distinction
**Actual code:** `/newsletter/preview` is POST-only (`routes/admin/newsletters.py:221`)
**Impact:** Minor documentation clarity issue.

---

## Improvement Opportunities

### 1. Document missing admin routes
**Priority: HIGH**
The following routes exist in code but are NOT documented in the admin routes table:
- `/admin/sources/add` [POST] — `routes/admin/sources.py:39`
- `/admin/trend-memory` [GET] — `routes/admin/trend_memory.py:16`
- `/admin/trend-memory/` [GET] — `routes/admin/trend_memory.py:17`
- `/admin/trend-memory/delete/<id>` [POST] — `routes/admin/trend_memory.py:53`
- `/admin/trend-memory/delete-expired` [POST] — `routes/admin/trend_memory.py:85`
- `/admin/api/trend-memory/semantic-search` [GET] — `routes/admin/trend_memory.py:117`

### 2. Add `api/utils.py` to structure section
**Priority: LOW**
`routes/admin/api/utils.py` provides the `api_response()` helper used by all API endpoints. Should be listed in the structure tree.

### 3. Document CSRF protection details
**Priority: LOW**
The doc says "All state-changing routes protected via Flask-WTF tokens" but doesn't explain the two mechanisms:
- Form endpoints: Flask-WTF automatic CSRF validation
- JSON endpoints: Custom `validate_csrf_json` decorator checking `X-CSRFToken` header

### 4. Clarify public_bp health endpoint
**Priority: LOW**
The health endpoint at `/health` is on `public_bp` (no auth), while the admin API has its own `/api/v1/health` (with auth). The doc's public routes section mentions it but could clarify this distinction.

### 5. Document unsubscribe route separation
**Priority: LOW**
The doc shows `@subscribe_bp.route('/unsubscribe/<token>')` and `@subscribe_bp.route('/unsubscribe/<token>', methods=['POST'])` on the same function, but in code these are two separate functions: `unsubscribe()` (GET, line 137) and `unsubscribe_confirm()` (POST, line 153). The doc's pseudocode is misleading.

---

## Stale Content

### 1. Subscribe blueprint reference
**Priority: LOW**
The doc references `subscribe_bp` in pseudocode (`@subscribe_bp.route(...)`) but the actual code uses `public_bp` for all subscribe routes. There is no `subscribe_bp` — it's `public_bp` imported in `routes/public/subscribe.py:17`.

### 2. Duplicate endpoint table
**Priority: LOW**
The admin API endpoints are documented twice: once in the compact table (lines 100-127) and once in the detailed section (lines 199-256). The detailed section adds Health and Audit/Search subsections but the compact table already covers them. This creates maintenance burden and drift risk.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | ~70 route endpoints confirmed correct |
| Incorrect Claims | 5 (2 HIGH, 2 MEDIUM, 1 LOW) |
| Bugs Found | 2 (1 MEDIUM, 1 LOW) |
| Improvement Opportunities | 5 |
| Stale Content | 2 |

**Critical findings:**
1. Trigger-crawl path is wrong (`/admin/pipelines/trigger-crawl` → `/admin/trigger-crawl`)
2. Trend memory semantic search path is wrong (`/api/trend-memory/semantic-search` → `/admin/api/trend-memory/semantic-search`)
3. Missing `UnsafeURLError` import in `routes/admin/sources.py` is a runtime bug
4. 6 admin routes are undocumented (trend-memory CRUD, sources/add, semantic search)

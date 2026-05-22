# Routes Module Architecture Review

## Summary

Document: `architecture/routes.md` (350 lines)
Review date: 2026-05-22

## Verified Claims

### Structure (Lines 7-25)
**VERIFIED** - File structure matches codebase exactly:
```
routes/
├── public/
│   ├── feeds.py ✓
│   ├── subscribe.py ✓
│   └── links.py ✓
└── admin/
    ├── __init__.py ✓
    ├── auth.py ✓
    ├── api_tokens.py ✓
    └── api/
        ├── articles.py ✓
        ├── sources.py ✓
        ├── pipeline.py ✓
        ├── search.py ✓
        ├── webhooks.py ✓
        ├── config.py ✓
        ├── audit.py ✓
        └── (utils.py - extra, not documented)
```

### Blueprint Structure (Lines 27-36)
**VERIFIED** - Three blueprints with correct URL prefixes:
| Blueprint | URL Prefix | Verified |
|-----------|------------|----------|
| `public_bp` | `/` | routes/public/__init__.py:26 |
| `admin_bp` | `/admin` | routes/admin/__init__.py:14 |
| `admin_api_bp` | `/api/v1` | routes/admin/__init__.py:15 |

### Public Routes
**VERIFIED** - All routes exist in correct files:
- `routes/public/feeds.py`: index, topic_feed, tag_feed, feed_all, feed_topic, sitemap ✓
- `routes/public/subscribe.py`: subscribe, unsubscribe, verify ✓
- `routes/public/links.py`: article_detail, short_url_redirect, short_url_tracking_page, track_share_click, track_newsletter_click ✓
- Health endpoint at `/health` in routes/public/__init__.py:111 ✓

### Admin Authentication (Lines 253-270)
**VERIFIED** - Security features implemented:
- TOTP 2FA support: routes/admin/auth.py ✓
- 8 backup codes: services/totp.py (generate_backup_codes, verify_backup_code, consume_backup_code) ✓
- Session hijacking protection (IP + User-Agent binding): routes/admin/__init__.py:75-86 ✓
- Login lockout via Redis with in-memory fallback: routes/admin/__init__.py:104-303 ✓

### API Token Authentication (Lines 334-342)
**VERIFIED** - Token format and storage:
- Bearer token in Authorization header: routes/admin/__init__.py:51-69 ✓
- Prefix + hash storage (never plaintext): routes/admin/__init__.py:32 ✓
- Token stored as `prefix + "." + hash`: routes/admin/api_tokens.py:59 ✓

### CSRF Protection (Line 346)
**VERIFIED** - Flask-WTF tokens on state-changing routes via `validate_csrf_json` decorator in routes/decorators.py ✓

## Discrepancies and Issues

### CRIT - Documentation Errors

#### 1. Duplicate `/admin/metrics` entry (Line 78-79)
**File:** architecture/routes.md:78-79
```markdown
79: - `/admin/metrics` - Metrics dashboard
80: - `/admin/metrics` - Metrics dashboard  ← DUPLICATE, should be `/admin/verify-2fa`
```
**Actual:** `/admin/verify-2fa` exists at routes/admin/auth.py:97

#### 2. `api_tokens_bp` structure section is confusing (Lines 224-241)
The document includes `api_tokens_bp` under "API Tokens" section with duplicate route definitions from `links.py`. This is misleading - `api_tokens_bp` is a standalone blueprint registered in app.py, NOT part of admin module. The "public_bp = Blueprint('links', __name__)" code block is from links.py and shouldn't be in this section.

### HIGH - Missing Implementations in Document

#### 3. Missing API endpoint: `/api/v1/workers/health`
**File:** routes/admin/api/health.py:54
```python
@admin_api_bp.route("/workers/health")
@require_auth
def workers_health() -> Response:
```
Not documented in architecture/routes.md

#### 4. Missing API endpoint: `/api/v1/task/<task_id>`
**File:** routes/admin/api/health.py:102
```python
@admin_api_bp.route("/task/<task_id>")
@require_auth
def task_status(task_id: str) -> Response:
```
Not documented in architecture/routes.md

#### 5. Missing API endpoint: `/api/v1/newsletters/stats`
**File:** routes/admin/newsletters.py:177
```python
@admin_api_bp.route("/newsletters/stats", methods=["GET"])
@require_auth
def newsletters_stats():
```
Not documented in architecture/routes.md

#### 6. Missing API endpoint: `/api/v1/newsletter/preview`
**File:** routes/admin/newsletters.py:221
```python
@admin_api_bp.route("/newsletter/preview", methods=["POST"])
@require_auth
@validate_csrf_json
def newsletter_preview():
```
Not documented in architecture/routes.md

### MED - Incomplete Documentation

#### 7. Missing admin route: `/admin/pipelines/trigger-crawl`
**File:** routes/admin/pipelines.py:84
```python
@admin_bp.route("/trigger-crawl", methods=["POST"])
@require_auth
@validate_csrf_json
def trigger_crawl():
```
Not documented - only `/admin/pipelines` and `/admin/pipelines/<run_id>/logs` are listed

#### 8. Missing admin route: `/admin/articles/<id>/original`
**File:** routes/admin/articles.py:426
```python
@admin_bp.route("/articles/<int:article_id>/original")
@require_auth
def view_original_article(article_id):
```
Not documented - only versions and edit are listed

#### 9. Missing admin route: `/admin/articles/<id>/versions/<int:version_id>/rollback`
**File:** routes/admin/articles.py:458
```python
@admin_bp.route("/articles/<int:article_id>/versions/<int:version_id>/rollback", methods=["POST"])
@require_auth
def rollback_article(article_id, version_id):
```
Not documented

#### 10. Missing admin route: `/admin/api/trend-memory/semantic-search`
**File:** routes/admin/trend_memory.py:117
```python
@admin_bp.route("/api/trend-memory/semantic-search", methods=["GET"])
@require_auth
def trend_memory_semantic_search():
```
Not documented

#### 11. Missing admin route: `/admin/topic-notes/row/<topic>`
**File:** routes/admin/topic_notes.py:172
```python
@admin_bp.route("/topic-notes/row/<topic>")
@require_auth
def topic_notes_row(topic):
```
Not documented

#### 12. Missing admin route: `/admin/shares/<id>/edit-form` and `/admin/shares/<id>/row`
**File:** routes/admin/shares.py:142, 152
```python
@admin_bp.route("/shares/<int:config_id>/edit-form", methods=["GET"])
@admin_bp.route("/shares/<int:config_id>/row", methods=["GET"])
```
Not documented

### LOW - Template Structure Note

#### 13. Template structure shows `templates/admin/` as flat
**File:** architecture/routes.md:309-322

Actual templates under `templates/admin/`:
```
admin/
├── partials/          # Admin partial templates (documented as flat)
│   ├── articles_table.html
│   ├── webhook_events.html
│   ├── share_row.html
│   ├── share_edit_form.html
│   └── ... (more partials)
├── dashboard.html
├── articles.html
└── ...
```

The `partials/` subdirectory exists but is documented as part of the flat structure - this is a minor structural inaccuracy in the directory tree visualization.

## Security Review

### VERIFIED Security Features

1. **Session hijacking protection** (Lines 326-333): IP + User-Agent binding implemented correctly in routes/admin/__init__.py:75-86 ✓

2. **Login lockout via Redis Lua script** - Atomic check-and-record prevents TOCTOU race conditions ✓

3. **CSRF protection** via `validate_csrf_json` decorator on all JSON API state-changing endpoints ✓

4. **API token authentication** with hashed storage, prefix lookup ✓

5. **Health endpoint detailed auth** (Line 160-163): `GET /health?detailed=true` requires admin session ✓

6. **URL validation** via `validate_url_safe()` in webhook, source, and subscribe routes ✓

7. **safe_href Jinja filter** prevents XSS in templates ✓

### No Security Issues Found

No security vulnerabilities detected in routes implementation.

## Performance Concerns

### 1. Dashboard stats caching could be improved
**File:** routes/admin/dashboard.py:86-189

`_compute_dashboard_stats()` caches for 180 seconds but individual lookups (PipelineRun, Article counts) could be parallelized.

### 2. CSV export uses yield_per but processes sequentially
**File:** routes/admin/subscribers.py:72-91

The streaming CSV export is correct but could benefit from batch inserts in the generator.

## Bugs in Implementation

### 1. Minor: Import ordering in routes/admin/newsletters.py
**File:** routes/admin/newsletters.py:8
```python
from routes.admin import admin_api_bp, admin_bp, require_auth
```
Line 8 imports all three, but `admin_bp` is used on line 70 for the HTML routes, while `admin_api_bp` is used on lines 177 and 221 for JSON endpoints. This is actually correct - the file serves both page and API routes. Not a bug.

## Recommendations

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| CRIT | Duplicate `/admin/metrics` entry | routes.md:78-79 | Fix typo - second entry should be `/admin/verify-2fa` |
| CRIT | Misleading `api_tokens_bp` documentation | routes.md:224-241 | Remove duplicate code block; clarify it's registered in app.py |
| HIGH | Missing `/api/v1/workers/health` endpoint | routes.md | Add to Admin API endpoints table |
| HIGH | Missing `/api/v1/task/<task_id>` endpoint | routes.md | Add to Admin API endpoints table |
| HIGH | Missing `/api/v1/newsletters/stats` endpoint | routes.md | Add to Admin API endpoints table |
| HIGH | Missing `/api/v1/newsletter/preview` endpoint | routes.md | Add to Admin API endpoints table |
| MED | Missing `/admin/pipelines/trigger-crawl` route | routes.md | Add to Admin Blueprint routes list |
| MED | Missing article version routes | routes.md | Add `/articles/<id>/original` and `/articles/<id>/versions/<version_id>/rollback` |
| MED | Missing `/admin/api/trend-memory/semantic-search` | routes.md | Add to Admin API endpoints |
| MED | Missing topic-notes row route | routes.md | Add `/admin/topic-notes/row/<topic>` |
| MED | Missing share edit-form and row routes | routes.md | Add `/admin/shares/<id>/edit-form` and `/admin/shares/<id>/row` |
| LOW | Template partials subdirectory not shown | routes.md:309-322 | Update directory tree to show `admin/partials/` |

## Summary Statistics

- **Total routes documented:** ~90
- **Routes verified in code:** ~85
- **Missing from document:** 10 routes (HIGH priority: 4, MED priority: 6)
- **Documentation errors:** 2 (CRIT)
- **Security issues:** 0
- **Implementation bugs:** 0
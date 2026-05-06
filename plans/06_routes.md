# Routes Architecture Verification

Date: 2026-05-06
Review of: `architecture/routes.md`

## Verification Results

### Structure Claims

| Claim | Status | Notes |
|-------|--------|-------|
| `routes/public/feeds.py` exists | VERIFIED | Contains sitemap, RSS/atom feeds, topic/tag feeds |
| `routes/public/subscribe.py` exists | VERIFIED | Contains subscribe, verify, unsubscribe |
| `routes/public/links.py` exists | VERIFIED | Contains short URLs, article detail, tracking |
| `routes/admin/__init__.py` exists | VERIFIED | Dashboard, articles, sources, subscribers, newsletters, plus additional modules |
| `routes/admin/auth.py` exists | VERIFIED | Login with TOTP support |
| `routes/admin/api_tokens.py` exists | VERIFIED | API token management |
| `routes/admin/api/` subdirectory exists | VERIFIED | Contains articles, sources, pipeline, search, webhooks, config, audit, health |

**DISCREPANCY**: Document claims `articles.py` is in `routes/admin/` top-level but it is actually in `routes/admin/api/articles.py`.

### Public Feeds Routes

| Route | Documented | Actual | Status |
|-------|------------|--------|--------|
| `/sitemap.xml` | Yes | `public_bp.route("/sitemap.xml")` | VERIFIED |
| `/feed/<format>` | Yes (atom, rss, json) | `/feed` and `/feed/<category>` only (RSS only) | DISCREPANCY |
| `/articles` | Yes | Does not exist as `/articles` route | DISCREPANCY |

Actual feeds.py contains: `/`, `/topic/<category>`, `/tag/<slug>`, `/feed`, `/feed/<category>`, `/sitemap.xml`.

### Subscribe Routes

| Route | Documented | Actual | Status |
|-------|------------|--------|--------|
| `/subscribe` (POST) | Yes | `public_bp.route("/subscribe", methods=["POST"])` | VERIFIED |
| `/verify/<token>` | Yes | `public_bp.route("/verify/<token>")` | VERIFIED |
| `/unsubscribe/<token>` | Yes | `public_bp.route("/unsubscribe/<token>")` (GET for page, POST for action) | VERIFIED |

### Links Routes

| Route | Documented | Actual | Status |
|-------|------------|--------|--------|
| `/a/<short_id>` | Yes | `public_bp.route("/a/<short_id>")` | VERIFIED |
| `/share/<platform>/<article_id>` | Documented | NOT FOUND | DISCREPANCY |
| `/click/<tracking_id>` | Documented | NOT FOUND | DISCREPANCY |

Actual links.py contains: `/article/<int:article_id>`, `/s/<short_id>` (redirect), `/a/<short_id>` (tracking page), `/api/v1/track/share-click/<int:article_id>`, `/track/newsletter-click/<int:article_id>`.

### Authentication

| Feature | Documented | Actual | Status |
|---------|------------|--------|--------|
| Login route `/login` | Yes | `admin_bp.route("/login")` | VERIFIED |
| Logout route `/logout` | Yes | `admin_bp.route("/logout", methods=["POST"])` | VERIFIED |
| TOTP 2FA support | Yes | `/verify-2fa` and `/setup-2fa` routes | VERIFIED |
| 8 backup codes | Yes | Implemented in `services/totp.py` | VERIFIED |
| Session hijacking protection (IP + UA) | Yes | Implemented in `require_auth` decorator | VERIFIED |
| Login lockout via Redis | Yes | Implemented via `_check_and_record_attempt` | VERIFIED |

**DISCREPANCY**: Document shows logout as route without `methods=["POST"]` but actual implementation requires POST.

### API Endpoints

| Endpoint | Documented | Actual | Status |
|----------|------------|--------|--------|
| `GET/POST /api/articles` | Yes | `GET /articles/ids`, `GET /articles/counts-by-status`, `POST /articles/bulk` (bulk ops, not list) | DISCREPANCY |
| `GET/PUT/DELETE /api/articles/<id>` | Yes | NOT FOUND individually - exists as bulk operations only | DISCREPANCY |
| `POST /api/articles/<id>/pipeline` | Yes | NOT FOUND | DISCREPANCY |
| `GET/POST /api/sources` | Yes | Found in sources.py | VERIFIED |
| `GET/PUT/DELETE /api/sources/<id>` | Yes | Found with PUT/PATCH/DELETE | VERIFIED |
| `POST /api/sources/<id>/refresh` | Yes | NOT FOUND | DISCREPANCY |
| `GET /api/pipeline/runs` | Yes | NOT FOUND at documented path | DISCREPANCY |
| `GET /api/pipeline/runs/<id>` | Yes | NOT FOUND | DISCREPANCY |
| `POST /api/pipeline/trigger` | Yes | NOT FOUND | DISCREPANCY |
| `GET/POST /api/webhooks` | Yes | Found | VERIFIED |
| `POST /api/webhooks/<id>/test` | Yes | Found | VERIFIED |
| `GET/PUT /api/config` | Documented | Only `POST /config/reload` found | DISCREPANCY |
| `GET /api/audit` | Yes | `GET /audit-logs` | VERIFIED |

Actual API endpoints found:
- `/articles/ids` (GET)
- `/articles/counts-by-status` (GET)
- `/articles/bulk` (POST)
- `/sources` (GET, POST)
- `/sources/<id>` (GET, PUT, PATCH, DELETE)
- `/pipeline/stats` (GET)
- `/pipeline/dead-letter/stats` (GET)
- `/pipeline/backlog` (GET)
- `/pipeline/sla` (GET)
- `/costs` (GET)
- `/sources/health` (GET)
- `/webhooks` (GET, POST)
- `/webhooks/<id>` (GET, PUT, PATCH, DELETE)
- `/webhooks/<id>/test` (POST)
- `/webhooks/<id>/events` (GET)
- `/webhooks/events/<int:event_id>/resend` (POST)
- `/config/reload` (POST)
- `/metrics` (GET)
- `/metrics/prometheus` (GET)
- `/audit-logs` (GET)
- `/health` (GET)
- `/workers/health` (GET)
- `/task/<task_id>` (GET)
- `/search/analytics` (GET)

### Template Structure

| Claim | Status | Notes |
|-------|--------|-------|
| `templates/admin/base.html` | Yes | Exists |
| `templates/admin/dashboard.html` | Yes | Exists |
| `templates/admin/articles/list.html` | Documented | Only `articles.html` exists (no subdirectory) |
| `templates/admin/articles/edit.html` | Documented | `article_edit.html` exists |
| `templates/admin/sources/list.html` | Documented | Only `sources.html` exists (no subdirectory) |
| `templates/admin/sources/edit.html` | Documented | No dedicated edit template |
| `templates/admin/newsletters/list.html` | Documented | Only `newsletters.html` exists |
| `templates/admin/newsletters/view.html` | Documented | Not found |

DISCREPANCY: Templates are flat, not organized in subdirectories as documented.

### Security

| Feature | Documented | Actual | Status |
|---------|------------|--------|--------|
| Session hijacking protection | Yes | Implemented in `require_auth` | VERIFIED |
| Bearer token auth | Yes | Implemented in `require_auth` | VERIFIED |
| CSRF via Flask-WTF | Yes | Implemented via `validate_csrf_json` decorator | VERIFIED |
| Rate limiting on admin routes | Yes | `@limiter.limit("10 per minute")` on login | VERIFIED |

## Bug Findings

### Critical

1. **Missing Article CRUD Endpoints**: The documented `/api/articles` with individual GET/PUT/DELETE and `/api/articles/<id>/pipeline` do not exist. Only bulk operations exist at `/articles/bulk`. This is a major API gap for programmatic article management.

### High

2. **Missing Pipeline Trigger Endpoint**: Documented `/api/pipeline/trigger`, `/api/pipeline/runs`, and `/api/pipeline/runs/<id>` do not exist in the API. Pipeline runs are managed via the HTML dashboard at `/admin/pipelines` and `/admin/pipelines/<id>/logs`.

3. **Missing Source Refresh Endpoint**: Documented `POST /api/sources/<id>/refresh` does not exist. No API equivalent found.

4. **Logout Requires POST (Not Documented)**: Document shows `/logout` without method specification implying GET works, but actual implementation requires POST. This could cause integration issues.

### Medium

5. **Template Directory Structure Mismatch**: Document shows `templates/admin/articles/list.html`, `templates/admin/sources/list.html`, etc. but actual templates are flat (`articles.html`, `sources.html`). No subdirectories exist under `templates/admin/`.

6. **Share/Click Tracking Routes Mismatch**: Document shows `/share/<platform>/<article_id>` and `/click/<tracking_id>` but actual implementation has `/api/v1/track/share-click/<int:article_id>` and `/track/newsletter-click/<int:article_id>`. These are functionally similar but different URLs.

7. **Article List Route Missing**: Document shows `/articles` public route but actual implementation uses `/` (index) or topic/tag feeds.

8. **Config API Limited**: Only `POST /config/reload` exists, not the documented `GET /api/config` and `PUT /api/config`.

### Low

9. **Feed Format Limitation**: Document shows support for atom, rss, json formats via `/feed/<format>`, but actual implementation only has `/feed` and `/feed/<category>` which produce RSS.

## Improvement Opportunities

1. **Complete Article CRUD API**: Add individual article GET/PUT/DELETE endpoints and pipeline stage trigger endpoint to match documented API surface.

2. **Add Missing Pipeline API Endpoints**: Implement `/api/pipeline/runs`, `/api/pipeline/runs/<id>`, `/api/pipeline/trigger` to provide programmatic pipeline management.

3. **Add Source Refresh API**: Implement `POST /api/sources/<id>/refresh` for programmatic source refresh.

4. **Document Actual Route Structure**: Update `architecture/routes.md` to accurately reflect the implemented route structure, especially for:
   - Flat template structure vs. documented subdirectories
   - Actual API endpoints available
   - POST requirement for logout

5. **Consider Standardizing Share Tracking URLs**: The documented `/share/<platform>/<article_id>` and `/click/<tracking_id>` may be more intuitive than the implemented `/api/v1/track/share-click` and `/track/newsletter-click`.

6. **Add `/articles` Public Route**: If the documented `/articles` listing page is intended, it should be implemented.

## Action Items

| Priority | Item | Files Affected |
|----------|------|----------------|
| High | Add individual Article CRUD API endpoints (`/api/articles/<id>` with GET/PUT/DELETE) | `routes/admin/api/articles.py` |
| High | Add pipeline stage trigger endpoint (`/api/articles/<id>/pipeline` POST) | `routes/admin/api/articles.py` |
| High | Add source refresh API endpoint (`/api/sources/<id>/refresh` POST) | `routes/admin/api/sources.py` |
| Medium | Update architecture document to match actual implementation | `architecture/routes.md` |
| Medium | Add missing pipeline API endpoints (`/api/pipeline/runs`, `/api/pipeline/trigger`) | `routes/admin/api/pipeline.py` |
| Low | Consider adding `/articles` public route if intended | `routes/public/feeds.py` |
| Low | Standardize share tracking URL naming to match documentation | `routes/public/links.py` |

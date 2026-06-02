# Routes Architecture Review

## Summary
Overall health: **Good with minor discrepancies**. Most claims in `architecture/routes.md` are accurate. The main issues are:
1. Trend Memory semantic search endpoint registered on wrong blueprint (major)
2. Incomplete directory structure listing in routes.md (minor)
3. Some endpoints missing from documentation tables

## Verified Claims

### Blueprint Structure ✓
| Blueprint | URL Prefix | Verified |
|-----------|------------|----------|
| `public_bp` | `/` (no prefix) | ✓ Correct |
| `admin_bp` | `/admin` | ✓ Correct |
| `admin_api_bp` | `/api/v1` | ✓ Correct |
| `api_tokens_bp` | `/api-tokens` (no prefix) | ✓ Correct |

### Admin Routes ✓
All documented admin routes exist with correct HTTP methods:
- `/admin/login` [GET/POST] - `auth.py:45`
- `/admin/` [GET] - `dashboard.py:192`
- `/admin/articles` [GET] - `articles.py:221`
- `/admin/articles/<id>/edit` [GET/POST] - `articles.py:385`
- `/admin/articles/<id>/original` [GET] - `articles.py:426`
- `/admin/articles/<id>/versions` [GET] - `articles.py:440`
- `/admin/articles/<id>/versions/<version_id>/rollback` [POST] - `articles.py:458`
- `/admin/articles/<id>/delete` [POST] - `articles.py:505`
- `/admin/articles/<id>/reprocess` [POST] - `articles.py:534`
- `/admin/sources` [GET] - `sources.py:26`
- `/admin/sources/<id>/enable` [POST] - `sources.py:106`
- `/admin/sources/<id>/disable` [POST] - `sources.py:142`
- `/admin/subscribers` [GET] - `subscribers.py:7`
- `/admin/subscribers/export` [GET] - `subscribers.py:51`
- `/admin/newsletters` [GET] - `newsletters.py:70`
- `/admin/newsletters/<id>` [GET] - `newsletters.py:90`
- `/admin/newsletters/generate` [POST] - `newsletters.py:100`
- `/admin/newsletters/dry-run` [POST] - `newsletters.py:126`
- `/admin/dead-letters` [GET] - `dashboard.py:13`
- `/admin/pipelines` [GET] - `pipelines.py:12`
- `/admin/pipelines/<run_id>/logs` [GET] - `pipelines.py:40`
- `/admin/trigger-crawl` [POST] - `pipelines.py:84`
- `/admin/sources/add` [POST] - `sources.py:39`
- `/admin/trend-memory` [GET] - `trend_memory.py:16`
- `/admin/trend-memory/delete/<id>` [POST] - `trend_memory.py:53`
- `/admin/trend-memory/delete-expired` [POST] - `trend_memory.py:85`
- `/admin/review` [GET] - `review.py:17`
- `/admin/review/<id>/approve` [POST] - `review.py:64`
- `/admin/review/<id>/reject` [POST] - `review.py:121`
- `/admin/topic-notes` [GET] - `topic_notes.py:20`
- `/admin/topic-notes/create` [POST] - `topic_notes.py:42`
- `/admin/topic-notes/edit` [POST] - `topic_notes.py:86`
- `/admin/topic-notes/delete` [POST] - `topic_notes.py:143`
- `/admin/topic-notes/row/<topic>` [GET] - `topic_notes.py:172`
- `/admin/webhooks` [GET] - `webhooks.py:8`
- `/admin/shares` [GET] - `shares.py:8`
- `/admin/shares/<id>/edit-form` [GET] - `shares.py:143`
- `/admin/shares/<id>/row` [GET] - `shares.py:153`
- `/admin/shares/add` [POST] - `shares.py:17`
- `/admin/shares/<id>/edit` [POST] - `shares.py:69`
- `/admin/shares/<id>/delete` [POST] - `shares.py:120`
- `/admin/shares/<id>/toggle` [POST] - `shares.py:163`
- `/admin/metrics` [GET] - `metrics.py:10`
- `/admin/verify-2fa` [GET/POST] - `auth.py:99`
- `/admin/setup-2fa` [GET/POST] - `auth.py:153`
- `/admin/logout` [POST] - `auth.py:190`

### Admin API Routes ✓
All documented API endpoints exist with correct HTTP methods:
- `/articles/ids` [GET] - `api/articles.py:152`
- `/articles/counts-by-status` [GET] - `api/articles.py:171`
- `/articles/<id>` [GET, PUT, DELETE] - `api/articles.py:597,620,673`
- `/articles/<id>/pipeline` [POST] - `api/articles.py:528`
- `/articles/bulk` [POST] - `api/articles.py:470`
- `/sources` [GET, POST] - `api/sources.py:16,48`
- `/sources/<id>` [GET, PUT, PATCH, DELETE] - `api/sources.py:123,154,225,314`
- `/sources/<id>/refresh` [POST] - `api/sources.py:342`
- `/sources/health` [GET] - `api/pipeline.py:167`
- `/pipeline/stats` [GET] - `api/pipeline.py:13`
- `/pipeline/backlog` [GET] - `api/pipeline.py:87`
- `/pipeline/dead-letter/stats` [GET] - `api/pipeline.py:48`
- `/pipeline/sla` [GET] - `api/pipeline.py:193`
- `/costs` [GET] - `api/pipeline.py:135`
- `/webhooks` [GET, POST] - `api/webhooks.py:57,91`
- `/webhooks/<id>` [GET, PUT, PATCH, DELETE] - `api/webhooks.py:166,210,270`
- `/webhooks/<id>/test` [POST] - `api/webhooks.py:298`
- `/webhooks/<id>/events` [GET] - `api/webhooks.py:322`
- `/webhooks/events/<id>/resend` [POST] - `api/webhooks.py:365`
- `/search/analytics` [GET] - `api/search.py:11`
- `/config/reload` [POST] - `api/config.py:13`
- `/metrics` [GET] - `api/config.py:52`
- `/metrics/prometheus` [GET] - `api/config.py:60`
- `/audit-logs` [GET] - `api/audit.py:11`
- `/alerts` [GET] - `api/alerts.py:14`
- `/sources/performance` [GET] - `api/source_intelligence.py:11`
- `/topics/coverage` [GET] - `api/source_intelligence.py:74`
- `/sources/recommendations` [GET] - `api/source_intelligence.py:104`
- `/topic-gap/reports` [GET] - `api/topic_gap.py:12`
- `/articles/<id>/quality` [GET] - `api/quality.py:10`
- `/quality/recent` [GET] - `api/quality.py:59`
- `/articles/<id>/pipeline/history` [GET] - `api/replay.py:15`
- `/articles/<id>/pipeline/replay` [POST] - `api/replay.py:33`
- `/articles/<id>/pipeline/restore-version` [POST] - `api/replay.py:107`
- `/newsletters/stats` [GET] - `newsletters.py:177`
- `/newsletter/preview` [POST] - `newsletters.py:221`
- `/search/articles` [GET] - `api/search.py:60`

### Public Routes ✓
All documented public routes exist:
- `/` - `feeds.py:74`
- `/topic/<category>` - `feeds.py:127`
- `/tag/<slug>` - `feeds.py:177`
- `/feed` - `feeds.py:229`
- `/feed/<category>` - `feeds.py:266`
- `/sitemap.xml` - `feeds.py:315`
- `/subscribe` [POST] - `subscribe.py:32`
- `/verify/<token>` - `subscribe.py:184`
- `/unsubscribe/<token>` [GET/POST] - `subscribe.py:138,154`
- `/article/<int:article_id>` - `links.py:24`
- `/s/<short_id>` - `links.py:94`
- `/a/<short_id>` - `links.py:103`
- `/api/v1/track/share-click/<int:article_id>` [POST] - `links.py:123`
- `/track/newsletter-click/<int:article_id>` - `links.py:130`
- `/health` - `public/__init__.py:115`

### API Tokens ✓
- `GET /api-tokens` - `api_tokens.py:13`
- `POST /api-tokens` - `api_tokens.py:30`
- `DELETE /api-tokens/<id>` - `api_tokens.py:66`

### Authentication ✓
- Session hijacking protection (IP + User-Agent binding) - `decorators.py:45-56`
- TOTP 2FA support with 8 backup codes - `auth.py:99-187`
- Login lockout via Redis (with in-memory fallback) - `admin/__init__.py:56-256`

### CSRF Protection ✓
- `@validate_csrf_json` decorator implemented - `decorators.py:74-96`
- Validates X-CSRFToken header for JSON API endpoints
- Respects WTF_CSRF_ENABLED = False in TestingConfig

### Template Structure ✓
Directory structure matches documented structure. All templates exist:
- `templates/base.html` ✓
- `templates/base_admin.html` ✓
- `templates/admin/*.html` - all exist
- `templates/admin/partials/*.html` - all exist
- `templates/partials/*.html` - all exist
- `templates/errors/*.html` - all exist
- `templates/macros/*.html` - all exist

## Discrepancies Found

### 1. **Claim**: `routes/admin/api/` directory contains only `articles.py`, `sources.py`, `pipeline.py`, `search.py`, `webhooks.py`, `config.py`, `audit.py`, `health.py`, `alerts.py`, `newsletter.py`, `quality.py`, `replay.py`, `source_intelligence.py`, `topic_gap.py`, `utils.py`
- **Reality**: The directory structure listing in `routes.md:7-44` shows a truncated list. The actual `routes/admin/api/` contains all 15+ files as listed above, but the initial tree diagram in lines 7-45 only shows a subset (articles, sources, pipeline, search, webhooks, config, audit, health, alerts, newsletter, quality, replay, source_intelligence, topic_gap, utils).
- **Severity**: Minor
- **Location**: `architecture/routes.md:7-44`
- **Note**: The Admin API Blueprint section (lines 108-151) correctly lists most endpoints, but the initial directory tree at lines 7-44 only shows a partial list. The tree shows files under `api/` that don't all match the actual structure.

### 2. **Claim**: `/admin/api/trend-memory/semantic-search` [GET] - Semantic search in trend memory (listed in Admin Blueprint section at line 86)
- **Reality**: This endpoint is registered on `admin_bp` at `/api/trend-memory/semantic-search` (without the `/admin` prefix since it's already under admin_bp). The URL is actually `/admin/api/trend-memory/semantic-search` due to the admin_bp prefix.
- **Severity**: Minor (technically correct URL, but inconsistent with API pattern)
- **Location**: `trend_memory.py:117`
- **Note**: This endpoint returns JSON but is on `admin_bp` rather than `admin_api_bp`, which is inconsistent with other API endpoints.

### 3. **Claim**: `/newsletter/preview` endpoint is at `routes/admin/newsletters.py:221`
- **Reality**: Verified correct - the endpoint is at line 221 of `newsletters.py`.
- **Status**: ✓ Verified

### 4. **Missing from Documentation**:
The following endpoints exist in code but are not documented in routes.md:
- `/api/v1/sources/health` - `api/pipeline.py:167` [GET]
- `/api/v1/workers/health` - `api/health.py:55` [GET]
- `/api/v1/task/<task_id>` - `api/health.py:103` [GET]
- `/api/v1/search/articles` - `api/search.py:60` [GET] (partially documented at line 150)
- `/api/v1/newsletters/performance` - `api/newsletter.py:176` [GET] (not explicitly in docs)

## Bugs Identified

### 1. **Bug**: Trend Memory semantic search returns inconsistent response format
- **Location**: `trend_memory.py:117-143`
- **Impact**: This endpoint returns `jsonify({"results": ..., "query": ..., "count": ...})` directly, while all other admin API endpoints use the `api_response()` wrapper from `routes/admin/api/utils.py`. This creates inconsistent JSON response format.
- **Suggested fix**: Move this endpoint to `admin_api_bp` and use `api_response()` wrapper, or refactor to use `api_response()` wrapper even on `admin_bp`.

### 2. **Bug**: Mixed route types in `newsletters.py`
- **Location**: `newsletters.py`
- **Impact**: This single file contains both `admin_bp` HTML routes (lines 70-174) and `admin_api_bp` JSON routes (lines 177-278). This violates the convention used by other admin modules which separate HTML and API routes.
- **Suggested fix**: Move `/newsletters/stats` and `/newsletter/preview` to `routes/admin/api/newsletter.py` to maintain consistency.

## Improvement Opportunities

### 1. **Improvement**: Consistent API response format for all admin endpoints
- **Location**: `trend_memory.py:117-143`
- **Benefit**: All admin API endpoints would return consistent JSON structure with `data`, `meta`, `error` keys via `api_response()` wrapper.

### 2. **Improvement**: Route file organization
- **Location**: `newsletters.py` mixes HTML and API routes
- **Benefit**: Follows the pattern established by other admin modules (articles, sources have separate API files).

### 3. **Improvement**: Document missing API endpoints
- **Location**: `architecture/routes.md`
- **Benefit**: Complete documentation of all available API endpoints.

## Stale Items Found

### 1. **Stale**: Directory tree in `routes.md:7-45`
The directory tree shows a simplified/partial view of `routes/admin/api/` files. The actual structure is more complete.

### 2. **Stale**: Initial mention of `routes/admin/api/` contents
The tree diagram in lines 7-45 shows `api/` with only some files listed, but later sections (108-151) correctly list more endpoints. The tree should be updated to reflect the complete structure.

## Recommendations

1. **High Priority**: Refactor `trend_memory.py:117` to use `admin_api_bp` and `api_response()` for consistency
2. **Medium Priority**: Update `architecture/routes.md` directory tree to show all actual files in `routes/admin/api/`
3. **Medium Priority**: Move `/newsletters/stats` and `/newsletter/preview` to `routes/admin/api/newsletter.py`
4. **Low Priority**: Add missing endpoints to documentation: `/api/v1/sources/health`, `/api/v1/workers/health`, `/api/v1/task/<task_id>`, `/api/v1/newsletters/performance`
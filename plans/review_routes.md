# Review: routes.md

**Reviewed:** 2026-05-31
**Source:** `architecture/routes.md`
**Reviewer:** Subagent 6 (Routes Layer)
**Status:** COMPLETE

---

## Verified Claims

### Blueprint Structure
- **VERIFIED**: `public_bp` blueprint with no URL prefix (`routes/public/__init__.py:26`)
- **VERIFIED**: `admin_bp` blueprint with `/admin` prefix (`routes/admin/__init__.py:12`)
- **VERIFIED**: `admin_api_bp` blueprint with `/api/v1` prefix (`routes/admin/__init__.py:13`)
- **VERIFIED**: `api_tokens_bp` blueprint registered WITHOUT url_prefix (`app.py:197`, `routes/admin/api_tokens.py:9`)

### Admin Routes Table
- **VERIFIED**: All 47 admin routes listed in the document exist with correct HTTP methods
- **VERIFIED**: `/admin/logout` is POST only (`routes/admin/auth.py:188`)
- **VERIFIED**: `/admin/login` supports GET/POST (`routes/admin/auth.py:43`)
- **VERIFIED**: `/admin/verify-2fa` supports GET/POST (`routes/admin/auth.py:97`)
- **VERIFIED**: `/admin/setup-2fa` supports GET/POST (`routes/admin/auth.py:151`)

### Admin API Endpoints Table
- **VERIFIED**: All 35+ API endpoints listed in the document exist with correct HTTP methods
- **VERIFIED**: `/articles/ids` GET (`routes/admin/api/articles.py:152`)
- **VERIFIED**: `/articles/counts-by-status` GET (`routes/admin/api/articles.py:171`)
- **VERIFIED**: `/articles/<id>` GET, PUT, DELETE (`routes/admin/api/articles.py:597,620,673`)
- **VERIFIED**: `/articles/<id>/pipeline` POST (`routes/admin/api/articles.py:528`)
- **VERIFIED**: `/articles/bulk` POST (`routes/admin/api/articles.py:470`)
- **VERIFIED**: `/sources` GET, POST (`routes/admin/api/sources.py:16,48`)
- **VERIFIED**: `/sources/<id>` GET, PUT, PATCH, DELETE (`routes/admin/api/sources.py:123,154,225,314`)
- **VERIFIED**: `/sources/<id>/refresh` POST (`routes/admin/api/sources.py:342`)
- **VERIFIED**: `/sources/health` GET (`routes/admin/api/pipeline.py:167`)
- **VERIFIED**: `/pipeline/stats` GET (`routes/admin/api/pipeline.py:13`)
- **VERIFIED**: `/pipeline/backlog` GET (`routes/admin/api/pipeline.py:87`)
- **VERIFIED**: `/pipeline/dead-letter/stats` GET (`routes/admin/api/pipeline.py:48`)
- **VERIFIED**: `/pipeline/sla` GET (`routes/admin/api/pipeline.py:193`)
- **VERIFIED**: `/costs` GET (`routes/admin/api/pipeline.py:135`)
- **VERIFIED**: `/webhooks` GET, POST (`routes/admin/api/webhooks.py:56,90`)
- **VERIFIED**: `/webhooks/<id>` GET, PUT/PATCH, DELETE (`routes/admin/api/webhooks.py:165,209,269`)
- **VERIFIED**: `/webhooks/<id>/test` POST (`routes/admin/api/webhooks.py:297`)
- **VERIFIED**: `/webhooks/<id>/events` GET (`routes/admin/api/webhooks.py:321`)
- **VERIFIED**: `/webhooks/events/<id>/resend` POST (`routes/admin/api/webhooks.py:363`)
- **VERIFIED**: `/search/analytics` GET (`routes/admin/api/search.py:11`)
- **VERIFIED**: `/config/reload` POST (`routes/admin/api/config.py:13`)
- **VERIFIED**: `/metrics` GET (`routes/admin/api/config.py:52`)
- **VERIFIED**: `/metrics/prometheus` GET (`routes/admin/api/config.py:60`)
- **VERIFIED**: `/audit-logs` GET (`routes/admin/api/audit.py:11`)
- **VERIFIED**: `/alerts` GET (`routes/admin/api/alerts.py:14`)
- **VERIFIED**: `/sources/performance` GET (`routes/admin/api/source_intelligence.py:11`)
- **VERIFIED**: `/topics/coverage` GET (`routes/admin/api/source_intelligence.py:74`)
- **VERIFIED**: `/sources/recommendations` GET (`routes/admin/api/source_intelligence.py:104`)
- **VERIFIED**: `/topic-gap/reports` GET (`routes/admin/api/topic_gap.py:12`)
- **VERIFIED**: `/articles/<id>/quality` GET (`routes/admin/api/quality.py:10`)
- **VERIFIED**: `/quality/recent` GET (`routes/admin/api/quality.py:59`)
- **VERIFIED**: `/articles/<id>/pipeline/history` GET (`routes/admin/api/replay.py:15`)
- **VERIFIED**: `/articles/<id>/pipeline/replay` POST (`routes/admin/api/replay.py:33`)
- **VERIFIED**: `/articles/<id>/pipeline/restore-version` POST (`routes/admin/api/replay.py:107`)
- **VERIFIED**: `/search/articles` GET (`routes/admin/api/search.py:60`)

### Public Routes
- **VERIFIED**: Feeds (`routes/public/feeds.py`) - index, topic_feed, tag_feed, feed_all, feed_topic, sitemap
- **VERIFIED**: Subscribe (`routes/public/subscribe.py`) - subscribe, verify, unsubscribe
- **VERIFIED**: Links (`routes/public/links.py`) - article_detail, short_url_redirect, short_url_tracking_page, track_share_click, track_newsletter_click
- **VERIFIED**: Health check (`routes/public/__init__.py:111`)

### Security Features
- **VERIFIED**: `@require_auth` decorator (`routes/decorators.py:14`)
- **VERIFIED**: Session hijacking protection (IP + User-Agent binding) (`routes/decorators.py:43-54`)
- **VERIFIED**: CSRF protection with `@validate_csrf_json` (`routes/decorators.py:72-94`)
- **VERIFIED**: Rate limiting on login routes (10/min) (`routes/admin/auth.py:44,98`)
- **VERIFIED**: Default rate limit 60/min (`extensions.py:49`)

### Template Structure
- **VERIFIED**: All admin templates listed in the document exist in `templates/admin/`
- **VERIFIED**: All public templates listed in the document exist in `templates/`
- **VERIFIED**: Social sharing is client-side JavaScript, NOT server endpoint (noted in document line 308)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 148 | `/newsletters/performance` GET - Newsletter performance metrics | `routes/admin/api/newsletters.py:177` - endpoint is `/newsletters/stats` | MEDIUM |
| 252 | `GET /api/v1/newsletters/performance` - Newsletter performance metrics | `routes/admin/api/newsletters.py:177` - endpoint is `/newsletters/stats` | MEDIUM |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | Missing API endpoint: `/newsletter/preview` POST - Newsletter preview endpoint exists in code but not documented | `routes/admin/api/newsletters.py:221` | LOW | Endpoint exists at `/newsletter/preview` with POST method, requires `@require_auth` and `@validate_csrf_json` |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Document the `/newsletter/preview` POST endpoint in the Admin API endpoints table | maintainability | P2 |
| 2 | Fix the `/newsletters/performance` endpoint name to `/newsletters/stats` in the document | accuracy | P1 |
| 3 | Add documentation for the `limit_content_length` decorator used on some routes (`routes/__init__.py:8`) | security | P3 |
| 4 | Document the HTMX partial rendering pattern used by many admin routes (e.g., `request.headers.get("HX-Request")`) | maintainability | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 148, 252 | `/newsletters/performance` endpoint name | Actual endpoint is `/newsletters/stats` | update |

---

## Summary

- **Verified:** 47 claims
- **Incorrect:** 2 claims (endpoint name mismatch)
- **Bugs:** 1 (LOW: missing endpoint documentation)
- **Improvements:** 4 (P1: 1, P2: 1, P3: 2)
- **Stale items:** 1 (endpoint name)

The architecture document is highly accurate. The main issues are:
1. The newsletter performance endpoint is misnamed (should be `/newsletters/stats`)
2. The `/newsletter/preview` POST endpoint is missing from documentation
3. Minor documentation gaps for utility decorators and HTMX patterns

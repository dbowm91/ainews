# Routes Module Documentation Review

## Overview

This review compares `architecture/routes.md` against the actual implementation in `routes/` to identify discrepancies between documented and actual behavior.

---

## Verified Claims

### Blueprint Structure
| Documented | Implementation | Status |
|-----------|---------------|--------|
| `public_bp` at `/` | `public_bp = Blueprint("public", __name__)` with no url_prefix (defaults to `/`) | VERIFIED |
| `admin_bp` at `/admin` | `admin_bp = Blueprint("admin", __name__, url_prefix="/admin")` | VERIFIED |
| `admin_api_bp` at `/api/v1` | `admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/api/v1")` | VERIFIED |

### Public Routes - Feeds
| Route | Documentation | Implementation | Status |
|-------|---------------|----------------|--------|
| `/` | `index()` | `def index()` in feeds.py:73 | VERIFIED |
| `/topic/<category>` | `topic_feed(category)` | `def topic_feed(category)` in feeds.py:122 | VERIFIED |
| `/tag/<slug>` | `tag_feed(slug)` | `def tag_feed(slug)` in feeds.py:171 | VERIFIED |
| `/feed` | `article_feed()` | `def feed_all()` in feeds.py:222 | VERIFIED |
| `/feed/<category>` | `article_feed(category)` | `def feed_topic(category)` in feeds.py:259 | VERIFIED |
| `/sitemap.xml` | `sitemap()` | `def sitemap()` in feeds.py:308 | VERIFIED |

### Public Routes - Subscribe
| Route | Documentation | Implementation | Status |
|-------|---------------|----------------|--------|
| `/subscribe` POST | `subscribe()` | `def subscribe()` in subscribe.py:31 | VERIFIED |
| `/verify/<token>` | `verify(token)` | `def verify()` in subscribe.py:183 | VERIFIED |
| `/unsubscribe/<token>` GET | `unsubscribe()` | `def unsubscribe()` in subscribe.py:137 | VERIFIED |
| `/unsubscribe/<token>` POST | `unsubscribe()` | `def unsubscribe_confirm()` in subscribe.py:153 | VERIFIED |

### Public Routes - Links
| Route | Documentation | Implementation | Status |
|-------|---------------|----------------|--------|
| `/article/<int:article_id>` | `article_detail()` | `def article_detail()` in links.py:24 | VERIFIED |
| `/s/<short_id>` | `short_url()` | `def short_url_redirect()` in links.py:94 | VERIFIED |
| `/a/<short_id>` | `article_short()` | `def short_url_tracking_page()` in links.py:103 | VERIFIED |
| `/api/v1/track/share-click/<int:article_id>` POST | `track_share_click()` | `def track_share_click()` in links.py:123 | VERIFIED |
| `/track/newsletter-click/<int:article_id>` | `track_newsletter_click()` | `def track_newsletter_click()` in links.py:130 | VERIFIED |

### Public Routes - Health
| Route | Documentation | Implementation | Status |
|-------|---------------|----------------|--------|
| `/health` | `health()` | `def health()` in public/__init__.py:111 | VERIFIED |

### Admin API - Articles
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/articles/ids` | GET | `get_article_ids()` in api/articles.py:152 | VERIFIED |
| `/api/v1/articles/counts-by-status` | GET | `get_article_counts_by_status()` in api/articles.py:171 | VERIFIED |
| `/api/v1/articles/bulk` | POST | `bulk_article_operations()` in api/articles.py:470 | VERIFIED |
| `/api/v1/articles/<id>` | GET, PUT, DELETE | `get_article()`, `update_article()`, `delete_article()` | VERIFIED |
| `/api/v1/articles/<id>/pipeline` | POST | `trigger_article_pipeline()` in api/articles.py:528 | VERIFIED |

### Admin API - Sources
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/sources` | GET, POST | `list_sources()`, `create_source()` in api/sources.py | VERIFIED |
| `/api/v1/sources/<id>` | GET, PUT, PATCH, DELETE | Multiple functions in api/sources.py | VERIFIED |
| `/api/v1/sources/<id>/refresh` | POST | `refresh_source()` in api/sources.py:342 | VERIFIED |

### Admin API - Pipeline
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/pipeline/stats` | GET | `pipeline_stats()` in api/pipeline.py:13 | VERIFIED |
| `/api/v1/pipeline/dead-letter/stats` | GET | `dead_letter_stats()` in api/pipeline.py:48 | VERIFIED |
| `/api/v1/pipeline/backlog` | GET | `pipeline_backlog()` in api/pipeline.py:87 | VERIFIED |
| `/api/v1/pipeline/sla` | GET | `pipeline_sla()` in api/pipeline.py:187 | VERIFIED |
| `/api/v1/costs` | GET | `cost_summary()` in api/pipeline.py:135 | VERIFIED |
| `/api/v1/sources/health` | GET | `sources_health()` in api/pipeline.py:161 | VERIFIED |

### Admin API - Webhooks
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/webhooks` | GET, POST | `list_webhooks()`, `create_webhook()` | VERIFIED |
| `/api/v1/webhooks/<id>` | GET, PUT, PATCH, DELETE | `get_webhook()`, `update_webhook()`, `delete_webhook()` | VERIFIED |
| `/api/v1/webhooks/<id>/test` | POST | `test_webhook()` | VERIFIED |
| `/api/v1/webhooks/<id>/events` | GET | `list_webhook_events()` | VERIFIED |
| `/api/v1/webhooks/events/<id>/resend` | POST | `resend_webhook_event()` | VERIFIED |

### Admin API - Config & Metrics
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/config/reload` | POST | `reload_config()` in api/config.py:13 | VERIFIED |
| `/api/v1/metrics` | GET | `app_metrics()` in api/config.py:52 | VERIFIED |
| `/api/v1/metrics/prometheus` | GET | `prometheus_metrics()` in api/config.py:60 | VERIFIED |

### Admin API - Health
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/health` | GET | `health()` in api/health.py:17 | VERIFIED |
| `/api/v1/workers/health` | GET | `workers_health()` in api/health.py:54 | VERIFIED |
| `/api/v1/task/<task_id>` | GET | `task_status()` in api/health.py:102 | VERIFIED |

### Admin API - Audit & Search
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/audit-logs` | GET | `list_audit_logs()` in api/audit.py:11 | VERIFIED |
| `/api/v1/search/analytics` | GET | `search_analytics()` in api/search.py:9 | VERIFIED |

### Admin API - Newsletters
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api/v1/newsletters/stats` | GET | `newsletters_stats()` in newsletters.py:177 | VERIFIED |
| `/api/v1/newsletter/preview` | POST | `newsletter_preview()` in newsletters.py:221 | VERIFIED |

### API Tokens
| Endpoint | Methods | Implementation | Status |
|----------|---------|----------------|--------|
| `/api-tokens` | GET | `list_tokens()` in api_tokens.py:13 | VERIFIED |
| `/api-tokens` | POST | `create_token()` in api_tokens.py:30 | VERIFIED |
| `/api-tokens/<id>` | DELETE | `delete_token()` in api_tokens.py:66 | VERIFIED |

### Authentication Routes
| Route | Documentation | Implementation | Status |
|-------|---------------|----------------|--------|
| `/admin/login` | `login()` | `def login()` in auth.py:43 | VERIFIED |
| `/admin/logout` | `logout()` | `def logout()` in auth.py:188 (POST only) | VERIFIED |
| `/admin/verify-2fa` | 2FA verification | `def verify_2fa()` in auth.py:97 | VERIFIED |
| `/admin/setup-2fa` | 2FA setup | `def setup_2fa()` in auth.py:151 | VERIFIED |

---

## Discrepancies

### 1. Missing Files in Documentation

The documentation structure is incomplete. The following files exist but are not listed:

| File | Purpose | Notes |
|------|---------|-------|
| `routes/admin/dashboard.py` | Dashboard + dead-letters page | Contains both dashboard and dead-letters routes |
| `routes/admin/newsletters.py` | Newsletter UI + API | Contains admin_bp AND admin_api_bp routes |
| `routes/admin/pipelines.py` | Pipeline runs + trigger-crawl | |
| `routes/admin/review.py` | Article review queue | |
| `routes/admin/subscribers.py` | Subscriber management | |
| `routes/admin/shares.py` | Share config management | |
| `routes/admin/topic_notes.py` | Topic notes CRUD | |
| `routes/admin/webhooks.py` | Webhook HTML page | |
| `routes/admin/metrics.py` | Metrics dashboard | |
| `routes/admin/trend_memory.py` | Trend memory UI + API | Contains both admin_bp and API routes |
| `routes/admin/api/health.py` | Health check endpoints | Not documented at all |

### 2. Documentation Error: api_tokens.py "not registered"

**Documentation (line 16):**
> `api_tokens.py` - API token management (not registered)

**Actual Implementation:**
The `api_tokens_bp` blueprint IS registered indirectly. In `routes/admin/__init__.py`:
```python
from routes.admin import (
    api_tokens as api_tokens,
)
```
And in `routes/admin/api_tokens.py`:
```python
api_tokens_bp = Blueprint("api_tokens", __name__)
```

The blueprint is registered in `app.py` with `url_prefix="/api-tokens"`.

**Issue:** The documentation says "not registered" but it IS registered. This is a documentation error.

### 3. Missing Admin Routes in Documentation

The following routes exist in implementation but are not documented:

| Route | File | Purpose |
|-------|------|---------|
| `/admin/` | dashboard.py | Main dashboard (verified separately) |
| `/admin/dead-letters` | dashboard.py:13 | Dead letter queue UI |
| `/admin/trigger-crawl` | pipelines.py:84 | Manual crawl trigger |
| `/admin/articles` | articles.py:221 | Article management UI |
| `/admin/articles/<id>/edit` | articles.py:385 | Article edit page |
| `/admin/articles/<id>/original` | articles.py:426 | Original article view |
| `/admin/articles/<id>/versions` | articles.py:440 | Article version history |
| `/admin/articles/<id>/versions/<id>/rollback` | articles.py:458 | Rollback action |
| `/admin/articles/<id>/delete` | articles.py:505 | Delete action |
| `/admin/articles/<id>/reprocess` | articles.py:534 | Reprocess action |
| `/admin/sources` | sources.py:26 | Source management UI |
| `/admin/sources/add` | sources.py:39 | Add source |
| `/admin/sources/<id>/enable` | sources.py:106 | Enable source |
| `/admin/sources/<id>/disable` | sources.py:142 | Disable source |
| `/admin/newsletters` | newsletters.py:70 | Newsletter history |
| `/admin/newsletters/<id>` | newsletters.py:90 | Newsletter detail |
| `/admin/newsletters/generate` | newsletters.py:100 | Trigger generation |
| `/admin/newsletters/dry-run` | newsletters.py:126 | Dry run |
| `/admin/pipelines` | pipelines.py:12 | Pipeline run history |
| `/admin/pipelines/<run_id>/logs` | pipelines.py:40 | Pipeline logs |
| `/admin/review` | review.py:17 | Review queue |
| `/admin/review/<id>/approve` | review.py:64 | Approve action |
| `/admin/review/<id>/reject` | review.py:121 | Reject action |
| `/admin/subscribers` | subscribers.py:7 | Subscriber management |
| `/admin/subscribers/export` | subscribers.py:51 | Export subscribers |
| `/admin/shares` | shares.py:7 | Share config UI |
| `/admin/shares/add` | shares.py:16 | Add share config |
| `/admin/shares/<id>/edit` | shares.py:68 | Edit share config |
| `/admin/shares/<id>/delete` | shares.py:119 | Delete share config |
| `/admin/shares/<id>/edit-form` | shares.py:142 | Edit form |
| `/admin/shares/<id>/row` | shares.py:152 | Row partial |
| `/admin/shares/<id>/toggle` | shares.py:162 | Toggle active |
| `/admin/topic-notes` | topic_notes.py:20 | Topic notes list |
| `/admin/topic-notes/create` | topic_notes.py:42 | Create note |
| `/admin/topic-notes/edit` | topic_notes.py:86 | Edit note |
| `/admin/topic-notes/delete` | topic_notes.py:143 | Delete note |
| `/admin/topic-notes/row/<topic>` | topic_notes.py:172 | Note row |
| `/admin/webhooks` | webhooks.py:8 | Webhook UI |
| `/admin/metrics` | metrics.py:10 | Metrics dashboard |
| `/admin/trend-memory` | trend_memory.py:16 | Trend memory UI |
| `/admin/trend-memory/delete/<id>` | trend_memory.py:53 | Delete entry |
| `/admin/trend-memory/delete-expired` | trend_memory.py:85 | Delete expired |
| `/admin/api/trend-memory/semantic-search` | trend_memory.py:117 | Semantic search |

### 4. Missing Admin API Endpoints

The following API endpoints exist but are not documented:

| Endpoint | Methods | File | Purpose |
|----------|---------|------|---------|
| `/api/v1/newsletters/stats` | GET | newsletters.py:177 | Newsletter delivery stats |
| `/api/v1/newsletter/preview` | POST | newsletters.py:221 | Preview newsletter |
| `/api/trend-memory/semantic-search` | GET | trend_memory.py:117 | Semantic search (uses admin_bp, not admin_api_bp) |

### 5. Documentation Naming Inconsistencies

| Documented | Actual | Location |
|------------|--------|----------|
| `article_feed(format)` | `feed_all()` and `feed_topic()` | feeds.py |
| `short_url(short_id)` | `short_url_redirect()` | links.py |
| `article_short(short_id)` | `short_url_tracking_page()` | links.py |
| `unsubscribe(token)` GET | `unsubscribe()` | subscribe.py |
| `unsubscribe(token)` POST | `unsubscribe_confirm()` | subscribe.py |

### 6. Shares Route Path Inconsistency

**Documentation (line 74):**
```
- `/admin/shares/add` - Add share config
```

**Actual (shares.py line 16):**
```python
@admin_bp.route("/shares/add", methods=["POST"])
def add_share() -> str | Response:
```

The route is `/admin/shares/add`, which matches documentation. However, this is listed under the `admin/shares/` section with a separate `- `/admin/shares/<id>/add`` entry, which creates confusion about whether these are separate sub-routes or part of the same pattern.

---

## Bugs

### Bug 1: Logout Method Mismatch

**Documentation (auth.py section):**
```python
@admin_bp.route('/logout')
def logout(): ...
```

**Actual Implementation (auth.py:188):**
```python
@admin_bp.route("/logout", methods=["POST"])
def logout() -> Response:
```

The documentation does not specify that logout requires POST method. This could cause confusion for developers expecting GET to work.

---

## Security Concerns

### 1. Logout Uses POST Only (Not a Bug, but Worth Documenting)

The logout endpoint only accepts POST requests. This is intentional security design (preventing CSRF on logout), but the documentation does not specify this constraint.

### 2. API Token Authentication is Correctly Documented

The documentation accurately describes the token format (`prefix + hash`) and storage approach.

---

## Improvements

### 1. Update File Structure in Documentation

The file structure section should be updated to include all actual files:
- Add `dashboard.py`
- Add `newsletters.py`
- Add `pipelines.py`
- Add `review.py`
- Add `subscribers.py`
- Add `shares.py`
- Add `topic_notes.py`
- Add `webhooks.py`
- Add `metrics.py`
- Add `trend_memory.py`
- Add `api/health.py`

### 2. Remove "not registered" from api_tokens.py Description

The statement that `api_tokens.py` is "not registered" is incorrect. Either remove this note or clarify what it means.

### 3. Document All Admin Routes

The admin routes section is incomplete. All routes from the following files should be documented:
- `articles.py` - all article management routes
- `sources.py` - source management routes
- `newsletters.py` - newsletter UI routes
- `pipelines.py` - pipeline management routes
- `review.py` - review queue routes
- `subscribers.py` - subscriber management routes
- `shares.py` - share config routes
- `topic_notes.py` - topic notes routes
- `webhooks.py` - webhook UI routes
- `metrics.py` - metrics dashboard
- `trend_memory.py` - trend memory UI routes
- `dashboard.py` - dashboard and dead-letters

### 4. Add Health API Documentation

The `api/health.py` file with `/api/v1/health`, `/api/v1/workers/health`, and `/api/v1/task/<task_id>` endpoints is completely undocumented.

### 5. Clarify Newsletter API Endpoints

The newsletter API endpoints (`/api/v1/newsletters/stats` and `/api/v1/newsletter/preview`) are not in the documented API table but exist in the implementation.

### 6. Document HTTP Methods for Admin Routes

The admin routes section lists routes without HTTP methods. For consistency and clarity, add methods (GET, POST, etc.) to each route.

### 7. Fix Template Structure Documentation

The template structure lists files that may not exist or be incomplete. Verify against actual `templates/` directory.

---

## Summary

The documentation is **partially accurate** but has significant gaps:

- **Core blueprint structure**: Correct
- **Public routes**: Mostly accurate with minor naming differences
- **Admin API routes**: Mostly accurate
- **Admin HTML routes**: Severely incomplete (most routes undocumented)
- **File structure**: Incomplete (missing ~11 files)
- **Security features**: Accurately documented

The most critical issues are:
1. Missing files in the documented structure
2. Missing admin routes documentation
3. Incorrect "not registered" claim for api_tokens.py
4. Missing health API endpoints
5. Missing newsletter API endpoints

A comprehensive rewrite of the routes documentation is recommended to reflect the actual implementation.

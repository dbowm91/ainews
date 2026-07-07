# Routes Module

The `routes/` package contains Flask blueprints for public and admin interfaces.

## Structure

```
routes/
├── public/                 # Public-facing routes
│   ├── feeds.py           # Article feeds, sitemap, RSS
│   ├── subscribe.py        # Subscription management
│   └── links.py           # Article detail, short URLs, share tracking
└── admin/                  # Admin interface
    ├── __init__.py        # Dashboard, login, dead-letters
    ├── auth.py            # Login with TOTP support
    ├── articles.py        # Article management UI
    ├── dashboard.py       # Dashboard + dead-letters page
    ├── newsletters.py     # Newsletter UI + API
    ├── pipelines.py       # Pipeline runs + trigger-crawl
    ├── review.py          # Article review queue
    ├── sources.py         # Source management UI
    ├── subscribers.py     # Subscriber management
    ├── shares.py          # Share config management
    ├── topic_notes.py     # Topic notes CRUD
    ├── webhooks.py        # Webhook UI
    ├── metrics.py         # Metrics dashboard
    ├── trend_memory.py    # Trend memory UI + API
    ├── api_tokens.py      # API token management
    └── api/               # Admin API endpoints
        ├── articles.py    # Article CRUD and pipeline control
        ├── sources.py     # Source management
        ├── pipeline.py    # Pipeline run control
        ├── search.py      # Search analytics
        ├── webhooks.py    # Webhook management
        ├── config.py      # Configuration management
        ├── audit.py       # Audit log access
        ├── health.py      # Health check endpoints
        ├── alerts.py      # Alerting API
        ├── newsletter.py  # Newsletter performance API
        ├── quality.py     # Quality report API
        ├── replay.py      # Pipeline replay API
        ├── source_intelligence.py  # Source intelligence API
        ├── topic_gap.py   # Topic gap analysis API
        └── utils.py       # API utility functions
```

## Blueprint Structure

The application uses two distinct blueprint types with separate URL namespaces:

| Blueprint | URL Prefix | Content Type | Auth Method |
|-----------|------------|--------------|-------------|
| `public_bp` | `/` | HTML pages | None |
| `admin_bp` | `/admin` | HTML pages | Session-based |
| `admin_api_bp` | `/api/v1` | JSON API | Session or Bearer token |

### Admin Blueprint (`admin_bp`)

Serves HTML admin pages at `/admin/*`:
- `/admin/login` [GET/POST] - Admin login page
- `/admin/` [GET] - Main dashboard (redirects to articles)
- `/admin/articles` [GET] - Article management UI
- `/admin/articles/<id>/edit` [GET/POST] - Article edit page
- `/admin/articles/<id>/original` [GET] - Original article view
- `/admin/articles/<id>/versions` [GET] - Article version history
- `/admin/articles/<id>/versions/<version_id>/rollback` [POST] - Rollback article to version
- `/admin/articles/<id>/delete` [POST] - Article delete action
- `/admin/articles/<id>/reprocess` [POST] - Article reprocess action
- `/admin/sources` [GET] - Source management UI
- `/admin/sources/<id>/enable` [POST] - Enable source action
- `/admin/sources/<id>/disable` [POST] - Disable source action
- `/admin/subscribers` [GET] - Subscriber management UI
- `/admin/subscribers/export` [GET] - Export subscribers
- `/admin/newsletters` [GET] - Newsletter history UI
- `/admin/newsletters/<id>` [GET] - Newsletter detail view
- `/admin/newsletters/generate` [POST] - Trigger newsletter generation
- `/admin/newsletters/dry-run` [POST] - Newsletter dry run
- `/admin/dead-letters` [GET] - Dead letter queue UI
- `/admin/pipelines` [GET] - Pipeline run history
- `/admin/pipelines/<run_id>/logs` [GET] - Pipeline run logs
- `/admin/trigger-crawl` [POST] - Manual crawl trigger
- `/admin/sources/add` [POST] - Add new source
- `/admin/trend-memory` [GET] - Trend memory management UI
- `/admin/trend-memory/delete/<id>` [POST] - Delete trend memory entry
- `/admin/trend-memory/delete-expired` [POST] - Delete expired trend memory entries
- `/admin/api/trend-memory/semantic-search` [GET] - Semantic search in trend memory
- `/admin/review` [GET] - Article review queue
- `/admin/review/<id>/approve` [POST] - Approve article action
- `/admin/review/<id>/reject` [POST] - Reject article action
- `/admin/topic-notes` [GET] - Topic notes management
- `/admin/topic-notes/create` [POST] - Create topic note
- `/admin/topic-notes/edit` [POST] - Edit topic note
- `/admin/topic-notes/delete` [POST] - Delete topic note
- `/admin/topic-notes/row/<topic>` [GET] - Topic note row
- `/admin/webhooks` [GET] - Webhook management UI
- `/admin/shares` [GET] - Share config management
- `/admin/shares/<id>/edit-form` [GET] - Edit share config form
- `/admin/shares/<id>/row` [GET] - Share config row
- `/admin/shares/add` [POST] - Add share config
- `/admin/shares/<id>/edit` [POST] - Edit share config
- `/admin/shares/<id>/delete` [POST] - Delete share config
- `/admin/shares/<id>/toggle` [POST] - Toggle share config
- `/admin/metrics` [GET] - Metrics dashboard
- `/admin/verify-2fa` [GET/POST] - 2FA verification page
- `/admin/setup-2fa` [GET/POST] - 2FA setup page
- `/admin/logout` [POST] - Logout action (POST only)

### Admin API Blueprint (`admin_api_bp`)

Serves JSON REST API at `/api/v1/*`. Detailed endpoint table with HTTP methods:

| Endpoint | Methods | Purpose |
|----------|---------|---------|
| `/articles/ids` | GET | Batch article ID lookup with filters |
| `/articles/counts-by-status` | GET | Article count by pipeline status |
| `/articles/<id>` | GET, PUT, DELETE | Article CRUD |
| `/articles/<id>/pipeline` | POST | Trigger pipeline stage |
| `/articles/bulk` | POST | Bulk article operations |
| `/sources` | GET, POST | List/create sources |
| `/sources/<id>` | GET, PUT, PATCH, DELETE | Source CRUD |
| `/sources/<id>/refresh` | POST | Force source refresh |
| `/sources/health` | GET | Source health status |
| `/pipeline/stats` | GET | Pipeline stage statistics |
| `/pipeline/backlog` | GET | Pipeline backlog |
| `/pipeline/dead-letter/stats` | GET | Dead letter queue stats |
| `/pipeline/sla` | GET | SLA metrics |
| `/costs` | GET | LLM cost summary |
| `/webhooks` | GET, POST | List/create webhooks |
| `/webhooks/<id>` | GET, PUT, PATCH, DELETE | Webhook CRUD |
| `/webhooks/<id>/test` | POST | Test webhook delivery |
| `/webhooks/<id>/events` | GET | Webhook delivery events |
| `/webhooks/events/<id>/resend` | POST | Resend webhook event |
| `/search/analytics` | GET | Search analytics |
| `/config/reload` | POST | Reload configuration |
| `/metrics` | GET | Application metrics |
| `/metrics/prometheus` | GET | Prometheus-formatted metrics |
| `/audit-logs` | GET | Audit log entries |
| `/alerts` | GET | Active alerts grouped by severity |
| `/sources/performance` | GET | Source performance metrics |
| `/topics/coverage` | GET | Topic coverage distribution |
| `/sources/recommendations` | GET | Source improvement recommendations |
| `/topic-gap/reports` | GET | Topic gap analysis reports |
| `/articles/<id>/quality` | GET | Latest quality report for article |
| `/quality/recent` | GET | Recent quality reports with filtering |
| `/articles/<id>/pipeline/history` | GET | Pipeline history for article |
| `/articles/<id>/pipeline/replay` | POST | Replay article from specific stage |
| `/articles/<id>/pipeline/restore-version` | POST | Restore article to previous version |
| `/newsletters/stats` | GET | Newsletter performance metrics |
| `/newsletter/preview` | POST | Generate newsletter HTML preview without sending (file: `routes/admin/newsletters.py:221`) |
| `/search/articles` | GET | Article search with hybrid mode |

**Note:** The `api_tokens_bp` blueprint is registered in `app.py` without a `url_prefix` — routes include the full `/api-tokens` path.

## Public Routes

### Feeds (`public/feeds.py`)

```python
public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def index(): ...

@public_bp.route('/topic/<category>')
def topic_feed(category): ...

@public_bp.route('/tag/<slug>')
def tag_feed(slug): ...

@public_bp.route('/feed')
@public_bp.route('/feed/<category>')
def article_feed(format): ...  # atom, rss, json

@public_bp.route('/sitemap.xml')
def sitemap(): ...
```

### Subscribe (`public/subscribe.py`)

Subscription management with verification:

```python
@subscribe_bp.route('/subscribe', methods=['POST'])
def subscribe(): ...  # New subscription

@subscribe_bp.route('/verify/<token>')
def verify(token): ...  # Email verification

@subscribe_bp.route('/unsubscribe/<token>')
@subscribe_bp.route('/unsubscribe/<token>', methods=['POST'])
def unsubscribe(token): ...  # One-click unsubscribe
```

### Links (`public/links.py`)

Article routing and tracking:

```python
@public_bp.route("/article/<int:article_id>")
def article_detail(article_id): ...

@public_bp.route("/s/<short_id>")
def short_url_redirect(short_id): ...  # Short URL redirect

@public_bp.route("/a/<short_id>")
def short_url_tracking_page(short_id): ...  # Article short URL with share tracking

@public_bp.route("/api/v1/track/share-click/<int:article_id>", methods=["POST"])
def track_share_click(article_id): ...

@public_bp.route("/track/newsletter-click/<int:article_id>")
def track_newsletter_click(article_id): ...
```

### Health Check

```python
@public_bp.route("/health")
def health(): ...
```

### Admin API (`admin_api_bp`)

JSON REST API at `/api/v1/*`:

#### Articles
- `GET /api/v1/articles/ids` - Get article IDs by status (returns `{ids: [...], count: n}`)
- `GET /api/v1/articles/counts-by-status` - Get article counts by status
- `POST /api/v1/articles/bulk` - Bulk article operations
- `GET /api/v1/articles/<id>` - Get single article
- `PUT /api/v1/articles/<id>` - Update article
- `DELETE /api/v1/articles/<id>` - Delete article
- `POST /api/v1/articles/<id>/pipeline` - Trigger pipeline for article

#### Sources
- `GET /api/v1/sources` - List sources
- `POST /api/v1/sources` - Create source
- `GET /api/v1/sources/<id>` - Get single source
- `PUT /api/v1/sources/<id>` - Update source
- `PATCH /api/v1/sources/<id>` - Partial update source
- `DELETE /api/v1/sources/<id>` - Delete source
- `POST /api/v1/sources/<id>/refresh` - Trigger source refresh

#### Pipeline
- `GET /api/v1/pipeline/stats` - Pipeline statistics
- `GET /api/v1/pipeline/dead-letter/stats` - Dead letter stats
- `GET /api/v1/pipeline/backlog` - Pipeline backlog
- `GET /api/v1/costs` - Cost tracking
- `GET /api/v1/sources/health` - Source health overview
- `GET /api/v1/pipeline/sla` - SLA metrics

#### Newsletters
- `GET /api/v1/newsletters/stats` - Newsletter performance metrics (sent/failed/click counts, top articles, subscriber counts by type)
- `POST /api/v1/newsletter/preview` - Generate newsletter HTML preview without sending emails (file: `routes/admin/newsletters.py:221`)

#### Quality
- `GET /api/v1/articles/<id>/quality` - Latest quality report for an article (scores, findings by severity)
- `GET /api/v1/quality/recent` - Recent quality reports (filterable by `passed`, `needs_review`, `limit`)

#### Alerts
- `GET /api/v1/alerts` - Active alerts grouped by severity (critical/warning/info); also dispatches critical alerts via webhooks

#### Source Intelligence
- `GET /api/v1/sources/performance` - Source performance metrics within time window (query: `days`, `limit`)
- `GET /api/v1/topics/coverage` - Topic coverage distribution across sources (query: `days`)
- `GET /api/v1/sources/recommendations` - Actionable source recommendations (query: `days`)

#### Topic Gap
- `GET /api/v1/topic-gap/reports` - Topic gap analysis reports (query: `topics`, `days`)

#### Pipeline Replay
- `GET /api/v1/articles/<id>/pipeline/history` - Pipeline log history for an article
- `POST /api/v1/articles/<id>/pipeline/replay` - Replay article from a specific stage (body: `stage`, `reason`, optional `provider_id`/`model`)
- `POST /api/v1/articles/<id>/pipeline/restore-version` - Restore article to a previous version (body: `version_id`)

#### Search
- `GET /api/v1/search/articles` - Article search with hybrid mode (query: `q`, `mode` [fts/hybrid], `category`, `page`, `per_page`)

#### Webhooks
- `GET /api/v1/webhooks` - List webhooks
- `POST /api/v1/webhooks` - Create webhook
- `GET /api/v1/webhooks/<id>` - Get webhook
- `PUT /api/v1/webhooks/<id>` - Update webhook
- `DELETE /api/v1/webhooks/<id>` - Delete webhook
- `POST /api/v1/webhooks/<id>/test` - Test webhook
- `GET /api/v1/webhooks/<id>/events` - Get webhook events
- `POST /api/v1/webhooks/events/<id>/resend` - Resend event

#### Config
- `POST /api/v1/config/reload` - Reload configuration
- `GET /api/v1/metrics` - Application metrics
- `GET /api/v1/metrics/prometheus` - Prometheus metrics

#### Health
- `GET /api/v1/health` - Detailed health check
- `GET /api/v1/workers/health` - Celery workers health
- `GET /api/v1/task/<task_id>` - Task status

#### Audit & Search
- `GET /api/v1/audit-logs` - Audit log query
- `GET /api/v1/search/analytics` - Search analytics

### API Tokens (`api_tokens_bp`)

Note: This blueprint is registered in `app.py` and provides `/api-tokens` endpoints (not `/api/v1`):
- `GET /api-tokens` - List non-revoked API tokens
- `POST /api-tokens` - Create API token (returns full token once, accepts optional `name` and `expires_in`)
- `DELETE /api-tokens/<id>` - Delete API token (hard delete)

Token format: `ak_<prefix>.<secret>`. Only the hashed secret is stored. Tokens are returned once at creation and cannot be retrieved again.

**Note:** `/share/<platform>/<article_id>` is not implemented as a server endpoint. Social sharing is handled client-side via JavaScript.

## Admin Routes

### Dashboard

Admin dashboard at `/admin/` with sections for:
- Overview statistics
- Recent pipeline runs
- Source health
- Subscriber growth

### Authentication (`admin/auth.py`)

Session-based auth with security features:

```python
@admin_bp.route('/login', methods=['GET', 'POST'])
def login(): ...

@admin_bp.route('/logout', methods=['POST'])
def logout(): ...
```

**Security features:**
- TOTP 2FA support
- 8 backup codes for account recovery
- Session hijacking protection (IP + User-Agent binding)
- Login lockout via Redis (with in-memory fallback)

**Auth enforcement architecture (`routes/decorators.py`):**
- `authenticate_request()` — standalone helper returning `None` on success or a Flask response tuple on failure. Used by both the decorator and blueprint `before_request` hooks.
- `require_auth` decorator — wraps individual route functions. Must be placed AFTER `@blueprint.route(...)` (innermost) so Flask registers the authenticated wrapper.
- Blueprint-level `before_request` — defense-in-depth guard on blueprints where ALL routes require auth (e.g., `api_tokens_bp`).

**Decorator ordering rule:** `@blueprint.route(...)` must always be outermost (closest to `def`), followed by auth/CSRF decorators. Wrong order means Flask sees the unwrapped function and the endpoint is unprotected.

### API Endpoints (`admin/api/`)

Note: Endpoints are registered at `/api/v1/` prefix (e.g., `/api/v1/articles`, not `/articles`).

## Template Structure

Templates use a flat directory structure under `templates/`:

```
templates/
├── base.html              # Base layout for public pages
├── base_admin.html        # Base layout for admin pages
├── admin/                 # Admin templates (flat)
│   ├── dashboard.html     # Main dashboard
│   ├── login.html         # Admin login page
│   ├── articles.html      # Article list
│   ├── article_edit.html  # Article editor
│   ├── article_versions.html # Article version history
│   ├── sources.html       # Source management
│   ├── subscribers.html   # Subscriber management
│   ├── newsletters.html   # Newsletter history
│   ├── pipelines.html     # Pipeline run history
│   ├── pipeline_logs.html # Pipeline run logs
│   ├── review.html        # Article review queue
│   ├── topic_notes.html   # Topic notes management
│   ├── shares.html        # Share config management
│   ├── webhooks.html      # Webhook management UI
│   ├── trend_memory.html  # Trend memory management
│   ├── metrics.html       # Metrics dashboard
│   ├── dead_letters.html  # Dead letter queue
│   ├── setup_2fa.html     # 2FA setup page
│   ├── verify_2fa.html    # 2FA verification page
│   └── partials/          # Admin partial templates
│       ├── articles_table.html
│       ├── source_row.html
│       ├── topic_note_row.html
│       ├── share_row.html
│       ├── share_edit_form.html
│       ├── review_table.html
│       ├── webhook_events.html
│       └── empty_state.html
├── partials/              # Public partial templates
├── errors/                # Error pages (404, 500, 429)
├── macros/                # Jinja macros
├── article.html           # Article detail page
├── index.html             # Home page
├── topic.html             # Topic feed page
├── tag.html               # Tag feed page
├── verify.html            # Email verification page
├── unsubscribe.html       # Unsubscribe page
└── share_redirect.html    # Share redirect page
```

## Security

### Session Hijacking Protection

```python
# On each request:
# Session binding validates BOTH IP address AND User-Agent header
if session['ip'] != request.ip or session['user_agent'] != request.user_agent:
    # Force re-login
```

**Session binding** validates both the client's IP address and User-Agent header to prevent session hijacking. If either changes mid-session, the user is forced to re-authenticate.

### API Token Authentication

Admin API supports Bearer token auth:

```python
# Header: Authorization: Bearer ak_<prefix>.<secret>
# Token format: ak_<prefix>.<secret>
# Only hashed secret stored — raw token returned once at creation
# Prefix (first 12 chars of secret) used for DB lookup
# Expiration and revocation enforced during verification
```

### CSRF Protection

API blueprints (`admin_api_bp` at `/api/v1/*`, `api_tokens_bp` at `/api-tokens/*`) are exempted from Flask-WTF's global CSRF. Bearer-token requests bypass CSRF entirely.

For non-exempted routes, per-route decorators handle CSRF policy:

- **`@validate_csrf_json`**: Validates `X-CSRFToken` header for session-authenticated JSON endpoints. Returns controlled JSON 400 on invalid CSRF (never propagates exceptions). Used on HTML form/HTMX routes.
- **`@csrf_for_session_auth`**: Like `@validate_csrf_json` but skips CSRF for verified bearer-token requests (uses `g.auth_mode` set by `authenticate_request()`). Returns 401 if auth has not run. Used on all JSON API mutating routes.
- **Form-based routes**: Flask-WTF's built-in CSRF handles forms automatically.

`api_tokens_bp` uses blueprint-level `before_request` for auth — no duplicate `@require_auth` on individual routes.

```python
# Header: X-CSRFToken: <token>
# Decorator: @csrf_for_session_auth (routes/decorators.py)
# Uses g.auth_mode from authenticate_request() to determine auth mode
```

### Rate Limiting

Admin login routes have explicit rate limits via `extensions.limiter` (`@limiter.limit("10 per minute")`). Other admin routes rely on the **global default limit of 60 per minute**, configurable via `RATELIMIT_DEFAULT` env var.

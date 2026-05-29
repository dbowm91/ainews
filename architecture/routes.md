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
def short_url(short_id): ...  # Short URL redirect

@public_bp.route("/a/<short_id>")
def article_short(short_id): ...  # Article short URL

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
- `GET /api/v1/newsletters/stats` - Newsletter delivery stats
- `POST /api/v1/newsletter/preview` - Preview newsletter

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
- `GET /api-tokens` - List API tokens
- `POST /api-tokens` - Create API token
- `DELETE /api-tokens/<id>` - Revoke API token

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

### API Endpoints (`admin/api/`)

Note: Endpoints are registered at `/api/v1/` prefix (e.g., `/api/v1/articles`, not `/articles`).

## Template Structure

Templates use a flat directory structure under `templates/`:

```
templates/
├── admin/                 # Admin templates (flat)
│   ├── dashboard.html     # Main dashboard
│   ├── articles.html      # Article list
│   ├── article_edit.html  # Article editor
│   ├── sources.html       # Source management
│   ├── newsletters.html   # Newsletter history
│   └── partials/          # Admin partial templates
├── partials/              # Public partial templates
├── errors/                # Error pages (404, 500, 429)
├── macros/                # Jinja macros
├── article.html           # Article detail page
├── index.html             # Home page
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

Admin API supports token auth:

```python
# Header: Authorization: Bearer <token>
# Token stored as: prefix + hash (never plaintext)
# Prefix is first 16 characters of the hash for lookup
```

### CSRF Protection

All state-changing routes protected via Flask-WTF tokens. JSON API endpoints use the `X-CSRFToken` header:

```python
# Header: X-CSRFToken: <token>
# Decorator: @validate_csrf_json (routes/decorators.py:72-94)
# Validates X-CSRFToken header for JSON endpoints (Flask-WTF only handles form/multipart)
# Respects WTF_CSRF_ENABLED = False in TestingConfig
```

### Rate Limiting

Admin login routes have explicit rate limits via `extensions.limiter` (`@limiter.limit("10 per minute")`). Other admin routes rely on the **global default limit of 60 per minute**, configurable via `RATELIMIT_DEFAULT` env var.

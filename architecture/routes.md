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
    ├── __init__.py        # Dashboard, articles, sources, subscribers, newsletters
    ├── auth.py            # Login with TOTP support
    ├── api_tokens.py      # API token management (not registered)
    └── api/               # Admin API endpoints
        ├── articles.py    # Article CRUD and pipeline control
        ├── sources.py     # Source management
        ├── pipeline.py    # Pipeline run control
        ├── search.py      # Search analytics
        ├── webhooks.py    # Webhook management
        ├── config.py      # Configuration management
        └── audit.py       # Audit log access
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
- `/admin/login` - Admin login page
- `/admin/` - Main dashboard (redirects to articles)
- `/admin/articles` - Article management UI
- `/admin/articles/<id>/edit` - Article edit page
- `/admin/articles/<id>/original` - Original article view
- `/admin/articles/<id>/versions` - Article version history
- `/admin/articles/<id>/versions/<version_id>/rollback` - Rollback article to version
- `/admin/articles/<id>/delete` - Article delete action
- `/admin/articles/<id>/reprocess` - Article reprocess action
- `/admin/sources` - Source management UI
- `/admin/sources/<id>/enable` - Enable source action
- `/admin/sources/<id>/disable` - Disable source action
- `/admin/subscribers` - Subscriber management UI
- `/admin/subscribers/export` - Export subscribers
- `/admin/newsletters` - Newsletter history UI
- `/admin/newsletters/<id>` - Newsletter detail view
- `/admin/newsletters/generate` - Trigger newsletter generation
- `/admin/newsletters/dry-run` - Newsletter dry run
- `/admin/dead-letters` - Dead letter queue UI
- `/admin/pipelines` - Pipeline run history
- `/admin/pipelines/<run_id>/logs` - Pipeline run logs
- `/admin/pipelines/trigger-crawl` - Manual crawl trigger
- `/admin/review` - Article review queue
- `/admin/review/<id>/approve` - Approve article action
- `/admin/review/<id>/reject` - Reject article action
- `/admin/topic-notes` - Topic notes management
- `/admin/topic-notes/create` - Create topic note
- `/admin/topic-notes/edit` - Edit topic note
- `/admin/topic-notes/delete` - Delete topic note
- `/admin/topic-notes/row/<topic>` - Topic note row
- `/admin/webhooks` - Webhook management UI
- `/admin/shares` - Share config management
- `/admin/shares/<id>/edit-form` - Edit share config form
- `/admin/shares/<id>/row` - Share config row
- `/admin/shares/add` - Add share config
- `/admin/shares/<id>/edit` - Edit share config
- `/admin/shares/<id>/delete` - Delete share config
- `/admin/shares/<id>/toggle` - Toggle share config
- `/admin/metrics` - Metrics dashboard
- `/admin/verify-2fa` - 2FA verification page
- `/admin/setup-2fa` - 2FA setup page
- `/admin/logout` - Logout action

### Admin API Blueprint (`admin_api_bp`)

Serves JSON REST API at `/api/v1/*`:
- `/api/v1/articles` - Article CRUD
- `/api/v1/sources` - Source CRUD
- `/api/v1/pipeline/stats` - Pipeline statistics
- `/api/v1/webhooks` - Webhook management
- `/api/v1/metrics` - Prometheus metrics
- `/api/v1/costs` - Cost tracking
- `/api-tokens` - API token management (list, create, delete)

**Note:** The `api_tokens_bp` blueprint is registered in `app.py` and provides `/api-tokens` endpoints.

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

@admin_bp.route('/logout')
def logout(): ...
```

**Security features:**
- TOTP 2FA support
- 8 backup codes for account recovery
- Session hijacking protection (IP + User-Agent binding)
- Login lockout via Redis (with in-memory fallback)

### API Endpoints (`admin/api/`)

Note: Endpoints are registered at `/api/v1/` prefix (e.g., `/api/v1/articles`, not `/articles`).

| Endpoint | Methods | Purpose |
|----------|---------|---------|
| `/articles` | GET | List articles |
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
| `/api/trend-memory/semantic-search` | GET | Semantic search in trend memory |

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
if session['ip'] != request.ip or session['ua'] != request.ua:
    # Force re-login
```

### API Token Authentication

Admin API supports token auth:

```python
# Header: Authorization: Bearer <token>
# Token stored as: prefix + hash (never plaintext)
# Prefix is first 16 characters of the hash for lookup
```

### CSRF Protection

All state-changing routes protected via Flask-WTF tokens.

### Rate Limiting

Admin routes have stricter rate limits via `extensions.limiter`.

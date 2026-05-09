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
- `/admin/` - Main dashboard
- `/admin/articles` - Article management UI
- `/admin/sources` - Source management UI
- `/admin/subscribers` - Subscriber management UI
- `/admin/newsletters` - Newsletter history UI

### Admin API Blueprint (`admin_api_bp`)

Serves JSON REST API at `/api/v1/*`:
- `/api/v1/articles` - Article CRUD
- `/api/v1/sources` - Source CRUD
- `/api/v1/pipeline/stats` - Pipeline statistics
- `/api/v1/webhooks` - Webhook management
- `/api/v1/metrics` - Prometheus metrics
- `/api/v1/costs` - Cost tracking

**Note:** The `api_tokens_bp` blueprint exists in `routes/admin/api_tokens.py` but is NOT registered in `app.py`. All `/api-tokens` routes return 404.

## Public Routes

### Feeds (`public/feeds.py`)

```python
feeds_bp = Blueprint('feeds', __name__)

@feeds_bp.route('/sitemap.xml')
def sitemap(): ...

@feeds_bp.route('/feed/<format>')
def article_feed(format): ...  # atom, rss, json

@feeds_bp.route('/articles')
def article_list(): ...
```

### Subscribe (`public/subscribe.py`)

Subscription management with verification:

```python
subscribe_bp = Blueprint('subscribe', __name__)

@subscribe_bp.route('/subscribe', methods=['POST'])
def subscribe(): ...  # New subscription

@subscribe_bp.route('/verify/<token>')
def verify(token): ...  # Email verification

@subscribe_bp.route('/unsubscribe/<token>')
def unsubscribe(token): ...  # One-click unsubscribe
```

### Links (`public/links.py`)

Article routing and tracking:

```python
public_bp = Blueprint('links', __name__)

@public_bp.route('/a/<short_id>')
def article_short(short_id): ...  # Short URL redirect (also /s/<short_id>)

@public_bp.route("/track/newsletter-click/<int:article_id>")
def track_newsletter_click(article_id): ...  # Newsletter click tracking
```

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

Note: Endpoints are registered at root level (e.g., `/articles`, not `/api/v1/articles`).

| Endpoint | Methods | Purpose |
|----------|---------|---------|
| `/articles` | GET, POST | List/create articles |
| `/articles/<id>` | GET, PUT, DELETE | Article CRUD |
| `/articles/<id>/pipeline` | POST | Trigger pipeline stage |
| `/articles/bulk` | POST | Bulk article operations |
| `/sources` | GET, POST | List/create sources |
| `/sources/<id>` | GET, PUT, PATCH, DELETE | Source CRUD |
| `/sources/<id>/refresh` | POST | Force source refresh |
| `/pipeline/stats` | GET | Pipeline statistics |
| `/pipeline/backlog` | GET | Pipeline backlog |
| `/pipeline/dead-letter/stats` | GET | Dead letter queue stats |
| `/pipeline/sla` | GET | SLA metrics |
| `/webhooks` | GET, POST | List/create webhooks |
| `/webhooks/<id>/test` | POST | Test webhook delivery |
| `/webhooks/<id>/events` | GET | Webhook delivery events |
| `/config/reload` | POST | Reload configuration |
| `/audit-logs` | GET | Audit log entries |
| `/metrics` | GET | Prometheus metrics |

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
```

### CSRF Protection

All state-changing routes protected via Flask-WTF tokens.

### Rate Limiting

Admin routes have stricter rate limits via `extensions.limiter`.

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
    ├── api_tokens.py      # API token management
    └── api/               # Admin API endpoints
        ├── articles.py    # Article CRUD and pipeline control
        ├── sources.py     # Source management
        ├── pipeline.py    # Pipeline run control
        ├── search.py      # Search analytics
        ├── webhooks.py    # Webhook management
        ├── config.py      # Configuration management
        └── audit.py       # Audit log access
```

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
def article_short(short_id): ...  # Short URL redirect

@public_bp.route("/track/newsletter-click/<int:article_id>")
def track_newsletter_click(article_id): ...  # Newsletter click tracking
```

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

| Endpoint | Methods | Purpose |
|----------|---------|---------|
| `/api/v1/articles` | GET, POST | List/create articles |
| `/api/v1/articles/<id>` | GET, PUT, DELETE | Article CRUD |
| `/api/v1/articles/<id>/pipeline` | POST | Trigger pipeline stage |
| `/api/v1/sources` | GET, POST | List/create sources |
| `/api/v1/sources/<id>` | GET, PUT, DELETE | Source CRUD |
| `/api/v1/sources/<id>/refresh` | POST | Force source refresh |
| `/api/v1/pipeline/stats` | GET | Pipeline statistics |
| `/api/v1/pipeline/backlog` | GET | Pipeline backlog |
| `/api/v1/webhooks` | GET, POST | List/create webhooks |
| `/api/v1/webhooks/<id>/test` | POST | Test webhook delivery |
| `/api/v1/config/reload` | POST | Reload configuration |
| `/api/v1/audit-logs` | GET | Audit log entries |

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

# Routes Module Architecture Review

This document reviews the claims in `architecture/routes.md` against the actual implementation in the codebase.

---

## Verified Correct

### Blueprint URL Prefixes
- **admin_bp** at `/admin` - **CORRECT** (`routes/admin/__init__.py:14`)
- **admin_api_bp** at `/api/v1` - **CORRECT** (`routes/admin/__init__.py:15`)
- **public_bp** at `/` - **CORRECT** (`routes/public/__init__.py:26`)

### Blueprint Registration (app.py:188-197)
All four blueprints are registered:
```python
app.register_blueprint(public_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(admin_api_bp)
app.register_blueprint(api_tokens_bp)  # <-- NOW REGISTERED
```

### Admin API Endpoints - Verified Present
| Endpoint | File | Methods | Verified |
|----------|------|---------|----------|
| `/articles/ids` | `routes/admin/api/articles.py:152` | GET | ✓ |
| `/articles/counts-by-status` | `routes/admin/api/articles.py:171` | GET | ✓ |
| `/articles/bulk` | `routes/admin/api/articles.py:470` | POST | ✓ |
| `/articles/<id>/pipeline` | `routes/admin/api/articles.py:528` | POST | ✓ |
| `/articles/<id>` | `routes/admin/api/articles.py:597,620,673` | GET, PUT, DELETE | ✓ |
| `/sources` | `routes/admin/api/sources.py:16,48` | GET, POST | ✓ |
| `/sources/<id>` | `routes/admin/api/sources.py:123,154,225,314` | GET, PUT, PATCH, DELETE | ✓ |
| `/sources/<id>/refresh` | `routes/admin/api/sources.py:342` | POST | ✓ |
| `/sources/health` | `routes/admin/api/pipeline.py:161` | GET | ✓ |
| `/pipeline/stats` | `routes/admin/api/pipeline.py:13` | GET | ✓ |
| `/pipeline/backlog` | `routes/admin/api/pipeline.py:87` | GET | ✓ |
| `/pipeline/dead-letter/stats` | `routes/admin/api/pipeline.py:48` | GET | ✓ |
| `/pipeline/sla` | `routes/admin/api/pipeline.py:187` | GET | ✓ |
| `/costs` | `routes/admin/api/pipeline.py:135` | GET | ✓ |
| `/webhooks` | `routes/admin/api/webhooks.py:56,90` | GET, POST | ✓ |
| `/webhooks/<id>` | `routes/admin/api/webhooks.py:165,209,269` | GET, PUT/PATCH, DELETE | ✓ |
| `/webhooks/<id>/test` | `routes/admin/api/webhooks.py:297` | POST | ✓ |
| `/webhooks/<id>/events` | `routes/admin/api/webhooks.py:321` | GET | ✓ |
| `/webhooks/events/<id>/resend` | `routes/admin/api/webhooks.py:363` | POST | ✓ |
| `/search/analytics` | `routes/admin/api/search.py:9` | GET | ✓ |
| `/config/reload` | `routes/admin/api/config.py:13` | POST | ✓ |
| `/metrics` | `routes/admin/api/config.py:52` | GET | ✓ |
| `/metrics/prometheus` | `routes/admin/api/config.py:60` | GET | ✓ |
| `/audit-logs` | `routes/admin/api/audit.py:11` | GET | ✓ |
| `/health` | `routes/admin/api/health.py:17` | GET | ✓ |
| `/workers/health` | `routes/admin/api/health.py:54` | GET | ✓ |
| `/task/<task_id>` | `routes/admin/api/health.py:102` | GET | ✓ |

### Public Routes - Verified Present
| Route | File | Verified |
|-------|------|----------|
| `/` (index) | `routes/public/feeds.py:73` | ✓ |
| `/topic/<category>` | `routes/public/feeds.py:122` | ✓ |
| `/tag/<slug>` | `routes/public/feeds.py:171` | ✓ |
| `/feed` | `routes/public/feeds.py:222` | ✓ |
| `/feed/<category>` | `routes/public/feeds.py:259` | ✓ |
| `/sitemap.xml` | `routes/public/feeds.py:308` | ✓ |
| `/subscribe` (POST only) | `routes/public/subscribe.py:31` | ✓ |
| `/verify/<token>` | `routes/public/subscribe.py:183` | ✓ |
| `/unsubscribe/<token>` | `routes/public/subscribe.py:137,153` | ✓ GET+POST |
| `/article/<int:article_id>` | `routes/public/links.py:24` | ✓ |
| `/s/<short_id>` | `routes/public/links.py:94` | ✓ |
| `/a/<short_id>` | `routes/public/links.py:103` | ✓ |
| `/track/newsletter-click/<int:article_id>` | `routes/public/links.py:130` | ✓ |
| `/api/v1/track/share-click/<int:article_id>` | `routes/public/links.py:123` | ✓ POST |
| `/health` | `routes/public/__init__.py:111` | ✓ |

### Authentication Security Features (Verified)
- **TOTP 2FA support** - `routes/admin/auth.py` - `verify_token()` from `services/totp.py`
- **8 backup codes** - `routes/admin/auth.py:126` - `verify_backup_code()` and `consume_backup_code()`
- **Session hijacking protection (IP + User-Agent binding)** - `routes/admin/__init__.py:75-86`
- **Login lockout via Redis (with in-memory fallback)** - `routes/admin/__init__.py:104-303`
- **Login rate limit** - `routes/admin/auth.py:44` - `@limiter.limit("10 per minute")`

### CSRF Protection (Verified)
- **Flask-WTF tokens** - `validate_csrf_json` decorator in `routes/decorators.py`
- All state-changing API routes use `@validate_csrf_json` decorator
- Public form submissions use Flask-WTF form tokens

### Admin HTML Pages (Verified)
| Page | Route | File |
|------|-------|------|
| Login | `/admin/login` | `routes/admin/auth.py:43` |
| Dashboard | `/admin/` | `routes/admin/dashboard.py:192` |
| Articles | `/admin/articles` | `routes/admin/articles.py:221` |
| Sources | `/admin/sources` | `routes/admin/sources.py:26` |
| Subscribers | `/admin/subscribers` | `routes/admin/subscribers.py:7` |
| Newsletters | `/admin/newsletters` | (via `routes/admin/__init__.py` import) |
| Webhooks | `/admin/webhooks` | (via `routes/admin/__init__.py` import) |
| Dead Letters | `/admin/dead-letters` | `routes/admin/dashboard.py:13` |
| Metrics | `/admin/metrics` | `routes/admin/metrics.py:10` |
| Article Edit | `/admin/articles/<id>/edit` | `routes/admin/articles.py:385` |
| Article Versions | `/admin/articles/<id>/versions` | `routes/admin/articles.py:440` |
| Verify 2FA | `/admin/verify-2fa` | `routes/admin/auth.py:97` |
| Setup 2FA | `/admin/setup-2fa` | `routes/admin/auth.py:151` |
| Pipeline Logs | `/admin/pipeline-logs` | (imported in `__init__.py`) |
| Review | `/admin/review` | (imported in `__init__.py`) |
| Shares | `/admin/shares` | (imported in `__init__.py`) |
| Topic Notes | `/admin/topic-notes` | (imported in `__init__.py`) |
| Trend Memory | `/admin/trend-memory` | (imported in `__init__.py`) |

### Template Structure (Verified)
```
templates/
├── admin/
│   ├── dashboard.html
│   ├── articles.html
│   ├── article_edit.html
│   ├── sources.html
│   ├── newsletters.html
│   ├── subscribers.html
│   ├── webhooks.html
│   ├── metrics.html
│   ├── dead_letters.html
│   ├── verify_2fa.html
│   ├── setup_2fa.html
│   ├── shares.html
│   ├── topic_notes.html
│   ├── trend_memory.html
│   ├── pipeline_logs.html
│   ├── review.html
│   ├── article_versions.html
│   └── partials/
├── partials/
├── errors/
├── macros/
├── article.html
├── index.html
├── topic.html
├── tag.html
├── share_redirect.html
├── unsubscribe.html
└── verify.html
```

---

## Discrepancies and Documentation Bugs

### 1. `api_tokens_bp` Registration - **OUTDATED DOCUMENTATION**

**Document says (line 57):**
> **Note:** The `api_tokens_bp` blueprint exists in `routes/admin/api_tokens.py` but is NOT registered in `app.py`. All `/api-tokens` routes return 404.

**Actual code (`app.py:188-197`):**
The `api_tokens_bp` IS registered. The `/api-tokens` routes work.

**Fix needed:** Remove the "not registered" note from the documentation.

### 2. Blueprint Naming - `feeds_bp` vs `public_bp`

**Document says (line 64):**
```python
feeds_bp = Blueprint('feeds', __name__)
```

**Actual code (`routes/public/__init__.py:26`):**
```python
public_bp = Blueprint("public", __name__)
```

The blueprint is `public_bp`. Minor naming discrepancy.

### 3. Missing `POST /articles` Endpoint

**Document says (line 143):**
> | `/articles` | GET, POST | List/create articles |

**Actual code:** There is NO `POST /api/v1/articles` endpoint. Article creation is through the pipeline only.

### 4. Additional 2FA Routes Not Documented

**Document only shows:**
- `/admin/login`
- `/admin/logout`

**Actual code has additional routes:**
- `/admin/verify-2fa` (`routes/admin/auth.py:97`) - POST for 2FA verification
- `/admin/setup-2fa` (`routes/admin/auth.py:151`) - GET/POST for 2FA setup

### 5. Additional Admin Routes Not Documented

**Document lists:**
- `/admin/` - Dashboard
- `/admin/articles` - Article management
- `/admin/sources` - Source management
- `/admin/subscribers` - Subscriber management
- `/admin/newsletters` - Newsletter history

**Additional routes in code:**
- `/admin/dead-letters` (`routes/admin/dashboard.py:13`)
- `/admin/metrics` (`routes/admin/metrics.py:10`)
- `/admin/articles/<id>/edit` (`routes/admin/articles.py:385`)
- `/admin/articles/<id>/versions` (`routes/admin/articles.py:440`)
- `/admin/articles/<id>/original` (`routes/admin/articles.py:426`)
- `/admin/articles/<id>/delete` (`routes/admin/articles.py:505`)
- `/admin/articles/<id>/reprocess` (`routes/admin/articles.py:534`)
- `/admin/sources/add` (`routes/admin/sources.py:39`)
- `/admin/sources/<id>/enable` (`routes/admin/sources.py:106`)
- `/admin/sources/<id>/disable` (`routes/admin/sources.py:142`)
- `/admin/subscribers/export` (`routes/admin/subscribers.py:51`)

### 6. Share Endpoint Note

**Document says (line 107):**
> **Note:** `/share/<platform>/<article_id>` is not implemented as a server endpoint.

**Actual code:** The `routes/admin/shares.py` exists but only manages share configurations in admin UI. There is no public `/share/` route. This note is accurate.

### 7. API Token Format Documentation

**Document says (line 206):**
> Token stored as: prefix + hash (never plaintext)

**Actual code (`routes/admin/api_tokens.py:37-45`):**
```python
plain_token = secrets.token_urlsafe(32)
token_hash = secrets.token_hex(32)
api_token = ApiToken(
    token_hash=generate_password_hash(token_hash),
    raw_token_hash=token_hash,  # <-- Stores raw hash, not plaintext
    name=name,
)
```

The format is `plain_token.token_hash` returned to user on creation, but `token_hash` is stored in DB (not plaintext token). This is essentially correct but the storage is the hash of a hash.

### 8. API Token Prefix Matching

**Document doesn't specify prefix length:**
**Actual code (`routes/admin/__init__.py:31-32`):**
```python
provided_hash = parts[1]
prefix = provided_hash[:16]  # Uses first 16 chars of hash as prefix
```

Then queries `ApiToken.token_prefix == prefix`. This is an implementation detail not documented.

---

## Specific Bugs Identified

### Bug 1: Documentation Outdated - api_tokens_bp Registration

**File:** `architecture/routes.md:57`
**Issue:** Documentation claims `api_tokens_bp` is NOT registered, but it IS registered in `app.py:197`
**Severity:** Medium - could cause debugging confusion

### Bug 2: Documentation Missing Routes

**File:** `architecture/routes.md`
**Issue:** Missing documentation for:
- `/admin/verify-2fa` (2FA verification flow)
- `/admin/setup-2fa` (2FA setup flow)
- `/admin/dead-letters` (Dead letter queue UI)
- `/admin/metrics` (Metrics dashboard)
- `/articles/bulk` operations
**Severity:** Low - documentation completeness

### Bug 3: POST /articles Claimed But Not Implemented

**File:** `architecture/routes.md:143`
**Issue:** Table shows `POST /articles` for article creation, but this endpoint doesn't exist
**Severity:** Medium - API documentation error

---

## Improvement Recommendations

### 1. Update `api_tokens_bp` Registration Note (HIGH)

**Location:** `architecture/routes.md:57`
**Change from:**
> **Note:** The `api_tokens_bp` blueprint exists in `routes/admin/api_tokens.py` but is NOT registered in `app.py`. All `/api-tokens` routes return 404.

**Change to:**
> The `api_tokens_bp` blueprint is registered in `app.py` and provides `/api-tokens` endpoints for API token management (list, create, delete).

### 2. Fix Feeds Blueprint Name (LOW)

**Location:** `architecture/routes.md:64`
**Change from:**
```python
feeds_bp = Blueprint('feeds', __name__)
```
**Change to:**
```python
public_bp = Blueprint("public", __name__)
```

### 3. Add Missing Routes to Documentation (MEDIUM)

Add to Admin Blueprint section:
- `/admin/verify-2fa` - 2FA verification
- `/admin/setup-2fa` - 2FA setup
- `/admin/dead-letters` - Dead letter queue
- `/admin/metrics` - Metrics dashboard

Add to API Endpoints table:
- `/articles/bulk` with POST method for bulk operations

### 4. Remove or Fix POST /articles (MEDIUM)

**Location:** `architecture/routes.md:143`
**Option A:** Remove `POST /articles` if articles are only created via pipeline
**Option B:** Implement `POST /api/v1/articles` endpoint

### 5. Document API Token Prefix Matching (LOW)

Add detail about prefix matching:
- Uses first 16 characters of the hash portion as prefix
- Tokens queried by prefix, then verified with full hash

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct Claims | ~60 |
| Discrepancies (Documentation vs Code) | 8 |
| Documentation Errors | 3 |
| Missing Route Documentation | 12+ |
| Implementation Bugs | 0 |

**Overall Assessment:** The implementation is correct and consistent. The issues are primarily documentation bugs where the documentation has not been updated to reflect current code. The `api_tokens_bp` registration note is the most significant issue as it incorrectly claims a feature is non-functional.
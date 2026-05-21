# Routes Module Architecture Review

This document reviews the claims in `architecture/routes.md` against the actual implementation in the codebase.

---

## Verified Correct

### Blueprint URL Prefixes
- **admin_bp** at `/admin` - **CORRECT** (`routes/admin/__init__.py` line 14)
- **admin_api_bp** at `/api/v1` - **CORRECT** (`routes/admin/__init__.py` line 15)
- **public_bp** at `/` - **CORRECT** (`routes/public/__init__.py` line 26)

### Admin API Endpoints - Verified Present
All documented API endpoints exist in the codebase:

| Endpoint | File | Methods | Verified |
|----------|------|---------|----------|
| `/articles/ids` | `routes/admin/api/articles.py` | GET | ✓ |
| `/articles/counts-by-status` | `routes/admin/api/articles.py` | GET | ✓ |
| `/articles/bulk` | `routes/admin/api/articles.py` | POST | ✓ |
| `/articles/<id>/pipeline` | `routes/admin/api/articles.py` | POST | ✓ |
| `/articles/<id>` | `routes/admin/api/articles.py` | GET, PUT, DELETE | ✓ |
| `/sources` | `routes/admin/api/sources.py` | GET, POST | ✓ |
| `/sources/<id>` | `routes/admin/api/sources.py` | GET, PUT, PATCH, DELETE | ✓ |
| `/sources/<id>/refresh` | `routes/admin/api/sources.py` | POST | ✓ |
| `/sources/health` | `routes/admin/api/pipeline.py` | GET | ✓ |
| `/pipeline/stats` | `routes/admin/api/pipeline.py` | GET | ✓ |
| `/pipeline/backlog` | `routes/admin/api/pipeline.py` | GET | ✓ |
| `/pipeline/dead-letter/stats` | `routes/admin/api/pipeline.py` | GET | ✓ |
| `/pipeline/sla` | `routes/admin/api/pipeline.py` | GET | ✓ |
| `/costs` | `routes/admin/api/pipeline.py` | GET | ✓ |
| `/webhooks` | `routes/admin/api/webhooks.py` | GET, POST | ✓ |
| `/webhooks/<id>` | `routes/admin/api/webhooks.py` | GET, PUT, PATCH, DELETE | ✓ |
| `/webhooks/<id>/test` | `routes/admin/api/webhooks.py` | POST | ✓ |
| `/webhooks/<id>/events` | `routes/admin/api/webhooks.py` | GET | ✓ |
| `/webhooks/events/<id>/resend` | `routes/admin/api/webhooks.py` | POST | ✓ |
| `/search/analytics` | `routes/admin/api/search.py` | GET | ✓ |
| `/config/reload` | `routes/admin/api/config.py` | POST | ✓ |
| `/metrics` | `routes/admin/api/config.py` | GET | ✓ |
| `/metrics/prometheus` | `routes/admin/api/config.py` | GET | ✓ |
| `/audit-logs` | `routes/admin/api/audit.py` | GET | ✓ |
| `/health` | `routes/admin/api/health.py` | GET | ✓ |
| `/workers/health` | `routes/admin/api/health.py` | GET | ✓ |
| `/task/<task_id>` | `routes/admin/api/health.py` | GET | ✓ |

### Public Routes - Verified Present
| Route | File | Verified |
|-------|------|----------|
| `/` (index) | `routes/public/feeds.py` | ✓ |
| `/topic/<category>` | `routes/public/feeds.py` | ✓ |
| `/tag/<slug>` | `routes/public/feeds.py` | ✓ |
| `/feed` | `routes/public/feeds.py` | ✓ |
| `/feed/<category>` | `routes/public/feeds.py` | ✓ |
| `/sitemap.xml` | `routes/public/feeds.py` | ✓ |
| `/subscribe` | `routes/public/subscribe.py` | ✓ POST only |
| `/verify/<token>` | `routes/public/subscribe.py` | ✓ |
| `/unsubscribe/<token>` | `routes/public/subscribe.py` | ✓ GET+POST |
| `/article/<int:article_id>` | `routes/public/links.py` | ✓ |
| `/s/<short_id>` | `routes/public/links.py` | ✓ |
| `/a/<short_id>` | `routes/public/links.py` | ✓ |
| `/track/newsletter-click/<int:article_id>` | `routes/public/links.py` | ✓ |
| `/api/v1/track/share-click/<int:article_id>` | `routes/public/links.py` | ✓ POST |
| `/health` | `routes/public/__init__.py` | ✓ |

### Authentication Security Features
- **TOTP 2FA support** - **CORRECT** (`routes/admin/auth.py` - `verify_token()` from `services/totp.py`)
- **8 backup codes** - **CORRECT** (`routes/admin/auth.py` line 126 - `verify_backup_code()` and `consume_backup_code()`)
- **Session hijacking protection (IP + User-Agent binding)** - **CORRECT** (`routes/admin/__init__.py` lines 75-86)
- **Login lockout via Redis (with in-memory fallback)** - **CORRECT** (`routes/admin/__init__.py` lines 104-303)

### CSRF Protection
- **Flask-WTF tokens** - **CORRECT** - `validate_csrf_json` decorator in `routes/decorators.py` validates CSRF for JSON endpoints via `X-CSRFToken` header
- All state-changing API routes use `@validate_csrf_json` decorator

### Admin HTML Pages
| Page | Route | Verified |
|------|-------|----------|
| Login | `/admin/login` | ✓ |
| Dashboard | `/admin/` | ✓ |
| Articles | `/admin/articles` | ✓ |
| Sources | `/admin/sources` | ✓ |
| Subscribers | `/admin/subscribers` | ✓ (via HTML, not separately listed) |
| Newsletters | `/admin/newsletters` | ✓ |
| Webhooks | `/admin/webhooks` | ✓ |
| Dead Letters | `/admin/dead-letters` | ✓ |

### Feeds Functionality
- `feeds_bp` used for feeds as documented (but actual name is `public_bp` imported from `routes.public`)
- `/sitemap.xml`, `/feed`, `/feed/<category>` all present and functioning

---

## Discrepancies Found

### 1. `api_tokens_bp` Registration Status - **CRITICAL DISCREPANCY**

**Document says (line 57):**
> **Note:** The `api_tokens_bp` blueprint exists in `routes/admin/api_tokens.py` but is NOT registered in `app.py`. All `/api-tokens` routes return 404.

**Actual code (`app.py` lines 188-197):**
```python
def _register_blueprints(app):
    """Register Flask blueprints."""
    from routes.admin import admin_bp, admin_api_bp
    from routes.admin.api_tokens import api_tokens_bp  # <-- IMPORTED
    from routes.public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_api_bp)
    app.register_blueprint(api_tokens_bp)  # <-- REGISTERED!
```

**The `api_tokens_bp` IS registered**, contradicting the documentation. The `/api-tokens` routes are functional, not 404.

### 2. `feeds_bp` vs `public_bp` Naming

**Document says (line 64):**
```python
feeds_bp = Blueprint('feeds', __name__)
```

**Actual code (`routes/public/__init__.py` line 26):**
```python
public_bp = Blueprint("public", __name__)
```

The blueprint is named `public_bp`, not `feeds_bp`. This is a minor naming discrepancy but the structure remains functionally equivalent.

### 3. Missing `POST /articles` Endpoint

The documentation shows `/articles` with `GET, POST` methods (line 143):
> | `/articles` | GET, POST | List/create articles |

**Actual code:** There is NO `POST /api/v1/articles` endpoint in `routes/admin/api/articles.py`. There is only:
- `GET /articles/ids` (line 152)
- `GET /articles/counts-by-status` (line 171)
- `POST /articles/bulk` (line 470)
- `GET/PUT/DELETE /articles/<id>` (lines 597, 620, 673)

Article creation is handled through the pipeline, not a direct POST endpoint.

### 4. Share Endpoint Note Inconsistent

**Document says (line 107):**
> **Note:** `/share/<platform>/<article_id>` is not implemented as a server endpoint. Social sharing is handled client-side via JavaScript.

**Actual code:** There is no `/share/` route anywhere in the codebase. The `shares.py` file (`routes/admin/shares.py`) exists but only serves HTML management UI, not public share routes. The documentation accurately notes that share functionality is client-side, but the note implies there's an intentional design decision documented somewhere - this is correct as implemented.

### 5. Template Structure

**Document shows (lines 173-188):** Flat structure under `templates/` with admin partials at `templates/admin/partials/`.

**Actual structure:** Template directories verified:
- `templates/admin/partials/` exists
- `templates/partials/` exists for public
- `templates/errors/` exists
- `templates/macros/` exists

This matches the documentation.

---

## Bugs Identified

### Bug 1: Inconsistent Route Documentation for Article Creation

The architecture document shows `POST /articles` as an endpoint but this doesn't exist. This is a documentation bug, not an implementation bug. The actual article creation flow is through the pipeline (`POST /articles/<id>/pipeline`).

### Bug 2: `api_tokens_bp` Blueprint Registered Despite Documentation Claim

The documentation explicitly states `api_tokens_bp` is "NOT registered" but it IS registered in `app.py`. This is a documentation bug that should be corrected to avoid confusion during debugging.

---

## Improvement Suggestions

### 1. Update Documentation to Reflect `api_tokens_bp` Registration

The note on line 57 of `routes.md` should be updated:
- **Current:** "The `api_tokens_bp` blueprint exists in `routes/admin/api_tokens.py` but is NOT registered in `app.py`."
- **Should be:** The blueprint is registered and functional at `/api-tokens`.

### 2. Add `POST /articles` Endpoint or Remove from Documentation

Either:
- Add a proper article creation endpoint to `routes/admin/api/articles.py`, OR
- Remove `POST /articles` from the API table and document that articles are created via the pipeline

### 3. Clarify "Shares" Route in Documentation

The `routes/admin/shares.py` file exists but doesn't implement public share routes. Consider either:
- Documenting the admin-only nature of shares management
- Or removing the "Note" about `/share/<platform>/<article_id>` if it's causing confusion

### 4. Update Blueprint Naming in Documentation

The `feeds_bp` reference in the Feeds section (line 64) should be updated to `public_bp` to match the actual implementation.

---

## Questions for Architecture

### Q1: Was `api_tokens_bp` intended to be unregistered?

The documentation explicitly states it's NOT registered as a design decision. But the code shows it IS registered. Should it be:
- Left registered (documentation error)
- Removed from `app.py` registration (code error)
- Or was this changed at some point and documentation wasn't updated?

### Q2: Should there be a `POST /api/v1/articles` endpoint?

The documentation shows article creation via POST, but the implementation doesn't have this. Is this:
- An intentional design choice (articles created via pipeline only)?
- A missing feature that should be implemented?
- Or just a documentation error?

### Q3: What is the intended scope of `routes/admin/shares.py`?

The file `routes/admin/shares.py` exists and is imported in `routes/admin/__init__.py`, but it only contains admin UI for share configuration. Is there intent to add public share tracking endpoints, or should this file be documented as admin-only?

### Q4: Rate Limiting Details

The documentation mentions "Admin routes have stricter rate limits via `extensions.limiter`" but doesn't specify exact limits. Should specific rate limits be documented for:
- Login endpoints
- API endpoints
- Public endpoints

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct Claims | ~45 |
| Discrepancies (Documentation vs Code) | 4 |
| Bugs (Implementation Issues) | 0 |
| Documentation Errors | 2 |
| Questions for Architecture | 4 |

**Overall Assessment:** The architecture documentation is largely accurate. The primary issue is the `api_tokens_bp` registration status contradiction, which is a documentation bug (the code is correct, docs are wrong). The missing `POST /articles` endpoint and `feeds_bp` naming are minor issues that should be clarified.

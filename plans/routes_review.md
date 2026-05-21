# Routes Module Architecture Review

## Summary

Document: `architecture/routes.md` (221 lines)
Review date: 2026-05-21
Module: `routes/`

The architecture document provides a good high-level overview but is **incomplete and has minor inaccuracies**. Several routes, templates, and patterns exist in the codebase that are not documented.

---

## Part I: Verified Claims

### Structure ✓
- `routes/public/`: `feeds.py`, `subscribe.py`, `links.py` — all match
- `routes/admin/`: `__init__.py`, `auth.py`, `api_tokens.py`, `api/` subpackage — all match
- `routes/admin/api/`: `articles.py`, `sources.py`, `pipeline.py`, `search.py`, `webhooks.py`, `config.py`, `audit.py` — all match

### Blueprint Registration ✓
- `public_bp` at `/` — verified in `app.py:194`
- `admin_bp` at `/admin` — verified in `app.py:195`
- `admin_api_bp` at `/api/v1` — verified in `app.py:196`
- `api_tokens_bp` at `/api-tokens` — verified in `app.py:197`

### Public Routes (Mostly Accurate)
- `/sitemap.xml` — `routes/public/feeds.py:308`
- `/feed/<format>` — `routes/public/feeds.py:222,259`
- `/articles` — `routes/public/feeds.py:73` (index route at `/`)
- `/subscribe`, `/verify/<token>`, `/unsubscribe/<token>` — `routes/public/subscribe.py`
- `/a/<short_id>`, `/s/<short_id>` — `routes/public/links.py:94,103`
- `/track/newsletter-click/<int:article_id>` — `routes/public/links.py:130`

### Admin Auth Routes (Accurate)
- `/admin/login`, `/admin/logout` — `routes/admin/auth.py:43,188`
- TOTP 2FA with 8 backup codes — `routes/admin/auth.py`
- Session hijacking protection (IP + User-Agent binding) — `routes/admin/__init__.py:75-86`

### API Endpoints (Mostly Accurate)
Most documented endpoints exist. See discrepancies below.

### Template Structure (Partially Accurate)
- `templates/admin/` flat structure with partials — correct
- `templates/errors/` for 404, 500, 429 — correct
- `templates/macros/` — correct

---

## Part II: Discrepancies & Issues

### 1. INCOMPLETE DOCUMENTATION (HIGH Priority)

#### Undocumented Public Routes:
| Route | File | Line |
|-------|------|------|
| `/` (index with topics/tags) | `routes/public/feeds.py` | 73 |
| `/topic/<category>` | `routes/public/feeds.py` | 122 |
| `/tag/<slug>` | `routes/public/feeds.py` | 171 |
| `/article/<int:article_id>` | `routes/public/links.py` | 24 |
| `/api/v1/track/share-click/<int:article_id>` | `routes/public/links.py` | 123 |
| `/health` | `routes/public/__init__.py` | 111 |

#### Undocumented Admin HTML Routes:
| Route | File | Line |
|-------|------|------|
| `/admin/metrics` | `routes/admin/metrics.py` | 10 |
| `/admin/shares` | `routes/admin/shares.py` | 7 |
| `/admin/topic-notes` | `routes/admin/topic_notes.py` | 20 |
| `/admin/trend-memory` | `routes/admin/trend_memory.py` | 16 |
| `/admin/pipelines` | `routes/admin/pipelines.py` | 12 |
| `/admin/pipelines/<int:run_id>/logs` | `routes/admin/pipelines.py` | 40 |
| `/admin/trigger-crawl` | `routes/admin/pipelines.py` | 84 |
| `/admin/review` | `routes/admin/review.py` | 17 |
| `/admin/newsletters/<int:newsletter_id>` | `routes/admin/newsletters.py` | 90 |
| `/admin/newsletters/generate` | `routes/admin/newsletters.py` | 100 |
| `/admin/newsletters/dry-run` | `routes/admin/newsletters.py` | 126 |
| `/admin/subscribers/export` | `routes/admin/subscribers.py` | 51 |
| `/admin/sources/add` | `routes/admin/sources.py` | 39 |
| `/admin/sources/<int:source_id>/enable` | `routes/admin/sources.py` | 106 |
| `/admin/sources/<int:source_id>/disable` | `routes/admin/sources.py` | 142 |
| `/admin/articles/<int:article_id>/edit` | `routes/admin/articles.py` | 385 |
| `/admin/articles/<int:article_id>/original` | `routes/admin/articles.py` | 426 |
| `/admin/articles/<int:article_id>/versions` | `routes/admin/articles.py` | 440 |
| `/admin/articles/<int:article_id>/versions/<int:version_id>/rollback` | `routes/admin/articles.py` | 458 |
| `/admin/articles/<int:article_id>/delete` | `routes/admin/articles.py` | 505 |
| `/admin/articles/<int:article_id>/reprocess` | `routes/admin/articles.py` | 534 |
| `/admin/review/<int:article_id>/approve` | `routes/admin/review.py` | 64 |
| `/admin/review/<int:article_id>/reject` | `routes/admin/review.py` | 121 |
| `/admin/shares/add` | `routes/admin/shares.py` | 16 |
| `/admin/shares/<int:config_id>/edit` | `routes/admin/shares.py` | 68 |
| `/admin/shares/<int:config_id>/delete` | `routes/admin/shares.py` | 119 |
| `/admin/shares/<int:config_id>/edit-form` | `routes/admin/shares.py` | 142 |
| `/admin/shares/<int:config_id>/row` | `routes/admin/shares.py` | 152 |
| `/admin/shares/<int:config_id>/toggle` | `routes/admin/shares.py` | 162 |
| `/admin/topic-notes/create` | `routes/admin/topic_notes.py` | 42 |
| `/admin/topic-notes/edit` | `routes/admin/topic_notes.py` | 86 |
| `/admin/topic-notes/delete` | `routes/admin/topic_notes.py` | 143 |
| `/admin/topic-notes/row/<topic>` | `routes/admin/topic_notes.py` | 172 |
| `/admin/trend-memory/delete/<int:memory_id>` | `routes/admin/trend_memory.py` | 53 |
| `/admin/trend-memory/delete-expired` | `routes/admin/trend_memory.py` | 85 |

#### Undocumented API Endpoints:
| Route | File | Line |
|-------|------|------|
| `/api/v1/health` | `routes/admin/api/health.py` | 17 |
| `/api/v1/workers/health` | `routes/admin/api/health.py` | 54 |
| `/api/v1/task/<task_id>` | `routes/admin/api/health.py` | 102 |
| `/api/v1/newsletters/stats` | `routes/admin/newsletters.py` | 177 |
| `/api/v1/newsletter/preview` | `routes/admin/newsletters.py` | 221 |

#### Undocumented Templates:
| Template | File |
|----------|------|
| `admin/shares.html` | `templates/admin/shares.html` |
| `admin/topic_notes.html` | `templates/admin/topic_notes.html` |
| `admin/trend_memory.html` | `templates/admin/trend_memory.html` |
| `admin/pipelines.html` | `templates/admin/pipelines.html` |
| `admin/pipeline_logs.html` | `templates/admin/pipeline_logs.html` |
| `admin/review.html` | `templates/admin/review.html` |
| `admin/setup_2fa.html` | `templates/admin/setup_2fa.html` |
| `admin/verify_2fa.html` | `templates/admin/verify_2fa.html` |
| `admin/partials/review_table.html` | `templates/admin/partials/review_table.html` |
| `admin/partials/share_edit_form.html` | `templates/admin/partials/share_edit_form.html` |
| `admin/partials/share_row.html` | `templates/admin/partials/share_row.html` |
| `admin/partials/topic_note_row.html` | `templates/admin/partials/topic_note_row.html` |
| `topic.html` | `templates/topic.html` |
| `tag.html` | `templates/tag.html` |
| `share_redirect.html` | `templates/share_redirect.html` |

---

### 2. DOCUMENTATION ACCURACY ISSUES

#### A. Session Key Names Mismatch (LOW Priority — Documentation Bug)
**File:** `routes/admin/__init__.py:75-86`
**Doc says:** `session['ip']` and `session['ua']`
**Code uses:** `session['ip']` and `session['user_agent']`

The documentation at `architecture/routes.md:201` shows `session['ua']` but the actual code at `routes/admin/__init__.py:76` stores `session['user_agent']`. This is a documentation bug, not a code bug.

**Fix:** Update doc to reference `session['user_agent']`.

#### B. API Token Storage (MED Priority — Potential Security Issue)
**File:** `routes/admin/api_tokens.py:43-45`
```python
api_token = ApiToken(
    token_hash=generate_password_hash(token_hash),
    raw_token_hash=token_hash,  # <-- Stores the unhashed hash
    name=name,
)
```
The `raw_token_hash` field stores the unhashed token hash. Combined with the stored hash, an attacker with database access could potentially verify tokens. While not a critical flaw (the plaintext token is returned only once on creation), storing `raw_token_hash` is unusual and potentially insecure.

**Recommendation:** Remove `raw_token_hash` from the model or encrypt it at rest. The hash stored via `generate_password_hash` is sufficient for verification.

#### C. Dead Letter Queue Route Path (MED Priority — Documentation Bug)
**File:** `routes/admin/dashboard.py:13`
**Doc says:** `/admin/dead-letters`
**Code:** Route is registered at `/dead-letters` not `/admin/dead-letters`

The blueprint `admin_bp` has `url_prefix="/admin"` so the actual URL is `/admin/dead-letters`. The documentation is correct.

---

### 3. LAYERING ISSUES

#### A. Routes Import from Services Layer (Acceptable but worth noting)
The routes module imports from `services/` in many places:
- `services.totp` in `auth.py`
- `services.audit`, `services.cache`, `services.task_security` in various routes
- `services.article`, `services.newsletter`, etc.

This is **acceptable per the architecture** since routes → services is a valid dependency direction. The restriction is adapters → services.

---

### 4. MISSING IMPLEMENTATIONS

#### A. `/share/<platform>/<article_id>` Not Implemented (Acknowledged in Doc)
The doc at `architecture/routes.md:113` correctly notes:
> `/share/<platform>/<article_id>` is not implemented as a server endpoint. Social sharing is handled client-side via JavaScript.

This is accurate. No server route exists for `/share/...`.

---

### 5. SECURITY OBSERVATIONS

#### A. CSRF Protection (Good)
All state-changing API routes use `@validate_csrf_json` decorator. Public form routes rely on Flask-WTF CSRF tokens. ✓

#### B. Session Hijacking Protection (Good but Incomplete)
The IP + User-Agent binding at `routes/admin/__init__.py:75-86` is solid. However, the session binding only occurs on login — if an attacker steals a session cookie and makes requests from the same IP/UA, they will be authenticated. The binding is checked but doesn't prevent reuse of a valid session from a different IP (it forces re-login but the attacker still has the stolen session).

**Note:** This is a standard session hijacking pattern and is acceptable.

#### C. API Token Authentication (Good)
- Tokens stored as `prefix + hash` ✓
- Only prefix stored for lookup ✓
- Bearer token auth in header ✓

#### D. Login Lockout (Good)
Redis-based with Lua script for atomicity + in-memory fallback. ✓

---

### 6. PERFORMANCE CONCERNS

#### A. Dashboard Stats Caching
**File:** `routes/admin/dashboard.py:86-189`

The `_compute_dashboard_stats()` function caches for only 60 seconds (`cache.set(cache_key, stats, 60)`). For an admin dashboard with heavy queries (pipeline stats, source counts, article counts, LLM provider info, Redis health), this may be too aggressive and cause unnecessary load.

**Recommendation:** Consider increasing cache TTL to 120-300 seconds, or add caching headers to the response.

#### B. Newsletter Export Streaming
**File:** `routes/admin/subscribers.py:51-108`

The CSV export uses `yield_per(500)` and streams responses correctly. This is good for memory efficiency with large subscriber lists. ✓

---

### 7. BUGS IN IMPLEMENTATION

#### A. Bug: `verify_backup_code` Result Checked but Not Used Properly
**File:** `routes/admin/auth.py:127-130`
```python
if verify_backup_code(admin_user.backup_codes, backup_code):
    new_codes = consume_backup_code(admin_user.backup_codes, backup_code)
    if new_codes is not None:
        admin_user.backup_codes = new_codes
```

The `verify_backup_code` returns a boolean for validity, then `consume_backup_code` is called which also validates. The logic is correct but unnecessarily complex — `consume_backup_code` should be called first and return the new codes directly if valid.

**Not a bug, just convoluted logic.**

#### B. Bug: `/api/v1/track/share-click` Returns Empty String
**File:** `routes/public/links.py:125`
```python
def track_share_click(article_id: int) -> tuple[str, int]:
    track_metric(article_id, ArticleMetric.share_button_clicks)
    return "", 204
```

Returns a bare `""` string which may cause issues with some clients expecting JSON. Should return `jsonify({"success": True})` or similar. The comment above notes CSRF protection exists but rate limiting comment is misleading.

---

## Part III: Improvement Recommendations

### CRIT (Critical — Should Fix)

None identified. No security-critical bugs found.

### HIGH (High Priority)

1. **Update architecture/routes.md with undocumented routes**
   - Add all undocumented public routes (`/topic/<category>`, `/tag/<slug>`, `/article/<int:article_id>`, `/health`)
   - Add all undocumented admin HTML routes (shares, topic-notes, trend-memory, pipelines, review, metrics, etc.)
   - Add all undocumented API endpoints (health, workers, task status, newsletter stats/preview)
   - Add missing templates to inventory

2. **Document Session Key Names Correctly**
   - File: `architecture/routes.md:201`
   - Change `session['ua']` to `session['user_agent']`

### MED (Medium Priority)

3. **Review ApiToken.raw_token_hash storage**
   - File: `routes/admin/api_tokens.py:43-45`
   - Consider removing `raw_token_hash` field or encrypting at rest
   - Impact: Security improvement for token storage

4. **Increase dashboard stats cache TTL**
   - File: `routes/admin/dashboard.py:188`
   - Change `60` to `120` or `300` seconds
   - Impact: Reduced database/Celery load

5. **Improve track_share_click response**
   - File: `routes/public/links.py:125`
   - Return JSON response instead of bare string
   - Impact: More consistent API behavior

### LOW (Low Priority)

6. **Standardize error response envelope for public routes**
   - Many public routes return inconsistent error formats
   - Some use `redirect("/")`, others render templates
   - Impact: Developer experience

7. **Document the `/admin/trigger-crawl` endpoint**
   - This is an important admin action not in the doc
   - Impact: Completeness

8. **Add api_tokens_bp to documented blueprint structure**
   - File: `architecture/routes.md:62`
   - Already mentioned in note, should be in main table

---

## Summary Table

| Category | Count |
|----------|-------|
| Undocumented Public Routes | 6 |
| Undocumented Admin HTML Routes | 35+ |
| Undocumented API Endpoints | 5 |
| Undocumented Templates | 13 |
| Documentation Accuracy Issues | 2 |
| Security Observations | 4 (all satisfactory) |
| Performance Concerns | 2 |
| Bugs in Implementation | 1 minor |

---

## Verification Commands

```bash
# List all registered routes
flask routes 2>/dev/null || grep -r "@.*\.route" routes/ --include="*.py"

# Check for undocumented templates
ls templates/admin/*.html templates/admin/partials/*.html

# Verify blueprint registration
grep -n "register_blueprint\|bp" app.py
```
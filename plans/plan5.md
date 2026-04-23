# Security Improvement Plan — XSS and Input Validation

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Source**: Security Audit — 2026-04-23

---

## Executive Summary

This plan addresses XSS vulnerabilities and input validation gaps identified during a comprehensive security audit. One critical stored XSS vulnerability requires immediate remediation.

| Priority | Issue | Severity | Tasks | Effort |
|----------|-------|----------|-------|--------|
| 🔴 Critical | Stored XSS in admin article edit form | **CRITICAL** | 8 | 15 min |
| 🔴 High | Bulk article IDs missing validation | HIGH | 1 | 10 min |
| 🟡 Medium | Health endpoint information disclosure | MEDIUM | 2 | 30 min |
| 🟡 Medium | Admin template error message XSS | MEDIUM | — | (in Priority 1) |
| 🟢 Low | Token logging verbosity | LOW | 2 | 10 min |
| ✅ OK | SSRF protection | Secure | — | — |
| ✅ OK | Auth flows | Secure | — | — |
| ✅ OK | Celery task signing | Secure | — | — |
| ✅ OK | Webhook encryption | Secure | — | — |

---

## Priority 1: 🔴 CRITICAL — XSS Vulnerabilities

### 1.1 Stored XSS in Admin Article Edit Form

**Severity**: CRITICAL
**Risk**: Stored XSS allows execution of malicious scripts when admin views the edit page. LLM-generated content in `final_article` JSON is rendered without escaping.

**Current State**: `templates/admin/article_edit.html` renders form values directly:

| Line | Field | Current Code | Required Fix |
|------|-------|--------------|--------------|
| 48 | headline | `value="{{ fa.get('headline', '') if fa else article.original_title or '' }}"` | Add `\|e` |
| 53 | tldr | `<textarea>{{ fa.get('tldr', '') if fa else '' }}</textarea>` | Add `\|e` |
| 58 | why_it_matters | `<textarea>{{ fa.get('why_it_matters', '') if fa else '' }}</textarea>` | Add `\|e` |
| 63 | body | `<textarea>{{ fa.get('body', '') if fa else '' }}</textarea>` | Add `\|e` |
| 68 | what_to_watch | `<textarea>{{ fa.get('what_to_watch', '') if fa else '' }}</textarea>` | Add `\|e` |
| 73 | key_points | `<textarea>{{ '\n'.join(fa.get('key_points', []) if fa else []) }}</textarea>` | Add `\|e` |
| 79 | tags | `value="{{ ', '.join(fa.get('tags', []) if fa else []) }}"` | Add `\|e` |

**Vulnerable Data Flow**:
1. LLM generates `final_article` JSON containing potentially malicious HTML/JS
2. Article saved to database with `pipeline_status="published"`
3. Admin navigates to `/admin/articles/<id>/edit`
4. `routes/admin/articles.py:297` loads `json.loads(article.final_article)`
5. Template renders values without escaping
6. XSS executes in admin's browser

**Required Changes**:

```html
<!-- Line 48: Add |e to headline value -->
value="{{ (fa.get('headline', '') if fa else article.original_title or '') | e }}"

<!-- Lines 53, 58, 63, 68: Add |e to textarea content -->
<textarea id="tldr" ...>{{ (fa.get('tldr', '') if fa else '') | e }}</textarea>

<!-- Line 73: key_points requires join filter -->
{{ '\n'.join(fa.get('key_points', []) if fa else []) | e }}

<!-- Line 79: tags -->
value="{{ ', '.join(fa.get('tags', []) if fa else []) | e }}"
```

**Action Items**:
- [ ] Fix line 48 — add `|e` to headline value
- [ ] Fix line 53 — add `|e` to tldr textarea
- [ ] Fix line 58 — add `|e` to why_it_matters textarea
- [ ] Fix line 63 — add `|e` to body textarea
- [ ] Fix line 68 — add `|e` to what_to_watch textarea
- [ ] Fix line 73 — add `|e` to key_points textarea
- [ ] Fix line 79 — add `|e` to tags input
- [ ] Fix lines 28-32 — add `|e` to error message (section 3.2 also covers this)

**Effort**: 15 minutes
**Risk**: None (adding escaping is safe, fixes vulnerability)

**Testing**:
```bash
# Manual: Navigate to /admin/articles/<id>/edit with crafted final_article
# Verify <script>alert('xss')</script> in any field does NOT execute
.venv/bin/ruff check . --exclude .venv
```

---

### 1.2 XSS in Admin Dead Letters Page

**Severity**: CRITICAL (same class as 1.1)
**Risk**: Crawled content titles may contain malicious HTML/JS.

**Current State**: `templates/admin/dead_letters.html` renders article titles without escaping:

| Line | Current Code | Required Fix |
|------|--------------|--------------|
| 66 | `{{ article.original_title if article.original_title else '(no title)' }}` | Add `\|e` |
| 106 | `{{ article.original_title if article.original_title else '(no title)' }}` | Add `\|e` |

**Note**: Lines 65 and 105 correctly use `{{ article.original_title|e }}` in title attributes.

**Required Changes**:

```html
<!-- Line 66: Change to -->
{{ (article.original_title if article.original_title else '(no title)') | e }}

<!-- Line 106: Change to -->
{{ (article.original_title if article.original_title else '(no title)') | e }}
```

**Action Items**:
- [ ] Fix line 66 — add `|e` to article title
- [ ] Fix line 106 — add `|e` to article title

**Effort**: 5 minutes
**Risk**: None

---

## Priority 2: 🔴 HIGH Priority

### 2.1 Bulk Article IDs — Missing Integer Validation

**Severity**: HIGH
**Risk**: Non-integer values could potentially cause unexpected behavior or SQL errors (though SQLAlchemy would reject them at DB level).

**Current State**: `routes/admin/api/articles.py:183-191`:

```python
article_ids = data.get("article_ids", [])
if not article_ids or not isinstance(article_ids, list):
    return jsonify({"error": "article_ids must be a non-empty list"}), 400
if len(article_ids) > 500:
    return jsonify({"error": "Maximum 500 articles per bulk operation"}), 400
# Missing: validation that each element is an integer
articles = Article.query.filter(Article.id.in_(article_ids)).all()
```

**Note**: A dedicated `validate_bulk_ids()` function exists in `services/validation.py:90` but is NOT USED by this endpoint.

**Required Changes**:

```python
# Add after length check (line 188)
from services.validation import validate_bulk_ids

try:
    article_ids = validate_bulk_ids(article_ids)
except ValueError as e:
    return jsonify({"error": str(e)}), 400
```

**Action Items**:
- [ ] Import `validate_bulk_ids` from `services.validation`
- [ ] Call `validate_bulk_ids(article_ids)` before the query
- [ ] Handle `ValueError` with proper error response

**Effort**: 10 minutes
**Risk**: None (defense-in-depth improvement)

**Testing**:
```bash
# Send non-integer in article_ids: [1, "foo", 2]
# Should return 400 with error message
.venv/bin/pytest tests/test_admin_api.py -v -k bulk
```

---

### 2.2 Documentation — Missing WEBHOOK_SECRET_KEY

**Severity**: HIGH (for deployments)
**Risk**: Webhook encryption requires this key; missing documentation causes setup failures.

**Current State**:
- `WEBHOOK_SECRET_KEY` documented in `AGENTS.md:376` and `SKILL.md:334`
- NOT documented in `.env.example`
- NOT documented in `docs/configuration.md`

**Required Changes**:

1. **Add to `.env.example`**:
```bash
# Webhook secret encryption key (44 base64 characters)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
WEBHOOK_SECRET_KEY=
```

2. **Add to `docs/configuration.md`** in Optional variables section:
```markdown
| WEBHOOK_SECRET_KEY | Yes | Fernet key for webhook secret encryption |
```

**Action Items**:
- [ ] Add `WEBHOOK_SECRET_KEY` to `.env.example` with generation instructions
- [ ] Add `WEBHOOK_SECRET_KEY` to `docs/configuration.md`

**Effort**: 10 minutes
**Risk**: None

---

## Priority 3: 🟡 MEDIUM Priority

### 3.1 Health Endpoint Information Disclosure

**Severity**: MEDIUM
**Risk**: Unauthenticated `/health?detailed=true` exposes git commit hash and database connection pool statistics.

**Current State**: `services/health.py:159-189`:

```python
if detailed:
    result["git_commit"] = self._get_git_commit()
    result["pool"] = {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid(),
    }
```

**Required Changes**:

1. **Option A — Require auth for detailed mode** (preferred):
```python
# In routes/public/__init__.py:108-115
@public_bp.route("/health")
def health() -> tuple[Response, int]:
    detailed = request.args.get("detailed", "false").lower() == "true"
    if detailed and not session.get("admin"):
        detailed = False  # Downgrade if not authenticated
    result = run_health_checks(include_celery=True, detailed=detailed)
```

2. **Option B — Remove sensitive fields from public view**:
```python
if detailed:
    # Only include git commit for authenticated users
    if session.get("admin"):
        result["git_commit"] = self._get_git_commit()
    result["pool"] = {  # Remove pool stats entirely }
```

**Recommendation**: Option A — simplest fix with clear security model.

**Action Items**:
- [ ] Implement auth check for detailed health endpoint
- [ ] Add test for detailed mode with/without auth

**Effort**: 30 minutes
**Risk**: Low

---

### 3.2 Admin Template Error Message XSS

**Severity**: MEDIUM
**Risk**: If attacker can control error content (e.g., via form submission that triggers validation errors), XSS could execute.

**Current State**: `templates/admin/article_edit.html:28-31`:

```html
{% if error %}
<div class="form-error" role="alert">
  {{ error }}
</div>
{% endif %}
```

**Required Changes**:

```html
{% if error %}
<div class="form-error" role="alert">
  {{ error | e }}
</div>
{% endif %}
```

**Note**: Covered in Priority 1 section 1.1 action items. No duplicate work needed.

**Effort**: Included in Priority 1
**Risk**: None

---

### 3.3 Rate Limiting on Public Subscribe Endpoints

**Severity**: MEDIUM
**Risk**: `/subscribe`, `/unsubscribe`, `/verify` endpoints lack per-IP rate limiting. Could be targeted for email enumeration or DoS.

**Current State**:
- Global 60/min limit via Flask-Limiter
- Only `@limit_content_length(1024)` applied to subscribe
- No explicit `@limiter.limit()` on subscribe/unsubscribe/verify routes

**Required Changes**:

1. **Add rate limits** (`routes/public/subscribe.py`):

```python
# At module level or import
from extensions import limiter

@public_bp.route("/subscribe", methods=["POST"])
@limiter.limit("5 per minute")  # Prevent email enumeration
@limit_content_length(1024)
def subscribe():
    ...

@public_bp.route("/unsubscribe/<token>", methods=["POST"])
@limiter.limit("10 per minute")  # Higher limit for unsubscribe
def unsubscribe(token):
    ...
```

**Note**: Per AGENTS.md, the app runs behind WAF that handles rate limiting. This change is defense-in-depth.

**Action Items**:
- [ ] Add rate limit to `/subscribe` route
- [ ] Add rate limit to `/unsubscribe` route
- [ ] Add rate limit to `/verify` route

**Effort**: 15 minutes
**Risk**: Low (ensure limits don't break legitimate use)

---

## Priority 4: 🟢 LOW Priority

### 4.1 Token Logging Verbosity

**Severity**: LOW
**Risk**: Subscriber tokens (unsubscribe/verification) logged in full. Low sensitivity but could aid attacker in token enumeration.

**Current State**: `routes/public/subscribe.py`:

| Line | Code | Issue |
|------|------|-------|
| 171 | `logger.exception("Failed to unsubscribe token %s", token)` | Logs full token |
| 212 | `logger.exception("Failed to verify subscriber token %s", token)` | Logs full token |

**Required Changes**:

```python
# Option A: Log only prefix (8 chars)
logger.exception("Failed to unsubscribe token %s...", token[:8])

# Option B: Log hash only
import hashlib
token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
logger.exception("Failed to unsubscribe token hash: %s", token_hash)

# Option C: Don't log at all (just log error type)
logger.warning("Failed to unsubscribe subscriber")
```

**Recommendation**: Option A — `token[:8]` prefix provides enough info for debugging without exposing full token.

**Action Items**:
- [ ] Update line 171 — truncate token to `token[:8]`
- [ ] Update line 212 — truncate token to `token[:8]`

**Effort**: 10 minutes
**Risk**: None

---

## Priority 5: ✅ Already Secure (No Action Needed)

### 5.1 SSRF Protection

**Finding**: Well-implemented. `validate_url_safe()` blocks all private IP ranges with DNS caching (60s TTL).

| Component | Status |
|-----------|--------|
| Private IP blocking | ✅ Complete |
| IPv6 support | ✅ Complete |
| Scheme validation | ✅ http/https only |
| Thread-safe DNS cache | ✅ |
| All HTTP clients protected | ✅ |

**Conclusion**: No changes needed.

---

### 5.2 Authentication Flows

**Finding**: Robust implementation.

- Session-based auth with `@require_auth` decorator
- Werkzeug password hashing (scrypt/pbkdf2/argon2)
- `session.clear()` on successful login
- Login lockout: Redis Lua script + memory fallback
- Open redirect protection via `_safe_redirect_url()`

**Conclusion**: No changes needed.

---

### 5.3 Celery Task Signing

**Finding**: Properly implemented.

- HMAC-SHA256 signing for `run_all_sources`, `select_article`, `generate_daily_newsletters`
- Fail-closed when secret not configured
- Pydantic input validation via `schemas/tasks.py`

**Conclusion**: No changes needed.

---

### 5.4 Webhook Encryption

**Finding**: Proper encryption at rest.

- Fernet (AES-128-CBC) for webhook secrets
- HMAC-SHA256 payload signing
- Replay protection via timestamp
- Secret masking in API responses

**Conclusion**: No changes needed.

---

### 5.5 SQLAlchemy ORM Usage

**Finding**: No SQL injection vectors.

- All queries use SQLAlchemy ORM or parameterized raw SQL
- LIKE patterns properly escaped
- Bulk ID validation function exists (`validate_bulk_ids`)

**Conclusion**: No changes needed.

---

## Implementation Order

```
Phase 1: Critical XSS (15 min)
├── 1.1 article_edit.html form values + error   (15 min)
└── 1.2 dead_letters.html titles               (5 min)

Phase 2: High Priority (20 min)
├── 2.1 bulk article_ids validation           (10 min)
└── 2.2 WEBHOOK_SECRET_KEY docs              (10 min)

Phase 3: Medium Priority (45 min)
├── 3.1 health endpoint auth                 (30 min)
└── 3.3 rate limiting on subscribe           (15 min)

Phase 4: Low Priority (10 min)
└── 4.1 token logging verbosity              (10 min)

Total estimated time: ~90 minutes
```

---

## Testing Requirements

1. **Before any changes**:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

2. **After XSS fixes**:
```bash
# Manual verification: Navigate to /admin/articles/<id>/edit
# Inject <script>alert('xss')</script> in any LLM-generated field
# Verify script does NOT execute
```

3. **After bulk ID validation**:
```bash
# Send POST /admin/api/articles/bulk with article_ids: ["foo", "bar"]
# Verify 400 response with error message
```

4. **After health endpoint changes**:
```bash
# curl "http://localhost:5000/health?detailed=true" as anonymous
# Verify git_commit and pool stats are NOT returned
```

5. **After rate limit changes**:
```bash
# Send 6 subscribe requests in 1 minute
# Verify 429 response on 6th request
```

---

## Rollback Plan

| Change | Rollback Method |
|--------|----------------|
| XSS fixes (1.1, 1.2, 3.2) | Remove `|e` filters |
| Bulk ID validation | Remove `validate_bulk_ids` call |
| Health endpoint | Revert to unauthenticated detailed mode |
| Rate limits | Remove `@limiter.limit()` decorators |
| Token logging | Revert to full token in log |

---

## Appendix A: Issue Summary Table

| ID | Priority | Category | Severity | File | Line | Description |
|----|----------|----------|----------|------|------|-------------|
| XSS-001 | 🔴 CRITICAL | XSS | CRITICAL | templates/admin/article_edit.html | 48,53,58,63,68,73,79 | Form values without escaping |
| XSS-002 | 🔴 CRITICAL | XSS | CRITICAL | templates/admin/dead_letters.html | 66,106 | Title text without escaping |
| XSS-003 | 🔴 CRITICAL | XSS | CRITICAL | templates/admin/article_edit.html | 28-32 | Error message without escaping (covered in XSS-001) |
| VAL-001 | 🔴 HIGH | Validation | HIGH | routes/admin/api/articles.py | 183-191 | Missing integer validation |
| DOC-001 | 🔴 HIGH | Documentation | HIGH | .env.example, docs/configuration.md | — | Missing WEBHOOK_SECRET_KEY |
| INFO-001 | 🟡 MEDIUM | Info Disclosure | MEDIUM | services/health.py | 159-189 | Detailed health leaks system info |
| RATE-001 | 🟡 MEDIUM | Rate Limiting | MEDIUM | routes/public/subscribe.py | — | Missing per-endpoint limits |
| LOG-001 | 🟢 LOW | Logging | LOW | routes/public/subscribe.py | 171,212 | Full tokens logged |
| SEC-001 | ✅ OK | SSRF | Secure | services/url.py | — | Well implemented |
| SEC-002 | ✅ OK | Auth | Secure | routes/admin/* | — | Well implemented |
| SEC-003 | ✅ OK | Task Signing | Secure | services/task_security.py | — | Well implemented |
| SEC-004 | ✅ OK | Webhooks | Secure | services/webhooks.py | — | Well implemented |

---

## Appendix B: Investigation Details

### Investigation 1: Template XSS

**Method**: Read all template files rendering LLM-generated content, checked for `|e` filter on every field.

**Key Files**:
- `templates/admin/article_edit.html` — form values
- `templates/admin/dead_letters.html` — article titles
- `templates/partials/article_body.html` — correctly escaped
- `templates/partials/condensed_article.html` — correctly escaped
- `templates/partials/article_card.html` — correctly escaped

**Reference**: AGENTS.md — "LLM-generated content...must be escaped with the `|e` filter"

---

### Investigation 2: Bulk Article ID Validation

**Method**: Read `routes/admin/api/articles.py:bulk_article_operations()`, found no integer validation despite `validate_bulk_ids()` existing.

**Key Files**:
- `routes/admin/api/articles.py:183-191`
- `services/validation.py:90` (the unused function)

---

### Investigation 3: Health Endpoint

**Method**: Read `routes/public/__init__.py:108-115` and `services/health.py:159-189`.

**Key Finding**: Detailed mode exposes git commit and pool stats to unauthenticated users.

---

### Investigation 4: Rate Limiting

**Method**: Read `routes/public/subscribe.py` for rate limit decorators.

**Finding**: No `@limiter.limit()` decorators on subscribe/unsubscribe/verify routes.

---

## Appendix C: Reference Resources

- [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [Flask Template Escaping](https://flask.palletsprojects.com/en/2.3.x/security/)
- [Jinja2 Autoescape](https://jinja.palletsprojects.com/en/3.1.x/api/#autoescape)

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] XSS findings reviewed (1.1, 1.2 confirmed)
- [ ] Testing plan reviewed

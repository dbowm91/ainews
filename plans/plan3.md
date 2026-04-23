# Security Improvement Plan

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Source**: Security Audit — 2026-04-23

---

## Executive Summary

A comprehensive security audit identified 7 areas requiring improvement. This plan prioritizes fixes based on severity and effort.

| Priority | Issue | Severity | Tasks | Effort |
|----------|-------|----------|-------|--------|
| 🔴 High | Redis TLS/SSL | CRITICAL | 2 | Medium |
| 🔴 High | DEBUG enforcement | HIGH | 1 | Low |
| 🟡 Medium | Task signing gaps | MEDIUM | 2 | Low |
| 🟡 Medium | Rate limiting documentation | MEDIUM | 1 | Medium |
| 🟢 Low | Docstring accuracy | LOW | 1 | Minimal |
| ✅ OK | Redirect validation | Secure | — | — |
| ✅ OK | Auth flows | Secure | — | — |
| ✅ OK | XSS prevention | Secure | — | — |

---

## Priority 1: 🔴 CRITICAL/HIGH Priority

### 1.1 Redis TLS/SSL Connection Security

**Severity**: CRITICAL  
**Risk**: All Redis traffic (sessions, task queues, cached configs) transmitted in plaintext. Man-in-the-middle attacks possible on untrusted networks.

**Current State**:
- All Redis connections use plain `redis://` protocol
- No TLS/SSL configured in `ConnectionPool.from_url()` calls
- Password authentication exists but sent unencrypted
- Documentation in `docs/security.md` omits Redis TLS guidance

**Affected Files**:

| File | Location | Description |
|------|----------|-------------|
| `extensions.py` | 106-113 | General Redis pool (DB 0) |
| `services/config_cache.py` | 248 | Config cache Redis pool (DB 1) |
| `extensions.py` | 18-31 | Rate limiter pool (DB 15) |
| `config.py` | 86 | Celery broker URL |

**Note**: Rate limiter uses `_get_limiter_storage_uri()` to construct URL from broker, so SSL changes there should apply there.

**Required Changes**:

1. **Add SSL support to connection pools** (`extensions.py`):
   ```python
   # Detect TLS from protocol or env var
   redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
   ssl_enabled = redis_url.startswith("rediss://") or os.environ.get("REDIS_SSL") == "true"
   
   pool = redis.ConnectionPool.from_url(
       redis_url,
       max_connections=100,
       socket_timeout=5,
       socket_connect_timeout=3,
       socket_keepalive=True,
       ssl=ssl_enabled,  # Add this
   )
   ```

2. **Update config cache** (`services/config_cache.py:248`):
   ```python
   ssl_enabled = url.startswith("rediss://") or os.environ.get("REDIS_SSL") == "true"
   pool = redis.ConnectionPool.from_url(url, max_connections=20, socket_timeout=5, ssl=ssl_enabled)
   ```

3. **Update documentation** (`docs/security.md`):
   - Add "Redis TLS/SSL required for all Redis connections" requirement
   - Document `REDIS_SSL=true` env var
   - Document `rediss://` protocol support

4. **Add environment variable support**:
   - `REDIS_SSL=true` — Force TLS regardless of protocol
   - `REDIS_SSL=false` — Disable TLS regardless of protocol

**Testing**:
- Unit test with `rediss://` URLs
- Integration test with TLS-enabled Redis
- Verify `REDIS_SSL` env var override works

**Effort**: 2-4 hours  
**Risk**: Medium (could break existing deployments without TLS)

**Action Items**:
- [ ] Add TLS support to `extensions.py` Redis pool
- [ ] Add TLS support to `config_cache.py` Redis pool
- [ ] Update Celery broker URL handling for TLS
- [ ] Document in `docs/security.md`
- [ ] Add tests for TLS connections
- [ ] Update `.env.example` with Redis TLS variables

---

### 1.2 DEBUG Mode Enforcement in Production

**Severity**: HIGH  
**Risk**: Accidental DEBUG mode enables may expose sensitive stack traces and enable debugger access.

**Current State**:
- `ProductionConfig.DEBUG = False` (hardcoded)
- `app.py:254-256` only **logs a warning** if `DEBUG=True` with production config
- No check for `FLASK_DEBUG` environment variable

**Gap Scenario**:
```bash
FLASK_CONFIG=production DEBUG=True flask run  # Starts with warning, continues
```

**Required Changes**:

1. **Add to `ProductionConfig.validate()`** (`config.py`):
   ```python
   @classmethod
   def validate(cls):
       """Validate production configuration."""
       errors = []
       
       # Existing validations...
       if cls.SECRET_KEY == "dev-secret-key-change-me":
           errors.append("SECRET_KEY must be changed from default value")
       # ... (existing code)
       
       # Add DEBUG check
       if cls.DEBUG:
           errors.append("DEBUG must be False in production")
       
       if errors:
           raise RuntimeError("Production config errors:\n" + "\n".join(errors))
   ```

2. **Optional: Add `FLASK_DEBUG` env var check** (`app.py`):
   ```python
   flask_debug = os.environ.get("FLASK_DEBUG", "").lower()
   if flask_debug == "true" and config_name == "production":
       logger.error("FLASK_DEBUG=true is not supported in production")
       raise RuntimeError("FLASK_DEBUG cannot be used with production config")
   ```

**Testing**:
- Unit test: `ProductionConfig.DEBUG = True` raises error
- Integration test: `FLASK_CONFIG=production FLASK_DEBUG=true` fails startup

**Effort**: 30 minutes  
**Risk**: Low (fails safe at startup)

**Action Items**:
- [ ] Add DEBUG check to `ProductionConfig.validate()`
- [ ] Add test for DEBUG enforcement
- [ ] (Optional) Check `FLASK_DEBUG` env var

---

## Priority 2: 🟡 MEDIUM Priority

### 2.1 Celery Task Signature Verification for Beat Tasks

**Severity**: MEDIUM  
**Risk**: Tasks accepting arguments from Celery Beat without HMAC signing could be manipulated by attackers with broker access.

**Current State** (17 total tasks):
- ✅ Signed & verified (3): `run_all_sources`, `select_article`, `generate_daily_newsletters`
- ❌ Not verified but accepts args (1): `cleanup_old_article_versions`
- ❌ Not verified, no args (13): Internal pipeline tasks, cleanup tasks (OK)

**Specific Gap**:

| Task | Location | Args | Risk |
|------|----------|------|------|
| `cleanup_old_article_versions` | tasks/cleanup.py:152 | `days_to_keep: 90` | Attacker could dispatch with arbitrary `days_to_keep` |

**Required Changes**:

1. **Add signature verification to `cleanup_old_article_versions`**:

   Current code in `tasks/cleanup.py`:
   ```python
   @shared_task(bind=True, autoretry_for=(ConnectionError, TimeoutError))
   def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
   ```

   Should add at start of task:
   ```python
   from services.task_security import verify_task

   @shared_task(bind=True, autoretry_for=(ConnectionError, TimeoutError))
   def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
       if not verify_task("cleanup_old_article_versions", (), {"days_to_keep": days_to_keep, "dry_run": dry_run}):
           raise ValueError("Invalid task signature")
   ```

2. **Celery Beat Dispatch Issue**:
   - Celery Beat passes `kwargs` via `celery_app.send_task()` which supports `_signature`
   - But current beat schedule in `config.py:174-177` uses static kwargs without signing
   - **Solution**: Sign kwargs at schedule creation time using `sign_task()` from `services.task_security`
   
   **Important**: Signing must happen after `CELERY_TASK_SECRET` is loaded (typically at app startup or config reload). `sign_task()` returns unsigned dict if secret is not configured, causing verification to fail — which is the desired fail-closed behavior.

   Example:
   ```python
   # config.py - imports at top
   from services.task_security import sign_task

   # config.py:177 - fixed (signed kwargs)
   "kwargs": sign_task(
       "cleanup_old_article_versions",
       (),
       {"days_to_keep": versions_days, "dry_run": False}
   ),
   ```

   **Alternative**: Remove args from beat schedule and use hardcoded defaults in task (simpler but less flexible)

**Note**: Internal pipeline tasks (`research_article`, `write_article`, `edit_article`) correctly do NOT have verification — they use `.s()` positional args which inherently cannot carry kwargs including `_signature`.

**Effort**: 1-2 hours  
**Risk**: Low (fails safe if signature missing)

**Action Items**:
- [ ] Add `verify_task()` to `cleanup_old_article_versions`
- [ ] Update beat schedule in `config.py` to include signed kwargs
- [ ] Or: Use hardcoded defaults in task (simpler alternative)

---

### 2.2 Docstring Accuracy for verify_task()

**Severity**: LOW  
**Risk**: Documentation misleading; doesn't affect security if implementation is correct.

**Current State**: `services/task_security.py:57`:
```python
Returns:
    True if signature is valid, no secret is configured, or no signature present (internal call)
```

**Issue**: The docstring doesn't distinguish between "no secret configured" (returns False, fail-closed) and "no signature present" (returns True, allows internal calls).

**Actual Behavior** (verified correct):
```python
if not secret:
    return False  # Fail closed when no secret configured

if "_signature" not in kwargs:
    return True   # Internal .s() calls don't have _signature

return hmac.compare_digest(...)  # Verify provided signature
```

**Required Changes**:

1. **Update docstring** (`services/task_security.py:47-58`):
   ```python
   Returns:
       True if signature is valid or no signature is present (indicating internal call)
       False if signature is invalid or CELERY_TASK_SECRET is not configured
   ```

**Effort**: 5 minutes  
**Risk**: None

**Action Items**:
- [ ] Update `verify_task()` docstring for accuracy

---

### 2.3 Rate Limiting Documentation

**Severity**: MEDIUM  
**Risk**: Unclear whether infrastructure handles rate limiting or if app-level limits are needed.

**Current State**:
- Admin login: 10/minute explicit limit
- All other routes: default 60/minute via Flask-Limiter
- AGENTS.md: "Do not add @limiter.limit() decorators" — app runs behind WAF
- `docs/deployment.md:740-763`: Documents Nginx rate limiting example
- **No WAF configuration files exist in repo**

**Gap**: AGENTS.md says WAF handles it, but no WAF config is provided or documented.

**Required Changes**:

1. **Option A — Document WAF requirement explicitly**:
   - Update `docs/deployment.md` with complete WAF configuration
   - Add checklist for rate limiting verification

2. **Option B — Add explicit rate limits** (per endpoint):
   - Add `@limiter.limit()` to sensitive public endpoints
   - Override AGENTS.md guidance if WAF not guaranteed

3. **Option C — Hybrid approach**:
   - Add lightweight per-endpoint limits as defense-in-depth
   - Keep WAF documentation

**Recommendation**: Option C — add explicit limits for:
- `/subscribe` — prevent email enumeration
- `/search` — prevent search abuse
- `/article/<id>` — prevent scraping

**Effort**: 2-3 hours  
**Risk**: Low (rate limiting is safe)

**Action Items**:
- [ ] Decide on approach (A, B, or C)
- [ ] Implement chosen approach
- [ ] Update AGENTS.md if adding explicit limits

---

## Priority 3: ✅ Already Secure (No Action Needed)

### 3.1 Redirect URL Validation

**Finding**: NO open redirect vulnerabilities.

| Redirect Point | Validation | Status |
|---------------|------------|--------|
| Admin login `?next=` | `_safe_redirect_url()` | ✅ Secure |
| All other redirects | Hardcoded or `url_for()` | ✅ Secure |

**Conclusion**: Properly implemented. No changes needed.

---

### 3.2 Admin Authentication

**Finding**: Robust implementation.

- Session-based auth with `@require_auth` decorator
- Werkzeug password hashing (scrypt/pbkdf2/argon2)
- `session.clear()` on successful login (session fixation prevention)
- Login lockout: 5 failures → 15 minute block

**Conclusion**: Well implemented. No changes needed.

---

### 3.3 Webhook Security

**Finding**: Proper encryption at rest.

- Fernet (AES-128-CBC) for webhook secrets
- HMAC-SHA256 payload signing
- Replay protection via timestamp

**Conclusion**: Well implemented. No changes needed.

---

### 3.4 LLM Prompt Injection Prevention

**Finding**: XML escaping in place.

- `esc_xml_text()` and `esc_xml_attr()` in `services/prompts.py`
- `_escape_prompt_data()` for nested dicts
- Used in all subagent prompt building

**Conclusion**: Well implemented. No changes needed.

---

### 3.5 Input Validation

**Finding**: Comprehensive validators.

- `services/validation.py`: slugs, tokens, categories, bulk IDs
- `services/url.py`: SSRF protection with DNS cache
- Pydantic schemas for task inputs

**Conclusion**: Well implemented. No changes needed.

---

## Implementation Order

```
Phase 1: High Priority
├── 1.2 DEBUG enforcement          (30 min, 1 file)
└── 1.1 Redis TLS/SSL              (2-4 hrs, 4 files)

Phase 2: Medium Priority
├── 2.2 Docstring accuracy        (5 min, 1 file)
├── 2.1 Task signing gap         (1-2 hrs, 2 files)
└── 2.3 Rate limiting docs       (2-3 hrs, docs)

Phase 3: Documentation
└── Update security.md with findings
```

---

## Testing Requirements

1. **Before any changes**:
   ```bash
   .venv/bin/ruff check . --exclude .venv
   .venv/bin/python -m pytest tests/ -x -q --tb=short
   ```

2. **After Redis TLS changes**:
   - Unit tests with `rediss://` URLs
   - Integration test with TLS Redis (if available)

3. **After DEBUG enforcement**:
   - Unit test: `ProductionConfig.DEBUG = True` raises
   - Integration: `FLASK_CONFIG=production python run.py` (if DEBUG set)

4. **After task signing changes**:
   - Verify unsigned calls fail
   - Verify signed calls succeed

---

## Rollback Plan

| Change | Rollback Method |
|--------|----------------|
| Redis TLS | Remove `ssl=` parameter, revert to `redis://` |
| DEBUG enforcement | Remove check from `ProductionConfig.validate()` |
| Task signing | Remove `verify_task()` call |
| Rate limiting | Remove `@limiter.limit()` decorators |
| Docstring | Revert to original text |

---

## Appendix A: Issue Summary Table

| ID | Priority | Category | Severity | File(s) | Description |
|----|----------|----------|----------|---------|-------------|
| SEC-001 | 🔴 HIGH | TLS | CRITICAL | extensions.py, config_cache.py | No TLS for Redis connections |
| SEC-002 | 🔴 HIGH | Config | HIGH | config.py | DEBUG warning-only enforcement |
| SEC-003 | 🟡 MEDIUM | Task | MEDIUM | tasks/cleanup.py | cleanup_old_article_versions lacks signing |
| SEC-004 | 🟡 MEDIUM | Docs | MEDIUM | docs/deployment.md | WAF config unclear |
| SEC-005 | 🟢 LOW | Docs | LOW | services/task_security.py | Misleading docstring |
| SEC-006 | ✅ OK | Auth | Secure | routes/admin/* | Well implemented |
| SEC-007 | ✅ OK | XSS | Secure | templates/* | Well implemented |
| SEC-008 | ✅ OK | Redirect | Secure | routes/* | Well implemented |

---

## Appendix B: Celery Task Verification Status

| Task | File | Verified | Type | Notes |
|------|------|---------|------|-------|
| run_all_sources | tasks/crawl.py | ✅ | External | Signed from HTTP routes |
| select_article | tasks/select.py | ✅ | External | Signed from HTTP routes |
| generate_daily_newsletters | tasks/newsletter.py | ✅ | External | Signed from HTTP routes |
| **cleanup_old_article_versions** | tasks/cleanup.py | ❌ | **Beat w/args** | **Needs signing** |
| process_item | tasks/extract.py | N/A | Internal | Uses `.s()` positional |
| research_article | tasks/research.py | N/A | Internal | Uses `.s()` positional |
| write_article | tasks/write.py | N/A | Internal | Uses `.s()` positional |
| edit_article | tasks/edit.py | N/A | Internal | Uses `.s()` positional |
| *others* | tasks/*.py | N/A | Beat, no args | Safe — no args from external |

---

## Appendix C: Reference Resources

- [OWASP Redis Security](https://cheatsheetseries.owasp.org/cheatsheets/Redis_Recurity_Note.html)
- [Flask DEBUG Security](https://flask.palletsprojects.com/en/2.3.x/config/)
- [Celery Security](https://docs.celeryproject.org/en/stable/userguide/security.html)
- [HMAC Security](https://docs.python.org/3/library/hmac.html)

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] Redis TLS approach agreed (Option: auto-detect rediss:// or env var)
- [ ] Rate limiting approach decided (A/B/C from section 2.3)
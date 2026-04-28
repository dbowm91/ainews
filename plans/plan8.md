# Security Improvement Plan - Plan 8

**Date:** 2026-04-28  
**Auditor:** opencode  
**Scope:** Security audit findings from deep dive analysis

---

## Executive Summary

The ainews codebase demonstrates **strong security practices** overall, with proper implementations of:
- SSRF prevention (`services/url.py`)
- CSRF protection (Flask-WTF + `@validate_csrf_json`)
- XSS prevention (consistent `|e` filter usage, CSP with nonce)
- Session security (hashing, fixation prevention)
- Celery task HMAC signing (`services/task_security.py`)
- Webhook encryption at rest (Fernet)

However, **critical operational security issues** exist:
1. All sensitive files have world-readable/writable permissions (777)
2. Redis has no password authentication in Docker deployment
3. No permission validation exists in application startup code

This plan addresses all findings in priority order.

---

## Critical Priority (Fix Immediately)

### 1. Fix File Permissions - Sensitive Files Are 777

**Current State:**
```
-rwxrwxrwx .env (contains SECRET_KEY, ADMIN_PASSWORD, API keys)
-rwxrwxrwx providers.yaml (API key references)
-rwxrwxrwx sources.yaml (RSS config)
-rwxrwxrwx topics.yaml (topic definitions)
-rwxrwxrwx instance/*.db (user data, articles, subscribers)
-rwxrwxrwx instance/*.db-shm (WAL shared memory)
-rwxrwxrwx instance/*.db-wal (WAL write-ahead log)
drwxrwxrwx instance/ (database directory)
```

**Risk:** Any local user can read secrets, modify databases, or corrupt data.

**Recommended Permissions:**
| File/Directory | Current | Target | Reason |
|----------------|---------|--------|--------|
| `.env` | 777 | **600** | Contains all secrets (SECRET_KEY, passwords, API keys) |
| `providers.yaml` | 777 | **600** | Contains API key references (even if using env vars) |
| `pipeline.yaml` | 775 | **644** | System prompts (intellectual property) |
| `sources.yaml` | 777 | **644** | RSS feed configuration |
| `topics.yaml` | 777 | **644** | Topic definitions |
| `instance/` | 777 | **700** | Contains databases |
| `instance/*.db` | 777 | **600** | User data, subscriber emails, articles |
| `instance/*.db-shm` | 777 | **600** | WAL shared memory |
| `instance/*.db-wal` | 777 | **600** | WAL write-ahead log |

**Immediate Fix Command:**
```bash
chmod 600 /home/sugarwookie/projects/ainews/.env
chmod 600 /home/sugarwookie/projects/ainews/providers.yaml
chmod 644 /home/sugarwookie/projects/ainews/pipeline.yaml
chmod 644 /home/sugarwookie/projects/ainews/sources.yaml
chmod 644 /home/sugarwookie/projects/ainews/topics.yaml
chmod 700 /home/sugarwookie/projects/ainews/instance
chmod 600 /home/sugarwookie/projects/ainews/instance/*.db
chmod 600 /home/sugarwookie/projects/ainews/instance/*.db-shm 2>/dev/null || true
chmod 600 /home/sugarwookie/projects/ainews/instance/*.db-wal 2>/dev/null || true
```

---

### 2. Redis Security - No Password in Docker Compose

**Current State (docker-compose.yml lines 84-93):**
```yaml
redis:
  image: redis:7-alpine
  volumes:
    - redis-data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
  restart: unless-stopped
```

**Problems:**
- No `requirepass` - any container on the Docker network can access Redis
- No ACL configuration
- Connection URLs don't include password: `redis://redis:6379/0`

**Risk:** Data exfiltration, DoS via FLUSHALL, pipeline state corruption, bypass rate limits.

**Recommended Fix:**

**Step 1: Generate Redis Password**
```bash
openssl rand -base64 32
# Or:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Step 2: Update `.env` File**
```env
REDIS_PASSWORD=<generated-password>
```

**Step 3: Update `docker-compose.yml`**
```yaml
services:
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis-data:/data
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    # No ports exposed - good practice, keep it

  web:
    build: .
    environment:
      - FLASK_CONFIG=production
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/1
    # ... rest of config

  celery-worker:
    build: .
    environment:
      - FLASK_CONFIG=production
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/1
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -h redis -a ${REDIS_PASSWORD} ping"]
    # ... rest of config

  celery-beat:
    build: .
    environment:
      - FLASK_CONFIG=production
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/1
    # ... rest of config
```

**Step 4: Verify Code Supports Password**

The code in `extensions.py` (lines 89-105) already supports `REDIS_PASSWORD`:
```python
redis_password = os.environ.get("REDIS_PASSWORD")
if redis_password:
    # Reconstruct URL with password
```

No code changes needed - just configuration updates.

---

## Medium Priority (Code Improvements)

### 3. Add File Permission Validation at Startup

**Current State:** No validation that `.env` or config files have secure permissions.

**Files to Modify:** `config.py`

**Recommended Code Change in `config.py`:**

Add after `load_dotenv()` call (around line 19):

```python
import stat
from pathlib import Path

def _check_sensitive_file_permissions():
    """Warn if sensitive files have insecure permissions."""
    files_to_check = [
        (".env", 0o600),
        ("providers.yaml", 0o644),
        ("pipeline.yaml", 0o644),
    ]
    
    for filename, max_perm in files_to_check:
        f = Path(filename)
        if not f.exists():
            continue
        file_perm = stat.S_IMODE(f.stat().st_mode)
        if file_perm > max_perm:
            logger.warning(
                "INSECURE FILE PERMISSIONS: %s has %o (recommended: %o or stricter). "
                "Run: chmod %o %s",
                filename, file_perm, max_perm, max_perm, filename
            )

_check_sensitive_file_permissions()
```

**Add to `ProductionConfig.validate()` (around line 224):**

```python
@classmethod
def validate(cls):
    if cls.DEBUG:
        raise RuntimeError("DEBUG must be False in production")
    if not cls.SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set in production")
    # ... existing validations ...
    
    # Check .env file permissions in production
    env_path = Path(".env")
    if env_path.exists():
        file_perm = stat.S_IMODE(env_path.stat().st_mode)
        if file_perm != 0o600:
            raise RuntimeError(
                f"INSECURE .env FILE PERMISSIONS ({oct(file_perm)}). "
                f"Run: chmod 600 .env"
            )
```

---

### 4. Update `install.sh` to Set Proper Permissions

**Current State:** `install.sh` only sets `chmod 600` for `.env` (line 153), but not for other config files or database directory.

**Recommended Changes to `scripts/install.sh`:**

After line 153 (after `.env` permissions), add:

```bash
# Set secure permissions on sensitive files
chmod 600 "$APP_DIR/.env"
chmod 600 "$APP_DIR/providers.yaml" 2>/dev/null || true  # Contains API key references
chmod 644 "$APP_DIR/pipeline.yaml" 2>/dev/null || true
chmod 644 "$APP_DIR/sources.yaml" 2>/dev/null || true
chmod 644 "$APP_DIR/topics.yaml" 2>/dev/null || true

# Restrict instance directory and database files
chmod 700 "$APP_DIR/instance" 2>/dev/null || true
chmod 600 "$APP_DIR/instance"/*.db 2>/dev/null || true
chmod 600 "$APP_DIR/instance"/*.db-* 2>/dev/null || true

chown -R "$APP_USER":"$APP_GROUP" "$APP_DIR"
```

---

### 5. Embed Lua Script (Code Quality)

**Current State:** `routes/admin/__init__.py` loads Lua script from file path (lines 99-103). All other Lua scripts in the codebase (`services/limiter.py`, `tasks/crawl.py`, `tasks/newsletter.py`) are embedded as Python strings.

**Recommended Change:**

In `routes/admin/__init__.py`, replace lines 92-104:

**Before:**
```python
_LUA_SCRIPT = None

def _get_lockout_lua_script():
    """Load the login lockout Lua script (cached after first load)."""
    global _LUA_SCRIPT
    if _LUA_SCRIPT is None:
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "services", "login_lockout.lua"
        )
        with open(script_path) as f:
            _LUA_SCRIPT = f.read()
    return _LUA_SCRIPT
```

**After:**
```python
_LOGIN_LOCKOUT_SCRIPT = """
-- Atomic login attempt tracking and lockout check.
-- Returns 1 if locked out, 0 if allowed.
-- KEYS[1] = lockout hash key
-- ARGV[1] = current timestamp
-- ARGV[2] = lockout window in seconds
-- ARGV[3] = max attempts threshold

local count = redis.call('HINCRBY', KEYS[1], 'count', 1)
redis.call('HSETNX', KEYS[1], 'first_attempt', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])

if count >= tonumber(ARGV[3]) then
    return 1
end
return 0
"""

def _get_lockout_script():
    """Get the login lockout Lua script (embedded)."""
    return _LOGIN_LOCKOUT_SCRIPT
```

Then update the usage in `_check_and_record_attempt()` (around line 181):

**Before:**
```python
result = r.eval(
    _get_lockout_lua_script(),
    1,
    key,
    str(time.time()),
    str(_get_login_lockout_seconds()),
    str(_get_login_max_attempts()),
)
```

**After:**
```python
# Use register_script for better performance (Redis caches by SHA1)
_lockout_script_obj = None

def _get_lockout_redis_script(redis_client):
    """Get cached Redis script object."""
    global _lockout_script_obj
    if _lockout_script_obj is None:
        _lockout_script_obj = redis_client.register_script(_LOGIN_LOCKOUT_SCRIPT)
    return _lockout_script_obj

# In _check_and_record_attempt():
r = _get_redis()
script = _get_lockout_redis_script(r)
result = script(
    keys=[key],
    args=[
        str(time.time()),
        str(_get_login_lockout_seconds()),
        str(_get_login_max_attempts()),
    ],
)
```

---

## Low Priority (Nice to Have)

### 6. REPO_URL Default Value - Fail Early with Clear Error

**Current State:** `install.sh` line 11: `REPO_URL="${REPO_URL:-https://github.com/yourorg/ainews.git}"`

**Problem:** Placeholder URL causes installation failure with unhelpful git error.

**Recommended Change to `scripts/install.sh`:**

After line 11, add:

```bash
# Fail early if REPO_URL is the default placeholder
if [[ "$REPO_URL" == *"yourorg/ainews"* ]]; then
    log_error "============================================="
    log_error "REPO_URL is set to a placeholder value!"
    log_error "============================================="
    log_error "The default REPO_URL is not a real repository."
    log_error ""
    log_error "To install from your fork/clone:"
    log_error "  REPO_URL=https://github.com/YOUR_ORG/ainews.git \\"
    log_error "    bash scripts/install.sh"
    log_error ""
    log_error "Or clone manually first:"
    log_error "  git clone https://github.com/YOUR_ORG/ainews.git /opt/ainews"
    log_error "  bash scripts/install.sh -d /opt/ainews"
    log_error "============================================="
    exit 1
fi

# Basic URL validation
if [[ ! "$REPO_URL" =~ ^https?://[^[:space:]]+$ ]]; then
    log_error "Invalid REPO_URL format: $REPO_URL"
    log_error "URL must start with http:// or https://"
    exit 1
fi
```

---

### 7. CSP `style-src 'unsafe-inline'` - Optional Hardening

**Current State:** `app.py` line 112: `"style-src": "'self' 'unsafe-inline'"`

**Analysis:** Only 1 location uses inline styles (`templates/admin/dashboard.html:33`) to set `--bar-width` CSS custom property. This is low risk - no user input flows into the style attribute.

**Optional Improvement (JavaScript approach):**

Remove `style="--bar-width: {{ pct }}%"` from `templates/admin/dashboard.html` and use JavaScript:

```html
<div class="pipeline-bar-segment pipeline-bar-{{ status }}" 
     data-bar-width="{{ pct }}" 
     title="{{ status }}: {{ count }} ({{ pct }}%)">
</div>

<script nonce="{{ csp_nonce() }}">
document.querySelectorAll('[data-bar-width]').forEach(el => {
    el.style.setProperty('--bar-width', el.dataset.barWidth + '%');
});
</script>
```

Then update CSP in `app.py`:
```python
csp = {
    "default-src": "'self'",
    "style-src": "'self'",  # Remove 'unsafe-inline'
    # ... rest of config
}
```

**Priority:** Low - minimal security benefit, mainly defense in depth.

---

### 8. Session Cookie Secure Flag - No Changes Needed

**Current State:** ✅ **Already Secure**

- `ProductionConfig` explicitly sets `SESSION_COOKIE_SECURE = True` (config.py:214)
- `ProductionConfig.validate()` enforces this (raises RuntimeError if False)
- Flask-Talisman forces `True` at runtime when not in debug mode
- Nginx configuration enforces HTTPS (redirects HTTP to HTTPS)

**Action:** None required.

---

## Implementation Order

| Order | Item | Priority | Estimated Effort |
|-------|------|----------|------------------|
| 1 | Fix file permissions (chmod commands) | Critical | 5 minutes |
| 2 | Update docker-compose.yml + .env for Redis | Critical | 15 minutes |
| 3 | Add permission validation to config.py | Medium | 30 minutes |
| 4 | Update install.sh permissions | Medium | 15 minutes |
| 5 | Embed Lua script in routes/admin/__init__.py | Medium | 15 minutes |
| 6 | Fix REPO_URL validation in install.sh | Low | 10 minutes |
| 7 | CSP unsafe-inline hardening | Low | 30 minutes (optional) |

---

## Files That Need Changes

### Critical Priority
- `.env` (permissions - manual fix)
- `instance/*.db`, `instance/` (permissions - manual fix)
- `docker-compose.yml` (add Redis password)
- `.env` (add `REDIS_PASSWORD`)

### Medium Priority
- `config.py` (add `_check_sensitive_file_permissions()` + update `ProductionConfig.validate()`)
- `scripts/install.sh` (add permission setting + REPO_URL validation)
- `routes/admin/__init__.py` (embed Lua script)

### Documentation Updates
- `docs/security.md` (add file permission section)
- `docs/deployment.md` (Redis security section)
- `.env.example` (file permission note)

---

## Verification Steps

### After Critical Fixes:
```bash
# 1. Verify file permissions
ls -la /home/sugarwookie/projects/ainews/.env
ls -la /home/sugarwookie/projects/ainews/*.yaml
ls -la /home/sugarwookie/projects/ainews/instance/
# Should show: .env=600, *.yaml=644 or 600, instance/=700

# 2. Test Redis authentication
docker-compose exec redis redis-cli -a $REDIS_PASSWORD ping
# Should return: PONG

# 3. Verify application starts
.venv/bin/python -c "from app import create_app; app = create_app('production')"
# Should show no permission warnings
```

### After Code Changes:
```bash
# 1. Run lint
.venv/bin/ruff check . --exclude .venv

# 2. Run tests
.venv/bin/python -m pytest tests/ -x -q

# 3. Test production validation
.venv/bin/python -c "
from config import ProductionConfig
try:
    ProductionConfig.validate()
    print('Validation passed')
except RuntimeError as e:
    print(f'Validation failed: {e}')
"
```

---

## Summary

| Priority | Items | Count |
|----------|-------|-------|
| 🔴 Critical | File permissions, Redis security | 2 |
| 🟡 Medium | Permission validation, install.sh, Lua script | 3 |
| 🟢 Low | REPO_URL, CSP unsafe-inline, session cookie (no action) | 2 (1 optional) |

**Total Estimated Time:** ~2 hours (excluding optional CSP hardening)

**Next Step:** User approval to begin implementation.

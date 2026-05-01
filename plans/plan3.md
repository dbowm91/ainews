# Security Improvement Plan - ainews Codebase

**Date:** 2026-05-01  
**Status:** Ready for Implementation  
**Estimated Total Effort:** ~65-95 hours  
**Auditor:** AI Security Review (via opencode)

---

## Executive Summary

The ainews codebase demonstrates **good security foundations** with defense-in-depth approach (CSP, SSRF prevention, CSRF protection, audit logging). However, **critical issues** exist that require immediate attention:

**Overall Security Rating:** 🟡 **MODERATE** (would be 8.5+/10 after critical fixes)

| Priority | Items | Effort | Impact |
|----------|-------|--------|--------|
| 🔴 CRITICAL | 2 items | ~1 hour | Prevents immediate exploitation |
| 🟠 HIGH | 4 items | 25-35 hours | Significant security improvement |
| 🟡 MEDIUM | 4 items | 35-50 hours | Enhanced security posture |
| 🟢 LOW | 1 item | ~5 hours | Maintenance & compliance |

---

## 🔴 CRITICAL - Fix Immediately

### 1. Fix `.env` File Permissions

**Current State:**
```bash
-rwxrwxrwx 1 sugarwookie sugarwookie 333 Apr 30 20:27 /home/sugarwookie/projects/ainews/.env
```

**Risk:** Any user/process on the system can read ALL secrets (SECRET_KEY, API keys, passwords).

**Root Cause:** Likely a recursive `chmod 777` was run on the project directory. 30+ files have erroneous execute permissions.

**Fix Command (Run Immediately):**
```bash
chmod 600 /home/sugarwookie/projects/ainews/.env
ls -la /home/sugarwookie/projects/ainews/.env  # Verify: -rw------- (600)
```

**Bulk Permission Repair:**
```bash
# Remove execute permissions from non-script files
find /home/sugarwookie/projects/ainews -type f \
  ! -name "*.sh" \
  ! -path "*/.git/*" \
  ! -path "*/.venv/*" \
  -exec chmod 644 {} \;

# Set scripts as executable
find /home/sugarwookie/projects/ainews -type f -name "*.sh" -exec chmod 755 {} \;

# Verify .env
chmod 600 /home/sugarwookie/projects/ainews/.env
```

**Code Changes Needed:**

1. **Update `Makefile` (line 11):**
```makefile
@test -f .env || (cp .env.example .env && chmod 600 .env && echo "Created .env — edit it before running")
```

2. **Update `scripts/dev.sh` (after line 57):**
```bash
cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
chmod 600 "$PROJECT_DIR/.env"
log_warn "Edit .env to configure your settings before running"
```

3. **Add startup permission check to `app.py`:**
```python
import os
import stat

env_path = ".env"
if os.path.exists(env_path):
    mode = os.stat(env_path).st_mode
    if mode & stat.S_IROTH or mode & stat.S_IWOTH:
        print("WARNING: .env file has insecure permissions. Run: chmod 600 .env")
```

**Effort:** 5 minutes (fix) + 30 minutes (code improvements)

---

### 2. Regenerate Weak `SECRET_KEY`

**Current Value:** `dev-secret-key-change-me-now-changed-32chars`  
**Issue:** Human-readable, predictable pattern — NOT cryptographically secure.

**Risk:** Session hijacking (forged session cookies), CSRF token prediction.

**Fix Command:**
```bash
# Generate new secure key
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "New SECRET_KEY: $NEW_KEY"

# Update .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_KEY/" /home/sugarwookie/projects/ainews/.env
```

**Code Improvement - Add Validation to `config.py`:**

Add helper function:
```python
import re

def _is_strong_secret_key(key: str) -> tuple[bool, str]:
    """Check if a secret key meets strength requirements.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not key:
        return False, "SECRET_KEY must be set"
    
    if len(key) < 32:
        return False, "SECRET_KEY must be at least 32 characters"
    
    # Check for common weak patterns
    weak_patterns = [
        r'^dev-', r'secret', r'password', r'change-me', r'changeme',
        r'default', r'test', r'12345', r'(.)\1{5,}'  # Repeated chars
    ]
    for pattern in weak_patterns:
        if re.search(pattern, key, re.IGNORECASE):
            return False, f"SECRET_KEY appears to contain weak pattern: {pattern}"
    
    # For hex keys (most common from secrets.token_hex), check length = 64
    if re.fullmatch(r'[0-9a-fA-F]{64}', key):
        return True, ""
    
    # For base64 keys from token_urlsafe(32), check length ~43
    if re.fullmatch(r'[a-zA-Z0-9_\-]{43}', key):
        return True, ""
    
    # For other formats, warn but don't fail
    if len(key) >= 64:
        return True, ""
    
    return True, "WARNING: SECRET_KEY format not recognized as standard hex or base64"
```

Update `ProductionConfig.validate()`:
```python
@classmethod
def validate(cls):
    if cls.DEBUG:
        raise RuntimeError("DEBUG must be False in production")
    
    # Enhanced SECRET_KEY validation
    is_valid, message = _is_strong_secret_key(cls.SECRET_KEY)
    if not is_valid:
        raise RuntimeError(f"SECRET_KEY validation failed: {message}")
    
    if not cls.SESSION_COOKIE_SECURE:
        raise RuntimeError("SESSION_COOKIE_SECURE must be True in production")
    # ... rest of validation
```

**Effort:** 15 minutes (regenerate) + 1 hour (code improvements)

---

## 🟠 HIGH - Fix Soon

### 3. Fix FTS5 Query Injection Vulnerability

**File:** `routes/admin/api/articles.py:88`  
**Risk:** Attackers can manipulate FTS5 search queries to access unauthorized data or cause errors.

**Vulnerable Code:**
```python
if _query_looks_like_url(query):
    fts_query = f'original_url:"{query}"'  # VULNERABLE!
```

**Attack Examples:**
| Input URL | Resulting FTS5 Query | Effect |
|-----------|---------------------|--------|
| `https://example.com" OR "x` | `original_url:"https://example.com" OR "x"` | Injects OR operator |
| `https://example.com" NOT "x` | `original_url:"https://example.com" NOT "x"` | Injects NOT operator |

**Fix - Add Escape Function:**

Add to `routes/admin/api/articles.py` (module level, before the route handlers):
```python
def _escape_fts5_string(value: str) -> str:
    """Escape a string for safe use inside FTS5 quotes.
    
    In FTS5, double quotes inside quoted strings are escaped by doubling them.
    """
    return value.replace('"', '""')
```

**Update Route Handler:**
```python
from services.pagination import _build_fts_query

if query:
    fts_results = None
    try:
        from sqlalchemy import text
        from extensions import db

        if _query_looks_like_url(query):
            # Safe URL search: escape the URL for FTS5
            escaped_url = _escape_fts5_string(query)
            fts_query = f'original_url:"{escaped_url}"'
        else:
            # Safe general search using existing safe builder
            fts_query = _build_fts_query(query)
        
        if fts_query:
            sql = text(
                "SELECT rowid FROM articles_admin_fts WHERE articles_admin_fts MATCH :q"
            )
            result = db.session.execute(sql, {"q": fts_query}).fetchall()
            fts_results = [row[0] for row in result]
    except Exception:
        logger.debug("FTS5 search unavailable, falling back to ILIKE")
```

**Tests to Add (`tests/test_fts.py`):**
```python
def test_fts5_url_injection_prevention():
    """Test that FTS5 special characters in URLs are escaped."""
    from routes.admin.api.articles import _escape_fts5_string
    
    # Test double-quote escaping
    assert _escape_fts5_string('http://example.com" OR "x') == 'http://example.com"" OR ""x'
    
    # Test that safe URLs pass through
    assert _escape_fts5_string('https://example.com/path') == 'https://example.com/path'
```

**Files to Modify:**
- `routes/admin/api/articles.py` - Fix vulnerable line 88, add escape function
- `tests/test_fts.py` - Add test cases for URL escaping

**Effort:** 2-3 hours

---

### 4. Fix Bare `except Exception` Clauses

**Scope:** ~201 occurrences found (excluding tests and .venv)  
**Guidance:** AGENTS.md line 145: "When catching exceptions, prefer specific types (`SQLAlchemyError`, `ValueError`, `KeyError`, `AttributeError`) over broad `Exception`"

**Priority Order:**

#### CRITICAL (Fix First)

**File:** `routes/decorators.py:29`
```python
# BEFORE
except Exception:
    return jsonify({"error": "CSRF token invalid"}), 400

# AFTER
from flask_wtf.csrf import CSRFError
except CSRFError:
    return jsonify({"error": "CSRF token invalid"}), 400
```

#### HIGH (Fix Soon)

**File:** `tasks/extract.py` (7 occurrences)

| Line | Current | Recommended |
|------|---------|---------------|
| 27 | `except Exception as exc:` | `ConnectionError, TimeoutError, ValueError, AttributeError` |
| 188 | `except Exception as e:` | `ConnectionError, TimeoutError, SQLAlchemyError` |
| 256 | `except Exception as exc:` | `SQLAlchemyError` |
| 318 | `except Exception as e:` | `ValueError, TypeError, KeyError` |
| 345 | `except Exception as exc:` | `SQLAlchemyError, ConnectionError` |
| 350 | `except Exception as e:` | `ConnectionError, TimeoutError, AttributeError` |
| 385 | `except Exception as exc:` | `SQLAlchemyError` |

Example fix for line 256:
```python
from sqlalchemy.exc import SQLAlchemyError
# ...
except SQLAlchemyError as exc:
    db.session.rollback()
    logger.warning("Failed to add citation for duplicate %s: %s", duplicate.id, exc)
```

**File:** `routes/admin/newsletters.py` (4 occurrences)

| Line | Current | Recommended |
|------|---------|---------------|
| 121 | `except Exception:` | `ConnectionError, TimeoutError, ValueError, AttributeError` |
| 167 | `except Exception:` | Same as above |
| 257 | `except Exception as e:` | `ConnectionError, TimeoutError, ProviderServerError, RateLimitError` |
| 267 | `except Exception as e:` | `ConnectionError, TimeoutError, ValueError, KeyError` |

#### MEDIUM (Fix When Convenient)

**Files:**
- `routes/admin/api/articles.py` (11 occurrences) - Use `SQLAlchemyError` for DB operations
- `services/subagent.py` (14 occurrences) - Remove redundant bare excepts after specific handlers
- `tasks/newsletter.py` (9 occurrences) - Use `smtplib.SMTPException` for email
- `services/webhooks.py` (7 occurrences) - Use `cryptography.fernet.InvalidToken`

#### LOW (Acceptable As-Is)

**Files:** `services/llm/*.py` (25 occurrences)  
**Note:** Current pattern is acceptable for provider abstraction:
```python
except (KeyboardInterrupt, SystemExit):
    raise
except Exception as e:
    raise _handle_openai_error(e)
```

**Effort:** 8-12 hours (focus on critical/high first)

---

### 5. Optimize API Token O(n) Lookup

**File:** `routes/admin/__init__.py:35`  
**Issue:** `ApiToken.query.all()` loads ALL tokens for each auth check.

**Performance Impact:**
| Tokens | Bcrypt Checks | Est. Time |
|---------|----------------|-----------|
| 10 | 10 | ~1 second |
| 50 | 50 | ~5 seconds |
| 100 | 100 | ~10 seconds |

**Solution:** Add `token_prefix` column (first 16 chars of token hash) with index.

#### Database Migration

**Create:** `migrations/versions/033_add_api_token_prefix.py`
```python
"""Add token_prefix column to api_tokens for O(1) lookup

Revision ID: 033_add_api_token_prefix
Revises: 032_add_api_tokens
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = '033_add_api_token_prefix'
down_revision = '032_add_api_tokens'


def upgrade():
    # Add token_prefix column
    op.add_column('api_tokens', sa.Column('token_prefix', sa.String(length=16), nullable=True))
    
    # Create index on token_prefix
    op.create_index('ix_api_tokens_prefix', 'api_tokens', ['token_prefix'])
    
    # Expire all existing tokens to force re-creation with prefix
    from datetime import datetime, timezone
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE api_tokens SET expires_at = :now WHERE expires_at IS NULL"),
        {"now": datetime.now(timezone.utc)}
    )


def downgrade():
    op.drop_index('ix_api_tokens_prefix', 'api_tokens')
    op.drop_column('api_tokens', 'token_prefix')
```

#### Model Update (`models.py`)

Add to `ApiToken` class around line 505:
```python
token_prefix = db.Column(db.String(16), index=True, nullable=True)  # NEW
```

#### Token Creation Update (`routes/admin/api_tokens.py`)

Around line 41, update token creation:
```python
# Generate token
plain_token = secrets.token_urlsafe(32)
token_hash_hex = secrets.token_hex(32)

api_token = ApiToken(
    token_hash=generate_password_hash(token_hash_hex),
    token_prefix=token_hash_hex[:16],  # NEW: Store prefix for O(1) lookup
    name=name,
)
```

#### Verification Optimization (`routes/admin/__init__.py`)

Update `verify_api_token()`:
```python
def verify_api_token(token_str):
    """Verify an API token and return True if valid."""
    from werkzeug.security import check_password_hash
    from models import ApiToken

    if "." not in token_str:
        return False
    
    parts = token_str.split(".", 1)
    if len(parts) != 2:
        return False

    provided_hash = parts[1]
    provided_prefix = provided_hash[:16]

    # O(1) lookup using indexed prefix column
    if provided_prefix:
        tokens = ApiToken.query.filter_by(token_prefix=provided_prefix).all()
    else:
        tokens = ApiToken.query.all()  # Fallback for edge cases
    
    for api_token in tokens:
        if check_password_hash(api_token.token_hash, provided_hash):
            from datetime import datetime, timezone
            from extensions import db
            api_token.last_used_at = datetime.now(timezone.utc)
            db.session.commit()
            return True
    return False
```

**Effort:** 6-8 hours

---

### 6. Enhance Exception Handling per AGENTS.md

**Reference:** AGENTS.md line 145

Update all exception handlers to use specific types:
- `SQLAlchemyError` for DB operations
- `ConnectionError, TimeoutError` for network calls
- `ValueError, TypeError, KeyError` for validation

**Files to Update:**
- `tasks/extract.py` - All DB ops need `SQLAlchemyError`
- `tasks/edit.py` - Non-critical fallbacks (acceptable but could be more specific)
- `routes/admin/newsletters.py` - Task triggering needs specific Redis/Celery errors
- `routes/admin/topic_notes.py` - DB ops need `SQLAlchemyError`

**Example Pattern:**
```python
# BEFORE
try:
    db.session.commit()
except Exception as e:
    db.session.rollback()

# AFTER
from sqlalchemy.exc import SQLAlchemyError
try:
    db.session.commit()
except SQLAlchemyError as e:
    db.session.rollback()
    logger.error("Database error: %s", e)
    raise
```

**Effort:** 4-6 hours

---

## 🟡 MEDIUM - When Convenient

### 7. Implement Two-Factor Authentication (2FA)

**Current State:** Password-only authentication for single admin user.  
**Recommendation:** **YES, implement 2FA** - the application handles sensitive data (subscriber emails, API tokens, webhook secrets).

#### New Dependencies

Add to `pyproject.toml`:
```toml
dependencies = [
    # ... existing dependencies ...
    "pyotp>=2.9.0",
    "qrcode[pil]>=7.4.0",
    "cryptography>=42.0.0",  # For encrypting TOTP secrets
]
```

#### Database Schema Changes

**Create:** `migrations/versions/034_add_admin_user_2fa.py`

New model (or extend config-based approach):
```python
class AdminUser(db.Model):
    __tablename__ = "admin_users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, default="admin")
    password_hash = db.Column(db.String(128), nullable=False)
    
    # 2FA fields
    totp_secret = db.Column(db.String(64), nullable=True)  # Encrypted
    totp_enabled = db.Column(db.Boolean, default=False)
    totp_verified_at = db.Column(db.DateTime, nullable=True)
    
    # Backup codes (stored as JSON array of hashed codes)
    backup_codes = db.Column(db.JSON, nullable=True)
    backup_codes_used = db.Column(db.JSON, nullable=True)
    
    # Account metadata
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)
```

#### Login Flow Changes

**Current:**
```
Password → Set session["admin"] = True → Dashboard
```

**New 2FA Flow:**
```
Step 1: Password Entry
Password → Verify against DB/Config → Set session["pre_2fa"] = True → 2FA page

Step 2: 2FA Verification
TOTP Code → Verify against totp_secret → Clear session["pre_2fa"] → Set session["admin"] = True

Step 3: Backup Code Fallback
Backup Code → Verify against hashed backup codes → Mark used → Complete login
```

#### New Routes Required

| Route | Method | Purpose |
|-------|--------|---------|
| `/admin/2fa` | GET/POST | TOTP/Backup code verification |
| `/admin/2fa/setup` | GET/POST | Initial 2FA setup with QR code |
| `/admin/2fa/disable` | POST | Disable 2FA |
| `/admin/2fa/regenerate-backup-codes` | POST | New backup codes |

#### QR Code Generation Example

```python
import pyotp
import qrcode
import io

@admin_bp.route("/2fa/setup", methods=["GET", "POST"])
@require_auth  # Must be logged in first (password only)
def setup_2fa():
    user = get_current_admin_user()
    
    if request.method == "GET":
        # Generate secret if not exists
        if not user.totp_secret:
            secret = pyotp.random_base32()
            session["temp_totp_secret"] = secret
        else:
            secret = decrypt_secret(user.totp_secret)
        
        # Create provisioning URI
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name="admin@ainews",
            issuer_name="ainews"
        )
        
        # Generate QR code
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        
        return render_template("admin/2fa_setup.html", 
                             qr_code=base64.b64encode(buf.read()).decode(),
                             secret=secret)
    
    elif request.method == "POST":
        code = request.form.get("verification_code")
        secret = session.get("temp_totp_secret")
        totp = pyotp.TOTP(secret)
        
        if totp.verify(code):
            user.totp_secret = encrypt_secret(secret)
            user.totp_enabled = True
            user.totp_verified_at = datetime.now(timezone.utc)
            user.backup_codes = hash_backup_codes(generate_backup_codes())
            db.session.commit()
            
            session.pop("temp_totp_secret", None)
            return redirect(url_for("admin.dashboard"))
        else:
            return render_template("admin/2fa_setup.html", error="Invalid code")
```

#### Backup Codes

```python
import secrets

def generate_backup_codes(count=10) -> list[str]:
    """Generate backup codes (format: XXXX-XXXX-XXXX)."""
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(6).upper()
        formatted = f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}"
        codes.append(formatted)
    return codes
```

**Effort:** 16-23 hours

---

### 8. Consider RBAC Implementation

**Current State:** Single admin user with `ADMIN_PASSWORD` env var.  
**Recommendation:** **Delay** unless multiple admin users needed.

#### If Implementing Later - Custom Lightweight Approach

**New Models:**
```python
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    active = db.Column(db.Boolean, default=True, index=True)
    roles = db.relationship("UserRole", backref="user", lazy="dynamic")

class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    permissions = db.relationship("RolePermission", backref="role", lazy="dynamic")

class Permission(db.Model):
    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    category = db.Column(db.String(32))  # Maps to audit categories
```

**Suggested Initial Roles (based on `VALID_CATEGORIES` in audit.py):**
- `superadmin` - All permissions
- `editor` - article:read, article:write, pipeline:read
- `publisher` - newsletter:*, subscriber:read
- `viewer` - *:read (read-only)

**Effort:** 37-53 hours

---

### 9. Improve Login Lockout TOCTOU

**File:** `routes/admin/auth.py`  
**Issue:** Race condition between `_is_locked_out()` check (line 45) and `_check_and_record_attempt()` (line 67).

**Current Problem:**
```
Time of Check:  Multiple requests pass _is_locked_out() check
Time of Use:    All proceed to _check_and_record_attempt()
Result:        Counter can exceed 5 (configured max)
```

**Fix:** Remove redundant initial check (Lua script already handles atomically):
```python
# Remove this block - it's redundant and creates TOCTOU
#if _is_locked_out(ip):
#    error = "Too many failed attempts. Try again later."
#    return render_template("admin/login.html", error=error), 429
```

The Lua script in `services/login_lockout.lua` is already atomic and returns lockout status.

**In-Memory Fallback Note:** Uses `threading.Lock()` but is per-worker only. Acceptable for brief Redis outages.

**Effort:** 2-3 hours

---

### 10. Docker Security Hardening

#### Quick Wins (Implement First)

1. **Bind ports to localhost** in `docker-compose.yml`:
```yaml
services:
  web:
    ports:
      - "127.0.0.1:5000:5000"  # Was: "5000:5000"
```

2. **Add security options** to all services:
```yaml
services:
  web:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    cap_drop:
      - ALL
```

3. **Add logging configuration:**
```yaml
services:
  web:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

4. **Pin base image digests** in Dockerfile:
```dockerfile
FROM python:3.12-slim@sha256:<specific-digest>
```

#### Add Image Scanning to CI/CD

**.github/workflows/ci.yml:**
```yaml
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
          
      - name: Upload Trivy scan results
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'
```

**Effort:** 8-12 hours

---

## 🟢 LOW - Nice to Have

### 11. Add Dependency Scanning

#### Primary Tool: `pip-audit` (Free, Open Source, PyPA Maintained)

**Add to CI:**
```yaml
  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install pip-audit
        run: pip install pip-audit
      - name: Run pip-audit
        run: pip-audit --desc --format=columns
```

**Add to `Makefile`:**
```makefile
security-scan: ## Scan dependencies for vulnerabilities
	@echo "Running pip-audit..."
	.venv/bin/pip install pip-audit
	.venv/bin/pip-audit --desc --format=columns
```

#### Enable GitHub Dependabot

**Create:** `.github/dependabot.yml`
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    groups:
      dev-dependencies:
        dependency-type: "development"
```

**Effort:** ~5 hours

---

## Implementation Roadmap

### Week 1 (Critical + High Priority)

**Days 1-2:**
- [ ] Fix `.env` permissions (`chmod 600 .env`)
- [ ] Regenerate `SECRET_KEY` with `secrets.token_hex(32)`
- [ ] Add `SECRET_KEY` validation to `config.py`
- [ ] Fix bulk file permissions
- [ ] Fix FTS5 injection in `routes/admin/api/articles.py:88`

**Days 3-5:**
- [ ] Start fixing bare `except Exception` clauses (critical/high first)
- [ ] Add `token_prefix` column to `ApiToken` model
- [ ] Optimize `verify_api_token()` function
- [ ] Run linter and tests after each change

### Week 2-3 (Medium Priority - Optional)

- [ ] Implement 2FA if desired (16-23 hours)
- [ ] Improve login lockout TOCTOU
- [ ] Docker security hardening (read-only, no-new-privileges)

### Week 4+ (Low Priority)

- [ ] Add `pip-audit` to CI
- [ ] Enable GitHub Dependabot
- [ ] Consider RBAC (if multi-user needed)

---

## Testing Requirements

After each fix:
```bash
# Run linter
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Verify security fixes
make security-scan  # After implementing dependency scanning
```

**Specific Test Additions:**
- `tests/test_fts.py` - Add FTS5 URL escaping tests
- `tests/test_auth.py` - Add 2FA tests (if implementing)
- `tests/test_api_tokens.py` - Add O(1) lookup tests

---

## Summary Checklist

### CRITICAL (Do Today)
- [ ] `chmod 600 .env`
- [ ] Regenerate `SECRET_KEY` with `secrets.token_hex(32)`
- [ ] Fix bulk file permissions
- [ ] Add `.env` permission check to `app.py`

### HIGH (This Week)
- [ ] Fix FTS5 injection in `routes/admin/api/articles.py:88`
- [ ] Fix `routes/decorators.py:29` (use `CSRFError`)
- [ ] Fix bare `except` in `tasks/extract.py` (7 occurrences)
- [ ] Fix bare `except` in `routes/admin/newsletters.py` (4 occurrences)
- [ ] Add `token_prefix` to `ApiToken` model (migration)
- [ ] Optimize `verify_api_token()` to O(1)
- [ ] Enhance exception handling per AGENTS.md

### MEDIUM (When Convenient)
- [ ] Implement 2FA with pyotp (or defer if single admin)
- [ ] Docker security hardening (read-only, no-new-privileges, Trivy)
- [ ] Improve login lockout TOCTOU
- [ ] Consider RBAC (if multiple users needed)

### LOW (Backlog)
- [ ] Add `pip-audit` to CI
- [ ] Enable GitHub Dependabot
- [ ] Add `make security-scan` target

---

## References

- AGENTS.md - Coding conventions and security notes
- OWASP Top 10 - https://owasp.org/www-project-top-ten/
- Flask Security - https://flask.palletsprojects.com/en/3.1.x/security/
- SQLite FTS5 - https://www.sqlite.org/fts5.html
- PyOTP Documentation - https://pyotp.readthedocs.io/
- Docker Security - https://docs.docker.com/develop/security-best-practices/
- Trivy Scanner - https://github.com/aquasecurity/trivy

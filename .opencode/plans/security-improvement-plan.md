# Security Improvement Plan - ainews

**Date**: 2026-05-05  
**Author**: opencode (hy3-preview-free)  
**Review Status**: Draft - Ready for Implementation

---

## Executive Summary

Based on a comprehensive security audit and deep-dive analysis, this plan outlines **10 security improvements** for the ainews codebase. Items are prioritized as P0 (Critical), P1 (High), P2 (Medium), and P3 (Low).

**Key Findings:**
- Strong security posture with multiple defense layers
- 3 P1 items require immediate attention
- 5 P2 items for medium-term improvement
- 2 P3 items for long-term consideration

---

## P0 - Critical (None Found)

No critical vulnerabilities found. The codebase demonstrates good security practices.

---

## P1 - High Priority

### P1.1: Enforce .env File Permissions (Fail-Closed)

**Severity**: HIGH  
**Current State**: Warning only (app.py:74-82)  
**Issue**: Violates project's "Fail-Closed Policy" (AGENTS.md)

**Problem**:
```python
# Current: Only warns
if mode != "600":
    logger.warning(".env file permissions are %s...", mode)
```

**Solution**: Refuse to start in production with insecure permissions.

**Implementation**:

```python
# File: /home/sugarwookie/projects/ainews/app.py
# Replace lines 74-84 with:

def _validate_config(app, config_name):
    """Validate configuration and enforce security."""
    # ... existing validation ...
    
    # Check .env file permissions
    env_path = Path(app.root_path) / ".env"
    if env_path.exists():
        _check_env_permissions(env_path, config_name)
    else:
        if config_name == "production":
            raise RuntimeError(
                f".env file not found at {env_path}. "
                "Create one from .env.example or use a secrets manager."
            )
        else:
            logger.info(".env file not found, using environment variables")

def _check_env_permissions(env_path: Path, config_name: str) -> None:
    """Check .env file has secure permissions. Fail-closed in production."""
    import stat
    
    file_stat = env_path.stat()
    mode = stat.S_IMODE(file_stat.st_mode)
    
    # Only owner should have access (600) or owner+rw, group+r (640)
    if mode & stat.S_IRWXO:  # Other bits set
        msg = (
            f"Insecure .env permissions {oct(mode)}: world-readable. "
            f"Fix with: chmod 600 {env_path}"
        )
        if config_name == "production":
            raise RuntimeError(f"Security check failed: {msg}")
        else:
            if os.environ.get("ALLOW_INSECURE_ENV", "").lower() != "true":
                logger.warning("Security: %s", msg)
    
    if mode & stat.S_IRWXG:  # Group bits set (and not 640)
        if mode != 0o640:
            msg = (
                f"Questionable .env permissions {oct(mode)}: group-readable. "
                f"Recommended: chmod 600 {env_path}"
            )
            logger.warning("Security: %s", msg)
    
    if mode != 0o600 and mode != 0o640:
        msg = (
            f"Insecure permissions {oct(mode)}. "
            f"Recommended: chmod 600 {env_path}"
        )
        if config_name == "production":
            raise RuntimeError(f"Security check failed: {msg}")
        else:
            logger.warning("Security: %s", msg)
```

**Verification**:
```bash
# Test with wrong permissions
chmod 644 .env
python -c "from app import create_app; create_app('production')"  # Should fail

# Fix
chmod 600 .env
```

---

### P1.2: Fix Redis CVE-2025-49844 (Dependency Update)

**Severity**: HIGH (CVSS 10.0 - Critical)  
**Current State**: `redis==6.4.0` (pyproject.toml:16)  
**Issue**: Redis client/server may be vulnerable to RCE via Lua use-after-free

**Research Finding**: 
- CVE-2025-49844 affects Redis with Lua scripting
- Fixed in Redis server 6.4.2-131+, 7.2.4-138+, 7.4.6-272+
- Python redis client 6.4.0 may need verification

**Solution**: 
1. Verify if Python package or server is affected
2. Upgrade Redis server to patched version
3. Consider upgrading Python client

**Implementation**:

```toml
# File: /home/sugarwookie/projects/ainews/pyproject.toml
# Line 16: Change from
"redis==6.4.0",

# To (verify latest secure version):
"redis>=6.4.2,<7",
```

**Also update CI check**:
```yaml
# .github/workflows/ci.yml - Add to pip-audit job
- name: Run pip-audit
  run: |
    .venv/bin/pip-audit \
      --desc \
      --format json \
      --output pip-audit-report.json \
      --fail-on-severity high
```

**Verification**:
```bash
# Check current Redis server version
redis-cli --version
redis-cli INFO server | grep redis_version

# Run pip-audit to check Python client
.venv/bin/pip-audit
```

---

### P1.3: Add Session Regeneration to Prevent Fixation

**Severity**: HIGH  
**Current State**: `session.clear()` used but no explicit regeneration (routes/admin/auth.py:59-62)  
**Issue**: Session fixation vulnerability - attackers can pre-set session IDs

**Research Finding**:
- Flask default sessions (signed cookies) don't have `session.regenerate()`
- `session.clear()` + setting new data may not guarantee new session ID
- Flask-Session extension has `regenerate()` method

**Solution** (Two options):

**Option A: Enhanced Default Sessions (Simpler - Recommended)**

```python
# File: /home/sugarwookie/projects/ainews/routes/admin/auth.py
# In login() function, replace lines 59-62:

def login():
    # ... password verification ...
    if admin_user and admin_user.totp_enabled:
        session["partial_login"] = True
        session["ip"] = ip
        session["user_agent"] = request.headers.get("User-Agent", "")
        return redirect(url_for("admin.verify_2fa"))
    
    # Clear entire session to force new cookie
    session.clear()
    
    # Set new session data
    session["admin"] = True
    session["ip"] = ip
    session["user_agent"] = request.headers.get("User-Agent", "")
    
    # Force session modification to ensure new cookie
    session.modified = True
    
    # Log the login
    try:
        from services.audit import log_admin_action
        log_admin_action("admin_login", user="admin")
    except (SQLAlchemyError, RuntimeError) as e:
        logger.error("Failed to log admin login action: %s", e)
    
    next_url = request.args.get("next", "")
    return redirect(_safe_redirect_url(next_url))
```

**Option B: Use Flask-Session for Server-Side Sessions (More Secure)**

```bash
# Install Flask-Session
uv pip install Flask-Session
```

```python
# File: /home/sugarwookie/projects/ainews/extensions.py
# Add after line 15:

from flask_session import Session

# Initialize session with Redis backend
session_session = Session()

# In create_app():
def create_app(config_name=None):
    # ... existing code ...
    
    # Configure server-side sessions
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = get_redis()
    app.config["SESSION_USE_SIGNER"] = True
    session_session.init_app(app)
    
    # ... rest of code ...
```

```python
# Then in routes/admin/auth.py, add after login verification:
from flask import current_app

# After successful authentication:
current_app.session_interface.regenerate(session)
```

**Recommendation**: Start with Option A (simpler), consider Option B for long-term.

---

## P2 - Medium Priority

### P2.1: Enable SameSite=Strict for Admin Cookies

**Severity**: MEDIUM  
**Current State**: `SESSION_COOKIE_SAMESITE = "Lax"` (config.py:49)  
**Benefit**: Stronger CSRF protection for admin panel

**Implementation**:

```python
# File: /home/sugarwookie/projects/ainews/config.py
# Change line 49 from:
SESSION_COOKIE_SAMESITE = "Lax"

# To:
SESSION_COOKIE_SAMESITE = "Strict"
```

**Caveat**: If admin panel needs to be accessed via cross-site requests (e.g., from another domain), use "Lax". For same-site admin access, "Strict" is better.

---

### P2.2: Support Multiple Admin Users

**Severity**: MEDIUM  
**Current State**: Single hardcoded "admin" user (routes/admin/auth.py:53)  
**Issue**: No individual accountability, AdminUser model exists but unused

**Research Finding**:
- `AdminUser` model exists in models.py (lines 525-541)
- `password_hash` field exists but never used for authentication
- Login uses `ADMIN_PASSWORD` config instead of database

**Implementation Steps**:

**Step 1: Create Database Migration**

```bash
# Generate migration
uv run flask db migrate -m "Add admin_users table"
```

If migration doesn't detect the table, create manually:

```python
# File: migrations/versions/036_add_admin_users.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("totp_secret", sa.String(32)),
        sa.Column("totp_enabled", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)

def downgrade():
    op.drop_table("admin_users")
```

**Step 2: Update Login Form** (templates/admin/login.html)

Add username field:
```html
<form method="POST">
    <div class="form-group">
        <label for="username">Username</label>
        <input type="text" name="username" id="username" required autofocus>
    </div>
    <div class="form-group">
        <label for="password">Password</label>
        <input type="password" name="password" id="password" required>
    </div>
    <button type="submit">Login</button>
</form>
```

**Step 3: Update Authentication Logic** (routes/admin/auth.py)

```python
# Replace hardcoded "admin" queries with form username
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))
    
    ip = request.remote_addr or "unknown"
    error = None
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        # Query user from database
        admin_user = AdminUser.query.filter_by(username=username).first()
        
        if admin_user and check_password_hash(admin_user.password_hash, password):
            _clear_attempts(ip)
            session.clear()
            session["admin"] = username  # Store actual username
            session["ip"] = ip
            session["user_agent"] = request.headers.get("User-Agent", "")
            session.modified = True
            
            if admin_user.totp_enabled:
                session["partial_login"] = True
                return redirect(url_for("admin.verify_2fa"))
            
            # Log with actual username
            log_admin_action("admin_login", user=username)
            return redirect(_safe_redirect_url(request.args.get("next", "")))
        
        # ... rest of login failure handling ...
```

**Step 4: Update Audit Logging**

Replace all `user="admin"` with actual username from session.

---

### P2.3: Docker Security Hardening

**Severity**: MEDIUM  
**Current State**: Basic Dockerfile exists, some hardening needed  
**Issues**: No `NO_NEW_PRIVILEGES`, no read-only filesystem, build tools in runtime

**Implementation**:

**Hardened Dockerfile** (multi-stage build):

```dockerfile
# File: /home/sugarwookie/projects/ainews/Dockerfile
# syntax=docker/dockerfile:1

# Stage 1: Builder
FROM python:3.12-slim@sha256:YOUR_DIGEST_HERE AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install -e ".[dev]"

# Stage 2: Runtime
FROM python:3.12-slim@sha256:YOUR_DIGEST_HERE AS runtime

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1 \
    libffi8 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --system --gid 1000 ainews \
    && useradd --system --uid 1000 --gid 1000 --create-home ainews

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=ainews:ainews /install /usr/local

# Copy application code
COPY --chown=ainews:ainews . /app/

# Switch to non-root
USER ainews

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "5000", "run:app"]
```

**docker-compose.yml Security Additions**:

```yaml
# File: /home/sugarwookie/projects/ainews/docker-compose.yml
services:
  web:
    # ... existing config ...
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
      - /app/instance
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
```

---

### P2.4: Add GitHub Dependabot for Automated Updates

**Severity**: MEDIUM  
**Current State**: pip-audit in CI, but no automated PR creation  
**Benefit**: Automated dependency updates with security focus

**Implementation**:

```yaml
# File: /home/sugarwookie/projects/ainews/.github/dependabot.yml
# Create this new file:

version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
    # Focus on security updates
    open-pull-requests-limit: 10
    groups:
      python-deps:
        patterns:
          - "*"
```

**Also Enhance Existing pip-audit CI Job**:

```yaml
# File: /home/sugarwookie/projects/ainews/.github/workflows/ci.yml
# Update pip-audit job:

  pip-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      
      - name: Install dependencies
        run: uv sync --all-extras
      
      - name: Run pip-audit
        run: |
          uv run pip-audit \
            --desc \
            --format json \
            --output pip-audit-report.json \
            --fail-on-severity high
        continue-on-error: true
      
      - name: Upload audit report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pip-audit-report
          path: pip-audit-report.json
      
      - name: Check for vulnerabilities
        run: |
          if [ -f pip-audit-report.json ]; then
            vulns=$(cat pip-audit-report.json | jq '.vulnerabilities | length')
            if [ "$vulns" -gt 0 ]; then
              echo "Found $vulns vulnerabilities!"
              cat pip-audit-report.json | jq '.vulnerabilities[] | {package: .name, severity: .severity, id: .id}'
              exit 1
            fi
          fi
```

---

### P2.5: Pin google-genai Exactly (Consistency)

**Severity**: MEDIUM  
**Current State**: `google-genai>=1.0.0,<2.0.0` (pyproject.toml:30)  
**Issue**: Inconsistent with other deps (openai==2.29.0, anthropic==0.86.0)

**Implementation**:

```toml
# File: /home/sugarwookie/projects/ainews/pyproject.toml
# Line 30: Change from
"google-genai>=1.0.0,<2.0.0",

# To (exact pin, consistent with other ML packages):
"google-genai==1.74.0",
```

**Also generate uv.lock for reproducible builds**:

```bash
cd /home/sugarwookie/projects/ainews
uv lock
git add uv.lock
git commit -m "Add uv.lock for reproducible builds"
```

---

## P3 - Low Priority

### P3.1: Add CSP Report-URI for Monitoring

**Severity**: LOW  
**Current State**: CSP configured but no reporting (app.py:103-114)  
**Benefit**: Detects XSS attempts and policy misconfigurations

**Implementation**:

```python
# File: /home/sugarwookie/projects/ainews/app.py
# In _setup_security(), update Talisman config:

csp = {
    "default-src": "'self'",
    "style-src": "'self' 'unsafe-inline'",
    "script-src": "'self'",
    "img-src": "'self' data:",
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
}

Talisman(
    app,
    content_security_policy=csp,
    content_security_policy_report_uri="/csp-report",  # Add this line
    content_security_policy_nonce_in=["script-src"],
    frame_options="SAMEORIGIN",
    referrer_policy="strict-origin-when-cross-origin",
    strict_transport_security_max_age=31536000,
    strict_transport_security_include_subdomains=False,
    permissions_policy={
        "camera": "()",
        "microphone": "()",
        "geolocation": "()",
    },
)
```

**Create CSP Report Endpoint**:

```python
# File: /home/sugarwookie/projects/ainews/routes/public/csp_report.py
import json
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
csp_bp = Blueprint("csp", __name__)

@csp_bp.route("/csp-report", methods=["POST"])
def csp_report():
    """Receive CSP violation reports."""
    try:
        data = json.loads(request.data.decode("utf-8"))
        
        logger.warning(
            "CSP Violation Report",
            extra={
                "csp_report": data,
                "user_agent": request.headers.get("User-Agent"),
                "ip": request.remote_addr,
            }
        )
    except Exception as e:
        logger.error("Failed to process CSP report: %s", e)
    
    return jsonify({"status": "received"}), 200
```

**Register in routes/public/__init__.py**:
```python
from routes.public import csp_report as csp_module
# Register the blueprint
# app.register_blueprint(csp_module.csp_bp)
```

---

### P3.2: Plan PostgreSQL Migration (Long-Term)

**Severity**: LOW (but important for scaling)  
**Current State**: SQLite with WAL mode  
**Trigger for Migration**: 
- Multiple app servers needed
- Write contention noticed in logs
- Database > 5-10GB

**Note**: `docs/postgresql-migration-strategy.md` already exists with a solid plan.

**Action Items**:
1. Monitor for `SQLITE_BUSY` errors
2. Set up alerts on WAL file size
3. Keep migration strategy doc updated
4. Consider migration when adding second app server

---

## Implementation Order

### Phase 1: Immediate (This Week)
1. ✅ P1.1: Enforce .env permissions
2. ✅ P1.2: Fix Redis CVE (upgrade)
3. ✅ P1.3: Add session regeneration

### Phase 2: Short-Term (Next 2-4 Weeks)
4. P2.1: SameSite=Strict
5. P2.2: Multiple admin users (or defer to Phase 3)
6. P2.5: Pin google-genai

### Phase 3: Medium-Term (1-2 Months)
7. P2.3: Docker hardening
8. P2.4: Add Dependabot
9. P2.2: Multiple admin users (if not done in Phase 2)

### Phase 4: Long-Term (3-6 Months)
10. P3.1: CSP reporting
11. P3.2: PostgreSQL migration (when triggered by growth)

---

## Verification Checklist

After implementing each item, verify:

| Item | Verification Command |
|------|----------------------|
| P1.1 | `chmod 644 .env && python -c "create_app('production')"` # Should fail |
| P1.2 | `.venv/bin/pip-audit` # Should show no high/critical vulns |
| P1.3 | Use session fixation test tools / manual testing |
| P2.1 | Check cookie attributes in browser DevTools |
| P2.2 | Create multiple admin users, verify login works |
| P2.3 | `docker scan ainews:latest` # Should pass |
| P2.4 | Check GitHub for Dependabot PRs |
| P2.5 | `uv pip list | grep google-genai` # Should show exact version |
| P3.1 | Check logs for CSP violation reports |

---

## Resources

- [Flask-Session Documentation](https://flask-session.readthedocs.io/)
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)
- [GitHub Dependabot](https://docs.github.com/en/code-security/dependabot)

---

## Summary

| Priority | Items | Effort | Impact |
|----------|-------|--------|--------|
| P1 (High) | 3 items | 2-4 hours | Prevents critical vulnerabilities |
| P2 (Medium) | 5 items | 1-2 days | Improves security posture |
| P3 (Low) | 2 items | 2-4 hours | Monitoring & future-proofing |

**Total Estimated Effort**: 2-3 days

The codebase is already secure. These improvements will make it **more robust** and align with security best practices.

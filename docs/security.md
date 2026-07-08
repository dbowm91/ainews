# Security Documentation

## Security Architecture

### Overview

ainews implements defense-in-depth security with multiple layers:

```
┌─────────────────────────────────────────────────┐
│                 Network Layer                    │
│  Firewall → Nginx (SSL) → Port 5000 (internal)  │
└─────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────┐
│              Application Layer                   │
│   CSRF Protection → Session Security → Auth    │
└─────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────┐
│               Data Layer                         │
│     Password Hashing → Input Validation         │
└─────────────────────────────────────────────────┘
```

### Security Layers

1. **Network**: Firewall blocks direct access to port 5000
2. **Transport**: SSL/TLS required for all connections
3. **Application**: CSRF tokens, secure sessions
4. **Authentication**: Hashed passwords, rate limiting
5. **Authorization**: Admin-only routes protected by auth

---

## Secrets Management

### Environment Variables

All secrets are stored in environment variables:

```bash
# Required for production (app won't start without these)
SECRET_KEY=<64-char hex string>
ADMIN_PASSWORD=<hashed password from scripts/hash_password.py>
CELERY_TASK_SECRET=<32+ char random string>

# Optional with defaults
CELERY_BROKER_URL=redis://localhost:6379/0
SMTP_PASSWORD=your-smtp-password
```

### Secret Key Requirements

- Must be a 64-character hex string (32 bytes of entropy)
- Use `python -c "import secrets; print(secrets.token_hex(32))"` to generate
- Must be unique per environment
- Production validation rejects keys that are not 64-char hex

### Hashed Passwords

Admin passwords must be hashed using werkzeug's password hasher:

```bash
python scripts/hash_password.py
# Enter password when prompted (interactive mode recommended)
# Output: scrypt:32768:8:1$salt$hash...
```

Add the hash to `.env`:
```
ADMIN_PASSWORD=scrypt:32768:8:1$salt$hash...
```

### Docker Secrets

For Docker deployments, use secrets files:

```yaml
# docker-compose.prod.yml
services:
  web:
    secrets:
      - secret_key
      - admin_password

secrets:
  secret_key:
    file: ./secrets/secret_key
  admin_password:
    file: ./secrets/admin_password
```

---

## Password Security

### Hashing Algorithm

Uses werkzeug's `check_password_hash()` which supports:
- Scrypt (default, OWASP 2024-2026 compliant)
- PBKDF2 with SHA256
- Argon2

### Password Requirements

- Minimum 12 characters
- No maximum (uses secure comparison)
- Case sensitive

### Login Lockout

After 5 failed login attempts within 15 minutes, the IP is locked out for 15 minutes.

Lockout tracking:
- Primary: Redis-based (distributed)
- Fallback: In-memory (per-process)

```python
# Check lockout status
from routes.admin.auth import _is_locked_out
is_locked = _is_locked_out(ip_address)
```

### Production Fail-Closed Validation

In production mode (`FLASK_CONFIG=production`), the app validates all secrets at startup and **refuses to start** if any check fails:

- `SECRET_KEY` must be a 64-character hex string
- `ADMIN_PASSWORD` must be a hashed password (scrypt/pbkdf2/argon2)
- `CELERY_TASK_SECRET` must be at least 32 characters
- At least one LLM provider must be enabled with valid credentials
- `default_provider` must exist and be enabled

This prevents common deployment mistakes like running with default dev secrets.

---

## API Token Security

### Token Format

API tokens use the format `ak_<prefix>.<secret>`:
- `prefix`: First 12 characters of the random secret, used for database lookup (non-secret)
- `secret`: Random URL-safe string (32 bytes) used for authentication

### Token Lifecycle

1. **Creation:** Token is generated, only the hashed secret (via werkzeug password hashing) is stored in `ApiToken.token_hash`. The full token is returned once in the creation response and never stored.
2. **Verification:** Bearer token is parsed, looked up by prefix, checked for revocation and expiration, then the secret is verified against the stored hash using constant-time comparison.
3. **Revocation:** Tokens can be soft-revoked (sets `revoked_at` timestamp) or hard-deleted. Revoked tokens are rejected during verification.
4. **Expiration:** Optional `expires_at` timestamp enforced during verification. Expired tokens are rejected.

### Storage Guarantees

- **Never stored:** Raw token secret material
- **Stored:** Hashed secret (`token_hash`), lookup prefix (`token_prefix`), metadata
- **Token returned once:** Full token appears only in the creation response

### Key Implementation Details

- `services/api_tokens.py`: Token generation, hashing, verification, parsing helpers
- `verify_api_token()` in `routes/admin/__init__.py`: Full verification flow with prefix lookup, expiry/revocation checks, and constant-time secret comparison. Iterates all candidates matching the prefix, so prefix collisions cannot cause valid-token auth failure.
- Token creation retries on prefix collision to guarantee uniqueness.
- Tokens from before the API token redesign are invalid — regeneration required

---

## Session Security

### Cookie Configuration

| Setting | Development | Production |
|---------|-------------|------------|
| `HttpOnly` | Yes | Yes |
| `Secure` | No | Yes |
| `SameSite` | Lax | Lax |
| `Max-Age` | 2 hours | 2 hours |

### Session Storage

Sessions are stored client-side in signed cookies. The `SECRET_KEY` is used to sign session data.

---

## Input Validation

### Request Size Limits

- Global: 64KB max content length
- Subscribe endpoint: 1KB limit
- Admin login: 1KB limit

### SQL Injection Prevention

Uses SQLAlchemy ORM with parameterized queries:

```python
# Safe - uses parameterized query
Article.query.filter(Article.id.in_(article_ids))

# Avoid string concatenation in queries
```

### XSS Prevention

All user content in templates is auto-escaped by Jinja2.

Newsletter content from LLM is explicitly escaped:

```python
from services.newsletter import escape_newsletter_content
safe_html = escape_newsletter_content(llm_output)
```

### SSRF Prevention

All untrusted URL fetches use the first-party safe fetch client (`services/safe_fetch.py`) which validates URLs, resolves DNS, blocks private/reserved IPs, handles redirects manually, and enforces byte/content-type limits:

```python
from services.safe_fetch import safe_fetch_url, UnsafeFetchError, SafeFetchError

try:
    result = safe_fetch_url(untrusted_url)
    html = result.text
except UnsafeFetchError:
    # Blocked: private IP, bad scheme, etc.
    pass
except SafeFetchError:
    # Fetch failed: timeout, too large, bad status, etc.
    pass
```

For URL validation without fetching (e.g., webhook URLs), use `validate_url_safe()`:

```python
from services.url import validate_url_safe, UnsafeURLError

try:
    safe_url = validate_url_safe(user_provided_url)
except UnsafeURLError:
    pass
```

---

## CSRF Protection

### Enabled in Production

`WTF_CSRF_ENABLED = True` in ProductionConfig.

### Form Handling

All forms use Flask-WTF with CSRF tokens:

```html
<form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
</form>
```

### API CSRF Exemptions

API blueprints (`admin_api_bp` at `/api/v1/*`, `api_tokens_bp` at `/api-tokens/*`) are exempted from Flask-WTF's global CSRF protection. This is intentional — API routes accept Bearer tokens which should not require CSRF.

### Per-Route CSRF Decorators

- **`@validate_csrf_json`**: Validates `X-CSRFToken` header for session-authenticated JSON endpoints. Invalid CSRF returns a controlled JSON 400 response (never propagates exceptions). Used on HTML form/HTMX routes.
- **`@csrf_for_session_auth`**: Like `@validate_csrf_json` but skips CSRF for verified bearer-token requests (uses `g.auth_mode` set by `authenticate_request()`). Returns 401 if auth has not run. Used on all JSON API mutating routes.

### Bearer-Token CSRF Bypass

Bearer-token API requests bypass CSRF entirely via `@csrf_for_session_auth`. Invalid Bearer tokens return 401 immediately and do NOT fall back to session auth.

---

## Rate Limiting

### Admin Login Lockout

Primary defense against brute force:

```python
# After 5 failed attempts in 15 minutes → 15 minute lockout
MAX_ATTEMPTS = 5
LOCKOUT_WINDOW = 900  # 15 minutes
LOCKOUT_DURATION = 900  # 15 minutes
```

### Application Rate Limiting

The application runs behind a reverse proxy/WAF that handles rate limiting efficiently.

---

## Audit Logging

### Login Attempts

All login attempts are logged with IP address:

```python
logger.warning("Failed login attempt", extra={"ip": ip, "user": "admin"})
```

### Admin Actions

Admin API operations are logged:

```python
logger.info("Bulk article operation", extra={
    "action": "delete",
    "article_count": 10,
    "admin": "admin"
})
```

### Pipeline Events

Article processing events are logged with structured data:

```python
logger.info("Article processed", extra={
    "article_id": 123,
    "stage": "write",
    "duration_ms": 1500
})
```

---

## Security Headers

Nginx configuration sets security headers:

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

---

## Incident Response

### Suspected Breach

1. **Isolate**: Stop affected services
   ```bash
   sudo systemctl stop ainews-web ainews-celery-worker
   ```

2. **Assess**: Check logs for unauthorized access
   ```bash
   journalctl -u ainews-web --since "1 hour ago" | grep -i "failed\|error"
   ```

3. **Preserve**: Backup current logs and database
   ```bash
   cp /opt/ainews/instance/prod.db / backups/incident-$(date +%Y%m%d).db
   ```

4. **Recover**: Restore from known-good backup if needed
   ```bash
   # Stop services
   # Restore backup
   # Restart services
   ```

5. **Report**: Document incident and lessons learned

### Suspicious Activity Checklist

- [ ] Unusual login times or locations
- [ ] Unexpected API calls in logs
- [ ] High error rates from specific IPs
- [ ] Unknown sources added to configuration
- [ ] Unexpected changes to subscriber data

### Contact

Report security vulnerabilities privately via [GitHub Private Vulnerability Reporting](https://github.com/dbowm91/ainews/security/advisories/new). Do not disclose vulnerabilities in public issues.

---

## Compliance

### Data Retention

- Articles: Retained indefinitely until manually deleted
- Subscriber emails: Retained until unsubscribe
- Login logs: Rotated with application logs
- Backup data: Retained 30 days (configurable)

### Subscriber Data

- Only email address stored (no PII beyond email)
- Double opt-in verification required
- One-click unsubscribe in every newsletter

### Security Scanning

Run security checks before deployment:

```bash
# Check for exposed secrets (install: https://github.com/gitleaks/gitleaks)
gitleaks detect --source . --no-git

# Dependency audit
pip-audit
```

---

## Best Practices

1. **Never commit secrets** - Use `.env` or Docker secrets
2. **Rotate credentials** - Change `SECRET_KEY` and passwords periodically
3. **Monitor logs** - Set up alerts for failed logins
4. **Keep dependencies updated** - Run `pip list --outdated` regularly
5. **Use SSL** - Never run without HTTPS in production
6. **Firewall** - Block direct access to application ports
7. **Backups** - Verify backup restoration procedures
8. **Least privilege** - Run services with minimal required permissions
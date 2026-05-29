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
# Required for production
SECRET_KEY=<32+ character random string>
ADMIN_PASSWORD=<hashed password from scripts/hash_password.py>

# Optional with defaults
CELERY_BROKER_URL=redis://localhost:6379/0
SMTP_PASSWORD=your-smtp-password
```

### Secret Key Requirements

- Minimum 32 characters
- Use `python -c "import secrets; print(secrets.token_hex(32))"` to generate
- Must be unique per environment

### Hashed Passwords

Admin passwords must be hashed using werkzeug's password hasher:

```bash
python scripts/hash_password.py
# Enter password when prompted
# Output: pbkdf2:sha256:600000$<hash>
```

Add the hash to `.env`:
```
ADMIN_PASSWORD=scrypt:sha256:<hash>
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

All outbound URLs are validated against private IP ranges:

```python
from services.url import validate_url_safe

try:
    safe_url = validate_url_safe(user_provided_url)
except UnsafeURLError:
    # Handle blocked URL
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

### API CSRF

Admin API routes use `@require_auth` decorator. Session-based auth is protected by CSRF.

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
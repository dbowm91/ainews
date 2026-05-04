# Key Rotation Procedure

## Overview

This document describes the procedure for rotating secrets and cryptographic keys in the ainews system. Regular key rotation is essential for security.

## Keys Requiring Rotation

| Key | Environment Variable | Rotation Frequency | Impact |
|-----|---------------------|--------------------| ------|
| Flask Secret Key | `SECRET_KEY` | 90 days | Session invalidation |
| API Token Secret | `API_TOKEN_SECRET` | 180 days | API token reissuance |
| Webhook Secret | `WEBHOOK_SECRET_KEY` | 90 days | Webhook reconfiguration |
| Celery Task Secret | `CELERY_TASK_SECRET` | 30 days | Task re-signing |
| Database Encryption | `FERNET_KEY` | 365 days | Data re-encryption |

## Flask Secret Key (`SECRET_KEY`)

### When to Rotate

- Scheduled: Every 90 days
- After suspected compromise
- After staff changes with access

### Procedure

1. Generate a new key:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Update `.env`:
   ```
   SECRET_KEY=<new-key>
   SECRET_KEY_PREVIOUS=<old-key>
   ```

3. Restart the application to apply the new key.

### Impact

All existing user sessions will be invalidated. Users will need to log in again.

## Celery Task Secret (`CELERY_TASK_SECRET`)

### When to Rotate

- Scheduled: Every 30 days
- After suspected compromise
- After worker replacement

### Procedure

1. Generate a new secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Update `.env` on all application servers and workers:
   ```
   CELERY_TASK_SECRET=<new-secret>
   ```

3. Restart all Celery workers:
   ```bash
   celery -A app.control shutdown  # Graceful shutdown
   celery -A app worker --detach    # Restart
   ```

### Impact

Tasks signed with the old secret will be rejected. Use overlap period below.

### Overlap Period

For zero-downtime rotation, set `CELERY_TASK_SECRET_PREVIOUS` alongside the new key. Workers will accept both during the transition.

## Webhook Secret (`WEBHOOK_SECRET_KEY`)

### When to Rotate

- Scheduled: Every 90 days
- After suspected compromise
- When a receiver needs to be reconfigured

### Procedure

1. Generate a new key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Update `.env`:
   ```
   WEBHOOK_SECRET_KEY=<new-key>
   ```

3. If the webhook receiver supports signature verification, update its secret first to avoid delivery failures.

4. Restart the application.

### Impact

Webhook deliveries may fail if the receiver still uses the old secret. Coordinate with webhook consumers.

## API Token Secret (`API_TOKEN_SECRET`)

### When to Rotate

- Scheduled: Every 180 days
- After suspected compromise

### Procedure

1. Generate a new secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Update `.env`:
   ```
   API_TOKEN_SECRET=<new-secret>
   ```

3. Reissue all API tokens via `/admin/api-tokens`.

### Impact

All existing API tokens will be invalidated. Clients must request new tokens.

## Fernet Encryption Key (`FERNET_KEY`)

### When to Rotate

- Scheduled: Yearly
- After suspected compromise

### Procedure

```bash
# Generate new key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Update environment
FERNET_KEY=<new-key>
FERNET_KEY_PREVIOUS=<old-key>
```

### Impact

High - all encrypted webhook secrets must be re-encrypted with the new key.

## Emergency Rotation

If a key is compromised:

1. Immediately rotate the affected key
2. Audit logs for unauthorized usage: `grep "auth" logs/*.json | jq`
3. Revoke all sessions and tokens if Flask session secret was compromised
4. Notify affected users if API tokens or webhooks were compromised
5. Document the incident in security log

## Verification

After rotation:

1. Verify application starts without errors: `granian --check`
2. Verify Celery workers connect: `celery -A app inspect active`
3. Verify webhooks still deliver: Check `/admin/webhooks` after test delivery
4. Verify API authentication works: `curl -H "Authorization: Bearer <token>" /api/v1/sources`
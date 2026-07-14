# Troubleshooting Guide

## Common Issues and Solutions

### Application Won't Start

#### Port Already in Use

```bash
# Check what's using port 5000
ss -tlnp | grep 5000

# Kill the process or change port
export PORT=5001
```

#### Database Lock Error

```bash
# Check for stale locks
ps aux | grep -E '(granian|celery)'

# Force unlock if needed
rm -f /opt/ainews/instance/prod.db-journal
```

#### Missing Environment Variables

```bash
# Verify .env file exists and is loaded
cat .env
source .env && echo "SECRET_KEY=$SECRET_KEY"
```

### Database Issues

#### "Database is locked" Errors

This happens when multiple processes access SQLite simultaneously.

```bash
# Solution 1: Restart Celery workers
sudo systemctl restart ainews-celery-worker

# Solution 2: Check WAL mode
sqlite3 /opt/ainews/instance/prod.db "PRAGMA journal_mode;"

# Should return: wal

# Solution 3: Increase timeout
# Add to .env: SQLITE_TIMEOUT=30
```

#### Migration Failures

```bash
# Check current migration state
flask db current

# Reset migrations (development only!)
flask db downgrade base
flask db upgrade

# Manually run SQL
sqlite3 /opt/ainews/instance/prod.db < migration.sql
```

### Celery Issues

#### Tasks Not Processing

```bash
# Check worker is running
sudo systemctl status ainews-celery-worker

# View worker logs
journalctl -u ainews-celery-worker -f

# Ping workers
celery -A celery_app inspect ping

# Check queue
celery -A celery_app inspect active_queues
```

#### Lost Tasks After Restart

Tasks in progress are lost (Celery task acknowledgment is not durable by default).

```bash
# Enable task persistence (add to config)
CELERY_TASK_ACKS_LATE=True
CELERY_TASK_REJECT_ON_WORKER_LOST=True

# Restart workers
sudo systemctl restart ainews-celery-worker
```

#### Prefetch Too Many Tasks

```bash
# Reduce prefetch multiplier
celery -A celery_app worker --prefetch-multiplier=1

# Or in config
CELERY_WORKER_PREFETCH_MULTIPLIER=1
```

### Redis Issues

#### Redis Connection Refused

```bash
# Check Redis is running
sudo systemctl status redis

# Test connection
redis-cli ping

# Should return: PONG

# Restart Redis if needed
sudo systemctl restart redis
```

#### Redis Memory Issues

```bash
# Check memory usage
redis-cli info memory

# View keys count
redis-cli dbsize

# Clear unused keys if needed
redis-cli FLUSHDB  # Warning: clears all keys
```

### Pipeline Issues

#### Articles Stuck in "pending"

```bash
# Check dead letter stats
curl -u admin:password http://localhost:5000/admin/api/pipeline/dead-letter/stats

# Manually trigger retry
celery -A celery_app inspect revoke <task-id>

# Reprocess stuck articles
# Via admin UI: /admin/articles → select stuck → reprocess
```

#### Newsletter Not Sending

```bash
# Check if newsletters were generated
# Look at admin dashboard for newsletter status

# Verify SMTP settings
curl -X POST http://localhost:5000/admin/api/newsletter/preview

# Check Celery beat schedule
celery -A celery_app beat --loglevel=info
# Should show: 'run-all-sources' every 30 minutes
#              'generate-newsletters' daily at 8:00 AM
```

### Email Issues

#### Emails Not Delivered

```bash
# Check SMTP configuration
# In .env:
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-username
SMTP_PASSWORD=your-password

# Test SMTP
python -c "
import smtplib
s = smtplib.SMTP('smtp.example.com', 587)
s.starttls()
s.login('user', 'pass')
s.quit()
"

# Check spam folder
# Verify sender email matches SMTP credentials
```

### Performance Issues

#### High CPU Usage

```bash
# Check which process
top -c

# Reduce worker count
# Edit systemd service: ExecStart=... --workers 3

# Reduce Celery concurrency
# celery -A celery_app worker --concurrency=2
```

#### Slow Page Loads

```bash
# Check database size
ls -lh /opt/ainews/instance/prod.db

# Vacuum database
sqlite3 /opt/ainews/instance/prod.db "VACUUM;"

# Check for missing indexes
sqlite3 /opt/ainews/instance/prod.db ".indices"
```

### Docker Ollama Issues

#### LLM calls fail with connection error in Docker

The most common Docker issue: `localhost` inside a container refers to the container itself, not the host machine.

```bash
# Check what the container can reach:
docker compose exec web curl -sf http://localhost:11434/api/tags  # Will fail if Ollama is on host
docker compose exec web curl -sf http://ollama:11434/api/tags     # Works with Compose Ollama service
docker compose exec web curl -sf http://host.docker.internal:11434/api/tags  # Works with host Ollama
```

**Fix:** Update `providers.yaml` host to match your deployment:
- Compose Ollama service: `http://ollama:11434`
- Host Ollama: `http://host.docker.internal:11434`

Then restart: `docker compose restart web celery-worker`

#### Ollama model not found

```bash
# List available models in the Ollama container:
docker compose exec ollama ollama list

# Pull the model:
docker compose exec ollama ollama pull qwen3:8b
```

#### Ollama container healthcheck failing

```bash
docker compose logs ollama
# Common causes:
# - Insufficient memory (Ollama needs 4GB+ for qwen3:8b)
# - GPU not available (CPU-only is fine, just slower)
```

#### Ollama healthcheck uses `ollama list` instead of `curl`

The `ollama/ollama` Docker image ships the `ollama` binary but does **not** include `curl` or `wget`. The Compose healthcheck therefore uses `["CMD", "ollama", "list"]` rather than a curl-based check. If you replace or customize the healthcheck, verify the tool is present:

```bash
docker run --rm ollama/ollama:latest sh -lc 'command -v curl || command -v wget || command -v ollama'
```

### Safe Fetch Errors

#### `UnsafeFetchError` — URL targets private/reserved IP

The safe fetch client blocks requests to private, loopback, link-local, and reserved IP ranges. This prevents SSRF attacks. DNS rebinding protection ensures the TCP connection uses a pre-validated IP via custom urllib3 connection classes (`PinnedHTTPConnection`, `PinnedHTTPSConnection`) rather than re-resolving DNS, closing TOCTOU race conditions. No process-global socket monkeypatching is used — each connection pins the validated IP at the connection-class level.

```bash
# Check the URL for private IPs or hostnames that resolve locally
# Common cause: URL points to an internal service or localhost
# Fix: Verify the URL is correct and points to a public host

# If testing locally, use the test helper to bypass SSRF validation
# (see tests/test_safe_fetch.py for examples)
```

#### `SafeFetchTimeoutError` — target too slow

The request exceeded the configured timeout. Total timeout is enforced as a hard ceiling across all redirect hops and streaming chunk reads — the request is aborted if the cumulative time exceeds `SAFE_FETCH_TOTAL_TIMEOUT`.

```bash
# Increase timeouts in .env if the target is known to be slow:
SAFE_FETCH_CONNECT_TIMEOUT=10
SAFE_FETCH_READ_TIMEOUT=30
SAFE_FETCH_TOTAL_TIMEOUT=60

# Or check network connectivity to the target
curl -sf --max-time 10 <url>
```

#### `SafeFetchTooLargeError` — response exceeds `SAFE_FETCH_MAX_BYTES`

The response body exceeds the maximum allowed size. This prevents memory exhaustion on unexpectedly large responses.

```bash
# Increase the byte limit if needed:
SAFE_FETCH_MAX_BYTES=5000000  # 5MB

# Or verify the URL returns the expected content type and size
curl -sI <url> | grep -i content-length
```

#### `SafeFetchContentTypeError` — response not in allowlist

The response `Content-Type` is not in the allowlist (HTML/XML only). Binary or JSON responses are rejected.

```bash
# Check what content type the URL returns:
curl -sI <url> | grep -i content-type

# Ensure the URL returns HTML or XML content
# If the URL redirects to a login page or API endpoint, the content type may change
```

#### `SafeFetchError` with redirect chain — redirect loop or too many hops

The request hit a redirect loop or exceeded `SAFE_FETCH_MAX_REDIRECTS`.

```bash
# Trace the redirect chain manually:
curl -sLv <url> 2>&1 | grep -i "location:"

# If it's a legitimate redirect chain, increase the limit:
SAFE_FETCH_MAX_REDIRECTS=10

# If it's a loop, fix the URL or server configuration
```

#### HTTPS pinning — SNI and certificate verification

For HTTPS URLs, the safe fetch client connects to the pre-validated IP but preserves the original hostname for TLS SNI and certificate verification. If you see TLS errors on HTTPS URLs, the issue is typically certificate-related, not pinning-related.

```bash
# Check if the target has a valid certificate:
openssl s_client -connect <host>:443 -servername <host> </dev/null 2>/dev/null | openssl x509 -noout -dates

# If using self-signed certs in development, ensure the target is accessible via HTTP
# or configure the system trust store appropriately
```

#### Proxy bypass — environment proxies are ignored

The safe fetch client sets `trust_env=False` and passes `proxies={}` on every request. Environment variables like `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` are ignored for untrusted URL fetches. This prevents proxies from bypassing SSRF controls. If you need proxy support for safe fetch, a separate `SAFE_FETCH_PROXY_URL` configuration with its own validation would be required.

```bash
# If your fetch is failing and you expect it to go through a proxy,
# note that safe fetch bypasses proxies by design.
# Check direct connectivity instead:
curl -sf --max-time 10 <url>
```

### Configuration Errors

The configuration system emits structured diagnostics with severity, code, and remediation. Run `ainews config check` to see all errors and warnings, or `ainews config check --production` for production-specific checks.

#### `ROLE_PROVIDER_MISSING` — pipeline role references missing provider

A pipeline role (selector, researcher, writer, editor) references a provider ID that doesn't exist in `providers.yaml`.

```bash
# Check which provider is missing
ainews config check

# Fix: add the provider to providers.yaml, or reassign the role
ainews config set pipeline.writer.provider ollama-local
```

#### `ROLE_PROVIDER_DISABLED` — pipeline role references disabled provider

A pipeline role references a provider that exists but has `enabled: false`.

```bash
# Enable the provider in providers.yaml
ainews config set providers.providers.<id>.enabled true

# Or reassign the role to an enabled provider
ainews config set pipeline.writer.provider ollama-local
```

#### `PROVIDER_MISSING` — default provider does not exist

The `default_provider` in `providers.yaml` references a non-existent provider ID.

```bash
# Add the provider, or change the default
ainews config set providers.default_provider ollama-local
```

#### `PROVIDER_DISABLED` — default provider is disabled

The `default_provider` points to a provider with `enabled: false`.

```bash
ainews config set providers.providers.<id>.enabled true
```

#### `SOURCE_TOPIC_MISSING` — source references non-existent topic

A source's `topics.include` list references a topic ID not defined in `topics.yaml`.

```bash
# Add the missing topic to topics.yaml, or remove the reference
# Check which source and topic
ainews config check
```

#### `SCHEDULE_OUT_OF_RANGE` — numeric value outside valid bounds

A schedule or pipeline numeric value is outside its allowed range.

```bash
# Valid ranges:
# crawl_interval_minutes: 1-1440
# generate_newsletters_hour: 0-23
# max_tokens: 1-1000000
# concurrency: 1-64
# timeout_seconds: 1-86400

ainews config set schedule.crawl_interval_minutes 30
```

#### `TIMEZONE_INVALID` — newsletter timezone not recognized

The `newsletter.timezone` value is not in the allowed list of IANA timezones.

```bash
# Use a valid timezone
ainews config set newsletter.timezone "America/New_York"
```

#### `SECRET_KEY_SHORT` / `CELERY_SECRET_SHORT` — secrets too short for production

Production requires secrets of sufficient length. `SECRET_KEY` must be >= 16 characters. `CELERY_TASK_SECRET` must be >= 16 characters.

```bash
# Generate a strong secret
python -c "import secrets; print(secrets.token_hex(32))"

# Set it in .env
# SECRET_KEY=<generated value>
# CELERY_TASK_SECRET=<generated value>
```

#### `ADMIN_PASSWORD_PLAINTEXT` — password not hashed in production

The `ADMIN_PASSWORD` in `.env` is plaintext. Production requires a hashed password.

```bash
# Hash the password
python scripts/hash_password.py

# Or inline:
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"

# Paste the scrypt/pbkdf2 hash into ADMIN_PASSWORD in .env
```

#### `SAFE_FETCH_OUT_OF_RANGE` — safe fetch env var invalid

A `SAFE_FETCH_*` environment variable is not an integer or is outside its valid range.

```bash
# Valid ranges:
# SAFE_FETCH_MAX_REDIRECTS: 0-20
# SAFE_FETCH_MAX_BYTES: 1024-100000000
# SAFE_FETCH_CONNECT_TIMEOUT: 1-60
# SAFE_FETCH_READ_TIMEOUT: 1-300
# SAFE_FETCH_TOTAL_TIMEOUT: 1-600

# Set valid values in .env
```

#### `YAML_PARSE_ERROR` — YAML syntax error in config file

A configuration YAML file has invalid syntax.

```bash
# Check which file
ainews config check

# Fix the YAML syntax (indentation, colons, etc.)
# Common issues:
# - Missing colons after keys
# - Incorrect indentation (use spaces, not tabs)
# - Unclosed quotes
```

#### `DOTENV_MALFORMED_LINE` / `DOTENV_EMPTY_KEY` — `.env` file issues

The `.env` file has lines that don't follow `KEY=value` format.

```bash
# Check for malformed lines
ainews config check

# Fix: ensure each line is KEY=value
# Remove empty lines or lines without '='
```

#### `ENV_VAR_UNRESOLVED` — environment variable not found

A `${VAR}` reference in a YAML file couldn't be resolved from the environment or `.env`.

```bash
# Set the missing variable
echo "MISSING_VAR=value" >> .env

# Or remove the ${VAR} reference and use a literal value
```

#### `REDIS_URL_MISMATCH` — broker and backend Redis URLs mismatched

The Celery broker and result backend use different Redis configurations when both are Redis, or one is Redis and the other isn't.

```bash
# Ensure consistent Redis URLs in .env
# CELERY_BROKER_URL=redis://localhost:6379/0
# CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

#### General: checking and fixing configuration

```bash
# Full validation
ainews config check --production

# Show effective configuration with provenance
ainews config show

# Show resolved paths
ainews config path

# Show specific value
ainews config get pipeline.writer.model

# Set a value
ainews config set pipeline.writer.model qwen3:8b

# Compare with defaults
ainews config diff
```

---

## Diagnostic Commands

### System Health

```bash
# Check all services
systemctl status ainews-web ainews-celery-worker ainews-celery-beat redis nginx

# Check open ports
ss -tlnp | grep -E '(5000|6379|80|443)'

# Check memory
free -h
```

### Application Health

```bash
# Public health endpoint
curl http://localhost:5000/health

# Admin health endpoint
curl -u admin:password http://localhost:5000/admin/api/health

# Worker health
curl -u admin:password http://localhost:5000/admin/api/workers/health
```

### Database Diagnostics

```bash
# Database file size
ls -lh /opt/ainews/instance/prod.db*

# Check WAL mode
sqlite3 /opt/ainews/instance/prod.db "PRAGMA journal_mode;"

# Check for corruption
sqlite3 /opt/ainews/instance/prod.db "PRAGMA integrity_check;"

# Table statistics
sqlite3 /opt/ainews/instance/prod.db "SELECT COUNT(*) FROM article;"

# Migration status
flask db current
```

### Redis Diagnostics

```bash
# Connection test
redis-cli ping

# Key count
redis-cli dbsize

# Memory usage
redis-cli info memory | grep used

# List all keys
redis-cli keys '*'

# Monitor operations (debug)
redis-cli monitor
```

### Celery Diagnostics

```bash
# Worker status
celery -A celery_app inspect stats

# Active tasks
celery -A celery_app inspect active

# Scheduled tasks
celery -A celery_app inspect scheduled

# Reserved tasks
celery -A celery_app inspect reserved

# Registered tasks
celery -A celery_app inspect registered
```

---

## Log Locations and Format

### Log Locations

| Environment | Location |
|------------|----------|
| systemd | `journalctl -u ainews-*` |
| Docker | `docker compose logs -f [service]` |
| Development | stdout (console) |

### Log Format

#### JSON Format (Production)

```json
{
  "timestamp": "2024-01-01T12:00:00.000Z",
  "level": "INFO",
  "logger": "routes.admin",
  "message": "Article processed",
  "request_id": "abc123",
  "article_id": 123,
  "stage": "write"
}
```

#### Text Format (Development)

```
2024-01-01T12:00:00 INFO routes.admin: Article processed [request_id=abc123]
```

### Key Log Patterns

| Pattern | Meaning |
|---------|---------|
| `Failed login attempt` | Possible brute force attack |
| `Health check: database ping failed` | Database connectivity issue |
| `Health check: Redis ping failed` | Redis connectivity issue |
| `Article stuck for >60min` | Pipeline stalled |
| `Pool size exceeded` | Connection pool exhausted |

### Request ID Tracing

Every request has a `request_id` for tracing:

```
# Get request ID from response header
curl -i http://localhost:5000/health
# X-Request-ID: abc123def456

# Search logs by request ID
journalctl -u ainews-web | grep abc123def456
```

### Slow Query Logging

Slow queries (>500ms) are logged at `DB_QUERY_LOG_LEVEL`:

```bash
export DB_QUERY_LOG_LEVEL=INFO
# Logs include stack trace for slow queries
```

---

## Recovery Procedures

### Complete Service Failure

```bash
# 1. Check system resources
df -h
free -h

# 2. Restart all services
sudo systemctl restart redis
sudo systemctl restart ainews-web ainews-celery-worker ainews-celery-beat

# 3. Verify health
curl http://localhost:5000/health
```

### Database Recovery

```bash
# 1. Stop services
sudo systemctl stop ainews-web ainews-celery-worker ainews-celery-beat

# 2. Backup corrupted database
cp /opt/ainews/instance/prod.db /opt/ainews/instance/prod.db.corrupt

# 3. Restore from backup
gunzip -c /opt/ainews/backups/ainews-20240101-020000.db.gz > /opt/ainews/instance/prod.db

# 4. Verify
sqlite3 /opt/ainews/instance/prod.db "PRAGMA integrity_check;"

# 5. Restart services
sudo systemctl start ainews-web ainews-celery-worker ainews-celery-beat
```

### Redis Recovery

```bash
# 1. Stop Celery workers
sudo systemctl stop ainews-celery-worker

# 2. Clear Redis
redis-cli FLUSHDB

# 3. Restart Redis
sudo systemctl restart redis

# 4. Restart Celery workers
sudo systemctl start ainews-celery-worker
```

### Manual Task Retry

```bash
# Get stuck task IDs from admin API
curl -u admin:password http://localhost:5000/admin/api/pipeline/dead-letter/stats

# Revoke stuck tasks
celery -A celery_app inspect revoke <task-id>

# Manually dispatch reprocess via admin API
curl -X POST -u admin:password http://localhost:5000/admin/api/articles/bulk \
  -H "Content-Type: application/json" \
  -d '{"article_ids": [1,2,3], "action": "reprocess"}'
```
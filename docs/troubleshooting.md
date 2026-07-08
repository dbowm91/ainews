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
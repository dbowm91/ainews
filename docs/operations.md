# Operations Guide

## Celery Beat Tasks

Fourteen scheduled tasks run via Celery Beat:

| Task | Schedule | Purpose |
|------|----------|--------|
| run-all-sources | Every 30 min | Crawl all active RSS/API sources |
| retry-stuck | Every 60 min | Retry articles stuck in pipeline |
| generate-newsletters | Daily 8:00 AM | Generate newsletter emails |
| cleanup-old-logs | Daily 3:00 AM | Purge old pipeline logs |
| cleanup-expired-verifications | Every 15 min | Clean expired subscriber tokens |
| cleanup-stale-limiter-slots | Every 5 min | Release stale limiter slots |
| consolidate-trend-memory | Daily 3:30 AM | Promote low-importance memory |
| purge-trend-memory | Daily 3:45 AM | Delete expired memory entries |
| cleanup-old-versions | Daily 3:45 AM | Purge old article versions |
| publish-scheduled-articles | Every 5 min | Publish time-scheduled articles |
| backfill-embeddings | Daily 2:00 AM | Backfill article embeddings |
| retry-failed-newsletter-deliveries | Every 2 hours | Retry failed newsletter sends |
| recalculate-impact-scores | Daily 4:00 AM | Recalculate article impact scores |
| cleanup-inactive-subscribers | Daily 1:00 AM | Remove inactive subscribers |

All schedules are configurable via `pipeline.yaml` `schedule:` section.

## Dead Letter Queue

Articles stuck in the pipeline (no progress within threshold) are tracked in the dead letter queue.

### Identifying Stuck Articles

```bash
curl http://localhost:5000/admin/api/pipeline/dead-letter/stats
```

### Bulk Reprocess

```bash
curl -X POST http://localhost:5000/admin/api/articles/bulk \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ..." \
  -d '{"article_ids": [1,2,3], "action": "reprocess"}'
```

### Admin UI

View dead letter articles at `/admin/dead-letters` with bulk reprocess/delete actions.

## Config Cache Reload

After changes to `pipeline.yaml` or `providers.yaml`:

```bash
curl -X POST http://localhost:5000/admin/api/config/reload \
  -H "X-CSRFToken: ..."
```

This clears:
- Config singleton
- Provider instances
- LLM provider cache
- Celery beat schedule (reloads from pipeline.yaml)

### Celery Beat Schedule Reload

The beat schedule is dynamically loaded from `pipeline.yaml` `schedule:` section via `Config.get_beat_schedule()`. Config reload endpoint calls `Config.reload_beat_schedule(celery_app)` to update without restart.

## Task HMAC Signing

Orchestrator tasks (run_all_sources, generate_daily_newsletters, select_article) require HMAC signing for external invocation.

### Signing

```python
from services.task_security import sign_task

signed = sign_task("select_article", (article_id,), {"run_id": run_id})
# Task can now be called externally
```

### Verification

Tasks verify signature via `verify_task()` which checks:
- HMAC matches
- Timestamp within 5 minutes
- Replay prevention via nonce

Requires `CELERY_TASK_SECRET` environment variable (min 32 characters).

## Distributed Lock Pattern

Celery tasks use Redis distributed locks for coordination:

```python
with redis_utils.acquire_lock("task_name", ttl=300, blocking=True):
    # Critical section
    pass
```

### Lock Features

- Atomic check-and-delete via Lua script
- Fail-closed when Redis unavailable
- TTL prevents deadlocks
- Per-task-ID lock value allows retry from same task

### Lock Release

Always in `finally` block:

```python
try:
    # work
finally:
    redis_utils.release_lock("task_name", lock_value)
```

## Health Checks

### Application

```bash
curl http://localhost:5000/health
curl http://localhost:5000/health?detailed=true
```

### Workers

```bash
curl http://localhost:5000/admin/api/workers/health
```

### Pipeline Stats

```bash
curl http://localhost:5000/admin/api/pipeline/stats?minutes=15
curl http://localhost:5000/admin/api/pipeline/dead-letter/stats
curl http://localhost:5000/admin/api/pipeline/sla
```

## Database Operations

### Backup

```bash
python scripts/backup.sh
```

### Verify Backup

```bash
python scripts/verify_backup.sh
```

### Query Analysis

```bash
./scripts/query_analysis.sh
./scripts/query_analysis.sh custom
./scripts/query_analysis.sh article 123
```

## Common Error Signatures

### Redis Connection Errors

**Signature:** `redis.exceptions.ConnectionError: Error -2 connecting to localhost:6379`

**Recovery:**
1. Check Redis is running: `systemctl status redis`
2. Check Redis logs: `journalctl -u redis`
3. Verify Redis network connectivity: `redis-cli ping`

**Signature:** `ResponseError: BUSY Redis is busy running a Lua script`

**Recovery:** Wait for the script to complete or kill long-running scripts with `redis-cli debug sleep 0`

### Pipeline Stage Failures

**Signature:** `InvalidStateTransitionError: Invalid pipeline transition for article N: selecting -> failed`

**Recovery:** Check the article's current status in admin UI. If stuck, reprocess via bulk action or manually reset status.

**Signature:** `CircuitOpenError: All providers failed for stage: research`

**Recovery:**
1. Check provider health: `GET /admin/api/health`
2. Verify providers.yaml configuration
3. Check circuit breaker status in Redis: `redis-cli keys "*circuit*"`

### Database Lock Errors

**Signature:** `OperationalError: database is locked`

**Recovery:**
1. Increase SQLite timeout (already configured to 15s)
2. Check for long-running transactions
3. Restart the service to release locks
4. For Celery workers, ensure only one worker per queue

### Authentication Failures

**Signature:** `AuthError: Non-retryable authentication error`

**Recovery:** Verify LLM provider API keys are valid and not expired. Check provider status in admin dashboard.

### Celery Task Failures

**Signature:** `SoftTimeLimitExceeded: Soft time limit exceeded`

**Recovery:** Tasks have 300s soft limit. If pipeline stages regularly timeout, increase `timeout_seconds` in pipeline.yaml for that stage.

## Recovery Procedures

### Recovering from Stuck Locks

```bash
# List active locks
redis-cli keys "ainews:*lock*"

# Clear a specific lock (use with caution)
redis-cli DEL "ainews:lock:stage:article_id"
```

### Resetting Failed Pipeline Stages

```bash
# Via API
curl -X POST http://localhost:5000/admin/api/articles/bulk \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ..." \
  -d '{"article_ids": [1,2,3], "action": "set_status", "status": "pending"}'
```

### Circuit Breaker Reset

```bash
# View circuit breaker state
redis-cli keys "*breaker*"

# Manually reset (clears all failure counts)
redis-cli flushdb  # Use only in emergencies
```
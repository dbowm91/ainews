# Operations Guide

## Celery Beat Tasks

Nine scheduled tasks run via Celery Beat:

| Task | Schedule | Purpose |
|------|----------|--------|
| run-all-sources | Every 30 min | Crawl all active RSS/API sources |
| retry-stuck-articles | Every 60 min | Retry articles stuck in pipeline |
| generate-newsletters | Daily 8:00 AM | Generate newsletter emails |
| cleanup-old-logs | Daily 3:00 AM | Purge old pipeline logs |
| cleanup-expired-verifications | Every 15 min | Clean expired subscriber tokens |
| cleanup-stale-limiter-slots | Every 5 min | Release stale limiter slots |
| consolidate-trend-memory | Daily 3:30 AM | Promote low-importance memory |
| cleanup-old-article-versions | Daily 3:45 AM | Purge old article versions |
| publish-scheduled-articles | Every 5 min | Publish time-scheduled articles |

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
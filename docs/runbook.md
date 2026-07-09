# Deployment Runbook

## Overview

AINews is a Flask + Celery application with SQLite database and Redis broker.

## Prerequisites

- Python 3.12
- Redis (for Celery broker and caching)
- Docker (optional, for containerized deployment)

## Quick Start

### Local Development

```bash
# Install dependencies
uv sync --all-extras

# Set environment variables
export CELERY_BROKER_URL=redis://localhost:6379/0
export ADMIN_PASSWORD=your_secure_password

# Run Flask app
python run.py

# Run Celery worker (in another terminal)
celery -A celery_app worker -l info

# Run Celery beat (in another terminal)
celery -A celery_app beat -l info
```

### Docker Compose

```bash
docker-compose up -d
```

## Operational Procedures

### Monitoring

- **Health check**: `GET /admin/api/health`
- **Worker health**: `GET /admin/api/workers/health`
- **Pipeline stats**: `GET /admin/api/pipeline/stats`
- **Dead letter stats**: `GET /admin/api/pipeline/dead-letter/stats`
- **Search analytics**: `GET /admin/api/search/analytics`
- **Cost summary**: `GET /admin/api/costs`
- **SLA metrics**: `GET /admin/api/pipeline/sla`

### Webhook Management

- **List webhooks**: `GET /admin/api/webhooks`
- **Create webhook**: `POST /admin/api/webhooks`
- **Test webhook**: `POST /admin/api/webhooks/<id>/test`
- **View events**: `GET /admin/api/webhooks/<id>/events`

### Audit Logs

- **View logs**: `GET /admin/api/audit-logs`

### Task Inspection

- **Task status**: `GET /admin/api/task/<task_id>`

### Logs

```bash
# Celery worker logs
docker-compose logs -f worker

# Celery beat logs
docker-compose logs -f beat

# Flask app logs
docker-compose logs -f web
```

### Rollback

1. Identify the previous working commit:
   ```bash
   git log --oneline -10
   ```

2. Revert to previous version:
   ```bash
   git revert <commit>
   ```

3. Redeploy:
   ```bash
   docker-compose up -d --force-recreate
   ```

### Dead Letter Queue Handling

When articles get stuck in the pipeline:

1. Check dead letter stats:
   ```bash
   curl http://localhost:5000/admin/api/pipeline/dead-letter/stats
   ```

2. View stuck articles:
   ```bash
   curl http://localhost:5000/admin/dead-letters
   ```

3. Bulk reprocess:
   ```bash
   curl -X POST http://localhost:5000/admin/api/articles/bulk \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: $(curl -s http://localhost:5000/admin/dead-letters | grep -oP 'csrf_token.*?value="\K[^"]+')" \
     -d '{"article_ids": [1,2,3], "action": "reprocess"}'
   ```

### Config Reload

After changes to pipeline.yaml or providers.yaml:

```bash
curl -X POST http://localhost:5000/admin/api/config/reload \
  -H "X-CSRFToken: your_csrf_token"
```

## Scheduled Tasks

The following tasks are run automatically via Celery Beat:

| Task | Schedule | Description |
|------|----------|-------------|
| `cleanup_old_pipeline_logs` | Daily | Delete pipeline logs older than 30 days |
| `cleanup_expired_verifications` | Every 15 min | Remove unverified subscribers past expiry |
| `cleanup_stale_limiter_slots` | Every 5 min | Reclaim stale model limiter slots |
| `consolidate_trend_memory` | Nightly (3:30 AM) | Merge low-importance trend entries |
| `recalculate_impact_scores` | Nightly (4:00 AM) | Update article impact from engagement |
| `purge_trend_memory` | Nightly (3:45 AM) | Remove expired trend memory entries |
| `cleanup_old_article_versions` | Daily | Delete article versions older than 90 days |
| `cleanup_inactive_subscribers` | Daily | Deactivate subscribers with excessive bounces or inactivity |

### Subscriber Cleanup

The `cleanup_inactive_subscribers` task automatically deactivates subscribers based on:
- **Bounce threshold**: `SUBSCRIBER_MAX_BOUNCES` (default: 5) - subscribers with bounce count at or above this threshold are deactivated
- **Inactivity period**: `SUBSCRIBER_INACTIVITY_DAYS` (default: 180 days) - subscribers with no activity since before cutoff are deactivated

Configure via environment variables:
```bash
export SUBSCRIBER_MAX_BOUNCES=5
export SUBSCRIBER_INACTIVITY_DAYS=180
```

## Troubleshooting

### Redis Connection Issues

1. Check Redis is running:
   ```bash
   redis-cli ping
   ```

2. Verify connection:
   ```bash
   curl http://localhost:5000/admin/api/health | jq '.redis'
   ```

### Database Issues

1. Check SQLite integrity:
   ```bash
   python scripts/verify_backup.sh
   ```

2. Run migrations:
   ```bash
   flask db upgrade
   ```

### Worker Queue Backlog

1. Check queue length:
   ```bash
   celery -A celery_app inspect active_queues
   ```

2. Purge stale tasks (if needed):
   ```bash
   celery -A celery_app purge
   ```

## Security

- Store secrets in environment variables, not in config files
- Use `ADMIN_PASSWORD` for admin login
- Use `CELERY_TASK_SECRET` for task signing (optional)
- Use `REDIS_PASSWORD` for Redis auth (optional)
- Change default secrets before production deployment

## Backup

```bash
# Database backup
python scripts/backup.sh
```

## Scaling

For high traffic:
1. Add more Celery workers: `celery -A celery_app worker -l info`
2. Use Redis cluster for caching
3. The app currently uses SQLite (WAL mode) only; there is no PostgreSQL driver or connection configuration in this codebase. Do not attempt to set `DATABASE_URL=postgresql://...`.
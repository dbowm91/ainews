# Dead Letter Queue (DLQ) & Recovery

## Overview

The Dead Letter Queue (DLQ) is a failure handling mechanism for pipeline articles that become stuck or exceed retry limits. When an article cannot be processed successfully after multiple attempts, it is "dead-lettered" - finalized as failed with a fallback draft.

## How It Works

### Trigger Conditions

An article is dead-lettered when:
1. **Retry limit exceeded**: `retry_count >= max_retries` (default 5)
2. **Pipeline timeout**: Article exceeds `PIPELINE_TIMEOUT_SECONDS` (default 1 hour)
3. **Stuck in stage**: Article remains in the same status longer than `STUCK_THRESHOLD_MINUTES` (default 30 minutes)

### Dead Letter Process

When an article is dead-lettered:

1. **Version created**: A snapshot of the article is saved to `ArticleVersion` for audit trail
2. **Fallback applied**: `_apply_fallback()` generates a minimal draft with error context
3. **Status updated**: `pipeline_status` set to `FAILED`
4. **Error recorded**: `last_error` field captures the reason for dead-lettering
5. **Retry count reset**: `retry_count` set to 0 to allow manual retry

## Key Functions

### In `tasks/retry.py`

#### `_dead_letter(article)`
Force-finalizes a stuck article as failed:
- Creates article version with `change_reason="dead_letter"`
- Applies fallback draft via `_apply_fallback()`
- Sets status to `FAILED`
- Records error message with threshold details

#### `retry_stuck()`
Celery task that runs periodically to find and retry stuck articles:
- Queries articles with `pipeline_status` in active stages
- Checks if article has been stuck beyond threshold
- Attempts retry first (up to max retries)
- Dead-letters if retry limit exceeded

### In `tasks/pipeline.py`

#### `_apply_fallback(article)`
Generates a minimal fallback draft:
- Creates a basic article structure with error context
- Sets `final_article` to a placeholder indicating the failure
- Preserves original article metadata

## Configuration

| Setting | Environment Variable | Default | Description |
|---------|---------------------|---------|-------------|
| Max Retries | `PIPELINE_MAX_RETRIES` | 5 | Maximum retry attempts before dead-lettering |
| Stuck Threshold | `STUCK_THRESHOLD_MINUTES` | 30 | Minutes before an article is considered stuck |
| Pipeline Timeout | `PIPELINE_TIMEOUT_SECONDS` | 3600 (1 hour) | Maximum total pipeline time |

## Monitoring

### Admin API Endpoints

- **GET** `/admin/api/pipeline/dead-letter-stats`
  - Returns counts of dead-lettered articles
  - Filters by date range, stage, reason

### Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `pipeline.dead_lettered` | `stage`, `reason` | Count of dead-lettered articles |
| `pipeline.retry_exceeded` | `stage` | Retry limit exceeded |
| `pipeline.timeout_exceeded` | `stage` | Pipeline timeout exceeded |

### Logs

Dead letter events are logged with:
- Level: `ERROR`
- Logger: `tasks.retry`
- Message includes: article ID, stuck stage, retry count, threshold

## Recovery Options

### Manual Retry

Administrators can:
1. View dead-lettered articles in admin dashboard
2. Review error messages and article versions
3. Manually reset status to `pending` for reprocessing
4. Edit fallback drafts if needed

### Automatic Handling

The system automatically:
- Retries transient failures (rate limits, timeouts)
- Escalates to degraded mode when possible
- Dead-letters only after all retry options exhausted

## API Reference

See [API Documentation](api.md#dead-letter-stats) for endpoint details.

## Troubleshooting

### High Dead Letter Rate

Possible causes:
- LLM provider consistently failing
- Invalid article data
- Configuration issues

Check:
1. LLM provider health endpoints
2. Article source quality
3. Pipeline stage logs

### Stuck Articles Not Dead-Lettering

Verify:
1. Celery beat is running (for periodic retry task)
2. `STUCK_THRESHOLD_MINUTES` is appropriate
3. Redis is accessible (for distributed locking)

## Related Documentation

- [Pipeline Documentation](pipeline.md)
- [Runbook](runbook.md#dead-letter-queue-handling)
- [Troubleshooting](troubleshooting.md#dead-letter-issues)
- [Monitoring](monitoring.md#dead-letter-metrics)

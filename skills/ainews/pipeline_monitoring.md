# Pipeline Monitoring Skill

## Overview
Monitor and debug the ainews pipeline stages (select → research → write → edit) using built-in metrics, health endpoints, and logging utilities.

## Key Monitoring Endpoints

### Pipeline Stats
```
GET /admin/api/pipeline/stats
```
Returns per-stage success/failure counts for the last 15 minutes (configurable via `minutes` query param).

### SLA Metrics
```
GET /admin/api/pipeline/sla
```
Returns avg/p50/p95 processing times for:
- Crawl → Select
- Select → Publish  
- Crawl → Publish

Uses SQL aggregation with `ROW_NUMBER() OVER()` for efficiency.

### Dead Letter Stats
```
GET /admin/api/pipeline/dead-letter/stats
```
Returns counts of failed and stuck articles. Alert threshold configurable via `DEAD_LETTER_ALERT_THRESHOLD` env var (default 10).

### Pipeline Backlog
```
GET /admin/api/pipeline/backlog
```
Returns up to 100 active articles (pending, selected, researching, writing, editing, review) ordered by most recently updated. Each entry includes:
- `id`, `title` (truncated to 80 chars), `pipeline_status`
- `updated_at` ISO timestamp
- `is_stuck` boolean (updated_at older than stuck threshold)
- `retry_count`, `last_error` (truncated to 100 chars)

### Dead Letter Root Cause Aggregation
```
GET /admin/api/pipeline/failure-reasons?stage=select&minutes=15
```
Returns breakdown of failure reasons for a specific stage:
```json
{"reasons": {"rate_limit": 5, "timeout": 3, "server_error": 2}}
```

Aggregate across all stages via `get_all_stages_failure_reasons()` from `services/pipeline_monitor.py`.

## Key Metrics (Prometheus format)

### Pipeline Stage Duration
```
pipeline.stage_duration_seconds{stage="select|research|write|edit", success="true|false"}
```

### LLM Call Tracking
```
llm.calls{provider="...", model="...", stage="select|research|write|edit"}
llm.tokens{provider="...", model="...", stage="select|research|write|edit"}
llm.validation_failures{provider="...", model="..."}
llm.validation_retries{provider="...", model="..."}
```

### Pipeline Counters (Redis minute-buckets)
```
ainews:pipeline:counters:{stage}:{minute}:success
ainews:pipeline:counters:{stage}:{minute}:failure:{reason}
```
Reason codes: `rate_limit`, `timeout`, `server_error`, `validation`, `circuit_open`, `unknown`

## Structured Logging

### Pipeline Logger
```python
from services.logging_utils import PipelineLogger, log_pipeline_event, log_article_event

logger = get_pipeline_logger(task_id=run_id)
log_pipeline_event(logger, "info", "Message: %s", arg, article_id=123)
log_article_event(article_id, "info", "Message: %s", arg)
```

### Request ID Tracing
- Flask: `g.request_id` set in `before_request`
- Celery: Pass via task headers `headers={'request_id': get_request_id()}`
- Retrieve: `get_task_request_id()` from `services/logging_utils.py`

## OpenTelemetry Tracing

```python
from services.logging_utils import traced_llm_call, traced_stage

# LLM calls
with traced_llm_call(provider="...", model="...", stage="select"):
    result = provider.chat_structured(...)

# Pipeline stages
with traced_stage("select", "work"):
    # stage work here
```

Uses noop exporter when OTel libraries unavailable.

## Failure Tracking

### Per-Stage Failure Tracking
`services/pipeline_failure.py:_track_stage_failure()` tracks failures per stage per article in Redis:
- Key: `ainews:article:stage_failures:{article_id}:{stage}`
- Early termination after 3 failures at same stage
- Webhook `article.failed` triggered with payload: `{"article_id": ..., "stage": ..., "reason": ...}`

### Failure Reasons
| Reason Code | Description |
|-------------|-------------|
| `rate_limit` | LLM provider rate limit exceeded |
| `timeout` | Soft/hard timeout exceeded |
| `server_error` | 5xx from provider |
| `validation` | Pydantic validation failure |
| `circuit_open` | Circuit breaker open |
| `total_retries_exceeded` | Global retry budget exhausted |
| `per_stage_limit` | Per-stage failure limit (3) exceeded |
| `pipeline_timeout` | Pipeline timeout (default 600s) exceeded |

## Health Check Degradation

`GET /health` returns:
- `"ok"` — All systems operational
- `"degraded"` — Redis/Celery/limiter errors (non-core systems)
- `"unhealthy"` — Database errors (core functionality broken)

`HealthResult.is_healthy` returns True for both "ok" and "degraded".

## Circuit Breaker

Automatically tracks provider health:
- Success → circuit closed
- Failure → circuit opened (after threshold)
- `circuit_breaker.state_change` counter emitted on state transitions
- `circuit_breaker.opened` counter emitted on OPEN transitions

Access via `get_provider_for_role()` which returns providers with fallback chain.

## Cost Tracking

```
GET /admin/api/costs
```
Returns LLM costs aggregated from `llm.tokens` and `llm.calls` metrics using rates from `services/cost_tracker.py:_DEFAULT_RATES`.

Configurable via:
- `COST_RATES` env var (JSON dict)
- `COST_INPUT_RATIO` (default 0.6)
- `COST_OUTPUT_RATIO` (default 0.4)

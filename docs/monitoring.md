# Monitoring and Alerting Guide

## Critical Metrics

### Application Health

| Metric | Warning | Critical | Description |
|--------|---------|----------|-------------|
| `health.status` | `degraded` | `unhealthy` | Overall system health |
| `database.ping` | N/A | `error` | Database connectivity |
| `redis.ping` | N/A | `error` | Redis connectivity |
| `celery.workers` | < 1 | 0 | Active Celery workers |
| `limiter.healthy` | `false` | N/A | Rate limiter status |

### Pipeline Health

| Metric | Warning | Critical | Description |
|--------|---------|----------|-------------|
| `pipeline.stuck_articles` | > 5 | > 10 | Articles stuck in pipeline |
| `pipeline.failed_articles` | > 20 | > 50 | Permanently failed articles |
| `dead_letter.count` | > 10 | > 25 | Dead letter queue size |
| `pipeline.degradation` | rate > 2% over 15m | rate > 5% over 15m | Pipeline degradation rate |
| `pipeline.multi_stage_degradation` | > 3 over 1h | > 10 over 1h | Articles degraded 2+ times |
| `pipeline.timeout_exceeded` | > 0 | > 5 | Articles exceeding pipeline timeout |

### Source Health

| Metric | Warning | Critical | Description |
|--------|---------|----------|-------------|
| `source.consecutive_failures` | > 5 | > 10 | Source auto-disable threshold |
| `source.disabled_count` | > 2 | > 5 | Number of disabled sources |

### Performance

| Metric | Warning | Critical | Description |
|--------|---------|----------|-------------|
| `request.duration_ms.p95` | > 500ms | > 1000ms | 95th percentile response time |
| `request.error_rate` | > 1% | > 5% | HTTP error rate |
| `celery.task.duration.p95` | > 30s | > 60s | Task execution time |
| `celery.queue.size` | > 100 | > 500 | Pending tasks in queue |

---

## Alerting Thresholds

### Prometheus Alert Rules

```yaml
# prometheus/alerts.yml

groups:
  - name: ainews
    rules:
      # Application Health
      - alert: AinewsUnhealthy
        expr: health_status == 2
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AINews is unhealthy"
          description: "Application health check returned unhealthy status"

      - alert: AinewsDegraded
        expr: health_status == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AINews is degraded"
          description: "Application is running with reduced functionality"

      # Database
      - alert: AinewsDatabaseDown
        expr: database_status == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AINews database is down"
          description: "Database connectivity check failed"

      # Redis
      - alert: AinewsRedisDown
        expr: redis_status == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AINews Redis is down"
          description: "Redis connectivity check failed"

      # Celery Workers
      - alert: AinewsNoWorkers
        expr: celery_active_workers == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "No AINews Celery workers"
          description: "All Celery workers are down"

      - alert: AinewsFewWorkers
        expr: celery_active_workers < 2
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low number of AINews workers"
          description: "Only {{ $value }} workers active"

      # Pipeline
      - alert: AinewsStuckArticles
        expr: pipeline_stuck_articles > 10
        for: 30m
        labels:
          severity: critical
        annotations:
          summary: "AINews has stuck articles"
          description: "{{ $value }} articles stuck in pipeline"

      - alert: AinewsDeadLetterHigh
        expr: dead_letter_count > 25
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "AINews dead letter queue high"
          description: "{{ $value }} items in dead letter queue"

      - alert: AinewsHighDegradationRate
        expr: rate(pipeline_degradation_total[15m]) / rate(pipeline_stage_completions_total[15m]) > 0.05
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "AINews high pipeline degradation rate"
          description: "Degradation rate is {{ $value | humanizePercentage }} over 15 minutes"

      - alert: AinewsMultiStageDegradation
        expr: increase(pipeline_multi_stage_degradation_total[1h]) > 10
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "AINews excessive multi-stage degradations"
          description: "{{ $value }} articles degraded 2+ times in the last hour"

      # Performance
      - alert: AinewsSlowResponses
        expr: request_duration_p95 > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AINews slow responses"
          description: "95th percentile response time is {{ $value }}ms"

      - alert: AinewsHighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "AINews high error rate"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # Sources
      - alert: AinewsManyDisabledSources
        expr: sources_disabled_count > 5
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Many AINews sources disabled"
          description: "{{ $value }} sources have been auto-disabled"
```

---

## Health Check Response

### Response Codes

| Status | HTTP Code | Meaning |
|--------|-----------|---------|
| `ok` | 200 | All systems operational |
| `degraded` | 200 | Non-critical systems degraded |
| `unhealthy` | 503 | Critical systems down |

### Detailed Health Response

```json
{
  "status": "degraded",
  "checks": {
    "database": {"status": "ok", "pool": {"size": 5, "checked_out": 2}},
    "redis": "ok",
    "celery": "ok",
    "limiter": "degraded"
  }
}
```

### With Version Info

```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok"},
    "redis": "ok",
    "celery": "ok",
    "limiter": "ok"
  },
  "version": {
    "commit": "abc1234",
    "build_time": "2024-01-01T00:00:00Z"
  }
}
```

---

## Grafana Dashboard Recommendations

### Dashboard Panels

#### 1. Overview Row
- **Stat Panel**: Health status (green/yellow/red)
- **Stat Panel**: Active workers count
- **Stat Panel**: Stuck articles gauge
- **Stat Panel**: Queue size

#### 2. Request Performance Row
- **Time Series**: Request rate by status code
- **Time Series**: Response time percentiles (p50, p95, p99)
- **Gauge**: Current p95 vs threshold

#### 3. Pipeline Row
- **Time Series**: Articles processed per hour
- **Time Series**: Pipeline stage durations
- **Time Series**: Success/failure ratio by stage
- **Table**: Dead letter queue items

#### 4. Sources Row
- **Bar Gauge**: Articles per source
- **Table**: Source health status
- **Time Series**: Source failure rate

#### 5. Infrastructure Row
- **Time Series**: CPU usage by service
- **Time Series**: Memory usage by service
- **Time Series**: Redis memory
- **Gauge**: Database connection pool usage

### Sample Dashboard JSON

```json
{
  "dashboard": {
    "title": "AINews Overview",
    "panels": [
      {
        "title": "Health Status",
        "type": "stat",
        "targets": [
          {
            "expr": "health_status",
            "legendFormat": "{{status}}"
          }
        ],
        "fieldConfig": {
          "mappings": [
            {"type": "value", "value": "0", "text": "Unhealthy", "color": "red"},
            {"type": "value", "value": "1", "text": "Degraded", "color": "yellow"},
            {"type": "value", "value": "2", "text": "OK", "color": "green"}
          ]
        }
      },
      {
        "title": "Response Time (p95)",
        "type": "gauge",
        "targets": [
          {
            "expr": "request_duration_p95",
            "legendFormat": "p95"
          }
        ],
        "fieldConfig": {
          "thresholds": {
            "steps": [
              {"value": 0, "color": "green"},
              {"value": 500, "color": "yellow"},
              {"value": 1000, "color": "red"}
            ]
          }
        }
      }
    ]
  }
}
```

---

## Metrics Endpoint

### Prometheus Format

```
# HELP health_status Application health (0=unhealthy, 1=degraded, 2=ok)
# TYPE health_status gauge
health_status 2

# HELP database_status Database health (1=ok, 0=error)
# TYPE database_status gauge
database_status 1

# HELP redis_status Redis health (1=ok, 0=error)
# TYPE redis_status gauge
redis_status 1

# HELP celery_active_workers Number of active Celery workers
# TYPE celery_active_workers gauge
celery_active_workers 2

# HELP pipeline_stuck_articles Number of stuck articles
# TYPE pipeline_stuck_articles gauge
pipeline_stuck_articles 3

# HELP dead_letter_count Dead letter queue size
# TYPE dead_letter_count gauge
dead_letter_count 0

# HELP sources_disabled_count Number of disabled sources
# TYPE sources_disabled_count gauge
sources_disabled_count 1

# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{status="200",method="GET"} 1000
http_requests_total{status="404",method="GET"} 10
http_requests_total{status="500",method="GET"} 2

# HELP request_duration_seconds HTTP request duration
# TYPE request_duration_seconds histogram
request_duration_seconds_bucket{le="0.1"} 800
request_duration_seconds_bucket{le="0.5"} 950
request_duration_seconds_bucket{le="1.0"} 990
request_duration_seconds_bucket{le="+Inf"} 1000

# HELP pipeline_stage_duration_seconds Pipeline stage duration
# TYPE pipeline_stage_duration_seconds histogram
pipeline_stage_duration_seconds_bucket{stage="select",le="5"} 100
pipeline_stage_duration_seconds_bucket{stage="select",le="30"} 105

# HELP circuit_breaker_state_change Circuit breaker state transitions
# TYPE circuit_breaker_state_change counter
circuit_breaker_state_change{provider="openai",from="closed",to="open"} 2
```

---

## Alerting Best Practices

1. **Start with Warning** - Critical alerts should be for genuine emergencies
2. **Set appropriate durations** - Avoid flapping alerts with `for: 1m` or longer
3. **Include context** - Alert descriptions should explain the impact
4. **Create runbooks** - Link to troubleshooting docs in annotations
5. **Test alerts** - Verify alerting rules work before going to production
6. **Alert fatigue** - Keep total alert count manageable

---

## External Monitoring

### Uptime Monitoring

Set up external checks on:
- `GET /health` (expect 200 with `{"status": "ok"}`)
- `GET /health?detailed=true` (includes dependency checks)

### Synthetic Monitoring

Create test workflows:
1. Subscribe to newsletter
2. Verify email delivery
3. Click unsubscribe link
4. Confirm unsubscribed

### Log Aggregation

Forward logs to your aggregation service:

```bash
# Docker: Add log driver
logging:
  driver: syslog
  options:
    syslog-address: tcp://your-log-server:514

# systemd: Forward to remote syslog
# Edit /etc/systemd/journald.conf
[Journal]
RemoteSyslog=your-log-server:514
```
# Logging Guide

## Log Format

### JSON Format (Production)

All logs are output as JSON for easy parsing by log aggregation tools:

```json
{
  "timestamp": "2024-01-01T12:00:00.000Z",
  "level": "INFO",
  "logger": "routes.admin",
  "message": "Article processed",
  "request_id": "abc123def456",
  "correlation_id": "pipeline-123-abc",
  "article_id": 123,
  "stage": "write",
  "duration_ms": 1500.5
}
```

### Text Format (Development)

For local development, set `LOG_FORMAT=text` in environment:

```
2024-01-01T12:00:00 INFO routes.admin: Article processed [request_id=abc123def456]
```

---

## Log Correlation IDs

### Request ID

Every HTTP request is assigned a unique request ID:

- Generated as 12-character hex string (e.g., `abc123def456`)
- Included in response header: `X-Request-ID`
- Added to all log entries during request

```bash
# Get request ID from response
curl -i http://localhost:5000/health
# X-Request-ID: abc123def456

# Search logs by request ID
journalctl -u ainews-web | grep abc123def456
```

### Correlation ID

Pipeline and lifecycle events use a correlation ID to track operations across services:

- Format: `pipeline-{run_id}-{short_id}`
- Set automatically during pipeline execution
- Enables tracing from crawl through newsletter delivery

---

## Log Fields

### Standard Fields

All log entries include:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO8601 | UTC timestamp |
| `level` | string | DEBUG, INFO, WARNING, ERROR |
| `logger` | string | Logger name (e.g., `routes.admin`) |
| `message` | string | Human-readable message |

### Request Context Fields

When available:

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | HTTP request ID |
| `correlation_id` | string | Pipeline/lifecycle correlation ID |
| `method` | string | HTTP method (GET, POST, etc.) |
| `path` | string | Request path |
| `duration_ms` | float | Request duration in milliseconds |

### Database Query Fields

When SQL query logging is enabled:

| Field | Type | Description |
|-------|------|-------------|
| `duration_ms` | float | Query execution time |
| `statement` | string | SQL statement (truncated to 500 chars) |

### Slow Query Fields (additional)

When query exceeds threshold (>500ms):

| Field | Type | Description |
|-------|------|-------------|
| `stack` | array | Stack trace of query execution |

---

## Slow Query Logging

Enable with `DB_QUERY_LOG_LEVEL`:

```bash
export DB_QUERY_LOG_LEVEL=DEBUG  # Logs all queries
export DB_QUERY_LOG_LEVEL=WARNING  # Only slow queries
export DB_QUERY_LOG_LEVEL=ERROR    # Disable query logging
```

Slow queries (>500ms) include full stack trace for debugging:

```json
{
  "timestamp": "2024-01-01T12:00:00.000Z",
  "level": "WARNING",
  "logger": "db.slow_query",
  "message": "Slow query: 1250.50ms",
  "duration_ms": 1250.50,
  "request_id": "abc123def456",
  "statement": "SELECT * FROM article WHERE...",
  "stack": [
    "  File 'app.py', line 100, in process_request",
    "  File 'services/article.py', line 50, in get_article",
    ...
  ]
}
```

---

## Log Aggregation Tools

### ELK Stack (Elasticsearch, Logstash, Kibana)

Configure Filebeat to collect logs:

```yaml
# filebeat.yml
filebeat.inputs:
  - type: container
    paths:
      - /var/log/containers/ainews-*.log
    processors:
      - add_kubernetes_metadata: ~
      - add_host_metadata: ~

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "ainews-%{+yyyy.MM.dd}"
```

### Grafana Loki

```yaml
# Promtail config
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

client:
  url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: ainews
    static_configs:
      - targets:
          - localhost
        labels:
          job: ainews
          __path__: /var/log/ainews/*.log
```

### Datadog

Add to your Dockerfile:

```dockerfile
ENV DD_LOGS_INTAKE_URL=https://http-intake.logs.datadoghq.com
ENV DD_LOGS_INTAKE_PORT=443
ENV DD_SERVICE=ainews
ENV DD_ENV=production
```

### CloudWatch Logs

```bash
# Install CloudWatch agent
aws logs create-log-group --log-group-name /ainews
aws logs create-log-stream --log-group-name /ainews --log-stream-name web

# Configure agent (etc/amazon/amazon-cloudwatch-agent/)
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/ainews/*.log",
            "log_group_name": "/ainews",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
```

---

## Log Query Examples

### Find all logs for a specific request

```
request_id:"abc123def456"
```

### Find slow queries

```
logger:"db.slow_query" duration_ms:>1000
```

### Find article processing errors

```
logger:"tasks.pipeline" level:"ERROR" article_id:123
```

### Find all logs for an article through pipeline

```
correlation_id:"pipeline-456-abc"
```

### Find login failures from IP

```
logger:"routes.admin" message:"Failed login" ip:"192.168.1.1"
```

### Find slow requests

```
logger:"request" duration_ms:>500
```

---

## Structured Logging Usage

### Python Logger Usage

```python
import logging

logger = logging.getLogger(__name__)

# Standard log
logger.info("Processing article")

# With extra fields
logger.info(
    "Article processed",
    extra={
        "article_id": 123,
        "stage": "write",
        "duration_ms": 1500.5
    }
)

# Error with exception
logger.error(
    "Failed to process article",
    extra={"article_id": 123},
    exc_info=True
)
```

### Avoid F-strings in Logs

Use `%`-style formatting for log messages:

```python
# Good - only constructs message if logged
logger.info("Article %s processed in %dms", article_id, duration_ms)

# Bad - always constructs message
logger.info(f"Article {article_id} processed in {duration_ms}ms")
```

---

## Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Detailed debugging information |
| INFO | General operational events |
| WARNING | Potential issues requiring attention |
| ERROR | Errors that affected request processing |
| CRITICAL | System-level failures |

### Recommended Levels

| Component | Default Level | Production Level |
|-----------|---------------|------------------|
| Application | INFO | INFO |
| Request logs | INFO | INFO |
| Database queries | DEBUG | WARNING |
| Slow queries | INFO | WARNING |
| Celery tasks | INFO | INFO |
| External services | WARNING | WARNING |

---

## Centralized Logging Best Practices

1. **Always include request_id** - Enables correlation across services
2. **Use structured fields** - Avoid embedding data in message strings
3. **Set appropriate levels** - Avoid log spam in production
4. **Rotate logs** - Configure log rotation to prevent disk exhaustion
5. **Monitor slow queries** - Set alerts for slow query threshold breaches
6. **Correlate pipeline events** - Use correlation_id to trace article lifecycle
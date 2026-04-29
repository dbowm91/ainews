# API Documentation

## Public Endpoints

### Health Check

**GET** `/health`

Returns the health status of the application.

**Authentication:** None required

**Query Parameters:**
- `detailed` (optional, boolean): Include detailed dependency checks

**Response (200 OK):**
```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok"},
    "redis": "ok",
    "celery": "ok",
    "limiter": "ok"
  }
}
```

**Response with `?detailed=true` (200 OK):**
```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok", "pool": {"size": 5, "checked_in": 0, "checked_out": 1}},
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

**Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "checks": {
    "database": {"status": "error"}
  }
}
```

### RSS Feed

**GET** `/rss`

Returns the latest articles as RSS feed.

**Response (200 OK):** RSS 2.0 XML

### Topic Feed

**GET** `/topic/<topic_name>`

Returns articles filtered by topic.

**Query Parameters:**
- `page` (optional, integer): Page number for pagination

### Article Detail

**GET** `/article/<short_id>`

Returns article detail page.

**Parameters:**
- `short_id`: Short article identifier

### Subscribe

**POST** `/subscribe`

Subscribe to the newsletter.

**Request Body:**
```json
{
  "email": "user@example.com",
  "newsletter_type": "main"
}
```

**Response (200 OK):**
```json
{"message": "Verification email sent"}
```

### Verify Subscription

**GET** `/verify/<token>`

Verify email subscription.

**Response (302 Redirect):** Redirects to success page or error page.

### Unsubscribe

**POST** `/unsubscribe`

Unsubscribe from newsletter.

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 OK):**
```json
{"message": "Unsubscribed successfully"}
```

---

## Admin API Endpoints

All admin endpoints require authentication via session-based auth (login at `/admin/login`).

### Admin Health Check

**GET** `/admin/api/health`

Returns detailed health status including circuit breakers, cache stats, and DNS cache.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "flask": "ok",
  "database": {"status": "ok"},
  "redis": "ok",
  "celery": "ok",
  "limiter": {"healthy": true},
  "circuit_breakers": {
    "openai": {"state": "closed", "failures": 0},
    "anthropic": {"state": "closed", "failures": 0}
  },
  "cache": {"hits": 100, "misses": 10},
  "dns_cache": {"size": 50, "hits": 200}
}
```

### Worker Health

**GET** `/admin/api/workers/health`

Returns detailed Celery worker status.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "status": "ok",
  "workers": {"worker1@example.com": "alive"},
  "active_tasks": {"worker1@example.com": 2},
  "reserved_tasks": {"worker1@example.com": 1},
  "stats": {
    "worker1@example.com": {
      "pool": 4,
      "total_tasks": 1500
    }
  }
}
```

### Task Status

**GET** `/admin/api/task/<task_id>`

Get status of a Celery task.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "task_id": "abc123",
  "status": "SUCCESS",
  "result": {"article_id": 1}
}
```

### Config Reload

**POST** `/admin/api/config/reload`

Clear all cached configs and reload from disk. Validates config before reload.

**Authentication:** Session required

**Request Body:** None

**Response (200 OK):**
```json
{"message": "Config cache cleared"}
```

**Response (400 Bad Request):**
```json
{"error": "Config validation failed", "details": ["Invalid LLM provider"]}
```

### Metrics

**GET** `/admin/api/metrics`

Get application metrics as JSON.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "counters": {"requests": 1000},
  "gauges": {"queue_size": 5},
  "histograms": {"request_duration": [0.1, 0.2, 0.3]}
}
```

### Prometheus Metrics

**GET** `/admin/api/metrics/prometheus`

Get metrics in Prometheus text format.

**Authentication:** Session required

**Response (200 OK):**
```
# HELP requests_total Total requests
# TYPE requests_total counter
requests_total 1000
```

### Pipeline Stats

**GET** `/admin/api/pipeline/stats`

Get pipeline stage success/failure statistics.

**Authentication:** Session required

**Query Parameters:**
- `minutes` (optional, integer): Time window in minutes (default: 15, max: 120)

**Response (200 OK):**
```json
{
  "select": {"success": 100, "failure": 5},
  "research": {"success": 95, "failure": 3},
  "write": {"success": 90, "failure": 2},
  "edit": {"success": 88, "failure": 1}
}
```

### Dead Letter Stats

**GET** `/admin/api/pipeline/dead-letter/stats`

Get statistics on stuck and failed articles.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "stuck_articles": 3,
  "failed_articles": 15,
  "gauge_stuck": 3
}
```

### Pipeline SLA

**GET** `/admin/api/pipeline/sla`

Get SLA metrics for article processing (avg, p50, p95 latencies).

**Authentication:** Session required

**Query Parameters:**
- `days` (optional, integer): Time window in days (default: 7, max: 30)

**Response (200 OK):**
```json
{
  "crawl_to_select": {"avg": 12.5, "p50": 10.2, "p95": 25.0},
  "select_to_research": {"avg": 45.0, "p50": 40.1, "p95": 90.5},
  "select_to_done": {"avg": 180.0, "p50": 150.0, "p95": 400.0}
}
```

### Article IDs

**GET** `/admin/api/articles/ids`

Return article IDs matching filter params for bulk selection UI.

**Authentication:** Session required

**Query Parameters:**
- `q` (optional): Search query (URLs or titles)
- `status` (optional): Pipeline status filter
- `category` (optional): Category filter
- `source_id` (optional): Source ID filter
- `date_from`, `date_to` (optional): Date range (ISO format)
- `impact_min`, `impact_max` (optional): Impact score range
- `tag` (optional): Tag slug filter

**Response (200 OK):**
```json
{"ids": [1, 2, 3], "count": 3}
```

### Newsletter Stats

**GET** `/admin/api/newsletters/stats`

Get newsletter delivery statistics.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "total_newsletters": 100,
  "total_recipients": 5000,
  "total_delivered": 4800,
  "total_with_errors": 50,
  "recent": [...]
}
```

### Cost Summary

**GET** `/admin/api/costs`

Get LLM cost summary from token usage metrics.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "total_tokens": 150000,
  "total_cost_usd": 2.50,
  "total_calls": 500,
  "models": [
    {
      "provider": "openai",
      "model": "gpt-4",
      "total_tokens": 100000,
      "estimated_cost_usd": 1.50,
      "call_count": 300
    }
  ]
}
```

### Sources Health

**GET** `/admin/api/sources/health`

Get health status of all sources.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "sources": [
    {
      "id": 1,
      "source_key": "hacker-news",
      "name": "Hacker News",
      "active": true,
      "consecutive_failures": 0,
      "last_success_at": "2024-01-01T12:00:00Z",
      "last_error": null,
      "disabled_at": null
    }
  ]
}
```

### Bulk Article Operations

**POST** `/admin/api/articles/bulk`

Perform bulk operations on articles.

**Authentication:** Session required

**Request Body:**
```json
{
  "article_ids": [1, 2, 3],
  "action": "delete|set_status|set_category|reprocess|add_tags",
  "status": "pending|researching|writing|editing|completed|failed",
  "category": "ai|programming|hardware|security|other",
  "tags": ["tag1", "tag2"]
}
```

**Response (200 OK):**
```json
{"message": "Deleted 3 articles"}
```

### Newsletter Preview

**POST** `/admin/api/newsletter/preview`

Generate newsletter HTML without sending.

**Authentication:** Session required

**Request Body:**
```json
{
  "newsletter_type": "main"
}
```

**Response (200 OK):**
```json
{
  "subject": "AI News - January 1, 2024",
  "article_count": 10,
  "html": "<html>..."
}
```

### Webhooks

#### List Webhooks

**GET** `/admin/api/webhooks`

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "webhooks": [
    {
      "id": 1,
      "name": "My Webhook",
      "url": "https://example.com/webhook",
      "events": ["article.published"],
      "active": true,
      "failure_count": 0
    }
  ]
}
```

#### Create Webhook

**POST** `/admin/api/webhooks`

**Authentication:** Session required

**Request Body:**
```json
{
  "name": "New Webhook",
  "url": "https://example.com/hook",
  "events": ["article.published", "article.selected"],
  "secret": "optional-secret"
}
```

**Response (201 Created):**
```json
{"message": "Webhook created", "id": 2}
```

#### Update Webhook

**PUT** `/admin/api/webhooks/<id>`

**Authentication:** Session required

**Request Body:**
```json
{
  "name": "Updated Name",
  "url": "https://new-url.com/hook",
  "events": ["article.published"],
  "active": true
}
```

**Response (200 OK):**
```json
{"message": "Webhook updated"}
```

#### Delete Webhook

**DELETE** `/admin/api/webhooks/<id>`

**Authentication:** Session required

**Response (200 OK):**
```json
{"message": "Webhook deleted"}
```

#### Test Webhook

**POST** `/admin/api/webhooks/<id>/test`

**Authentication:** Session required

**Response (200 OK):**
```json
{"message": "Webhook test sent", "status_code": 200}
```

#### Webhook Events

**GET** `/admin/api/webhooks/<id>/events`

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "events": [
    {
      "event_type": "article.published",
      "status_code": 200,
      "delivered_at": "2024-01-01T12:00:00Z"
    }
  ]
}
```

### Search Analytics

**GET** `/admin/api/search/analytics`

Get search query statistics and zero-result queries.

**Authentication:** Session required

**Response (200 OK):**
```json
{
  "total_queries": 500,
  "top_queries": [
    {"query": "openai", "count": 150}
  ],
  "zero_result_queries": [
    {"query": "unknown term", "count": 10}
  ]
}
```

### Audit Logs

**GET** `/admin/api/audit-logs`

Get audit log entries.

**Authentication:** Session required

**Query Parameters:**
- `action` (optional): Filter by action type
- `category` (optional): Filter by category
- `page` (optional): Page number

**Response (200 OK):**
```json
{
  "logs": [
    {
      "id": 1,
      "action": "article.publish",
      "category": "article",
      "target_type": "article",
      "target_id": 123,
      "created_at": "2024-01-01T12:00:00Z"
    }
  ]
}
```

### Reprocess Article

**POST** `/admin/api/articles/<article_id>/reprocess`

Reset article for reprocessing through the pipeline.

**Authentication:** Session required

**Response (200 OK):**
```json
{"message": "Article queued for reprocessing"}
```

### Article Search

Articles can be searched via the admin interface with URL search, source filtering, and date range filtering.

---

## Authentication

Admin endpoints use session-based authentication via `/admin/login`.

Rate limiting on admin login prevents brute-force attacks. After 5 failed attempts within 15 minutes, the IP is locked out for 15 minutes.

---

## Error Responses

All error responses use this format:

```json
{"error": "Error message describing what went wrong"}
```

Status codes:
- 400: Bad Request (invalid input)
- 401: Unauthorized (missing/invalid credentials)
- 403: Forbidden (insufficient permissions)
- 404: Not Found
- 500: Internal Server Error
# Infrastructure

Core infrastructure services powering the ainews platform: Redis, SQLite, Celery, email delivery, health checks, rate limiting, and caching.

## Redis

Redis serves multiple roles: message broker, cache, rate limiter, distributed lock, and metrics store.

### Connection Management

```python
# extensions.py

def get_redis() -> redis.Redis:
    """Thread-safe Redis client with connection pooling.
    Supports TLS via REDIS_SSL env var.
    Password preserved via urlparse when switching DBs."""

_redis_client: redis.Redis | None = None
_redis_lock = threading.Lock()
```

### Redis DB Allocation

| DB | Purpose |
|----|---------|
| 0 | Celery broker (from `CELERY_BROKER_URL` env var) |
| 1 | Config cache (via `CONFIG_CACHE_REDIS_URL`) |
| 15 | Flask-Limiter storage (derived from broker URL) |

### Distributed Locks

Used for crawl dedup, retry sweeps, and publish scheduling:

```python
# Pattern: Use task's self.request.id as lock value
# so retries can re-acquire the lock
lock = redis_client.lock(f"lock:crawl:{source_key}", timeout=300)
if lock.acquire(blocking=False):
    try:
        # ... do work
    finally:
        lock.release()
```

**Fail-closed**: `crawl_source`, `retry_stuck`, and `publish_scheduled` raise immediately when Redis is unavailable.

## SQLite

SQLite with WAL mode is the primary data store — intentional for read-heavy workload.

### WAL Mode

```python
# app.py
def set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
```

### Key Models

- **Article**: 30+ fields, pipeline_status flow, 15+ indexes
- **Source**: Health tracking (consecutive_failures, disabled_at)
- **Newsletter**: Delivery tracking with idempotency
- **TrendMemory**: Embedding-based semantic trend storage
- **AdminUser**: TOTP 2FA with 8 backup codes

### Indexes

Key composite indexes for query performance:
- `ix_articles_status_created` on `(pipeline_status, created_at)`
- `ix_articles_published` on `original_published_at`
- `ix_articles_impact` on `impact_score`
- `uq_source_external_id` unique on `(source_id, external_id)`

## Celery

### Task Architecture

```python
# celery_app.py

class FlaskTask(celery.Task):
    """Base task that creates Flask app context per execution."""
    def __call__(self, *args, **kwargs):
        with current_app.app_context():
            return self.run(*args, **kwargs)
```

### Task Configuration

```python
# config.py
class Config:
    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TIMEZONE = "UTC"
    CELERY_TASK_TRACK_STARTED = True
```

### Autoretry Pattern

All tasks use autoretry for transient errors:

```python
@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def my_task(self, ...):
    ...
```

### Celery Beat Schedule

14 scheduled tasks loaded from `pipeline.yaml`:

| Task | Schedule | Description |
|------|----------|-------------|
| `run-all-sources` | Every 30 min | Crawl all sources |
| `retry-stuck-articles` | Every 60 min | Retry/dead-letter stuck articles |
| `generate-newsletters` | Daily 8 AM ET | Generate newsletters |
| `cleanup-old-logs` | Daily 3 AM | Clean old pipeline logs |
| `consolidate-trend-memory` | Daily 3:30 AM | Consolidate trend memory |
| `purge-trend-memory` | Daily 3:45 AM | Purge expired memory |
| `cleanup-old-versions` | Daily 3:45 AM | Clean article versions |
| `cleanup-expired-verifications` | Every 15 min | Clean expired tokens |
| `publish-scheduled-articles` | Every 5 min | Publish scheduled articles |
| `cleanup-stale-limiter-slots` | Every 5 min | Clean stale limiter slots |
| `retry-failed-newsletter-deliveries` | Every 2 hours | Retry failed emails |
| `recalculate-impact-scores` | Daily 4 AM | Recalculate scores |
| `cleanup-inactive-subscribers` | Daily 1 AM | Flag inactive subscribers |
| `backfill-embeddings` | Daily 2 AM | Generate missing embeddings |

## Email Delivery

```python
# services/email.py

def send_newsletter_email(email: str, subject: str, html_content: str, unsubscribe_url: str):
    """Send newsletter with SMTP connection pooling."""

def send_verification_email(email: str, newsletter_type: str, verification_url: str, ...):
    """Send subscription verification email."""

def send_welcome_email(email: str, newsletter_type: str, unsubscribe_url: str, ...):
    """Send welcome email after subscription."""
```

### Features

- **Connection pooling**: Reuses SMTP connections across sends
- **Plain-text fallback**: `multipart/alternative` with both plain-text and HTML
- **HTML-to-plain**: `html_to_plain_text()` for RFC-compliant email
- **Batched sending**: Newsletter dispatch in batches of 500
- **Retry logic**: 3 attempts with exponential backoff

## Health Checks

```python
# services/health.py

@dataclass
class HealthResult:
    status: str  # "ok", "degraded", "unhealthy"
    checks: dict[str, Any]
    version: dict[str, str] | None

    @property
    def is_healthy(self) -> bool:
        """Returns True for both 'ok' and 'degraded'."""
        return self.status in ("ok", "degraded")

def run_health_checks(include_celery: bool = True, detailed: bool = False) -> HealthResult:
    """Check database, Redis, Celery, and limiter health."""
    # Database: Core service - failure → "unhealthy"
    # Redis: Non-core - failure → "degraded"
    # Celery: Non-core - failure → "degraded"
    # Limiter: Non-core - failure → "degraded"
```

**Degradation**: Redis/Celery/limiter failures return "degraded" (app still serves). Database failure returns "unhealthy".

**Detailed auth**: `GET /health?detailed=true` requires admin session — prevents information disclosure.

## Rate Limiting

```python
# services/limiter.py

class ModelLimiter:
    """Redis-based concurrency limiter for LLM providers.
    Uses Lua scripts for atomic slot management.
    Provider/model-aware with pub/sub notifications."""

    def acquire(self, provider_id: str, model: str, max_concurrent: int, timeout: float = 300) -> bool:
        """Acquire rate limiter slot for specific provider/model. Returns True if acquired."""

    def release(self, provider_id: str, model: str, timeout: float = 300) -> None:
        """Release rate limiter slot. Always call in finally block."""

    def get_active(self, provider_id: str, model: str) -> int | None:
        """Get count of active slots for provider/model."""
```

### Slot Management

- **Acquire**: Redis Lua script atomically checks and decrements slots
- **Release**: Redis Lua script increments slots, publishes notification
- **Stale cleanup**: `cleanup-stale-limiter-slots` task removes orphaned slots
- **Pub/Sub**: Waiters notified when slots become available

**Critical**: Always release in `finally` block using `provider_id or rc.provider` as fallback.

## Caching

```python
# services/cache.py

class ResponseCache:
    """Two-level cache: L1 in-memory (LRU) + L2 Redis.
    With stampede protection via Redis pub/sub."""

    def get(self, key: str) -> Any | None:
        """Get value from cache (L1 then L2)."""

    def set(self, key: str, value: Any, ttl: int = 120) -> None:
        """Set value in both cache levels."""

    def invalidate(self, key: str) -> None:
        """Invalidate a specific cache key."""

    def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all keys matching prefix."""
```

### Cache Keys

Public cache keys use `pub:` prefix:
- `pub:top_impact:10` — Top impact articles
- `pub:article_detail:123` — Article detail page
- `pub:related:456` — Related articles

### Stampede Protection

`get_or_set()` wraps lock acquisition + value computation in `RedisError` try/except, falling back to uncached computation if Redis is unavailable.

### Incremental Eviction

O(1) eviction checks only the oldest 5 entries (FIFO via `OrderedDict`) on each `get()`/`set()` call.

## Circuit Breaker

```python
# services/circuit_breaker.py

class CircuitBreaker:
    """CLOSED → OPEN → HALF_OPEN state machine.
    Uses sliding window failure counting."""

    def __init__(self, name: str, failure_threshold=5, recovery_timeout=60.0, half_open_max_calls=1, window_seconds=120.0):
        ...

    def record_success(self) -> None:
        """Record success, potentially closing circuit."""

    def record_failure(self) -> None:
        """Record failure, potentially opening circuit."""

    def can_execute(self) -> bool:
        """Check if circuit allows requests (not open)."""
```

### States

- **CLOSED**: Normal operation, failures counted in sliding window
- **OPEN**: All requests rejected immediately (no LLM call)
- **HALF_OPEN**: After recovery timeout, one test request allowed

## Webhook Dispatch

```python
# services/webhooks.py

def dispatch_webhook(webhook_id, name, url, secret, event_type, event_data, idempotency_key=None) -> tuple[bool, str | None]:
    """Dispatch webhook event with HMAC signing."""
    # 1. Find matching webhooks by event_type
    # 2. Sign payload with HMAC-SHA256
    # 3. Encrypt secrets at rest (Fernet/AES-128-CBC)
    # 4. Send with retry + exponential backoff
    # 5. Log delivery in WebhookEvent model
```

### Security

- **HMAC-SHA256 signatures** with timestamp replay protection
- **Fernet encryption** for webhook secrets at rest
- **Key rotation** support via `WEBHOOK_SECRET_KEY`
- **Idempotency keys** for duplicate prevention

## Structured Logging

```python
# services/logging_utils.py

def get_tracer() -> Tracer:
    """Returns tracer (noop exporter when OTel unavailable)."""

def traced_llm_call(provider: str, model: str, stage: str):
    """Context manager for LLM spans."""

def traced_stage(stage: str, operation: str = "execute"):
    """Context manager for pipeline stage spans."""

def log_pipeline_event(stage: str, event: str, article_id=None, run_id=None, level="info", **extra):
    """Structured pipeline event logging."""

def log_article_event(article_id: int, event: str, level="info", **extra):
    """Structured article event logging."""
```

### Features

- **Request ID propagation**: `g.request_id` → Celery task headers
- **OpenTelemetry tracing**: LLM calls and pipeline stages
- **Slow query detection**: Query duration logging
- **Correlation IDs**: Request-level tracing

## Metrics

```python
# services/metrics.py

class MetricsCollector:
    """Redis-backed counters, gauges, histograms.
    With in-memory fallback."""

    def counter_inc(self, name: str, value: int = 1, labels: dict = None): ...
    def gauge_set(self, name: str, value: float, labels: dict = None): ...
    def histogram_observe(self, name: str, value: float, labels: dict = None): ...
    def get_prometheus(self) -> str: ...
```

### Pipeline Metrics

- `pipeline.stage.{stage}.success` — Stage success count
- `pipeline.stage.{stage}.failure` — Stage failure count
- `pipeline.throughput.{stage}` — Items per minute
- `llm.calls` — LLM call count (with stage label)
- `llm.tokens` — Token usage (with stage label)

## ThreadPoolExecutor Pattern

Blocking I/O must use bounded thread pools:

```python
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="my_service")

def blocking_api(arg):
    try:
        future = _EXECUTOR.submit(_do_blocking_work, arg)
        return future.result(timeout=30)
    except (FuturesTimeoutError, TimeoutError):
        future.cancel()
        raise
```

**Important**: In `finally` block, use `executor.shutdown(wait=False, cancel_futures=True)` — not a `with` context manager.

Used in: `services/content_extractor.py`, `services/search/*.py`, `services/subagent/`.

## Key Files

| File | Purpose |
|------|---------|
| `extensions.py` | `db`, `redis`, `limiter` singletons |
| `config.py` | Flask config + Celery beat schedule |
| `celery_app.py` | Celery setup + `FlaskTask` base |
| `services/cache.py` | `ResponseCache` (L1 + L2) |
| `services/limiter.py` | `ModelLimiter` (Redis slots) |
| `services/circuit_breaker.py` | `CircuitBreaker` + `RedisCircuitBreaker` |
| `services/health.py` | Health check with degradation |
| `services/metrics.py` | `MetricsCollector` |
| `services/logging_utils.py` | Structured logging + OpenTelemetry |
| `services/email.py` | SMTP with connection pooling |
| `services/webhooks.py` | HMAC-signed webhook dispatch |
| `services/cost_tracker.py` | LLM cost tracking |
| `services/task_security.py` | HMAC task signing |

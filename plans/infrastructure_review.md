# Infrastructure Architecture Review

## Summary
Overall health: **Good with minor issues**

The infrastructure documentation is largely accurate. Most claims about Redis DB allocation, SQLite WAL pragmas, Celery configuration, rate limiting, circuit breaker, metrics, and email delivery are correct. One discrepancy was found related to request ID propagation.

## Verified Claims

### Redis - Verified
- **DB 0**: Celery broker from `CELERY_BROKER_URL` - Verified in `config.py:96`
- **DB 1**: Config cache via `CONFIG_CACHE_REDIS_URL` - Verified in `services/config_cache.py:297-302`
- **DB 15**: Flask-Limiter storage derived from broker URL - Verified in `extensions.py:18-31`
- Connection pooling with TLS support via `REDIS_SSL` env var - Verified in `extensions.py:107-126`
- Thread-safe initialization with `_redis_lock` - Verified in `extensions.py:65,79-81`

### SQLite WAL - Verified
All PRAGMA settings verified in `app.py:163-173`:
- `journal_mode=WAL` - Correct
- `synchronous=NORMAL` - Correct
- `busy_timeout=5000` - Correct
- `cache_size=-64000` (64MB) - Correct
- `foreign_keys=ON` - Correct
- `temp_store=MEMORY` - Correct
- `mmap_size=268435456` (256MB) - Correct

### Celery Configuration - Verified
- `CELERY_TASK_SERIALIZER = "json"` - `config.py:102`
- `CELERY_RESULT_SERIALIZER = "json"` - `config.py:103`
- `CELERY_ACCEPT_CONTENT = ["json"]` - `config.py:100`
- `CELERY_TIMEZONE = "UTC"` - `config.py:104`
- `CELERY_TASK_TRACK_STARTED = True` - `config.py:106`
- FlaskTask creates app context per execution - Verified in `celery_app.py:20-45`

### ModelLimiter Interface - Verified
- `acquire(provider_id, model, max_concurrent, timeout=300)` - `services/limiter.py:39-93`
- `release(provider_id, model, timeout=300)` - `services/limiter.py:95-130`
- `get_active(provider_id, model)` - `services/limiter.py:132-140`
- Lua scripts for atomic slot management - Verified in `services/limiter.py:9-29`
- Stampede protection via pub/sub - Verified in `services/limiter.py:54-85`

### Health Checks - Verified
- `HealthResult.is_healthy` returns True for "ok" and "degraded" - `services/health.py:27-29`
- `HealthResult.is_fully_healthy` returns True only for "ok" - `services/health.py:31-33`
- Database failure → "unhealthy" - `services/health.py:140-144`
- Redis/Celery/limiter failure → "degraded" - `services/health.py:146-163`

### MetricsCollector - Verified
- `counter_inc(name, value=1, labels=None)` - `services/metrics.py:44-58`
- `gauge_set(name, value, labels=None)` - `services/metrics.py:60-75`
- `histogram_observe(name, value, labels=None)` - `services/metrics.py:77-97`
- `get_prometheus()` - `services/metrics.py:219-271`

### ConfigCache - Verified
- Two-tier L1/L2 architecture - Verified in `services/config_cache.py:76-212`
- `_MAX_MEMORY_ENTRIES = 500` - `services/config_cache.py:16`
- Default TTL 300s - `services/config_cache.py:191`
- Stampede protection via Redis locks with 10s expiry - `services/config_cache.py:138`
- Polling every 50ms for 10 iterations - `services/config_cache.py:121-133`
- Pydantic serialization with type metadata - `services/config_cache.py:19-55`
- Allowlist enforcement for `schemas.*` only - `services/config_cache.py:64-73`
- mtime-based invalidation with 86400s TTL - `services/config_cache.py:241-274`

### ResponseCache - Verified
- Two-tier L1/L2 architecture - Verified in `services/cache.py:32-305`
- Default TTL 120s - `services/cache.py:49`
- L1 max size from `L1_CACHE_MAXSIZE` env var - `services/cache.py:22-29`
- FIFO eviction checking oldest 5 entries - `services/cache.py:67-78`
- Stampede protection via pub/sub - `services/cache.py:143-189`
- Cache keys with `pub:` prefix - `services/cache.py:84`

### Circuit Breaker - Verified
- CLOSED → OPEN → HALF_OPEN state machine - `services/circuit_breaker.py:25-28`
- Sliding window failure counting - `services/circuit_breaker.py:99-108`
- Default parameters: failure_threshold=5, recovery_timeout=60.0, half_open_max_calls=1, window_seconds=120.0 - `services/circuit_breaker.py:40-52`
- `can_execute()` method - `services/circuit_breaker.py:155-170`
- `record_success()` and `record_failure()` - `services/circuit_breaker.py:110-153`

### Email Delivery - Verified
- `SMTPConnectionPool` class - `services/email.py:14-122`
- Connection pooling with configurable pool size - Verified
- `multipart/alternative` with plain-text and HTML - `services/email.py:354-363`
- `html_to_plain_text()` for RFC-compliant fallback - `services/email.py:329-347`
- `send_newsletter_email()` - `services/email.py:287-326`
- `send_verification_email()` - `services/email.py:186-238`
- `send_welcome_email()` - `services/email.py:241-284`
- Batch sending in `tasks/newsletter.py:70-110` with BATCH_SIZE=500
- `send_single_email` Celery task with autoretry - `tasks/newsletter.py:42-68`

### Webhook Dispatch - Verified
- HMAC-SHA256 signatures with timestamp replay protection - `services/webhooks.py:104-125`
- Fernet encryption for secrets at rest - `services/webhooks.py:69-101`
- Key rotation support via `WEBHOOK_SECRET_KEY_PREVIOUS_1/2` - `services/webhooks.py:51-66`
- Idempotency keys - `services/webhooks.py:223-239`
- Retry with exponential backoff (up to 5 attempts) - `services/webhooks.py:158-194`
- SSRF protection via `validate_url_safe()` - `services/webhooks.py:241-247`

### ThreadPoolExecutor Pattern - Verified
1. **Subagent Executor** (`services/subagent/config.py:11`): `ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS)` where `SUBAGENT_WORKERS` defaults to 8. Graceful shutdown via `atexit` handler.
2. **Batch LLM Executor** (`services/llm/base.py:398`): `ThreadPoolExecutor(max_workers=max_workers)` with fresh executor per batch call.
3. **Timeout Executor** (`services/timeout.py:49`): `ThreadPoolExecutor(max_workers=1)` with `shutdown(wait=False, cancel_futures=True)`.

### Structured Logging - Verified
- `get_tracer()` returns None when OTel unavailable - `services/logging_utils.py:61-74`
- `traced_llm_call()` context manager - `services/logging_utils.py:250-275`
- `traced_stage()` context manager - `services/logging_utils.py:278-298`
- `log_pipeline_event()` - `services/logging_utils.py:85-111`
- `log_article_event()` - `services/logging_utils.py:114-132`
- OpenTelemetry span attributes: `llm.provider`, `llm.model`, `llm.stage`, `pipeline.stage`, `pipeline.operation` - Verified

### Celery Beat Schedule - Mostly Verified
13 scheduled tasks defined in `config.py:148-205`:
1. run-all-sources - Every 30 min
2. retry-stuck - Every 60 min
3. generate-newsletters - Daily 8 AM
4. cleanup-old-logs - Daily 3 AM
5. consolidate-trend-memory - Daily 3:30 AM
6. purge-trend-memory - Daily 3:45 AM
7. cleanup-old-versions - Daily 3:45 AM
8. cleanup-expired-verifications - Every 15 min
9. publish-scheduled-articles - Every 5 min
10. cleanup-stale-limiter-slots - Every 5 min
11. retry-failed-newsletter-deliveries - Every 2 hours
12. recalculate-impact-scores - Daily 4 AM
13. cleanup-inactive-subscribers - Daily 1 AM
14. backfill-embeddings - Daily 2 AM

### Fail-Closed Behavior - Verified
- `crawl_source` raises on Redis error - `tasks/crawl.py:72-74`
- `retry_stuck` raises on Redis error - `tasks/retry.py:108-110`
- `publish_scheduled_articles` raises on Redis error - `tasks/scheduler.py:53-55`

### Database Models - Verified
- Article: 30+ fields, pipeline_status flow, 15+ indexes - Verified in `models/article.py`
- `ix_articles_status_created` on `(pipeline_status, created_at)` - `models/article.py:68`
- `ix_articles_published` on `original_published_at` - `models/article.py:69`
- `ix_articles_impact` on `impact_score` - `models/article.py:70`
- `uq_source_external_id` unique constraint on `(source_id, external_id)` - `models/article.py:67`

## Discrepancies Found

### 1. Request ID Propagation Description Inaccurate
- **Claim**: "Request ID propagation: g.request_id → Celery task headers"
- **Reality**: Request ID is stored in `request_id_var` (a ContextVar), NOT in `g.request_id`. The Flask middleware sets `g.request_id` from `get_request_id()` (which reads from `request_id_var`), but the actual propagation to Celery uses `request_id_var` directly.
- **Severity**: Minor
- **Location**: `services/logging_utils.py:34` and `celery_app.py:48-56`
- **Suggested fix**: Update documentation to say "Request ID propagation: request_id_var (ContextVar) → Celery task headers"

## Bugs Identified

No bugs found. All verified infrastructure components function as documented.

## Improvement Opportunities

### 1. Add `is_fully_healthy` to Documentation
The `HealthResult` class has both `is_healthy` (returns True for "ok" and "degraded") and `is_fully_healthy` (returns True only for "ok"), but only `is_healthy` is documented. Consider documenting both properties.

**Location**: `services/health.py:27-33`

### 2. Document `ResponseCache.record_hit()` and `record_miss()`
The `ResponseCache` class has `record_hit()` and `record_miss()` methods for tracking cache statistics that are not documented in the infrastructure doc.

**Location**: `services/cache.py:51-65`

### 3. Document `ResponseCache.get_stats()`
The `get_stats()` method returns hit/miss statistics but is not documented.

**Location**: `services/cache.py:223-244`

### 4. Add `cleanup_stale_slots` Method to Limiter Documentation
The `ModelLimiter.cleanup_stale_slots()` method exists and is used by the `cleanup_stale_limiter_slots` Celery task, but the infrastructure doc's "Slot Management" section doesn't mention the cleanup mechanism.

**Location**: `services/limiter.py:142-163`

## Stale Items Found

None - the infrastructure document is current and accurate.

## Recommendations

1. **Low Priority**: Update the "Request ID propagation" description to accurately reflect that `request_id_var` (ContextVar) is used, not `g.request_id`.

2. **Low Priority**: Consider adding `is_fully_healthy` to the documentation alongside `is_healthy`.

3. **Informational**: The infrastructure documentation is comprehensive and well-maintained. The few discrepancies found are minor and do not affect system behavior.
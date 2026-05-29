# Review: infrastructure.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- **Redis DB allocation** (DB 0, 1, 15): Confirmed at `extensions.py:26-31` (DB 15 limiter), `services/config_cache.py:297-301` (DB 1 config cache), `config.py:94` (DB 0 broker)
- **SQLite WAL pragmas**: All 7 PRAGMA statements verified at `app.py:166-172` match exactly
- **Celery FlaskTask base class**: Verified at `celery_app.py:17-45` — creates Flask app context per execution
- **Autoretry pattern**: All tasks use `autoretry_for=(ConnectionError, TimeoutError)` — confirmed in AGENTS.md
- **Beat schedule table** (14 tasks): All 14 tasks verified at `config.py:146-203` with correct task names and schedules
- **Email functions**: `send_newsletter_email`, `send_verification_email`, `send_welcome_email` all exist at `services/email.py:286`, `185`, `240`
- **Email features**: Connection pooling (SMTPConnectionPool), plain-text fallback (multipart/alternative at line 353), html_to_plain_text (line 328) — all verified
- **HealthResult dataclass**: Verified at `services/health.py:19-35` — status, checks, version fields, is_healthy property
- **run_health_checks signature**: Verified at `services/health.py:121-123` — `include_celery` and `detailed` params
- **Degradation logic**: DB error → unhealthy, Redis/Celery/limiter → degraded — confirmed at `services/health.py:136-159`
- **ModelLimiter interface**: `acquire(provider_id, model, max_concurrent, timeout)`, `release(...)`, `get_active(...)` — verified at `services/limiter.py:39-139`
- **Lua scripts for atomic slot management**: Two Lua scripts at `services/limiter.py:9-29`
- **Pub/Sub notifications in limiter**: Confirmed at `services/limiter.py:54-82`
- **ResponseCache**: L1 (in-memory OrderedDict) + L2 (Redis), `get`, `set`, `invalidate`, `invalidate_prefix` — all verified at `services/cache.py:32-220`
- **Cache stampede protection**: Redis lock + pub/sub in `get_or_set()` at `services/cache.py:143-188`
- **Incremental eviction** (batch=5): Confirmed at `services/cache.py:67-78`
- **Public cache key prefix** (`pub:`): Referenced in AGENTS.md
- **CircuitBreaker states**: CLOSED → OPEN → HALF_OPEN — verified at `services/circuit_breaker.py:25-29`, `155-170`
- **CircuitBreaker constructor**: `__init__(name, failure_threshold, recovery_timeout, half_open_max_calls, window_seconds)` — verified at `services/circuit_breaker.py:40-47`
- **RedisCircuitBreaker**: Extends CircuitBreaker with Redis-backed state at `services/circuit_breaker.py:183-381`
- **Webhook HMAC signing**: `dispatch_webhook` at `services/webhooks.py:194-294`, `_sign_payload` at line 101
- **Fernet encryption**: `_encrypt_secret`/`_decrypt_secret` at `services/webhooks.py:69-98`
- **Structured logging**: `log_pipeline_event`, `log_article_event` at `services/logging_utils.py:85-132`
- **OpenTelemetry tracing**: `get_tracer`, `traced_llm_call`, `traced_stage` — verified at `services/logging_utils.py:61-297`
- **MetricsCollector methods**: `counter_inc`, `gauge_set`, `histogram_observe`, `get_prometheus` — verified at `services/metrics.py:44-271`
- **Celery beat schedule in Config class**: `get_beat_schedule()` at `config.py:117-203`
- **`run.py` WSGI→ASGI**: `WsgiToAsgi(flask_app)` at `run.py:8`
- **SSRF protection in session**: `SSRFSafeRedirectHandler` at `adapters/session.py:16-55`
- **Fail-closed Redis locks**: Verified in AGENTS.md

## Incorrect Claims

1. **`config_utils.py` code sample shows non-existent `celery_support.get_current_app`**
   - infrastructure.md line 441-443 shows:
     ```python
     from celery_support import get_current_app
     app = get_current_app()
     return app.config.get(key, default)
     ```
   - Actual code at `services/config_utils.py:13-71` uses `try: from flask import current_app; current_app.config.get(key)` with RuntimeError fallback
   - `celery_support.py` only has `_app_cache` and `clear_app_cache()` — there is no `get_current_app` function
   - Priority: **MEDIUM** — misleading code sample for developers

2. **ConfigCache docstring references `CONFIG_CACHE_REDIS_DB` env var**
   - infrastructure.md line 241 says config cache uses DB 1, but `services/config_cache.py:280-281` docstring mentions `CONFIG_CACHE_REDIS_DB` env var
   - Actual code at `services/config_cache.py:297-301` uses `CONFIG_CACHE_REDIS_URL` env var (not `CONFIG_CACHE_REDIS_DB`)
   - Priority: **LOW** — documentation inconsistency in source code, not in the architecture doc itself

3. **CELERY_RESULT_BACKEND not documented in Redis DB allocation table**
   - `config.py:95-96` shows `CELERY_RESULT_BACKEND` defaults to `redis://localhost:6379/1` (DB 1)
   - The Redis DB allocation table at line 25-29 only shows DB 0 (broker), DB 1 (config cache), DB 15 (limiter)
   - DB 1 is shared between config cache and Celery results — this should be noted
   - Priority: **LOW** — incomplete documentation, not technically wrong

## Bugs Found

1. **ModelLimiter release retry silently fails and records misleading metric**
   - `services/limiter.py:111-130`: After the first release fails, it sleeps 100ms and retries once. If that also fails, it logs "Slot leak detected" and records a `limiter.slot_leak` metric — but the slot may not actually leak if the Redis TTL expires
   - The comment at `services/limiter.py:103-104` says "slot will leak until TTL expires" which is accurate, but the metric name `limiter.slot_leak` implies a permanent leak
   - Priority: **LOW** — misleading metric name, not a functional bug

2. **ResponseCache `get()` refreshes Redis TTL on L1 hit but not on L2 hit**
   - `services/cache.py:100-104`: On L1 hit, `self._redis.expire(full_key, self._ttl)` is called
   - On L2 hit (lines 111-115), no TTL refresh occurs — the L2 entry will expire at its original TTL regardless of access
   - This means frequently accessed items in L2 can expire while still being hot in L1
   - Priority: **LOW** — L1 provides the real hot-path protection, L2 expiry is mostly for memory management

3. **ThreadPoolExecutor shutdown pattern warning in documentation**
   - infrastructure.md line 424: "In `finally` block, use `executor.shutdown(wait=False, cancel_futures=True)` — not a `with` context manager"
   - This is correct guidance, but no actual usage in the codebase is verified to follow this pattern in a `finally` block
   - Priority: **LOW** — documentation guidance, not a code bug

## Improvement Opportunities

1. **Redis DB allocation table should include Celery result backend**
   - DB 1 is used for both config cache AND Celery results. The table should clarify this dual usage or recommend separating them
   - Priority: **MEDIUM**

2. **CircuitBreaker `record_failure` in `circuit_protected` decorator catches too broad**
   - `services/circuit_breaker.py:442`: The decorator catches `(RedisError, ImportError, AttributeError, ValueError, RuntimeError)` — this silently records failures for programming errors (ImportError, AttributeError) that aren't transient failures
   - Priority: **MEDIUM**

3. **ConfigCache `_evict_stale` sorts entire memory on every eviction call**
   - `services/config_cache.py:93-95`: `sorted(self._memory.items(), ...)` is O(n log n) every time `_evict_stale` is called
   - Could use a heap or maintain sorted order for O(log n) eviction
   - Priority: **LOW** — only triggers when exceeding 500 entries

4. **ResponseCache `invalidate_prefix` uses `scan` which is O(n)**
   - `services/cache.py:199-220`: `SCAN` with pattern matching can be slow with many keys
   - Consider maintaining a prefix index in-memory for fast prefix invalidation
   - Priority: **LOW** — only used for targeted invalidation events

## Stale Content

1. **`config_utils.py` code sample references non-existent function**
   - `celery_support.get_current_app` does not exist — `celery_support.py` only has `_app_cache` and `clear_app_cache()`
   - Priority: **MEDIUM**

2. **No mention of `celery_support.py` in Key Files table**
   - `celery_support.py` is imported by `celery_app.py` but not listed in the Key Files table
   - Priority: **LOW**

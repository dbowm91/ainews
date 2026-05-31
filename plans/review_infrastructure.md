# Review: infrastructure.md

**Reviewed:** 2026-05-31
**Source:** `architecture/infrastructure.md`
**Reviewer:** Subagent 5 (Infrastructure & Config Layer)
**Status:** COMPLETE

---

## Verified Claims

### Redis DB Allocation
| Claim | Status | Evidence |
|-------|--------|----------|
| DB 0 = Celery broker | VERIFIED | `extensions.py:87` reads `CELERY_BROKER_URL` |
| DB 1 = Config cache | VERIFIED | `services/config_cache.py:297-302` uses DB 1 via `CONFIG_CACHE_REDIS_URL` |
| DB 15 = Flask-Limiter storage | VERIFIED | `extensions.py:29` sets `path="/15"` |

### SQLite WAL Pragmas
| Claim | Status | Evidence |
|-------|--------|----------|
| `journal_mode=WAL` | VERIFIED | `app.py:166` |
| `synchronous=NORMAL` | VERIFIED | `app.py:167` |
| `busy_timeout=5000` | VERIFIED | `app.py:168` |
| `cache_size=-64000` (64MB) | VERIFIED | `app.py:169` |
| `foreign_keys=ON` | VERIFIED | `app.py:170` |
| `temp_store=MEMORY` | VERIFIED | `app.py:171` |
| `mmap_size=268435456` (256MB) | VERIFIED | `app.py:172` |

### Celery Task Configuration
| Claim | Status | Evidence |
|-------|--------|----------|
| `FlaskTask` base class | VERIFIED | `celery_app.py:17-45` |
| `CELERY_TIMEZONE = "UTC"` | VERIFIED | `config.py:102` |
| `CELERY_TASK_TRACK_STARTED = True` | VERIFIED | `config.py:104` |
| `CELERY_TASK_SERIALIZER = "json"` | VERIFIED | `config.py:100` |

### Email Delivery
| Claim | Status | Evidence |
|-------|--------|----------|
| `SMTPConnectionPool` class | VERIFIED | `services/email.py:13-121` |
| `send_newsletter_email()` exists | VERIFIED | `services/email.py:286-325` |
| `send_verification_email()` exists | VERIFIED | `services/email.py:185-237` |
| `send_welcome_email()` exists | VERIFIED | `services/email.py:240-283` |
| Plain-text fallback (`multipart/alternative`) | VERIFIED | `services/email.py:353-362` |

### Health Checks
| Claim | Status | Evidence |
|-------|--------|----------|
| `HealthResult` dataclass | VERIFIED | `services/health.py:19-35` |
| `run_health_checks()` signature | VERIFIED | `services/health.py:121-165` |
| DB failure → "unhealthy" | VERIFIED | `services/health.py:139-140` |
| Redis/Celery/limiter failure → "degraded" | VERIFIED | `services/health.py:144-159` |

### Rate Limiter
| Claim | Status | Evidence |
|-------|--------|----------|
| `ModelLimiter` class | VERIFIED | `services/limiter.py:32-169` |
| `acquire(provider_id, model, max_concurrent)` | VERIFIED | `services/limiter.py:39-93` |
| `release(provider_id, model)` | VERIFIED | `services/limiter.py:95-130` |
| `get_active(provider_id, model)` | VERIFIED | `services/limiter.py:132-139` |
| Pub/sub notification pattern | VERIFIED | `services/limiter.py:54-85` |

### Response Cache
| Claim | Status | Evidence |
|-------|--------|----------|
| L1 in-memory + L2 Redis | VERIFIED | `services/cache.py:32-41` |
| `get()`, `set()`, `invalidate()`, `invalidate_prefix()` | VERIFIED | `services/cache.py:86-221` |
| Incremental eviction (batch=5) | VERIFIED | `services/cache.py:67-78` |
| Stampede protection via Redis lock + pub/sub | VERIFIED | `services/cache.py:143-189` |

### Config Cache
| Claim | Status | Evidence |
|-------|--------|----------|
| Two-tier: L1 memory + L2 Redis | VERIFIED | `services/config_cache.py:76-83` |
| `_MAX_MEMORY_ENTRIES = 500` | VERIFIED | `services/config_cache.py:16` |
| `invalidate_if_stale()` with mtime | VERIFIED | `services/config_cache.py:241-261` |
| Stampede protection via Redis lock | VERIFIED | `services/config_cache.py:136-185` |

### Circuit Breaker
| Claim | Status | Evidence |
|-------|--------|----------|
| `CircuitBreaker(name, failure_threshold=5)` | VERIFIED | `services/circuit_breaker.py:40-59` |
| `can_execute()` method | VERIFIED | `services/circuit_breaker.py:155-170` |
| `record_success()` / `record_failure()` | VERIFIED | `services/circuit_breaker.py:110-153` |
| `RedisCircuitBreaker` with in-memory fallback | VERIFIED | `services/circuit_breaker.py:183-380` |

### Webhook Dispatch
| Claim | Status | Evidence |
|-------|--------|----------|
| HMAC-SHA256 signatures | VERIFIED | `services/webhooks.py:101-122` |
| Fernet encryption for secrets | VERIFIED | `services/webhooks.py:69-98` |
| Retry with exponential backoff (5 attempts) | VERIFIED | `services/webhooks.py:155-191` |
| `dispatch_webhook()` function | VERIFIED | `services/webhooks.py:194-294` |
| `trigger_event()` fanout | VERIFIED | `services/webhooks.py:297-330` |

### Metrics
| Claim | Status | Evidence |
|-------|--------|----------|
| `MetricsCollector` class | VERIFIED | `services/metrics.py:23-97` |
| `counter_inc()`, `gauge_set()`, `histogram_observe()` | VERIFIED | `services/metrics.py:44-97` |
| `get_prometheus()` format | VERIFIED | `services/metrics.py:219-271` |

### Structured Logging
| Claim | Status | Evidence |
|-------|--------|----------|
| `log_pipeline_event()` | VERIFIED | `services/logging_utils.py:85-111` |
| `log_article_event()` | VERIFIED | `services/logging_utils.py:114-132` |
| `traced_llm_call()` context manager | VERIFIED | `services/logging_utils.py:251-275` |
| `traced_stage()` context manager | VERIFIED | `services/logging_utils.py:278-298` |
| OpenTelemetry tracing | VERIFIED | `services/logging_utils.py:16-26` |

### ThreadPoolExecutor Pattern
| Claim | Status | Evidence |
|-------|--------|----------|
| Used in `services/content_extractor.py` | VERIFIED | `services/content_extractor.py:4,19` |
| Used in `services/search/duckduckgo.py` | VERIFIED | `services/search/duckduckgo.py:2,15` |
| Used in `services/search/google.py` | VERIFIED | `services/search/google.py:2,16` |
| Used in `services/search/searxng.py` | VERIFIED | `services/search/searxng.py:2,15` |
| Module-level singleton pattern | VERIFIED | All above files use module-level `_EXECUTOR` |

### URL Validation Layering
| Claim | Status | Evidence |
|-------|--------|----------|
| `utils/url.py` for adapters | VERIFIED | `utils/url.py:1-264` contains `validate_url_safe()` |
| `services/url.py` for services | VERIFIED | `services/url.py:1-192` re-exports from utils/url.py |

### Celery Beat Schedule (14 tasks)
| Claim | Status | Evidence |
|-------|--------|----------|
| `run-all-sources` | VERIFIED | `config.py:147-149` |
| `retry-stuck-articles` | VERIFIED | `config.py:150-152` |
| `generate-newsletters` | VERIFIED | `config.py:153-156` |
| `cleanup-old-logs` | VERIFIED | `config.py:157-160` |
| `consolidate-trend-memory` | VERIFIED | `config.py:161-164` |
| `purge-trend-memory` | VERIFIED | `config.py:165-168` |
| `cleanup-old-versions` | VERIFIED | `config.py:169-172` |
| `cleanup-expired-verifications` | VERIFIED | `config.py:173-176` |
| `publish-scheduled-articles` | VERIFIED | `config.py:177-180` |
| `cleanup-stale-limiter-slots` | VERIFIED | `config.py:181-184` |
| `retry-failed-newsletter-deliveries` | VERIFIED | `config.py:185-188` |
| `recalculate-impact-scores` | VERIFIED | `config.py:189-192` |
| `cleanup-inactive-subscribers` | VERIFIED | `config.py:193-197` |
| `backfill-embeddings` | VERIFIED | `config.py:198-202` |

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 386-389 | `traced_llm_call` and `traced_stage` signatures shown as standalone functions | These are `@contextmanager` functions in `services/logging_utils.py:251,278` — they are used as context managers (`with traced_llm_call(...):`), not standalone function calls | LOW |
| 445-446 | `executor.shutdown(wait=False, cancel_futures=True)` pattern described as "Important" | This pattern is NOT consistently used across all services. `services/subagent/config.py:11` creates executor but no explicit shutdown. The pattern is good but documentation implies it's universally followed when it isn't | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | infrastructure.md does not document the `services/subagent/config.py` ThreadPoolExecutor singleton (`_subagent_executor`), which is used for subagent LLM calls | `services/subagent/config.py:11` | LOW | The subagent system uses a bounded pool but this is not mentioned in the ThreadPoolExecutor section |
| 2 | infrastructure.md does not document the `services/llm/base.py` ThreadPoolExecutor for batch operations (`chat_structured_batch`) | `services/llm/base.py:396` | LOW | Batch LLM operations use a bounded pool for parallelism |
| 3 | infrastructure.md does not mention the `services/timeout.py` ThreadPoolExecutor for cross-platform timeout support | `services/timeout.py:29-49` | LOW | Timeout utility uses executor for cross-platform support |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Add documentation for the `services/subagent/config.py` executor pattern with configurable `SUBAGENT_WORKERS` env var | documentation | P3 |
| 2 | Document the `services/llm/base.py` batch LLM execution pattern with ThreadPoolExecutor | documentation | P3 |
| 3 | Document the `services/timeout.py` utility for cross-platform timeout support | documentation | P3 |
| 4 | Add note that `services/limiter.py` uses Redis DB 15 (derived from broker URL), which is the same DB as Flask-Limiter in `extensions.py` — this is intentional but could be clearer | documentation | P3 |
| 5 | The infrastructure.md `traced_llm_call` signature should show it's a context manager, not a regular function | documentation | P2 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 447 | "Used in: `services/content_extractor.py`, `services/search/*.py`, `services/subagent/`" | The subagent executor is in `services/subagent/config.py`, not a general pattern in `services/subagent/` | Update to `services/subagent/config.py` |

---

## Summary

- Verified: 68 claims
- Incorrect: 2 claims (both LOW severity)
- Bugs: 3 (HIGH: 0, MEDIUM: 0, LOW: 3)
- Improvements: 5
- Stale items: 1

The infrastructure.md document is highly accurate. The main issues are minor documentation gaps around ThreadPoolExecutor usage in subagent and batch LLM operations, and a slight inaccuracy in how `traced_llm_call`/`traced_stage` are presented (as standalone functions vs. context managers). No critical or high-severity issues found.

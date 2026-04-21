# Implementation Plan — Performance, Observability & Security

**Created:** April 21, 2026
**Status:** CLOSED — All items completed; E.2 deferred pending infrastructure work.

---

## Deferred Items

### E.2: Celery Task Event Streaming

**Status:** DEFERRED

Requires significant infrastructure work (celery.events.RealabilityMonitor or pubsub consumer, Redis streaming, MetricsCollector updates). Complex and invasive — not a stub implementation.

---

## Critical Implementation Notes

### Thread Safety
- Shared `ThreadPoolExecutor` instances are accessed from Celery task threads. `ThreadPoolExecutor` is thread-safe for `submit()` and `result()`. `ResponseCache` already uses `threading.Lock` for `_memory` access.
- Executor shutdown is not needed on module reload — executors clean up automatically when the process exits.

### Redis Error Handling
- All Redis operations should catch `redis.exceptions.RedisError` (not bare `Exception`)
- Webhook event queue uses separate Redis DB or key prefix to avoid collisions
- Celery event streaming to Redis should be fire-and-forget (don't block on Redis errors)

### Celery Task Patterns
- All long-running tasks should have both `soft_time_limit` and `time_limit`
- Use `autoretry_for` / `retry_backoff` decorators instead of manual `self.retry()`
- Tasks that touch database should commit in try/except with rollback on failure
- Re-raise after logging when the exception should trigger Celery retry

### Template Escaping
- All user-controlled data in templates should use `|e` filter
- Database fields populated from external sources (RSS feeds, LLM output) are NOT exempt
- Compromised feed sources could inject malicious content via these fields

### LLM Input Validation
- Treat LLM responses as untrusted input
- Parse JSON with error handling
- Validate structure before use
- Never pass unsanitized LLM output to system calls or dangerous functions

### Metrics Naming
Follow Prometheus naming conventions:
- Counters: `ainews_<subsystem>_<name>_total`
- Gauges: `ainews_<subsystem>_<name>`
- Histograms: `ainews_<subsystem>_<name>_seconds`

---

## Rollback Plan

If any change causes issues:
1. Revert the specific file change
2. Run tests to confirm restoration
3. Re-analyze before re-applying
4. For model changes, generate downgrade migration
5. Clear relevant Redis keys (config cache, locks)
6. For Celery task changes, ensure workers pick up changes (may need restart)
7. For template changes, clear any template cache

---

## Testing Commands

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

Key test files by area:
- DNS/URL validation: `tests/test_url_ssrf.py`
- Subagent: `tests/test_subagent.py`
- Cleanup tasks: `tests/test_cleanup.py`
- LLM adapters: `tests/test_llm_adapters/`
- Admin API: `tests/test_admin_api.py`
- Search/FTS: `tests/test_search.py`, `tests/test_fts.py`

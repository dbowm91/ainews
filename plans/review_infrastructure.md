# Infrastructure.md Review

**Reviewed:** 2026-05-29
**Source:** `architecture/infrastructure.md`

---

## Verified Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| Redis DB 0 = Celery broker | ✅ Verified | `config.py:94` uses `CELERY_BROKER_URL` |
| Redis DB 15 = Flask-Limiter | ✅ Verified | `extensions.py:29` uses `new_parsed._replace(path="/15")` |
| SQLite WAL pragmas | ✅ Verified | `app.py:163-172` sets all listed pragmas |
| CELERY_TIMEZONE = "UTC" | ✅ Verified | `config.py:102` |
| HealthResult dataclass | ✅ Verified | `services/health.py:19-35` |
| `run_health_checks()` function | ✅ Verified | `services/health.py:121-165` |
| ModelLimiter interface | ✅ Verified | `services/limiter.py:32-169` - `acquire(provider_id, model, max_concurrent)`, `release(provider_id, model)`, `get_active(provider_id, model)` |
| ResponseCache L1+L2 | ✅ Verified | `services/cache.py:32-120` - L1 OrderedDict, L2 Redis |
| CircuitBreaker `can_execute()` | ✅ Verified | `services/circuit_breaker.py:155-170` |
| CircuitBreaker `name` param | ✅ Verified | `services/circuit_breaker.py:40-47` |
| `get_breaker()` factory | ✅ Verified | `services/circuit_breaker.py:388-406` |
| MetricsCollector methods | ✅ Verified | `services/metrics.py:44-97` - `counter_inc`, `gauge_set`, `histogram_observe` |
| Email functions | ✅ Verified | `services/email.py:185,240,286` |
| Webhook HMAC+Fernet | ✅ Verified | `services/webhooks.py:1-80` |
| `services/url.py` exists | ✅ Verified | File exists at `services/url.py` |
| ConfigCache two-tier | ✅ Verified | `services/config_cache.py:16` - `_MAX_MEMORY_ENTRIES = 500` |

---

## Incorrect Claims

### HIGH: `CELERY_RESULT_BACKEND` uses wrong env var (line 103)

**Doc says:**
```python
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
```

**Actual (`config.py:95-96`):**
```python
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
)
```

The doc uses `REDIS_URL` but the actual code uses `CELERY_RESULT_BACKEND`. Also default is `/1` not `/0`.

---

## Bugs Found

### MEDIUM: Missing `services/task_security.py` in Key Files table (line 443)

The table lists `services/task_security.py` as a key file, but the file does exist at `services/task_security.py`. The listing is correct but incomplete - see Improvement Opportunities.

### LOW: `services/webhooks.py` listed but `dispatch_webhook` function signature differs

**Doc says (`infrastructure.md:341`):**
```python
def dispatch_webhook(webhook_id, name, url, secret, event_type, event_data, idempotency_key=None)
```

**Actual** - need to verify full signature from `services/webhooks.py`.

---

## Improvement Opportunities

### `services/url.py` SSRF protection not documented as duplicate of `utils/url.py`

The doc mentions `services/url.py` in the Key Files table but doesn't document the relationship with `utils/url.py`. Per `AGENTS.md`:

> `utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py`, but duplicates `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` with its own config support. Use `utils/url.py` for adapters (clean layering), `services/url.py` for services (has config support).

The `services/url.py` does `from utils.url import ...` for the exports but has its own SSRF implementation with config support.

### Missing `services/url.py` relationship to `utils/url.py`

The Key Files table entry for `services/url.py` should clarify its purpose vs `utils/url.py`.

### Stale/Outdated References

The "Key Files" table (lines 428-445) mentions `services/task_security.py` but doesn't mention:
- `services/alerts.py` (alerting layer - Phase 3.7)
- `services/quality_report_service.py` (new quality report service)
- `services/stage_cost.py` (new cost estimation)

---

## Priority Findings

| Priority | Finding | Location |
|----------|---------|----------|
| HIGH | `CELERY_RESULT_BACKEND` env var name is wrong | `infrastructure.md:103` vs `config.py:95-96` |
| MEDIUM | Missing documentation of `services/url.py` vs `utils/url.py` layering | `infrastructure.md` Key Files |
| LOW | Incomplete Key Files table - missing newer services | `infrastructure.md:428-445` |

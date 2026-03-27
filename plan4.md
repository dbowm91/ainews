# ainews Codebase Improvement Plan 4

Additional recommendations from codebase review, focusing on items not covered in plan.md or already implemented.

---

## Already Implemented (Verified)

The following items from my review are already addressed in the codebase:

| Item | Location | Status |
|------|----------|--------|
| LLM Provider Fallback | `services/llm/__init__.py:29-69` | ✅ Implemented |
| N+1 Query Fix (joinedload) | `services/related.py:16` | ✅ Implemented |
| Crawl Lock Retry-Aware | `tasks/crawl.py:27-36` | ✅ Implemented |
| Argon2 Password Hash | `routes/admin/__init__.py:44-46` | ✅ Implemented |
| Login Lockout TOCTOU | `routes/admin/__init__.py:107-131`, `services/login_lockout.lua` | ✅ Implemented |
| SMTP Timeout | `services/email.py:129` (timeout=30) | ✅ Implemented |
| Email Warning to Users | `routes/public.py:501-516` | ✅ Implemented |
| Newsletter Silent Failure | `tasks/newsletter.py:125-127` | ✅ Implemented |
| Redundant Count Query | `routes/admin/review.py:19-23` | ✅ Implemented |
| Ollama Error Conversion | `services/llm/ollama.py:10-21` | ✅ Implemented |
| Article Age/Stuck Tracking | `tasks/retry.py:27-66`, `constants.py:32-33` | ✅ Implemented |
| Logger Consistency | All task files use `get_task_logger` | ✅ Implemented |
| Transaction Safety | All task files use proper rollback+raise | ✅ Implemented |
| Cross-Source Deduplication | `tasks/extract.py:10-58` (_find_duplicate_article) | ✅ Implemented |

---

## Priority 1: Correctness & Safety

### 1.1 DNS Cache Thread Safety
**Location:** `services/url.py:34-63`

**Problem:** The `_TTLCache` class comment says "Thread-safe enough for GIL-guarded access" but this is misleading. While CPython's GIL makes single bytecode operations atomic, the `get`/`set`/`clear` methods have multiple bytecode instructions and can interleave with other threads. In practice, the risk is very low (SSRF validation is fast, race window tiny) but the comment is technically incorrect.

**Fix:** Add a threading lock to `_TTLCache`:
```python
import threading

class _TTLCache:
    def __init__(self, maxsize: int, ttl: float) -> None:
        self._store: dict[str, tuple[float, list[str]]] = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> list[str] | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if (time.monotonic() - ts) >= self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: list[str]) -> None:
        with self._lock:
            if len(self._store) >= self._maxsize:
                oldest = min(self._store, key=lambda k: self._store[k][0])
                del self._store[oldest]
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
```

**Update comment:**
```python
# Bounded TTL cache for DNS results.
# Thread-safe via explicit locking (not relying on GIL for multi-instruction operations).
# Short TTL limits DNS rebinding window for SSRF protection.
```

**Files:** `services/url.py`, `tests/test_url.py`

**Estimated time:** 30 minutes

---

## Priority 2: Observability

### 2.1 Pipeline Stage Failure Rate Tracking
**Location:** New `services/pipeline_monitor.py`, admin API

**Problem:** Pipeline failures are logged per-article but there's no aggregated view of failure rates. A gradual increase in LLM failures (provider degradation, rate limits, model issues) goes unnoticed until articles pile up.

**Current state:** Individual errors logged, no aggregation or alerting.

**Fix:** Add failure rate tracking with Redis minute-buckets:
```python
# New file: services/pipeline_monitor.py
import time
from extensions import get_redis

STAGES = ["crawl", "select", "research", "write", "edit"]
BUCKET_TTL = 7200  # 2 hours (keep 2x the window)

def record_stage_result(stage: str, success: bool):
    """Record pipeline stage result for failure rate calculation."""
    redis = get_redis()
    bucket = int(time.time() // 60)  # Per-minute buckets
    key = f"ainews:pipeline:{stage}:{bucket}"
    field = "success" if success else "failure"
    redis.hincrby(key, field, 1)
    redis.expire(key, BUCKET_TTL)

def get_failure_rates(window_minutes: int = 60) -> dict:
    """Get failure rates for each stage in the last N minutes."""
    redis = get_redis()
    now = int(time.time() // 60)
    rates = {}
    
    for stage in STAGES:
        total_success = 0
        total_failure = 0
        for offset in range(window_minutes):
            key = f"ainews:pipeline:{stage}:{now - offset}"
            data = redis.hgetall(key)
            if data:
                total_success += int(data.get(b"success", 0))
                total_failure += int(data.get(b"failure", 0))
        total = total_success + total_failure
        rates[stage] = {
            "success": total_success,
            "failure": total_failure,
            "total": total,
            "failure_rate": total_failure / total if total > 0 else 0.0,
        }
    return rates
```

Call `record_stage_result()` in `tasks/pipeline.py:run_stage()` success/except paths.

Add admin endpoint:
```python
# routes/admin/api.py
@admin_bp.route("/api/pipeline/stats")
@require_auth
def pipeline_stats():
    from services.pipeline_monitor import get_failure_rates
    return jsonify(get_failure_rates())
```

**Files:** New `services/pipeline_monitor.py`, `tasks/pipeline.py`, `routes/admin/api.py`

**Estimated time:** 2-3 hours

---

### 2.2 Celery Worker Health Check
**Location:** `routes/public.py` health endpoint

**Problem:** The `/health` endpoint checks database and Redis but not Celery workers. Workers could be dead while Flask is healthy, causing articles to pile up in "pending" status silently.

**Current state:** No Celery health check in `/health`.

**Fix:** Add Celery inspect ping to health check:
```python
# routes/public.py health() function
# Celery worker check
try:
    from celery_app import celery
    inspect = celery.control.inspect(timeout=2.0)
    ping = inspect.ping()
    if ping:
        checks["celery"] = "ok"
        checks["celery_workers"] = len(ping)
    else:
        checks["celery"] = "no_response"
        overall = "degraded"
except Exception as e:
    checks["celery"] = f"error: {str(e)[:100]}"
    overall = "degraded"
```

**Note:** `inspect.ping()` can be slow if workers are unresponsive, so add a short timeout.

**Files:** `routes/public.py`, `celery_app.py`

**Estimated time:** 1 hour

---

### 2.3 Config Hot-Reload Validation
**Location:** `routes/admin/api.py` config reload endpoint

**Problem:** `POST /admin/api/config/reload` clears caches but doesn't validate the new config is valid. Admin could upload broken YAML and only discover errors when tasks fail.

**Current state:** Cache cleared, no validation before returning success.

**Fix:** Validate all configs before clearing cache:
```python
@admin_bp.route("/api/config/reload", methods=["POST"])
@require_auth
def config_reload():
    from schemas.pipeline import load_pipeline_config
    from schemas.source import load_sources
    from schemas.topic import load_topics
    from schemas.llm import load_providers_config
    from services.llm import clear_provider_cache
    from services.cache import get_response_cache
    
    errors = []
    
    # Validate each config file
    try:
        load_pipeline_config()
    except Exception as e:
        errors.append(f"pipeline.yaml: {e}")
    
    try:
        load_sources()
    except Exception as e:
        errors.append(f"sources.yaml: {e}")
    
    try:
        load_topics()
    except Exception as e:
        errors.append(f"topics.yaml: {e}")
    
    try:
        providers = load_providers_config()
        # Validate enabled providers have required config
        for p in providers.providers:
            if p.enabled:
                if p.type == "openai" and not p.config.get("api_key"):
                    errors.append(f"Provider '{p.id}': missing api_key")
                elif p.type == "anthropic" and not p.config.get("api_key"):
                    errors.append(f"Provider '{p.id}': missing api_key")
                elif p.type == "ollama" and not p.config.get("model"):
                    errors.append(f"Provider '{p.id}': missing model")
    except Exception as e:
        errors.append(f"providers.yaml: {e}")
    
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400
    
    # All valid — clear caches
    clear_provider_cache()
    get_response_cache().clear()
    # ... clear config_cache ...
    
    return jsonify({"status": "ok", "message": "Config reloaded successfully"})
```

**Files:** `routes/admin/api.py`

**Estimated time:** 1 hour

---

## Priority 3: Documentation

### 3.1 DNS Cache TTL Tradeoffs
**Location:** `services/url.py:26-30`

**Current comment exists but could be clearer about the threat model:**
```python
# DNS cache to prevent rebinding between validation and fetch.
# Short TTL limits DNS rebinding window for SSRF protection.
# Entries may be stale for legitimate DNS changes (CDN rotation,
# failover) but shorter is safer here — fetch failures are
# preferable to SSRF exposure. 60s matches typical OS DNS cache TTLs.
```

**Recommendation:** This is already well-documented. No changes needed unless we want to add:
- Link to OWASP SSRF guidance
- Note about split-horizon DNS considerations

**Status:** Already documented adequately.

---

## Implementation Order

| # | Item | Priority | Time | Dependencies |
|---|------|----------|------|--------------|
| 1 | DNS Cache Thread Safety | High | 30m | None |
| 2 | Pipeline Failure Tracking | Medium | 2-3h | None |
| 3 | Celery Worker Health | Medium | 1h | None |
| 4 | Config Reload Validation | Low | 1h | None |

**Total estimated time:** ~5-7 hours

---

## Testing Strategy

For each fix:
1. Add/modify unit tests to verify the fix
2. Run full test suite: `.venv/bin/python -m pytest tests/ -x -q`
3. Run linting: `.venv/bin/ruff check . --exclude .venv`

---

## Pre-commit checks

After all changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

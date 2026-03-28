# ainews Improvement Plan

Consolidated plan from plan2–plan6. Items are deduplicated, organized by phase, and ordered by dependency and risk. Implementation should proceed top-to-bottom within each phase.

**Pre-commit checks (run after every item):**
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Phase 1: Thread Safety & Correctness (High Risk If Left Unfixed)

### 1.1 DNS Cache Thread Safety

**Location:** `services/url.py:34-63`

**Problem:** `_TTLCache` comment claims "thread-safe enough for GIL-guarded access" but `get`/`set`/`clear` have multiple bytecode instructions that can interleave across threads.

**Fix:** Add explicit `threading.Lock` to all `_TTLCache` methods. Update the comment to reflect explicit locking.

**Files:** `services/url.py`

**Estimated time:** 30 minutes

**Sources:** plan4 item 1.1

---

### 1.2 ConfigCache Thread Safety

**Location:** `services/config_cache.py:66`

**Problem:** `_memory_cache` is a plain dict with no thread-safety. Concurrent reads/writes from Celery workers or Flask threads can cause race conditions.

**Fix:**
1. Add `threading.RLock()` in `ConfigCache.__init__`
2. Wrap all `_memory_cache` read/write operations with lock context
3. Review all methods that access `_memory_cache`

**Files:** `services/config_cache.py`

**Estimated time:** 2 hours

**Sources:** plan6 item 1

---

### 1.3 Metrics Singleton Thread Safety

**Location:** `services/metrics.py:84-90`

**Problem:** `get_metrics()` lacks thread-safe initialization. Two threads can both see `_metrics_instance is None` and create duplicate instances.

**Fix:** Apply double-checked locking pattern (same as `services/limiter.py:72-86`):
```python
_metrics_lock = threading.Lock()

def get_metrics() -> MetricsCollector:
    global _metrics_instance
    if _metrics_instance is not None:
        return _metrics_instance
    with _metrics_lock:
        if _metrics_instance is not None:
            return _metrics_instance
        _metrics_instance = MetricsCollector()
    return _metrics_instance
```

**Files:** `services/metrics.py`

**Estimated time:** 15 minutes

**Sources:** plan3 item 1

---

## Phase 2: Security & Safety

### 2.1 Admin Route Authorization Audit

**Location:** `routes/admin/api.py`, all admin route modules

**Problem:** Verify that every admin endpoint uses `@require_auth`. While 27 instances were found, no centralized audit has been done.

**Fix:** Run audit command and add `@require_auth` to any missing endpoints:
```bash
grep -rn "def " routes/admin/ | grep -v "@require_auth" | grep "def "
```

**Files:** `routes/admin/api.py`, all admin route modules

**Estimated time:** 30 minutes

**Sources:** plan5 item 5.1 (revised per plan5's own accuracy review — "verify remaining routes" not "fix gaps")

---

### 2.2 Celery Task Timeout Protection

**Location:** All task modules in `tasks/`

**Problem:** Long-running LLM calls can stall workers indefinitely. No `soft_time_limit` or `time_limit` on Celery tasks (confirmed via grep).

**Fix:** Add to all task decorators:
```python
@shared_task(bind=True, max_retries=2, default_retry_delay=60,
             soft_time_limit=300, time_limit=360)
```

**Apply to:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `tasks/crawl.py`

**Files:** All task modules

**Estimated time:** 1 hour

**Sources:** plan5 item 5.6

---

### 2.3 Subscriber Soft Delete for GDPR

**Location:** `models.py:151-172`

**Problem:** Subscriber has no `deleted_at` column (confirmed). GDPR requires data minimization — soft delete should be default.

**Fix:**
1. Add `deleted_at = db.Column(db.DateTime)` to Subscriber model
2. Create migration for the new column
3. Add `get_active()` classmethod filtering `deleted_at.is_(None)`
4. Update all subscriber queries to filter out deleted records

**Files:** `models.py`, `routes/admin/subscribers.py`, `routes/public.py`, new migration

**Estimated time:** 2 hours

**Sources:** plan5 item 5.7

---

### 2.4 Admin Password Warning in Dev Mode

**Location:** `config.py:78-79`

**Problem:** `DevelopmentConfig` allows empty `ADMIN_PASSWORD`. Could accidentally run production with no admin auth if misconfigured.

**Fix:** Add warning when admin password is empty:
```python
class DevelopmentConfig(Config):
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    def __init__(self):
        super().__init__()
        if not self.ADMIN_PASSWORD:
            logging.warning("ADMIN_PASSWORD not set - admin login disabled")
```

**Files:** `config.py`

**Estimated time:** 30 minutes

**Sources:** plan5 item 5.4

---

## Phase 3: Configuration & Validation (Consolidated)

Merges: plan3 item 4 (production config startup validation), plan4 item 2.3 (config hot-reload validation), plan5 item 5.5 (LLM provider startup validation).

### 3.1 Config Validation (Startup + Hot-Reload)

**Problem:** Three related issues:
1. LLM provider validation at startup only warns, doesn't fail
2. `POST /admin/api/config/reload` clears caches without validating new config
3. No validation that enabled providers have required fields

**Fix — Startup (config.py):**
```python
def _validate_llm_providers():
    enabled_providers = []
    try:
        from schemas.llm import load_providers_config
        config = load_providers_config()
        for pdef in config.providers:
            if not pdef.enabled:
                continue
            enabled_providers.append(pdef.id)
            if pdef.type == "openai" and not pdef.config.get("api_key"):
                raise RuntimeError(f"Provider '{pdef.id}': missing api_key")
            elif pdef.type == "anthropic" and not pdef.config.get("api_key"):
                raise RuntimeError(f"Provider '{pdef.id}': missing api_key")
            elif pdef.type == "ollama" and not pdef.config.get("model"):
                raise RuntimeError(f"Provider '{pdef.id}': missing model")
    except Exception as e:
        logger.warning(f"Could not validate LLM providers: {e}")

    if not enabled_providers:
        raise RuntimeError("No LLM providers enabled. Configure at least one in providers.yaml")
```

**Fix — Hot-reload (`routes/admin/api.py:60-68`):**
1. Validate all config files (pipeline, sources, topics, providers) *before* clearing caches
2. If validation fails, return 400 with errors — do not clear caches
3. Only clear caches on success

**Files:** `config.py`, `routes/admin/api.py`

**Estimated time:** 1.5 hours

**Sources:** plan3 item 4, plan4 item 2.3, plan5 item 5.5

---

## Phase 4: Pipeline Reliability (COMPLETED)

**Status:** All items completed. See deferred.md for details on changes made.

### 4.1 Newsletter Pipeline Error Handling

**Location:** `services/newsletter_pipeline.py`

**Problem:** LLM stages fail silently:
- Reader failure logs but continues with empty themes/highlights (lines 143-144)
- Writer failure returns empty string (lines 173-177)
- Editor failure falls back to previous output (lines 209-214)
- Main newsletter generates even with empty articles ("Top 0 stories")

**Fix:**
1. Add metrics counters for each pipeline fallback: `metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": "reader"})`
2. Fail explicitly if all stages produce nothing:
   ```python
   if not brief.themes and not brief.highlights:
       raise ValueError("Reader stage produced empty brief")
   ```
3. Add empty-article guard to main newsletter generation:
   ```python
   if not articles:
       logger.warning("Main newsletter has no articles, skipping generation")
       return
   ```
4. Include `used_fallback: bool` and `fallback_stages: list[str]` in response for observability

**Files:** `services/newsletter_pipeline.py`, `tasks/newsletter.py`

**Estimated time:** 2-3 hours

**Sources:** plan3 item 3, plan6 item 3, plan5 item 5.11

---

### 4.2 Pipeline Logging Silent Failures

**Location:** `tasks/pipeline.py:92-110`

**Problem:** `_log_pipeline()` silently catches exceptions on log write failures. Pipeline log entries are critical for audit trail.

**Current:**
```python
except Exception as e:
    savepoint.rollback()
    logger.error(f"Failed to write pipeline log: {e}")  # Only logs, doesn't re-raise
```

**Fix:**
1. Add metrics counter for failed log writes
2. For fatal stages, re-raise after logging failure
3. Consider storing in Redis queue as failover

**Files:** `tasks/pipeline.py`

**Estimated time:** 1 hour

**Sources:** plan5 item 5.3

---

### 4.3 Pipeline Stage Failure Rate Tracking

**Location:** New `services/pipeline_monitor.py`

**Problem:** Pipeline failures are logged per-article but there's no aggregated view. Gradual provider degradation goes unnoticed.

**Fix:** Add Redis minute-bucket counters for each stage (crawl, select, research, write, edit). Track success/failure counts. Add admin endpoint `GET /admin/api/pipeline/stats`.

**Files:** New `services/pipeline_monitor.py`, `tasks/pipeline.py`, `routes/admin/api.py`

**Estimated time:** 2-3 hours

**Sources:** plan4 item 2.1

---

### 4.4 Pipeline Status Constants

**Location:** Throughout `tasks/` and `services/`

**Problem:** Status strings (`"pending"`, `"researching"`, `"writing"`, `"done"`, `"failed"`) scattered as string literals. Easy to misspell.

**Fix:** Create `PipelineStatus` class in `constants.py` and replace all string literals:
```python
class PipelineStatus:
    PENDING = "pending"
    SELECTING = "selecting"
    RESEARCHING = "researching"
    WRITING = "writing"
    EDITING = "editing"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"
```

**Files:** `constants.py`, all task modules

**Estimated time:** 2 hours

**Sources:** plan5 item 5.10

---

## Phase 5: Error Handling & Logging (COMPLETED)

**Status:** All items completed. See deferred.md for details on changes made.

### 5.1 Redis Error Handling Standardization

**Location:** `routes/admin/__init__.py` lines 88, 127, 150, 178

**Problem:** Login lockout flow uses bare `Exception` for Redis operations. Per AGENTS.md convention, should use `redis.exceptions.RedisError`.

**Fix:**
```python
import redis.exceptions

# Change from:
except Exception as e:
# To:
except redis.exceptions.RedisError as e:
```

Note: Other services (LLM, search, email) intentionally use broader `Exception` for resilience. This fix applies only to Redis-specific operations.

**Files:** `routes/admin/__init__.py`

**Estimated time:** 15 minutes

**Sources:** plan3 item 2

---

### 5.2 Bare Exception Cleanup in Routes

**Location:** `routes/public.py` (5 remaining), `routes/admin/review.py`, `routes/admin/articles.py`

**Problem:** Many places catch bare `Exception` instead of specific types, hiding bugs.

**Fix:** Replace with specific types:
- `SQLAlchemyError` for database operations
- `redis.exceptions.RedisError` for Redis operations
- Keep bare `Exception` in Celery tasks for robustness

**Files:** `routes/public.py`, `routes/admin/review.py`, `routes/admin/articles.py`

**Estimated time:** 1-2 hours

**Sources:** plan2 item 2

---

### 5.3 Login Attempts Memory Cleanup

**Location:** `routes/admin/__init__.py:18`

**Problem:** `_login_attempts_memory` dict (Redis fallback) has no cleanup mechanism. Stale entries for one-time IP attempts remain indefinitely.

**Fix:**
1. Add `_MAX_MEMORY_ENTRIES = 1000` constant
2. Add `_cleanup_stale_entries()` that removes expired entries
3. Call cleanup in lockout check and record attempt functions

**Files:** `routes/admin/__init__.py`

**Estimated time:** 1 hour

**Sources:** plan6 item 4

---

### 5.4 Consistent Log Truncation

**Location:** Multiple files truncate article titles with inconsistent lengths.

**Fix:**
1. Add `MAX_LOG_TITLE_LENGTH = 100` and `truncate_for_log()` helper to `constants.py`
2. Replace inline `[:50]` truncations with the helper

**Files:** `constants.py`, `tasks/pipeline.py`, `services/crawling.py`

**Estimated time:** 30 minutes

**Sources:** plan6 item 6

---

## Phase 6: Observability (DEFERRED)

**Status:** All items deferred to future work. See deferred.md for details.

### 6.1 Request Correlation IDs

**Location:** `app.py`, `logging_config.py`

**Problem:** No correlation IDs for tracking requests across Flask, Celery, and logs.

**Fix:**
1. Add `@app.before_request` middleware to generate/pass `X-Correlation-ID` header
2. Store in Flask `g`
3. Include correlation ID in log format via custom formatter
4. Pass Celery task ID as correlation ID in task metadata

**Files:** `app.py`, `logging_config.py`, `celery_app.py`

**Estimated time:** 3-4 hours

**Sources:** plan2 item 3

---

### 6.2 Enhanced Logging (JSON + Request Timing)

**Location:** `logging_config.py`

**Remaining gaps:** Structured JSON logging option, user context in admin logs, request timing.

**Fix:**
1. Add `JSONFormatter` class for structured logging
2. Add `@app.after_request` handler for request duration logging
3. Set `g.user_id` in `require_auth` decorator, include in logs

**Files:** `logging_config.py`, `app.py`

**Estimated time:** 2-3 hours

**Sources:** plan2 item 4

---

### 6.3 Celery Worker Health Check

**Location:** `routes/public.py` health endpoint

**Problem:** `/health` checks DB and Redis but not Celery workers. Workers could be dead while Flask reports healthy.

**Fix:** Add `celery.control.inspect(timeout=2.0).ping()` to health check. Report worker count or mark degraded.

**Files:** `routes/public.py`, `celery_app.py`

**Estimated time:** 1 hour

**Sources:** plan4 item 2.2

---

## Phase 7: Maintainability & Cleanup (DEFERRED)

**Status:** All items deferred to future work. See deferred.md for details.

### 7.1 Extract Common Newsletter Logic

**Location:** `services/newsletter.py`

**Problem:** `generate_main_newsletter` and `generate_topic_newsletter` share ~80% code.

**Fix:** Extract shared logic into `_generate_newsletter(topic_key, ...)` private method. Both public functions call it.

**Files:** `services/newsletter.py`

**Estimated time:** 1-2 hours

**Sources:** plan6 item 5

---

### 7.2 Hardcoded Download Timeout

**Location:** `services/content_extractor.py`

**Problem:** `DOWNLOAD_TIMEOUT=30` is hardcoded. Should be configurable via environment variable.

**Fix:**
```python
DOWNLOAD_TIMEOUT = int(os.environ.get("CONTENT_EXTRACTOR_TIMEOUT", "30"))
```

**Files:** `services/content_extractor.py`

**Estimated time:** 30 minutes

**Sources:** plan5 item 5.9

---

### 7.3 Missing Type Hints on Key Services

**Location:** `services/url.py`, `services/prompts.py`, `services/utils.py`

**Fix:** Add return type annotations to all public functions.

**Estimated time:** 1 hour

**Sources:** plan5 item 5.12

---

## Phase 8: Testing (DEFERRED)

**Status:** All items deferred to future work. See deferred.md for details.

### 8.1 XML Escaping Tests

**Location:** `services/prompts.py:11-25`

**Problem:** `esc_xml_text()` and `esc_xml_attr()` exist but have no tests enforcing usage.

**Fix:** Add `tests/test_prompts.py` with tests for angle bracket escaping, attribute escaping, edge cases.

**Files:** `tests/test_prompts.py` (new)

**Estimated time:** 30 minutes

**Sources:** plan5 item 5.14

---

### 8.2 URL Validation Test Coverage

**Location:** `services/url.py`

**Problem:** URL validation is correct but edge cases untested (localhost with port, mixed case, public URLs with ports).

**Fix:** Add test cases to `tests/test_url_validate.py`:
1. Explicit `localhost` hostname
2. `localhost:8080` with port
3. Public URLs with ports
4. Mixed case hostname normalization

**Files:** `tests/test_url_validate.py`

**Estimated time:** 1 hour

**Sources:** plan6 item 2

---

### 8.3 Auth Lockout Tests

**Location:** `routes/admin/__init__.py`

**Problem:** No explicit tests for login lockout behavior.

**Fix:** Add tests for:
1. Failed login decrements remaining attempts
2. Lockout activates after max attempts
3. Lockout releases after timeout
4. Successful login resets attempts
5. Memory fallback on Redis failure

**Files:** `tests/test_admin_auth.py` (new)

**Estimated time:** 2 hours

**Sources:** plan6 item 7

---

### 8.4 Concurrent Access Tests

**Problem:** No tests for concurrent access patterns in ConfigCache, metrics singleton.

**Fix:** Add thread-safety tests for:
1. ConfigCache concurrent reads/writes
2. Metrics singleton uniqueness under concurrent access

**Files:** `tests/test_config_cache.py`, `tests/test_metrics_race.py`

**Estimated time:** 1-2 hours

**Sources:** plan6 item 8, plan3 item 1

---

### 8.5 Migration Testing

**Location:** Test suite

**Problem:** Tests use `db.create_all()` but production uses Flask-Migrate. Can miss migration-specific issues.

**Fix:** Add CI step that runs `flask db upgrade` before tests, or add dedicated migration test.

**Estimated time:** 1-2 hours

**Sources:** plan3 item 5

---

## Phase 9: Optional / Low ROI (DEFERRED)

**Status:** All items deferred to future work. See deferred.md for details.

### 9.1 Cost Tracking

**Problem:** LLM token usage not persisted or aggregated. Requires DB schema changes (`tokens_used`, `model_used` columns).

**Fix:** Add `services/cost_tracker.py` with per-model cost calculation. Add admin API endpoint.

**Files:** New `services/cost_tracker.py`, new `routes/admin/costs.py`

**Estimated time:** 4 hours

**Note:** Optional — pricing changes frequently, limited ROI.

**Sources:** plan2 item 5

---

### 9.2 Metrics Endpoint (Prometheus Format)

**Problem:** `services/metrics.py` exists but may not expose Prometheus format.

**Fix:** Verify current impl, add Prometheus exposition if needed.

**Estimated time:** 30 minutes

**Sources:** plan5 item 5.13

---

### 9.3 Rate Limit Configuration Review

**Location:** `extensions.py:32-36`

**Problem:** Default rate limit is 200/minute — very high for a news site, could enable scraping.

**Fix:** Make configurable via `DEFAULT_RATE_LIMIT` env var, default to 60/minute.

**Files:** `extensions.py`

**Estimated time:** 15 minutes

**Sources:** plan3 item 6

---

## Already Implemented (Do Not Re-Do)

These items appeared in source plans but are confirmed complete:

| Item | Evidence |
|------|----------|
| Enhanced Health Checks | `routes/public.py:295-330` checks DB, Redis, rate limiter |
| LLM Provider Fallback | `services/llm/__init__.py:29-69` |
| N+1 Query Fix | `services/related.py:16` (joinedload) |
| Crawl Lock Retry-Aware | `tasks/crawl.py:27-36` |
| Argon2 Password Hash | `routes/admin/__init__.py:44-46` |
| Login Lockout TOCTOU Fix | `routes/admin/__init__.py:107-131`, Lua script |
| SMTP Timeout | `services/email.py:129` |
| Redundant Count Query | `routes/admin/review.py:19-23` |
| Ollama Error Conversion | `services/llm/ollama.py:10-21` |
| Article Age/Stuck Tracking | `tasks/retry.py:27-66` |
| Transaction Safety | All task files use rollback+raise |
| Cross-Source Deduplication | `tasks/extract.py:10-58` |
| Subscriber Validation | `routes/public.py:406-408` |
| Login Lockout In-Memory Fallback | Intentional Redis fallback — keep as-is |

---

## Summary

| Phase | Items | Est. Time | Status |
|-------|-------|-----------|--------|
| 1. Thread Safety | 3 | ~2.75h | Not started (pre-existing) |
| 2. Security & Safety | 4 | ~3.5h | Not started (pre-existing) |
| 3. Config Validation | 1 | ~1.5h | Not started (pre-existing) |
| 4. Pipeline Reliability | 4 | ~7-8h | **COMPLETED** |
| 5. Error Handling & Logging | 4 | ~3-4h | **COMPLETED** |
| 6. Observability | 3 | ~6-8h | **DEFERRED** |
| 7. Maintainability | 3 | ~2.25h | **DEFERRED** |
| 8. Testing | 5 | ~5-6h | **DEFERRED** |
| 9. Optional | 3 | ~4.75h | **DEFERRED** |
| **Total (non-optional)** | **27** | **~30-35h** | |
| **Total (all)** | **30** | **~35-40h** | |
| **Completed** | **8** | **~10-12h** | **33% of total** |
| **Deferred** | **14** | **~18-22h** | **47% of total** |

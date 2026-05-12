# Tasks Architecture Review

## Overview
Review of the `tasks/` module against `architecture/tasks.md` claims.

---

## Verified Claims

### Task Definitions and Decorators
All task files correctly define Celery tasks with appropriate decorators:
- `@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, max_retries=CELERY_TASK_MAX_RETRIES)`
- Soft time limits and time limits properly configured (300s/360s typical)
- `autoretry_for` includes `ConnectionError`, `TimeoutError`, `ProviderServerError`
- `retry_backoff=True`, `retry_jitter=True` properly set

### File Inventory (architecture/tasks.md lines 5-18)
| File | Verified |
|------|----------|
| `crawl.py` | Yes - `run_all_sources`, `crawl_source`, `aggregate_crawl_results` |
| `extract.py` | Yes - `process_item` |
| `select.py` | Yes - `select_article` |
| `research.py` | Yes - `research_article` |
| `write.py` | Yes - `write_article` |
| `edit.py` | Yes - `edit_article` |
| `newsletter.py` | Yes - `generate_daily_newsletters`, `send_single_email`, `retry_failed_newsletter_deliveries` |
| `scheduler.py` | Yes - `publish_scheduled_articles` |
| `cleanup.py` | Yes - multiple cleanup tasks |
| `embeddings.py` | Yes - `backfill_embeddings` |

### Pipeline Stages (architecture/tasks.md lines 20-37)
Status values and transitions in `constants.py`:
- `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed` - **All present**
- `VALID_TRANSITIONS` properly defines allowed transitions
- `STAGE_STATUS_MAP` correctly maps stage names to status names

### run_stage() Helper (architecture/tasks.md lines 132-145)
The `run_stage()` function in `tasks/pipeline.py` (lines 389-442) correctly implements:
1. Acquires stage lock (prevents duplicate processing) - Line 415
2. Updates article status to stage - Done in `work()` functions
3. Executes task_func - Line 425
4. On success: transitions to next_stage - Done in `work()` functions via `_dispatch_next()`
5. On failure: handles retry/degrade - Line 433 via `_handle_stage_exception()`
6. Releases stage lock in finally block - Lines 437-442

### Degradation Path (architecture/tasks.md lines 147-156)
The `_degrade_and_advance()` function in `tasks/pipeline.py` correctly handles degradation:
- `select` failure: Sets `selector_result` and moves to `researching`
- `research` failure: Calls `degrade_stage(article, "writing")`
- `write` failure: Calls `degrade_stage(article, "editing")`
- `edit` failure: Calls `_finalize(article.id)`

### Celery Beat Schedule (architecture/tasks.md lines 157-177)
| Task | Schedule | Verified |
|------|----------|----------|
| `run-all-sources` | Every 30 min | Yes - `timedelta(minutes=crawl_interval)` |
| `retry-stuck-articles` | Every 60 min | Yes - `timedelta(minutes=retry_interval)` |
| `generate-newsletters` | 8:00 AM ET | Yes - `crontab(hour=newsletters_hour, minute=0)` |
| `cleanup-old-logs` | Daily 3 AM | Yes - `crontab(hour=cleanup_logs_hour, minute=0)` |
| `consolidate-trend-memory` | Daily 3:30 AM | Yes - `crontab(hour=trend_memory_hour, minute=30)` |
| `purge-trend-memory` | Daily 3:45 AM | Yes - `crontab(hour=trend_memory_hour, minute=45)` |
| `cleanup-old-versions` | Daily 3:45 AM | Yes - `crontab(hour=cleanup_versions_hour, minute=45)` |
| `cleanup-expired-verifications` | Every 15 min | Yes - `timedelta(minutes=cleanup_expired_interval)` |
| `publish-scheduled-articles` | Every 5 min | Yes - `timedelta(minutes=publish_interval)` |
| `cleanup-stale-limiter-slots` | Every 5 min | Yes - `timedelta(minutes=cleanup_limiter_interval)` |
| `retry-failed-newsletter-deliveries` | Every 2 hours | Yes - `timedelta(hours=2)` |
| `recalculate-impact-scores` | Daily 4:00 AM | Yes - `crontab(hour=4, minute=0)` |
| `cleanup-inactive-subscribers` | Daily 1:00 AM | Yes - `crontab(hour=cleanup_subscribers_hour, minute=cleanup_subscribers_minute)` |
| `backfill-embeddings` | Daily 2:00 AM | Yes - `crontab(hour=2, minute=0)` |

### Rate Limiting (architecture/tasks.md lines 178-184)
- LLM slots: Properly acquired via `services.limiter.ModelLimiter`
- Source slots: Per-source rate limiting via Redis locks in `crawl_source`
- Release in finally: Correctly implemented in `run_stage()` at line 436

---

## Discrepancies

### 1. Documented Degradation Path vs Actual Implementation
**Architecture doc (line 153):**
```
select → research → write → edit → review → done
```

**Actual code (`tasks/pipeline.py` `_degrade_and_advance`):**
- `edit` failure finalizes directly via `_finalize()` - does NOT go through `review`

**Impact:** Low - The actual implementation may be more efficient (direct finalization) than documented path.

### 2. `skip_next="finalize"` Parameter
**Architecture doc:** Describes `skip_next` in context of stage transitions (e.g., `skip_next=PipelineStatus.WRITING`)

**Actual code (`tasks/edit.py` line 397):**
```python
return run_stage("editor", article_id, _execute_editor_work, task_self=self, run_id=run_id, skip_next="finalize")
```
Uses string `"finalize"` not a `PipelineStatus` value. This is handled correctly in `_handle_disabled()` but differs from other stage tasks which use proper `PipelineStatus` values.

---

## Improvement Recommendations

### 1. Provider Resolution Before Limiter Acquisition
**Location:** `tasks/pipeline.py` lines 413-415

The provider is resolved BEFORE acquiring limiter resources:
```python
provider_info = _get_provider_for_stage(stage)
rc.provider, rc.model = provider_info[0], provider_info[1]
limiter, redis_client, lock_acquired = _acquire_stage_resources(...)
```

**Recommendation:** This is actually correct per the AGENTS.md note: "The `run_stage()` function resolves provider/model before acquiring limiter resources, ensuring correct release on early return." However, consider adding a comment explaining this ordering is intentional.

### 2. Missing Input Validation on `skip_next` Parameter
**Location:** `tasks/pipeline.py` `_handle_disabled()` function

The function accepts any `skip_next` value but only handles:
- `"finalize"` - calls `_finalize(article_id)`
- Anything else - calls `_dispatch_next(article_id, ..., skip_next)`

**Recommendation:** Add validation or documentation explaining expected values.

### 3. `_run_stage_core` Early Return Values
**Location:** `tasks/pipeline.py` lines 350, 367

When article not found or pipeline timeout exceeded, `_run_stage_core` returns:
```python
return {"article_id": article_id, "error": "not found"}, None, None
```
The `None, None` for provider_id and model could cause issues in the caller if not properly handled.

**Recommendation:** Ensure callers properly check for error returns before accessing provider_id/model.

---

## Bugs Found

### 1. Potential Uninitialized Variable Access in Exception Handler
**Location:** `tasks/pipeline.py` lines 422-423, 433

```python
model = None
provider_id = None
try:
    result, provider_id, model = _run_stage_core(...)
    ...
except Exception as e:
    return _handle_stage_exception(e, stage, article_id, run_id, t0, provider_id, model)
```

**Issue:** If `_run_stage_core` raises an exception BEFORE line 374 where `model` and `provider_id` are assigned, the exception handler will receive `None` values.

**Affected paths:**
- Line 352-367: Pipeline timeout check can raise and would prevent lines 369-374 from executing

**Impact:** Medium - The `_handle_stage_exception()` calls `record_provider_failure(provider_id, model, stage)` with potentially `None` values, which could cause issues in the circuit breaker/metrics.

### 2. `retry_stuck` Query Missing `SELECTING` Status
**Location:** `tasks/retry.py` lines 118-132

```python
stuck = (
    Article.query.filter(
        Article.pipeline_status.in_(
            [
                PipelineStatus.RESEARCHING,
                PipelineStatus.WRITING,
                PipelineStatus.EDITING,
                PipelineStatus.PENDING,
            ],
        ),
        Article.updated_at < soft_cutoff,
    )
    ...
)
```

**Issue:** Missing `PipelineStatus.SELECTING` from the stuck article query. Articles stuck in `selecting` status would not be retried.

**Recommendation:** Add `PipelineStatus.SELECTING` to the filter list.

---

## Layer Violations

### No Layer Violations Found

The tasks module correctly follows the architecture layering:
- Tasks import from `services` layer (allowed - tasks are orchestrators)
- Tasks do NOT import from `adapters` layer
- Services are used for business logic, not adapters

**Verified imports in tasks:**
- `tasks/crawl.py` - imports from `services.crawling`, `services.task_security` ✓
- `tasks/extract.py` - imports from `services.content_extractor`, `services.article`, `services.url` ✓
- `tasks/select.py` - imports from `services.llm`, `services.config_unified` ✓
- `tasks/research.py` - imports from `services.subagent`, `services.search`, `services.researcher` ✓
- `tasks/write.py` - imports from `services.writer`, `services.trend_memory` ✓
- `tasks/edit.py` - imports from `services.editor`, `services.article_validation`, `services.subagent` ✓
- `tasks/newsletter.py` - imports from `services.email`, `services.newsletter`, `services.webhooks` ✓
- `tasks/pipeline.py` - imports from `services.llm`, `services.limiter`, `services.pipeline_*` ✓

---

## Additional Notes

### Rate Limiter Release Pattern
The rate limiter release in `run_stage()` (line 436) correctly uses the `provider_id` returned from `_run_stage_core`:
```python
limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```

This matches the AGENTS.md note: "Use `provider_id` from `_try_stage_work` - the model is now correct."

### Error Response Convention
All task files correctly document the error response convention in comments:
```python
# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results
```

### Task Security
All tasks properly use `verify_task()` decorator at entry points:
- `run_all_sources`, `crawl_source`
- `select_article`, `research_article`, `write_article`, `edit_article`
- `generate_daily_newsletters`, `publish_scheduled_articles`
- `retry_stuck`, `cleanup_*`, `backfill_embeddings`
- `dispatch_webhook_task`

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 14 |
| Discrepancies | 2 |
| Improvement Recommendations | 3 |
| Bugs Found | 2 |
| Layer Violations | 0 |

**Overall Assessment:** The tasks module implementation closely matches the architecture documentation. The two bugs found are medium severity and should be fixed. The discrepancies are minor and may represent intentional optimizations over the documented behavior.

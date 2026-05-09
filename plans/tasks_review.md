# Tasks Architecture Review Plan

## Verified Claims

### File Inventory (Confirmed)
- `crawl.py`: `run_all_sources`, `crawl_source`, `aggregate_crawl_results` - all exist
- `extract.py`: `process_item` - exists with correct signature and lifecycle
- `select.py`: `select_article` - exists with score threshold 6 confirmed at line 126
- `research.py`: `research_article` - exists with web search + context workflow
- `write.py`: `write_article` - exists with Smart Brevity format (200-400 words target)
- `edit.py`: `edit_article` - exists with `_assign_tags()`, `validate_and_raise()`, `_post_finalize_article()`
- `newsletter.py`: `generate_daily_newsletters` - exists with executive summary (3-stage LLM), main+topic newsletters, batch=500 confirmed at line 85
- `scheduler.py`: `publish_scheduled_articles` - exists, runs every 5 min via Beat
- `cleanup.py`: Multiple tasks exist matching schedule
- `embeddings.py`: `backfill_embeddings` - exists, runs daily at 2 AM
- `pipeline.py`: Contains `run_stage()`, `_transition_article_status()`, `_assign_tags()`, `_log_pipeline()`
- `retry.py`: `retry_stuck` - exists with dead-letter/degrade/retry logic
- `subscribers.py`: `cleanup_inactive_subscribers` - exists, runs daily at 1 AM
- `webhook.py`: `dispatch_webhook_task` - exists

### Pipeline Stage States (Confirmed)
Valid transitions in `constants.py`:
- `PENDING -> RESEARCHING, REVIEW`
- `RESEARCHING -> WRITING, FAILED`
- `WRITING -> EDITING, FAILED`
- `EDITING -> REVIEW, DONE, FAILED`
- `REVIEW -> DONE, FAILED`

Stage status mapping via `STAGE_STATUS_MAP` confirmed in `constants.py:72-87`.

### run_stage Helper (Confirmed)
`tasks/pipeline.py:389-442` implements:
- Distributed locking via Redis
- Stage lock acquisition/release in finally block
- Limiter acquisition/release in finally block
- Pipeline timeout checking
- Soft time limit handling
- Circuit breaker handling
- Error handling with degradation path

### Rate Limiting (Confirmed)
`services/limiter.py`:
- `ModelLimiter.acquire()` / `ModelLimiter.release()` pattern
- Uses Redis pubsub for blocking wait with timeout
- `cleanup_stale_slots()` scans for stale keys with TTL < 60s
- Release in finally block confirmed in `run_stage()`

### Celery Beat Schedule (Confirmed)
`config.py:146-203` matches architecture doc:
- `run-all-sources`: every 30 min
- `retry-stuck-articles`: every 60 min
- `generate-newsletters`: 8:00 AM ET
- `cleanup-old-logs`: Daily 3 AM
- `consolidate-trend-memory`: Daily 3:30 AM
- `purge-trend-memory`: Daily 3:45 AM
- `cleanup-old-versions`: Daily 3:45 AM
- `cleanup-expired-verifications`: Every 15 min
- `publish-scheduled-articles`: Every 5 min
- `cleanup-stale-limiter-slots`: Every 5 min
- `retry-failed-newsletter-deliveries`: Every 2 hours
- `recalculate-impact-scores`: Daily 4:00 AM
- `cleanup-inactive-subscribers`: Daily 1:00 AM
- `backfill-embeddings`: Daily 2:00 AM

### Degradation Path (Confirmed)
`_degrade_and_advance()` in `tasks/pipeline.py:36-71` handles:
- select failure -> auto-select with score 6, transition to researching
- research failure -> degrade_stage to writing
- write failure -> degrade_stage to editing
- edit failure -> finalize with fallback

### Newsletter Idempotency (Confirmed)
`_generate_daily_newsletters_core()` in `tasks/newsletter.py:412-469`:
- Lock acquisition with `_check_newsletter_lock()`
- Idempotency key set after successful completion

---

## Discrepancies

### 1. Stage Transition Flow Mismatch [MEDIUM]
**Architecture doc says:**
```
pending -> select -> research -> write -> edit -> done
```

**Actual code in `constants.py:50-58`:**
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
...
```

Articles go from `PENDING` directly to `RESEARCHING` (bypassing `SELECT`).

The `STAGE_STATUS_MAP` shows `"pending": "select"` but the actual status constants use `"researching"` not `"select"`. The stage names in the architecture (select, research, write, edit) don't directly map to status constants (pending, researching, writing, editing).

### 2. Newsletter Generation Uses group() Without Callback [LOW]
**Architecture doc says:** Uses chord for barrier + callback
**Actual code in `newsletter.py:349-350`:**
```python
job = group(task_signatures)
job.apply_async()
```
Uses `group` with fire-and-forget `apply_async()` instead of `chord` with a callback. No barrier synchronization for newsletter generation.

### 3. Degradation Path Routing Mismatch [MEDIUM]
**Architecture doc says:** `select -> research -> write -> edit -> review -> done`

**Actual code:** When `select` stage fails and degrades, it sets `pipeline_status = "researching"` directly (line 56 in `_degrade_and_advance`), skipping the `select` stage entirely on retry. This is semantically correct but contradicts the linear flow in the diagram.

---

## Improvement Recommendations

### 1. [HIGH] Document Actual Stage Flow
The architecture doc's stage transition diagram and table don't match the actual code. Either:
- Update the diagram to show PENDING -> RESEARCHING (skipping SELECT)
- Or ensure the actual pipeline uses the named stages consistently

### 2. [HIGH] Clarify Stage vs Status Naming
The architecture uses "select", "research", "write", "edit" as stage names, but:
- Status constants are: pending, researching, writing, editing
- STAGE_STATUS_MAP maps stage names to statuses

This creates confusion. Standardize terminology.

### 3. [MEDIUM] Use chord with Callback for Newsletter Generation
The newsletter generation at `newsletter.py:349` should use `chord` with a callback task to:
- Properly synchronize parallel topic newsletter generation
- Handle errors aggregatedly
- Update PipelineRun status when all complete

### 4. [MEDIUM] Add Missing Task in Beat Schedule Documentation
`cleanup-inactive-subscribers` is in the beat schedule at 1:00 AM but not documented in the architecture table.

### 5. [LOW] Add `aggregate_crawl_results` to Documentation
The chord callback `aggregate_crawl_results` (crawl.py:215) should be documented since it handles result aggregation after parallel crawling.

### 6. [LOW] Document `retry_failed_newsletter_deliveries` Task
This task is in the beat schedule (every 2 hours) but not mentioned in the architecture doc's file inventory.

---

## Bugs Found

### 1. [HIGH] Model Limiter Release Uses `None` Model After Exception
**File:** `tasks/pipeline.py:436`
```python
limiter.release(rc.provider, model if model is not None else None, rc.timeout_seconds)
```

When `_run_stage_core` fails before assigning model (e.g., article not found), `model` is `None` and `provider_id` may also be `None`. The limiter is released with `None` model, which could cause incorrect slot tracking in `services/limiter.py`.

**Fix needed:** Track which provider/model was actually acquired and release that specific slot.

### 2. [MEDIUM] `idempotency_key` Variable Scope Issue
**File:** `tasks/newsletter.py:430`
```python
redis_client.setex(idempotency_key, 86400 * 2, "1")
```

The `idempotency_key` is defined in `_generate_daily_newsletters_core` at line 381 but used at line 430. However, this is within the same function so scope is correct. This is NOT a bug - AGENTS.md mentioned it as a pattern, and it's correctly implemented.

### 3. [LOW] `provider_id` May Be `None` When Recorded in Exception Handler
**File:** `tasks/pipeline.py:269`
```python
if provider_id:
    record_provider_failure(provider_id, model, stage)
```

If `_get_provider_for_stage()` succeeds but `_try_stage_work()` fails before any provider is tried, `provider_id` from `_run_stage_core` will be passed but may not reflect the actual failed provider. The `provider_id` returned is from the first provider in the chain, not the one that actually failed if fallback occurred.

---

## Layer Violations

### 1. [LOW] `tasks/pipeline.py` Imports from `services.pipeline_degradation`
**File:** `tasks/pipeline.py:26-27`
```python
from services.pipeline_degradation import (
    finalize_article as _finalize,
)
```

`tasks/pipeline.py` is in the `tasks/` package (task layer) but imports from `services/` for business logic (`finalize_article`). While this is a utility module, it creates a dependency where task code depends on service implementation details.

### 2. [LOW] `tasks/pipeline.py` Imports from `services.pipeline_failure`
**File:** `tasks/pipeline.py:28`
```python
from services.pipeline_failure import handle_stage_failure as _handle_stage_failure
```

Same issue - task utility module depends on service layer for core business logic.

### 3. [LOW] `tasks/extract.py` Imports from `services.article`
**File:** `tasks/extract.py:121`
```python
from services.article import find_duplicate_titles
```

Directly in task code (not pipeline utils), importing from `services.article`. This is a cross-layer dependency for deduplication logic.

---

## Summary

The architecture document is mostly accurate but has several areas needing clarification:
1. **Critical**: Stage transition flow doesn't match actual code - documents show `pending -> select` but code goes `pending -> researching`
2. **High**: Limiter release with potentially `None` model is a latent bug
3. **Medium**: Newsletter uses `group()` not `chord()` as documented
4. **Low**: Layer violations exist where tasks import from services directly

The core `run_stage()` helper implementation is correct and well-implemented. Rate limiting is properly integrated with finally-block release patterns.

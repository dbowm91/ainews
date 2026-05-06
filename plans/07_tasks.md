# Architecture Review: `architecture/tasks.md` vs Codebase

## Verification Results

### VERIFIED Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| **All described task files exist** | VERIFIED | `tasks/crawl.py`, `tasks/extract.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `tasks/newsletter.py`, `tasks/scheduler.py`, `tasks/cleanup.py`, `tasks/embeddings.py` all exist |
| **All described tasks exist** | VERIFIED | `run_all_sources`, `process_item`, `select_article`, `research_article`, `write_article`, `edit_article`, `generate_daily_newsletters`, `publish_scheduled_articles`, `backfill_embeddings` all implemented as `@shared_task` functions |
| **Pipeline stages match diagram** | VERIFIED | `pending -> select -> research -> write -> edit -> done` flow confirmed in code. `_STAGE_TASKS` in `services/pipeline_utils.py` correctly maps statuses to task modules |
| **Degradation path** | VERIFIED | When a stage is disabled, `run_stage()` calls `_handle_disabled()` which dispatches directly to `skip_next` (e.g., `review`) without running the actual stage, implementing `select -> review` degradation path |
| **run_stage helper exists** | VERIFIED | `tasks/pipeline.py` defines `run_stage()` with standard lifecycle: lock acquisition, stage status update, work execution, transition, lock release in `finally` block |
| **Rate limiting** | VERIFIED | `services/limiter.py` implements `ModelLimiter` with acquire/release; `run_stage()` acquires limiter slot before processing and releases in `finally` block |
| **Cleanup task** | VERIFIED | `tasks/cleanup.py` has `cleanup_old_pipeline_logs` among many other cleanup tasks |

### DISCREPANCIES

| Issue | Severity | Description |
|-------|----------|-------------|
| **Task naming inconsistency** | LOW | `process_item` task is in `tasks/extract.py` but doc claims it belongs to "extract" stage. The actual task function is named `process_item` and correctly dispatches to `select_article` afterward |
| **Schedule documentation incomplete** | MEDIUM | `architecture/tasks.md` only lists 5 scheduled tasks, but `config.py` `get_beat_schedule()` defines 14 tasks including `retry-stuck-articles`, `consolidate-trend-memory`, `purge-trend-memory`, `cleanup-old-versions`, `cleanup-expired-verifications`, `cleanup-stale-limiter-slots`, `retry-failed-newsletter-deliveries`, `recalculate-impact-scores`, `cleanup-inactive-subscribers`, `backfill-embeddings` |
| **backfill_embeddings schedule mismatch** | MEDIUM | Doc says "Weekly" but actual schedule is `crontab(hour=2, minute=0)` (daily at 2 AM) per `config.py` line 201 |
| **cleanup_old_logs schedule** | MEDIUM | Doc says "Daily 3 AM" but `pipeline.yaml` schedule uses `cleanup_old_logs_hour: 3` which translates to `crontab(hour=3, minute=0)` - this IS 3 AM so VERIFIED actually. Wait - rechecking... `cleanup_old_logs_hour: 3` -> `crontab(hour=3, minute=0)` = 3 AM daily. Doc says "Daily 3 AM" - MATCHES. |

---

## Bug Findings

### CRITICAL
None identified.

### HIGH

**Limiter release uses `model=None` after failure in early return**

- **File**: `tasks/pipeline.py` lines 414-417
- **Location**:
```python
if not lock_acquired:
    if limiter is not None:
        limiter.release(rc.provider, None, rc.timeout_seconds)
    logger.info("Stage %s already running for article %s, skipping", trace_id, stage, article_id)
    return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```
- **Issue**: When stage lock cannot be acquired, the limiter slot is released with `model=None` instead of the actual model that was acquired. The `limiter.release()` method uses the key `ainews:llm:{provider_id}:{model}`, so releasing with `model=None` creates a different key (`...:None`) than the one used during acquire (`...:qwen3:8b`), causing the slot to not actually be released.
- **Impact**: Slot leak until TTL expires (default 300s). This could cause artificial rate limiting.
- **Fix**: Change `limiter.release(rc.provider, None, rc.timeout_seconds)` to `limiter.release(rc.provider, model, rc.timeout_seconds)` but `model` is not yet set at this point. Better fix: store the acquired model or change the release logic to use just the provider when model is unknown.

### MEDIUM

**1. Stage lock released on soft timeout before failure handling completes**

- **File**: `tasks/pipeline.py` lines 425-427
- **Location**: In the `except SoftTimeLimitExceeded` block, `_handle_soft_timeout_module()` is called, then the exception is re-raised. The `finally` block releases the lock immediately. However, `_handle_soft_timeout_module()` updates `retry_count` and `total_retries` on the article but does NOT commit - the re-raise causes the caller to potentially retry which may hit the same timeout.
- **Issue**: The article's retry state is updated in `_handle_soft_timeout_module()` but the `SoftTimeLimitExceeded` is then re-raised for Celery retry. The article state is saved but the task is immediately retried without any additional delay.
- **Fix**: Consider adding a small delay before retry or using `retry()` with a countdown on soft timeout.

**2. `_dispatch_next` status mapping incomplete for "review" status**

- **File**: `services/pipeline_utils.py` lines 10-18
- **Issue**: `_STAGE_TASKS` does not have an entry for `review` status. If an article in `review` status needs to be re-dispatched (e.g., after manual editing), `_dispatch_next` will silently do nothing because `status not in _STAGE_TASKS`.
- **Impact**: Manual review flow may break if re-dispatch is needed.
- **Fix**: Add `"review": ("tasks.edit", "edit_article")` or appropriate mapping to `_STAGE_TASKS`.

**3. `_degrade_and_advance` calls `_log_pipeline` with wrong argument order**

- **File**: `tasks/pipeline.py` line 60
- **Location**: `_log_pipeline(failed_stage, article.id, run_id, "degraded_to_research")` - but `_log_pipeline` signature is `_log_pipeline(run_id, stage, level, message, *args, article_id=None)`. Arguments are in wrong order.
- **Impact**: Logged messages will have incorrect data but no runtime error since it's just string formatting.
- **Fix**: Change to `_log_pipeline(run_id, failed_stage, "info", "degraded_to_research", article_id=article.id)`.

---

## Improvement Opportunities

### 1. Missing `cleanup_old_logs` in architecture/tasks.md
The document should list all cleanup tasks including:
- `cleanup_old_pipeline_logs` - deletes logs > 30 days (daily 3 AM)
- `cleanup_expired_verifications` - deletes unverified expired subscribers (every 15 min)
- `cleanup_stale_limiter_slots` - cleans up leaked limiter slots (every 5 min)
- `consolidate_trend_memory` - merges low-importance entries (3:30 AM)
- `purge_trend_memory` - removes expired trend memory entries (3:45 AM)
- `cleanup_old_article_versions` - deletes article versions > 90 days (3:45 AM)
- `cleanup_inactive_subscribers` - (hourly)
- `recalculate_impact_scores` - updates impact scores based on engagement (4 AM)

### 2. Document `retry_stuck` task
The `tasks/retry.py` `retry_stuck` task is missing from the architecture document. It runs every 60 minutes to retry articles that are "stuck" in a stage.

### 3. Document `retry_failed_newsletter_deliveries` task
Missing from architecture - runs every 2 hours to retry newsletter deliveries that failed with transient SMTP errors.

### 4. Celery beat schedule table is incomplete
Should list all 14 scheduled tasks, not just 5.

### 5. Missing degradation transition documentation
The architecture shows "review" as a fallback path but doesn't document:
- What triggers review (low confidence selection, quality gate failures, validation failures)
- How articles get from review to done (manual intervention via `publish_scheduled_articles` or admin API)

---

## Action Items

### HIGH Priority

- [ ] **Fix limiter release on early return** (`tasks/pipeline.py` line 416): Change `limiter.release(rc.provider, None, rc.timeout_seconds)` to properly release the slot. Since model is not yet available at that point, either store the model from the provider chain lookup, or release using just the provider key. The simplest fix is to defer the early return until after we have the model, or store the provider/model from `_acquire_stage_resources`.

### MEDIUM Priority

- [ ] **Fix `_degrade_and_advance` log call** (`tasks/pipeline.py` line 60): Correct argument order to `_log_pipeline(run_id, failed_stage, "info", "degraded_to_research", article_id=article.id)`

- [ ] **Add `review` to `_STAGE_TASKS`** (`services/pipeline_utils.py`): Add `"review": ("tasks.edit", "edit_article")` to handle re-dispatch of articles in review status

- [ ] **Update `architecture/tasks.md`**: Expand Celery beat schedule table to include all 14 scheduled tasks

- [ ] **Update `architecture/tasks.md`**: Add documentation for `retry_stuck`, `retry_failed_newsletter_deliveries`, and other missing cleanup tasks

- [ ] **Update `architecture/tasks.md`**: Change "Weekly" for `backfill_embeddings` to "Daily at 2 AM" to match actual schedule

### LOW Priority

- [ ] **Update `architecture/tasks.md`**: Add section documenting the degradation path more thoroughly

- [ ] **Update `architecture/tasks.md`**: Document what triggers `review` status and how articles move from review to done

---

## Summary

The tasks module architecture is fundamentally sound and well-implemented. All described files and tasks exist, the pipeline stages match the documentation, and the `run_stage` helper provides consistent lifecycle management. The main issues are:

1. One actual bug (limiter release with `None` model) that could cause slot leaks
2. Several log call argument order issues that produce incorrect log output  
3. Documentation that is incomplete (only documents 5 of 14 scheduled tasks)
4. Some missing task documentation (`retry_stuck`, etc.)

The rate limiting implementation is correct - slots are always released in the `finally` block, and the `cleanup_stale_limiter_slots` task provides a safety net for crash scenarios.

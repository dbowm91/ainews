# Architecture Review: `architecture/tasks.md` vs Codebase
## Review Date: 2026-05-07 | Reviewer: explore agent

---

## 1. Executive Summary

The `architecture/tasks.md` document describes a Celery-based newsletter pipeline with 10 task files and 5 scheduled tasks. Verification against the codebase reveals:

- **All described files and tasks exist and are correctly implemented**
- **Pipeline stage transitions match the documented diagram**
- **`run_stage()` helper provides consistent lifecycle management**
- **Rate limiting with limiter slot acquisition/release is properly implemented**

**Critical issues found**: 1 bug (limiter slot leak), 2 documentation gaps, 1 potential incorrect log call argument order.

---

## 2. File Inventory Verification

| File | Task | Doc Claim | Actual Implementation | Status |
|------|------|-----------|---------------------|--------|
| `crawl.py` | `run_all_sources` | Stage: `crawl` | `run_all_sources` + `crawl_source` + `aggregate_crawl_results` | VERIFIED |
| `extract.py` | `process_item` | Stage: `extract` | `process_item` with `_extract_content_if_needed`, `_find_duplicate_article`, `_create_article_record` | VERIFIED |
| `select.py` | `select_article` | Stage: `select` | `select_article` with `_assign_experiment_group` | VERIFIED |
| `research.py` | `research_article` | Stage: `research` | `research_article` with web search, context gathering, quality gate | VERIFIED |
| `write.py` | `write_article` | Stage: `write` | `write_article` with Smart Brevity format, quality gate | VERIFIED |
| `edit.py` | `edit_article` | Stage: `edit` | `edit_article` with contextualization, tag assignment, validation | VERIFIED |
| `newsletter.py` | `generate_daily_newsletters` | Stage: `newsletter` | `generate_daily_newsletters` + `send_single_email` + `retry_failed_newsletter_deliveries` | VERIFIED |
| `scheduler.py` | `publish_scheduled_articles` | Stage: `publish` | `publish_scheduled_articles` | VERIFIED |
| `cleanup.py` | Various | - | 8 cleanup tasks (see Section 5) | VERIFIED |
| `embeddings.py` | `backfill_embeddings` | Stage: `embeddings` | `backfill_embeddings` | VERIFIED |
| `retry.py` | `retry_stuck` | Not in doc | `retry_stuck` (runs hourly, retries/dead-letters stuck articles) | **UNDOCUMENTED** |
| `webhook.py` | `dispatch_webhook_task` | Not in doc | Async webhook delivery task | **UNDOCUMENTED** |
| `subscribers.py` | `cleanup_inactive_subscribers` | Not in doc | Daily subscriber cleanup | **UNDOCUMENTED** |

---

## 3. Pipeline Stage Transitions Verification

### Doc Claim (lines 40-47):
```
pending -> select -> research -> write -> edit -> done
           fail    -> fail      -> fail   -> fail -> review (manual)
```

### Actual Implementation:

| Current Status | Next (success) | Next (review) | Next (fail) | Implementation |
|----------------|---------------|---------------|-------------|----------------|
| `pending` | `selecting` | - | `failed` | `_dispatch_next` dispatches to `select_article` |
| `selecting` | `researching` | `review` (low confidence) | `failed` | `select_article` work() transitions based on score/confidence |
| `researching` | `writing` | `review` (degenerate brief) | `failed` | `_handle_quality_gate_and_transition` |
| `writing` | `editing` | `review` (degenerate article) | `failed` | `_is_degenerate_write` quality gate |
| `editing` | `done` | `review` (validation failed) | `failed` | `_handle_validation_and_routing` |
| `review` | (manual/admin) | - | `failed` | `publish_scheduled_articles` can auto-publish |

**Status**: VERIFIED with one caveat - the `_STAGE_TASKS` dict in `services/pipeline_utils.py` (lines 10-19) maps statuses to task modules but does NOT include `review` status. This means if an article in `review` needs re-dispatch, `_dispatch_next` will silently do nothing.

---

## 4. run_stage Helper Verification

### Doc Claim (lines 133-145):
```python
def run_stage(task, article_id: int, stage: str, next_stage: str, task_func):
    """Standard stage runner with locking and error handling"""
    # 1. Acquire stage lock (prevents duplicate processing)
    # 2. Update article status to stage
    # 3. Execute task_func
    # 4. On success: transition to next_stage
    # 5. On failure: handle_retry() or mark_failed()
    # 6. Release stage lock in finally block
```

### Actual Implementation (`tasks/pipeline.py` lines 389-440):

| Doc Step | Actual Code | Status |
|----------|-------------|--------|
| 1. Acquire stage lock | Lines 413: `_acquire_stage_resources()` -> `_acquire_stage_lock()` | VERIFIED |
| 2. Update article status | Line 369 (via `_run_stage_core`): `_transition_article_status()` called in work() | VERIFIED |
| 3. Execute task_func | Line 374: `_try_stage_work()` -> `work_fn()` | VERIFIED |
| 4. On success: transition | Lines 376-384 in `_run_stage_core`: commit + `record_stage_result` | VERIFIED |
| 5. On failure: handle_retry/mark_failed | Lines 264-284: `_handle_stage_exception()` calls `_handle_stage_failure()` for degradation | VERIFIED |
| 6. Release lock in finally | Lines 432-440: `finally` block calls `limiter.release()` and `release_lock()` | VERIFIED |

**Additional verification**:
- Limiter acquired at line 308: `_check_stage_limiter()`
- Limiter released in finally at line 433: `limiter.release()`
- Lock released in finally at line 437-439: `release_lock()`

**IMPORTANT BUG FOUND** at lines 414-417:
```python
if not lock_acquired:
    if limiter is not None:
        limiter.release(rc.provider, None, rc.timeout_seconds)  # BUG: model=None
    logger.info("Stage %s already running...")
    return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```

The limiter slot is released with `model=None` instead of the actual model. The limiter key is `ainews:llm:{provider_id}:{model}`, so releasing with `None` creates a different key than the one used during acquire (`...:qwen3:8b`), meaning the actual slot is NOT released - it just expires via TTL.

---

## 5. Scheduler / Celery Beat Schedule

### Doc Claim (lines 159-168):
| Task | Schedule | Description |
|------|----------|-------------|
| `run_all_sources` | Every 30 min | Crawl all sources |
| `generate_daily_newsletters` | 8:00 AM ET | Generate newsletters |
| `publish_scheduled_articles` | Every 5 min | Check scheduled publishes |
| `cleanup_old_logs` | Daily 3 AM | Clean old pipeline logs |
| `backfill_embeddings` | Weekly | Update embeddings |

### Actual Schedule (from `config.py:get_beat_schedule()` lines 146-203):

| Task | Schedule | Match |
|------|----------|-------|
| `run-all-sources` | Every 30 min (from `crawl_interval_minutes`) | VERIFIED |
| `generate-newsletters` | 8:00 AM (from `generate_newsletters_hour: 8`) | VERIFIED |
| `publish-scheduled-articles` | Every 5 min (from `publish_scheduled_interval_minutes: 5`) | VERIFIED |
| `cleanup-old-logs` | Daily 3 AM (from `cleanup_old_logs_hour: 3`) | VERIFIED |
| `backfill-embeddings` | **Daily at 2 AM** (not weekly!) | **DISCREPANCY** |
| `retry-stuck-articles` | Every 60 min | **UNDOCUMENTED** |
| `cleanup-expired-verifications` | Every 15 min | **UNDOCUMENTED** |
| `cleanup-stale-limiter-slots` | Every 5 min | **UNDOCUMENTED** |
| `retry-failed-newsletter-deliveries` | Every 2 hours | **UNDOCUMENTED** |
| `recalculate-impact-scores` | Daily 4 AM | **UNDOCUMENTED** |
| `cleanup-inactive-subscribers` | Daily 1 AM | **UNDOCUMENTED** |
| `consolidate-trend-memory` | Daily 3:30 AM | **UNDOCUMENTED** |
| `purge-trend-memory` | Daily 3:45 AM | **UNDOCUMENTED** |
| `cleanup-old-versions` | Daily 3:45 AM | **UNDOCUMENTED** |

**Discrepancy**: Doc says `backfill_embeddings` is "Weekly" but actual schedule is `crontab(hour=2, minute=0)` - daily at 2 AM.

---

## 6. Rate Limiting Verification

### Doc Claim (lines 169-175):
- LLM slots: Configured per provider (default: 10 concurrent)
- Source slots: Per-source rate limiting
- Release in finally: Always release acquired slots

### Actual Implementation:

| Component | Location | Status |
|-----------|----------|--------|
| LLM limiter | `services/limiter.py` - `ModelLimiter` class | VERIFIED |
| acquire() with timeout/poll | `limiter.py` lines 39-93 | VERIFIED |
| release() with DECR script | `limiter.py` lines 95-110 | VERIFIED |
| Limiter slot acquired in run_stage | `pipeline.py` line 308 | VERIFIED |
| Limiter released in finally | `pipeline.py` lines 433-434 | VERIFIED |
| Source rate limiting | `crawl.py` lines 51-82 (crawl lock) | VERIFIED |

**BUG**: Early return when lock not acquired (line 416) releases limiter with `model=None` instead of actual model, causing slot leak.

---

## 7. Degradation Path Verification

### Doc Claim (lines 147-155):
When full pipeline is disabled, articles follow: `select -> research -> write -> edit -> review -> done`

### Actual Implementation:

1. **When stage disabled** (`_handle_disabled()` at `pipeline.py` lines 296-303):
   - If `skip_next == "finalize"`: calls `_finalize(article_id)` directly
   - Otherwise: dispatches to `skip_next` status (e.g., `review`)

2. **Degradation on failure** (`_degrade_and_advance()` at `pipeline.py` lines 36-71):
   - `select` failure -> sets `selector_result` to auto-pass, transitions to `researching`
   - `research` failure -> `degrade_stage(article, "writing")`
   - `write` failure -> `degrade_stage(article, "editing")`
   - `edit` failure -> `_finalize(article.id)` (finalize with fallback)

**BUG FOUND** at line 60:
```python
_log_pipeline(failed_stage, article.id, run_id, "degraded_to_research")
```
But `_log_pipeline` signature is `_log_pipeline(run_id, stage, level, message, *args, article_id=None)`. Arguments are in wrong order. This produces garbled log output but no runtime error.

---

## 8. Additional Tasks Not Documented

### 8.1 `retry_stuck` (`tasks/retry.py`)
- **Purpose**: Retry or dead-letter articles stuck in pipeline stages
- **Schedule**: Every 60 minutes
- **Logic**:
  - Articles stuck > 15 min: classify as `dead_letter`, `degrade`, or `retry`
  - `dead_letter`: mark as `failed` with fallback draft
  - `degrade`: advance to next stage with degraded quality
  - `retry`: increment retry_count and re-dispatch current stage

### 8.2 `retry_failed_newsletter_deliveries` (`tasks/newsletter.py` lines 503-585)
- **Purpose**: Re-attempt delivery for newsletters with non-null `error_message`
- **Schedule**: Every 2 hours

### 8.3 `dispatch_webhook_task` (`tasks/webhook.py`)
- **Purpose**: Async webhook event delivery with HMAC signing

### 8.4 `cleanup_inactive_subscribers` (`tasks/subscribers.py`)
- **Purpose**: Flag/remove inactive subscribers based on bounce count or inactivity
- **Schedule**: Daily at 1 AM

---

## 9. Cleanup Tasks in `tasks/cleanup.py`

| Task | Schedule | Description |
|------|----------|-------------|
| `cleanup_old_pipeline_logs` | Daily 3 AM | Delete logs > 30 days, batch 10k |
| `cleanup_expired_verifications` | Every 15 min | Delete unverified expired subscribers |
| `cleanup_stale_limiter_slots` | Every 5 min | Clean up leaked Redis limiter slots |
| `consolidate_trend_memory` | Daily 3:30 AM | Merge low-importance with high-importance entries |
| `recalculate_impact_scores` | Daily 4 AM | Update impact scores based on engagement metrics |
| `purge_trend_memory` | Daily 3:45 AM | Remove expired trend memory entries |
| `cleanup_old_article_versions` | Daily 3:45 AM | Delete versions > 90 days (configurable) |

---

## 10. Critical Bug: Limiter Slot Leak on Early Return

### Location
`tasks/pipeline.py` lines 414-417

### Code
```python
if not lock_acquired:
    if limiter is not None:
        limiter.release(rc.provider, None, rc.timeout_seconds)  # BUG: model=None
    logger.info("TraceID=%s: Stage %s already running for article %s, skipping", trace_id, stage, article_id)
    return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```

### Root Cause
When stage lock cannot be acquired (another worker is processing this stage for this article), the code releases the limiter slot with `model=None`. The limiter key is `ainews:llm:{provider_id}:{model}`, so:
- During acquire: key = `ainews:llm:ollama-local:qwen3:8b`
- During release with model=None: key = `ainews:llm:ollama-local:None`

The release script operates on the wrong key, so the actual slot is never released.

### Impact
- Slot leak until TTL expires (default 300 seconds)
- Could cause artificial rate limiting if many articles hit this path
- Particularly problematic during high load when many articles are queued for same stage

### Recommended Fix
```python
if not lock_acquired:
    if limiter is not None:
        # Release using just the provider; model is not yet known at this point
        limiter.release(rc.provider, None, rc.timeout_seconds)
        # But this is wrong - we need to track what was actually acquired
    ...
```

Better approach: store the provider/model that was actually acquired before the lock check, or restructure the early return to happen after we have all resources.

```python
# Alternative fix - track what was actually acquired
limiter, redis_client, lock_acquired = _acquire_stage_resources(...)
if not lock_acquired:
    # Need to know which model was acquired to release correctly
    # Since limiter.acquire() already happened and succeeded, we need to store the result
```

**Note**: The `_acquire_stage_resources` calls `_check_stage_limiter()` which does acquire the slot before checking the lock. So the limiter slot IS acquired. The fix should track the model that was used for the limiter acquisition.

---

## 11. Bug: Incorrect Log Call Argument Order

### Location
`tasks/pipeline.py` line 60 (and similar lines 63, 66)

### Code
```python
_log_pipeline(failed_stage, article.id, run_id, "degraded_to_research")
```

### Expected
```python
_log_pipeline(run_id, failed_stage, "info", "degraded_to_research", article_id=article.id)
```

### Signature
`_log_pipeline(run_id, stage, level, message, *args, article_id=None)`

### Impact
Log messages are garbled but no runtime error.

---

## 12. Bug: Missing `review` Status in `_STAGE_TASKS`

### Location
`services/pipeline_utils.py` lines 10-19

### Code
```python
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "written": ("tasks.edit", "edit_article"),
    "editing": ("tasks.edit", "edit_article"),
    "review": ("tasks.edit", "edit_article"),  # MISSING!
}
```

### Impact
If an article in `review` status needs re-dispatch (e.g., after manual editing via admin API), `_dispatch_next` will silently return without dispatching any task. The article would be stuck in review forever unless manually moved.

### Recommended Fix
Add `"review": ("tasks.edit", "edit_article")` to `_STAGE_TASKS`.

---

## 13. Improvement Recommendations

### HIGH Priority

#### 1. Fix Limiter Slot Leak on Early Return
**File**: `tasks/pipeline.py` lines 414-417

The limiter is acquired before the lock check but released with `model=None` on early return. This causes the slot to not actually be released.

**Fix approach**: Modify `_acquire_stage_resources` to return the model that was used, or restructure to ensure we can release the correct slot on early return.

#### 2. Add `review` to `_STAGE_TASKS`
**File**: `services/pipeline_utils.py`

Prevents silent failure when re-dispatching articles in review status.

#### 3. Fix Incorrect Log Call Arguments
**File**: `tasks/pipeline.py` lines 60, 63, 66

`_log_pipeline` calls have wrong argument order producing garbled output.

### MEDIUM Priority

#### 4. Update `architecture/tasks.md` Celery Beat Schedule
The document only lists 5 scheduled tasks but 14 actually exist. Update to include:
- `retry-stuck-articles` (every 60 min)
- `cleanup-expired-verifications` (every 15 min)
- `cleanup-stale-limiter-slots` (every 5 min)
- `retry-failed-newsletter-deliveries` (every 2 hours)
- `recalculate-impact-scores` (daily 4 AM)
- `cleanup-inactive-subscribers` (daily 1 AM)
- `consolidate-trend-memory` (daily 3:30 AM)
- `purge-trend-memory` (daily 3:45 AM)
- `cleanup-old-versions` (daily 3:45 AM)

#### 5. Update `backfill_embeddings` Schedule in Doc
Change from "Weekly" to "Daily at 2 AM" to match actual schedule in `config.py`.

#### 6. Document Missing Tasks
Add documentation for:
- `retry_stuck` - retry/dead-letter stuck articles
- `retry_failed_newsletter_deliveries` - retry failed newsletter emails
- `dispatch_webhook_task` - async webhook delivery

#### 7. Document Degradation Path Triggers
The doc shows `review` as a fallback but doesn't explain:
- What triggers review (low confidence selection, quality gate failures, validation failures)
- How articles get from review to done (manual intervention, `publish_scheduled_articles`)

### LOW Priority

#### 8. Document Stage Lock Behavior
Add documentation about what happens when stage lock cannot be acquired (skip with reason "stage_locked").

#### 9. Document Rate Limiter Key Format
Helpful for debugging: `ainews:llm:{provider_id}:{model}` with slot counting via Redis INCR/DECR.

---

## 14. Summary of Verified Claims

| Claim | Status |
|-------|--------|
| All 10 described task files exist | VERIFIED |
| All described tasks exist | VERIFIED |
| Pipeline stages match diagram | VERIFIED |
| Degradation path implemented | VERIFIED |
| run_stage helper exists with correct lifecycle | VERIFIED |
| Rate limiting with finally-block release | VERIFIED (with bug) |
| cleanup_old_logs task exists | VERIFIED |
| backfill_embeddings exists | VERIFIED (wrong schedule in doc) |
| Scheduler table in doc is incomplete (5/14) | DISCREPANCY |
| backfill_embeddings "Weekly" schedule is wrong | DISCREPANCY |
| Limiter released with model=None on early return | BUG |
| _log_pipeline called with wrong argument order | BUG |
| review status missing from _STAGE_TASKS | BUG |

---

## 15. Action Items

### Immediate (Critical Bugs)

- [ ] **FIX**: Limiter slot leak in `tasks/pipeline.py` line 416 - release with correct model, not `None`
- [ ] **FIX**: Add `"review": ("tasks.edit", "edit_article")` to `_STAGE_TASKS` in `services/pipeline_utils.py`
- [ ] **FIX**: Correct `_log_pipeline` argument order in `_degrade_and_advance` at `tasks/pipeline.py` lines 60, 63, 66

### Short Term (Documentation)

- [ ] **UPDATE**: `architecture/tasks.md` Celery Beat Schedule - add 9 missing tasks
- [ ] **UPDATE**: `architecture/tasks.md` - change `backfill_embeddings` schedule from "Weekly" to "Daily at 2 AM"
- [ ] **UPDATE**: `architecture/tasks.md` - add documentation for `retry_stuck`, `retry_failed_newsletter_deliveries`, `dispatch_webhook_task`
- [ ] **UPDATE**: `architecture/tasks.md` - document degradation path triggers and review-to-done flow

### Long Term (Architecture)

- [ ] Consider adding monitoring for limiter slot leaks
- [ ] Consider adding task tracing for `aggregate_crawl_results` callback
- [ ] Document the task security (HMAC signing) mechanism

---

*End of review*

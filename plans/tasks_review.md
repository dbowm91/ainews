# Tasks Architecture Review

Based on review of `architecture/tasks.md` against the actual implementation in `tasks/` and related files.

---

## Verified Correct

### 1. File to Stage Mapping
All task files match their documented stage assignments:

| File | Task | Stage | Verified |
|------|------|-------|----------|
| `crawl.py` | `run_all_sources` | `crawl` | Line 269: `def run_all_sources(self, run_id=None):` |
| `extract.py` | `process_item` | `extract` | Line 278: `def process_item(self, ...):` |
| `select.py` | `select_article` | `select` | Line 59: `def select_article(self, article_id: int, run_id=None):` |
| `research.py` | `research_article` | `research` | Line 267: `def research_article(self, article_id: int, run_id=None):` |
| `write.py` | `write_article` | `write` | Line 48: `def write_article(self, article_id: int, run_id=None):` |
| `edit.py` | `edit_article` | `edit` | Line 394: `def edit_article(self, article_id: int, run_id=None):` |
| `newsletter.py` | `generate_daily_newsletters` | `newsletter` | Line 475: `def generate_daily_newsletters(self, dry_run_email=None, run_id=None):` |
| `scheduler.py` | `publish_scheduled_articles` | `publish` | Line 11: `def publish_scheduled_articles(self):` |
| `embeddings.py` | `backfill_embeddings` | `embeddings` | Line 19: `def backfill_embeddings(self, batch_size: int = 50, delay_seconds: float = 0.1):` |

Cleanup tasks in `cleanup.py`:
- `cleanup_old_pipeline_logs` (Line 19)
- `cleanup_expired_verifications` (Line 69)
- `cleanup_stale_limiter_slots` (Line 110)
- `consolidate_trend_memory` (Line 134)
- `recalculate_impact_scores` (Line 171)
- `purge_trend_memory` (Line 237)
- `cleanup_old_article_versions` (Line 268)

### 2. Stage Transition Table
The documented transitions match `constants.py` lines 52-64:

| Current | Next (success) | Next (review) | Next (fail) |
|---------|----------------|--------------|-------------|
| `pending` | `select` | - | `failed` |
| `select` | `research` | `review` | `failed` |
| `research` | `write` | `review` | `failed` |
| `write` | `edit` | `review` | `failed` |
| `edit` | `done` | `review` | `failed` |

**Note**: The actual implementation has additional quality-gate routing to `review` not shown in the table (e.g., research fails `_is_degenerate_research()`, write fails `_is_degenerate_write()`, edit fails validation). This is an **omission in documentation**, not a code bug.

### 3. run_stage Helper Lifecycle
`tasks/pipeline.py` lines 389-442 implement the documented lifecycle correctly:

1. Acquire stage lock (lines 409-420)
2. Update article status to stage (inside `_run_stage_core` via `_transition_article_status`)
3. Execute task_func via `_run_stage_core` (line 425)
4. On success: transition to next_stage (via `_dispatch_next` in work functions)
5. On failure: handle_retry() or mark_failed() (via `_handle_stage_exception`)
6. **Release stage lock in finally block** (lines 434-442)

### 4. Degradation Path
`services/pipeline_degradation.py` `_STAGE_DEGRADE_MAP` (lines 33-55) correctly maps:
- `select` -> `researching`
- `research` -> `writing`
- `write` -> `editing`
- `edit` -> finalization/review

Articles skip select/research and go directly to `review` when degraded.

### 5. Max Retries Configuration
Correctly documented and implemented in `constants.py`:
- `CELERY_TASK_MAX_RETRIES = 3` (line 6) - per task
- `MAX_STAGE_RETRIES = 3` (line 9) - per stage
- `MAX_TOTAL_RETRIES = 10` (line 11) - total budget

All pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES`.

### 6. Rate Limiting Slot Management
In `tasks/pipeline.py` lines 435-436, slots are correctly released in the `finally` block:
```python
finally:
    if limiter is not None:
        limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```
This matches the documented "Release in finally" behavior.

---

## Discrepancies Found

### 1. Quality Gate Routing Not Documented
**Location**: `architecture/tasks.md` stage transition table (lines 41-47)

The transition table shows only basic success/fail paths, but the actual code implements quality-gate routing that can send articles to `review` even on "success":

- `select.py` lines 127-146: Low confidence selections route to `review`
- `research.py` lines 206-231: Degenerate research briefs route to `review`
- `write.py` lines 128-154: Degenerate drafts route to `review`
- `edit.py` lines 161-205: Validation failures route to `review`

**Recommendation**: Update the stage transition table to reflect quality-gate paths.

### 2. Degradation Count Threshold Not Documented
**Location**: `services/pipeline_degradation.py` lines 94, 99-100, 144, 147

When `degradation_count >= 2`, articles are automatically routed to `review` regardless of quality. This behavior is not mentioned in the architecture document.

**Recommendation**: Document that degraded articles that fail a second stage go to `review` automatically.

### 3. backfill_embeddings Missing max_retries in Decorator
**Location**: `tasks/embeddings.py` lines 13-18

```python
@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True,
    soft_time_limit=600, time_limit=660,
    ...
)
def backfill_embeddings(self, batch_size: int = 50, delay_seconds: float = 0.1):
```

Unlike other tasks, `backfill_embeddings` doesn't explicitly set `max_retries=CELERY_TASK_MAX_RETRIES`. However, the task uses `verify_task` security and has proper autoretry configuration, so this is not a critical issue.

**Recommendation**: Add `max_retries=CELERY_TASK_MAX_RETRIES` for consistency with other tasks.

---

## Bugs Identified

### 1. Potential Limiter Release Bug with Early Return
**Location**: `tasks/pipeline.py` lines 416-420

```python
if not lock_acquired:
    if limiter is not None:
        limiter.release(rc.provider, rc.model, rc.timeout_seconds)
    logger.info("TraceID=%s: Stage %s already running for article %s, skipping", trace_id, stage, article_id)
    return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```

When the stage lock cannot be acquired, the limiter is released but with `rc.provider` and `rc.model`. However, `rc.provider` and `rc.model` may have been updated by `_get_provider_for_stage()` at line 413-414. If the stage lock failed because another worker already has it, the provider/model used here is correct.

However, there's a subtle issue: the `limiter.release()` call uses `rc.provider` and `rc.model` (line 418), but these are the resolved provider/model from line 414. The `finally` block at line 435-436 uses `provider_id` and `model` (the local variables set in `run_stage`). This inconsistency could cause incorrect slot release if the early return path is taken.

**Note**: The `cleanup_stale_limiter_slots` task mitigates this by cleaning stale slots every 5 minutes.

**Recommendation**: Verify that `provider_id` and `model` are captured correctly before the early return, or use consistent variable naming.

---

## Improvement Suggestions

### 1. Document run_stage Parameters Accurately
**Location**: `architecture/tasks.md` lines 136-145

The documented signature shows `run_stage(task, article_id: int, stage: str, next_stage: str, task_func)` but actual signature in `tasks/pipeline.py` line 389-398 is:
```python
def run_stage(
    stage: str,
    article_id: int,
    work_fn,
    task_self,
    run_id=None,
    skip_next: str = "finalize",
    retry_countdown: int = 30,
    retry_max: int = 15,
):
```

**Recommendation**: Update documentation to match actual signature.

### 2. Clarify Newsletter Generation Flow
**Location**: `architecture/tasks.md` lines 119-130

The document says newsletter generation uses "3-stage LLM" but doesn't detail the parallel topic newsletter generation implemented in `tasks/newsletter.py`. The actual implementation (lines 330-363) fetches articles for all topics upfront, then dispatches parallel tasks for each topic.

**Recommendation**: Update to reflect parallel generation per topic.

### 3. Add Missing Tasks to Documentation
**Location**: `architecture/tasks.md`

The document lists 10 task files but misses:
- `retry.py` - Contains `retry_stuck` task which is critical for pipeline health
- `subscribers.py` - Contains `cleanup_inactive_subscribers`
- `webhook.py` - Contains `dispatch_webhook_task`

**Recommendation**: Add these to the file inventory table.

---

## Questions for Architecture

### 1. Should degradation_count >= 2 Always Route to Review?
In `services/pipeline_degradation.py` lines 94, 99-100, 144, 147, articles with `degradation_count >= 2` are automatically routed to `review`. This is implemented but not documented. Is this the intended behavior?

### 2. What's the Rationale for backfill_embeddings Not Having Explicit max_retries?
Unlike all other pipeline tasks, `backfill_embeddings` doesn't set `max_retries=CELERY_TASK_MAX_RETRIES`. Is this intentional (e.g., because it's a low-priority background task), or should it be added for consistency?

### 3. Should Stage Transition Documentation Include Quality Gates?
The current stage transition table only shows success/fail paths. Should it be expanded to include quality-gate routing? This would make the documentation more accurate but more complex.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct | 6 |
| Discrepancies Found | 3 |
| Bugs Identified | 1 (minor) |
| Improvement Suggestions | 3 |
| Questions for Architecture | 3 |

**Overall**: The implementation largely matches the architecture document. Most discrepancies are documentation omissions rather than actual bugs. The `run_stage` helper and rate limiting are correctly implemented.

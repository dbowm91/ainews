# Tasks.md Review

**Reviewed:** 2026-05-29
**Document:** `architecture/tasks.md`
**Cross-referenced with:** `plans/plan.md` (no re-flagging of resolved issues)

---

## Verified Claims

| Claim | Status | Evidence |
|-------|--------|---------|
| File inventory (13 task files) | VERIFIED | All files exist in `tasks/` |
| `cleanup_old_pipeline_logs` in cleanup.py | VERIFIED | `tasks/cleanup.py:19` |
| `cleanup_expired_verifications` in cleanup.py | VERIFIED | `tasks/cleanup.py:69` |
| `cleanup_stale_limiter_slots` in cleanup.py | VERIFIED | `tasks/cleanup.py:110` |
| `consolidate_trend_memory` in cleanup.py | VERIFIED | `tasks/cleanup.py:134` |
| `recalculate_impact_scores` in cleanup.py | VERIFIED | `tasks/cleanup.py:171` |
| `purge_trend_memory` in cleanup.py | VERIFIED | `tasks/cleanup.py:237` |
| `cleanup_old_article_versions` in cleanup.py | VERIFIED | `tasks/cleanup.py:268` |
| `cleanup_inactive_subscribers` in subscribers.py | VERIFIED | `tasks/subscribers.py` |
| `dispatch_webhook_task` in webhook.py | VERIFIED | `tasks/webhook.py:13` |
| `retry_stuck` in retry.py | VERIFIED | `tasks/retry.py` |
| `backfill_embeddings` in embeddings.py | VERIFIED | `tasks/embeddings.py` |
| `run_stage()` signature (retry_max=15) | VERIFIED | `tasks/pipeline.py:353-361` |
| `run_stage()` skip_next default "finalize" | VERIFIED | `tasks/pipeline.py:359` |
| `run_stage()` retry_countdown default 30 | VERIFIED | `tasks/pipeline.py:360` |
| `select_article` retry_max=20 | VERIFIED | `tasks/select.py:202` |
| Quality gate: select confidence="low" → review | VERIFIED | `tasks/select.py` |
| Quality gate: research `_is_degenerate_research()` | VERIFIED | Present in `services/researcher.py` |
| Quality gate: write `_is_degenerate_write()` | VERIFIED | Present in `services/writer.py` |
| Quality gate: edit validation fails → review | VERIFIED | `tasks/edit.py` |
| 14 scheduled tasks in beat schedule | VERIFIED | `config.py:get_beat_schedule()` |
| `retry-stuck-articles` at 60 min interval | VERIFIED | `config.py:151-153` |
| `cleanup-old-logs` at 3 AM | VERIFIED | `config.py:159-161` |
| `cleanup-old-versions` at 3:45 AM | VERIFIED | `config.py:171-173` (hour=3, minute=45) |
| `cleanup-expired-verifications` at 15 min | VERIFIED | `config.py:175-177` |
| `publish-scheduled-articles` at 5 min | VERIFIED | `config.py:179-181` |
| `cleanup-stale-limiter-slots` at 5 min | VERIFIED | `config.py:183-185` |
| `retry-failed-newsletter-deliveries` at 2 hours | VERIFIED | `config.py:187-189` |
| `recalculate-impact-scores` at 4 AM | VERIFIED | `config.py:191-193` |
| `cleanup-inactive-subscribers` at 1 AM | VERIFIED | `config.py:195-197` |
| `backfill-embeddings` at 2 AM | VERIFIED | `config.py:199-201` |
| `generate-newsletters` at 8 AM | VERIFIED | `config.py:155-157` |
| `consolidate-trend-memory` at 3:30 AM | VERIFIED | `config.py:163-165` |
| `purge-trend-memory` at 3:45 AM | VERIFIED | `config.py:167-169` |
| `MAX_CONSECUTIVE_FAILURES` is separate from per-stage limits | VERIFIED | `config.py:67` and `constants.py` |
| Rate limiting via `services.limiter` | VERIFIED | `services/limiter.py` |
| Stage lock release in finally block | VERIFIED | `tasks/pipeline.py:400-407` |
| Degradation path: pending → review → done | VERIFIED | `services/pipeline_degradation.py` |
| `retry_stuck` uses `_degrade_and_advance` | VERIFIED | `tasks/retry.py` |

---

## Incorrect Claims

### 1. Selector retry_max=20 exception not documented in general retry description (LOW)

**Location:** `architecture/tasks.md:66`

**Claim:**
```
**Retry Configuration:** All pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES`
from `constants.py` (default: 3, configurable via `CELERY_TASK_MAX_RETRIES` environment variable).
```

**Issue:** This describes the Celery task retry configuration but does not mention that the selector stage uses a different `retry_max` parameter (20) in the `run_stage()` call at `tasks/select.py:202`.

The selector stage's `run_stage()` call:
```python
return run_stage(
    "selector",
    article_id,
    work,
    task_self=self,
    run_id=run_id,
    skip_next=PipelineStatus.RESEARCHING,
    retry_countdown=15,
    retry_max=20,  # <-- Exception: 20 instead of default 15
)
```

This exception is correctly documented in `architecture/pipeline.md:290`:
```
**Exception**: Selector stage uses `retry_max=20` with `retry_countdown=15` for more aggressive selection attempts
```

But `tasks.md` only mentions the Celery-level `max_retries` without noting the selector-specific override at the stage runner level.

**Priority:** LOW (the exception IS documented in pipeline.md)

---

## Bugs Found

None identified.

---

## Improvement Opportunities

### 1. Document selector stage's retry_max=20 exception in tasks.md

**Location:** `architecture/tasks.md:108-117`

The `select_article` task documentation shows the signature but doesn't note the special retry behavior. The selector's more aggressive retry configuration (retry_max=20 vs default 15) should be mentioned.

**Recommendation:** Add a note to the Select task section:
```python
### Select (`select.py`)
...
# Note: Uses retry_max=20 (vs default 15) for more aggressive selection attempts
```

### 2. Clarify "degradation_count >= 2" in degraded flow description

**Location:** `architecture/tasks.md:200`

**Claim:**
```
**Degraded flow:** When stages fail persistently (degradation_count >= 2), articles
bypass remaining stages and go directly to `review` for manual processing.
```

The statement is correct but could be clearer. The degradation_count threshold of 2 means that after 2 stages have failed (not 2 retries of the same stage), the article goes to review. This distinction matters.

**Priority:** LOW

---

## Stale Content

### 1. tasks.md references `services/pipeline_degradation.py:_degrade_and_advance()`

**Location:** `architecture/tasks.md:203`

**Claim:**
```
See `services/pipeline_degradation.py:_degrade_and_advance()` for the public degradation API.
Note: `tasks/pipeline.py` has a local `_degrade_and_advance` for use by `retry.py` (task-layer only).
```

**Issue:** The document mentions a "local `_degrade_and_advance` in `tasks/pipeline.py`". I did not find this function in `tasks/pipeline.py`. The retry task at `tasks/retry.py` uses `degrade_stage()` from `services/pipeline_degradation.py`, not a local function.

Let me verify by searching for `_degrade_and_advance` in tasks/pipeline.py...

Actually, I searched but did not find it. Let me check if this is stale documentation.

Upon re-examination, `tasks/pipeline.py` does not contain `_degrade_and_advance`. The `retry.py` imports and uses `degrade_stage` from `services/pipeline_degradation.py`.

**Priority:** MEDIUM - documentation references code that doesn't exist in stated location

---

## Priority Summary

| Finding | Priority | Type |
|---------|----------|------|
| Stale reference to `_degrade_and_advance` in tasks/pipeline.py | MEDIUM | Stale Content |
| Selector retry_max=20 not in general retry description | LOW | Improvement |
| degradation_count >= 2 could be clearer | LOW | Improvement |

**Overall Assessment:** Document is mostly accurate but contains one stale reference. The selector stage's special retry_max should also be mentioned in the task-level retry documentation for completeness.

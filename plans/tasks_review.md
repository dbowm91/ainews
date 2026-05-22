# Tasks Module Architecture Review

## Summary

The `architecture/tasks.md` document is **largely accurate** with a few discrepancies and one significant bug. The file inventory and pipeline stage documentation are correct. Celery Beat schedule times match actual config. The `run_stage()` helper implementation is accurate, though the document's claim about stage lock release using `provider_id or rc.provider` is important to verify.

---

## Verified Claims

### Accurate

1. **File Inventory** - All files listed in the table exist and implement the described tasks:
   - `crawl.py`: `run_all_sources`, `crawl_source`, `aggregate_crawl_results` ✓
   - `extract.py`: `process_item` ✓
   - `select.py`: `select_article` ✓
   - `research.py`: `research_article` ✓
   - `write.py`: `write_article` ✓
   - `edit.py`: `edit_article` ✓
   - `newsletter.py`: `generate_daily_newsletters`, `send_single_email`, `retry_failed_newsletter_deliveries` ✓
   - `scheduler.py`: `publish_scheduled_articles` ✓
   - `cleanup.py`: All 7 tasks listed ✓
   - `embeddings.py`: `backfill_embeddings` ✓
   - `retry.py`: `retry_stuck` (note: function name is `retry_stuck` not `retry_stuck_articles`) ✓
   - `subscribers.py`: `cleanup_inactive_subscribers` ✓
   - `webhook.py`: `dispatch_webhook_task` ✓

2. **Pipeline Stage Transitions** - Table accurately reflects actual transitions in `services/pipeline_utils.py:_STAGE_TASKS` (lines 10-19).

3. **Quality Gates** - All quality gate conditions correctly implemented:
   - `select`: confidence="low" → review (`tasks/select.py:127-146`) ✓
   - `research`: `_is_degenerate_research()` (`tasks/research.py:13-28`, `206-231`) ✓
   - `write`: `_is_degenerate_write()` (`tasks/write.py:12-27`, `128-154`) ✓
   - `edit`: validation failure (`tasks/edit.py:161-186`) ✓

4. **Celery Beat Schedule** - All schedules match `config.py:get_beat_schedule()`:
   - `run-all-sources`: Every 30 min ✓
   - `retry-stuck-articles`: Every 60 min ✓
   - `generate-newsletters`: 8:00 AM ET ✓
   - `cleanup-old-logs`: Daily 3 AM ✓
   - `consolidate-trend-memory`: Daily 3:30 AM ✓
   - `purge-trend-memory`: Daily 3:45 AM ✓
   - `cleanup-old-versions`: Daily 3:45 AM ✓
   - `cleanup-expired-verifications`: Every 15 min ✓
   - `publish-scheduled-articles`: Every 5 min ✓
   - `cleanup-stale-limiter-slots`: Every 5 min ✓
   - `retry-failed-newsletter-deliveries`: Every 2 hours ✓
   - `recalculate-impact-scores`: Daily 4:00 AM ✓
   - `cleanup-inactive-subscribers`: Daily 1:00 AM ✓
   - `backfill-embeddings`: Daily 2:00 AM ✓

5. **run_stage Helper** - Implementation in `tasks/pipeline.py:353-408` correctly implements the described lifecycle: lock acquisition, status update, task execution, transition, and finally block with lock release.

6. **Rate Limiting** - Uses `services.limiter.ModelLimiter` with proper slot acquisition and release in finally block (`tasks/pipeline.py:401-402`).

7. **Degradation Path** - `pending → review → done` flow works via `_degrade_and_advance()` in `services/pipeline_degradation.py:183-206`.

---

## Discrepancies

### 1. Task Name Mismatch (Low)
**Document says**: `retry_stuck_articles`  
**Actual code**: `retry_stuck` (`tasks/retry.py:79`)  
The document's file inventory says "Retry/dead-letter stuck articles" but the task name in the Scheduler section is `retry-stuck-articles`. The actual task function is named `retry_stuck`, and the beat schedule key is `retry-stuck-articles`. This is a documentation inconsistency but not a bug.

### 2. Missing `_dead_letter` Import Path (HIGH - Bug)
**Document doesn't mention**: `_dead_letter` is defined locally in `tasks/retry.py:206-240`, not imported from `tasks.pipeline`. The document says `tasks/pipeline.py` has a local `_degrade_and_advance` (correct), but the `retry.py` does NOT import `_dead_letter` from `pipeline.py`.

**Actual state**:
- `tasks/retry.py:37` imports from `tasks.pipeline`: `from tasks.pipeline import _dead_letter` - but `_dead_letter` is defined locally at line 206
- This is a **self-import bug** - the function imports itself from the same module

```python
# tasks/retry.py:37
from tasks.pipeline import _dead_letter  # Circular - _dead_letter is defined at line 206 in same file!

# tasks/retry.py:34
def _process_dead_letter(article):
    from tasks.pipeline import _dead_letter  # This imports from same module - line 206 has _dead_letter
    _dead_letter(article)
```

**Bug location**: `tasks/retry.py:34-42`

### 3. `_apply_fallback` Import Path Issue (HIGH - Bug)
**Document doesn't mention**: `_apply_fallback` is in `services/pipeline_degradation.py:74`, not `tasks/pipeline.py`.

```python
# tasks/retry.py:209
from tasks.pipeline import _apply_fallback  # WRONG - should be from services.pipeline_degradation
```

**Actual location**: `services/pipeline_degradation.py:74`

**Bug location**: `tasks/retry.py:209`

### 4. Limiter Release Fallback Claim (Verified Correct)
The document says to use `provider_id or rc.provider` and `model or rc.model` as fallbacks. Looking at `tasks/pipeline.py:402`:
```python
limiter.release(provider_id or rc.provider, model or rc.model, rc.timeout_seconds)
```
This is correctly implemented.

### 5. `aggregate_crawl_results` Not Documented (Low)
The document doesn't list `aggregate_crawl_results` in the file inventory. It is a chord callback task in `crawl.py:215-253` that aggregates results after parallel source crawling. This is an oversight in the document but not a bug.

---

## Bugs Found

### Bug 1: Local Import Creates Module-Level Self-Reference
**File**: `tasks/retry.py:34-42`
**Severity**: HIGH
```python
def _process_dead_letter(article):
    try:
        from tasks.pipeline import _dead_letter  # Imports from same module!
        _dead_letter(article)
        return True
    except Exception:
        ...
```
The `_dead_letter` function is defined locally at line 206 in the same file. The import statement `from tasks.pipeline import _dead_letter` would only work if there's also a `_dead_letter` in `tasks/pipeline.py`, which there isn't. This creates a confusing circular module-level import.

**Fix**: Remove the import statement at line 37 and call `_dead_letter(article)` directly since it's defined in the same scope at line 206.

### Bug 2: Wrong Import Source for `_apply_fallback`
**File**: `tasks/retry.py:209`
**Severity**: HIGH
```python
from tasks.pipeline import _apply_fallback
```
`_apply_fallback` is defined in `services/pipeline_degradation.py:74`. This import would fail at runtime (though may be caught by the bare `except` at line 40).

**Fix**: Change to `from services.pipeline_degradation import _apply_fallback`

---

## Layering Violations

### 1. tasks/retry.py Imports from tasks.pipeline
`tasks/retry.py` is importing from `tasks.pipeline`:
- Line 37: `from tasks.pipeline import _dead_letter`
- Line 209: `from tasks.pipeline import _apply_fallback`

This is acceptable since `retry.py` is part of the tasks layer and `pipeline.py` is in the same layer. However, both `_dead_letter` and `_apply_fallback` are defined locally in `retry.py`, making the imports redundant and confusing.

### 2. tasks/pipeline.py Imports from services.pipeline_degradation
`tasks/pipeline.py:25-28` imports from `services.pipeline_degradation`:
```python
from services.pipeline_degradation import (
    _should_route_to_review,
    finalize_article as _finalize,
)
```
This is a services→services import, which is fine. But `_finalize` is re-exported for use by `tasks/edit.py`.

---

## Recommendations

| Priority | File | Line | Issue |
|----------|------|------|-------|
| HIGH | `tasks/retry.py` | 37 | Remove self-import of `_dead_letter` |
| HIGH | `tasks/retry.py` | 209 | Change import source to `services.pipeline_degradation` |
| MED | `architecture/tasks.md` | - | Document `aggregate_crawl_results` task |
| MED | `architecture/tasks.md` | - | Fix task name `retry-stuck-articles` vs actual `retry_stuck` |
| LOW | `tasks/retry.py` | 11 | Add `verify_task` security check to `retry_stuck` (other tasks have it) |

---

## Action Items

1. **Fix self-import bug** (`tasks/retry.py:37`): Remove `from tasks.pipeline import _dead_letter` since `_dead_letter` is defined locally at line 206.

2. **Fix wrong import** (`tasks/retry.py:209`): Change `from tasks.pipeline import _apply_fallback` to `from services.pipeline_degradation import _apply_fallback`.

3. **Update document**: Add `aggregate_crawl_results` to file inventory table.

4. **Update document**: Align task name (either document `retry_stuck` or note the beat schedule uses `retry-stuck-articles`).

5. **Add security check**: `retry_stuck` task at line 79 lacks `verify_task` check unlike other scheduled tasks.
# Tasks Module Architecture Review

## Summary

This document reviews the `architecture/tasks.md` claims against the actual `tasks/` codebase. Overall, the documentation is **mostly accurate** with minor discrepancies and one critical bug identified.

---

## 1. Verified Claims (ACCURATE)

### File Inventory
All 14 files in the document exist and match their described task/stage:

| File | Task | Stage | Status |
|------|------|-------|--------|
| `crawl.py` | `run_all_sources` | `crawl` | ✓ Verified |
| `extract.py` | `process_item` | `extract` | ✓ Verified |
| `select.py` | `select_article` | `select` | ✓ Verified |
| `research.py` | `research_article` | `research` | ✓ Verified |
| `write.py` | `write_article` | `write` | ✓ Verified |
| `edit.py` | `edit_article` | `edit` | ✓ Verified |
| `newsletter.py` | `generate_daily_newsletters` | `newsletter` | ✓ Verified |
| `scheduler.py` | `publish_scheduled_articles` | `publish` | ✓ Verified |
| `cleanup.py` | Multiple cleanup tasks | - | ✓ Verified |
| `embeddings.py` | `backfill_embeddings` | `embeddings` | ✓ Verified |
| `retry.py` | `retry_stuck_articles` | - | ✓ Verified |
| `subscribers.py` | `cleanup_inactive_subscribers` | - | ✓ Verified |
| `webhook.py` | `dispatch_webhook_task` | - | ✓ Verified |

### Pipeline Stages
- Stage diagram correctly shows: `pending → select → research → write → edit → done`
- Fail/review paths correctly documented

### Stage Transitions
The transition table is accurate for all stages.

### Quality Gates
Documented quality gates match implementation:
- `select`: Low confidence → `review` ✓ (`tasks/select.py:127`)
- `research`: `_is_degenerate_research(brief)` → `review` ✓ (`tasks/research.py:206`)
- `write`: `_is_degenerate_write(draft)` → `review` ✓ (`tasks/write.py:128`)
- `edit`: Validation fails → `review` ✓ (`tasks/edit.py:169`)

### run_stage Helper
Exists in `tasks/pipeline.py:389-442` with documented signature.

### Degradation Path
Documented correctly: `pending → review → done` with `degradation_count >= 2` logic.

### Scheduler
All 14 Celery Beat tasks documented match `config.py:get_beat_schedule()`:
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

---

## 2. Discrepancies & Issues

### CRIT-1: Limiter Release with Uninitialized Variables in run_stage()

**File:** `tasks/pipeline.py:424-436`

**Issue:** In the `finally` block of `run_stage()`, the limiter is released using `provider_id or rc.provider` and `model or rc.model`. However, `provider_id` and `model` are only set if `_run_stage_core()` succeeds. If an exception occurs during `_run_stage_core()` (e.g., before line 369 where `provider_id` is assigned), these variables remain `None`.

**Code path:**
```python
# Line 413-414: provider_info is a tuple (provider, model, max_tokens, provider_id)
provider_info = _get_provider_for_stage(stage)
rc.provider, rc.model = provider_info[0], provider_info[1]

# Line 424-433: try block
try:
    result, provider_id, model = _run_stage_core(...)  # provider_id only set here
    return result
except Exception as e:
    return _handle_stage_exception(...)  # provider_id may be None here

# Line 434-441: finally block - uses provider_id which may be None
finally:
    if limiter is not None:
        limiter.release(provider_id or rc.provider, model or rc.model, rc.timeout_seconds)
```

**Impact:** If `_run_stage_core()` raises an exception before returning (e.g., at line 349 "article not found" or line 368 "pipeline_timeout"), `provider_id` will be `None`. The `or rc.provider` fallback correctly resolves this, so no actual leak occurs. However, the pattern is fragile and error-prone.

**Recommendation:** Set `provider_id` and `model` to `rc.provider` and `rc.model` before the try block, not after, or ensure they're initialized to those values at declaration.

---

### CRIT-2: Incorrect Error Propagation in _run_stage_core

**File:** `tasks/pipeline.py:345-386`

**Issue:** `_run_stage_core()` can return `{"article_id": article_id, "error": "pipeline_timeout"}, None, None` at line 367. This is a tuple of `(dict, None, None)`. However, `run_stage()` at line 425 unpacks this as:
```python
result, provider_id, model = _run_stage_core(...)
```

This works because `_handle_stage_exception()` is called for exceptions, not for these return values. But the error dict with `error` key is returned directly without proper handling.

**Impact:** When `_run_stage_core()` returns an error dict (pipeline timeout, article not found), the error information is lost because it's treated as a normal result.

**Recommendation:** Check if the returned dict contains an `error` key and handle appropriately.

---

### HIGH-1: Duplicated `_degrade_and_advance` Definition

**Files:**
- `tasks/pipeline.py:36` - defines `_degrade_and_advance`
- `services/pipeline_degradation.py:183` - also defines `_degrade_and_advance`

**Issue:** `tasks/pipeline.py` imports from `services.pipeline_degradation` at line 25-27:
```python
from services.pipeline_degradation import (
    finalize_article as _finalize,
)
```

But then defines its own `_degrade_and_advance` at line 36 which calls `degrade_stage` from services:
```python
def _degrade_and_advance(article, failed_stage: str, run_id=None):
    from services.pipeline_degradation import degrade_stage
    ...
    degrade_stage(article, "writing")
```

This is confusing and creates duplicate logic. The `tasks/pipeline.py:36` version is actually used by `retry.py` (line 47-48), while `services/pipeline_degradation.py:183` is the public API.

**Recommendation:** Remove the duplicate in `tasks/pipeline.py` or have it simply re-export from services.

---

### HIGH-2: Document Missing `aggregate_crawl_results` Task

**Issue:** The document only shows `run_all_sources` in crawl.py but doesn't mention `aggregate_crawl_results` which is the Celery chord callback that aggregates results from all crawl tasks.

**Location:** `tasks/crawl.py:215-253`

**Recommendation:** Document this task in the file inventory.

---

### MED-1: Document Missing Internal Helper Functions

**Issue:** Several internal helper functions are not documented:
- `_generate_topic_newsletter_impl` in `tasks/newsletter.py:132-288`
- `aggregate_crawl_results` in `tasks/crawl.py:215-253`
- `cleanup_stale_limiter_slots` details

These are implementation details but should at least be noted.

---

### MED-2: `cleanup_old_article_versions` Has Configurable Parameter

**Issue:** The document says the task runs "Daily 3:45 AM" but doesn't mention the `days_to_keep` parameter that makes it configurable.

**Location:** `tasks/cleanup.py:268`

**Actual signature:**
```python
def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
```

**Recommendation:** Note that `days_to_keep` is configurable (default 90 days).

---

### MED-3: Layering - tasks/cleanup.py imports Limiter Directly

**File:** `tasks/cleanup.py:120-126`

```python
from services.limiter import get_limiter
limiter = get_limiter()
cleaned = limiter.cleanup_stale_slots()
```

**Issue:** While tasks→services is an allowed layer (per AGENTS.md), this imports the limiter service directly rather than through an adapter pattern. This is acceptable but worth noting.

---

### LOW-1: Document Doesn't Mention `retry_failed_newsletter_deliveries`

**Issue:** The task is listed in the scheduler section (line 191) but not documented in the File Inventory.

---

### LOW-2: Newsletter Send Batches Documented as 500, Actually 500

**Document says:** "batches of 500" (line 143)
**Actual code:** `BATCH_SIZE = 500` in `tasks/newsletter.py:85`

This is correct.

---

## 3. Bug List Summary

| ID | Severity | Location | Issue |
|----|----------|----------|-------|
| CRIT-1 | CRIT | `tasks/pipeline.py:434-436` | Limiter release uses potentially uninitialized `provider_id`/`model` |
| CRIT-2 | HIGH | `tasks/pipeline.py:425` | Error dicts returned from `_run_stage_core()` not properly handled |
| HIGH-1 | HIGH | `tasks/pipeline.py:36` | Duplicate `_degrade_and_advance` definition |
| HIGH-2 | HIGH | `architecture/tasks.md` | Missing `aggregate_crawl_results` task |
| MED-1 | MED | `architecture/tasks.md` | Missing internal helpers |
| MED-2 | MED | `tasks/cleanup.py:268` | Missing `days_to_keep` parameter documentation |
| MED-3 | MED | `tasks/cleanup.py:120` | Direct limiter import |
| LOW-1 | LOW | `architecture/tasks.md` | Missing `retry_failed_newsletter_deliveries` |

---

## 4. Improvement Recommendations

### Priority: CRIT

1. **Fix limiter release pattern in run_stage()** (`tasks/pipeline.py:434-436`)
   - Initialize `provider_id = rc.provider` and `model = rc.model` before the try block
   - Or restructure so provider_info is unpacked before acquiring resources

### Priority: HIGH

2. **Document `aggregate_crawl_results` task** (`tasks/crawl.py:215-253`)
   - Add to file inventory
   - Describe as chord callback for aggregating crawl results

3. **Remove duplicate `_degrade_and_advance`** (`tasks/pipeline.py:36`)
   - Either remove the local definition and import from services directly, or keep only the services version and have tasks import from there

4. **Handle error dicts from `_run_stage_core()`** (`tasks/pipeline.py:425`)
   - Check for `error` key in returned dict and handle appropriately

### Priority: MED

5. **Document internal helpers** - Note that `_generate_topic_newsletter_impl`, `aggregate_crawl_results`, and similar are internal implementation details not part of the public task API.

6. **Add `days_to_keep` to documentation** for `cleanup_old_article_versions`

7. **Add `retry_failed_newsletter_deliveries` to File Inventory**

---

## 5. Verified Layering

Per AGENTS.md: "Tasks layer IS allowed to import from services layer."

All `tasks/*.py` files correctly import from `services/` as expected. No adapters→services violations detected in the tasks module. The `tasks/cleanup.py` import of `services.limiter` is acceptable since tasks→services is a valid layer.

---

## 6. Verified Security

- Task security (`verify_task`) is properly used in all documented tasks
- Rate limiting uses Redis-based locking with proper cleanup
- No obvious security issues found

---

## 7. Conclusion

The architecture document is **mostly accurate** with only minor discrepancies:
- All file inventory items are correct
- All pipeline stages and transitions match
- Quality gates are correctly documented
- Scheduler matches actual implementation

The main issues are:
1. Missing `aggregate_crawl_results` task (HIGH)
2. Missing configurable parameters in cleanup tasks (MED)
3. Duplicate `_degrade_and_advance` definition (HIGH)
4. Fragile limiter release pattern in `run_stage()` (CRIT)

Overall the codebase follows the documented architecture well.
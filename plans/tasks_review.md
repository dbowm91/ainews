# Tasks Module Architecture Review

**Review Date:** 2026-05-22
**Module:** `tasks/`
**Document:** `architecture/tasks.md`

## Summary

The `architecture/tasks.md` document is generally accurate and comprehensive. All 15 files in the file inventory are present and match their documented task names and stages. The pipeline stage diagram, transitions, and quality gates are correctly documented. However, there are several discrepancies between documented behavior and actual implementation, plus some issues that should be addressed.

---

## Verified Claims

### File Inventory ✓
All 15 files exist with correct task names:

| File | Task | Stage | Verified |
|------|------|-------|----------|
| `crawl.py` | `run_all_sources` | `crawl` | ✓ |
| `extract.py` | `process_item` | `extract` | ✓ |
| `select.py` | `select_article` | `select` | ✓ |
| `research.py` | `research_article` | `research` | ✓ |
| `write.py` | `write_article` | `write` | ✓ |
| `edit.py` | `edit_article` | `edit` | ✓ |
| `newsletter.py` | `generate_daily_newsletters` | `newsletter` | ✓ |
| `scheduler.py` | `publish_scheduled_articles` | `publish` | ✓ |
| `cleanup.py` | Multiple cleanup tasks | - | ✓ |
| `embeddings.py` | `backfill_embeddings` | `embeddings` | ✓ |
| `retry.py` | `retry_stuck_articles` | - | ✓ (actually `retry_stuck` in code) |
| `subscribers.py` | `cleanup_inactive_subscribers` | - | ✓ |
| `webhook.py` | `dispatch_webhook_task` | - | ✓ |

### Pipeline Stages ✓
- Stage diagram correctly shows `pending → select → research → write → edit → done`
- Fail path correctly shows articles going to `failed` or `review`
- Quality gate conditions match implementation:
  - `select`: confidence="low" routes to `review` (`tasks/select.py:127-146`)
  - `research`: `_is_degenerate_research()` routes to `review` (`tasks/research.py:206-231`)
  - `write`: `_is_degenerate_write()` routes to `review` (`tasks/write.py:128-154`)
  - `edit`: `validate_and_raise()` failure routes to `review` (`tasks/edit.py:161-185`)

### run_stage Helper ✓
- `tasks/pipeline.py:353-408` implements standard lifecycle with locking and error handling
- Limiter release in `finally` block at line 401-402 with correct fallback pattern

### Degradation Path ✓
- `services/pipeline_degradation.py` has both `_degrade_and_advance` (local) and `degrade_stage` (public API)
- `tasks/retry.py:47-48` correctly imports from services
- Degraded flow `pending → review → done` is correctly documented

### Beat Schedule ✓
- All 14 tasks present in `config.py:get_beat_schedule()` (lines 146-203)
- Schedules match document: 30min crawl, 60min retry, 8AM newsletters, etc.

---

## Discrepancies and Issues

### 1. Incorrect Task Name Documentation (LOW)

**Document says:** `retry_stuck_articles` for `retry.py`
**Actual:** Task function is named `retry_stuck` in `tasks/retry.py:79`

This is a minor naming discrepancy. The Celery task name for beat schedule is `tasks.retry.retry_stuck` which matches the actual function name.

---

## Recommendations

### CRIT (Critical - Should Fix)

None identified for tasks module.

### HIGH (High Priority)

1. **Newsletter lock release scope bug - CONFIRMED BUG** (`tasks/newsletter.py:470`)
   - `lock_key` is defined locally inside `_check_newsletter_lock` (line 398: `lock_key = "ainews:newsletter_lock"`)
   - `_check_newsletter_lock` returns only `(lock_status, skip_result)` at line 409
   - `lock_key` goes out of scope after `_check_newsletter_lock` returns
   - The `finally` block in `_generate_daily_newsletters_core` (lines 466-472) references `lock_key` which is not in scope
   - Python scoping test confirms: local variable from a called function is not accessible after the function returns
   - **Impact:** Newsletter lock will never be released - subsequent daily generations will always see "already in progress" and skip
   - **Fix:** Modify `_check_newsletter_lock` to return `lock_key` as third return value, update caller at line 419

### MED (Medium Priority)

2. **Edit stage missing `_dispatch_next` for review routing - CONFIRMED BUG** (`tasks/edit.py:185` and `205`)
   - When `_handle_validation_and_routing` returns `{"article_id": article.id, "status": "review"}`, the caller at line 366-368 returns immediately without calling `_dispatch_next`
   - Other stages (select, research, write) all call `_dispatch_next` after transitioning to REVIEW
   - **Impact:** Articles routed to review from edit stage may not properly enter the review queue workflow
   - **Fix:** Add `_dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)` before returning the routing result at lines 185 and 205

3. **run_stage error dict handling - CONFIRMED BUG** (`tasks/pipeline.py:390-391`)
   - When `_run_stage_core` returns error dicts (`{"article_id": article_id, "error": "not found"}` or `{"error": "pipeline_timeout"}`), they are returned directly without logging or metrics recording
   - Other stage errors are properly logged via `_handle_stage_exception`, but error dicts bypass this
   - **Fix:** Add logging and metrics before returning error dicts

4. **AGENTS.override.md is outdated** (`tasks/AGENTS.override.md:26-36`)
   - The document claims `retry.py` imports from `tasks.pipeline` which has a local version of `_degrade_and_advance`
   - But actual code in `retry.py:47-48`: `from services.pipeline_degradation import degrade_stage as _degrade_and_advance`
   - `tasks/pipeline.py` does NOT have a local `_degrade_and_advance` definition
   - `tasks/__init__.py:13` correctly exports from services
   - No bug, but documentation needs update

### LOW (Low Priority)

5. **Task name discrepancy** (`retry.py` documented as `retry_stuck_articles` vs actual `retry_stuck`)
   - Cosmetic issue, doesn't affect functionality

---

## Bug Summary

| Priority | File | Line | Issue |
|----------|------|------|-------|
| HIGH | `tasks/newsletter.py` | 470 | `lock_key` undefined in finally block (scope bug) |
| MED | `tasks/edit.py` | 185, 205 | Missing `_dispatch_next` for review routing |
| MED | `tasks/pipeline.py` | 390-391 | Error dicts not logged/metrics |
| LOW | `tasks/AGENTS.override.md` | 26-36 | Outdated documentation |

---

## Layering Violations

No significant layering violations found:
- Tasks correctly import from services (allowed per AGENTS.md)
- Adapters are not imported by tasks
- Schema imports from services are documented and intentional

---

## Security Considerations

No security issues identified. All tasks use `verify_task` for task security where appropriate.

---

## Performance Considerations

1. **Newsletter generation** (`tasks/newsletter.py:349`) uses Celery group for parallel topic processing - good
2. **Cleanup tasks** use batch processing (10,000 per batch) - good
3. **backfill_embeddings** respects rate limits with configurable delay - good

---

## Deprecated Patterns

None identified. The document accurately reflects the current implementation.
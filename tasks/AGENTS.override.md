# Tasks Agent Context

## Pipeline Stages
1. **Select:** Filter incoming articles.
2. **Research:** Deep dive into selected topics using subagents.
3. **Write:** Generate article content.
4. **Edit:** Review and refine content.

## Concurrency & Locking
- Use `run_stage` wrapper for pipeline tasks.
- **CRITICAL:** Ensure limiter slots are released even on early returns. Always use `provider_id or rc.provider` and `model or rc.model` as fallbacks when releasing limiter slots to prevent leaks.
- Be careful with `soft_time_limit` in Celery; ensure cleanup logic handles it.

## Error Handling
- Use specific exception types.
- Avoid broad `except Exception:` unless using `# noqa: BLE001` and logging appropriately.
- **Extraction:** `tasks/extract.py` needs to catch generic `Exception` to support certain test cases and handle unexpected parsing failures gracefully.

## Error Dicts From _run_stage_core
`_run_stage_core()` at `tasks/pipeline.py:346-387` returns error dicts at lines 351 and 368:
- `{"article_id": article_id, "error": "not found"}` - article not found
- `{"article_id": article_id, "error": "pipeline_timeout"}` - pipeline timeout exceeded

These error dicts are returned directly without proper error handling - callers receive raw error dicts instead of structured responses. The calling code at line 426-427 unpacks and returns them as-is.

## Degradation Notes
- **`_degrade_and_advance` location:** `_degrade_and_advance` is defined ONLY in `services/pipeline_degradation.py:183`. It does NOT exist in `tasks/pipeline.py`. When degrading select stage, ensure `selector_result` dict is set: `{"selected": True, "score": 6, "reason": "auto-selected after failure"}`
- **`tasks/__init__.py` re-exports it:** Line 13 imports `from services.pipeline_degradation import degrade_stage as _degrade_and_advance`
- **`retry.py` import:** Line 46 imports `from services.pipeline_degradation import degrade_stage as _degrade_and_advance`
- **Edit stage degradation:** Uses separate `_degrade_edit_stage()` in `services/pipeline_degradation.py` which bypasses `_STAGE_DEGRADE_MAP`. Routes to `review` when `degradation_count >= 2`.
- **Write stage degradation:** Sets `article.draft_article` but should also set `article.writer_model = "fallback"`.

## Known Issues
- **`_STAGE_TASKS`:** Contains `review` status mapping to `tasks/edit.edit_article` - verified present as of 2026-05-07.
- **PipelineLog meta field:** The model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.
- **`publish_scheduled_articles` has NO `autoretry_for`:** Unlike other pipeline tasks, this task at `tasks/scheduler.py:10` has no `autoretry_for` parameter. It uses Redis locks and SQLAlchemy error handling internally. Adding `max_retries` is recommended for consistency.

## run_stage Signature
The `run_stage()` function in `tasks/pipeline.py:353-362` has 8 parameters:
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

## Quality Gate Routing
Each pipeline stage has quality gates that route articles to `review` for manual inspection:
- **select:** Low confidence (score OK but confidence="low") → `review`
- **research:** Degenerate brief (fails `_is_degenerate_research()`) → `review`
- **write:** Degenerate draft (fails `_is_degenerate_write()`) → `review`
- **edit:** Validation failure OR `_should_route_to_review()` OR quality report `passed=False` → `review`

## Fixed Bug Patterns

The following bugs were previously encountered and fixed - do not re-fix these:

### Newsletter Lock Key Return Value
`tasks/newsletter.py:398-409` - `_check_newsletter_lock` must return `lock_key` as third value for the `finally` block to release the lock:
```python
return lock_status, lock_key, skip_result  # 3 values, not 2
```

### Edit Stage _dispatch_next
`tasks/edit.py:185,205` - When routing to review, must call `_dispatch_next`:
```python
if run_id:
    _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)
return {"article_id": article.id, "status": "review"}
```

### _degrade_and_advance Location Correction
`_degrade_and_advance` is defined ONLY in `services/pipeline_degradation.py:183`. There is NO local version in `tasks/pipeline.py`. 

`tasks/__init__.py:13` re-exports from services:
```python
from services.pipeline_degradation import degrade_stage as _degrade_and_advance
```

`retry.py:46` imports directly from services:
```python
from services.pipeline_degradation import degrade_stage as _degrade_and_advance
```

There are no duplicate definitions - only one exists in services/pipeline_degradation.py.

### Error Dicts Not Logged in run_stage
`tasks/pipeline.py:390-391` - Error dicts from `_run_stage_core` are returned directly without logging. However, `_run_stage_core` already logs errors internally before returning them, so no silent error swallowing occurs. The error handling is proper.

### _run_stage_core Error Return Values
`_run_stage_core()` at `tasks/pipeline.py:346-387` returns:
- `{"article_id": article_id, "error": "not found"}` - article not found (line 351)
- `{"article_id": article_id, "error": "pipeline_timeout"}` - pipeline timeout exceeded (line 368)

These dicts are returned to `run_stage()` which checks `if isinstance(result, dict) and "error" in result:` and returns early. Errors are already logged inside `_run_stage_core`.
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

## Duplicate _degrade_and_advance Definitions
There are two separate definitions of `_degrade_and_advance`:
- `tasks/pipeline.py:36` - local version used by `retry.py:47-48`
- `services/pipeline_degradation.py:183` - public API version

`tasks/__init__.py:13` exports the services version:
```python
from services.pipeline_degradation import degrade_stage as _degrade_and_advance
```

But `retry.py` imports from `tasks.pipeline` which has the local version. These have different logic paths.

## Degradation Notes
- **`_degrade_and_advance` in `tasks/pipeline.py`:** When degrading select stage, ensure `selector_result` dict is set: `{"selected": True, "score": 6, "reason": "auto-selected after failure"}`
- **Edit stage degradation:** Uses separate `_degrade_edit_stage()` in `services/pipeline_degradation.py` which bypasses `_STAGE_DEGRADE_MAP`. Routes to `review` when `degradation_count >= 2`.
- **Write stage degradation:** Sets `article.draft_article` but should also set `article.writer_model = "fallback"`.

## Known Issues
- **`_STAGE_TASKS`:** Contains `review` status mapping to `tasks/edit.edit_article` - verified present as of 2026-05-07.
- **PipelineLog meta field:** The model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.

## run_stage Signature
The `run_stage()` function in `tasks/pipeline.py:389-442` has 8 parameters:
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
- **edit:** Validation failure OR `_should_route_to_review()` → `review`
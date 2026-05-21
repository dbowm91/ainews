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

## Degradation Notes
- **`_degrade_and_advance` in `tasks/pipeline.py`:** When degrading select stage, ensure `selector_result` dict is set: `{"selected": True, "score": 6, "reason": "auto-selected after failure"}`
- **Edit stage degradation:** Uses separate `_degrade_edit_stage()` in `services/pipeline_degradation.py` which bypasses `_STAGE_DEGRADE_MAP`. Routes to `review` when `degradation_count >= 2`.
- **Write stage degradation:** Sets `article.draft_article` but should also set `article.writer_model = "fallback"`.

## Known Issues
- **`_STAGE_TASKS`:** Contains `review` status mapping to `tasks.edit.edit_article` - verified present as of 2026-05-07.
- **PipelineLog meta field:** The model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.
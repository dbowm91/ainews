# Tasks Agent Context

## Pipeline Stages
1. **Select:** Filter incoming articles.
2. **Research:** Deep dive into selected topics using subagents.
3. **Write:** Generate article content.
4. **Edit:** Review and refine content.

## Concurrency & Locking
- Use `run_stage` wrapper for pipeline tasks.
- **CRITICAL:** Ensure limiter slots are released even on early returns (e.g., when a lock is already held). See `tasks/pipeline.py` for known leak.
- Be careful with `soft_time_limit` in Celery; ensure cleanup logic handles it.

## Error Handling
- Use specific exception types.
- Avoid broad `except Exception:` unless using `# noqa: BLE001` and logging appropriately.
- **Extraction:** `tasks/extract.py` needs to catch generic `Exception` to support certain test cases and handle unexpected parsing failures gracefully.

## Known Bugs in Pipeline
- **`_log_pipeline` argument order:** Calls at `tasks/pipeline.py:60,63,66` have wrong argument order. Correct signature: `_log_pipeline(run_id, stage, level, message, *args, article_id=None)`. Current calls pass `failed_stage` first instead of `run_id`.
- **Limiter model mismatch:** `_run_stage_core` returns `model` from `_get_provider_for_stage` which only gets the PRIMARY provider's model, not the actual model used if fallback occurred in `_try_stage_work`. Use `provider_id` for tracking but be aware `model` may be incorrect.
- **`_STAGE_TASKS` missing `review`:** If article is in `review` status and needs re-dispatch, it will be stuck. `services/pipeline_utils.py` should have `"review": ("tasks.edit", "edit_article")` in `_STAGE_TASKS` dict. (Verified present as of 2026-05-07) - verify before adding.

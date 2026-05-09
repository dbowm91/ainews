# Tasks Agent Context

## Pipeline Stages
1. **Select:** Filter incoming articles.
2. **Research:** Deep dive into selected topics using subagents.
3. **Write:** Generate article content.
4. **Edit:** Review and refine content.

## Concurrency & Locking
- Use `run_stage` wrapper for pipeline tasks.
- **CRITICAL:** Ensure limiter slots are released even on early returns. Always use `provider_id` (actual provider used) not `rc.provider` (configured provider) when releasing limiter slots.
- Be careful with `soft_time_limit` in Celery; ensure cleanup logic handles it.

## Error Handling
- Use specific exception types.
- Avoid broad `except Exception:` unless using `# noqa: BLE001` and logging appropriately.
- **Extraction:** `tasks/extract.py` needs to catch generic `Exception` to support certain test cases and handle unexpected parsing failures gracefully.

## Known Issues
- **Limiter model mismatch:** `_run_stage_core` returns `model` from `_get_provider_for_stage` which only gets the PRIMARY provider's model, not the actual model used if fallback occurred in `_try_stage_work`. Use `provider_id` for tracking but be aware `model` may be incorrect.
- **`_STAGE_TASKS`:** Contains `review` status mapping to `tasks.edit.edit_article` - verified present as of 2026-05-07.
- **PipelineLog meta field:** The model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.
# Tasks Agent Context

## Pipeline Stages
1. **Select:** Filter incoming articles.
2. **Research:** Deep dive into selected topics using subagents.
3. **Write:** Generate article content.
4. **Edit:** Review and refine content.

## Concurrency & Locking
- Use `run_stage` wrapper for pipeline tasks.
- Ensure limiter slots are released even on early returns or failures.
- Be careful with `soft_time_limit` in Celery; ensure cleanup logic handles it.

## Error Handling
- Use specific exception types.
- Avoid broad `except Exception:` unless using `# noqa: BLE001` and logging appropriately.
- Extraction tasks should have robust fallbacks for parsing failures.

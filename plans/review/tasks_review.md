# Tasks Module Architecture Review

Review date: 2026-05-22
Document reviewed: `architecture/tasks.md`
Code examined: `tasks/` directory

---

## Verified Claims

### File Inventory (MATCH)
All documented files exist in the `tasks/` directory:
- `crawl.py` - `run_all_sources` and `aggregate_crawl_results` present
- `extract.py` - `process_item` present
- `select.py` - `select_article` present
- `research.py` - `research_article` present
- `write.py` - `write_article` present
- `edit.py` - `edit_article` present
- `newsletter.py` - `generate_daily_newsletters` present
- `scheduler.py` - `publish_scheduled_articles` present
- `cleanup.py` - All documented cleanup tasks present
- `embeddings.py` - `backfill_embeddings` present
- `retry.py` - retry task present
- `subscribers.py` - `cleanup_inactive_subscribers` present
- `webhook.py` - `dispatch_webhook_task` present

### Pipeline Stage Transitions (MATCH)
Stage transitions in `constants.py` match documentation:
- `pending` -> `select` -> `research` -> `write` -> `edit` -> `done`
- `review` route exists at each quality gate stage

### Quality Gates (MATCH)
Quality gate implementations verified:
- `select.py`: confidence="low" routes to `review` (line 127-128)
- `research.py`: `_is_degenerate_research()` routes to `review` (line 206)
- `write.py`: `_is_degenerate_write()` routes to `review` (line 128)
- `edit.py`: `ValidationError` from `validate_and_raise()` routes to `review` (line 163)

### Celery Beat Schedule (MATCH)
All scheduled tasks match between documentation and `config.py:get_beat_schedule()`:
- `run-all-sources`: Every 30 min
- `retry-stuck-articles`: Every 60 min
- `generate-newsletters`: 8:00 AM ET
- `cleanup-old-logs`: Daily 3 AM
- `consolidate-trend-memory`: Daily 3:30 AM
- `purge-trend-memory`: Daily 3:45 AM
- `cleanup-old-versions`: Daily 3:45 AM
- `cleanup-expired-verifications`: Every 15 min
- `publish-scheduled-articles`: Every 5 min
- `cleanup-stale-limiter-slots`: Every 5 min
- `retry-failed-newsletter-deliveries`: Every 2 hours
- `recalculate-impact-scores`: Daily 4:00 AM
- `cleanup-inactive-subscribers`: Daily 1:00 AM
- `backfill-embeddings`: Daily 2:00 AM

### Newsletter Email Batching (MATCH)
`_send_emails_parallel()` in `newsletter.py` correctly uses `BATCH_SIZE = 500` as documented.

### Stage Status Transitions (MATCH)
`is_valid_transition()` in `constants.py` correctly enforces the documented state machine.

---

## Discrepancies

### 1. `retry.py` Task Name Mismatch
**Documentation says:** `retry_stuck_articles`  
**Actual implementation:** `retry_stuck` (line 78)

```python
# Doc: retry_stuck_articles
# Actual:
@shared_task(...)
def retry_stuck(self):
```

The Celery Beat schedule correctly references `tasks.retry.retry_stuck`, so the bug is in the documentation, not the implementation.

---

### 2. `process_item` Signature Mismatch
**Documentation says:**
```python
def process_item(self, source_id: int, item_data: dict):
```

**Actual implementation (extract.py:278-294):**
```python
def process_item(
    self,
    source_key,
    source_name,
    source_type,
    external_id,
    title,
    url,
    author,
    published_at,
    text_content,
    raw_score,
    raw_metadata,
    topics,
    min_content_length=None,
    run_id=None,
):
```

The documentation shows a simplified/pseudocode signature that doesn't match the actual function. The actual function accepts flat parameters and uses `ProcessItemTask` schema for validation.

---

### 3. `run_stage` Helper Signature Mismatch
**Documentation says:**
```python
def run_stage(task, article_id: int, stage: str, next_stage: str, task_func):
```

**Actual implementation (pipeline.py:353-362):**
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

The parameter names and structure are completely different. The documentation's pseudocode doesn't reflect the actual implementation.

---

### 4. Degradation Path Routing - Partial Match
**Documentation says:** When degradation_count >= 2, articles bypass remaining stages and go directly to `review`.

**Actual implementation (retry.py:22-31):**
```python
def _classify_stuck_article(article, now):
    age_minutes = (now - article.updated_at).total_seconds() / 60
    
    if age_minutes >= get_stuck_threshold_minutes():
        return "dead_letter"
    elif (article.retry_count or 0) >= _get_max_stage_retries():
        return "degrade"
    else:
        return "retry"
```

The degradation decision is based on `retry_count` vs `_get_max_stage_retries()`, not `degradation_count`. This is a subtle semantic difference - the actual behavior aligns with the documented degraded flow but uses different variable naming.

---

### 5. Documentation Pseudo-code vs Actual Signatures
Several code examples in the documentation are simplified pseudocode that don't reflect actual function signatures:
- `process_item` example shows simplified params
- `run_stage` example shows incorrect parameter names

This makes the documentation misleading for someone trying to trace actual code paths.

---

## Bugs

### Bug 1: Documentation Uses Wrong Task Name for Retry Task
The task is registered as `retry_stuck` but documentation refers to it as `retry_stuck_articles`. This will cause confusion if someone tries to reference the task by the documented name.

---

## Improvements

### Improvement 1: Update `process_item` Signature in Documentation
The documentation should reflect the actual function signature or use a more accurate pseudocode representation. The actual implementation accepts 15 parameters plus an optional `run_id`, not just `source_id: int` and `item_data: dict`.

### Improvement 2: Update `run_stage` Signature in Documentation
The documented signature `run_stage(task, article_id: int, stage: str, next_stage: str, task_func)` doesn't match the actual `run_stage(stage, article_id, work_fn, task_self, run_id=None, skip_next="finalize", retry_countdown=30, retry_max=15)`. Documentation should use correct parameter names.

### Improvement 3: Clarify Degradation Variables
The documentation mentions `degradation_count >= 2` but the code uses `retry_count >= _get_max_stage_retries()`. While the end result is the same (articles go to review), the variable names are different. Consider aligning documentation with actual variable names or documenting the mapping.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 7 |
| Discrepancies | 4 |
| Bugs | 1 |
| Improvements | 3 |

The documentation is largely accurate regarding file inventory, pipeline stages, and scheduler configuration. The main issues are:
1. Pseudo-code examples don't match actual function signatures
2. Task name discrepancy in retry.py
3. Variable naming differences between docs and code (degradation_count vs retry_count)

No critical bugs that would prevent understanding of the system architecture were found. The pipeline flow and stage transitions are correctly documented.

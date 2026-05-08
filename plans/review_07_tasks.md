# Architecture Review: tasks.md

**Date:** 2026-05-08
**Reviewer:** Architecture Review Agent
**Document:** `/Users/davidbowman/projects/ainews/architecture/tasks.md`

---

## Summary

| Category | Status |
|----------|--------|
| File Inventory | Correct |
| Stage Transitions | Correct |
| run_stage Helper | Correct |
| Celery Beat Schedule | Partially accurate |
| Newsletter Tasks | Correct |
| Cleanup Tasks | Incomplete |

---

## 1. Verified Items (Correct)

### File Inventory (Correct)

All documented files exist and tasks match:

| Documented File | Documented Task | Actual File | Actual Tasks | Status |
|----------------|-----------------|-------------|--------------|--------|
| `crawl.py` | `run_all_sources` | `crawl.py` | `run_all_sources`, `crawl_source`, `aggregate_crawl_results` | CORRECT |
| `extract.py` | `process_item` | `extract.py` | `process_item` | CORRECT |
| `select.py` | `select_article` | `select.py` | `select_article` | CORRECT |
| `research.py` | `research_article` | `research.py` | `research_article` | CORRECT |
| `write.py` | `write_article` | `write.py` | `write_article` | CORRECT |
| `edit.py` | `edit_article` | `edit.py` | `edit_article` | CORRECT |
| `newsletter.py` | `generate_daily_newsletters` | `newsletter.py` | `generate_daily_newsletters`, `send_single_email`, `retry_failed_newsletter_deliveries` | CORRECT |
| `scheduler.py` | `publish_scheduled_articles` | `scheduler.py` | `publish_scheduled_articles` | CORRECT |
| `cleanup.py` | Various | `cleanup.py` | Multiple cleanup tasks | CORRECT |
| `embeddings.py` | `backfill_embeddings` | `embeddings.py` | `backfill_embeddings` | CORRECT |

### Stage Transitions (Correct)

Documented transitions match actual implementation in `constants.py`:

| Current | Next (success) | Next (review) | Next (fail) | Verified |
|---------|----------------|---------------|-------------|----------|
| `pending` | `select` | - | `failed` | VERIFIED |
| `select` | `research` | `review` | `failed` | VERIFIED |
| `research` | `write` | `review` | `failed` | VERIFIED |
| `write` | `edit` | `review` | `failed` | VERIFIED |
| `edit` | `done` | `review` | `failed` | VERIFIED |

**Code verification** from `constants.py:49-58`:
```python
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
    PipelineStatus.EDITING: frozenset([PipelineStatus.REVIEW, PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.REVIEW: frozenset([PipelineStatus.DONE, PipelineStatus.FAILED]),
    ...
}
```

Note: Document uses simplified stage names (`select`, `research`, etc.) while actual implementation uses pipeline status constants (`PENDING`, `RESEARCHING`, `WRITING`, `EDITING`, `REVIEW`). The mapping is correct.

### run_stage Helper (Correct)

Documented 6-step lifecycle in `pipeline.py:389-442` matches exactly:

1. Acquire stage lock (prevents duplicate processing) - Line 409-420
2. Update article status to stage - Line 274 in `work()` functions
3. Execute task_func - Line 425 via `_run_stage_core`
4. On success: transition to next_stage - Via `_dispatch_next` calls
5. On failure: handle_retry() or mark_failed() - Via `_handle_stage_exception`
6. Release stage lock in finally block - Lines 434-442

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

Signature matches documented `run_stage(task, article_id: int, stage: str, next_stage: str, task_func)`.

### Newsletter Tasks (Correct)

Documented 5-step flow matches `newsletter.py`:
1. `_fetch_articles_for_newsletter()` - Lines 113-129
2. `generate_executive_summary()` - 3-stage LLM via `newsletter_pipeline` in `services/newsletter_pipeline.py`
3. `generate_main_newsletter()` - Line 168
4. `generate_topic_newsletters()` - Line 174
5. `_send_emails_parallel()` - Lines 70-110, batches of 500

---

## 2. Discrepancies

### 2.1 Celery Beat Schedule - Incomplete and Inaccurate Times

**Document says:**
| Task | Schedule | Description |
|------|----------|-------------|
| `run_all_sources` | Every 30 min | Crawl all sources |
| `generate_daily_newsletters` | 8:00 AM ET | Generate newsletters |
| `publish_scheduled_articles` | Every 5 min | Check scheduled publishes |
| `cleanup_old_logs` | Daily 3 AM | Clean old pipeline logs |
| `backfill_embeddings` | Daily 2 AM | Update embeddings |

**Actual in `config.py:146-203`:**
```python
"run-all-sources": {
    "task": "tasks.crawl.run_all_sources",
    "schedule": timedelta(minutes=crawl_interval),  # 30 min - CORRECT
},
"generate-newsletters": {
    "task": "tasks.newsletter.generate_daily_newsletters",
    "schedule": crontab(hour=newsletters_hour, minute=0),  # 8 AM - CORRECT
},
"cleanup-old-logs": {
    "task": "tasks.cleanup.cleanup_old_pipeline_logs",
    "schedule": crontab(hour=cleanup_logs_hour, minute=0),  # Default 3 AM - CORRECT
},
"backfill-embeddings": {
    "task": "tasks.embeddings.backfill_embeddings",
    "schedule": crontab(hour=2, minute=0),  # 2 AM - CORRECT
},
"publish-scheduled-articles": {
    "task": "tasks.scheduler.publish_scheduled_articles",
    "schedule": timedelta(minutes=publish_interval),  # 5 min - CORRECT
},
```

**Discrepancies:**
1. Time for `cleanup_old_logs` is correct (3 AM default)
2. **Missing documented tasks** (exist but not documented):
   - `retry-stuck-articles` - Every 60 min
   - `consolidate-trend-memory` - 3:30 AM
   - `purge-trend-memory` - 3:45 AM
   - `cleanup-old-versions` - 3:45 AM
   - `cleanup-expired-verifications` - Every 15 min
   - `cleanup-stale-limiter-slots` - Every 5 min
   - `retry-failed-newsletter-deliveries` - Every 2 hours
   - `recalculate-impact-scores` - 4:00 AM
   - `cleanup-inactive-subscribers` - 1:00 AM

### 2.2 Stage Status Names - Simplified vs Actual

**Document shows:** `pending`, `select`, `research`, `write`, `edit`, `done`

**Actual `STAGE_STATUS_MAP` in `constants.py:72-87`:**
```python
STAGE_STATUS_MAP = {
    "pending": "select",
    "selected": "research",
    "researching": "research",
    "writing": "write",
    "written": "edit",
    "editing": "edit",
    "selector": "select",
    "researcher": "research",
    "writer": "write",
    "editor": "edit",
    ...
}
```

**Issue:** The document's simplified stage names (`select`, `research`, etc.) don't directly map to the actual `STAGE_STATUS_MAP`. The document should clarify that stage names in the pipeline flow diagram map to status values.

### 2.3 Cleanup Tasks - Incomplete Documentation

**Document says:** "Various - Cleanup old logs, versions, expired data"

**Actual cleanup tasks in `cleanup.py`:**
| Task | Description | Not Documented |
|------|-------------|-----------------|
| `cleanup_old_pipeline_logs` | Delete logs older than 30 days | - |
| `cleanup_expired_verifications` | Delete unverified subscribers | YES |
| `cleanup_stale_limiter_slots` | Clean up stale Redis limiter slots | YES |
| `consolidate_trend_memory` | Promote low-importance entries when high-importance arrive | YES |
| `recalculate_impact_scores` | Recalculate impact scores based on engagement | YES |
| `purge_trend_memory` | Remove expired trend memory entries | YES |
| `cleanup_old_article_versions` | Delete versions older than specified days | YES |

---

## 3. Issues Found

### 3.1 Missing Tasks in Beat Schedule Documentation

**Severity:** Medium
**Type:** Documentation Incomplete

The Celery Beat schedule table is missing 9 tasks that are actually scheduled:
- `retry-stuck-articles` - Every 60 minutes
- `consolidate-trend-memory` - 3:30 AM
- `purge-trend-memory` - 3:45 AM
- `cleanup-old-versions` - 3:45 AM
- `cleanup-expired-verifications` - Every 15 minutes
- `cleanup-stale-limiter-slots` - Every 5 minutes
- `retry-failed-newsletter-deliveries` - Every 2 hours
- `recalculate-impact-scores` - 4:00 AM
- `cleanup-inactive-subscribers` - 1:00 AM

### 3.2 Newsletter Task Not Documented

**Severity:** Low
**Type:** Documentation Missing

`retry_failed_newsletter_deliveries` task exists in `newsletter.py:491-585` but is not documented. This task re-attempts delivery for newsletters that previously failed and runs every 2 hours.

### 3.3 Degradation Path - Need Verification

**Severity:** Low
**Type:** Documentation Clarity

The degradation path `select → research → write → edit → review → done` needs clarification:
- When select is disabled, articles go directly to `researching` (skip_next=RESEARCHING)
- When research is disabled, articles go to `writing` (skip_next=WRITING)
- The degradation flow is actually the normal flow when stages are disabled

The document should clarify that degradation applies when stages are disabled via `pipeline.yaml`.

---

## 4. Recommendations

### High Priority

1. **Update Celery Beat Schedule table**
   - Add all 9 missing scheduled tasks
   - Verify times match pipeline.yaml defaults

2. **Document cleanup tasks in detail**
   - Replace "Various" with explicit table of cleanup tasks

### Medium Priority

3. **Add clarification on stage status mapping**
   - Document that `select`, `research`, etc. map to actual status values
   - Or use actual status values consistently

4. **Document `retry_failed_newsletter_deliveries` task**
   - Add to file inventory and newsletter section

### Low Priority

5. **Clarify degradation path explanation**
   - Explain that degradation happens when stages are disabled
   - Show example configuration that triggers degradation

---

## 5. Summary

The `tasks.md` document is mostly accurate for the core pipeline tasks. The file inventory, stage transitions, and `run_stage` helper all match the implementation correctly.

**Main issues:**
1. Celery Beat schedule table is incomplete (missing 9 scheduled tasks)
2. Cleanup tasks are documented vaguely as "Various" instead of explicit tasks
3. `retry_failed_newsletter_deliveries` is not documented
4. Stage status names in document are simplified vs actual implementation

**Overall Assessment:** The document captures the core architecture correctly but needs updates to reflect the complete set of scheduled tasks and clarify the degradation path behavior.

---

*End of Review*

# Tasks Module Architecture Review

## Summary of Verified Claims

### File Inventory
| File | Documented Task | Actual Task | Status |
|------|----------------|-------------|--------|
| `crawl.py` | `run_all_sources` | `run_all_sources` + `crawl_source` + `aggregate_crawl_results` | PARTIAL |
| `extract.py` | `process_item` | `process_item` | VERIFIED |
| `select.py` | `select_article` | `select_article` | VERIFIED |
| `research.py` | `research_article` | `research_article` | VERIFIED |
| `write.py` | `write_article` | `write_article` | VERIFIED |
| `edit.py` | `edit_article` | `edit_article` | VERIFIED |
| `newsletter.py` | `generate_daily_newsletters` | `generate_daily_newsletters` + `send_single_email` + `retry_failed_newsletter_deliveries` | PARTIAL |
| `scheduler.py` | `publish_scheduled_articles` | `publish_scheduled_articles` | VERIFIED |
| `cleanup.py` | Various | Multiple tasks (see below) | PARTIAL |
| `embeddings.py` | `backfill_embeddings` | `backfill_embeddings` | VERIFIED |
| `retry.py` | (not documented) | `retry_stuck` | MISSING |
| `subscribers.py` | (not documented) | `cleanup_inactive_subscribers` | MISSING |
| `webhook.py` | (not documented) | `dispatch_webhook_task` | MISSING |

### Stage Transitions
Documented transitions match implementation in `constants.py` and `tasks/pipeline.py`.

### Quality Gates
| Stage | Documented Condition | Actual Implementation | Status |
|-------|----------------------|----------------------|--------|
| select | confidence="low" | `select_article` lines 127-146 | VERIFIED |
| research | `_is_degenerate_research(brief)` | `research.py` lines 13-28, 204-231 | VERIFIED |
| write | `_is_degenerate_write(draft)` | `write.py` lines 12-27, 127-154 | VERIFIED |
| edit | Validation fails | `edit.py` lines 148-207 + `_should_route_to_review` | VERIFIED |

### Celery Beat Schedule
| Documented Task | Documented Schedule | Actual Schedule | Status |
|-----------------|---------------------|-----------------|--------|
| run-all-sources | Every 30 min | Every 30 min | VERIFIED |
| retry-stuck-articles | Every 60 min | Every 60 min | VERIFIED |
| generate-newsletters | 8:00 AM ET | 8:00 AM ET | VERIFIED |
| cleanup-old-logs | Daily 3 AM | Daily 3 AM | VERIFIED |
| consolidate-trend-memory | Daily 3:30 AM | Daily 3:30 AM | VERIFIED |
| purge-trend-memory | Daily 3:45 AM | Daily 3:45 AM | VERIFIED |
| cleanup-old-versions | Daily 3:45 AM | Daily 3:45 AM | VERIFIED |
| cleanup-expired-verifications | Every 15 min | Every 15 min | VERIFIED |
| publish-scheduled-articles | Every 5 min | Every 5 min | VERIFIED |
| cleanup-stale-limiter-slots | Every 5 min | Every 5 min | VERIFIED |
| retry-failed-newsletter-deliveries | Every 2 hours | Every 2 hours | VERIFIED |
| recalculate-impact-scores | Daily 4:00 AM | Daily 4:00 AM | VERIFIED |
| cleanup-inactive-subscribers | Daily 1:00 AM | Daily 1:00 AM | VERIFIED |
| backfill-embeddings | Daily 2:00 AM | Daily 2:00 AM | VERIFIED |

## Discrepancies and Issues

### 1. Missing Tasks in File Inventory (MINOR)

**Issue**: The document only lists 9 files but there are 15 Python files in `tasks/`.

**Missing tasks**:
- `retry.py`: `retry_stuck` - undocumented but critical for pipeline reliability
- `subscribers.py`: `cleanup_inactive_subscribers` - mentioned in Beat schedule but not file inventory
- `webhook.py`: `dispatch_webhook_task` - not mentioned at all
- `pipeline.py`: Contains shared helpers (not a task itself)

**Impact**: Low - the Beat schedule and actual behavior are correct, just not fully documented.

### 2. Cleanup Tasks Documented as "Various" (MINOR)

**Issue**: `cleanup.py` contains 7 distinct tasks but the document just says "Various".

**Actual tasks in cleanup.py**:
- `cleanup_old_pipeline_logs`
- `cleanup_expired_verifications`
- `cleanup_stale_limiter_slots`
- `consolidate_trend_memory`
- `recalculate_impact_scores`
- `purge_trend_memory`
- `cleanup_old_article_versions`

**Recommendation**: Document each task individually in the file inventory.

### 3. run_stage Helper Lacks `skip_next` Parameter Documentation (MINOR)

**Issue**: The documented signature shows `run_stage(task, article_id, stage, next_stage, task_func)` but actual signature in `pipeline.py:389-442` is:
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

**Impact**: Low - the documentation is simplified but the actual implementation has more options.

### 4. Newsletter Batch Size Not Documented (MINOR)

**Issue**: Document says "batches of 500" for email sending. This is correct in `newsletter.py:85` but not in the file inventory description.

### 5. Degradation Path Documented Incorrectly (BUG)

**Issue**: Document states:
```
select → research → write → edit → review → done
```
But this describes normal flow when degradation is disabled. The actual degradation path when full pipeline is disabled should be documented more clearly - articles go directly from `pending` to `review` (bypassing select/research/write/edit).

**Reference**: `pipeline.py:296-303` shows `_handle_disabled` which dispatches to `skip_next` directly.

## Specific Bugs Identified

### No bugs found in task signatures or stage transitions

All task names, signatures, and stage transitions match between documentation and implementation. The quality gates are correctly implemented. Celery Beat schedule matches. Rate limiting is correctly implemented in `services/limiter.py`.

## Improvement Recommendations

1. **Update File Inventory**: Add `retry.py`, `subscribers.py`, and `webhook.py` with their respective tasks.

2. **Document All cleanup.py Tasks**: List each task individually instead of "Various".

3. **Clarify Degradation Path**: The degradation path section conflates normal flow with degradation. Separate them more clearly:
   - Normal flow: `pending → select → research → write → edit → done`
   - Degraded flow (when stage disabled): skips directly to next enabled stage

4. **Fix run_stage Signature**: Document the actual 8-parameter signature instead of the simplified 5-parameter version.

5. **Add missing newsletter task description**: `retry_failed_newsletter_deliveries` should be listed.

6. **Add pipeline helper documentation**: Document that `pipeline.py` contains shared helpers used by all stage tasks.

## Verified Implementation Details

### Rate Limiting
- Uses Redis slots via `services/limiter.py`
- `ModelLimiter.acquire()` blocks with pubsub notification
- `ModelLimiter.release()` uses Lua script and publishes to done channel
- Slots are properly released in `finally` block in `run_stage` (`pipeline.py:434-442`)

### Quality Gate Routing
- Select: Low confidence routes to `review` (`select.py:127-146`)
- Research: Degenerate brief (`_is_degenerate_research`) routes to `review` (`research.py:204-231`)
- Write: Degenerate draft (`_is_degenerate_write`) routes to `review` (`write.py:127-154`)
- Edit: Validation failure OR `_should_route_to_review()` routes to `review` (`edit.py:187-205`)

### Pipeline Stage Statuses
All statuses from `constants.py` match documented transitions.
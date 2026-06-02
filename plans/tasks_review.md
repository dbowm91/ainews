# Tasks Architecture Review

## Summary
The architecture document `architecture/tasks.md` is mostly accurate but contains several discrepancies ranging from minor omissions to significant incomplete documentation. The core pipeline logic, stage transitions, and run_stage helper are correctly documented. However, the quality gates section is incomplete, and several tasks are missing from the file inventory.

## Verified Claims

### File Inventory - Partially Accurate
| File | Claim | Status |
|------|-------|--------|
| `crawl.py` | `run_all_sources`, `aggregate_crawl_results` | ✅ Correct |
| `extract.py` | `process_item` | ✅ Correct |
| `select.py` | `select_article` | ✅ Correct |
| `research.py` | `research_article` | ✅ Correct |
| `write.py` | `write_article` | ✅ Correct |
| `edit.py` | `edit_article` | ✅ Correct |
| `newsletter.py` | `generate_daily_newsletters` | ✅ Correct |
| `scheduler.py` | `publish_scheduled_articles` | ✅ Correct |
| `cleanup.py` | Multiple cleanup tasks | ⚠️ Incomplete |
| `embeddings.py` | `backfill_embeddings` | ⚠️ Missing `generate_article_embedding` |
| `retry.py` | `retry_stuck` | ✅ Correct |
| `subscribers.py` | `cleanup_inactive_subscribers` | ✅ Correct |
| `webhook.py` | `dispatch_webhook_task` | ✅ Correct |

### Pipeline Stages - Accurate
- `PipelineStatus` enum values match `constants.py:30-43`
- `VALID_TRANSITIONS` map matches `constants.py:52-64`
- Stage names (select, research, write, edit) correctly defined

### run_stage Helper - Accurate
- Signature matches `tasks/pipeline.py:353-362`
- Default `retry_max=15` confirmed
- `retry_max=20` for select stage confirmed at `tasks/select.py:202`

### Retry Configuration - Partially Accurate
- Core pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES` ✅
- `CELERY_TASK_MAX_RETRIES` default of 3 confirmed at `constants.py:6`

### Degradation Path - Accurate
- `degrade_stage` function at `services/pipeline_degradation.py:314`
- `degrade_stage as _degrade_and_advance` import at `tasks/retry.py:46`
- Degradation logic at `services/pipeline_degradation.py:84-131`

## Discrepancies Found

### 1. Missing Task: `crawl_source`
- **Claim**: `crawl.py` only has `run_all_sources` and `aggregate_crawl_results`
- **Reality**: `crawl_source` at `tasks/crawl.py:32` is the leaf task that performs actual crawling
- **Severity**: Minor
- **Location**: `architecture/tasks.md:9-10`
- **Suggested fix**: Add `crawl_source` to the file inventory table

### 2. Missing Task: `generate_article_embedding`
- **Claim**: `embeddings.py` only has `backfill_embeddings`
- **Reality**: `generate_article_embedding` at `tasks/embeddings.py:21` generates embedding for a single article
- **Severity**: Minor
- **Location**: `architecture/tasks.md:19`
- **Suggested fix**: Add `generate_article_embedding` to file inventory

### 3. Missing Task: `send_single_email`
- **Claim**: `newsletter.py` only has `generate_daily_newsletters`
- **Reality**: `send_single_email` at `tasks/newsletter.py:34` sends individual emails
- **Severity**: Minor
- **Location**: `architecture/tasks.md:16`
- **Suggested fix**: Add `send_single_email` to file inventory

### 4. Missing Task: `retry_failed_newsletter_deliveries`
- **Claim**: `newsletter.py` only has `generate_daily_newsletters`
- **Reality**: `retry_failed_newsletter_deliveries` at `tasks/newsletter.py:520` retries failed deliveries
- **Severity**: Minor
- **Location**: `architecture/tasks.md:16`
- **Suggested fix**: Add `retry_failed_newsletter_deliveries` to file inventory

### 5. Edit Quality Gate Incomplete
- **Claim**: "edit | Validation fails | Route to review"
- **Reality**: Three routing conditions exist in `tasks/edit.py`:
  1. Validation failure (line 161-185)
  2. `_should_route_to_review(article)` returns True (line 189-206)
  3. Quality report `passed=False` (line 328-349)
- **Severity**: Major
- **Location**: `architecture/tasks.md:70` and `tasks/edit.py:147-349`
- **Suggested fix**: Update quality gates table to list all three conditions

### 6. Stage Transitions - PENDING Status
- **Claim**: "pending | select (success) | review (quality gate) | failed"
- **Reality**: Document shows only `selecting` and `researching` as success transitions, but `constants.py:53` shows PENDING can also transition directly to `REVIEW`
- **Severity**: Minor
- **Location**: `architecture/tasks.md:49` and `constants.py:53`
- **Suggested fix**: Clarify that PENDING can transition to REVIEW via quality gate or degradation

### 7. Cleanup Tasks Missing `verify_task()`
- **Claim**: "Some orchestration and cleanup tasks... use autoretry_for without an explicit max_retries limit"
- **Reality**: Several cleanup tasks don't use `verify_task()` at all:
  - `cleanup_old_pipeline_logs` - HAS verify_task ✅
  - `cleanup_expired_verifications` - HAS verify_task ✅
  - `cleanup_stale_limiter_slots` - HAS verify_task ✅
  - `consolidate_trend_memory` - HAS verify_task ✅
  - `recalculate_impact_scores` - HAS verify_task ✅
  - `purge_trend_memory` - HAS verify_task ✅
  - `cleanup_old_article_versions` - HAS verify_task ✅
  - `cleanup_inactive_subscribers` - NO verify_task ❌
- **Severity**: Major (Security)
- **Location**: `tasks/subscribers.py:15`
- **Suggested fix**: Add `verify_task()` to `cleanup_inactive_subscribers` or document why it's intentionally public

### 8. Celery Beat Schedule Task Count
- **Claim**: 14 tasks listed in schedule
- **Reality**: 13 tasks in `config.py:get_beat_schedule()` (line 148-205)
- **Severity**: Minor
- **Location**: `architecture/tasks.md:220-235`
- **Suggested fix**: Verify actual task count; document lists 14 but only 13 exist

## Bugs Identified

### Bug: `cleanup_inactive_subscribers` Missing Security Check
- **Bug**: Task has no `verify_task()` call while all other cleanup tasks do
- **Location**: `tasks/subscribers.py:15`
- **Impact**: Unauthorized callers could invoke this task
- **Suggested fix**: Add `verify_task()` or document why it's intentionally public

### Bug: `generate_article_embedding` Missing from Beat Schedule
- **Bug**: `generate_article_embedding` at `tasks/embeddings.py:21` is never scheduled via Celery Beat
- **Location**: `tasks/embeddings.py` and `config.py`
- **Impact**: Only `backfill_embeddings` runs on schedule; single-article embedding must be triggered manually
- **Suggested fix**: Either add to beat schedule or document that this is intentional (incremental embedding only)

## Improvement Opportunities

### Improvement: Document `_is_degenerate_research` Logic
- **Location**: `tasks/research.py:13-28`
- **Benefit**: Clarify quality gate criteria (no key claims OR impact_score < 10)
- **Suggested fix**: Add inline documentation or update architecture doc

### Improvement: Document `_is_degenerate_write` Logic
- **Location**: `tasks/write.py:12-27`
- **Benefit**: Clarify quality gate criteria (body < 500 chars OR no key_points OR no citations)
- **Suggested fix**: Add inline documentation or update architecture doc

### Improvement: Document `_should_route_to_review` Logic
- **Location**: `services/pipeline_degradation.py:66-74`
- **Benefit**: Clarify that this is a configuration-driven check (review.enabled + auto_publish_threshold)
- **Suggested fix**: Add documentation explaining the threshold-based routing

## Stale Items Found

1. `crawl_source` task not in file inventory (exists and is critical)
2. `generate_article_embedding` not in file inventory
3. `send_single_email` not in file inventory
4. `retry_failed_newsletter_deliveries` not in file inventory
5. Edit quality gate table only shows 1 of 3 routing conditions
6. "3-stage LLM" description for executive summary is vague

## Recommendations

### Priority 1 (Critical)
1. **Add missing `verify_task()` to `cleanup_inactive_subscribers`** - security gap
2. **Update quality gates table** - edit stage has 3 routing conditions, not 1

### Priority 2 (High)
3. **Add `crawl_source` to file inventory** - it's the actual leaf task
4. **Add `generate_article_embedding` and `retry_failed_newsletter_deliveries` to file inventory**
5. **Verify Celery Beat task count** - claim says 14, code shows 13

### Priority 3 (Medium)
6. **Document `_should_route_to_review()` in quality gates** - important routing logic
7. **Clarify "3-stage LLM" description** for executive summary
8. **Document `_is_degenerate_research` and `_is_degenerate_write` criteria**
# Review: tasks.md

**Reviewed:** 2026-05-31
**Source:** `architecture/tasks.md`
**Reviewer:** Subagent 4 (Pipeline & Tasks Layer)
**Status:** COMPLETE

---

## Verified Claims

### File Inventory
All task files exist in `tasks/`:
- `crawl.py` — VERIFIED
- `extract.py` — VERIFIED
- `select.py` — VERIFIED
- `research.py` — VERIFIED
- `write.py` — VERIFIED
- `edit.py` — VERIFIED
- `newsletter.py` — VERIFIED
- `scheduler.py` — VERIFIED
- `cleanup.py` — VERIFIED
- `embeddings.py` — VERIFIED
- `retry.py` — VERIFIED
- `subscribers.py` — VERIFIED
- `webhook.py` — VERIFIED

### Task Functions
- `run_all_sources` — VERIFIED (`tasks/crawl.py:269`)
- `aggregate_crawl_results` — VERIFIED (`tasks/crawl.py:215`)
- `process_item` — VERIFIED (`tasks/extract.py:278`)
- `select_article` — VERIFIED (`tasks/select.py:59`)
- `research_article` — VERIFIED (`tasks/research.py:267`)
- `write_article` — VERIFIED (`tasks/write.py:48`)
- `edit_article` — VERIFIED (`tasks/edit.py:379`)
- `generate_daily_newsletters` — VERIFIED (`tasks/newsletter.py:488`)
- `publish_scheduled_articles` — VERIFIED (`tasks/scheduler.py:11`)
- `retry_stuck` — VERIFIED (`tasks/retry.py:78`)
- `backfill_embeddings` — VERIFIED (`tasks/embeddings.py:66`)
- `dispatch_webhook_task` — VERIFIED (`tasks/webhook.py:13`)
- `cleanup_inactive_subscribers` — VERIFIED (`tasks/subscribers.py:15`)

### Cleanup Tasks
- `cleanup_old_pipeline_logs` — VERIFIED (`tasks/cleanup.py:19`)
- `cleanup_expired_verifications` — VERIFIED (`tasks/cleanup.py:69`)
- `cleanup_stale_limiter_slots` — VERIFIED (`tasks/cleanup.py:110`)
- `consolidate_trend_memory` — VERIFIED (`tasks/cleanup.py:134`)
- `recalculate_impact_scores` — VERIFIED (`tasks/cleanup.py:171`)
- `purge_trend_memory` — VERIFIED (`tasks/cleanup.py:237`)
- `cleanup_old_article_versions` — VERIFIED (`tasks/cleanup.py:268`)

### run_stage() Signature
- `(stage, article_id, work_fn, task_self, run_id=None, skip_next="finalize", retry_countdown=30, retry_max=15)` — VERIFIED (`tasks/pipeline.py:353-362`)

### Quality Gates
- select: confidence="low" → review — VERIFIED (`tasks/select.py:127-128`)
- research: `_is_degenerate_research(brief)` → review — VERIFIED (`tasks/research.py:206`)
- write: `_is_degenerate_write(draft)` → review — VERIFIED (`tasks/write.py:128`)
- edit: validation fails → review — VERIFIED (`tasks/edit.py:160-185`)

### Degradation Path
- `degrade_stage()` in `services/pipeline_degradation.py` — VERIFIED (`services/pipeline_degradation.py:312-314`)
- `_degrade_and_advance` alias in `tasks/retry.py` — VERIFIED (`tasks/retry.py:46`)

### Beat Schedule
All 14 tasks match `config.py:get_beat_schedule()` — VERIFIED (see pipeline.md review for details)

### Rate Limiting
- LLM slots: per provider concurrency — VERIFIED (`tasks/pipeline.py:159-166`)
- Release in finally block — VERIFIED (`tasks/pipeline.py:400-408`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 47 | `pending` → `select` (success) | No direct PENDING→SELECT transition. Articles go PENDING→SELECTING (transient) then SELECTING→RESEARCHING on success. Stage transitions table omits SELECTING→RESEARCHING. | MEDIUM |
| 45-51 | Stage transitions table is incomplete | Missing: PENDING→RESEARCHING, SELECTING→SELECTED (transient), WRITTEN→EDITING (transient). Also omits that write disabled routes through finalize, not directly to edit. | MEDIUM |
| 66 | "All pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES`" | Not all tasks have this. Missing from: `retry_stuck` (`tasks/retry.py:67`), `generate_daily_newsletters` (`tasks/newsletter.py:476`), `publish_scheduled_articles` (`tasks/scheduler.py:10`), all cleanup tasks (`tasks/cleanup.py`), `cleanup_inactive_subscribers` (`tasks/subscribers.py:9`). | HIGH |
| 118 | "Uses `retry_max=20` in `run_stage()` (vs default 15)" | Correct value, but documentation uses "select" stage name while code passes "selector" as stage to run_stage | LOW |
| 199 | "Normal flow: pending → select → research → write → edit → review → done" | Review is not always in the normal flow. Articles can go directly from edit to DONE without review. Review is only reached via quality gates or `_should_route_to_review()`. | MEDIUM |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | `generate_daily_newsletters` lacks `max_retries` — could retry indefinitely on SMTP/connection errors | `tasks/newsletter.py:476-487` | MEDIUM | Decorator has `autoretry_for` but no `max_retries`. Other pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES`. |
| 2 | `retry_stuck` lacks `max_retries` — could retry indefinitely | `tasks/retry.py:67-77` | LOW | Has `autoretry_for` but no `max_retries`. Less critical since retry_stuck is an orchestration task. |
| 3 | `publish_scheduled_articles` lacks `max_retries` — could retry indefinitely | `tasks/scheduler.py:10` | LOW | Has `autoretry_for` but no `max_retries`. |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Fix stage transitions table to include SELECTING, WRITTEN, and RESEARCHING from PENDING | documentation | P1 |
| 2 | Add `max_retries=CELERY_TASK_MAX_RETRIES` to `generate_daily_newsletters`, `retry_stuck`, `publish_scheduled_articles`, and cleanup tasks | reliability | P1 |
| 3 | Clarify that "normal flow" doesn't always include review — review is a quality gate escape hatch | documentation | P2 |
| 4 | Document `generate_article_embedding` task (`tasks/embeddings.py:21`) — exists but not in tasks.md table | documentation | P2 |
| 5 | Document `send_single_email` task (`tasks/newsletter.py:34`) — exists but not in tasks.md | documentation | P3 |
| 6 | Note that cleanup tasks lack `max_retries` — may be intentional since they're short-lived | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 45-51 | Stage transitions table | Missing SELECTING, WRITTEN stages and PENDING→RESEARCHING transition | rewrite |
| 66 | "All pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES`" | Multiple tasks lack this parameter | update |

---

## Summary

- Verified: 35 claims
- Incorrect: 5 claims
- Bugs: 3 (HIGH: 0, MEDIUM: 2, LOW: 1)
- Improvements: 6
- Stale items: 2

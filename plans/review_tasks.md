# Review: tasks.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- **File Inventory matches actual files** — `tasks/` directory contains: `__init__.py`, `AGENTS.override.md`, `cleanup.py`, `crawl.py`, `edit.py`, `embeddings.py`, `extract.py`, `newsletter.py`, `pipeline.py`, `research.py`, `retry.py`, `scheduler.py`, `select.py`, `subscribers.py`, `webhook.py`, `write.py`
- **`run_all_sources` exists in `crawl.py`** — `tasks/crawl.py:269`
- **`aggregate_crawl_results` exists in `crawl.py`** — `tasks/crawl.py:215`
- **`process_item` exists in `extract.py`** — `tasks/extract.py:278`
- **`select_article` exists in `select.py`** — `tasks/select.py:59`
- **`research_article` exists in `research.py`** — `tasks/research.py:267`
- **`write_article` exists in `write.py`** — `tasks/write.py:48`
- **`edit_article` exists in `edit.py`** — `tasks/edit.py:445`
- **`generate_daily_newsletters` exists in `newsletter.py`** — `tasks/newsletter.py:488`
- **`publish_scheduled_articles` exists in `scheduler.py`** — `tasks/scheduler.py:11`
- **`backfill_embeddings` exists in `embeddings.py`** — `tasks/embeddings.py:66`
- **`retry_stuck` exists in `retry.py`** — `tasks/retry.py:78`
- **`cleanup_inactive_subscribers` exists in `subscribers.py`** — `tasks/subscribers.py:15`
- **`dispatch_webhook_task` exists in `webhook.py`** — `tasks/webhook.py:13`
- **Cleanup tasks match** — `cleanup_old_pipeline_logs` (`cleanup.py:19`), `cleanup_expired_verifications` (`cleanup.py:69`), `cleanup_stale_limiter_slots` (`cleanup.py:110`), `consolidate_trend_memory` (`cleanup.py:134`), `recalculate_impact_scores` (`cleanup.py:171`), `purge_trend_memory` (`cleanup.py:237`), `cleanup_old_article_versions` (`cleanup.py:268`)
- **`run_stage()` signature matches** — `tasks/pipeline.py:353-362` matches documented signature exactly
- **`run_all_sources` uses chord/group pattern** — `tasks/crawl.py:310-314`
- **`process_item` validated via `ProcessItemTask` schema** — `tasks/extract.py:302-318`
- **`select_article` returns `{score, confidence, reasoning}`** — `tasks/select.py:74-112` (returns via `SelectionResult`)
- **`research_article` calls subagent for web search** — `tasks/research.py:48-110`
- **`write_article` targets 200-400 words** — `tasks/write.py:58-101` (prompt requests Smart Brevity format)
- **`edit_article` calls subagent with context tools** — `tasks/edit.py:70-145`
- **`edit_article` assigns tags via `_assign_tags()`** — `tasks/edit.py:372`
- **`edit_article` validates via `validate_and_raise()`** — `tasks/edit.py:148-209`
- **`edit_article` calls `_post_finalize_article()`** — `tasks/edit.py:421`
- **`generate_daily_newsletters` calls `_fetch_articles_for_newsletter()`** — `tasks/newsletter.py:331`
- **`generate_daily_newsletters` calls `generate_executive_summary()`** — `tasks/newsletter.py:152`
- **`generate_daily_newsletters` calls `generate_main_newsletter()`** — `tasks/newsletter.py:168`
- **`generate_daily_newsletters` calls `_send_emails_parallel()`** — `tasks/newsletter.py:218`
- **Selector `retry_max=20`, `retry_countdown=15`** — `tasks/select.py:201-202`
- **Beat schedule has 14 tasks** — `config.py:146-203` matches documented count
- **Quality gates: select low confidence → review** — `tasks/select.py:127-146`
- **Quality gates: research degenerate → review** — `tasks/research.py:13-28`, `tasks/research.py:204-231`
- **Quality gates: write degenerate → review** — `tasks/write.py:12-27`, `tasks/write.py:128-154`
- **Quality gates: edit validation fail → review** — `tasks/edit.py:148-209`
- **`services/pipeline_degradation.py:_degrade_and_advance()`** — `services/pipeline_degradation.py:183-206`
- **`tasks/pipeline.py` has local `_degrade_and_advance` for retry.py** — referenced in `tasks/retry.py:46-48` which imports `degrade_stage` from `services/pipeline_degradation.py`

## Incorrect Claims

1. **Task signatures show `max_retries=3` as hardcoded** — `tasks.md:69,80,109,119,130,141,153`
   - Priority: **MEDIUM**
   - All task signatures in the documentation show `max_retries=3` as a literal value. In the actual code, tasks use `max_retries=CELERY_TASK_MAX_RETRIES` (e.g., `tasks/crawl.py:23`, `tasks/select.py:50`, `tasks/extract.py:269`), which defaults to 3 via `constants.py:6` but is configurable via the `CELERY_TASK_MAX_RETRIES` environment variable. The documentation should note this is configurable.

2. **`_should_route_to_review()` is documented as a public API** — `tasks.md:200`
   - Priority: **LOW**
   - `tasks.md:200` says "See `services/pipeline_degradation.py:_degrade_and_advance()` for the public degradation API." But `_should_route_to_review()` is a private function imported via `tasks/pipeline.py:26` as a re-export. The actual public API is `should_route_to_review()` at `services/pipeline_degradation.py:256-258`.

## Bugs Found

1. **Edit stage has undocumented quality report gate** — `tasks/edit.py:379-419`
   - Priority: **MEDIUM**
   - The quality gates table at `tasks.md:57-62` lists only validation failure as the edit stage gate. However, `tasks/edit.py:379-419` performs an additional quality report check (`build_quality_report()`) that can route articles to `review` when `quality_result.passed` is False. This is a third routing path that isn't documented.

2. **`retry_stuck` doesn't use `max_retries` parameter** — `tasks/retry.py:67-77`
   - Priority: **LOW**
   - The `retry_stuck` task decorator at `tasks/retry.py:67-77` doesn't include `max_retries=CELERY_TASK_MAX_RETRIES` like other tasks do. It only has `soft_time_limit=300, time_limit=360`. This means Celery's default retry behavior applies, which may differ from other tasks.

## Improvement Opportunities

1. **Document the Celery autoretry mechanism per task** — `tasks.md` task signatures
   - Priority: **MEDIUM**
   - The task signatures in the documentation show `max_retries=3` but don't document the `autoretry_for`, `retry_backoff`, `retry_backoff_max`, and `retry_jitter` parameters that differ between tasks. For example, `crawl_source` auto-retries on `(ConnectionError, TimeoutError)` while `select_article` auto-retries on `(ConnectionError, TimeoutError, ProviderServerError)`. These differences are operationally significant.

2. **Document the `verify_task()` call pattern** — `tasks.md` task signatures
   - Priority: **LOW**
   - Most tasks call `verify_task()` from `services/task_security.py` at the start (e.g., `tasks/select.py:67-69`, `tasks/crawl.py:271-273`). This is a security measure that validates task signatures but isn't mentioned in the documentation.

3. **Document `generate_article_embedding` task** — `tasks.md:19`
   - Priority: **LOW**
   - `tasks/embeddings.py:21` defines `generate_article_embedding` which is called from `tasks/edit.py:281` after article finalization. This task isn't listed in the file inventory table, though it's a leaf task rather than a scheduled task.

4. **Document the `process_item` dispatch chain** — `tasks.md:98-103`
   - Priority: **LOW**
   - The comment says "4. dispatch to select_article" but `tasks/extract.py:188` dispatches via `_dispatch_next(article_id, run_id=run_id, next_status="pending")` which goes through `services/pipeline_utils.py`, not directly to `select_article`. The dispatch is indirect.

## Stale Content

1. **Degradation path diagram is incomplete** — `tasks.md:26-41`
   - Priority: **MEDIUM**
   - The ASCII diagram shows `pending → select → research → write → edit → done` and `review → done` with fail arrows. But the actual flow is more complex: articles can skip stages (degradation), route to `review` from any quality gate, and the `written` status exists as a transient state. The diagram doesn't reflect the full complexity of the pipeline.

2. **`tasks/pipeline.py` local `_degrade_and_advance` claim** — `tasks.md:201`
   - Priority: **LOW**
   - `tasks.md:201` says "Note: `tasks/pipeline.py` has a local `_degrade_and_advance` for use by `retry.py` (task-layer only)." However, `tasks/retry.py:46-47` imports `degrade_stage` from `services/pipeline_degradation`, not from `tasks/pipeline.py`. The claim about a local function in `tasks/pipeline.py` appears to be stale — no such function exists there.

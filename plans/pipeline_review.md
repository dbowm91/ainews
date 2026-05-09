# Pipeline Architecture Review Plan

## Verified Claims
- **Stage transitions (pending → select → research → write → edit → done)**: Confirmed in `services/pipeline_utils.py` lines 10-19 (`_STAGE_TASKS` map) and `tasks/pipeline.py` line 389 (`run_stage` function orchestrates stages)
- **Degradation behavior when stages are disabled**: Confirmed in `tasks/pipeline.py` lines 296-303 (`_handle_disabled` function skips to next status) and `services/pipeline_degradation.py` (degrade_stage function with `_STAGE_DEGRADE_MAP`)
- **Dynamic fallback chain (from providers.yaml, not hardcoded)**: Confirmed in `services/llm/__init__.py` lines 58-98 (`get_provider_chain()` iterates through enabled providers from config and filters by circuit breaker state)
- **Newsletter generation 3-stage flow (reader → writer → editor)**: Confirmed in `services/newsletter_pipeline.py` lines 166-301 (`generate_executive_summary` runs reader/writer/editor stages sequentially)
- **3-stage LLM prompt structure**: Confirmed - Reader extracts themes, Writer generates first-draft, Editor polishes
- **Executive Summary returns summary text, used_fallback bool, fallback_stages list**: Confirmed in `services/newsletter_pipeline.py` lines 166-170 (return dict structure)
- **Batch size 500 for email sending**: Confirmed in `tasks/newsletter.py` line 85 (`BATCH_SIZE = 500`)
- **Newsletter idempotency key**: Confirmed - defined locally in `_generate_daily_newsletters_core()` (line 381 in tasks/newsletter.py)
- **Circuit breaker defaults (5 failures, 60s recovery, 120s window)**: Confirmed in `services/llm/__init__.py` lines 21-22 and `services/circuit_breaker.py` lines 43-52
- **Pipeline monitor tracks stage durations, failure rates, queue depth**: Confirmed in `services/pipeline_monitor.py` (record_stage_result, get_stage_stats, get_throughput_stats functions)
- **PipelineLog model with meta field (not metadata)**: Confirmed in AGENTS.md line 37 and actual code review shows `meta` JSON field
- **CELERY_BEAT_SCHEDULE from pipeline.yaml**: Confirmed in `config.py` lines 117-203
- **Article API endpoints at root level**: Confirmed in AGENTS.md line 40
- **Subagent location at services/subagent/**: Confirmed in AGENTS.md line 41

## Discrepancies

1. **Finalize step description incorrect**: Architecture doc (line 90-93) says "Update `finalized_at` timestamp" but Article model has no `finalized_at` field. Actual field is `published_at` (set in `tasks/edit.py` line 219)

2. **Backfill embeddings schedule wrong**: Architecture doc (line 146) says "Daily 2 AM" but actual schedule is `crontab(hour=2, minute=0)` from `config.py` line 201 - correct

3. **Max retries discrepancy**: Architecture doc (line 240) says "Max retries: 3 per stage" which matches `MAX_STAGE_RETRIES = 3` in constants.py. However, the actual code uses 15-20 retries in task definitions (e.g., `tasks/select.py` lines 201-202: retry_max=20, retry_countdown=15). The Celery-level max_retries is 3, but the retry_countdown values indicate more retry attempts are expected through the Celery autoretry mechanism

4. **Circuit breaker "2 minutes" vs actual implementation**: Architecture doc (line 248-249) says "After 5 failures in 2 minutes" but circuit breaker uses `window_seconds=120.0` (exactly 2 minutes) and `recovery_timeout=60.0` (not 60 seconds as documented). Actual behavior matches but naming is confusing

5. **Degradation table mismatch**: Architecture doc (line 201-207) shows:
   - "(select disabled) | research → write → edit → review" but code shows select disabled still auto-selects with score 6, not skips to research
   - Document says "edit disabled" goes to "review" but code shows it actually finalizes with draft as fallback (pipeline_degradation.py lines 165-179)

6. **Automatic retry backoff**: Architecture doc (line 241) says "Backoff: exponential (30s, 60s, 120s)" but actual Celery config uses `retry_backoff=True` with `retry_backoff_max=300` (exponential backoff with max 300s, not fixed 30/60/120 sequence)

7. **Topic newsletter generation**: Architecture doc (lines 130-136) describes topic newsletters but the code in `tasks/newsletter.py` only has `_generate_topic_newsletter_impl` which generates HTML but subscriber filtering by topic is not fully implemented (uses `newsletter_type` field)

## Improvement Recommendations

1. **[HIGH] Update finalized_at documentation**: The architecture doc references `finalized_at` but this field does not exist in the Article model. Document should reference `published_at` instead. Also clarify the "finalize" step is actually handled by `tasks/edit.py:_post_finalize_article()`

2. **[HIGH] Document the two-tier retry system**: There's a mismatch between document description (3 retries) and actual implementation (Celery task level + stage failure level). Need to document both levels clearly:
   - Celery task-level: max_retries=CELERY_TASK_MAX_RETRIES (3 by default)
   - Stage failure level: MAX_STAGE_RETRIES (3), MAX_TOTAL_RETRIES (10), MAX_STAGE_FAILURES (3)

3. **[MEDIUM] Clarify degradation behavior for disabled stages**: The degradation table in architecture doc doesn't match actual code behavior for "select disabled" case. Document should be updated to reflect that:
   - When select fails and degrades: sets selector_result with score 6 and proceeds to research
   - When research fails: degrades to write with minimal research brief
   - When write fails: degrades to edit with fallback article JSON
   - When edit fails: either routes to review (if threshold met) or finalizes with draft as final

4. **[MEDIUM] Document _should_route_to_review logic**: This function (pipeline_degradation.py:62) is critical for determining when articles go to review but is not mentioned in architecture doc. It checks `auto_publish_threshold` config - articles with impact_score >= threshold bypass review

5. **[MEDIUM] Add circuit breaker architecture diagram**: The circuit breaker behavior is described but no diagram. Should clarify:
   - Uses RedisCircuitBreaker with in-memory fallback
   - Key prefix: `ainews:circuit:{name}`
   - Failure tracking via Redis sorted sets with sliding window

6. **[LOW] Document PipelineLog meta field restriction**: AGENTS.md mentions SQLAlchemy reserved name restriction but architecture/pipeline.md doesn't explain why `meta` is used instead of `metadata`

7. **[LOW] Clarify newsletter lock mechanism**: The idempotency lock in `_generate_daily_newsletters_core()` uses a Lua script but this is not documented

## Bugs Found

1. **BUG: Newsletter lock idempotency_key reference error** (`tasks/newsletter.py:430`):
   The line `redis_client.setex(idempotency_key, 86400 * 2, "1")` uses `idempotency_key` which is defined locally in `_check_newsletter_lock()` (line 381: `idempotency_key = f"idempotency:newsletter:{today}"`). This will cause a `NameError` at runtime.

2. **BUG: Model reference in limiter.release after fallback** (`tasks/pipeline.py:436`):
   In the `finally` block of `run_stage()`, the code releases the limiter slot using `model if model is not None else None`. However, `model` is set from `_run_stage_core()` which returns the PRIMARY provider's model (from `_get_provider_for_stage`), not the actual model used if fallback occurred in `_try_stage_work`. Per AGENTS.md known issue: "Limiter Model Mismatch". The `provider_id` from `_try_stage_work` is the correct identifier to use, not `model`.

3. **BUG: Missing stage status in VALID_TRANSITIONS** (`constants.py:50-58`):
   The `VALID_TRANSITIONS` map is missing `"selecting": frozenset([...])` and `"selected": frozenset([...])`. Article status can be "selecting" (from `_transition_article_status` calls in `select.py`) but this isn't a valid transition target. While `STAGE_STATUS_MAP` maps these to stage names, the actual pipeline_status values used in code include "selecting", "selected", "written".

4. **BUG: _handle_disabled dispatches to wrong status when edit is disabled** (`tasks/pipeline.py:296-303`):
   When a stage is disabled and `skip_next="finalize"`, it calls `_finalize(article_id)`. But `_finalize` in `pipeline_degradation.py` (line 208) doesn't properly handle the case where edit is disabled - it just calls `_apply_fallback` and sets pipeline_status without going through the normal edit workflow validation.

5. **BUG: redis_client not passed to _generate_daily_newsletters_core** (`tasks/newsletter.py:419`):
   `_check_newsletter_lock` receives `redis_client` as first argument in the shared_task signature but `_generate_daily_newsletters_core` calls `_check_newsletter_lock(redis_client, task_id)` which passes redis_client correctly, but the lock_key used in `release_lock` (line 467) is not accessible within the finally block scope (defined inside `_check_newsletter_lock`).

## Layer Violations

1. **tasks/pipeline.py imports from services.pipeline_degradation** (line 26, 39):
   This creates a potential circular dependency since tasks is in the "outer" application layer and services.pipeline_degradation is a service module. Per AGENTS.md: "Services should NOT import from adapters" - but this doesn't explicitly prohibit tasks from importing from services. However, this is architectural smell - `degrade_stage` and `finalize_article` are imported and called from tasks/pipeline.py which is the Celery task layer.

2. **tasks/pipeline.py imports from services.logging_utils, services.tracing** (lines 31, 33):
   These are service utilities being used in the tasks layer, which is appropriate, but the imports are not consistent with clean layering conventions documented in AGENTS.md.

3. **services/newsletter_pipeline.py has direct redis_client access** (lines 106-135):
   The newsletter pipeline directly uses Redis for limiter acquire/release instead of going through the `services.limiter` abstraction. This is inconsistent - the article pipeline uses `services.limiter` via `_check_stage_limiter` but newsletter pipeline does its own Redis calls.

4. **Schema imports in newsletter pipeline** (`services/newsletter_pipeline.py:18`):
   `from schemas.pipeline import get_role_config` - this imports from schemas at the top level rather than using TYPE_CHECKING pattern, causing potential circular import issues if schemas.pipeline changes.

# Pipeline Architecture Review

## Summary

The `architecture/pipeline.md` document is largely accurate and well-structured. Core pipeline stages, statuses, transitions, and scheduled tasks are correctly documented. However, several discrepancies and gaps were identified between the documented behavior and actual implementation.

---

## Verified Claims

### Stage Statuses and Transitions
- **Verified**: Pipeline statuses in `constants.py` (lines 33-43) match the document exactly: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed`.
- **Verified**: `VALID_TRANSITIONS` dict in `constants.py` (lines 52-64) accurately reflects allowed transitions as documented.
- **Verified**: `_STAGE_TASKS` in `services/pipeline_utils.py` (lines 10-19) correctly maps statuses to task modules.

### Circuit Breaker Configuration
- **Verified**: `services/circuit_breaker.py` implements the documented circuit breaker pattern with correct defaults:
  - `failure_threshold=5` (line 43)
  - `recovery_timeout=60.0` (line 44)
  - `half_open_max_calls=1` (line 45)
  - `window_seconds=120.0` (line 46)

### Fallback Chain Implementation
- **Verified**: `services/llm/__init__.py` `get_provider_chain()` (lines 57-97) correctly implements the dynamic fallback chain from `providers.yaml` configuration order.

### Pipeline Stages
- **Verified**: `tasks/select.py` - Select stage with score 1-10, confidence levels, routing to `review` on low confidence.
- **Verified**: `tasks/research.py` - Research stage with `_is_degenerate_research()` quality gate (line 13-28).
- **Verified**: `tasks/write.py` - Write stage with `_is_degenerate_write()` quality gate (lines 12-27).
- **Verified**: `tasks/edit.py` - Edit stage with validation failure routing (lines 162-185) and `_should_route_to_review()` (lines 187-205).

### Scheduled Tasks
- **Verified**: All 13 scheduled tasks in `config.py` (lines 146-203) exist and match the document's table.

### Degradation Behavior
- **Verified**: `_STAGE_DEGRADE_MAP` in `services/pipeline_degradation.py` (lines 33-55) correctly maps stage failures to degraded next status.
- **Verified**: `degrade_stage()` function at line 240 correctly advances articles to next stage with degraded quality.

---

## Discrepancies and Issues

### 1. Valid Transitions: `PENDING` can transition to `SKIPPED` (not documented)

**File**: `constants.py:53`  
**Issue**: `PENDING` → `SELECTING` is documented, but the transition `PENDING` → `SKIPPED` is missing from the documented valid transitions table.

**Document says**:
```
Valid transitions:
- `pending` → `researching`, `review`
```

**Actual** (`constants.py:53`):
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
```

The document omits `SELECTING` in the table (line 54 shows it as separate from `PENDING`), and doesn't mention `SKIPPED` can happen from `PENDING` (when selector scores article < 6 and marks it skipped).

### 2. `write` stage degradation uses wrong model field

**File**: `services/pipeline_degradation.py:52`  
**Issue**: The `write` stage degradation uses `article.draft_article` but doesn't set `article.writer_model`. This is inconsistent with `tasks/write.py` which sets `article.writer_model = model` (line 104).

```python
"write": {
    "next_status": PipelineStatus.EDITING,
    "log_message": "Degraded: minimal draft for %s",
    "set_fields": lambda article: setattr(
        article, "draft_article", _build_fallback_article(article),
    ),
},
```

Should also set `article.writer_model = "fallback"` or similar for traceability.

### 3. `_degrade_and_advance` in `tasks/pipeline.py` has duplicate inline degradation logic

**File**: `tasks/pipeline.py:36-72`  
**Issue**: `_degrade_and_advance()` implements its own degradation logic for `select`, `research`, `write`, `edit` stages (lines 50-70) rather than delegating to `services/pipeline_degradation.py`. The inline logic for `select` (lines 50-60) directly sets `article.pipeline_status = "researching"` instead of using `PipelineStatus.RESEARCHING`.

```python
if failed_stage == "select":
    article.pipeline_status = "researching"  # Should use PipelineStatus
```

Additionally, `select` stage degradation in `tasks/pipeline.py` (lines 50-60) does NOT set `selector_result` to indicate auto-selection, unlike what `pipeline_degradation.py` does in its `_STAGE_DEGRADE_MAP` (line 37-41).

### 4. Documented degradation thresholds don't match implementation

**Document says** (line 250):
```
- Per-stage retries: 3 (configurable via `MAX_STAGE_RETRIES`)
```

**Actual** (`services/pipeline_degradation.py:94`):
```python
if article.degradation_count >= 2:
    article.pipeline_status = PipelineStatus.REVIEW
```

The document states "3 consecutive failures" but `degradation_count >= 2` routes to review, meaning only 2 degradations trigger review routing, not 3.

### 5. Edit stage degradation bypasses `_STAGE_DEGRADE_MAP`

**File**: `services/pipeline_degradation.py:129-179`  
**Issue**: The `_degrade_edit_stage()` function is a completely separate code path from the rest of the degradation logic in `_apply_degrade_config()`. It has its own `degradation_count >= 2` check (line 144) and doesn't use `_STAGE_DEGRADE_MAP["edit"]`.

The document says when `edit` fails, it "Finalizes immediately with fallback" (line 247), but the actual implementation (`_degrade_edit_stage`) has more complex logic including routing to `review` based on `degradation_count >= 2` or `_should_route_to_review(article)`.

### 6. Document's degradation table doesn't mention `degradation_count` threshold

**Document says** (line 244):
```
| Stage Fails | Degraded To |
|-------------|-------------|
| select | Auto-select with score 6, advance to research |
```

**Actual**: The document doesn't explain that articles with `degradation_count >= 2` get routed to `review` instead of advancing. This is a significant gap since it's a key quality gate.

### 7. Backoff configuration mismatch

**Document says** (line 289):
```
- Backoff: exponential (30s, 60s, 120s)
```

**Actual** (`tasks/select.py:51-56`):
```python
default_retry_delay=30,
retry_backoff=True,
retry_backoff_max=300,
retry_jitter=True,
```

The actual backoff is exponential with base 2 (Celery default), starting at 30s, doubling to 60s, 120s, 240s... max 300s. The document lists the first three values but doesn't capture the full exponential growth pattern or the max cap.

### 8. Newsletter batch size documented as 500, not visible in implementation

**Document says** (line 138):
```
# Batch size: 500
```

**Actual**: `services/newsletter.py` doesn't have a `batch_size` constant of 500. The newsletter generation uses `send_email` in batches but the batch size is not configurable via the same constant. Looking at `services/email.py` and `services/subscribers.py` would be needed to verify actual batch handling.

### 9. Pipeline Monitor implementation partial

**Document says** (line 258-264):
```
### Pipeline Monitor (`services/pipeline_monitor.py`)

Tracks pipeline health:
- Stage durations (avg, p95, p99)
- Failure rates per stage
- Queue depth per stage
- Source health correlation
```

**Actual**: `services/pipeline_monitor.py` (lines 1-290) implements:
- Stage duration histograms via `time_histogram` (in tasks, not here)
- Failure rates per stage (yes - `record_stage_result`, `get_stage_stats`)
- Queue depth per stage - **NOT IMPLEMENTED**
- Source health correlation - **NOT IMPLEMENTED**

### 10. Two-Tier Retry System document missing task-level max_retries detail

**Document says** (line 287-296):
```
**1. Celery Task Retry** (for transient errors)
- Max retries: 3 per task
- Backoff: exponential (30s, 60s, 120s)

**2. Stage Failure Retry** (for persistent failures)
- Per-stage retry limit: 3 (`MAX_STAGE_RETRIES`)
- After 3 per-stage retries: article degrades to next stage
```

**Gap**: The document doesn't mention that:
- The `retry_stuck` task (every 60 min) handles articles stuck with `retry_count >= _get_max_stage_retries()` and degrades them.
- Articles with `total_retries >= MAX_TOTAL_RETRIES (10)` are marked as `failed`.
- Per-stage failure limit (`MAX_STAGE_FAILURES`) of 3 consecutive failures at the same stage also marks the article as `failed`.

---

## Specific Bugs

### BUG-1: `_degrade_and_advance` uses string literal instead of `PipelineStatus`

**File**: `tasks/pipeline.py:56`  
```python
article.pipeline_status = "researching"
```
Should use `PipelineStatus.RESEARCHING`. While this works (string equality), it's inconsistent with the rest of the codebase and could cause issues if the constant values ever change.

### BUG-2: `_try_stage_work` returns before recording provider failure for `AuthError`

**File**: `services/llm/__init__.py:228-235`  
```python
except AuthError as auth_err:
    logger.error(...)
    record_provider_failure(provider_id, model, stage)
    raise auth_err
```

When `AuthError` is raised, `record_provider_failure` is called, but then the error is re-raised immediately without trying the fallback chain. The doc says fallback chain handles "RateLimitError, ProviderTimeoutError, ProviderServerError, ConnectionError" but `AuthError` is intentionally not retried. However, this means if the primary provider has an `AuthError`, the fallback providers are NOT tried. This may be intentional but is not documented.

### BUG-3: Limiter release uses wrong provider_id in `run_stage` finally block

**File**: `tasks/pipeline.py:436`  
```python
limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```

When `_handle_circuit_open_module` returns early (line 341 raises), `provider_id` and `model` may be `None`. The code handles this by using `model if model is not None else None`, but `provider_id` is used directly. If `provider_id` is `None` at this point (e.g., circuit opened before any provider was used), the limiter release may fail or behave incorrectly.

### BUG-4: Stage lock key uses string stage name but `STAGE_STATUS_MAP` isn't applied consistently

**File**: `tasks/pipeline.py:409`  
```python
lock_key = f"ainews:stage_lock:{article_id}:{stage}"
```

The `stage` parameter is the role name (e.g., "selector", "writer"), not the status. This is fine as long as each role maps to one stage, but `_degrade_and_advance` passes `failed_stage` which could be a status name like "writing" (from `STAGE_STATUS_MAP.get(failed_stage, failed_stage)` at line 44).

---

## Improvement Recommendations

### REC-1: Document the `degradation_count` threshold behavior

Add to the degradation section (after line 251):
```
Articles with `degradation_count >= 2` are routed to `review` regardless of stage, preventing infinite degradation loops.
```

### REC-2: Unify degradation logic

The inline `_degrade_and_advance` in `tasks/pipeline.py` duplicates logic from `services/pipeline_degradation.py`. Recommend refactoring to use a single `degrade_stage(article, failed_stage, run_id)` function that handles all stages uniformly.

### REC-3: Add `writer_model` field during write stage degradation

In `services/pipeline_degradation.py`, when degrading the `write` stage, also set `article.writer_model = "fallback"` to maintain traceability.

### REC-4: Fix string literal usage

Replace `article.pipeline_status = "researching"` with `article.pipeline_status = PipelineStatus.RESEARCHING` in `tasks/pipeline.py:56`.

### REC-5: Document `AuthError` behavior in fallback chain

The current fallback chain in `services/llm/__init__.py` only retries on `RateLimitError, ProviderTimeoutError, ProviderServerError, ConnectionError`. `AuthError` is not retried and causes immediate failure. Document this behavior.

### REC-6: Update Pipeline Monitor documentation

The document claims "Queue depth per stage" and "Source health correlation" are tracked, but these are not implemented in `services/pipeline_monitor.py`. Either implement them or remove from the documentation.

### REC-7: Add `select` stage's `selector_result` to degradation in `tasks/pipeline.py`

When `_degrade_and_advance` handles `select` stage (lines 50-60), it should set `article.selector_result = {"selected": True, "score": 6, "reason": "auto-selected after failure"}` to match the documented behavior.

### REC-8: Clarify Celery task retry backoff in documentation

The backoff description "(30s, 60s, 120s)" implies it stops at 120s. Clarify that it's exponential with max of 300s:
```
Backoff: exponential (30s, 60s, 120s, 240s, ... up to 300s max)
```
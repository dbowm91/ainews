# Pipeline Architecture Review

## Verified Claims

### Pipeline Status Values (constants.py:30-43)
**ACCURATE** - The 11 status values in the code match the document exactly: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed`.

### Valid Transitions (constants.py:52-63)
**PARTIALLY ACCURATE** - Code defines transitions, but some documented paths don't exist (see Discrepancy #1).

### Stage Tasks Map (services/pipeline_utils.py:10-19)
**ACCURATE** - `_STAGE_TASKS` correctly maps status → (module, task):
- pending/selecting → tasks.select.select_article
- selected/researching → tasks.research.research_article
- writing/written/editing/review → tasks.edit.edit_article

### Pipeline Monitor (services/pipeline_monitor.py)
**ACCURATE** - Tracks stage success/failure counts, throughput, and failure reason breakdown. Does NOT track p95/p99 percentiles, queue depth per stage, or source health correlation.

### PipelineLog Model (models/pipeline.py:36-60)
**ACCURATE** - Has run_id, stage, article_id, started_at, completed_at, status, error, meta fields. The doc's `status` field maps to the model's `level` field (values: "info", "warning", "error").

### Degradation Behavior (services/pipeline_degradation.py)
**MOSTLY ACCURATE** - Degradation maps match documented behavior except for edit stage which routes to DONE with fallback content (not immediately DONE as stated).

### Celery Beat Schedule (config.py:150-203)
**MOSTLY ACCURATE** - All documented tasks exist. Times slightly different (see Discrepancy #2).

### Circuit Breaker (services/circuit_breaker.py:31-170)
**ACCURATE** - Closed/Open/Half-open states, 5 failures in 2 minutes threshold, 60s recovery timeout, 1 probe request in half-open.

### Fallback Chain (services/llm/__init__.py:57-97)
**ACCURATE** - Dynamic chain from enabled providers in providers.yaml order, filters by circuit state. AuthError causes immediate failure without retry.

---

## Discrepancies & Issues

### CRIT-1: Invalid Transition `pending → skipped` in VALID_TRANSITIONS

**File**: `constants.py:52-63`

**Issue**: The documented transition `pending → skipped` is not in `VALID_TRANSITIONS`. Only `pending → selecting`, `pending → researching`, `pending → review` are allowed. The `SKIPPED` status is only reachable from `FAILED → pending` (for reprocessing), not directly from pending.

**Code location**: `constants.py:53`
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
```

**Doc claims**: "Valid transitions: ... pending → ... skipped ..."

**Fix**: Either remove `skipped` from pending transitions in the doc, or add it to VALID_TRANSITIONS if intentional.

---

### CRIT-2: `retry_max=20` in select_article Overrides Architecture Limit of 3

**File**: `tasks/select.py:193-203`

**Issue**: `run_stage()` is called with `retry_max=20`, but the architecture document says per-stage retries max is 3. This is a significant configuration override that bypasses the documented retry budget.

**Code location**: `tasks/select.py:201-202`
```python
return run_stage(
    "selector",
    article_id,
    work,
    task_self=self,
    run_id=run_id,
    skip_next=PipelineStatus.RESEARCHING,
    retry_countdown=15,   # Doc says 30s
    retry_max=20,          # Doc says 3
)
```

**Architecture says**: "Retry Limits: Per-stage retries: 3 (configurable via MAX_STAGE_RETRIES)"

**Impact**: The selector stage can retry up to 20 times (with countdown 15s) instead of the documented 3 times (with exponential backoff starting at 30s).

---

### CRIT-3: `finalized_at` Not Set During Finalize

**File**: `services/pipeline_degradation.py:209-239`

**Issue**: The architecture document states in Finalize: "Update `finalized_at` timestamp". The actual `_finalize()` function does NOT set `finalized_at`. It only sets `pipeline_status = DONE`, dispatches webhooks, and creates an article version.

**Code location**: `services/pipeline_degradation.py:227`
```python
article.pipeline_status = PipelineStatus.DONE
```

**What should happen**: Set `article.finalized_at = datetime.now(timezone.utc)` or similar.

**Contrast with edit.py:219**: `published_at` IS set in `_post_finalize_article()`:
```python
article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
```

---

### HIGH-1: Two Separate Cleanup Tasks at Different Times

**Doc says**: `cleanup-old-logs`: Daily 3 AM

**Actual** (`config.py:159-173`):
```
cleanup-old-logs: 3 AM
cleanup-old-versions: 3:45 AM
cleanup-old-versions_days_to_keep: 90
```

**Impact**: Two separate cleanup tasks at different times. `cleanup-old-versions` at 3:45 AM contradicts the document which implies a single "cleanup-old-logs" task at 3 AM.

---

### HIGH-2: Documented Cleanup at 3:45 AM But No `purge-trend-memory` Entry

**Issue**: The architecture document lists two tasks at 3:45 AM:
- `purge-trend-memory`: Daily 3:45 AM
- `cleanup-old-versions`: Daily 3:45 AM

But these are actually separate tasks in the code:
- `purge-trend-memory`: Daily 3:45 AM (line 167-169)
- `cleanup-old-versions`: Daily 3:45 AM (line 171-173)

The schedule at 3:45 AM has TWO tasks, not one. This is correct in code but confusing in doc.

---

### MED-1: Missing `_should_route_to_review` Definition in tasks/pipeline.py (BUG)

**File**: `tasks/edit.py:187`

**Issue**: `edit.py` imports `_should_route_to_review` from `tasks.pipeline`, but this function does NOT exist in `tasks/pipeline.py`. It only exists in `services/pipeline_degradation.py` as a private function.

**Code location - tasks/edit.py:187**:
```python
from tasks.pipeline import _should_route_to_review, _transition_article_status
```

**Verification**: `tasks/pipeline.py` has no definition of `_should_route_to_review` or `should_route_to_review`.

**Impact**: This is a **BUG** that will cause `ImportError` at runtime when the `edit` stage tries to route to review:
- `edit.py:189` calls `_should_route_to_review(article)`
- This function is NOT defined in `tasks/pipeline.py`
- It's only defined in `services/pipeline_degradation.py:63` as `_should_route_to_review`

**Fix**: Either:
1. Add `should_route_to_review = services.pipeline_degradation.should_route_to_review` to `tasks/pipeline.py` as a re-export
2. OR change the import in `edit.py:187` to import from `services.pipeline_degradation` directly

---

### MED-2: Task Naming Inconsistency

**Doc says**: `retry-stuck-articles`

**Code has**: `tasks.retry.retry_stuck` (in config.py:151-153)

**Issue**: The scheduled task name uses underscore (`retry_stuck`) but the document uses hyphen (`retry-stuck-articles`).

---

### MED-3: Newsletter Pipeline `_run_pipeline_stage` Limiter Release Uses Positional Args

**File**: `services/newsletter_pipeline.py:122-124`

**Issue**: When the newsletter pipeline stage succeeds, limiter release is called with positional args which could break if parameter order changes:

```python
limiter.release(
    provider_id, model, stage_config.timeout_seconds,
)
```

Compare to the article pipeline which uses named arguments for clarity:
```python
limiter.release(rc.provider, rc.model, rc.timeout_seconds)
```

This is not a bug yet but is inconsistent.

---

### LOW-1: `retry-stuck-articles` Lock Key Doesn't Match Other Redis Keys Pattern

**File**: `tasks/retry.py:100`

**Issue**: The lock key uses different pattern than stage locks:
```python
lock_key = "ainews:lock:retry_stuck"
```

Stage locks use: `"ainews:stage_lock:{article_id}:{stage}"`

Inconsistent naming but not a functional bug.

---

## Summary of Verified Claims

| Claim | Status |
|-------|--------|
| 11 pipeline statuses | ✅ Verified |
| Valid transitions table | ⚠️ Partially (pending→skipped missing) |
| Degradation behavior | ⚠️ Mostly (edit degradation differs) |
| Pipeline monitor features | ✅ Verified |
| PipelineLog model | ✅ Verified |
| Scheduled tasks | ⚠️ Timing differences |
| Circuit breaker | ✅ Verified |
| Fallback chain | ✅ Verified |
| `finalized_at` update | ❌ Not implemented |
| Per-stage retry limit 3 | ❌ Overridden to 20 in select |
| Exponential backoff 30s start | ❌ Countdown is 15s |

---

## Improvement Recommendations

| Priority | Issue | Recommendation |
|----------|-------|-----------------|
| CRIT | `finalized_at` not set | Add `article.finalized_at = datetime.now(timezone.utc)` in `_finalize()` |
| CRIT | `retry_max=20` overrides 3 | Either use `MAX_STAGE_RETRIES` or update doc to reflect actual behavior |
| CRIT | Invalid transition `pending→skipped` | Remove from doc or add to `VALID_TRANSITIONS` |
| HIGH | Two cleanup tasks at different times | Update doc to show both `cleanup-old-logs` (3 AM) and `cleanup-old-versions` (3:45 AM) |
| CRIT | Missing `_should_route_to_review` in tasks/pipeline.py | Add re-export from `services.pipeline_degradation` to `tasks/pipeline.py` |
| MED | Task naming inconsistency | Use `retry-stuck-articles` as task name to match doc |
| LOW | Newsletter pipeline limiter release | Use named arguments for consistency |
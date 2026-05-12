# Pipeline Architecture Review

**Review Date:** Tue May 12 2026  
**Reviewer:** Architecture Review Agent  
**Files Reviewed:**
- `architecture/pipeline.md`
- `services/newsletter_pipeline.py`
- `services/pipeline_degradation.py`
- `services/pipeline_failure.py`
- `services/llm/__init__.py`
- `constants.py`
- `tasks/pipeline.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `tasks/newsletter.py`

---

## Verified Claims

### 1. Stage Transitions with `selecting` and `selected` Statuses
**Status:** CONFIRMED

The `VALID_TRANSITIONS` in `constants.py` (lines 52-64) correctly includes `selecting` and `selected`:

```python
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
    PipelineStatus.SELECTING: frozenset([PipelineStatus.SELECTED, PipelineStatus.FAILED]),
    PipelineStatus.SELECTED: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.FAILED]),
    ...
}
```

### 2. Newsletter Idempotency Key Handling
**Status:** FIXED

The `idempotency_key` is properly defined in `_generate_daily_newsletters_core()` scope at `tasks/newsletter.py:429`:
```python
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
idempotency_key = f"idempotency:newsletter:{today}"
```
This was previously buggy (defined in nested function scope) but is now correctly placed.

### 3. Dynamic Fallback Chain
**Status:** CONFIRMED

`get_provider_chain()` in `services/llm/__init__.py` (lines 57-97) dynamically iterates through enabled providers in configuration order and filters out those with open circuits.

### 4. Degradation Behavior
**Status:** CONFIRMED with discrepancies

`_STAGE_DEGRADE_MAP` in `services/pipeline_degradation.py` (lines 33-55) correctly defines degradation paths:
```python
_STAGE_DEGRADE_MAP = {
    "select": {"next_status": PipelineStatus.RESEARCHING, ...},
    "research": {"next_status": PipelineStatus.WRITING, ...},
    "write": {"next_status": PipelineStatus.EDITING, ...},
}
```

### 5. Two-Tier Retry System
**Status:** CONFIRMED

- Celery task retry: 3 attempts with exponential backoff (`CELERY_TASK_MAX_RETRIES`)
- Stage failure retry: 3 per stage, 10 total (`MAX_STAGE_RETRIES`, `MAX_TOTAL_RETRIES`)

---

## Discrepancies

### 1. Architecture Doc Missing `selecting` Transition from `pending`

**Document says (line 54):**
```
- `pending` → `researching`, `review`
```

**Actual code (`constants.py:53`):**
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
```

**Impact:** Medium - The document is incomplete but not misleading. The `selecting` status IS in VALID_TRANSITIONS but just not documented as a possible first transition.

---

### 2. Architecture Doc Missing `WRITTEN` Status

**Document says (line 56):**
```
- `writing` → `editing`, `failed`
```

**Actual code:**
- `tasks/write.py:156`: Transitions to `PipelineStatus.EDITING` only after quality gate passes
- `constants.py:58`: `WRITTEN` status exists and transitions to `EDITING` or `FAILED`
- Quality gate failure in `write.py:128-154` routes to `review` not `failed`

The `written` status is a distinct intermediate state between `writing` and `editing` that the document doesn't mention.

---

### 3. Degradation for `selecting` Stage Failure Not Documented

**Document says (lines 237-238):**
```
| Stage Fails | Degraded To |
|-------------|-------------|
| select | Auto-select with score 6, advance to research |
```

**Issue:** The document doesn't clarify what happens when the `selecting` (in-progress) stage fails vs when `select` (configuration) is disabled. The actual degradation happens via `STAGE_STATUS_MAP` normalization of `selecting` to `select`.

---

### 4. Document Says Stage Disabled = Direct Transition, But Code Has Intermediate States

**Document says (lines 224-231):**
```
| Stage Disabled | Behavior |
|----------------|----------|
| select | Article goes directly to `researching` |
| research | Article goes directly to `writing` |
```

**Actual behavior:**
- When selector is disabled, `skip_next=PipelineStatus.RESEARCHING` is passed to `run_stage` (line 200 in `select.py`)
- The article still goes through the `selecting` status before being auto-selected
- This is a subtle but important distinction - the selector is not truly "skipped" but rather "auto-selects with score 6"

---

### 5. `pending → skipped` Valid Transition Not Documented

The architecture doc doesn't mention that `pending` can transition to `skipped` (via `selecting → skipped` path when selector determines article should be discarded).

---

### 6. Degradation Documented as `researching` but Code Uses `WRITING`

**Document says:**
```
| Stage Fails | Degraded To |
|-------------|-------------|
| research | Uses source text only (impact_score=30), advance to write |
```

**Actual code (`pipeline_degradation.py:43-47`):**
```python
"research": {
    "next_status": PipelineStatus.WRITING,  # Note: WRITING not RESEARCHING
    ...
}
```

This is correct - the degraded article should go to `writing` stage, not `researching`. The document is using imprecise language.

---

## Bugs Found

### BUG-1: Limiter Release Uses Wrong Provider ID When Fallback Occurs

**Severity:** Medium  
**Location:** `tasks/pipeline.py:434-436`

**Description:**
```python
finally:
    if limiter is not None:
        limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```

The `limiter.acquire()` at line 415 uses `rc.provider, rc.model` (primary provider info set at line 414). However, if `_run_stage_core` internally falls back to a different provider via `_try_stage_work`, the returned `provider_id` from `_try_stage_work` may be different from `rc.provider`.

**Scenario:**
1. Primary provider acquired at `rc.provider` (e.g., "provider-a")
2. Primary fails, fallback succeeds with "provider-b"
3. `provider_id` returned as "provider-b"
4. Release called with `provider_id="provider-b"`, not `rc.provider="provider-a"`
5. Primary provider's slot is NOT properly released

**AGENTS.md Note:** Claims "FIXED - The model returned by `_run_stage_core` is now the actual model used" but this only addresses the `model` variable, not the `provider_id` mismatch.

**Recommended Fix:**
Track the actually-used provider_id from `_try_stage_work` and ensure release uses the same values that were acquired, OR acquire the limiter AFTER the actual provider is determined.

---

### BUG-2: `pending` Not in `VALID_TRANSITIONS` for Direct `skipped` Path

**Severity:** Low  
**Location:** `constants.py:97-108`

**Description:**
`VALID_PIPELINE_STATUSES` (line 97-108) does not include `SELECTING` or `SELECTED`:
```python
VALID_PIPELINE_STATUSES = frozenset({
    PipelineStatus.PENDING,
    PipelineStatus.RESEARCHING,
    ...
})
```

But `PENDING` can legitimately transition to `SKIPPED` via the path `pending → selecting → skipped`. The `is_valid_transition` function (line 67-70) allows same-status transitions which masks this:
```python
return to_status in valid_next or to_status == from_status
```

This means `pending → skipped` appears valid because `pending == pending`. However, the explicit path `pending → skipped` is not in `VALID_TRANSITIONS`.

**Recommended Fix:** Either add explicit transitions or clarify that `is_valid_transition` allows no-op transitions.

---

## Improvement Recommendations

### REC-1: Document the `WRITTEN` Status

The architecture document should explicitly mention the `written` status as an intermediate state between `writing` and `editing`. This status is significant because:
- It's a quality gate checkpoint
- Articles that fail the write quality gate go to `review` from this state
- The transition `writing → written` is distinct from `written → editing`

### REC-2: Clarify Stage Disabled vs Stage Failure Degradation Paths

The architecture doc conflates "disabled" behavior with "failure" behavior. These are distinct scenarios:
1. **Stage disabled:** Configuration-based bypass, article goes to next status
2. **Stage failure:** Persistent errors after retries, article degrades with reduced quality

### REC-3: Add Sequence Diagram for Normal Flow

The current architecture doc shows stages as boxes but doesn't show the actual state machine transitions. A state diagram would clarify:
- When `selecting` is intermediate (before `selected` or `researching`)
- When `written` is intermediate (between `writing` and `editing`)
- Which transitions are conditional (quality gates)

### REC-4: Update Subagent Signature Documentation

AGENTS.md documents:
```python
run_subagent(task, context, tools, model)
```

Actual signature (`services/subagent/runner.py:38-44`):
```python
def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:
```

The documented signature is significantly different from the actual implementation.

---

## Layer Violations

### LV-1: URL Validation Duplication

**Severity:** Maintenance burden (not a runtime bug)  
**Files:** `utils/url.py`, `services/url.py`

Both files contain:
- `UnsafeURLError` class
- `_BLOCKED_NETWORKS` list
- `_TTLCache` class with identical implementation
- `_resolve_and_check()` function with identical logic
- `validate_url_safe()` function with identical logic
- Global mutable state: `_dns_cache`, `_dns_cache_lock`, `_dns_executor`

`services/url.py` imports from `utils/url.py` (line 15):
```python
from utils.url import TRACKING_PARAMS, normalize_title, normalize_url
```

But re-implements all SSRF protection locally instead of using `utils/url.py`'s `validate_url_safe`.

**Impact:** Violates DRY principle. Security fixes to SSRF protection must be made in two places.

**Recommendation:** Have `services/url.py` import and re-export from `utils/url.py`, or have adapters import directly from `utils/url.py` as the architecture doc suggests.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 5 |
| Discrepancies | 6 |
| Bugs Found | 2 |
| Improvement Recommendations | 4 |
| Layer Violations | 1 |

**Overall Assessment:** The pipeline architecture is well-implemented with most claims verified. The main concerns are:
1. Documentation gaps (missing `WRITTEN` status, incomplete transitions)
2. Limiter release bug when fallback providers are used
3. URL validation code duplication

The core stage transitions (pending → select → research → write → edit → done) are correctly implemented, and the degradation/failure systems are sound.

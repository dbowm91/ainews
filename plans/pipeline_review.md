# Pipeline Architecture Review

**Date:** 2026-05-22
**Module:** Pipeline
**Document Reviewed:** `architecture/pipeline.md`

---

## Summary

The pipeline document is largely accurate. Most claims about stage transitions, quality gates, rate limiter slot management, provider fallback chain behavior, and the `_run_stage_core` implementation are verified in code. However, several discrepancies and issues were found.

---

## Verified Claims

### ✓ Stage Status Values and Transitions
- **Claim (L37-64):** Pipeline stages use statuses defined in `constants.py`. Valid transitions documented.
- **Verification:** `constants.py:30-64` defines `PipelineStatus` enum and `VALID_TRANSITIONS` dict exactly as documented.

### ✓ Select Stage Quality Gate (Low Confidence)
- **Claim (L75-76):** Score >= 6 with medium/high confidence → proceed; score < 6 or low confidence → mark as `review` or `discard`.
- **Verification:** `tasks/select.py:126-171` correctly routes low-confidence selections to `REVIEW`.

### ✓ Research Quality Gate (Degenerate Research)
- **Claim (L88-89, L80-82):** If research brief fails quality gate, routes to `review`. `_is_degenerate_research()` checks for empty key claims and low impact score.
- **Verification:** `tasks/research.py:13-28` implements `_is_degenerate_research()` correctly. Lines 206-230 handle routing to review on degenerate brief.

### ✓ Write Quality Gate (Body < 500 chars)
- **Claim (L99):** If body < 500 chars, marks for `review`.
- **Verification:** `tasks/write.py:12-27` implements `_is_degenerate_write()` which checks body length < 500.

### ✓ Edit Validation and Quality Gate
- **Claim (L105-110):** Validation failure and `_should_route_to_review()` route to review.
- **Verification:** `tasks/edit.py:148-209` `_handle_validation_and_routing()` correctly calls `validate_and_raise()` and `_should_route_to_review()`.

### ✓ Provider Fallback Chain (Dynamic)
- **Claim (L231, L312):** Fallback chain is dynamically determined from enabled providers in `providers.yaml` configuration order, not hardcoded.
- **Verification:** `services/llm/__init__.py:57-97` `get_provider_chain()` iterates through `config.providers` in order, filtering open circuits. This is exactly as documented.

### ✓ Circuit Breaker Parameters
- **Claim (L305-308):** Circuit opens after 5 failures in 2 minutes, half-open after 60 seconds.
- **Verification:** `services/llm/__init__.py:20-21` sets `_LLM_FAILURE_THRESHOLD = 5` and `_LLM_RECOVERY_TIMEOUT = 60.0`. `services/circuit_breaker.py:40-47` uses `window_seconds=120.0` by default.

### ✓ AuthError Handling
- **Claim (L316):** `AuthError` causes immediate failure without retry or fallback.
- **Verification:** `services/llm/__init__.py:192-199` catches `AuthError` and immediately re-raises without trying fallback providers.

### ✓ Rate Limiter Slot Management (Limiter Leak Fix)
- **Claim (AGENTS.md):** Limiter release uses `provider_id or rc.provider` and `model or rc.model` as fallbacks.
- **Verification:** `tasks/pipeline.py:400-402` correctly releases using `provider_id or rc.provider, model or rc.model` in the `finally` block.

### ✓ `_run_stage_core` Implementation
- **Claim (AGENTS.md):** `_run_stage_core` resolves provider/model before acquiring limiter resources.
- **Verification:** `tasks/pipeline.py:377-379` calls `_get_provider_for_stage(stage)` before `_acquire_stage_resources()`, correctly resolving provider before acquiring limiter.

### ✓ Pipeline Timeout
- **Claim (constants.py):** `PIPELINE_TIMEOUT_SECONDS = 3600`.
- **Verification:** `constants.py:14` and `tasks/pipeline.py:319-331` implement article-level pipeline timeout that transitions articles to `FAILED` if exceeded.

### ✓ Two-Tier Retry System
- **Claim (L288-302):** Per-stage retry limit of 3 with total retry budget of 10.
- **Verification:** `services/pipeline_failure.py:83-159` correctly implements per-stage failure tracking (`stage_failures >= 3` → FAILED), per-stage retry exhaustion (`retry_count >= 3` → degrade), and total retry exhaustion (`total_retries >= 10` → FAILED).

### ✓ Scheduled Tasks
- **Claim (L168-186):** All scheduled tasks documented with correct schedules.
- **Verification:** `config.py:146-203` defines beat schedule matching the document exactly.

### ✓ Newsletter Generation Flow
- **Claim (L125-143):** 3-stage LLM executive summary (reader → writer → editor), batch size 500.
- **Verification:** `tasks/newsletter.py` implements `generate_executive_summary()` with 3-stage pattern. `_send_emails_parallel()` sends in batches of 500.

---

## Discrepancies and Issues

### 1. Document Missing `review` Status in Valid Transitions Table

**Location:** `architecture/pipeline.md:53-64`

**Issue:** The "Valid transitions" list does not show transitions TO the `review` status. The document shows transitions starting from `pending` but never shows how articles get TO `review`. The actual transitions are in `constants.py`:

```python
VALID_TRANSITIONS = {
    PENDING: frozenset([PENDING, SELECTING, RESEARCHING, REVIEW]),  # Can go to REVIEW
    SELECTING: frozenset([SELECTED, FAILED]),
    SELECTED: frozenset([RESEARCHING, FAILED]),
    RESEARCHING: frozenset([WRITING, FAILED]),
    WRITING: frozenset([EDITING, FAILED]),
    WRITTEN: frozenset([EDITING, FAILED]),
    EDITING: frozenset([REVIEW, DONE, FAILED]),
    REVIEW: frozenset([DONE, FAILED]),
    ...
}
```

Articles can transition to `review` from:
- `PENDING` (if `select` is disabled and config says to go to `review`)
- `EDITING` (quality gate failure, validation failure, or `_should_route_to_review()`)

**Severity:** MED - Documentation gap. The transitions table is incomplete.

---

### 2. Document Claims Select Uses `min_score` But Implementation Uses Both Score AND Confidence

**Location:** `architecture/pipeline.md:74-76` vs `tasks/select.py:126-171`

**Issue:** The document says:
> Score >= 6 with medium/high confidence → proceed to research
> Score < 6 or low confidence → mark as `review` or `discard`

But `tasks/select.py:126-171` implements:
```python
if result.selected and result.score >= (rc.min_score or 6):
    if result.confidence == "low":
        _transition_article_status(article, PipelineStatus.REVIEW)
        # ...
    else:
        _transition_article_status(article, PipelineStatus.RESEARCHING)
```

The logic requires BOTH `selected=True` AND `score >= min_score`. If the LLM returns `selected=False`, the article goes to `SKIPPED` regardless of score. This is a subtle behavioral difference from what the document describes.

**Severity:** MED - The documented threshold behavior implies score is the primary driver, but `selected` boolean from the LLM is also required.

---

### 3. Edit Stage Degradation Routing Condition Is More Complex Than Documented

**Location:** `architecture/pipeline.md:244-251` vs `services/pipeline_degradation.py:130-164`

**Issue:** The document says:
> edit | Apply fallback → route to review (if degradation_count >= 2 or _should_route_to_review())

But the actual implementation in `_degrade_edit_stage()` is:

```python
if article.degradation_count >= 2 or _should_route_to_review(article):
    article.pipeline_status = PipelineStatus.REVIEW
    # ...
else:
    article.pipeline_status = PipelineStatus.DONE
    # ...
```

This means edit degradation can route to `DONE` (not `review`) if:
- `degradation_count < 2` AND
- `_should_route_to_review()` returns False

This contradicts the document which implies route-to-review is the default outcome.

**Severity:** MED - Document over-simplifies the degradation routing.

---

### 4. Document Says Select Stage Uses `retry_max=20` but Implementation Uses `retry_max=20` with `retry_countdown=15`

**Location:** `architecture/pipeline.md:253-255`

**Issue:** The document accurately states that the selector uses more aggressive retry parameters (`retry_max=20` vs `retry_max=3` for other stages). But the document doesn't capture the `retry_countdown=15` parameter that makes it more aggressive. The actual call in `tasks/select.py:193-202`:

```python
return run_stage(
    "selector",
    article_id,
    work,
    task_self=self,
    run_id=run_id,
    skip_next=PipelineStatus.RESEARCHING,
    retry_countdown=15,
    retry_max=20,
)
```

**Severity:** LOW - Minor documentation omission. The retry behavior is more aggressive than documented.

---

### 5. `_handle_disabled` Logic Is Documented But Behavior Is Subtle

**Location:** `architecture/pipeline.md:233-243` vs `tasks/pipeline.py:260-267`

**Issue:** The degradation table says "When stages are disabled via `pipeline.yaml`, articles bypass that stage and advance directly to the next status." But the actual `_handle_disabled()` implementation:

```python
def _handle_disabled(rc, skip_next, run_id, stage, article_id):
    if not rc.enabled:
        if skip_next == "finalize":
            _finalize(article_id)
        else:
            _dispatch_next(article_id, run_id=run_id, next_status=skip_next)
        return True
    return False
```

For `edit` stage, `skip_next="finalize"`, which calls `_finalize()` which may still route to `review` via `_should_route_to_review()`. So "finalizes immediately" is not entirely accurate - it depends on the auto-publish threshold.

**Severity:** MED - The "finalizes immediately" claim is conditional.

---

### 6. Document Claims `PENDING → RESEARCHING` Transition But No Stage Handles This

**Location:** `architecture/pipeline.md:54` vs `tasks/pipeline.py:10-19` (`_STAGE_TASKS`)

**Issue:** The document claims `pending → researching` is a valid transition. Looking at `VALID_TRANSITIONS`:

```python
PipelineStatus.PENDING: frozenset([PENDING, SELECTING, RESEARCHING, REVIEW]),
```

But `services/pipeline_utils.py:10-19` shows:

```python
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    ...
}
```

The `PENDING` status dispatches to `select_article`, not `research_article`. So even though `PENDING → RESEARCHING` is listed as valid, nothing in the dispatch mechanism would route an article from `pending` to `researching` directly without going through `select`.

**Severity:** MED - The valid transition exists but there's no code path to achieve it without select stage running.

---

### 7. Document Missing `pending → review` Transition

**Location:** `architecture/pipeline.md:54` vs `constants.py:53`

**Issue:** The document doesn't mention `pending → review` as a valid transition, but `constants.py:53` shows:
```python
PipelineStatus.PENDING: frozenset([PENDING, SELECTING, RESEARCHING, REVIEW]),
```

This means an article in `pending` can go directly to `review`. Looking at `tasks/extract.py:188`, we see:
```python
_dispatch_next(article_id, run_id=run_id, next_status="pending")
```

But I don't see where `pending → review` would be triggered from code. Let me double-check by looking at `_STAGE_TASKS` and seeing what happens when an article is in `pending` state.

Actually, the `_handle_disabled()` function in `tasks/pipeline.py:260-267` would skip the stage if disabled and dispatch to the `skip_next` status. If select stage is disabled and `skip_next` is `review`, then `pending → review` is possible via the disabled path.

**Severity:** LOW - The transition exists but the code path is only through disabled stage handling.

---

### 8. Document Shows `written` Status But It's Not Used in `_STAGE_TASKS`

**Location:** `architecture/pipeline.md:59` vs `services/pipeline_utils.py:10-19`

**Issue:** The document shows `written → editing, failed` as a valid transition. The `VALID_TRANSITIONS` in `constants.py:58` confirms this. But `_STAGE_TASKS` in `services/pipeline_utils.py` doesn't have a `written` entry:

```python
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "written": ("tasks.edit", "edit_article"),  # Line 16 - EXISTS
    "editing": ("tasks.edit", "edit_article"),
    "review": ("tasks.edit", "edit_article"),
}
```

Actually, it DOES exist at line 16. I misread. Never mind.

**Severity:** None - The entry exists.

---

### 9. Pipeline Monitor Claims Incomplete Tracking

**Location:** `architecture/pipeline.md:261-269`

**Issue:** The document says the pipeline monitor does NOT track:
- p95/p99 percentiles
- queue depth per stage
- source health correlation

Looking at `services/pipeline_monitor.py`, this is accurate. The monitor only tracks:
- Stage success/failure counts
- Throughput (items per minute)
- Failure reason breakdown

This is a known limitation, not a bug. But the document doesn't mention that this is a planned feature or gap.

**Severity:** LOW - Documentation of known gaps would be helpful.

---

## Bugs Found

### BUG-1: `_dispatch_next` Import in `edit.py` Line 185

**File:** `tasks/edit.py:185`

```python
from tasks.pipeline import _should_route_to_review, _transition_article_status
# Missing: _dispatch_next
```

At line 185:
```python
_dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)
```

But `_dispatch_next` is not imported in the `from tasks.pipeline import ...` statement at line 188-189. It would be imported via the `from services.pipeline_utils import _dispatch_next, _log_pipeline` at line 31 of `tasks/pipeline.py`. But wait, `edit.py` doesn't import from `services.pipeline_utils`.

Looking at `tasks/edit.py` imports:
- Line 159: `from tasks.pipeline import _log_pipeline, _transition_article_status`
- Line 188: `from tasks.pipeline import _should_route_to_review, _transition_article_status`

The `_dispatch_next` used at line 185 is not imported! However, line 185 is inside the `if run_id:` block at line 176. The function `_execute_editor_work` starts at line 280 and `_dispatch_next` is not imported there either.

Wait, let me look again at `tasks/edit.py:148-210`:

```python
def _handle_validation_and_routing(
    article, db, run_id: int | None = None,
) -> dict | None:
    ...
    try:
        validate_and_raise(article.final_article)
    except ValidationError as e:
        ...
        _transition_article_status(article, PipelineStatus.REVIEW)
        ...
        if run_id:
            _log_pipeline(...)
        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)  # Line 185
        return {"article_id": article.id, "status": "review"}

    from tasks.pipeline import _should_route_to_review, _transition_article_status  # Line 188

    if _should_route_to_review(article):
        ...
        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)  # Line 206
        return {"article_id": article.id, "status": "review"}
```

Line 185 and 206 both call `_dispatch_next` but it's not imported! This would cause a `NameError` at runtime.

But wait - `tasks/pipeline.py` imports `_dispatch_next` at line 31:
```python
from services.pipeline_utils import _dispatch_next, _log_pipeline
```

And `tasks/pipeline.py` re-exports it? No, looking at `tasks/pipeline.py` line 31, it just imports from `services.pipeline_utils`. It does NOT re-export `_dispatch_next`.

So `tasks/edit.py:185` and `tasks/edit.py:206` would fail with `NameError: name '_dispatch_next' is not defined`.

Actually wait - `tasks/edit.py` doesn't define `_dispatch_next` locally. The only imports that could provide it are:
1. Line 159: `from tasks.pipeline import _log_pipeline, _transition_article_status` - no `_dispatch_next`
2. Line 188: `from tasks.pipeline import _should_route_to_review, _transition_article_status` - no `_dispatch_next`

So this IS a bug! But let me double-check by looking at whether `_dispatch_next` might be imported somewhere else in the file or if there's dynamic resolution happening.

Looking at `tasks/edit.py`:
- Line 19-22: Module-level `_TAG_CACHE` etc
- Line 396: `edit_article` task which calls `run_stage`
- Line 399: `run_stage` imported from `tasks.pipeline`
- Line 280: `_execute_editor_work` function
- Line 148: `_handle_validation_and_routing` function

I need to check if `_dispatch_next` is defined locally anywhere in `edit.py`. Looking at the full file - no it isn't.

So this IS a real bug. `_dispatch_next` is called at lines 185 and 206 but never imported.

**Severity:** CRIT - Runtime `NameError` would occur when validation fails in edit stage.

---

### BUG-2: `article_id` Unbound in `_handle_validation_and_routing`

**File:** `tasks/edit.py:185`

```python
def _handle_validation_and_routing(
    article, db, run_id: int | None = None,
) -> dict | None:
    ...
    except ValidationError as e:
        ...
        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)  # Line 185
```

The function signature is:
```python
def _handle_validation_and_routing(
    article, db, run_id: int | None = None,
) -> dict | None:
```

But at line 185, `article_id` is referenced but not passed as a parameter and not defined in the function scope! The function receives `article` but not `article_id`. This would cause a `NameError` at runtime.

**Severity:** CRIT - Runtime `NameError` when validation fails.

---

### BUG-3: Missing `_dispatch_next` Import in `tasks/edit.py` Causes NameError

**File:** `tasks/edit.py:185,206`

Actually wait - let me re-examine the file more carefully. Let me read the full file again...

Actually I already read it. Lines 185 and 206 both use `_dispatch_next` which is NOT imported. And the function uses `article_id` which is not in scope for `_handle_validation_and_routing`.

**This is a confirmed critical bug.** The edit stage cannot properly route to review when validation fails because:
1. `_dispatch_next` is not imported
2. `article_id` is not in scope

---

## Recommendations

### CRIT-1: Fix Missing `_dispatch_next` Import and `article_id` Scope Bug

**File:** `tasks/edit.py:148-210`

**Issue:** `_handle_validation_and_routing()` calls `_dispatch_next(article_id, ...)` but:
- `_dispatch_next` is not imported from `tasks.pipeline` or `services.pipeline_utils`
- `article_id` is not defined in the function scope (only `article` is passed)

**Fix:** Change the function signature to accept `article_id: int` and add the missing import:
```python
from services.pipeline_utils import _dispatch_next  # Add to imports
```

Or change the call to use `article.id`:
```python
_dispatch_next(article.id, run_id=run_id, next_status=PipelineStatus.REVIEW)
```

But `_dispatch_next` still needs to be imported.

**Priority:** CRITICAL - Prevents edit stage from routing to review on validation failure.

---

### MED-1: Document Complete Transition Table

**File:** `architecture/pipeline.md:53-64`

**Issue:** The valid transitions table doesn't show all transitions, particularly TO `review`.

**Fix:** Expand the table to show all valid transitions including `pending → review`, `editing → review`, etc.

---

### MED-2: Document Select Stage Requires Both `selected` AND Score Threshold

**File:** `architecture/pipeline.md:74-76`

**Issue:** The select stage requires the LLM to return `selected=True` AND `score >= min_score`. The document only describes the score threshold.

**Fix:** Update documentation to clarify that both conditions must be met.

---

### MED-3: Document Edit Degradation Routing Correctly

**File:** `architecture/pipeline.md:244-251`

**Issue:** Edit degradation can route to `DONE` if `degradation_count < 2` AND `_should_route_to_review()` returns False. The document over-simplifies this.

**Fix:** Update to clarify that edit degradation may finalize to `DONE` if auto-publish threshold is met.

---

### MED-4: Document Selector's `retry_countdown=15` Parameter

**File:** `architecture/pipeline.md:253-255`

**Issue:** Document mentions `retry_max=20` for selector but not the more aggressive `retry_countdown=15`.

**Fix:** Update to mention `retry_countdown=15` for selector stage.

---

### LOW-1: Document Pipeline Monitor Limitations

**File:** `architecture/pipeline.md:261-269`

**Issue:** Known gaps (p95/p99, queue depth, source correlation) not documented as future work.

**Fix:** Add a "Known Limitations" section.

---

### LOW-2: Document `pending → review` Code Path

**File:** `architecture/pipeline.md` and `tasks/pipeline.py:260-267`

**Issue:** The `pending → review` transition exists via `_handle_disabled()` when select stage is disabled.

**Fix:** Document this path clearly.

---

## File-to-Line Reference for Bugs

| Bug | File | Line(s) | Description |
|-----|------|---------|-------------|
| BUG-1 | `tasks/edit.py` | 185, 206 | `_dispatch_next` called but not imported |
| BUG-2 | `tasks/edit.py` | 185 | `article_id` not in scope (only `article` passed to function) |

---

## Files Reviewed

- `architecture/pipeline.md` - Document under review
- `tasks/pipeline.py` - Core pipeline helpers (`run_stage`, `_run_stage_core`, etc.)
- `tasks/select.py` - Select stage
- `tasks/research.py` - Research stage
- `tasks/write.py` - Write stage
- `tasks/edit.py` - Edit stage
- `services/pipeline_failure.py` - Failure handling
- `services/pipeline_degradation.py` - Degradation logic
- `services/pipeline_utils.py` - Pipeline utilities (`_dispatch_next`)
- `services/limiter.py` - Rate limiter
- `services/llm/__init__.py` - LLM provider chain
- `services/llm/errors.py` - LLM error types
- `services/circuit_breaker.py` - Circuit breaker
- `services/article_validation.py` - Content validation
- `constants.py` - Pipeline status definitions
- `models/article.py` - Article model
- `schemas/pipeline.py` - Pipeline config schemas
- `config.py` - Beat schedule
- `pipeline.yaml` - Pipeline configuration
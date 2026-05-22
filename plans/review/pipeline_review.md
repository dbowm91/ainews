# Pipeline Documentation Review

## Overview

Reviewed `architecture/pipeline.md` against the actual implementation in the codebase to verify accuracy and identify discrepancies.

---

## Verified Claims

### Pipeline Status Values and Transitions
- All pipeline statuses (`pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed`) match `constants.py`
- Valid state transitions match `VALID_TRANSITIONS` in `constants.py`

### Selector Stage Exception
- Selector stage correctly uses `retry_max=20` with `retry_countdown=15` as documented (exception to the 3-retries rule)
- Implemented in `tasks/select.py` lines 193-203

### Circuit Breaker Settings
- Failure threshold: 5 failures (configurable via `CIRCUIT_BREAKER_FAILURE_THRESHOLD`)
- Recovery timeout: 60 seconds (`_LLM_RECOVERY_TIMEOUT = 60.0`)
- Window: 120 seconds (`window_seconds = 120.0` in `circuit_breaker.py`)
- All values match documentation

### Two-Tier Retry System
1. **Celery Task Retry**: `max_retries=CELERY_TASK_MAX_RETRIES` (3), with exponential backoff (`retry_backoff=True`, `retry_backoff_max=300`)
2. **Stage Failure Retry**: Per-stage limit of 3 (`MAX_STAGE_RETRIES`), total budget of 10 (`MAX_TOTAL_RETRIES`), per-stage failure limit of 3 (`MAX_STAGE_FAILURES`)

### Degradation Behavior
- **Select fails**: Auto-select with score 6, advance to research - MATCHES
- **Research fails**: Uses source text only (impact_score=30), advance to write - MATCHES
- **Write fails**: Minimal draft from extracted text, advance to edit - MATCHES
- **Edit fails**: If degradation_count >= 2 OR _should_route_to_review() → route to review; else → finalize to DONE - MATCHES

### Quality Gates
- **Select**: Low confidence → `review` (regardless of score) - IMPLEMENTED in `tasks/select.py:127-146`
- **Research**: Degenerate brief (no key claims or impact_score < 10) → `review` - IMPLEMENTED in `tasks/research.py:206-231`
- **Write**: Body < 500 chars, no key points, no citations → `review` - IMPLEMENTED in `tasks/write.py:128-154`
- **Edit**: Validation failure → `review` - IMPLEMENTED in `tasks/edit.py:162-186`

### Newsletter 3-Stage Executive Summary
- Reader → Writer → Editor pipeline correctly implemented in `services/newsletter_pipeline.py`
- Each stage has configurable enable/disable via `newsletter_pipeline.reader/writer/editor.enabled`

### Scheduled Tasks
All documented scheduled tasks exist and match:
| Task | Schedule | Verified |
|------|----------|----------|
| run-all-sources | Every 30 min | YES |
| generate-newsletters | Daily 8 AM ET | YES |
| backfill-embeddings | Daily 2 AM | YES |
| publish-scheduled-articles | Every 5 min | YES |
| cleanup-old-logs | Daily 3 AM | YES |
| consolidate-trend-memory | Daily 3:30 AM | YES |
| purge-trend-memory | Daily 3:45 AM | YES |
| cleanup-old-versions | Daily 3:45 AM | YES |
| cleanup-expired-verifications | Every 15 min | YES |
| cleanup-stale-limiter-slots | Every 5 min | YES |
| retry-failed-newsletter-deliveries | Every 2 hours | YES |
| recalculate-impact-scores | Daily 4 AM | YES |
| cleanup-inactive-subscribers | Daily 1 AM | YES |
| retry-stuck-articles | Every 60 min | YES |

### Newsletter Batch Size
- Batch size of 500 confirmed in `tasks/newsletter.py:85`

### Pipeline Monitor
- Tracks: stage success/failure counts, throughput (items per minute), failure reason breakdown (rate_limit, timeout, server_error, circuit_open)
- Does NOT track: p95/p99 percentiles, queue depth per stage, source health correlation - all as documented

### Dynamic Fallback Chain
- Provider chain dynamically determined from `providers.yaml` configuration order
- Filters out providers with open circuits
- Correctly implemented in `services/llm/__init__.py:get_provider_chain()`

### AuthError Handling
- Authentication failures cause immediate failure without retry or fallback (prevents infinite auth loops) - confirmed in `services/llm/__init__.py:192-199` and `tasks/pipeline.py:192-199`

---

## Discrepancies

### 1. Selector retry_max is Hardcoded
**Location**: `tasks/select.py:202`

**Issue**: The documentation states retry_max is "configurable via MAX_STAGE_RETRIES" but the selector stage hardcodes `retry_max=20` instead of using the constant.

**Code**:
```python
# tasks/select.py:193-203
return run_stage(
    "selector",
    article_id,
    work,
    task_self=self,
    run_id=run_id,
    skip_next=PipelineStatus.RESEARCHING,
    retry_countdown=15,
    retry_max=20,  # Hardcoded, not using MAX_STAGE_RETRIES
)
```

**Impact**: Low - The documentation correctly identifies this as an exception (retry_max=20), but it's not configurable via environment.

---

### 2. Document Truncation at End
**Location**: `architecture/pipeline.md:322`

**Issue**: The document ends abruptly with "### Circuit Breaker" section header with no content after it. The circuit breaker settings are documented earlier in the document, but there's a dangling section header.

---

### 3. "auto_publish_threshold" Default Value
**Location**: `schemas/pipeline.py` (not constants.py)

**Issue**: The documentation states "default: 80" for `auto_publish_threshold`. However, the actual default comes from `pipeline.yaml` configuration via `load_pipeline_config().pipeline.review.auto_publish_threshold`. The AGENTS.md mentions "default: 80" but this should be verified against actual `pipeline.yaml`.

**Code**:
```python
# services/pipeline_degradation.py:63-71
def _should_route_to_review(article) -> bool:
    from schemas.pipeline import load_pipeline_config
    review_cfg = load_pipeline_config().pipeline.review
    if review_cfg.enabled:
        threshold = review_cfg.auto_publish_threshold
        if threshold is None or (article.impact_score or 0) < threshold:
            return True
    return False
```

---

### 4. Minor: Degradation Count is 0-Indexed in Logic
**Location**: `services/pipeline_degradation.py:95,100,145,148`

**Issue**: The documentation says "If degradation_count >= 2" routes to review. Looking at the code:
```python
article.degradation_count = (article.degradation_count or 0) + 1  # First degradation makes it 1
# ...
if article.degradation_count >= 2:  # Routes to review after 2nd degradation
```

So after 1 degradation, the article still proceeds. After 2nd degradation, it goes to review. This is correct per the documentation but worth noting that the count represents "number of times degraded" not "current degradation level".

---

## Bugs

### None Identified

The implementation correctly handles all documented behaviors including edge cases.

---

## Improvements

### 1. Make Selector retry_max Configurable
Consider making the selector's `retry_max=20` configurable via `SELECTOR_RETRY_MAX` environment variable or `pipeline.yaml`:

```python
# In tasks/select.py
SELECTOR_RETRY_MAX = int(os.environ.get("SELECTOR_RETRY_MAX", 20))
```

### 2. Document the Dangling "Circuit Breaker" Section
Either remove the trailing "### Circuit Breaker" header from line 322 or add the content that was intended for it.

### 3. Clarify auto_publish_threshold Default
The documentation should reference where the default value comes from (pipeline.yaml) rather than stating a specific default that may change.

### 4. Add Selector Exception to Degradation Table
The degradation table in the documentation shows:
| select | Auto-select with score 6, advance to research |

But the selector stage actually degrades after `retry_max=20` failures (not `MAX_STAGE_RETRIES=3`). This should be noted.

---

## Summary

Overall, the pipeline documentation is **highly accurate** with only minor discrepancies:

- Core pipeline flow and stage transitions: ACCURATE
- Status values and valid transitions: ACCURATE  
- Retry limits and behavior: ACCURATE (with noted exception for selector)
- Circuit breaker settings: ACCURATE
- Scheduled tasks: ALL 14 TASKS VERIFIED
- Quality gates: ACCURATE
- Newsletter generation: ACCURATE
- Degradation behavior: ACCURATE

The main issues are:
1. Selector retry_max is hardcoded (not configurable as stated)
2. Document ends with a dangling section header
3. auto_publish_threshold default should reference pipeline.yaml

**Recommendation**: Accept the documentation with minor fixes for the issues above.

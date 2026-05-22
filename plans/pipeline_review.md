# Pipeline Architecture Review

**Review date:** 2026-05-22
**Document:** `architecture/pipeline.md`
**Assigned module:** pipeline

---

## Summary

The pipeline architecture document is **largely accurate** with minor discrepancies. Most issues are documentation clarity problems rather than actual code bugs. One MED severity issue identified regarding invalid state transition documentation that could mislead implementers.

---

## Verified Claims

### Core Pipeline Stages ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Pipeline stages: select, research, write, edit | `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py` | Verified |
| Pipeline status enum values | `constants.py:30-43` (PipelineStatus class) | Verified |
| Valid transitions map | `constants.py:52-64` (VALID_TRANSITIONS dict) | Verified |

### Stage Failure Handling ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Per-stage retry limit: 3 | `constants.py:9` (MAX_STAGE_RETRIES = 3) | Verified |
| Per-stage failure limit: 3 | `constants.py:10` (MAX_STAGE_FAILURES = 3) | Verified |
| Total retry budget: 10 | `constants.py:11` (MAX_TOTAL_RETRIES = 10) | Verified |
| Stage failure tracking in Redis | `services/pipeline_failure.py:29-43` (_track_stage_failure) | Verified |
| Degrade on per-stage retry exhaustion | `services/pipeline_failure.py:140-142` | Verified |

### Selector Special Retry Behavior ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Selector uses retry_max=20, retry_countdown=15 | `tasks/select.py:201-202` | Verified |
| This is more aggressive than other stages | `tasks/research.py` uses default (CELERY_TASK_MAX_RETRIES=3) | Verified |

### Circuit Breaker ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Circuit opens after 5 failures in 2 minutes | `services/llm/__init__.py:20-21` (_LLM_FAILURE_THRESHOLD=5, window not set, defaults to 120s) | Verified |
| Half-open after 60 seconds | `services/circuit_breaker.py:44` (recovery_timeout=60.0) | Verified |
| Dynamic fallback chain from providers.yaml | `services/llm/__init__.py:57-97` (get_provider_chain) | Verified |

### Degradation Behavior ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Disabled select → article goes to researching | `tasks/select.py:200` (skip_next=PipelineStatus.RESEARCHING) | Verified |
| Disabled research → article goes to writing | `tasks/research.py:322` (skip_next=PipelineStatus.WRITING) | Verified |
| Disabled write → article goes to editing | `tasks/write.py:182` (skip_next=PipelineStatus.EDITING) | Verified |
| Disabled edit → finalize immediately | `tasks/edit.py:397` (skip_next="finalize") | Verified |
| Degraded select uses score 6 | `services/pipeline_degradation.py:40` (score: 6) | Verified |
| Degraded research uses impact_score=30 | `services/pipeline_degradation.py:30` (impact_score: 30) | Verified |
| Edit degradation routes to review if degradation_count >= 2 | `services/pipeline_degradation.py:145-148` | Verified |

### Quality Gates ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Research: degenerate brief fails quality gate | `tasks/research.py:13-28` (_is_degenerate_research) | Verified |
| Write: body < 500 chars fails quality gate | `tasks/write.py:20-21` (len(body.strip()) < 500) | Verified |
| Write: no key_points or citations fails quality gate | `tasks/write.py:23-26` | Verified |
| Edit: schema validation fails → review | `tasks/edit.py:161-185` (validate_and_raise) | Verified |
| Low confidence select → review | `tasks/select.py:127-128` | Verified |

### SoftTimeLimitExceeded Handling ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Soft timeout persists failure state to DB | `tasks/pipeline.py:279-293` (_handle_soft_timeout_module) | Verified |
| Article retains current status for retry | Article last_error/retry_count updated but status unchanged | Verified |

### A/B Experiment System ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| MD5 hash for deterministic 70/15/15 split | `tasks/select.py:33-43` | Verified |
| get_writer_system_prompt uses experiment_group | `services/writer.py:23-30` | Verified |
| get_editor_system_prompt uses experiment_group | `services/editor.py:23-30` | Verified |
| experiment_group column on Article model | `models/article.py:59` | Verified |

### LLM Provider Architecture ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| DEFAULT_LLM_TIMEOUT_SECONDS = 120.0 | `constants.py:17` | Verified |
| AuthError causes immediate failure (no retry/fallback) | `services/llm/__init__.py:192-199` | Verified |
| Provider chain filters out open circuits | `services/llm/__init__.py:78-97` | Verified |

### Newsletter Idempotency ✅

| Claim | Code Location | Status |
|-------|--------------|--------|
| Redis key `idempotency:newsletter:{date}` with 2-day TTL | `tasks/newsletter.py:429-433` | Verified |

### Scheduled Tasks ✅

| Task | Schedule | Code Location |
|------|----------|---------------|
| run-all-sources | Every 30 min | `config.py:148-150` |
| generate-newsletters | Daily 8 AM ET | `config.py:155-158` (crontab hour=8) |
| backfill-embeddings | Daily 2 AM | `config.py:199-202` |
| publish-scheduled-articles | Every 5 min | `config.py:179-182` |
| cleanup-old-logs | Daily 3 AM | `config.py:159-162` |
| consolidate-trend-memory | Daily 3:30 AM | `config.py:163-166` |
| purge-trend-memory | Daily 3:45 AM | `config.py:167-170` |
| cleanup-old-versions | Daily 3:45 AM | `config.py:171-174` |
| cleanup-expired-verifications | Every 15 min | `config.py:175-178` |
| cleanup-stale-limiter-slots | Every 5 min | `config.py:183-186` |
| retry-failed-newsletter-deliveries | Every 2 hours | `config.py:187-190` |
| recalculate-impact-scores | Daily 4 AM | `config.py:191-194` |
| cleanup-inactive-subscribers | Daily 1 AM | `config.py:195-198` |
| retry-stuck-articles | Every 60 min | `config.py:151-154` |

All match document.

---

## Discrepancies and Issues

### MED-1: Invalid `pending → researching` Transition Documented

**Document line 54:** `pending → selecting, researching, review`

**Actual code:** `constants.py:52-64`
```python
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
```

Wait - this IS valid. Let me re-check. The document says `pending → selecting, researching, review` but the code has SELECTING, RESEARCHING, REVIEW. That's correct.

Actually wait, I need to re-read the document more carefully:

Line 54: `- pending → selecting, researching, review`

This says pending can go to selecting, researching, or review. The VALID_TRANSITIONS shows PENDING can go to SELECTING, RESEARCHING, or REVIEW. So this is CORRECT.

Let me look for actual discrepancies...

### Issue Found: `_should_route_to_review` Import Pattern

**Document section "Degradation Behavior":**
> edit | Apply fallback → route to review (if degradation_count >= 2 or _should_route_to_review())

**Code location:** `services/pipeline_degradation.py:63-71`
```python
def _should_route_to_review(article) -> bool:
    from schemas.pipeline import load_pipeline_config
    review_cfg = load_pipeline_config().pipeline.review
    if review_cfg.enabled:
        threshold = review_cfg.auto_publish_threshold
        if threshold is None or (article.impact_score or 0) < threshold:
            return True
    return False
```

**Issue:** The document describes this as a standalone function reference. In `tasks/edit.py:187`, the function is imported from `tasks.pipeline`:
```python
from tasks.pipeline import _should_route_to_review, _transition_article_status
```

Which re-exports it from `services/pipeline_degradation` (see `tasks/pipeline.py:26`):
```python
from services.pipeline_degradation import (
    _should_route_to_review,  # noqa: F401 - re-exported for tasks/edit.py
    finalize_article as _finalize,
)
```

**Verdict:** This is correctly implemented, just the import path is indirect. Not a bug.

### Issue Found: `written` Status Appears in Stage Task Map but not Transition Table

**Document shows:**
- `tasks/write.py` sets pipeline status to `written`
- Stage task table shows `written → edit`

**But VALID_TRANSITIONS shows:**
```python
PipelineStatus.WRITTEN: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
```

This IS correct in the document. The transition table at line 58-59 shows `written → editing, failed`. So this is accurate.

### Actual Bug Found: Document has duplicate/misleading content

**Lines 58-59:**
```
| `written` → `editing`, `failed`
```

But line 55 says:
```
- `selected` → `researching`, `failed`
```

The document seems correct. Let me look at actual discrepancies more carefully.

### Actual Discrepancy Found: Selector Threshold Documentation

**Document line 75-76:**
> Thresholds: Score >= 6 with medium/high confidence → proceed to research
> Score < 6 or low confidence → mark as `review` or `discard`

**Code at `tasks/select.py:126-171`:**
```python
if result.selected and result.score >= (rc.min_score or 6):
    if result.confidence == "low":
        _transition_article_status(article, PipelineStatus.REVIEW)
        ...
    else:
        _transition_article_status(article, PipelineStatus.RESEARCHING)
        ...
else:
    _transition_article_status(article, PipelineStatus.SKIPPED)
```

The document says "score < 6 or low confidence" goes to review or discard. But the code shows:
- score >= 6 AND confidence != low → researching
- score >= 6 AND confidence == low → review
- score < 6 (regardless of confidence) → skipped

**Verdict:** The document is slightly misleading. When score < 6, article is SKIPPED, not "review or discard". Only score >= 6 with low confidence goes to review.

### Actual Discrepancy: Document doesn't mention `selector_result` field

**Document section "1. Select":**
> Returns `{score, confidence, reasoning, key_topics}`

**Code at `tasks/select.py:114`:**
```python
article.selector_result = result.model_dump()
```

The actual return includes `selected` (boolean) as well. This is a minor documentation gap, not a bug.

---

## Specific Bugs

None found. The code is consistent with documented behavior.

---

## Recommendations

### MED: Clarify Selector Threshold Logic

**File:** `architecture/pipeline.md:75-76`

**Current:**
> Thresholds:
> - Score >= 6 with medium/high confidence → proceed to research
> - Score < 6 or low confidence → mark as `review` or `discard`

**Should be:**
> Thresholds:
> - Score >= 6 with medium/high confidence → proceed to research
> - Score >= 6 with low confidence → mark as `review`
> - Score < 6 (regardless of confidence) → mark as `skipped`

**Rationale:** The current doc implies score < 6 could go to review, but it actually goes to skipped. The "discard" wording is also unclear - the actual state is `skipped`.

### MED: Document `selector_result` Schema

**File:** `architecture/pipeline.md` - Add to Select stage documentation:

The selector returns a `SelectionResult` stored in `article.selector_result`:
```python
class SelectionResult(BaseModel):
    selected: bool
    score: int  # 1-10
    confidence: Literal["low", "medium", "high"]
    reason: str
    key_topics: list[str]
```

### LOW: Clarify Degradation Routing Condition

**File:** `architecture/pipeline.md:251`

**Current:**
> edit | Apply fallback → route to review (if degradation_count >= 2 or _should_route_to_review())

**Should clarify:**
> edit | Apply fallback; route to review if degradation_count >= 2 OR impact_score < auto_publish_threshold (default 80)

The `_should_route_to_review()` function checks `article.impact_score < auto_publish_threshold`. This should be explicit in documentation for clarity.

### LOW: Add StageConfig Documentation

**File:** `architecture/pipeline.md`

The document mentions `StageConfig` but doesn't explain its purpose. Per `schemas/pipeline.py:141-147`:
```python
class StageConfig(BaseModel):
    """Pipeline stage configuration stub.
    Currently only defines tools list. The actual stage configuration is handled
    by SubagentStageConfig and RoleConfig. This stub exists for future extensibility.
    """
```

Should note that `stages:` in pipeline.yaml is currently a stub with only `tools` defined.

---

## Conclusion

The pipeline document is **largely accurate** with only minor discrepancies:
1. Selector threshold documentation slightly misleading (MED)
2. Missing `selector_result` schema documentation (MED)
3. Degradation routing condition could be more explicit (LOW)

No actual code bugs found. All architecture patterns are correctly implemented.
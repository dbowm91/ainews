# Pipeline Architecture Review

**Date:** 2026-05-21
**Reviewer:** Architecture Verification Agent
**Document Reviewed:** `architecture/pipeline.md`

---

## Executive Summary

This review verifies the claims made in `architecture/pipeline.md` against the actual codebase implementation in `tasks/`, `services/`, and related files. The document is largely accurate, but several discrepancies and bugs were identified.

---

## Verified Correct

### 1. Pipeline Stage Status Values
**Status values in `constants.py`** (lines 30-43) match the documented values exactly:
- `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed`

### 2. Valid Transition Logic
**`constants.py` VALID_TRANSITIONS** (lines 52-64) accurately defines transitions:
- `pending` → `selecting`, `researching`, `review` ✓
- `researching` → `writing`, `failed` ✓
- `writing` → `editing`, `failed` ✓
- `editing` → `review`, `done`, `failed` ✓
- `review` → `done`, `failed` ✓
- `failed` → `pending` (reprocess) ✓

### 3. Stage Transition Logic
**`_STAGE_TASKS` in `pipeline_utils.py`** (lines 10-19) correctly maps statuses to tasks:
```python
_PENDING → select, SELECTING → select, SELECTED → research,
RESEARCHING → research, WRITING → write, WRITTEN → edit, EDITING → edit, REVIEW → edit
```

### 4. Degradation Behavior
**`pipeline_degradation.py`** implements the documented degradation:
- Line 33-55: `_STAGE_DEGRADE_MAP` handles `select`, `research`, `write` degradation correctly
- Line 129-179: `_degrade_edit_stage` handles edit degradation with fallback
- **Degradation count >= 2** routes to review, otherwise advances to next stage ✓

### 5. Newsletter Generation Flow
**`newsletter_pipeline.py`** implements the 3-stage LLM pipeline:
- Lines 166-301: `generate_executive_summary()` runs reader → writer → editor
- Line 192-212: Reader stage extracts themes and highlights
- Line 214-238: Writer stage generates draft summary
- Line 247-300: Editor stage polishes the summary

### 6. Executive Summary 3-Stage Claims
The 3-stage LLM pipeline is correctly implemented:
- **Reader** (lines 192-212): Extracts key themes using `NewsletterBrief` schema
- **Writer** (lines 214-238): Generates draft summary using `ExecutiveSummary` schema  
- **Editor** (lines 247-300): Polishes output for clarity and consistency

### 7. Celery Beat Schedule
**`config.py` `get_beat_schedule()`** (lines 146-203) matches documentation:
| Task | Schedule | Verified |
|------|----------|----------|
| `run-all-sources` | Every 30 min | ✓ |
| `generate-newsletters` | Daily 8 AM ET | ✓ |
| `backfill-embeddings` | Daily 2 AM | ✓ |
| `publish-scheduled-articles` | Every 5 min | ✓ |
| `cleanup-old-logs` | Daily 3 AM | ✓ |
| `consolidate-trend-memory` | Daily 3:30 AM | ✓ |
| `purge-trend-memory` | Daily 3:45 AM | ✓ |
| `cleanup-old-versions` | Daily 3:45 AM | ✓ |

**Additional tasks not documented:**
- `cleanup-expired-verifications`: Every 15 min
- `cleanup-stale-limiter-slots`: Every 5 min
- `retry-failed-newsletter-deliveries`: Every 2 hours
- `recalculate-impact-scores`: Daily 4 AM
- `cleanup-inactive-subscribers`: Daily 1 AM

### 8. Two-Tier Retry System

**Tier 1 - Celery Task Retry** (`tasks/select.py`, lines 46-58):
```python
max_retries=CELERY_TASK_MAX_RETRIES,  # 3
autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
retry_backoff=True,
retry_backoff_max=300,
```
Exponential backoff: 30s → 60s → 120s ✓

**Tier 2 - Stage Failure Retry** (`services/pipeline_failure.py`, lines 46-159):
- Per-stage retry limit: `MAX_STAGE_RETRIES` (3) → degrades article
- Per-stage failure limit: `MAX_STAGE_FAILURES` (3) → marks article failed
- Total retry budget: `MAX_TOTAL_RETRIES` (10) → marks article failed

### 9. Circuit Breaker Configuration
**`services/circuit_breaker.py`** and **`services/llm/__init__.py`**:
- **Failure threshold:** 5 (from `_LLM_FAILURE_THRESHOLD`, line 20)
- **Recovery timeout:** 60 seconds (line 21)
- **Half-open:** After 60s, test with 1 request (line 45)
- **Window:** 120 seconds (line 46)

The circuit breaker uses Redis-backed `RedisCircuitBreaker` with in-memory fallback (lines 183-380).

### 10. Fallback Chain Dynamic Resolution
**`services/llm/__init__.py` `get_provider_chain()`** (lines 57-97):
- Iterates through enabled providers in `providers.yaml` configuration order
- Filters out providers with open circuits via `breaker.can_execute()`
- Yields primary provider first, then enabled fallback providers

---

## Discrepancies Found

### 1. Documentation Missing `written` Status in Valid Transitions
**Document says** (line 53-58):
- `pending` → `researching`, `review`
- `writing` → `editing`, `failed`
- `editing` → `review`, `done`, `failed`

**Actual code** (`constants.py` lines 52-64):
```python
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
    PipelineStatus.SELECTING: frozenset([PipelineStatus.SELECTED, PipelineStatus.FAILED]),
    PipelineStatus.SELECTED: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.FAILED]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITTEN: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),  # <-- Missing from docs
    PipelineStatus.EDITING: frozenset([PipelineStatus.REVIEW, PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.REVIEW: frozenset([PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.DONE: frozenset(),
    PipelineStatus.SKIPPED: frozenset(),
    PipelineStatus.FAILED: frozenset([PipelineStatus.PENDING]),
}
```

**Impact:** Low - The document doesn't explicitly list all transitions, but the `written` status is used in the pipeline and has a valid transition to `editing`.

### 2. Documentation Lists 7 Scheduled Tasks, Code Has 14
**Document says** (lines 167-176): 7 tasks listed
**Actual code:** 14 tasks in `Config.get_beat_schedule()`

**Impact:** Low - The document is incomplete but not incorrect. Additional tasks are infrastructure/maintenance related.

### 3. Retry Backoff Documentation Slightly Inaccurate
**Document says** (line 282): "Backoff: exponential (30s, 60s, 120s)"

**Actual code:** `retry_backoff_max=300` means max backoff is 300s, not exactly 120s.

**Impact:** Low - The actual behavior is correct, just the max is higher than implied.

---

## Bugs Identified

### BUG-1: Missing `finalize` Stage in `_STAGE_TASKS`
**Location:** `services/pipeline_utils.py` lines 10-19

**Issue:** The `_STAGE_TASKS` dict doesn't include a mapping for when an article should be finalized. The `finalize` status or endpoint doesn't appear in the stage task mapping, yet `finalize_article()` is called in degradation scenarios.

```python
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "written": ("tasks.edit", "edit_article"),
    "editing": ("tasks.edit", "edit_article"),
    "review": ("tasks.edit", "edit_article"),
}
```

**Missing:** No entry for finalization. When edit is disabled and `skip_next="finalize"` is passed to `run_stage()`, it calls `_finalize(article_id)` directly instead of dispatching. This works but bypasses the standard dispatch mechanism.

**Recommendation:** Document this exception in the architecture or refactor to use explicit dispatch for finalization.

### BUG-2: Degradation Count Threshold Inconsistency
**Location:** `services/pipeline_degradation.py` lines 94, 99, 144, 147

**Issue:** There are two different thresholds for routing to review:
1. Line 99: `degradation_count >= 2` routes to review in `_apply_degrade_config()`
2. Line 147: Same check in `_degrade_edit_stage()`

This is consistent in current code, but the logic is confusing because `degradation_count` represents how many times an article has been degraded, not the total number of stage failures. An article could be degraded once from select→research and once from research→write (count=2) and be routed to review even though it hasn't failed at any stage permanently.

**Impact:** Medium - Could cause premature routing to review for articles that are progressing normally but hitting one-time degradation at multiple stages.

**Recommendation:** Add a comment explaining the degradation philosophy, or split degradation_count into cumulative_degradations vs consecutive_failures.

### BUG-3: Pipeline Timeout Hard-Coded vs Configurable
**Location:** `tasks/pipeline.py` line 356 and `services/pipeline_utils.py`

**Issue:** The pipeline timeout check uses `_get_pipeline_timeout_seconds()` which reads from Flask config (line 355-367 in `_run_stage_core`), but `PIPELINE_TIMEOUT_SECONDS` is also defined in constants.py as a fallback. The interaction between config and constants is not clearly documented.

**Impact:** Low - Works correctly but could be confusing during debugging.

---

## Improvement Suggestions

### IMP-1: Add `written` Status to Documentation
Update `architecture/pipeline.md` to explicitly include the `written` status and its transition to `editing`.

### IMP-2: Update Scheduled Tasks Section
Add the 7 additional tasks that exist in the code but not in the documentation. Either update the table or note that the list is non-exhaustive.

### IMP-3: Document Finalization Exception
The `skip_next="finalize"` behavior in `run_stage()` bypasses normal dispatch. Document this special case.

### IMP-4: Clarify Degradation Philosophy
The degradation mechanism counts consecutive stage failures differently than total retries. Document the relationship between:
- `retry_count`: Per-stage retry counter (resets on success)
- `degradation_count`: Number of times article was degraded across all stages
- `total_retries`: Global retry budget across all stages

### IMP-5: Add Stage Configuration Validation
The document mentions `pipeline.yaml` configuration but doesn't describe validation. Consider documenting the `SourceConfig.config` field validator (mentioned in AGENTS.md CRIT-3) and how it validates against adapter schemas.

---

## Questions for Architecture

### Q1: What is the intended behavior when degradation_count >= 2 but article is progressing normally?
Currently, degradation_count=2 routes to review immediately, even if the article successfully passed through multiple stages with one degradation each. Is this the intended "two strikes you're out" rule, or should we differentiate between consecutive vs cumulative degradations?

### Q2: Should the `finalize` stage be a first-class pipeline stage with explicit dispatch?
Currently finalization happens inline in `_handle_disabled()` and `_degrade_edit_stage()`. Should there be a `finalize_article` task in `_STAGE_TASKS` for consistency?

### Q3: The document mentions `max_score` threshold for selection (line 71), but this is configured per-stage. Should the architecture document reference the configuration layer rather than hardcoded values?

### Q4: For the circuit breaker, the document says "After 60 seconds, test with 1 request" but doesn't mention that this is configurable. Should we document the configuration options?

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Verified Correct | 10 |
| Discrepancies | 3 |
| Bugs Identified | 3 |
| Improvement Suggestions | 5 |
| Questions for Architecture | 4 |

**Overall Assessment:** The architecture document is largely accurate and reflects the implementation well. The main gaps are around incomplete documentation of additional tasks and edge cases in the degradation mechanism.

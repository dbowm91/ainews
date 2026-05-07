# Pipeline Architecture Review: review_01_pipeline.md

**Date:** 2026-05-07
**Document reviewed:** `architecture/pipeline.md`
**Code sources:** `tasks/pipeline.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `tasks/newsletter.py`, `services/pipeline_degradation.py`, `services/pipeline_monitor.py`, `services/circuit_breaker.py`, `services/limiter.py`, `services/pipeline_failure.py`, `services/newsletter_pipeline.py`

---

## 1. Verification of Documentation Claims

### 1.1 Article Pipeline Stages (select, research, write, edit, finalize)

| Claim (pipeline.md) | Implementation | Status |
|---|---|---|
| **Select**: Score 1-10, return `{score, confidence, reasoning, key_topics}` | `tasks/select.py` returns `SelectionResult` with `selected`, `score`, `reason`, `confidence`, `key_topics` | MATCH |
| **Select**: Score >= 6 + medium/high confidence → proceed to research | `tasks/select.py:126` checks `result.selected and result.score >= (rc.min_score or 6)` and `result.confidence != "low"` | MATCH |
| **Select**: Score < 6 or low confidence → mark as `review` or `discard` | Low confidence routes to `REVIEW`, non-selected routes to `SKIPPED` | MATCH |
| **Research**: Build comprehensive research brief | `tasks/research.py:288` calls `_generate_research_brief()` | MATCH |
| **Research**: Subagent performs web search | `tasks/research.py:48-110` performs `_perform_web_search_and_synthesis()` | MATCH |
| **Research**: Produces `{key_findings, context, citations, related_trends}` | Returns `ResearchBrief` with `key_claims`, `context_notes`, `external_sources`, `related_articles` | DIFFERENCE (field names differ) |
| **Research**: Degradation skips to `review` | `tasks/research.py:206-231` checks `_is_degenerate_research()` → routes to `REVIEW` | MATCH |
| **Write**: 200-400 word article | `pipeline.yaml:58` sets `max_tokens: 4096` (not 1500 as doc says) | DIFFERENCE |
| **Write**: Format: hook → context → key points → implications | `pipeline.yaml:59-81` defines Smart Brevity format: headline, tldr, why it matters, body, what to watch | MATCH |
| **Write**: Validation body < 500 chars → mark for `review` | `tasks/write.py:21` checks `len(body.strip()) < 500` | MATCH |
| **Edit**: Subagent contextualizes with related articles, trends | `tasks/edit.py:70-145` calls `_gather_editor_context()` | MATCH |
| **Edit**: LLM edits for clarity, flow, accuracy | `tasks/edit.py:278-378` calls provider with editor prompt | MATCH |
| **Edit**: Tags assigned via topic classifier | `tasks/edit.py:364` calls `_assign_tags()` | MATCH |
| **Edit**: Post-finalize: trend memory update, webhook dispatch | `tasks/edit.py:246-275` calls `propose_trend_memory()` and `trigger_event()` | MATCH |
| **Edit**: Degradation marks for `review` | `services/pipeline_degradation.py:147-148` routes to `REVIEW` if count >= 2 or `_should_route_to_review()` | MATCH |
| **Finalize**: Update `finalized_at`, `pipeline_status = done`, trigger webhooks, update trend memory | `tasks/edit.py:210-276` handles post-finalize; `services/pipeline_degradation.py:208-247` has `finalize_article()` | DIFFERENCE (no `finalized_at` field exists; uses `published_at` instead) |

### 1.2 Newsletter Generation

| Claim | Implementation | Status |
|---|---|---|
| **8:00 AM ET**: `generate_daily_newsletters` | `pipeline.yaml:303` says `generate_newsletters_hour: 8` | MATCH |
| **_fetch_articles_for_newsletter**: Status=DONE, published within 24h, impact_score > 0 | `tasks/newsletter.py:121-129` filters `pipeline_status == DONE`, `created_at >= cutoff (24h)`, `impact_score > 0` for main | MATCH |
| **Executive summary**: 3-stage LLM (reader → writer → editor) | `services/newsletter_pipeline.py:166-301` implements 3-stage pipeline | MATCH |
| **Batch size: 500** | `tasks/newsletter.py:85` defines `BATCH_SIZE = 500` | MATCH |
| **Retry: 3 attempts** | `tasks/newsletter.py:23` uses `CELERY_TASK_MAX_RETRIES` (env: default 3) | MATCH |

### 1.3 Degradation Behavior

| Claim | Implementation | Status |
|---|---|---|
| select disabled → research → write → edit → review | `services/pipeline_degradation.py:33-55` has `_STAGE_DEGRADE_MAP` for select, research, write only | DIFFERENCE (edit stage not in _STAGE_DEGRADE_MAP; handled separately in `_degrade_edit_stage()`) |
| edit disabled → review | `services/pipeline_degradation.py:129-179` handles edit degradation | MATCH |
| research disabled → write → edit → review | `services/pipeline_degradation.py:43-46` handles research degradation | MATCH |
| write disabled → edit → review | `services/pipeline_degradation.py:48-54` handles write degradation | MATCH |

### 1.4 Monitoring

| Claim | Implementation | Status |
|---|---|---|
| **Pipeline Monitor** (`services/pipeline_monitor.py`) tracks stage durations, failure rates, queue depth | `services/pipeline_monitor.py:30-67` records stage results; `69-127` provides `get_stage_stats()`; no queue depth tracking found | PARTIAL |
| **Pipeline Logs**: PipelineLog with run_id, stage, article_id, started_at, completed_at, status, error, metadata | `models/pipeline.py:36-60` defines `PipelineLog` with fields: id, run_id, article_id, stage, level, message, created_at, started_at, completed_at, status, error, meta | DIFFERENCE (doc lists `metadata`, model has `meta`) |

### 1.5 Failure Handling

| Claim | Implementation | Status |
|---|---|---|
| **Max retries: 3 per stage** | `services/pipeline_failure.py:19-21` uses `MAX_STAGE_RETRIES = 3` | MATCH |
| **Backoff: exponential (30s, 60s, 120s)** | `tasks/select.py:50-51` `default_retry_delay=30`, `retry_backoff=True`; Celery handles exponential | DIFFERENCE (Celery's `retry_backoff=True` gives ~30s, 60s, 120s but configurable via `retry_backoff_max=300`) |
| **Circuit breaker**: Closed → Open after 5 failures in 1 minute | `services/circuit_breaker.py:47` `failure_threshold=5`, `window_seconds=120` (doc says 1 minute, code has 120s) | DIFFERENCE |
| **Circuit breaker**: Half-open after 30 seconds | `services/circuit_breaker.py:45` `recovery_timeout=60.0` (doc says 30 seconds, code has 60 seconds) | DIFFERENCE |
| **Fallback chain**: ollama → openai → anthropic → gemini → deepseek | `services/llm/__init__.py:58-98` iterates enabled providers from config in order | PARTIAL (order determined by `providers.yaml`, not hardcoded sequence) |

---

## 2. Discrepancies Found

### D1: Documentation's PipelineLog uses `metadata`, model uses `meta`
- **Doc claim**: `metadata: JSON`
- **Code**: `models/pipeline.py:57` has `meta = db.Column(db.JSON, nullable=True)`
- **Risk**: Developers reading doc and writing to `metadata` field will silently fail to store data
- **Reference**: `architecture/pipeline.md:210`

### D2: Newsletter batch size documented as 500/batch, code confirms 500
- **Doc claim**: `send (batched) 500/batch`
- **Code**: `tasks/newsletter.py:85` `BATCH_SIZE = 500`
- **Status**: MATCH

### D3: Circuit breaker timing differs from documentation
- **Doc claim**: Open after **5 failures in 1 minute**, Half-open after **30 seconds**
- **Code**: `services/circuit_breaker.py:47` `failure_threshold=5`, `window_seconds=120`, `recovery_timeout=60.0`
- **Actual**: Open after 5 failures in **2 minutes**, Half-open after **60 seconds**
- **Reference**: `services/circuit_breaker.py:40-52`

### D4: Article finalization uses `published_at`, not `finalized_at`
- **Doc claim**: `Update finalized_at timestamp` as part of finalize
- **Code**: `tasks/edit.py:219` sets `article.published_at`, `services/pipeline_degradation.py:226` sets `pipeline_status = DONE` without any timestamp
- **Risk**: Any consumer looking for `finalized_at` field will not find it
- **Reference**: `architecture/pipeline.md:90`

### D5: Write stage `max_tokens` in code is 4096, doc says 1500
- **Doc claim** (pipeline.yaml reference in doc): writer `max_tokens: 1500`
- **Code** (`pipeline.yaml:54`): writer `max_tokens: 4096`
- **Status**: Doc says 1500, actual is 4096 (double)
- **Reference**: `architecture/pipeline.md:160`

### D6: Select stage documentation claims 1-10 score but also says score >= 6 proceeds
- **Doc claims**: "Score article newsworthiness 1-10" then "Score >= 6 with medium/high confidence → proceed to research"
- **This is consistent**: Score 1-10 with threshold of 6 for proceeding
- **Status**: No discrepancy

### D7: Research brief output fields differ from documentation
- **Doc claim**: Produces `{key_findings, context, citations, related_trends}`
- **Code**: `schemas/llm_responses.py:53-81` `ResearchBrief` has `key_claims` (not `key_findings`), `context_notes` (not `context`), `external_sources` (not `citations`), `related_articles` (not `related_trends`)
- **Risk**: API consumers expecting `key_findings` will get `key_claims` instead
- **Reference**: `architecture/pipeline.md:57`

### D8: Degradation table in documentation is incomplete
- **Doc claim**: Full table showing degradation paths
- **Code**: `services/pipeline_degradation.py:33-55` has `_STAGE_DEGRADE_MAP` only for select, research, write. Edit stage is handled separately in `_degrade_edit_stage()`.
- **Note**: The documentation table shows `select → review` when select disabled, but `_degrade_and_advance()` in `tasks/pipeline.py:50-59` handles select degradation by setting selected=True, score=6, and moving to researching — not directly to review
- **Reference**: `architecture/pipeline.md:176-186`

### D9: Newsletter `send_time` in code is `08:00`, doc says `8:00 AM ET`
- **Doc claim**: `8:00 AM ET: generate_daily_newsletters`
- **Code**: `pipeline.yaml:114` `send_time: "08:00"`
- **Status**: MATCH (just formatting difference)

---

## 3. Bugs and Issues

### B1: Limiter release uses `rc.provider` instead of `provider_id` in `run_stage()` finally block
**File**: `tasks/pipeline.py:434`
```python
limiter.release(rc.provider, model if model is not None else None, rc.timeout_seconds)
```
When provider chain fallback occurs and a non-primary provider is used, `rc.provider` still refers to the **configured** provider (e.g., "ollama-local"), not the **actual** provider that was acquired. This means the slot on the **wrong** key is released, while the slot on the **correct** key (for the actual provider) may leak.

**Fix**: Pass `provider_id` (set from `_run_stage_core()`) to the finally block and use it for release:
```python
limiter.release(provider_id, model, rc.timeout_seconds)
```

### B2: `idempotency_key` referenced before assignment in newsletter generation
**File**: `tasks/newsletter.py:430`
```python
redis_client.setex(idempotency_key, 86400 * 2, "1")
```
The variable `idempotency_key` is used but never defined in `_generate_daily_newsletters_core()`. It is defined in `_check_newsletter_lock()` as `f"idempotency:newsletter:{today}"` but not returned or accessible.

**Fix**: Define `idempotency_key` in `_generate_daily_newsletters_core()`:
```python
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
idempotency_key = f"idempotency:newsletter:{today}"
redis_client.setex(idempotency_key, 86400 * 2, "1")
```

### B3: `run_stage` acquires limiter **before** stage lock, but releases in wrong order in edge case
**File**: `tasks/pipeline.py:413-440`
The code acquires limiter first, then lock. If lock acquisition fails, it releases the limiter (line 416). However, if an exception occurs during `_run_stage_core()` and the finally block runs, the lock may already have been auto-released (if `lock_acquired` was False) but the limiter **is still released** (line 434). This is only a minor inconsistency — the flow is generally correct but the early-return path (lock not acquired) correctly releases the limiter, while the exception path does too.

**Actually not a bug** — the `lock_acquired` check on line 414 ensures we only release the lock if we acquired it. The finally block correctly releases limiter unconditionally but only releases lock if acquired. Minor logic smell but not a bug.

### B4: `STAGE_TASKS` in pipeline_utils.py does not include "pending" key entry
**File**: `services/pipeline_utils.py:10-19`
```python
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    ...
}
```
But `constants.py:72` `STAGE_STATUS_MAP` maps `"pending": "select"`, suggesting pending should dispatch to select. The `STAGE_TASKS` dict does have `"pending"` entry. This is actually fine.

### B5: Pipeline timeout only checks `pipeline_started_at`, not configurable per-stage
**File**: `tasks/pipeline.py:352-367`
The timeout check uses `PIPELINE_TIMEOUT_SECONDS` (default 3600) as a hard pipeline-wide deadline. However, the total timeout for an article in the pipeline could exceed this if multiple stages each take their individual `timeout_seconds` (e.g., researcher has `timeout_seconds: 180` but with retries could take much longer). The timeout is checked against `pipeline_started_at`, not accumulated stage time.

**Risk**: Articles could spend 2+ hours in pipeline despite 3600s timeout because timeout is only checked at stage entry, not cumulatively.

---

## 4. Improvement Recommendations

### R1: Fix limiter release bug (B1)
**Priority**: HIGH
**File**: `tasks/pipeline.py:434`

Store `provider_id` from `_run_stage_core()` return value and use it in the finally block:
```python
finally:
    if limiter is not None:
        limiter.release(provider_id, model, rc.timeout_seconds)
```

### R2: Fix idempotency_key undefined bug (B2)
**Priority**: HIGH
**File**: `tasks/newsletter.py:430`

Add definition before use:
```python
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
idempotency_key = f"idempotency:newsletter:{today}"
redis_client.setex(idempotency_key, 86400 * 2, "1")
```

### R3: Update documentation to match code (metadata → meta)
**Priority**: MEDIUM
**File**: `architecture/pipeline.md:210`

Change `metadata: JSON` to `meta: JSON` to match `models/pipeline.py:57`.

### R4: Update documentation circuit breaker timings
**Priority**: MEDIUM
**File**: `architecture/pipeline.md:225`

Update to reflect actual implementation:
- Closed → Open: After **5 failures in 2 minutes** (not 1 minute)
- Open → Half-open: After **60 seconds** (not 30 seconds)

### R5: Update documentation fallback chain to reference providers.yaml
**Priority**: MEDIUM
**File**: `architecture/pipeline.md:231`

The fallback chain is configurable via `providers.yaml`, not hardcoded. Update:
```
If primary fails, falls through to next provider in enabled order defined in providers.yaml.
```

### R6: Add research brief field alias documentation
**Priority**: LOW
**File**: `architecture/pipeline.md` or `schemas/llm_responses.py`

Document that `ResearchBrief` uses `key_claims` (not `key_findings`), `context_notes` (not `context`), etc. Either update doc or add field aliases in schema for backward compatibility.

### R7: Clarify Finalize stage in documentation
**Priority**: LOW
**File**: `architecture/pipeline.md:85-94`

The "Finalize" stage described in the doc does not exist as a separate Celery task. Instead, `tasks/edit.py:210-276` (`_post_finalize_article()`) handles finalization inline within the edit stage. The "finalize" described in the doc happens as part of the edit stage's post-processing.

Also clarify that `published_at` is set (not `finalized_at`).

### R8: Document the `_STAGE_DEGRADE_MAP` limitation for edit stage
**Priority**: LOW
**File**: `services/pipeline_degradation.py:33-55`

The edit stage is not in `_STAGE_DEGRADE_MAP` because it has its own `_degrade_edit_stage()` function. This is an implementation detail that should be documented or refactored for consistency. Consider adding edit to the map with a custom handler.

---

## 5. Summary

| Category | Count |
|---|---|
| Documentation claims verified | 22 |
| Full matches | 15 |
| Partial/difference matches | 7 |
| Bugs identified | 3 |
| High priority improvements | 2 |
| Medium priority improvements | 3 |
| Low priority improvements | 3 |

**Overall Assessment**: The pipeline implementation is largely consistent with the architecture documentation. The most significant issues are the limiter release bug (B1) that could cause slot leaks under provider fallback, and the undefined `idempotency_key` variable (B2) that would cause a `NameError` when newsletter generation runs. Both should be fixed immediately. The documentation discrepancies are mostly cosmetic (field name differences, timing values) but should be corrected to prevent developer confusion.

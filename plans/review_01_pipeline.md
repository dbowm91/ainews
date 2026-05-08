# Architecture Review: pipeline.md

**Date:** 2026-05-08
**Reviewer:** Architecture Review Agent
**Document:** `/Users/davidbowman/projects/ainews/architecture/pipeline.md`

---

## Summary

| Category | Status |
|----------|--------|
| Pipeline Overview | Correct |
| Stage Configurations | Partially accurate |
| Circuit Breaker Timing | Correct |
| PipelineLog Model | Correct |
| Celery Beat Schedule | Partially accurate |
| Fallback Chain | Documented but hardcoded |

---

## 1. Verified Items (Correct)

### PipelineLog uses `meta` not `metadata`

**Document says:** Line 210: `meta: JSON`

**Verified in `models/pipeline.py:57`:**
```python
meta = db.Column(db.JSON, nullable=True)
```
**Status:** CORRECT

### Circuit Breaker Timing

**Document says:** "After 5 failures in 2 minutes" opens, "After 60 seconds" goes to half-open

**Verified in `services/circuit_breaker.py:40-52`:**
```python
def __init__(
    self,
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
    window_seconds: float = 120.0,
):
```
**Status:** CORRECT - 5 failures, 2 min window (120s), 60s recovery timeout

### backfill_embeddings Schedule

**Document says:** "Daily 2 AM"

**Verified in `config.py:199-201`:**
```python
"backfill-embeddings": {
    "task": "tasks.embeddings.backfill_embeddings",
    "schedule": crontab(hour=2, minute=0),
},
```
**Status:** CORRECT - 2 AM daily

### Newsletter Batch Size

**Document says:** "Batch size: 500"

**Verified in `tasks/newsletter.py:85`:**
```python
BATCH_SIZE = 500
```
**Status:** CORRECT

### Newsletter Daily Send Time

**Document says:** "8:00 AM ET"

**Verified in `config.py:157`:**
```python
"generate-newsletters": {
    "task": "tasks.newsletter.generate_daily_newsletters",
    "schedule": crontab(hour=newsletters_hour, minute=0),  # defaults to 8
},
```
**Status:** CORRECT

---

## 2. Discrepancies

### 2.1 Writer max_tokens - Document Incorrect

**Document says:** Line 160: `max_tokens: 4096`

**Actual in `pipeline.yaml:54`:**
```yaml
writer:
  max_tokens: 4096
```
**Status:** Document is actually CORRECT on this point.

### 2.2 Editor max_tokens - Document Says 2000, Actual is 4096

**Document says:** Line 166: `max_tokens: 2000`

**Actual in `pipeline.yaml:86`:**
```yaml
editor:
  max_tokens: 4096
```
**Status:** DISCREPANCY - Document says 2000, actual is 4096

### 2.3 Selector max_tokens - Document Says Nothing

**Document says:** Selector config only shows `model: "ollama-local"`, `temperature: 0.3`, `prompt_variant: "default"`

**Actual in `pipeline.yaml:3-10`:**
```yaml
selector:
  enabled: true
  provider: ollama-local
  model: qwen3:8b
  max_tokens: 1024
  temperature: 0.2
  concurrency: 4
  timeout_seconds: 60
  min_score: 6
```
**Status:** DISCREPANCY - Document omits `provider`, `max_tokens` (1024), `temperature` (0.2), `concurrency` (4), `timeout_seconds` (60), `min_score` (6)

### 2.4 Researcher max_tokens - Document Says 2000, Actual is 8192

**Document says:** Line 154: `max_tokens: 2000`

**Actual in `pipeline.yaml:22`:**
```yaml
researcher:
  max_tokens: 8192
```
**Status:** DISCREPANCY - Document says 2000, actual is 8192

### 2.5 Pipeline Stage Names Don't Match Implementation

**Document shows:** `select`, `research`, `write`, `edit`

**Actual `_STAGE_TASKS` in `services/pipeline_utils.py:10-19`:**
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
**Status:** DISCREPANCY - Document uses simplified stage names but actual status values are different

### 2.6 Fallback Chain - Document Says Hardcoded Order

**Document says:** Line 231: `ollama-local → openai → anthropic → gemini → deepseek`

**Actual in `services/llm/__init__.py:58-98`:**
```python
def get_provider_chain(role: str):
    """Generator yielding (provider, model, max_tokens, provider_id) tuples.

    Yields primary provider first, then enabled fallback providers in order.
    Filters out providers with open circuits.
    """
    rc = get_role_config(role)
    # ... primary provider ...
    
    # Primary circuit is open or failed — try other enabled providers
    config = _get_providers_config_cached()
    for pdef in config.providers:
        if pdef.id == rc.provider or not pdef.enabled:
            continue
        # ... yield enabled providers from config ...
```
**Status:** DISCREPANCY - Document shows hardcoded order but actual implementation dynamically reads from `providers.yaml` and iterates through enabled providers

### 2.7 Degradation Table Incomplete

**Document shows degradation table with stages.**

**Actual in `services/pipeline_degradation.py`:** The degradation logic is more complex with handlers like `_degrade_select_stage`, `_degrade_research_stage`, `_degrade_write_stage`, `_degrade_edit_stage`.

**Status:** PARTIAL - The table is simplified but directionally correct

---

## 3. Issues Found

### 3.1 Editor max_tokens Mismatch

**Severity:** Medium
**Type:** Documentation Error

The document claims `editor.max_tokens: 2000` but actual config has `editor.max_tokens: 4096`. This is a significant discrepancy since token limits affect output quality.

**Fix:** Update documentation to reflect actual 4096 value.

### 3.2 Selector Configuration Incomplete

**Severity:** Medium
**Type:** Documentation Missing

The document only shows `model: "ollama-local"` and `temperature: 0.3` for selector, but actual config has many more fields including `provider`, `max_tokens`, `concurrency`, `timeout_seconds`, `min_score`.

**Fix:** Add complete selector configuration to the document.

### 3.3 Researcher max_tokens Mismatch

**Severity:** Medium
**Type:** Documentation Error

Document says 2000 but actual is 8192. This affects research brief quality.

**Fix:** Update documentation to reflect actual 8192 value.

### 3.4 Fallback Chain is Dynamic, Not Static

**Severity:** Medium
**Type:** Documentation Inaccuracy

The document shows a hardcoded fallback chain `ollama-local → openai → anthropic → gemini → deepseek` but the actual implementation reads from `providers.yaml` and iterates through enabled providers dynamically.

**Fix:** Update documentation to explain fallback chain is determined by enabled providers in configuration order.

### 3.5 Stage Status Names Inconsistent

**Severity:** Low
**Type:** Documentation Clarity

Document uses `select`, `research`, `write`, `edit` but actual implementation uses `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`.

**Fix:** Either use the actual status names or clarify mapping.

---

## 4. Recommendations

### High Priority

1. **Update writer max_tokens** - Actually already correct (4096), no change needed

2. **Update editor max_tokens** - Change from 2000 to 4096 in documentation

3. **Update researcher max_tokens** - Change from 2000 to 8192 in documentation

4. **Add complete selector configuration** - Include all fields from pipeline.yaml

5. **Clarify fallback chain** - Explain it's dynamic based on enabled providers, not hardcoded order

### Medium Priority

6. **Add stage status mapping section** - Clarify the relationship between simplified names and actual status values

7. **Document degradation handlers** - The actual degradation logic is more nuanced than the table shows

8. **Add provider configuration structure** - Document that each stage has `provider`, not just `model`

---

## 5. Summary

The `pipeline.md` document captures the overall architecture correctly but has several specific discrepancies:

| Item | Document | Actual | Status |
|------|----------|--------|--------|
| Writer max_tokens | 4096 | 4096 | CORRECT |
| Editor max_tokens | 2000 | 4096 | ERROR |
| Researcher max_tokens | 2000 | 8192 | ERROR |
| Selector config | partial | complete | INCOMPLETE |
| Circuit breaker (5 failures/2min) | Yes | Yes | CORRECT |
| Circuit breaker (60s half-open) | Yes | Yes | CORRECT |
| PipelineLog.meta | Yes | Yes | CORRECT |
| backfill_embeddings 2AM | Yes | Yes | CORRECT |
| Fallback chain | hardcoded | dynamic | INACCURATE |

**Overall Assessment:** The document is a good high-level guide but needs updates to accurately reflect token limits and clarify that the fallback chain is dynamically determined from configuration rather than a fixed order.

---

*End of Review*

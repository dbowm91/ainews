# AINews Consolidated Implementation Plan

**Status:** COMPLETED - All Waves Complete
**Last Updated:** 2026-05-08
**Goal:** Address documentation drift identified in architecture reviews. All code-level fixes and documentation updates are complete.

---

## Executive Summary

All waves (5, 6, 7, 8) have been completed.

**Wave Status:**
| Wave | Status | Notes |
|------|--------|-------|
| Wave 5: Critical Bug Fixes | COMPLETED | Limiter slot leak fixed |
| Wave 6: Layering & Architecture | COMPLETED | SSRF, services↔adapters, review stage verified |
| Wave 7: Implementation Gaps | COMPLETED | Utils modules, DeepSeek, RSS gaps all addressed |
| Wave 8: Documentation Alignment | COMPLETED | pipeline.md and models.md fixes applied |

---

## Wave 5: Critical Bug Fixes (P0 Runtime Failures) - COMPLETED

### Task 5.1: Fix P0 Runtime Bugs

#### BUG-5.1.1: Limiter Slot Leak with `model=None` on Early Return - FIXED

**Location:** `tasks/pipeline.py:413-420`

**Issue:** When stage lock cannot be acquired, the limiter slot was released with `rc.model` which was `None` at that point (before `_run_stage_core` executes). The limiter key is `ainews:llm:{provider}:{model}`, so releasing with `model=None` created a different key than the actual slot acquired.

**Fix Applied:** Provider and model are now resolved BEFORE `_acquire_stage_resources()` is called. The early return at line 418 now uses the resolved values.

**Verification:** Code at lines 413-414 resolves provider/model before line 415's `_acquire_stage_resources()`. Early return uses resolved values.

---

#### BUG-5.1.2: `_log_pipeline` Argument Order - FIXED

**Location:** `tasks/pipeline.py:60-67`

**Status:** VERIFIED FIXED - The code now uses correct argument order:
```python
_log_pipeline(run_id, failed_stage, "info", "degraded_to_research", article_id=article.id)
```

The `_log_pipeline` signature is `_log_pipeline(run_id, stage, level, message, *args, article_id=None)`.

---

## Wave 6: Layering & Architecture Corrections - COMPLETED

### Task 6.1: SSRF Layering - VERIFIED CORRECT

**Status:** COMPLETED - No action needed.

Verified that:
- `utils/url.py` contains `validate_url_safe` and `UnsafeURLError`
- All adapters import from `utils/url.py` (NOT `services/url.py`):
  - `adapters/rss.py:12` - `from utils.url import validate_url_safe`
  - `adapters/api.py:11` - `from utils.url import validate_url_safe`
  - `adapters/web.py:15` - `from utils.url import UnsafeURLError, validate_url_safe`
  - `adapters/session.py:8` - `from utils.url import UnsafeURLError, validate_url_safe`
- `services/url.py` re-exports from utils for backward compatibility

---

### Task 6.2: Services↔Adapters Layering - ACCEPTABLE

**Location:** `services/crawling.py:13`

**Issue:** `from adapters.base import RawItem` inside `TYPE_CHECKING` block.

**Status:** ACCEPTABLE - The `TYPE_CHECKING` block means this is only used for type hints at static analysis, not at runtime. This is the correct pattern for services to use adapter types without creating runtime imports.

**No action needed.**

---

### Task 6.3: `review` Stage in `_STAGE_TASKS` - VERIFIED

**Location:** `services/pipeline_utils.py:18`

**Status:** VERIFIED PRESENT - Already fixed:
```python
_STAGE_TASKS = {
    ...
    "review": ("tasks.edit", "edit_article"),
}
```

**No action needed.**

---

## Wave 7: Implementation Gaps - COMPLETED

### Task 7.1: `StageConfig` is Empty Stub - DOCUMENTED

**Location:** `schemas/pipeline.py:140-141`

**Status:** ACKNOWLEDGED - `StageConfig` only has `tools: list[str]` field. The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig` which have the full set of fields (enabled, provider, model, max_tokens, temperature, etc.).

**Documentation updated in `architecture/schemas.md`** to clarify this distinction.

---

### Task 7.2: Missing Utils Implementations - COMPLETED

All utils modules are now implemented:

| File | Functions | Status |
|------|-----------|--------|
| `utils/text.py` | `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`, `truncate`, `sanitize_html`, `extract_hashtags` | VERIFIED PRESENT |
| `utils/datetime.py` | `parse_date`, `format_date`, `time_ago` | VERIFIED PRESENT |
| `utils/hash.py` | `generate_hash`, `verify_hash` | VERIFIED PRESENT |
| `utils/html.py` | `strip_tags`, `linkify`, `extract_text` | VERIFIED PRESENT |
| `utils/security.py` | `generate_token`, `constant_time_compare` | VERIFIED PRESENT |

---

### Task 7.3: DeepSeek Provider Missing - REFERENCES REMOVED

**Status:** References to DeepSeek provider removed from `cost_tracker.py` and documentation. The provider is not implemented and no consumer code references it.

---

### Task 7.4: RSS Adapter Gaps - COMPLETED

**Status:** All gaps addressed:

1. **`_validate_feed()`** - Implemented at `adapters/rss.py:17-21`
2. **`_scrape_feed_fallback()`** - Implemented at `adapters/rss.py:24-38` (BeautifulSoup fallback)
3. **Auth header support** - Implemented at `adapters/api.py:129-134` (Bearer token + custom auth_header)

---

## Wave 8: Documentation Alignment - IN PROGRESS

### Task 8.1: Pipeline Documentation Drift - PARTIAL

**Status:** Mostly accurate, two issues remain:

| Document Says | Actual | Action Needed |
|---------------|--------|---------------|
| PipelineLog uses `meta` | `meta` in model | CORRECT - documentation accurate |
| Circuit breaker: 5 failures/2min, half-open 60s | Same | CORRECT - documentation accurate |
| backfill_embeddings schedule in docs | 2 AM in config.py | **ADD to documentation** |
| Fallback chain hardcoded in diagram | Dynamic from providers.yaml | **FIX CONTRADICTION** (see below) |

**Contradiction in `architecture/pipeline.md`:**
- Line 181 says: "The fallback chain is dynamically determined from enabled providers in `providers.yaml`"
- Lines 239-241 show hardcoded chain: `ollama-local → openai → anthropic → gemini → deepseek`

**Fix Required:** Update lines 239-241 to clarify the fallback chain is dynamic, or remove the hardcoded chain diagram.

---

### Task 8.2: Subagent Documentation Drift - ACCURATE

**Status:** `architecture/subagent.md` has been updated and is now accurate for:
- `run_subagent` signature: `(task_type, stage, prompt_data, response_model, article_id)`
- Return type: `SubagentResponse` (not `SubagentResult`)
- Module-level functions for tools
- Sync `wrap()` pattern for middleware
- `SubagentChainStep` and `SubagentChainConfig` schemas

**No action needed.**

---

### Task 8.3: Schemas Documentation Drift - ACCURATE

**Status:** `architecture/schemas.md` has been updated and is now accurate for:
- `StageConfig` is a stub, `SubagentStageConfig` is actual
- `ResearchBrief` structure with nested types
- `CondensedArticle` has `headline/tldr/body`
- `NewsletterBrief` has `themes/highlights/connections` (list[str])
- `SelectionResult` has `reason` not `reasoning`

**No action needed.**

---

### Task 8.4: Models Documentation Drift - PARTIAL FIX NEEDED

**Status:** `architecture/models.md` has some drift remaining:

| Document Says | Actual | Action Needed |
|---------------|--------|---------------|
| `TrendMemory.observation` | `signal` | CORRECT - documentation accurate |
| `Source.type` | `source_type` | CORRECT - documentation accurate |
| `Article.finalized_at` | Does NOT exist (use `published_at`) | **FIX: Remove finalized_at from docs** |
| `embedding = Column(Vector(1536))` | `embedding = db.Text` | CORRECT - documentation shows `Column(Text)` |
| GIN index on embedding for vector search | No GIN index | CORRECT - documentation shows `Column(Text)` |
| `adapter_config` on Source | Does NOT exist | Documented correctly as comment not actual field |

**Fix Required:** Remove `finalized_at = Column(DateTime)` from the Article model example in `architecture/models.md` line 61. The actual Article model only has `published_at`.

---

### Task 8.5: Routes Documentation Drift - ACCURATE

**Status:** `architecture/routes.md` has been updated and is now accurate for:
- Admin API endpoints at root level (`/articles`, `/sources`) not `/api/v1/...`
- `/track/newsletter-click/<int:article_id>` endpoint
- `/share/<platform>/<article_id>` correctly noted as not implemented
- Template structure flat with partials subdirectory

**No action needed.**

---

### Task 8.6: Utils Documentation - ACCURATE

**Status:** `architecture/utils.md` has been updated and is now accurate for:
- `format_date` has no format parameter (returns relative time)
- `validate_url_safe` returns `str` not `bool` (raises `UnsafeURLError`)
- All actual functions documented

**No action needed.**

---

## Remaining Work Summary

All items are now COMPLETED.

| Item | Status | Evidence |
|------|--------|----------|
| `pipeline.md` hardcoded fallback chain | FIXED | Replaced with dynamic chain explanation |
| `pipeline.md` backfill_embeddings schedule | FIXED | Added Scheduled Tasks section with backfill-embeddings (2 AM) |
| `models.md` finalized_at | FIXED | Removed from Article model example |

---

## Wave Parallelization Guide

All waves complete. No further work needed.

---

## Verification Results (2026-05-08)

### Code-Level Items - ALL COMPLETE

| Task | Status | Evidence |
|------|--------|----------|
| 5.1.1 Limiter slot leak | FIXED | `tasks/pipeline.py:413-420` resolves provider/model before acquiring resources |
| 5.1.2 _log_pipeline args | FIXED | `tasks/pipeline.py:60-67` uses correct order |
| 6.1 SSRF layering | COMPLETED | All adapters import from `utils/url.py` |
| 6.2 Services↔adapters | COMPLETED | TYPE_CHECKING pattern is acceptable |
| 6.3 review stage | COMPLETED | `"review": ("tasks.edit", "edit_article")` in pipeline_utils.py |
| 7.1 StageConfig | COMPLETED | Stub documented, SubagentStageConfig is actual |
| 7.2 Utils gaps | COMPLETED | All 5 utils modules implemented and verified |
| 7.3 DeepSeek | COMPLETED | References removed, file does not exist |
| 7.4 RSS gaps | COMPLETED | Validation, fallback, auth headers all present |

### Documentation Items

| Document | Status | Issues Remaining |
|----------|--------|------------------|
| architecture/pipeline.md | ACCURATE | None |
| architecture/subagent.md | ACCURATE | None |
| architecture/schemas.md | ACCURATE | None |
| architecture/models.md | ACCURATE | None |
| architecture/routes.md | ACCURATE | None |
| architecture/utils.md | ACCURATE | None |

---

## Implementation Detail: Limiter Slot Leak Fix

### Understanding the Bug

The limiter uses Redis keys in format: `ainews:llm:{provider_id}:{model}`

When `limiter.acquire()` is called, it increments a counter for the specific provider+model combination.

When `limiter.release()` is called, it decrements the same key.

**The Bug:** At line 417, early return was releasing with:
- `provider`: `rc.provider` (configured primary provider, e.g., "ollama-local")
- `model`: `rc.model` (which was `None` at this point - before `_run_stage_core` runs)

The actual acquired key was something like `ainews:llm:ollama-local:qwen3:8b`, but release used `ainews:llm:ollama-local:None`.

### Fix Applied

The code now resolves provider/model BEFORE acquiring resources:
```python
# Line 413-414
rc.provider, rc.model = _get_provider_for_stage(stage)
limiter, redis_client, lock_acquired = _acquire_stage_resources(...)
```

This ensures early return uses the correct resolved values.

---

## Implementation Detail: Utils Modules

### utils/text.py
Functions: `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`, `truncate`, `sanitize_html`, `extract_hashtags`

### utils/datetime.py
Functions: `parse_date(date_str) -> datetime | None`, `format_date(dt) -> str` (returns relative time strings), `time_ago(dt)` (alias for format_date)

### utils/hash.py
Functions: `generate_hash(data, algorithm="sha256") -> str`, `verify_hash(data, hash, algorithm="sha256") -> bool`

### utils/html.py
Functions: `strip_tags(html) -> str`, `linkify(text) -> str`, `extract_text(html) -> str`

### utils/security.py
Functions: `generate_token(length=32) -> str` (uses secrets.token_urlsafe), `constant_time_compare(a, b) -> bool` (uses hmac.compare_digest)

---

## Wave 8 Completion Details

### Task 8.1: Pipeline Documentation Drift - FIXED

Changes applied:
1. **Fallback Chain (lines 251-255):** Replaced hardcoded `ollama-local → openai → anthropic → gemini → deepseek` chain diagram with dynamic chain explanation referencing `providers.yaml` and `get_provider_chain()` function.
2. **Scheduled Tasks (new section):** Added "Scheduled Tasks" subsection in Topic Newsletters section documenting key Celery Beat tasks including `backfill-embeddings` (Daily 2 AM).

### Task 8.4: Models Documentation Drift - FIXED

Changes applied:
- **Article model example (line 61):** Removed `finalized_at = Column(DateTime)` from the Article model example. The model only has `published_at` for publication timestamp.

### Commits Made

| Branch | Commit | Description |
|--------|--------|-------------|
| `docs/pipeline-wave8-fix` | a825270 | docs(pipeline): fix hardcoded fallback chain diagram, add backfill schedule |
| `docs/models-wave8-fix` | 139dcc6 | docs(models): remove finalized_at from Article model example |

---

*End of file*
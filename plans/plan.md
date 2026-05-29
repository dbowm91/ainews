# Architecture Documentation Correction Plan

**Status:** IN PROGRESS
**Created:** 2026-05-29
**Updated:** 2026-05-29
**Source:** Consolidated from 15 architecture review files + verification against actual codebase
**Note:** Many items from the original plan were already fixed in the architecture docs. This updated plan reflects verified current state.

## Overview

This plan consolidates documentation corrections identified during architecture review. Items marked as **[DONE]** were verified as already correct in the architecture files. Items marked as **[NEEDS FIX]** require actual changes to the documentation files.

---

## Wave 1: Config Documentation (HIGH Priority)

### W1-1: providers.yaml Structure Documentation ✅ [DONE]
**File:** `architecture/config.md` (lines 300-364)
**Status:** Already correct - uses list-based structure with `id`, `type`, `enabled`, `config` fields

### W1-2: search_providers: vs search: Key Name ✅ [DONE]
**File:** `architecture/config.md` (line 339)
**Status:** Already correct - uses `search_providers:` (plural)

### W1-3: CELERY_RESULT_BACKEND Env Var Name ✅ [DONE]
**File:** `architecture/infrastructure.md` (line 103)
**Status:** Already correct - uses `CELERY_RESULT_BACKEND` with default DB `/1`

### W1-4: Google Env Var Names in Config Docs ✅ [DONE]
**File:** `architecture/config.md` (lines 349-350, 511-512)
**Status:** Already correct - uses `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`

---

## Wave 2: Schema Documentation Completeness (HIGH Priority)

### W2-1: Document RoleConfig.enabled Field [NEEDS FIX]
**File:** `architecture/schemas.md`
**Issue:** `RoleConfig` class is completely missing from `schemas.md`. The actual code at `schemas/pipeline.py:16-17` has:
```python
class RoleConfig(BaseModel):
    enabled: bool = True
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    # ... plus role-specific optional fields
```
**Action:** Add complete `RoleConfig` documentation to `schemas.md`

### W2-2: Document ReviewConfig [NEEDS FIX]
**File:** `architecture/schemas.md`
**Issue:** `ReviewConfig` at `schemas/pipeline.py:35-41` is not documented:
```python
class ReviewConfig(BaseModel):
    enabled: bool = False
    auto_publish_threshold: Optional[int] = None
```
**Action:** Add `ReviewConfig` section to `schemas.md`

### W2-3: Document SubagentStageConfig Fully [NEEDS FIX]
**File:** `architecture/schemas.md`
**Issue:** `SubagentStageConfig` 13-field schema is not enumerated in `schemas.md`. Actual fields at `schemas/pipeline.py:93-105`:
```python
class SubagentStageConfig(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = MAX_TOKENS_FIELD
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    system_prompt: Optional[str] = None
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_delay: float = Field(default=5.0, ge=0.0, le=60.0)
    task_template: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=5, ge=1, le=20)
```
**Action:** Add full `SubagentStageConfig` field documentation

### W2-4: Document RoleConfig Role-Specific Optional Fields [NEEDS FIX]
**File:** `architecture/schemas.md`
**Issue:** Role-specific optional fields not documented. Actual fields at `schemas/pipeline.py:24-32`:
- `system_prompt: Optional[str]` - all roles
- `min_score: Optional[int]` - selector only
- `web_search: Optional[bool]` - researcher only
- `web_search_max_results: Optional[int]` - researcher only
- `web_search_provider: Optional[str]` - researcher only
- `db_related_max: Optional[int]` - researcher only
- `max_article_text_length: Optional[int]` - researcher only
- `max_key_points: Optional[int]` - writer only
- `max_tags: Optional[int]` - editor only
**Action:** Document role-specific fields with role annotations

---

## Wave 3: Routes/API Documentation Corrections (HIGH Priority)

### W3-1: Fix Triple-Listed counts-by-status Endpoint [NEEDS FIX]
**File:** `architecture/routes.md`
**Issue:** `/articles/counts-by-status` appears THREE times:
- Line 115 - Admin API detailed table
- Line 215 - Admin API section bullet list
- Line 311 - Another Admin API table
**Action:** Remove duplicate listings, keep only one canonical entry

### W3-2: /admin/articles/<id>/original Endpoint [CLARIFICATION]
**File:** `architecture/routes.md`
**Issue:** Plan claimed endpoint missing from detailed table, but it's correctly at line 64 as an HTML route (not JSON API). This is correct behavior - no fix needed.
**Action:** No action needed - this was a false positive in original plan

### W3-3: Document CSRF Protection for JSON Endpoints [NEEDS FIX]
**File:** `architecture/routes.md`
**Issue:** `X-CSRFToken` header via `@validate_csrf_json` decorator not documented. Current doc only mentions Flask-WTF tokens.
**Action:** Add documentation about `X-CSRFToken` header mechanism for JSON API endpoints at `routes/decorators.py:72-94`

### W3-4: Document Global Default Rate Limit Value [NEEDS FIX]
**File:** `architecture/routes.md`
**Issue:** Global default rate limit value not specified. Actual default is `60 per minute` (configurable via `RATELIMIT_DEFAULT` env var).
**Action:** Document that global default rate limit is `60 per minute`

---

## Wave 4: Infrastructure/Services Documentation (MEDIUM Priority)

### W4-1: services/url.py vs utils/url.py Relationship ✅ [DONE]
**File:** `architecture/infrastructure.md`
**Status:** Already documented correctly with relationship explanation

### W4-2: Update Key Files Table with New Services ✅ [DONE]
**File:** `architecture/infrastructure.md`
**Status:** Already includes `services/alerts.py`, `services/quality_report.py`, `services/stage_cost.py`
**Note:** File is `quality_report.py` not `quality_report_service.py` as originally noted

### W4-3: Remove Stale _degrade_and_advance Reference ✅ [DONE]
**File:** `architecture/tasks.md`
**Status:** Already correct - documentation properly attributes `_degrade_and_advance` to `services/pipeline_degradation.py` with alias

### W4-4: Clarify services/url.py Config Support Status ✅ [DONE]
**File:** `architecture/utils.md`
**Status:** `_get_dns_cache_config()` IS called at `services/url.py:123` - not dead code as originally claimed

### W4-5: CONFIG_CACHE_REDIS_URL and CONFIG_CACHE_REDIS_PASSWORD Env Vars ✅ [DONE]
**File:** `architecture/config.md`
**Status:** Already documented at lines 506-507

---

## Wave 5: Clarifications and Minor Improvements (MEDIUM Priority)

### W5-1: Pagination Implementation Differences ✅ [DONE]
**File:** `architecture/adapters.md`
**Status:** Already documented with implementation differences noted

### W5-2: article_tags Table Definition ✅ [DONE]
**File:** `architecture/models.md`
**Status:** Already documented at lines 189-200

### W5-3: Article.newsletters Backref ✅ [DONE]
**File:** `architecture/models.md`
**Status:** Already documented at line 202

### W5-4: models.py Root Re-export ✅ [DONE]
**File:** `architecture/overview.md`
**Status:** Already documented at line 162

### W5-5: Enumerate routes/admin/api/ Contents [NEEDS FIX]
**File:** `architecture/overview.md`
**Issue:** Directory shown but contents not enumerated. Actual contents (17 files):
- replay.py, source_intelligence.py, newsletter.py, quality.py, topic_gap.py
- pipeline.py, search.py, alerts.py, articles.py, health.py
- sources.py, webhooks.py, config.py, audit.py, utils.py, __init__.py
**Action:** Add enumeration of `routes/admin/api/` contents

### W5-6: Middleware Chain Order ✅ [DONE]
**File:** `architecture/subagent.md`
**Status:** Already documented with execution flow diagram

### W5-7: copy.deepcopy() Fix for Cached Tools ✅ [DONE]
**File:** `architecture/subagent.md`
**Status:** Already documented at line 142

### W5-8: Document Self-Correction Retry Mechanism [NEEDS FIX]
**File:** `architecture/subagent.md`
**Issue:** `self_corrected` flag and retry logic at `runner.py:401-417` not documented in detail. Brief mention at line 141 but no details.
**Action:** Document the self-correction mechanism with `self_corrected` flag

### W5-9: Selector retry_max=20 Exception ✅ [DONE]
**File:** `architecture/tasks.md`
**Status:** Already documented at line 118

### W5-10: degradation_count >= 2 Meaning ✅ [DONE]
**File:** `architecture/tasks.md`
**Status:** Already documented at line 201

### W5-11: Hybrid Search Enabled Status ✅ [DONE]
**File:** `architecture/search-providers.md`
**Status:** Already documented with clarification (for article search, not web search)

### W5-12: Document _format_subagent_prompt() Helper [NEEDS FIX]
**File:** `architecture/subagent.md`
**Issue:** Helper function at `services/subagent/utils.py:30` not documented
**Action:** Document `_format_subagent_prompt()` helper used by `run_subagent_with_tools()`

### W5-13: Document max_iterations Default [NEEDS FIX]
**File:** `architecture/subagent.md`
**Issue:** Default of 5 not explicitly documented
**Action:** Add explicit statement that `max_iterations` defaults to 5

### W5-14: session.py is Crawl Session ✅ [DONE]
**File:** `architecture/search-providers.md`
**Status:** Already documented as crawl session (SSRFSafeRedirectHandler)

### W5-15: Document Two Different truncate() Functions [NEEDS FIX]
**File:** `architecture/utils.md`
**Issue:** `utils/text.py:truncate()` vs `BaseSourceAdapter._truncate()` (adapters/base.py:104) have different behavior - word-boundary breaking vs simple slicing
**Action:** Document both truncate functions with behavior differences

### W5-16: Document SMTPConnectionPool [NEEDS FIX]
**File:** `architecture/services.md`
**Issue:** `SMTPConnectionPool` class at `services/email.py:13` not documented
**Action:** Add `SMTPConnectionPool` to email module documentation

### W5-17: Document cleanup_old_versions_hour Limitation [NEEDS FIX]
**File:** `architecture/pipeline.md`
**Issue:** Only hour controllable, minute not configurable (hardcoded to 45)
**Action:** Document this limitation in the Celery Beat Schedule section

### W5-18: Subagent Task Template Example ✅ [DONE]
**File:** `architecture/prompts.md`
**Status:** Already correctly documents file-based templates

---

## Summary

| Wave | Items | Done | Needs Fix |
|------|-------|------|-----------|
| W1 | 4 | 4 | 0 |
| W2 | 4 | 0 | 4 |
| W3 | 4 | 1 (W3-2) | 3 |
| W4 | 5 | 5 | 0 |
| W5 | 18 | 12 | 6 |

**Total: 35 action items - 22 already done, 13 need fixing**

---

## Implementation Notes

### Parallelization Strategy - WAVE Assignment

**Wave A (Config + Schemas - HIGH Priority):**
Can run in parallel with Wave B:
- W2-1: Document RoleConfig.enabled
- W2-2: Document ReviewConfig
- W2-3: Document SubagentStageConfig fields
- W2-4: Document RoleConfig role-specific fields

**Wave B (Routes - HIGH Priority):**
Can run in parallel with Wave A:
- W3-1: Fix triple-listed counts-by-status
- W3-3: Document CSRF protection
- W3-4: Document default rate limit

**Wave C (Minor Improvements - MEDIUM Priority):**
After Waves A and B complete:
- W5-5: Enumerate routes/admin/api/ contents
- W5-8: Document self-correction mechanism
- W5-12: Document _format_subagent_prompt()
- W5-13: Document max_iterations default
- W5-15: Document two truncate() functions
- W5-16: Document SMTPConnectionPool
- W5-17: Document cleanup_old_versions_hour limitation

### Verification Steps
Before implementing any item:
1. Read the actual architecture file
2. Verify the issue still exists
3. If already fixed, mark as `[DONE]` and skip
4. If needs fix, implement and verify

### Testing
After changes, run:
```bash
ruff check architecture/ --exclude .venv
```

---

## Items Removed from Original Plan (Already Fixed or False Positives)

The following were in the original plan but verified as already correct:
- providers.yaml structure (W1-1) ✅
- search_providers: key (W1-2) ✅
- CELERY_RESULT_BACKEND env var (W1-3) ✅
- Google env var names (W1-4) ✅
- services/url.py vs utils/url.py (W4-1) ✅
- Key Files table completeness (W4-2) ✅
- _degrade_and_advance reference (W4-3) ✅
- services/url.py config support (W4-4) - NOT dead code ✅
- CONFIG_CACHE_REDIS_URL env vars (W4-5) ✅
- Pagination differences (W5-1) ✅
- article_tags table (W5-2) ✅
- Article.newsletters backref (W5-3) ✅
- models.py root re-export (W5-4) ✅
- Middleware chain order (W5-6) ✅
- copy.deepcopy() fix (W5-7) ✅
- Selector retry_max=20 (W5-9) ✅
- degradation_count >= 2 (W5-10) ✅
- Hybrid Search status (W5-11) ✅
- session.py characterization (W5-14) ✅
- Subagent task template (W5-18) ✅
- W3-2: /admin/articles/<id>/original - false positive, correctly documented as HTML route ✅

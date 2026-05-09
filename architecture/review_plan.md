# Architecture Review Plan

**Status:** INCOMPLETE - Verification in Progress
**Last Updated:** 2026-05-09

## Modules to Review

| # | Module | Architecture Doc | Output Plan | Status |
|---|--------|-----------------|-------------|--------|
| 1 | Overview | `architecture/overview.md` | `plans/review_00_overview.md` | VERIFIED |
| 2 | Models | `architecture/models.md` | `plans/review_05_models.md` | VERIFIED |
| 3 | Services | `architecture/services.md` | `plans/review_02_services.md` | VERIFIED |
| 4 | Adapters | `architecture/adapters.md` | `plans/review_04_adapters.md` | VERIFIED |
| 5 | Schemas | `architecture/schemas.md` | `plans/review_08_schemas.md` | VERIFIED |
| 6 | Routes | `architecture/routes.md` | `plans/review_06_routes.md` | VERIFIED |
| 7 | Tasks | `architecture/tasks.md` | `plans/review_07_tasks.md` | VERIFIED |
| 8 | Pipeline | `architecture/pipeline.md` | `plans/review_01_pipeline.md` | VERIFIED |
| 9 | Subagent | `architecture/subagent.md` | `plans/review_03_subagent.md` | VERIFIED |
| 10 | Utils | `architecture/utils.md` | `plans/review_09_utils.md` | VERIFIED |

## Review Process

For each module, the subagent will:

1. **Read the architecture document** to understand the intended design
2. **Verify claims** by checking if the code implements what the docs claim
3. **Identify discrepancies** between documentation and implementation
4. **Find bugs and issues** in the implementation
5. **Propose improvements** based on best practices and the codebase conventions

## Subagent Instructions

Each subagent should:

- Read the designated architecture document fully
- Search the codebase for the relevant module code
- Compare documentation claims against actual implementation
- Check for:
  - Missing functionality described in docs
  - undocumented functionality in code
  - Bug-prone patterns or edge cases
  - Violations of the architecture principles (e.g., adapters importing from services)
  - Security concerns (fail-closed, proper validation)
  - Performance issues (caching, async patterns)
- Write a detailed improvement plan to the designated output path in `plans/`

## Execution

Run all subagent reviews in parallel for efficiency. Each subagent operates independently and writes its output to the plans directory.

## Review Summary (2026-05-09)

### Previous Bugs Found (2026-05-08)

| Bug | Location | Severity | Fix |
|-----|----------|----------|-----|
| Missing `import random` | `adapters/web.py:2` | Critical | Added import |

### Issues Found This Session

| Issue | Location | Severity | Fix Applied |
|-------|----------|----------|-------------|
| Adapters importing from `services.url` instead of `utils.url` | `adapters/rss.py`, `adapters/api.py`, `adapters/web.py`, `adapters/session.py` | Critical | Fixed imports to use `utils.url` per architecture layering |
| `validate_url_safe` return type documentation error | `architecture/utils.md:19` | Minor | Changed `-> bool` to `-> str` to match actual return type |

### Verification Results

#### Wave 5: Critical Bug Fixes - VERIFIED COMPLETE

| Bug | Location | Status |
|-----|----------|--------|
| BUG-5.1.1 (Limiter Slot Leak) | tasks/pipeline.py:413-420 | FIXED - provider/model resolved before `_acquire_stage_resources()` |
| BUG-5.1.2 (_log_pipeline arg order) | tasks/pipeline.py:60-67, 282 | FIXED - all call sites use correct argument order |

#### Wave 6: Layering & Architecture - VERIFIED WITH FIX

| Task | Status | Notes |
|------|--------|-------|
| 6.1 SSRF Layering | **FIXED** | All 4 adapters now correctly import from `utils.url` |
| 6.2 TYPE_CHECKING pattern | PASS | `services/crawling.py` correctly uses TYPE_CHECKING |
| 6.3 review stage | PASS | `"review": ("tasks.edit", "edit_article")` in pipeline_utils.py |

#### Wave 7: Implementation Gaps - VERIFIED COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 7.1 StageConfig stub | PASS | `StageConfig` only has `tools` field, actual config in `SubagentStageConfig`/`RoleConfig` |
| 7.2 Utils modules | PASS | All 5 utils modules implemented with correct functions |
| 7.3 DeepSeek references | PASS | No DeepSeek provider implemented |
| 7.4 RSS gaps | PASS | `_validate_feed()`, `_scrape_feed_fallback()`, auth headers all present |

#### Wave 8: Documentation Alignment - VERIFIED WITH FIX

| Task | Status | Notes |
|------|--------|-------|
| 8.1 Pipeline docs | PASS | Fallback chain dynamic, backfill at 2AM, max_tokens correct |
| 8.2 Subagent docs | PASS | Signature, return type, tool functions all correct |
| 8.3 Schemas docs | PASS | StageConfig, ResearchBrief, CondensedArticle, NewsletterBrief all correct |
| 8.4 Models docs | PASS | No `finalized_at`, `signal`, `source_type`, `Text` embedding all correct |
| 8.5 Routes docs | PASS | Root-level endpoints, newsletter-click, /share not implemented all noted |
| 8.6 Utils docs | **FIXED** | Changed `validate_url_safe` return type from `bool` to `str` |

### Key Findings

1. **Subagent location**: `services/subagent/` not top-level `subagent/`
2. **API endpoints**: Root-level (`/articles`) not prefixed (`/api/v1/articles`)
3. **StageConfig**: Only has `tools` field, actual config in `RoleConfig`/`SubagentStageConfig`
4. **ResearchBrief**: Much more complex structure with nested models not simple fields
5. **ExecutiveSummary**: Only has `summary` field, not the 6 documented fields
6. **Celery Beat**: 14 tasks exist, only 5 were documented
7. **SSRF Layering**: Adapters should import from `utils/url.py` NOT `services/url.py`
8. **URL Validation Return Type**: `validate_url_safe` returns `str` not `bool`

---

## Changes Made This Session

### 2026-05-09

#### Fix: SSRF Import Layering (Wave 6 Task 6.1)

Changed adapters to import from `utils/url.py` instead of `services/url.py` to follow architecture layering:

- `adapters/rss.py:12`: `from services.url import` → `from utils.url import`
- `adapters/api.py:11`: `from services.url import` → `from utils.url import`
- `adapters/web.py:15`: `from services.url import` → `from utils.url import`
- `adapters/session.py:8`: `from services.url import` → `from utils.url import`

#### Fix: Utils Documentation (Wave 8 Task 8.6)

- `architecture/utils.md:19`: Changed `def validate_url_safe(url: str) -> bool:` to `def validate_url_safe(url: str) -> str:` with note that it returns the validated URL string

---

## Current Status

All waves verified. All previous issues from 2026-05-08 are confirmed fixed. One additional issue found and fixed this session (SSRF import layering). One documentation discrepancy found and fixed (utils.md return type).

**Remaining Work:** None identified. All architecture documentation matches implementation.
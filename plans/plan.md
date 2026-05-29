# Architecture Documentation Correction Plan

**Status:** PENDING
**Created:** 2026-05-29
**Source:** Consolidated from 15 architecture review files
**Note:** Some items may already be fixed - verify each item before implementing.

## Overview

This plan consolidates documentation corrections identified during the architecture review. Items marked as **[VERIFY]** should be confirmed against the actual codebase before implementing.

---

## Wave 1: Critical Documentation Corrections (HIGH Priority)

### W1-1: Fix providers.yaml Structure Documentation
**File:** `architecture/config.md`
**Status:** [VERIFY] - May already be fixed
**Issue:** Documentation should show `providers.yaml` as a list of provider objects with `id`, `type`, `enabled`, `config` fields.

---

### W1-2: Fix search_providers: vs search: Key Name
**File:** `architecture/config.md`
**Status:** [VERIFY] - May already be fixed
**Issue:** Use `search_providers:` (plural) not `search:`.

---

### W1-3: Fix CELERY_RESULT_BACKEND Env Var Name
**File:** `architecture/infrastructure.md`
**Status:** [VERIFY] - May already be fixed
**Issue:** Use `CELERY_RESULT_BACKEND` (not `REDIS_URL`), default DB is `/1` (not `/0`).

---

### W1-4: Fix Google Env Var Names in Config Docs
**File:** `architecture/config.md`
**Status:** [VERIFY] - May already be fixed
**Issue:** Correct names are `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`.

---

## Wave 2: Schema Documentation Completeness (MEDIUM Priority)

### W2-1: Document RoleConfig.enabled Field
**File:** `architecture/schemas.md`
**Status:** [VERIFY] - Defined in config.md but not schemas.md
**Issue:** `RoleConfig` has `enabled: bool = True` field not documented in schemas.md.

---

### W2-2: Document ReviewConfig
**File:** `architecture/schemas.md`
**Status:** [VERIFY] - Defined in config.md but not schemas.md
**Issue:** `ReviewConfig` with `enabled` and `auto_publish_threshold` not documented in schemas.md.

---

### W2-3: Document SubagentStageConfig Fully
**File:** `architecture/schemas.md`
**Status:** [VERIFY] - May already be documented
**Issue:** `SubagentStageConfig` 14-field schema may need fuller documentation.

---

### W2-4: Document RoleConfig Role-Specific Optional Fields
**File:** `architecture/schemas.md`
**Status:** [VERIFY]
**Issue:** Role-specific options not fully documented:
- `system_prompt`, `min_score`, `web_search`, `web_search_max_results`
- `web_search_provider`, `db_related_max`, `max_article_text_length`
- `max_key_points`, `max_tags`

---

## Wave 3: Routes/API Documentation Corrections (MEDIUM Priority)

### W3-1: Fix Triple-Listed counts-by-status Endpoint
**File:** `architecture/routes.md`
**Status:** [NEEDS FIX] - Listed at lines 115, 215, 311
**Issue:** `/articles/counts-by-status` listed 3 times (in 3 different tables).

---

### W3-2: Add Missing /admin/articles/<id>/original to Detailed Table
**File:** `architecture/routes.md`
**Status:** [NEEDS FIX] - Listed at line 64 but missing from detailed table
**Issue:** Endpoint exists at line 64 but not in detailed Admin Routes table (lines 57-106).

---

### W3-3: Document CSRF Protection for JSON Endpoints
**File:** `architecture/routes.md`
**Status:** [NEEDS CLARIFICATION]
**Issue:** JSON API uses `X-CSRFToken` header via `@validate_csrf_json` decorator not documented.

---

### W3-4: Document Global Default Rate Limit Value
**File:** `architecture/routes.md`
**Status:** [NEEDS CLARIFICATION]
**Issue:** Global default rate limit value not specified.

---

## Wave 4: Infrastructure/Services Documentation (MEDIUM Priority)

### W4-1: Document services/url.py vs utils/url.py Relationship
**File:** `architecture/infrastructure.md`
**Status:** [NEEDS CLARIFICATION]
**Issue:** Relationship documented in AGENTS.md but infrastructure.md Key Files table may need update.

---

### W4-2: Update Key Files Table with New Services
**File:** `architecture/infrastructure.md`
**Status:** [NEEDS CLARIFICATION]
**Issue:** Key Files table may be missing:
- `services/alerts.py` (alerting layer)
- `services/quality_report_service.py` (quality report service)
- `services/stage_cost.py` (cost estimation)

---

### W4-3: Remove Stale _degrade_and_advance Reference
**File:** `architecture/tasks.md`
**Status:** [NEEDS FIX]
**Issue:** Documentation claims `tasks/pipeline.py` has a local `_degrade_and_advance` but function only exists in `services/pipeline_degradation.py`.

---

### W4-4: Clarify services/url.py Config Support Status
**File:** `architecture/utils.md`
**Status:** [NEEDS CLARIFICATION]
**Issue:** `_get_dns_cache_config()` exists but is never called - hardcoded values used instead. Clarify whether config support is implemented or dead code.

---

### W4-5: Add CONFIG_CACHE_REDIS_URL and CONFIG_CACHE_REDIS_PASSWORD Env Vars
**File:** `architecture/config.md`
**Status:** [VERIFY]
**Issue:** Missing `CONFIG_CACHE_REDIS_URL` and `CONFIG_CACHE_REDIS_PASSWORD` env vars.

---

## Wave 5: Clarifications and Minor Improvements (LOW Priority)

### W5-1: Clarify Pagination Implementation Differences
**File:** `architecture/adapters.md`
**Issue:** API adapter and Web adapter pagination implementations differ significantly.

### W5-2: Add article_tags Table Definition
**File:** `architecture/models.md`
**Issue:** Many-to-many table definition not explicitly documented.

### W5-3: Document Article.newsletters Backref
**File:** `architecture/models.md`
**Issue:** Dynamic backref relationship not documented.

### W5-4: Add models.py Root Re-export
**File:** `architecture/overview.md`
**Issue:** `models.py` root re-export not documented.

### W5-5: Enumerate routes/admin/api/ Contents
**File:** `architecture/overview.md`
**Issue:** Directory shown but contents not enumerated.

### W5-6: Clarify Middleware Chain Order
**File:** `architecture/subagent.md`
**Issue:** Application order vs execution order clarification needed.

### W5-7: Document copy.deepcopy() Fix for Cached Tools
**File:** `architecture/subagent.md`
**Issue:** `copy.deepcopy(tool.fn)` pattern prevents middleware compounding - not documented.

### W5-8: Document Self-Correction Retry Mechanism
**File:** `architecture/subagent.md`
**Issue:** `self_corrected` flag and retry logic not documented.

### W5-9: Document Selector retry_max=20 Exception
**File:** `architecture/tasks.md`
**Issue:** Selector stage uses `retry_max=20` (vs default 15) not noted.

### W5-10: Clarify degradation_count >= 2 Meaning
**File:** `architecture/tasks.md`
**Issue:** Counts failed stages, not retries of a single stage.

### W5-11: Clarify Hybrid Search Enabled Status
**File:** `architecture/search-providers.md`
**Issue:** Hybrid is for article search, not web search (DuckDuckGo is web search default).

### W5-12: Document _format_subagent_prompt() Helper
**File:** `architecture/subagent.md`
**Issue:** Helper function not documented.

### W5-13: Document max_iterations Default
**File:** `architecture/subagent.md`
**Issue:** Default of 5 not explicitly documented.

### W5-14: Clarify session.py is Crawl Session Management
**File:** `architecture/search-providers.md`
**Issue:** session.py is SSRFSafeRedirectHandler for crawling, not search-specific.

### W5-15: Document Two Different truncate() Functions
**File:** `architecture/utils.md`
**Issue:** `utils/text.py:truncate()` vs `BaseSourceAdapter._truncate()` have different behavior.

### W5-16: Consider Acknowledging SMTPConnectionPool
**File:** `architecture/services.md`
**Issue:** `SMTPConnectionPool` class exists but not mentioned.

### W5-17: Document cleanup_old_versions_hour Limitation
**File:** `architecture/pipeline.md`
**Issue:** Only hour controllable, minute not configurable.

### W5-18: Update Subagent Task Template Example
**File:** `architecture/prompts.md`
**Issue:** Example shows dict but templates are file-based.

---

## Summary

| Wave | Items | Status |
|------|-------|--------|
| W1 | 4 | [VERIFY] Most may be fixed |
| W2 | 4 | [VERIFY/NEEDS FIX] |
| W3 | 4 | [NEEDS FIX] 2 confirmed |
| W4 | 5 | [VERIFICATION NEEDED] |
| W5 | 18 | [LOW PRIORITY] |

**Total: 35 action items**

---

## Implementation Notes

### Parallelization Strategy
Each wave can be assigned to independent subagents. Within waves, items are independent except where noted.

### Verification Steps
Before implementing any item:
1. Read the actual architecture file
2. Compare with the issue description
3. If already fixed, mark as `[DONE]` and skip
4. If needs fix, implement and verify

### Testing
After changes, run:
```bash
ruff check architecture/ --exclude .venv
```

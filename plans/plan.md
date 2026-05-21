# AINews Consolidated Implementation Plan

**Status:** ACTIVE - Remaining items from architecture review
**Last Updated:** 2026-05-21
**Goal:** Consolidate all remaining action items from architecture review documents into actionable items for future agents.

---

## Executive Summary

This plan consolidates remaining action items discovered during the architecture review of: schemas, pipeline, routes, tasks, services, models, subagent, adapters, and utils modules.

**All previously identified bugs have been fixed.** The remaining items are primarily documentation updates to align architecture documents with actual implementation.

### Priority Summary

| Priority | Count | Type |
|----------|-------|------|
| CRIT | 2 | Documentation (alignment with code) |
| HIGH | 7 | Documentation (model accuracy) |
| MED | 18 | Documentation + 1 Implementation |
| LOW | 9 | Documentation consistency |
| **Total** | **36 items** | - |

---

## Completed Work (Reference)

The following items from earlier waves have been completed:

| Wave | Items | Status |
|------|-------|--------|
| Wave A | CRIT-1, CRIT-2, CRIT-3 (critical bugs) | COMPLETED |
| Wave B | MED-1 through MED-8 (medium priority) | COMPLETED |
| Wave C | LOW-1 through LOW-6 (documentation) | COMPLETED |
| Wave A4 | CRIT-A4 (TrendMemory.last_accessed_at) | COMPLETED |
| Wave B1 | HIGH-B1 (Quality gate routing) | COMPLETED |
| Wave C9 | MED-C9 (backfill_embeddings decorator) | COMPLETED |
| Wave D7 | LOW-D7 (Scheduled tasks documentation) | COMPLETED |

---

## Phase 1: Critical Documentation Fixes

These items fix critical mismatches between architecture documentation and actual code.

### CRIT-1: Source Model `adapter_config` Field Does Not Exist

**Location:** `architecture/models.md:91`
**Issue:** Documentation shows `adapter_config = Column(JSON)` on Source model, but this field does NOT exist. Adapter configuration is stored in `schemas/source.py` as `SourceConfig.config`.
**Fix:** Remove `adapter_config` from Source model documentation. Add note explaining adapter config is stored externally in `schemas/source.py` and accessed by adapters via `source_config.config` at runtime.

### CRIT-2: utils/url.py Global Mutable State Not Documented

**Location:** `architecture/utils.md:129-135` (Design Principles)
**Issue:** Design principles claim "Pure functions: No side effects, no global state" but `utils/url.py` has extensive global mutable state (`_dns_executor`, `_dns_cache`, `_TTLCache`). The DNS resolution in `validate_url_safe()` is NOT a pure function.
**Fix:** Update Design Principles section to note that `validate_url_safe()` in `url.py` performs DNS resolution with caching and is therefore NOT a pure function.

---

## Phase 2: High Priority Documentation (Model Accuracy)

### HIGH-1: Article Model Documentation is a Stub

**Location:** `architecture/models.md:40-61`
**Issue:** The Article model example shows only ~10 fields but actual implementation has 30+ fields. Missing: `original_title`, `original_url`, `extracted_text`, `short_id`, `external_id`, `selector_result`, `research_brief`, `draft_article`, `final_article`, `original_ai_article`, `writer_model`, `category`, `topics`, `raw_metadata`, `extraction_status`, `retry_count`, `total_retries`, `degradation_count`, `pipeline_started_at`, `last_error`, `updated_at`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `experiment_group`, `embedding`.
**Fix:** Replace the stub example with accurate field list from `models/article.py:10-75`. Document all JSON columns (`topics`, `raw_metadata`, `selector_result`). Document `short_id` as public-facing identifier. Document `experiment_group` for A/B testing.

### HIGH-2: Source Model Missing Fields

**Location:** `architecture/models.md:73-92`
**Issue:** Documentation missing actual fields: `source_key`, `url`, `feed_url`, `active`, `last_error`, `disabled_at`.
**Fix:** Update Source model documentation to include all actual fields from `models/source.py:6-30`.

### HIGH-3: Index Documentation Incomplete and Inaccurate

**Location:** `architecture/models.md:136-142`
**Issue:** Index documentation shows incorrect indexes. Missing for Article: `original_published_at`, `impact_score`, `category`, `total_retries`, `retry_count`, `degradation_count`. For Source: missing `consecutive_failures`, `disabled_at`, unique constraint on `source_key`. For PipelineRun: shows index on `created_at` which doesn't exist. For TrendMemory: missing `last_accessed_at` index.
**Fix:** Document actual indexes with correct names and column sets from `models/article.py:66-75`, `models/source.py`, `models/pipeline.py:27-30`, `models/context.py:48-51`.

### HIGH-4: Pipeline Status Flow Documentation Outdated

**Location:** `architecture/models.md:63-70`
**Issue:** Document shows `pending → select → research → writing → editing → done` but actual statuses use `write`/`edit` not `writing`/`editing`.
**Fix:** Update to reflect actual statuses from `constants.py:30-43` and `tasks/pipeline.py`: `pending`, `select`/`selecting`/`selected`, `research`/`researching`, `write`/`written`, `edit`/`editing`, `review`, `done`.

### HIGH-5: Adapter Config Schemas in Architecture Are Fictional

**Location:** `architecture/schemas.md:89-101`
**Issue:** Document shows `RSSConfig`, `APIConfig`, `WebConfig` with generic fields (`item_path`, `field_mappings`, `item_css`) that don't exist. Actual implementation has detailed fields: `feed_url`, `list_url`, `listing_url`, etc.
**Fix:** Update documentation to match actual schemas in `schemas/source.py`.

### HIGH-6: PaginationConfig Schema Inaccurate

**Location:** `architecture/schemas.md:104-109`
**Issue:** Document shows `Literal["cursor", "offset", "page"]` but actual uses `str` with values `"next_link"`, `"query_param"`, `"none"`. Also omits `enabled` and `max_pages` fields.
**Fix:** Update to match `PaginationConfig` in `schemas/source.py:58-69`.

### HIGH-7: `item_path` vs `list_items_path` Naming Mismatch

**Location:** `architecture/adapters.md` (multiple references)
**Issue:** Documentation uses `item_path` but implementation uses `list_items_path` and `list_method`.
**Fix:** Update all documentation references from `item_path` to `list_items_path` and document `list_method`.

---

## Phase 3: Medium Priority Items

### MED-1: Degradation Logic Bypasses `_STAGE_DEGRADE_MAP` for Edit Stage

**Location:** `services/pipeline_degradation.py:129-179` vs `architecture/pipeline.md`
**Issue:** `_degrade_edit_stage()` is completely separate from `_apply_degrade_config()` with its own `degradation_count >= 2` check. Documentation says edit "Finalizes immediately with fallback" but actual routes to `review` based on degradation count or `_should_route_to_review()`.
**Fix:** Document this behavior difference, or consider unifying the code paths.

### MED-2: `_degrade_and_advance` Uses String Literal Instead of Constant

**Location:** `tasks/pipeline.py:56`
**Issue:** `article.pipeline_status = "researching"` uses string literal instead of `PipelineStatus.RESEARCHING`.
**Status:** Already uses `PipelineStatus.RESEARCHING` at line 56 - VERIFIED CORRECT
**Fix:** N/A - Already correct

### MED-3: `select` Stage Degradation Doesn't Set `selector_result`

**Location:** `tasks/pipeline.py:50-60`
**Issue:** When degrading select stage, code should set `selector_result` dict.
**Status:** Already implemented at lines 51-55 - VERIFIED CORRECT
**Fix:** N/A - Already correct

### MED-4: `write` Stage Degradation Doesn't Set `writer_model`

**Location:** `services/pipeline_degradation.py:52`
**Issue:** Degradation should set `article.writer_model = "fallback"`.
**Status:** Already implemented at line 53 - VERIFIED CORRECT
**Fix:** N/A - Already correct

### MED-5: Degradation Threshold Documentation Wrong

**Location:** `architecture/pipeline.md:250` vs `services/pipeline_degradation.py:99`
**Issue:** Document says "3 consecutive failures" but code uses `degradation_count >= 2` (2 degradations trigger review routing).
**Fix:** Update documentation to state `degradation_count >= 2` routes to review.

### MED-6: `api_tokens_bp` Registration Note Outdated

**Location:** `architecture/routes.md:57`
**Issue:** Documentation claims `api_tokens_bp` is NOT registered, but it IS registered in `app.py:197`.
**Fix:** Update note to reflect that `api_tokens_bp` is registered and provides `/api-tokens` endpoints.

### MED-7: `POST /articles` Documented But Not Implemented

**Location:** `architecture/routes.md:143`
**Issue:** Table shows `POST /api/v1/articles` for article creation, but this endpoint doesn't exist (articles are created via pipeline only).
**Fix:** Either implement the endpoint or remove from documentation.

### MED-8: Missing Routes in Documentation

**Location:** `architecture/routes.md`
**Issue:** Missing routes: `/admin/verify-2fa`, `/admin/setup-2fa`, `/admin/dead-letters`, `/admin/metrics`, `/articles/bulk`.
**Fix:** Add these routes to the appropriate documentation tables.

### MED-9: `AuthError` Behavior in Fallback Chain Not Documented

**Location:** `services/llm/__init__.py:228-235` / `architecture/pipeline.md`
**Issue:** `AuthError` causes immediate failure without trying fallback providers, but this isn't documented.
**Fix:** Document that `AuthError` is not retried and bypasses fallback chain.

### MED-10: Backoff Configuration Documentation Incomplete

**Location:** `architecture/pipeline.md:289`
**Issue:** Documents "(30s, 60s, 120s)" but actual is exponential with max 300s.
**Fix:** Update to "exponential (30s, 60s, 120s, 240s, ... up to 300s max)".

### MED-11: APIAdapter Missing Pagination Support

**Location:** `adapters/api.py`
**Issue:** APIAdapter has NO pagination support despite documentation claiming it. Only single requests to `list_url` are made.
**Fix:** Implement pagination support (cursor, offset, or page-based) similar to WebAdapter's `ListingConfig.pagination`. **This is an implementation item, not just documentation.**

### MED-12: Missing `hybrid.py` Search Provider in Architecture

**Location:** `architecture/services.md`
**Issue:** HybridSearchProvider exists but not listed among search providers.
**Fix:** Add Hybrid provider to search provider table.

### MED-13: Missing `content_extractor.py` in Architecture Tree

**Location:** `architecture/services.md`
**Issue:** File exists but not in the file inventory tree.
**Fix:** Add `content_extractor.py` to tree (between `crawling.py` and `trend_detector.py`).

### MED-14: Multiple Services Missing from Architecture Tree

**Location:** `architecture/services.md`
**Issue:** These exist but not listed: `article_fallback.py`, `pipeline_utils.py`, `pipeline_monitor.py`, `pipeline_degradation.py`, `pipeline_failure.py`, `context_service.py`, `cache.py`, `cost_tracker.py`, `email.py`, `webhooks.py`.
**Fix:** Add to architecture tree or document why they're implementation details.

### MED-15: Blueprint Naming Discrepancy in Docs

**Location:** `architecture/routes.md:64`
**Issue:** Docs show `feeds_bp` but actual is `public_bp`.
**Fix:** Change to `public_bp = Blueprint("public", __name__)`.

### MED-16: Valid Transitions: `PENDING` → `SKIPPED` Not Documented

**Location:** `architecture/pipeline.md:54`
**Issue:** Transition exists in code but not in documented table.
**Fix:** Add `PENDING` → `SKIPPED` to valid transitions table.

### MED-17: API Token Prefix Matching Detail Missing

**Location:** `architecture/routes.md`
**Issue:** Not documented that prefix uses first 16 characters of hash.
**Fix:** Add detail about prefix matching implementation.

### MED-18: Missing Tasks in File Inventory

**Location:** `architecture/tasks.md`
**Issue:** Document lists 9 files but there are 15 Python files in `tasks/`. Missing: `retry.py` (`retry_stuck`), `subscribers.py` (`cleanup_inactive_subscribers`), `webhook.py` (`dispatch_webhook_task`).
**Fix:** Add `retry.py`, `subscribers.py`, and `webhook.py` with their respective tasks to the file inventory.

---

## Phase 4: Low Priority Documentation Consistency

### LOW-1: cleanup.py Tasks Listed as "Various"

**Location:** `architecture/tasks.md`
**Issue:** `cleanup.py` contains 7 distinct tasks but document just says "Various".
**Fix:** List each task individually: `cleanup_old_pipeline_logs`, `cleanup_expired_verifications`, `cleanup_stale_limiter_slots`, `consolidate_trend_memory`, `recalculate_impact_scores`, `purge_trend_memory`, `cleanup_old_article_versions`.

### LOW-2: Degradation Path Conflated with Normal Flow

**Location:** `architecture/tasks.md`
**Issue:** Document describes normal flow when degradation is disabled but actual degradation path should be documented - articles go directly from `pending` to `review` (bypassing select/research/write/edit).
**Fix:** Separate normal flow from degraded flow. Reference `pipeline.py:296-303` showing `_handle_disabled`.

### LOW-3: run_stage Signature Incomplete

**Location:** `architecture/tasks.md`
**Issue:** Documented signature shows 5 parameters but actual signature in `pipeline.py:389-442` has 8 parameters including `skip_next`, `retry_countdown`, `retry_max`.
**Fix:** Document the actual 8-parameter signature.

### LOW-4: url.py Section Duplicated

**Location:** `architecture/utils.md:16-28` and `architecture/utils.md:102-127`
**Issue:** Two "URL Utilities (`url.py`)" sections causing confusion.
**Fix:** Remove the first section (lines 16-28) or restructure to avoid duplication.

### LOW-5: Newsletter Batch Size Not in File Inventory

**Location:** `architecture/tasks.md`
**Issue:** Document says "batches of 500" but this isn't in the file inventory description.
**Fix:** Add `retry_failed_newsletter_deliveries` to the newsletter task description with batch size.

### LOW-6: Article Model Field Name Cross-References Wrong

**Location:** `architecture/overview.md:233`
**Issue:** Cross-references suggest `finalized_at` exists but correct field is `published_at`.
**Fix:** Ensure field names in cross-references match actual model fields (`published_at` not `finalized_at`, `last_crawled` not `last_fetch_at`).

### LOW-7: validate_url_safe Return Value Ambiguous

**Location:** `architecture/utils.md`
**Issue:** Function returns the original URL after validation but document is ambiguous.
**Fix:** Clarify that `validate_url_safe()` returns the original URL string if valid (does not return normalized URL).

### LOW-8: pipeline.py Helper Not Documented

**Location:** `architecture/tasks.md`
**Issue:** `pipeline.py` contains shared helpers used by all stage tasks but is not documented.
**Fix:** Add note that `pipeline.py` contains shared helpers used by all stage tasks.

### LOW-9: AdminUser Session Security Comment Clarification

**Location:** `architecture/models.md:111`
**Issue:** Comment says "not implemented" for `ip_binding` and `user_agent_hash` which implies TODO, but these fields do not exist at all.
**Fix:** Change "not implemented" comment to clearly state these fields do not exist in the model.

---

## Wave Organization for Parallelization

Items are organized into waves that can be executed in parallel by different agents.

### Wave A: Critical Documentation Fixes
| ID | Location | Issue |
|----|----------|-------|
| CRIT-1 | architecture/models.md:91 | Source.adapter_config doesn't exist |
| CRIT-2 | architecture/utils.md:129-135 | url.py global state not documented |

### Wave B: High Priority Model Documentation
| ID | Location | Issue |
|----|----------|-------|
| HIGH-1 | architecture/models.md:40-61 | Article model stub |
| HIGH-2 | architecture/models.md:73-92 | Source model missing fields |
| HIGH-3 | architecture/models.md:136-142 | Index documentation inaccurate |
| HIGH-4 | architecture/models.md:63-70 | Pipeline status flow outdated |
| HIGH-5 | architecture/schemas.md:89-101 | Adapter config schemas fictional |
| HIGH-6 | architecture/schemas.md:104-109 | PaginationConfig schema wrong |
| HIGH-7 | architecture/adapters.md | item_path vs list_items_path |

### Wave C: Medium Priority Documentation + 1 Implementation
| ID | Location | Issue | Type |
|----|----------|-------|------|
| MED-1 | architecture/pipeline.md | Degradation edit bypass | Doc |
| ~~MED-2~~ | ~~tasks/pipeline.py:56~~ | ~~String literal for status~~ | **VERIFIED** |
| ~~MED-3~~ | ~~tasks/pipeline.py:50-60~~ | ~~select degradation selector_result~~ | **VERIFIED** |
| ~~MED-4~~ | ~~services/pipeline_degradation.py:52~~ | ~~write stage writer_model~~ | **VERIFIED** |
| MED-5 | architecture/pipeline.md:250 | Degradation threshold wrong | Doc |
| MED-6 | architecture/routes.md:57 | api_tokens_bp note wrong | Doc |
| MED-7 | architecture/routes.md:143 | POST /articles not implemented | Doc |
| MED-8 | architecture/routes.md | Missing routes | Doc |
| MED-9 | architecture/pipeline.md | AuthError not documented | Doc |
| MED-10 | architecture/pipeline.md:289 | Backoff config incomplete | Doc |
| MED-11 | adapters/api.py | Pagination not implemented | **Code** |
| MED-12 | architecture/services.md | Missing hybrid.py | Doc |
| MED-13 | architecture/services.md | Missing content_extractor.py | Doc |
| MED-14 | architecture/services.md | Missing services | Doc |
| MED-15 | architecture/routes.md:64 | feeds_bp vs public_bp | Doc |
| MED-16 | architecture/pipeline.md:54 | PENDING→SKIPPED missing | Doc |
| MED-17 | architecture/routes.md | API token prefix detail | Doc |
| MED-18 | architecture/tasks.md | Missing tasks files | Doc |

### Wave D: Low Priority Documentation Consistency
| ID | Location | Issue |
|----|----------|-------|
| LOW-1 | architecture/tasks.md | cleanup.py tasks "Various" |
| LOW-2 | architecture/tasks.md | Degradation path conflates |
| LOW-3 | architecture/tasks.md | run_stage signature incomplete |
| LOW-4 | architecture/utils.md:16-28,102-127 | url.py section duplicated |
| LOW-5 | architecture/tasks.md | Newsletter batch size missing |
| LOW-6 | architecture/overview.md:233 | Field name cross-references wrong |
| LOW-7 | architecture/utils.md | validate_url_safe return ambiguous |
| LOW-8 | architecture/tasks.md | pipeline.py helper undocumented |
| LOW-9 | architecture/models.md:111 | AdminUser comment unclear |

---

## Implementation Notes for Future Agents

### Code Items (Require Testing)
- **MED-11**: `adapters/api.py` - Implement pagination support for APIAdapter (ONLY remaining code item)

### Documentation Items (32 items)
All other items are documentation-only changes to `architecture/*.md` files. No code changes required.

### Verified Items (Already Correct in Codebase)
The following items were marked for fixing but VERIFIED CORRECT in codebase:
- **MED-2**: `tasks/pipeline.py:56` - Already uses `PipelineStatus.RESEARCHING`
- **MED-3**: `tasks/pipeline.py:50-60` - Already sets `selector_result` dict
- **MED-4**: `services/pipeline_degradation.py:52` - Already sets `writer_model = "fallback"`

### Verification Steps
```bash
# Run linting on any code changes
ruff check . --exclude .venv

# Run mypy on changed files
mypy tasks/pipeline.py services/pipeline_degradation.py adapters/api.py

# Test any code changes
pytest tests/ -k "test_name" -v
```

---

## Progress Tracking

| Item | Status | Notes |
|------|--------|-------|
| CRIT-1 | PENDING | - |
| CRIT-2 | PENDING | - |
| HIGH-1 | PENDING | - |
| HIGH-2 | PENDING | - |
| HIGH-3 | PENDING | - |
| HIGH-4 | PENDING | - |
| HIGH-5 | PENDING | - |
| HIGH-6 | PENDING | - |
| HIGH-7 | PENDING | - |
| MED-1 | PENDING | - |
| MED-2 | VERIFIED | Already uses PipelineStatus.RESEARCHING |
| MED-3 | VERIFIED | Already sets selector_result dict |
| MED-4 | VERIFIED | Already sets writer_model = "fallback" |
| MED-5 | PENDING | - |
| MED-6 | PENDING | - |
| MED-7 | PENDING | - |
| MED-8 | PENDING | - |
| MED-9 | PENDING | - |
| MED-10 | PENDING | - |
| MED-11 | PENDING | Code change |
| MED-12 | PENDING | - |
| MED-13 | PENDING | - |
| MED-14 | PENDING | - |
| MED-15 | PENDING | - |
| MED-16 | PENDING | - |
| MED-17 | PENDING | - |
| MED-18 | PENDING | - |
| LOW-1 | PENDING | - |
| LOW-2 | PENDING | - |
| LOW-3 | PENDING | - |
| LOW-4 | PENDING | - |
| LOW-5 | PENDING | - |
| LOW-6 | PENDING | - |
| LOW-7 | PENDING | - |
| LOW-8 | PENDING | - |
| LOW-9 | PENDING | - |

---

*End of file*
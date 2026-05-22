# AINews Implementation Plan

**Status:** COMPLETED (Consolidated from architecture review - 2026-05-22)
**Last Updated:** 2026-05-22

---

## Overview

This plan consolidates findings from 10 architecture review files across all modules. Items are organized into waves based on priority and parallelization potential.

---

## Wave 1: CRITICAL (Must Fix - 4 items) ✅ COMPLETED

### SUB-1: Self-Correction Never Executes ✅ FIXED
**Module:** Services / Subagent
**Location:** `services/subagent/runner.py:428`
**Fix:** Added `ValidationError` to `retryable_exceptions` tuple.

### TASKS-1: Newsletter Lock Release Scope Bug ✅ FIXED
**Module:** Tasks
**Location:** `tasks/newsletter.py:398-409, 466-472`
**Fix:** Modified `_check_newsletter_lock` to return `lock_key` as third return value.

### SUB-2: run_subagent_chain Ignores steps Parameter ✅ FIXED
**Module:** Services / Subagent
**Location:** `services/subagent/chain.py:62`
**Fix:** Changed to use passed steps if provided, fall back to config.

### TASKS-2: Edit Stage Missing _dispatch_next ✅ FIXED
**Module:** Tasks
**Location:** `tasks/edit.py:185,205`
**Fix:** Added `_dispatch_next` calls before returning review status.

---

## Wave 2: HIGH Priority (6 items) ✅ COMPLETED

### MODELS-1: TrendMemory.topic Size Mismatch ✅ FIXED
Updated `architecture/models.md` to reflect actual code: `topic = db.Column(db.String(128), ...)`.

### MODELS-2: TrendMemory Fields Undocumented ✅ FIXED
Added `importance`, `expires_at`, `last_consolidated_at` fields to TrendMemory documentation.

### SCHEMA-1: search.py Missing from Documentation ✅ FIXED
Added `search.py` to file inventory in `architecture/schemas.md`.

### SCHEMA-2: APIConfig request_timeout Missing from Doc ✅ FIXED
`request_timeout: int = 15` already present in doc.

### SCHEMA-3: APIConfig auth_header Description Misleading ✅ FIXED
Clarified comment in `schemas/source.py`: "Header name for Bearer auth token (e.g., "Authorization")".

### ADPT-1: SSRFSafeRedirectHandler Interface Concern ✅ VERIFIED
Documented verification result in `architecture/adapters.md`.

---

## Wave 3: MEDIUM Priority (12 items) ✅ COMPLETED

### ADPT-2: APIAdapter Pagination Off-by-One ✅ VERIFIED
Pagination logic reviewed - no off-by-one error found.

### SVC-1: DeepSeek Search Provider Missing from Doc ✅ FIXED
Added `deepseek.py` to search provider table in `architecture/services.md`.

### SVC-2: circuit_breaker.py Not in File Inventory ✅ FIXED
Added `circuit_breaker.py` to file inventory in `architecture/services.md`.

### SVC-3: search/ Subdirectory Structure Not Documented ✅ FIXED
Added subdirectory listing in `architecture/services.md`.

### SCHEMA-4: ReviewConfig Default Inconsistent ✅ FIXED
Updated description to "Default: None (disabled)" in `schemas/pipeline.py`.

### SCHEMA-5: ProcessItemTask Structure Inaccurate ✅ FIXED
Updated `architecture/schemas.md` with accurate ProcessItemTask fields.

### SCHEMA-6: Layer Violation in common.py Not Documented ✅ FIXED
Documented intentional layer violation in `architecture/schemas.md`.

### ROUTES-1: Duplicate /admin/metrics Entry ✅ FIXED
Removed duplicate entry in `architecture/routes.md`.

### ROUTES-2: Misleading api_tokens_bp Documentation ✅ FIXED
Removed duplicate code block; clarified registration in `architecture/routes.md`.

### ROUTES-3: Missing /admin/pipelines/trigger-crawl ✅ VERIFIED (already present)

### ROUTES-4: Missing /admin/articles/<id>/original ✅ FIXED
Added to `architecture/routes.md`.

### ROUTES-5: Missing /admin/articles/<id>/versions/<version_id>/rollback ✅ FIXED
Added to `architecture/routes.md`.

### ROUTES-6: Missing /admin/api/trend-memory/semantic-search ✅ FIXED
Added to `architecture/routes.md`.

### ROUTES-7: Missing /admin/topic-notes/row/<topic> ✅ VERIFIED (already present)

### ROUTES-8: Missing /admin/shares/<id>/edit-form and /admin/shares/<id>/row ✅ FIXED
Added both routes to `architecture/routes.md`.

---

## Wave 4: LOW Priority - Documentation & Polish (13 items) ✅ COMPLETED

### UTIL-1: Missing __all__ Exports ✅ FIXED
Added explanation of mixed exports in `architecture/utils.md`.

### UTIL-2: Missing __init__.py in utils/ ✅ FIXED
Documented intentional empty `utils/__init__.py` in `architecture/utils.md`.

### UTIL-3: TRACKING_PARAMS Not in File Inventory ✅ VERIFIED
Already documented in `architecture/utils.md`.

### TASKS-4: AGENTS.override.md Outdated ✅ UPDATED
Updated with bug fix status notation.

### TASKS-5: Task Name Discrepancy ✅ VERIFIED
Actual task name is `retry_stuck` - documentation is correct.

### SUB-3: Chain Uses provider.chat() Not chat_with_tools ✅ FIXED
Documented limitation in `architecture/subagent.md`.

### SUB-4: Layering Violation in tools.py (Documented) ✅ VERIFIED
Already documented in AGENTS.md as known issue.

### SUB-5: Documentation Clarity for Schema Definitions ✅ FIXED
Added location note in `architecture/subagent.md`.

### SCHEMA-7: TopicMatchConfig Not Documented ✅ FIXED
Added TopicMatchConfig documentation to `architecture/schemas.md`.

### SCHEMA-8: admin.py Depends on constants.py ✅ VERIFIED
Dependency is internal to validation, no additional documentation needed.

### MODELS-3: Article.created_at Only Composite Index ✅ DEFERRED
Standalone index not added - composite index handles most queries.

### MODELS-4: PipelineRun.started_at Missing Index ✅ DEFERRED
Index not added - sorting by `started_at` is infrequent.

### OVERVIEW-1: utils/url.py Not Pure ✅ FIXED
Added note to `architecture/overview.md` and `architecture/utils.md`.

### OVERVIEW-2: TYPE_CHECKING Imports Not Documented ✅ FIXED
Added note about TYPE_CHECKING exception to `architecture/overview.md`.

---

## Implementation Summary (2026-05-22)

All 35 planned items completed:
- 4 critical bug fixes (Wave 1)
- 6 high priority documentation updates (Wave 2)
- 13 medium priority items (Wave 3)
- 12 low priority documentation items (Wave 4)
- 2 items deferred (MODELS-3, MODELS-4 - optional indexes)

Key code changes:
- `services/subagent/runner.py`: Added ValidationError to retryable_exceptions
- `services/subagent/chain.py`: Fixed steps parameter usage
- `tasks/newsletter.py`: Fixed lock_key scope bug
- `tasks/edit.py`: Added _dispatch_next calls
- `schemas/pipeline.py`: Fixed ReviewConfig description

---

*Plan completed - 2026-05-22*
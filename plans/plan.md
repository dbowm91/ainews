# AINews Consolidated Implementation Plan

**Status:** IN PROGRESS
**Last Updated:** 2026-05-09
**Goal:** Consolidate all pending action items from architecture reviews into a single actionable plan.

---

## Executive Summary

This plan consolidates action items from 9 architecture review documents. Items are organized by priority and phase to enable parallel implementation.

### Priority Summary

| Priority | Count | Items |
|----------|-------|-------|
| HIGH | 18 | Critical bugs, documentation fixes, missing functionality |
| MEDIUM | 21 | Documentation alignment, improvements |
| LOW | 17 | Cleanup, minor documentation fixes |

### Phase Overview

| Phase | Focus | Parallelizable |
|-------|-------|----------------|
| Phase 1 | Critical Bug Fixes | Yes - multiple independent bugs |
| Phase 2 | Documentation Alignment | Partial - some sequential dependencies |
| Phase 3 | Feature Completions | Partial - some modules independent |
| Phase 4 | Cleanup & Polish | Yes - independent items |

---

## Phase 1: Critical Bug Fixes

### BUG-1.1: Newsletter Lock NameError

**Location:** `tasks/newsletter.py:430`

**Issue:** `NameError` - `idempotency_key` reference error in newsletter generation lock.

**Fix Required:**
1. Locate the lock acquisition block around line 420-430
2. Ensure `idempotency_key` is defined before use in the lock key construction
3. Verify the Lua script for newsletter lock uses correct variable names

**Verification:** Check that `idempotency_key` is defined locally in `_generate_daily_newsletters_core()` before the lock is acquired.

---

### BUG-1.2: Redis Client Lock Key Not Accessible in Finally Block

**Location:** `tasks/newsletter.py` - newsletter generation

**Issue:** `redis_client` or `lock_key` not accessible in `finally` block scope, causing lock leak on early returns.

**Fix Required:**
1. Ensure `redis_client` and `lock_key` are defined in a scope accessible by the finally block
2. Verify the finally block properly releases the lock
3. Add logging for lock acquisition and release for debugging

---

### BUG-1.3: Missing Stage Status in VALID_TRANSITIONS

**Location:** `services/pipeline_utils.py` or similar

**Issue:** `selecting` and `selected` status values are not included in `VALID_TRANSITIONS` dict.

**Fix Required:**
1. Find the `VALID_TRANSITIONS` definition
2. Add entries for `selecting` and `selected` status transitions
3. Verify all valid stage transitions are covered

**Expected transitions for selecting/selected:**
- `pending` → `selecting` (article enters selection)
- `selecting` → `selected` (article selected for research)
- `selected` → `researching` (research begins)

---

### BUG-1.4: _handle_disabled Dispatches to Wrong Status

**Location:** `tasks/pipeline.py` or `services/pipeline_utils.py`

**Issue:** When `edit` stage is disabled, `_handle_disabled` dispatches to wrong status.

**Fix Required:**
1. Find `_handle_disabled` function
2. Check the dispatch logic for disabled stages
3. Ensure it dispatches to correct fallback status (should be `review` or `written` not `editing`)

---

### BUG-1.5: Limiter Model Mismatch After Fallback

**Location:** `tasks/pipeline.py:436`

**Issue:** The `model` returned by `_run_stage_core` comes from `_get_provider_for_stage` which only returns the PRIMARY provider's model, not the actual model used if fallback occurred.

**Fix Required:**
1. After `_try_stage_work` returns with `provider_id`, use that actual provider_id to look up the correct model
2. Or pass the actual model through from `_try_stage_work`

**Note:** This is related to but separate from BUG-5.1.1 which was fixed (limiter slot leak on early return). This bug is about the return value being wrong, not about slot release.

---

### BUG-1.6: provider_id May Be None in Exception Handler

**Location:** `tasks/pipeline.py:269`

**Issue:** `provider_id` may be `None` when recorded in exception handler.

**Fix Required:**
1. Check exception handler around line 269
2. Ensure provider_id is captured before potential None assignment
3. Add fallback value or skip recording if provider_id is None

---

### BUG-1.7: SSRFSafeRedirectHandler Reset Bug

**Location:** `adapters/web.py` or `adapters/session.py`

**Issue:** `_redirect_count` reset could allow redirect bypass - SSRF protection bypass via redirect counting reset.

**Fix Required:**
1. Find SSRFSafeRedirectHandler class
2. Check `_redirect_count` initialization and reset logic
3. Ensure redirect count is properly bounded and cannot be reset mid-redirect-chain
4. Add test for redirect chain limit

---

### BUG-1.8: WebAdapter Date Parsing Silently Returns None

**Location:** `adapters/web.py`

**Issue:** Date parsing failures silently return `None` with no logging.

**Fix Required:**
1. Find date parsing logic in WebAdapter
2. Add logging for parsing failures (warn level)
3. Consider adding a metric for parsing failures

---

### BUG-1.9: WebAdapter Trafilatura ImportError Caught Too Broadly

**Location:** `adapters/web.py`

**Issue:** `ImportError` is caught too broadly, potentially masking other import issues.

**Fix Required:**
1. Find the try/except block for trafilatura import
2. Split into specific exception handling:
   - `ImportError` for missing module (expected)
   - `Exception` for unexpected errors (re-raise)

---

### BUG-1.10: api_tokens_bp Blueprint Never Registered

**Location:** `app.py`

**Issue:** `api_tokens_bp` blueprint is defined but never registered in `app.py`, causing all token auth routes to return 404.

**Fix Required:**
1. Find `api_tokens_bp` definition
2. Add registration in `app.py`:
   ```python
   app.register_blueprint(api_tokens_bp, url_prefix='/api/v1/auth')
   ```
3. Verify token auth endpoints work

---

### BUG-1.11: API Token Auth Uses Wrong Auth Mechanism

**Location:** `routes/api_tokens.py` or similar

**Issue:** API token auth redirects to HTML login instead of returning JSON 401.

**Fix Required:**
1. Find the auth decorator or auth check logic for token endpoints
2. Change redirect behavior to return `jsonify({"error": "Unauthorized"})` with 401 status
3. Test with `Authorization: Bearer <token>` header

---

### BUG-1.12: Services/Newsletter Pipeline Limiter Slot Leak on Fallback - VERIFIED NOT A BUG

**Location:** `services/newsletter_pipeline.py:122-124`

**Issue:** Originally suspected slot leak on fallback - but code review shows correct pattern.

**Verified Behavior:**
```python
if limiter.acquire(provider, model, ...):
    try:
        result = llm_call(provider, model, max_tokens)
        return result, True
    finally:
        limiter.release(provider, model, ...)
else:
    # fallback_stages.append(role) - correctly does NOT release
    return None, False
```

**Analysis:** When `acquire()` returns `False`, the slot was never acquired (limiter rejected it). Release is only called in `finally` for successfully acquired slots. This is correct.

**No Fix Required.**

---

### BUG-1.13: Duplicate Import load_providers_config

**Location:** `services/llm/__init__.py:11-12`

**Issue:** `load_providers_config` is imported twice.

**Fix Required:**
1. Remove duplicate import
2. Ensure only one import statement for `load_providers_config`

---

## Phase 2: High Priority Documentation & Implementation Fixes

### TASK-2.1: API Path Prefix Documentation vs Reality - CONFIRMED BUG

**Issue:** Documentation and AGENTS.md incorrectly claim admin API endpoints are at root level (`/articles`) but actual is `/api/v1/articles`.

**Verified Actual State:**
- `admin_api_bp` registered with `url_prefix="/api/v1"`
- Admin API routes are at: `/api/v1/articles`, `/api/v1/sources`, `/api/v1/pipeline`
- `admin_bp` (HTML pages) is at `/admin`

**Fix Required:**
1. Update `architecture/routes.md` to show `/api/v1/` prefix for admin API
2. Update AGENTS.md line 45 to show correct paths

**Note:** This is not just documentation drift - AGENTS.md (used by agents) has the wrong info.

---

### TASK-2.2: Document All Actual API Endpoints

**Missing endpoints identified:**
- `/costs` - cost tracking endpoint
- `/sources/health` - source health check
- `/metrics/prometheus` - Prometheus metrics endpoint
- `/articles/ids` - batch article ID lookup
- `/articles/counts-by-status` - article count by status
- `/search/analytics` - search analytics
- `/webhooks/events/<id>/resend` - webhook resend

**Fix Required:**
1. Audit all route files to find actual endpoints
2. Document in `architecture/routes.md`
3. Add any missing to AGENTS.md

---

### TASK-2.3: MemoryConfig Documentation 0% Match

**Location:** `schemas/config.py` or `schemas/memory.py`

**Issue:** `MemoryConfig` in documentation completely different from actual code.

**Fix Required:**
1. Read actual `MemoryConfig` schema in code
2. Update `architecture/schemas.md` to match
3. Verify all fields match between docs and code

---

### TASK-2.4: NewsletterConfig Documentation Gaps

**Issue:** Documentation missing `enable_topic_newsletters`, `batch_size`; possibly wrong `max_articles` default.

**Verified Actual Schema (schemas/pipeline.py:51):**
```python
class NewsletterConfig(BaseModel):
    max_articles: int = Field(default=10, ge=1, le=50)
    send_time: str = "08:00"
    timezone: str = "America/New_York"
    site_url: str = "https://ainews.dev"
    prep_minutes: int = Field(default=15, ge=5, le=60)
```

**Note:** No `enable_topic_newsletters` or `batch_size` fields exist in actual schema.

**Fix Required:**
1. Update documentation to match actual schema (no enable_topic_newsletters, no batch_size)
2. Default max_articles is 10 (not 20)

---

### TASK-2.5: SourceConfig adapter_config Field Doesn't Exist

**Issue:** Docs show `adapter_config: RSSConfig | APIConfig | WebConfig` but actual is `config: dict[str, Any]`.

**Fix Required:**
1. Update documentation to show correct `config: dict[str, Any]` type
2. Document what keys are expected in the config dict

---

### TASK-2.6: PipelineRootConfig Missing version Field

**Issue:** `version` field documented but not present in code.

**Fix Required:**
1. Check if `version` field should be added to `PipelineRootConfig`
2. If not needed, remove from documentation
3. If needed, add to schema and config files

---

### TASK-2.7: SelectionResult impact_summary Field - CORRECTED

**Issue:** Originally said `impact_summary` field documented but not implemented.

**Verified Actual Schema (schemas/llm_responses.py:16):**
```python
class SelectionResult(BaseModel):
    selected: bool
    score: int = Field(ge=1, le=10)
    reason: str
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    key_topics: list[str] = Field(default_factory=list)
    impact_summary: Optional[str] = Field(default=None)  # EXISTS
```

**Status:** `impact_summary` field EXISTS. No code fix needed. Update documentation if it says otherwise.

**Fix Required:** Verify documentation shows `impact_summary: Optional[str]`

---

### TASK-2.8: SelectionResult confidence Type

**Issue:** Documentation shows `str` with pattern, actual should be `Literal["low", "medium", "high"]`.

**Fix Required:**
1. Update schema to use `Literal["low", "medium", "high"]`
2. Update documentation

---

### TASK-2.9: RelatedArticle/ExternalSource Field Names Different

**Issue:** Documentation field names completely different from actual schema.

**Fix Required:**
1. Read actual `RelatedArticle` and `ExternalSource` schemas
2. Update documentation to match

---

### TASK-2.10: DirectQuote Field Names Misaligned

**Issue:** `quote` vs `text`, `attribution` vs `source`.

**Fix Required:**
1. Verify actual field names in `DirectQuote` schema
2. Update documentation or code to align

---

### TASK-2.11: NewsletterArticle Field Names Misaligned

**Issue:** `headline` vs `title`, `tags` vs `key_points`.

**Fix Required:**
1. Verify actual field names in `NewsletterArticle` schema
2. Update documentation or code to align

---

### TASK-2.12: Consolidate URL Validation

**Issue:** `services/url.py` and `utils/url.py` have duplicate implementations causing confusion.

**Fix Required:**
1. Determine which is canonical (likely `utils/url.py` based on layering rules)
2. Move all SSRF protection to `utils/url.py`
3. Have `services/url.py` re-export from utils for backward compatibility
4. Update all imports to use `utils/url.py` directly
5. Clean up `__all__` exports in `utils/url.py` to not expose internal items (`_BLOCKED_NETWORKS`, `_TTLCache`, `_dns_executor`)

---

### TASK-2.13: Global Mutable DNS Cache Contradicts Pure Functions

**Location:** `utils/url.py`

**Issue:** `utils/url.py` claims pure functions but has global mutable DNS cache (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`).

**Fix Required:**
1. Document that this module has side effects (global DNS cache)
2. OR refactor to use a passed-in cache
3. Update AGENTS.md note if this is intentional

---

### TASK-2.14: adapter_config Field on Source Model

**Issue:** Documented but never implemented.

**Options:**
1. Implement `adapter_config` field on `Source` model
2. OR confirm it should be removed from documentation

**Decision Required:** Implement or remove from docs.

---

### TASK-2.15: GIN Index on TrendMemory.embedding

**Issue:** Documentation claims GIN index for vector search but no GIN index exists.

**Options:**
1. Implement GIN index on `TrendMemory.embedding` column
2. OR update docs to remove claim about vector search indexing

**Decision Required:** Implement index or remove claim.

---

### TASK-2.16: IP/User-Agent Binding for AdminUser Session

**Issue:** Documentation says "not implemented" but should either implement or remove note.

**Options:**
1. Implement IP/user-agent binding for AdminUser session security
2. OR remove "not implemented" note and document actual behavior

**Decision Required:** Implement or clean up docs.

---

### TASK-2.17: Update Pipeline Status Values in Documentation

**Issue:** Documentation shows different status values than actual code.

**Actual statuses:** `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`

**Fix Required:**
1. Update all documentation to use actual status values
2. Verify `selecting` and `selected` are properly documented

---

### TASK-2.18: Document API Adapter Pagination

**Issue:** Documentation shows API adapter has cursor/offset/page pagination but actual doesn't.

**Fix Required:**
1. Update architecture docs to reflect API adapter lacks pagination
2. OR add pagination support to API adapter

**Decision Required:** Add pagination or update docs.

---

### TASK-2.19: WebAdapter Documentation Fix

**Issue:** Uses `listing_url` (singular), not `start_urls`.

**Fix Required:**
1. Update documentation to use correct field name `listing_url`
2. Verify actual field name used in code

---

### TASK-2.20: BaseLLMProvider Interface Documentation

**Issue:** Architecture docs don't match actual `BaseLLMProvider` interface.

**Fix Required:**
1. Read actual `BaseLLMProvider` interface in `services/llm/base.py` or `services/llm/provider_base.py`
2. Update documentation to match
3. Consider renaming file to `provider_base.py` to match docs

---

### TASK-2.21: Limiter Provider Tracking Bug

**Issue:** Uses `stage_config.provider` instead of actual `provider_id` for tracking.

**Location:** Likely in limiter release or metrics tracking

**Fix Required:**
1. Find where `stage_config.provider` is used for limiter tracking
2. Replace with actual `provider_id` used during the call

---

### TASK-2.22: Subagent Tool Mapping Table Outdated

**Issue:** Architecture doc tool mapping table doesn't match actual tool names.

**Fix Required:**
1. Read actual tool definitions in `services/subagent/tools.py`
2. Update architecture doc to use actual canonical tool names

---

### TASK-2.23: Chain Configuration Source Documentation

**Issue:** Documentation shows inline YAML but actual comes from `pipeline.yaml` via `SubagentChainConfig`.

**Fix Required:**
1. Update `architecture/subagent.md` to document that chain config comes from `pipeline.yaml`
2. Document `SubagentChainConfig` schema

---

## Phase 3: Medium Priority Items

### TASK-3.1: Document Stage vs Status Naming Convention

**Issue:** "select/research/write/edit" stages vs "pending/researching/writing/editing" status constants cause confusion.

**Fix Required:**
1. Add glossary section to architecture docs clarifying:
   - Stages: select → research → write → edit (what happens)
   - Statuses: pending, selecting, selected, researching, writing, written, editing, review (state machine)
2. Update all documentation to be consistent

---

### TASK-3.2: Document Actual Stage Flow

**Issue:** Architecture doc shows `pending → select` but code uses `pending → researching` directly.

**Fix Required:**
1. Verify actual flow in `tasks/pipeline.py`
2. Update documentation to match actual flow
3. Document when selection is skipped/bypassed

---

### TASK-3.3: Use Chord with Callback for Newsletter

**Issue:** `group()` used for parallel topic newsletter generation but `chord()` would provide proper synchronization.

**Fix Required:**
1. Find newsletter generation code using `group()`
2. Replace with `chord()` and proper callback
3. Document the change

---

### TASK-3.4: Document Missing Tasks

**Issue:** `cleanup-inactive-subscribers` exists in beat schedule but not documented.

**Fix Required:**
1. Add to Celery Beat schedule documentation
2. Verify task exists and functions correctly

---

### TASK-3.5: Document aggregate_crawl_results

**Issue:** Chord callback at `crawl.py:215` needs documentation.

**Fix Required:**
1. Find `aggregate_crawl_results` function
2. Document its role in crawl flow
3. Add to architecture docs

---

### TASK-3.6: Document retry_failed_newsletter_deliveries

**Issue:** Task exists in beat schedule but not in architecture.

**Fix Required:**
1. Verify task exists
2. Add to documentation

---

### TASK-3.7: Document Blueprint Structure

**Issue:** Need section explaining `admin_bp` at `/admin` for HTML vs `admin_api_bp` at `/api/v1` for JSON.

**Fix Required:**
1. Add architecture section documenting blueprint structure
2. Clarify URL prefix separation between HTML and API routes

---

### TASK-3.8: Document @require_auth Behavior

**Issue:** Need to note it supports both session-based and token-based auth.

**Fix Required:**
1. Find `@require_auth` decorator implementation
2. Document both auth modes
3. Add examples for each mode

---

### TASK-3.9: Subagent Tool Function Naming Convention

**Issue:** Need to document `_context_tool_*` or `_search_*` prefix convention.

**Fix Required:**
1. Find actual naming convention used in `services/subagent/tools.py`
2. Document in `architecture/subagent.md`

---

### TASK-3.10: Add conditions.py to Architecture Overview

**Issue:** AST-based condition evaluation module not documented.

**Fix Required:**
1. Find `services/subagent/conditions.py`
2. Document its purpose and how it works
3. Add to architecture overview

---

### TASK-3.11: Document utils.py Contents

**Issue:** `_retry_with_backoff`, `_is_task_revoked`, `_format_subagent_prompt` not documented.

**Fix Required:**
1. Find `services/subagent/utils.py`
2. Document each function's purpose
3. Add to architecture docs

---

### TASK-3.12: Add ErrorHandlingMiddleware to run_subagent()

**Issue:** `run_subagent()` doesn't apply middleware but `run_subagent_with_tools()` does.

**Fix Required:**
1. Verify middleware consistency
2. Add `ErrorHandlingMiddleware` to `run_subagent()` or document why it's not needed

---

### TASK-3.13: Subagent Public API Documentation

**Issue:** Need to clarify which `__init__.py` exports are public API vs internal.

**Fix Required:**
1. Audit `services/subagent/__init__.py`
2. Mark internal functions with `_` prefix or move to `_internals.py`
3. Document public API surface

---

### TASK-3.14: ToolDefinition Missing cached Field

**Issue:** Architecture documents `cached: bool` on `ToolDefinition` but it's not in schema.

**Fix Required:**
1. Check if `cached` field should be added to `ToolDefinition`
2. Add to schema or remove from documentation

---

### TASK-3.15: Document Two-Tier Retry System

**Issue:** Celery task-level vs stage failure level retry system not documented.

**Fix Required:**
1. Find both retry mechanisms in code
2. Document how they interact
3. Add to architecture docs

---

### TASK-3.16: Clarify Degradation Behavior for Disabled Stages

**Issue:** What happens when a stage is disabled needs documentation.

**Fix Required:**
1. Find `_handle_disabled` or similar logic
2. Document behavior for each stage when disabled
3. Add to architecture docs

---

### TASK-3.17: Document _should_route_to_review Logic

**Issue:** `auto_publish_threshold` config and routing logic not documented.

**Fix Required:**
1. Find `_should_route_to_review` function
2. Document `auto_publish_threshold` config
3. Add flow diagram to architecture docs

---

### TASK-3.18: Add Circuit Breaker Architecture Diagram

**Issue:** Circuit breaker documented but no diagram.

**Fix Required:**
1. Create ASCII/text diagram showing:
   - Failure count threshold (5)
   - Time window (2 min)
   - Half-open state timeout (60s)
   - State transitions

---

### TASK-3.19: Document meta vs metadata on PipelineLog

**Issue:** Need to explain why `meta` is used instead of `metadata`.

**Fix Required:**
1. Add note explaining SQLAlchemy reserved name restriction
2. Document what data goes into `meta` field

---

### TASK-3.20: Clarify Newsletter Lock Mechanism

**Issue:** Lua script for newsletter lock not documented.

**Fix Required:**
1. Find Lua script for newsletter idempotency lock
2. Document the locking mechanism
3. Add to architecture docs

---

### TASK-3.21: Document 3-Stage Newsletter Pipeline Flow

**Issue:** 3-stage newsletter pipeline flow needs more precise documentation.

**Fix Required:**
1. Identify the 3 stages (likely: collect → generate → deliver)
2. Document each stage's inputs/outputs
3. Add flow diagram

---

## Phase 4: Cleanup & Low Priority Items

### TASK-4.1: Add Dedicated Unit Tests for Utils

**Issue:** Tests go through `services/url.py`; need direct tests for `utils/` functions.

**Fix Required:**
1. Create `tests/utils/` directory
2. Add tests for each utils module
3. Test edge cases (empty strings, None, etc.)

---

### TASK-4.2: Clean Up __all__ Exports in utils/url.py

**Issue:** Internal items exposed in public API (`_BLOCKED_NETWORKS`, `_TTLCache`, `_dns_executor`).

**Fix Required:**
1. Review `__all__` in `utils/url.py`
2. Remove internal items from public exports
3. Document public API surface

---

### TASK-4.3: Document Return Type Mismatch in Adapters

**Issue:** `list[Any]` vs `list[dict]` return type mismatch.

**Fix Required:**
1. Check actual return type of adapter fetch methods
2. Standardize to `list[dict]` or appropriate type
3. Update type hints

---

### TASK-4.4: Update YAML Config Examples

**Issue:** Config examples use wrong field names (`start_urls` vs `feed_url`, `list_url`, `listing_url`).

**Fix Required:**
1. Find YAML config examples in documentation
2. Update to use actual field names

---

### TASK-4.5: Clarify Rate Limiting Responsibility

**Issue:** Need to document LLM services handle Retry-After, not adapters.

**Fix Required:**
1. Document in architecture that adapters don't handle rate limiting
2. LLM providers handle Retry-After headers
3. Add note about backoff behavior

---

### TASK-4.6: Clarify Source Health Tracking

**Issue:** Documentation says adapters track source health but actual is `services/crawling.py`.

**Fix Required:**
1. Update documentation to show `services/crawling.py` handles health tracking
2. Document health check frequency and metrics

---

### TASK-4.7: Add embed() Method to BaseLLMProvider

**Issue:** Documented but not present in interface.

**Options:**
1. Add `embed()` method stub to `BaseLLMProvider`
2. OR remove from documentation

**Decision Required**

---

### TASK-4.8: Dead Code Removal

**Issue:** `_finalize_subagent_result()` is never called.

**Fix Required:**
1. Verify it's truly dead code
2. Remove if not used

---

### TASK-4.9: Layer Violation Cleanup - tasks/pipeline.py - VERIFIED INTENTIONAL

**Issue:** `tasks/pipeline.py` imports from `services.pipeline_degradation` and `services.pipeline_failure`.

**Analysis:** Tasks layer IS allowed to import from services layer. This is not a layer violation. The architecture layers are:
- Adapters → cannot import Services
- Services → cannot import Adapters  
- Tasks → can import Services (tasks are orchestrators that use business logic)

**No Fix Required.** Document this in AGENTS.md if not already clear.

---

### TASK-4.10: Layer Violation Cleanup - tasks/extract.py

**Issue:** `tasks/extract.py` imports from `services.article` for deduplication logic.

**Fix Required:**
1. Verify if this is acceptable or needs refactor
2. Move deduplication logic to avoid services import from tasks

---

### TASK-4.11: Services/Newsletter Pipeline Redis Access

**Issue:** `services/newsletter_pipeline.py` directly accesses Redis instead of using limiter abstraction.

**Fix Required:**
1. Check if direct Redis access is necessary
2. Consider using limiter abstraction or adding Redis client wrapper

---

### TASK-4.12: Schema Imports Should Use TYPE_CHECKING

**Issue:** Schema imports at top-level instead of TYPE_CHECKING pattern.

**Fix Required:**
1. Find schema files with runtime imports from services
2. Convert to TYPE_CHECKING pattern

---

## Wave Organization for Parallelization

### Wave A: Bug Fixes (Independent)
Can be done in parallel by multiple agents:

| Bug | Location | Dependencies |
|-----|----------|--------------|
| BUG-1.1 | tasks/newsletter.py:430 | None |
| BUG-1.2 | tasks/newsletter.py | None |
| BUG-1.3 | pipeline_utils.py | None |
| BUG-1.4 | tasks/pipeline.py | None |
| BUG-1.5 | tasks/pipeline.py:436 | None |
| BUG-1.6 | tasks/pipeline.py:269 | None |
| BUG-1.7 | adapters/web.py | None |
| BUG-1.8 | adapters/web.py | None |
| BUG-1.9 | adapters/web.py | None |
| BUG-1.10 | app.py | None |
| BUG-1.11 | routes/api_tokens.py | None |
| BUG-1.12 | services/newsletter_pipeline.py:122-124 | None |
| BUG-1.13 | services/llm/__init__.py:11-12 | None |

### Wave B: Documentation Fixes (Some Sequential)
- 2.1-2.11: Documentation alignment (can parallelize by doc file)
- 2.12-2.23: Implementation/documentation fixes

### Wave C: Feature Completions (Independent)
- 2.14, 2.15, 2.16: Decision items (implement or remove)
- 2.18, 2.19: Adapter updates

### Wave D: Cleanup (Independent)
- 4.1-4.12: Can parallelize

---

## Implementation Notes for Future Agents

### Starting Point
When picking up work from this plan:

1. **Read the relevant bug/task section fully**
2. **Check the current state** in the codebase before implementing
3. **Verify fix with tests** if applicable
4. **Update this plan** with completion status and any new findings

### Test Commands
```bash
# Run tests for specific module
pytest tests/ -k "test_name" -v

# Run linting
ruff check . --exclude .venv

# Run mypy on changed files
mypy module_path
```

### Key Files for Reference
- `tasks/pipeline.py` - Pipeline orchestration, stage execution
- `tasks/newsletter.py` - Newsletter generation, locking
- `services/pipeline_utils.py` - Stage task mappings, VALID_TRANSITIONS
- `adapters/` - RSS, API, Web adapter implementations
- `services/subagent/` - Subagent system, tool registry
- `schemas/` - Pydantic models for validation
- `architecture/` - Architecture documentation

---

## Progress Tracking

| Item | Status | Completed Date | Notes |
|------|--------|----------------|-------|
| BUG-1.1 | PENDING | | |
| BUG-1.2 | PENDING | | |
| BUG-1.3 | PENDING | | |
| BUG-1.4 | PENDING | | |
| BUG-1.5 | PENDING | | |
| BUG-1.6 | PENDING | | |
| BUG-1.7 | PENDING | | |
| BUG-1.8 | PENDING | | |
| BUG-1.9 | PENDING | | |
| BUG-1.10 | PENDING | | |
| BUG-1.11 | PENDING | | |
| BUG-1.12 | PENDING | | |
| BUG-1.13 | PENDING | | |
| TASK-2.1 | PENDING | | |
| ... | ... | | |

---

*End of file*
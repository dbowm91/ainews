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
| HIGH | 10 | Critical bugs that affect functionality |
| MEDIUM | 18 | Documentation fixes, improvements |
| LOW | 14 | Cleanup, minor documentation fixes |

### Verified Non-Bugs (Plan Corrections)
The following items in the original plan were INCORRECTLY marked as bugs:
- **BUG-1.2**: `redis_client` IS accessible in finally block - NOT A BUG
- **BUG-1.12**: Slot leak pattern is correct - NOT A BUG (already noted in plan)
- **TASK-2.1**: API path prefix is correctly documented in AGENTS.md - NO FIX NEEDED
- **TASK-2.7**: `impact_summary` field EXISTS in SelectionResult - NO FIX NEEDED

---

## Phase 1: Critical Bug Fixes

### BUG-1.1: Newsletter Lock NameError **[HIGH]**

**Location:** `tasks/newsletter.py:430`

**Issue:** `NameError` - `idempotency_key` reference error in newsletter generation lock.

**Verification:** `idempotency_key` is defined at line 381 inside `_check_newsletter_lock()` function. Line 430 is inside `_generate_daily_newsletters_core()` function. Since `idempotency_key` is a local variable in `_check_newsletter_lock`, it is OUT OF SCOPE at line 430. This will cause a `NameError`.

**Fix Required:**
1. Move `idempotency_key` definition to `_generate_daily_newsletters_core()` scope, OR
2. Pass `idempotency_key` as a return value from `_check_newsletter_lock()`, OR
3. Define `idempotency_key` at line 417 alongside `redis_client`

**Implementation Detail:**
```python
# Current (broken) - line 417-430 in _generate_daily_newsletters_core:
redis_client = get_redis()
# ... later at line 430:
redis_client.setex(idempotency_key, 86400 * 2, "1")  # NameError! idempotency_key undefined

# Fix: Define idempotency_key locally:
idempotency_key = f"idempotency:newsletter:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
redis_client.setex(idempotency_key, 86400 * 2, "1")
```

**Verification:** Check that `idempotency_key` is defined locally in `_generate_daily_newsletters_core()` before the lock is acquired.

---

### BUG-1.3: Missing Stage Status in VALID_TRANSITIONS **[HIGH]**

**Location:** `constants.py:49-58` (VALID_TRANSITIONS dict)

**Issue:** `selecting` and `selected` status values are not included in `VALID_TRANSITIONS` dict.

**Verification:**
- `VALID_TRANSITIONS` keys: `pending`, `researching`, `writing`, `editing`, `review`, `done`, `skipped`, `failed`
- Missing: `selected` (used in STAGE_STATUS_MAP line 74), `selecting`
- This creates inconsistency where `selected` can be set as a status but transitioning TO it would not be considered valid

**Fix Required:**
1. Add `selecting` and `selected` to `VALID_TRANSITIONS`:
```python
PipelineStatus.SELECTING: frozenset([PipelineStatus.SELECTED, PipelineStatus.FAILED]),
PipelineStatus.SELECTED: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.FAILED]),
```

**Expected transitions:**
- `pending` → `selecting` (article enters selection)
- `selecting` → `selected` (article selected for research)
- `selected` → `researching` (research begins)

---

### BUG-1.5: Limiter Model Mismatch After Fallback **[HIGH]**

**Location:** `tasks/pipeline.py:369, 374, 386, 436`

**Issue:** The `model` returned by `_run_stage_core` comes from `_get_provider_for_stage` which only returns the PRIMARY provider's model, not the actual model used if fallback occurred in `_try_stage_work`.

**Verification:** Confirmed - `provider_id` from `_try_stage_work` (line 374) is the ACTUAL provider used, but `model` from `_get_provider_for_stage` (line 369) is only the PRIMARY provider's model. Line 386 returns `model` which may be wrong. Line 436 releases with wrong model.

**Fix Required:**
1. Option A: After `_try_stage_work` returns with `provider_id`, use that actual provider_id to look up the correct model
2. Option B: Pass the actual model through from `_try_stage_work`
3. Use `provider_id` (actual) not `rc.provider` (configured) when releasing limiter

**Code location for fix (line 436):**
```python
# Current (may be wrong):
limiter.release(rc.provider, model if model is not None else None, rc.timeout_seconds)

# Fix - use provider_id which is actual provider:
limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```

**Note:** This is separate from slot leak on early return (BUG-5.1.1 which was fixed). This bug is about the return value being wrong, not about slot release.

---

### BUG-1.6: provider_id May Be None in Exception Handler **[MEDIUM]**

**Location:** `tasks/pipeline.py:264-270`

**Issue:** `_handle_stage_exception` receives `provider_id` which could be `None` if `_run_stage_core` failed before any provider was tried.

**Verification:** Line 423 initializes `provider_id = None`. The exception handler at line 269-270 checks `if provider_id:` before recording, so this is already guarded. However, the guard uses the `provider_id` parameter (which could be None), not the result from `_try_stage_work`.

**Fix Required:**
1. Verify if the guard `if provider_id:` at line 269 is sufficient
2. Consider if model could also be None and needs similar guarding
3. The current code at line 269 seems correct (checks provider_id before recording)

**Status:** Code appears to handle this correctly with the `if provider_id:` guard. Verify during implementation that this is sufficient.

---

### BUG-1.7: SSRFSafeRedirectHandler Reset Bug **[HIGH]**

**Location:** `adapters/session.py:23, 30-31, 41`

**Issue:** `_redirect_count` is reset to 0 after *every* successful redirect validation, not when beginning a new redirect chain. For a redirect chain A→B→C→D (all valid), the counter resets after each validation and never accumulates beyond 1, so the 30-redirect limit is never enforceable.

**Verification:** Confirmed at line 41: `self._redirect_count = 0` after successful validation. An attacker could chain unlimited redirects to bypass SSRF protection.

**Fix Required:**
1. Move `self._redirect_count = 0` to `__init__` only (beginning of redirect chain)
2. OR use a different tracking mechanism that persists across redirects in a chain
3. Add test for redirect chain limit

**Implementation Detail:**
```python
# Current (broken):
def __init__(self, ...):
    self._redirect_count = 0  # Line 23

def __call__(self, ...):
    # ... redirect handling ...
    self._redirect_count += 1  # Line 30
    if self._redirect_count > self._max_redirects:  # Line 31
        raise UnsafeURLError(...)
    # ... validation ...
    self._redirect_count = 0  # Line 41 - BUG: resets after EACH success

# Fix: Only reset in __init__, not after each validation
```

---

### BUG-1.8: WebAdapter Date Parsing Silently Returns None **[MEDIUM]**

**Location:** `adapters/web.py:206-221`

**Issue:** `_parse_date()` silently returns `None` for unparseable dates with no logging.

**Verification:** Line 221 returns `None` with no logging when all date formats fail.

**Fix Required:**
1. Add logging for parsing failures:
```python
logger.warning("Failed to parse date: %s", dt_str)
```
2. Consider adding a metric for parsing failures

---

### BUG-1.9: WebAdapter trafilatura ImportError Caught Too Broadly **[MEDIUM]**

**Location:** `adapters/web.py:112-120`

**Issue:** `except (ImportError, ValueError, AttributeError)` catches ValueError and AttributeError too broadly, potentially masking real bugs.

**Verification:** Only `ImportError` is expected for missing trafilatura. Catching ValueError and AttributeError could mask library usage errors.

**Fix Required:**
1. Split into specific exception handling:
```python
try:
    import trafilatura
    # ... trafilatura usage ...
except ImportError:
    logger.warning("trafilatura not installed, content extraction unavailable")
    return None  # or fallback behavior
except (ValueError, AttributeError) as e:
    logger.warning("Content extraction failed for %s: %s", url, e)
    raise  # Re-raise unexpected errors
```

---

### BUG-1.10: api_tokens_bp Blueprint Never Registered **[HIGH]**

**Location:** `app.py` - `_register_blueprints()` function

**Issue:** `api_tokens_bp` blueprint is defined in `routes/admin/api_tokens.py:9` but never registered in `app.py`, causing all `/api-tokens` routes to return 404.

**Verification:** Confirmed - only `public_bp`, `admin_bp`, and `admin_api_bp` are registered in `_register_blueprints()`.

**Fix Required:**
1. Add registration in `app.py:_register_blueprints()`:
```python
from routes.admin.api_tokens import api_tokens_bp
app.register_blueprint(api_tokens_bp)  # Uses url_prefix=None, so routes are absolute like /api-tokens
```

**Alternative:** If token management should be under `/api/v1/auth/api-tokens`, modify the blueprint definition and registration accordingly.

---

### BUG-1.11: API Token Auth Redirects to HTML Login Instead of JSON 401 **[HIGH]**

**Location:** `routes/admin/__init__.py:72`

**Issue:** `require_auth` decorator redirects to HTML login when no Authorization header is present. This is appropriate for browser-based admin but inappropriate for API token management routes.

**Verification:** Confirmed - line 72 redirects to HTML login, but `/api-tokens` routes should return JSON 401.

**Fix Required:**
1. Option A: Create a separate `@require_api_auth` decorator for API-only routes that returns JSON 401
2. Option B: Check if request expects JSON and return appropriate response
3. Ensure `api_tokens_bp` routes use the correct auth decorator

**Implementation Detail:**
```python
# In require_auth decorator, add JSON handling for API routes:
if request.path.startswith('/api') or request.headers.get('Accept') == 'application/json':
    return jsonify({"error": "Unauthorized"}), 401
# Otherwise redirect to HTML login
return redirect(url_for("admin.login"))
```

---

### BUG-1.13: Duplicate Import load_providers_config **[LOW]**

**Location:** `services/llm/__init__.py:11-12`

**Issue:** `load_providers_config` is imported twice - the first import is immediately shadowed.

**Fix Required:**
1. Remove line 11 (keep line 12)
2. Or combine into single import

---

## Phase 2: High Priority Documentation & Implementation Fixes

### TASK-2.2: Document All Actual API Endpoints **[MEDIUM]**

**Issue:** Several endpoints exist but are not documented in `architecture/routes.md`.

**Missing endpoints:**
- `/costs` - cost tracking endpoint (pipeline.py:135)
- `/sources/health` - source health check (pipeline.py:161)
- `/metrics/prometheus` - Prometheus metrics endpoint (config.py:60-62)
- `/articles/ids` - batch article ID lookup (articles.py:151)
- `/articles/counts-by-status` - article count by status (articles.py:170)
- `/search/analytics` - search analytics (search.py:9)
- `/webhooks/events/<id>/resend` - webhook resend (webhooks.py:363)

**Fix Required:**
1. Audit all route files to find actual endpoints
2. Document in `architecture/routes.md`
3. Update AGENTS.md if needed

---

### TASK-2.3: MemoryConfig Documentation 0% Match **[HIGH]**

**Location:** `schemas/pipeline.py:127-137` vs `architecture/schemas.md:67-73`

**Issue:** `MemoryConfig` in documentation completely different from actual code.

**Actual MemoryConfig (schemas/pipeline.py:127-137):**
```python
class MemoryConfig(BaseModel):
    ttl_days_low: int = 7
    ttl_days_medium: int = 30
    ttl_days_high: int = 0
    consolidation_cooldown_hours: int = 24
    max_entries_per_propose: int = 3
    consolidation_merge_window_hours: int = 72
    truncation_llm_enabled: bool = True
    truncation_llm_threshold: int = 2000
    truncation_llm_max_tokens: int = 512
    truncation_llm_temperature: float = 0.0
```

**Documented MemoryConfig (wrong):**
```python
enabled: bool = True
consolidate_interval_hours: int = 24
max_entries_per_topic: int = 100
embedding_model: str = "text-embedding-ada-002"
ttl_days: int = 365
```

**Fix Required:** Update `architecture/schemas.md` to match actual code.

---

### TASK-2.4: NewsletterConfig Documentation Gaps **[HIGH]**

**Issue:** Documentation shows `enable_topic_newsletters`, `batch_size` which don't exist; wrong `max_articles` default.

**Actual NewsletterConfig (schemas/pipeline.py:51-56):**
```python
class NewsletterConfig(BaseModel):
    max_articles: int = Field(default=10, ge=1, le=50)  # Default is 10, not 20
    send_time: str = "08:00"
    timezone: str = "America/New_York"
    site_url: str = "https://ainews.dev"  # Has default
    prep_minutes: int = Field(default=15, ge=5, le=60)
    # Note: NO enable_topic_newsletters or batch_size fields
```

**Fix Required:**
1. Update documentation to match actual schema (no enable_topic_newsletters, no batch_size)
2. Correct max_articles default to 10
3. Add default for site_url

---

### TASK-2.5: SourceConfig adapter_config Field Doesn't Exist **[HIGH]**

**Issue:** Docs show `adapter_config: RSSConfig | APIConfig | WebConfig` but actual is `config: dict[str, Any]`.

**Fix Required:**
1. Update documentation to show correct `config: dict[str, Any]` type
2. Document what keys are expected in the config dict for each adapter type

---

### TASK-2.6: PipelineRootConfig Missing version Field **[MEDIUM]**

**Issue:** `version` field documented but not present in code.

**Fix Required:**
1. Check if `version` field should be added to `PipelineRootConfig`
2. If not needed, remove from documentation
3. If needed, add to schema and config files

---

### TASK-2.8: SelectionResult confidence Type **[MEDIUM]**

**Issue:** Documentation shows `str` with pattern, actual should be `Literal["low", "medium", "high"]`.

**Fix Required:**
1. Update schema to use `Literal["low", "medium", "high"]` for stricter type safety
2. Update documentation

---

### TASK-2.9: RelatedArticle/ExternalSource Field Names Different **[MEDIUM]**

**Issue:** Documentation field names completely different from actual schema.

**Actual RelatedArticle (llm_responses.py:46-50):**
```python
title: str
category: str
summary_snippet: str
created_at: str
```

**Documented (wrong):**
```python
article_id: int
title: str
relevance: str
```

**Fix Required:**
1. Update documentation to match actual field names

---

### TASK-2.10: DirectQuote Field Names Misaligned **[LOW]**

**Issue:** `quote` vs `text`, `attribution` vs `source`.

**Actual DirectQuote (llm_responses.py:40-43):**
```python
quote: str
attribution: str
source_url: Optional[str] = None
```

**Fix Required:**
1. Update documentation or align code (code seems correct, docs wrong)

---

### TASK-2.11: NewsletterArticle Field Names Misaligned **[LOW]**

**Issue:** `headline` vs `title`, `tags` vs `key_points`.

**Actual NewsletterArticle (llm_responses.py:135-139):**
```python
headline: str  # Not title
summary: str
url: Optional[str]
tags: list[str]  # Not key_points
```

**Fix Required:**
1. Update documentation to match actual field names

---

### TASK-2.12: Consolidate URL Validation **[HIGH]**

**Issue:** `services/url.py` and `utils/url.py` have duplicate implementations causing confusion.

**Fix Required:**
1. Determine which is canonical (likely `utils/url.py` based on layering rules)
2. Move all SSRF protection to `utils/url.py`
3. Have `services/url.py` re-export from utils for backward compatibility
4. Update all imports to use `utils/url.py` directly
5. Clean up `__all__` exports in `utils/url.py` to not expose internal items (`_BLOCKED_NETWORKS`, `_TTLCache`, `_dns_executor`)

---

### TASK-2.13: Global Mutable DNS Cache Contradicts Pure Functions **[MEDIUM]**

**Location:** `utils/url.py`

**Issue:** `utils/url.py` claims pure functions but has global mutable DNS cache (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`).

**Fix Required:**
1. Document that this module has side effects (global DNS cache)
2. OR refactor to use a passed-in cache
3. Update AGENTS.md note if this is intentional

---

### TASK-2.14: adapter_config Field on Source Model **[DECISION]**

**Issue:** Documented but never implemented.

**Options:**
1. Implement `adapter_config` field on `Source` model
2. OR confirm it should be removed from documentation

**Decision Required:** Implement or remove from docs.

---

### TASK-2.15: GIN Index on TrendMemory.embedding **[DECISION]**

**Issue:** Documentation claims GIN index for vector search but no GIN index exists.

**Options:**
1. Implement GIN index on `TrendMemory.embedding` column
2. OR update docs to remove claim about vector search indexing

**Decision Required:** Implement index or remove claim.

---

### TASK-2.16: IP/User-Agent Binding for AdminUser Session **[DECISION]**

**Issue:** Documentation says "not implemented" but should either implement or remove note.

**Options:**
1. Implement IP/user-agent binding for AdminUser session security
2. OR remove "not implemented" note and document actual behavior

**Decision Required:** Implement or clean up docs.

---

### TASK-2.17: Update Pipeline Status Values in Documentation **[MEDIUM]**

**Issue:** Documentation shows different status values than actual code.

**Actual statuses:** `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`

**Fix Required:**
1. Update all documentation to use actual status values
2. Verify `selecting` and `selected` are properly documented

---

### TASK-2.18: API Adapter Pagination **[DECISION]**

**Issue:** Documentation shows API adapter has cursor/offset/page pagination but actual doesn't.

**Options:**
1. Update architecture docs to reflect API adapter lacks pagination
2. OR add pagination support to API adapter

**Decision Required:** Add pagination or update docs.

---

### TASK-2.19: WebAdapter Documentation Fix **[LOW]**

**Issue:** Uses `listing_url` (singular), not `start_urls`.

**Fix Required:**
1. Update documentation to use correct field name `listing_url`
2. Verify actual field name used in code

---

### TASK-2.20: BaseLLMProvider Interface Documentation **[MEDIUM]**

**Issue:** Architecture docs don't match actual `BaseLLMProvider` interface.

**Fix Required:**
1. Read actual `BaseLLMProvider` interface in `services/llm/base.py`
2. Update documentation to match actual methods (chat, chat_streaming, etc. not complete/embed)
3. Consider renaming file to `provider_base.py` to match docs

---

### TASK-2.21: Limiter Provider Tracking Bug **[HIGH]**

**Issue:** Uses `stage_config.provider` instead of actual `provider_id` for tracking.

**Location:** Likely in limiter release or metrics tracking

**Fix Required:**
1. Find where `stage_config.provider` is used for limiter tracking
2. Replace with actual `provider_id` used during the call

**Note:** Related to BUG-1.5 - same root cause.

---

### TASK-2.22: Subagent Tool Mapping Table Outdated **[MEDIUM]**

**Issue:** Architecture doc tool mapping table doesn't match actual tool names.

**Fix Required:**
1. Read actual tool definitions in `services/subagent/tools.py`
2. Update architecture doc to use actual canonical tool names

---

### TASK-2.23: Chain Configuration Source Documentation **[MEDIUM]**

**Issue:** Documentation shows inline YAML but actual comes from `pipeline.yaml` via `SubagentChainConfig`.

**Fix Required:**
1. Update `architecture/subagent.md` to document that chain config comes from `pipeline.yaml`
2. Document `SubagentChainConfig` schema

---

## Phase 3: Medium Priority Items

### TASK-3.1: Document Stage vs Status Naming Convention **[MEDIUM]**

**Issue:** "select/research/write/edit" stages vs "pending/researching/writing/editing" status constants cause confusion.

**Fix Required:**
1. Add glossary section to architecture docs clarifying:
   - Stages: select → research → write → edit (what happens)
   - Statuses: pending, selecting, selected, researching, writing, written, editing, review (state machine)
2. Update all documentation to be consistent

---

### TASK-3.2: Document Actual Stage Flow **[MEDIUM]**

**Issue:** Architecture doc shows `pending → select` but code uses `pending → researching` directly.

**Fix Required:**
1. Verify actual flow in `tasks/pipeline.py`
2. Update documentation to match actual flow
3. Document when selection is skipped/bypassed

---

### TASK-3.3: Use Chord with Callback for Newsletter **[MEDIUM]**

**Issue:** `group()` used for parallel topic newsletter generation but `chord()` would provide proper synchronization.

**Fix Required:**
1. Find newsletter generation code using `group()`
2. Replace with `chord()` and proper callback
3. Document the change

---

### TASK-3.4: Document Missing Tasks **[MEDIUM]**

**Issue:** `cleanup-inactive-subscribers` exists in beat schedule but not documented.

**Fix Required:**
1. Add to Celery Beat schedule documentation
2. Verify task exists and functions correctly

---

### TASK-3.5: Document aggregate_crawl_results **[LOW]**

**Issue:** Chord callback at `crawl.py:215` needs documentation.

**Fix Required:**
1. Find `aggregate_crawl_results` function
2. Document its role in crawl flow
3. Add to architecture docs

---

### TASK-3.6: Document retry_failed_newsletter_deliveries **[LOW]**

**Issue:** Task exists in beat schedule but not in architecture.

**Fix Required:**
1. Verify task exists
2. Add to documentation

---

### TASK-3.7: Document Blueprint Structure **[MEDIUM]**

**Issue:** Need section explaining `admin_bp` at `/admin` for HTML vs `admin_api_bp` at `/api/v1` for JSON.

**Fix Required:**
1. Add architecture section documenting blueprint structure
2. Clarify URL prefix separation between HTML and API routes

---

### TASK-3.8: Document @require_auth Behavior **[LOW]**

**Issue:** Need to note it supports both session-based and token-based auth.

**Fix Required:**
1. Find `@require_auth` decorator implementation
2. Document both auth modes
3. Add examples for each mode

---

### TASK-3.9: Subagent Tool Function Naming Convention **[LOW]**

**Issue:** Need to document `_context_tool_*` or `_search_*` prefix convention.

**Fix Required:**
1. Find actual naming convention used in `services/subagent/tools.py`
2. Document in `architecture/subagent.md`

---

### TASK-3.10: Add conditions.py to Architecture Overview **[LOW]**

**Issue:** AST-based condition evaluation module not documented.

**Fix Required:**
1. Find `services/subagent/conditions.py`
2. Document its purpose and how it works
3. Add to architecture overview

---

### TASK-3.11: Document utils.py Contents **[LOW]**

**Issue:** `_retry_with_backoff`, `_is_task_revoked`, `_format_subagent_prompt` not documented.

**Fix Required:**
1. Find `services/subagent/utils.py`
2. Document each function's purpose
3. Add to architecture docs

---

### TASK-3.12: Add ErrorHandlingMiddleware to run_subagent() **[LOW]**

**Issue:** `run_subagent()` doesn't apply middleware but `run_subagent_with_tools()` does.

**Fix Required:**
1. Verify middleware consistency
2. Add `ErrorHandlingMiddleware` to `run_subagent()` or document why it's not needed

---

### TASK-3.13: Subagent Public API Documentation **[LOW]**

**Issue:** Need to clarify which `__init__.py` exports are public API vs internal.

**Fix Required:**
1. Audit `services/subagent/__init__.py`
2. Mark internal functions with `_` prefix or move to `_internals.py`
3. Document public API surface

---

### TASK-3.14: ToolDefinition Missing cached Field **[DECISION]**

**Issue:** Architecture documents `cached: bool` on `ToolDefinition` but it's not in schema.

**Options:**
1. Add `cached` field to ToolDefinition schema
2. OR remove from documentation

**Decision Required**

---

### TASK-3.15: Document Two-Tier Retry System **[MEDIUM]**

**Issue:** Celery task-level vs stage failure level retry system not documented.

**Fix Required:**
1. Find both retry mechanisms in code
2. Document how they interact
3. Add to architecture docs

---

### TASK-3.16: Clarify Degradation Behavior for Disabled Stages **[MEDIUM]**

**Issue:** What happens when a stage is disabled needs documentation.

**Fix Required:**
1. Find `_handle_disabled` or similar logic
2. Document behavior for each stage when disabled
3. Add to architecture docs

---

### TASK-3.17: Document _should_route_to_review Logic **[MEDIUM]**

**Issue:** `auto_publish_threshold` config and routing logic not documented.

**Fix Required:**
1. Find `_should_route_to_review` function
2. Document `auto_publish_threshold` config
3. Add flow diagram to architecture docs

---

### TASK-3.18: Add Circuit Breaker Architecture Diagram **[LOW]**

**Issue:** Circuit breaker documented but no diagram.

**Fix Required:**
1. Create ASCII/text diagram showing:
   - Failure count threshold (5)
   - Time window (2 min)
   - Half-open state timeout (60s)
   - State transitions

---

### TASK-3.19: Document meta vs metadata on PipelineLog **[LOW]**

**Issue:** Need to explain why `meta` is used instead of `metadata`.

**Fix Required:**
1. Add note explaining SQLAlchemy reserved name restriction
2. Document what data goes into `meta` field

---

### TASK-3.20: Clarify Newsletter Lock Mechanism **[LOW]**

**Issue:** Lua script for newsletter lock not documented.

**Fix Required:**
1. Find Lua script for newsletter idempotency lock
2. Document the locking mechanism
3. Add to architecture docs

---

### TASK-3.21: Document 3-Stage Newsletter Pipeline Flow **[LOW]**

**Issue:** 3-stage newsletter pipeline flow needs more precise documentation.

**Fix Required:**
1. Identify the 3 stages (likely: reader → writer → editor)
2. Document each stage's inputs/outputs
3. Add flow diagram

---

## Phase 4: Cleanup & Low Priority Items

### TASK-4.1: Add Dedicated Unit Tests for Utils **[MEDIUM]**

**Issue:** Tests go through `services/url.py`; need direct tests for `utils/` functions.

**Fix Required:**
1. Create `tests/utils/` directory
2. Add tests for each utils module
3. Test edge cases (empty strings, None, etc.)

---

### TASK-4.2: Clean Up __all__ Exports in utils/url.py **[LOW]**

**Issue:** Internal items exposed in public API (`_BLOCKED_NETWORKS`, `_TTLCache`, `_dns_executor`).

**Fix Required:**
1. Review `__all__` in `utils/url.py`
2. Remove internal items from public exports
3. Document public API surface

---

### TASK-4.3: Document Return Type Mismatch in Adapters **[LOW]**

**Issue:** `list[Any]` vs `list[dict]` return type mismatch.

**Fix Required:**
1. Check actual return type of adapter fetch methods
2. Standardize to `list[dict]` or appropriate type
3. Update type hints

---

### TASK-4.4: Update YAML Config Examples **[LOW]**

**Issue:** Config examples use wrong field names (`start_urls` vs `feed_url`, `list_url`, `listing_url`).

**Fix Required:**
1. Find YAML config examples in documentation
2. Update to use actual field names

---

### TASK-4.5: Clarify Rate Limiting Responsibility **[LOW]**

**Issue:** Need to document LLM services handle Retry-After, not adapters.

**Fix Required:**
1. Document in architecture that adapters don't handle rate limiting
2. LLM providers handle Retry-After headers
3. Add note about backoff behavior

---

### TASK-4.6: Clarify Source Health Tracking **[LOW]**

**Issue:** Documentation says adapters track source health but actual is `services/crawling.py`.

**Fix Required:**
1. Update documentation to show `services/crawling.py` handles health tracking
2. Document health check frequency and metrics

---

### TASK-4.7: Add embed() Method to BaseLLMProvider **[DECISION]**

**Issue:** Documented but not present in interface.

**Options:**
1. Add `embed()` method stub to `BaseLLMProvider`
2. OR remove from documentation

**Decision Required**

---

### TASK-4.8: Dead Code Removal **[LOW]**

**Issue:** `_finalize_subagent_result()` is never called in `runner.py:277-328`.

**Fix Required:**
1. Verify it's truly dead code
2. Remove if not used

---

### TASK-4.10: Layer Violation Cleanup - tasks/extract.py **[LOW]**

**Issue:** `tasks/extract.py:121` imports from `services.article` for deduplication logic.

**Fix Required:**
1. Verify if this is acceptable or needs refactor
2. Move deduplication logic to avoid services import from tasks
3. Note: Per AGENTS.md, tasks→services is allowed (tasks are orchestrators). This may not be a violation.

---

### TASK-4.11: Services/Newsletter Pipeline Redis Access **[LOW]**

**Issue:** `services/newsletter_pipeline.py` directly accesses Redis instead of using limiter abstraction.

**Fix Required:**
1. Check if direct Redis access is necessary
2. Consider using limiter abstraction or adding Redis client wrapper

---

### TASK-4.12: Schema Imports Should Use TYPE_CHECKING **[LOW]**

**Issue:** Schema imports at top-level instead of TYPE_CHECKING pattern.

**Fix Required:**
1. Find schema files with runtime imports from services
2. Convert to TYPE_CHECKING pattern

---

## Wave Organization for Parallelization

### Wave A: Bug Fixes (Can run in parallel)
Each bug is independent - multiple agents can work on different bugs simultaneously.

| Bug | Location | Issue | Verification Status |
|-----|----------|-------|---------------------|
| BUG-1.1 | tasks/newsletter.py:430 | idempotency_key NameError | CONFIRMED |
| BUG-1.3 | constants.py:49-58 | VALID_TRANSITIONS missing selecting/selected | CONFIRMED |
| BUG-1.5 | tasks/pipeline.py:436 | Limiter model mismatch after fallback | CONFIRMED |
| BUG-1.6 | tasks/pipeline.py:269 | provider_id may be None in exception | CODE CHECK |
| BUG-1.7 | adapters/session.py:41 | SSRF redirect counter reset bug | CONFIRMED |
| BUG-1.8 | adapters/web.py:221 | Date parsing silently returns None | CONFIRMED |
| BUG-1.9 | adapters/web.py:119 | ImportError caught too broadly | CONFIRMED |
| BUG-1.10 | app.py | api_tokens_bp not registered | CONFIRMED |
| BUG-1.11 | routes/admin/__init__.py:72 | Token auth redirects to HTML | CONFIRMED |
| BUG-1.13 | services/llm/__init__.py:11-12 | Duplicate import | CONFIRMED |

### Wave B: Documentation Fixes - Group 1 (Schemas)
Can parallelize by schema file:

| Task | Location | Issue |
|------|----------|-------|
| TASK-2.3 | architecture/schemas.md vs pipeline.py:127-137 | MemoryConfig 0% match |
| TASK-2.4 | architecture/schemas.md vs pipeline.py:51-56 | NewsletterConfig wrong |
| TASK-2.5 | SourceConfig adapter_config | Wrong type |
| TASK-2.6 | PipelineRootConfig | Missing version field |
| TASK-2.8 | SelectionResult confidence | Should be Literal type |
| TASK-2.9 | RelatedArticle/ExternalSource | Wrong field names |

### Wave C: Documentation Fixes - Group 2 (Routes & Architecture)
| Task | Location | Issue |
|------|----------|-------|
| TASK-2.2 | architecture/routes.md | Missing endpoints |
| TASK-2.7 | SelectionResult impact_summary | Already correct - no action |
| TASK-2.10 | DirectQuote field names | quote vs text |
| TASK-2.11 | NewsletterArticle field names | headline vs title |
| TASK-2.17 | Pipeline status values | Doc shows different values |
| TASK-2.19 | WebAdapter docs | listing_url not start_urls |
| TASK-2.20 | BaseLLMProvider interface | Doc doesn't match code |

### Wave D: Implementation Fixes (Some decisions needed)
| Task | Location | Issue | Decision |
|------|----------|-------|----------|
| TASK-2.12 | utils/url.py + services/url.py | URL validation duplication | Pick canonical |
| TASK-2.14 | Source model | adapter_config field | Implement or remove |
| TASK-2.15 | TrendMemory | GIN index for vector search | Implement or remove |
| TASK-2.16 | AdminUser session | IP/User-Agent binding | Implement or document |
| TASK-2.18 | API adapter | Pagination missing | Add or update docs |
| TASK-2.21 | Limiter tracking | Uses wrong provider | Fix to use provider_id |
| TASK-2.22 | Subagent tools | Tool mapping table outdated | Update docs |
| TASK-2.23 | Chain config | YAML vs pipeline.yaml | Update docs |

### Wave E: Medium Priority Documentation
| Task | Location | Issue |
|------|----------|-------|
| TASK-3.1 | Stage vs Status naming | Clarify terminology |
| TASK-3.2 | Stage flow | Doc shows different flow |
| TASK-3.3 | Newsletter chord | group vs chord |
| TASK-3.4-3.6 | Missing tasks | Document missing tasks |
| TASK-3.7-3.11 | Blueprint, auth, naming | Document structure |
| TASK-3.15-3.17 | Retry, degradation, routing | Document behavior |
| TASK-3.18-3.21 | Diagrams, lock mechanism | Add documentation |

### Wave F: Cleanup
| Task | Location | Issue |
|------|----------|-------|
| TASK-4.1 | tests/utils/ | Add unit tests |
| TASK-4.2 | utils/url.py __all__ | Clean exports |
| TASK-4.3 | Adapter return types | Standardize |
| TASK-4.4 | YAML config examples | Fix field names |
| TASK-4.5 | Rate limiting | Document responsibility |
| TASK-4.6 | Source health | Update docs |
| TASK-4.7 | embed() method | Add or remove |
| TASK-4.8 | _finalize_subagent_result | Dead code |
| TASK-4.10 | tasks/extract.py | Verify if violation |
| TASK-4.11 | newsletter_pipeline.py | Redis abstraction |
| TASK-4.12 | Schema imports | TYPE_CHECKING pattern |

---

## Implementation Notes for Future Agents

### Starting Point
When picking up work from this plan:

1. **Read the relevant bug/task section fully** - each section has implementation details
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
- `tasks/pipeline.py` - Pipeline orchestration, stage execution, limiter release
- `tasks/newsletter.py` - Newsletter generation, locking, idempotency
- `constants.py` - VALID_TRANSITIONS, PipelineStatus enum
- `adapters/session.py` - SSRFSafeRedirectHandler
- `adapters/web.py` - WebAdapter, date parsing, trafilatura
- `routes/admin/__init__.py` - require_auth decorator
- `routes/admin/api_tokens.py` - api_tokens_bp (not registered)
- `services/llm/__init__.py` - Provider config, duplicate import
- `schemas/pipeline.py` - Config schemas
- `architecture/` - Architecture documentation

### Wave Execution Recommendation
For fastest execution, assign agents to waves as follows:
- **Agent 1**: Wave A (all bug fixes - independent)
- **Agent 2**: Wave B (schema documentation)
- **Agent 3**: Wave C (routes/architecture docs)
- **Agent 4**: Wave D (implementation fixes with decisions)
- **Agent 5**: Wave E (medium priority docs)
- **Agent 6**: Wave F (cleanup)

Waves B-F can start as soon as Wave A bugs are understood, but some tasks depend on decisions (Wave D).

---

## Progress Tracking

| Item | Status | Completed Date | Notes |
|------|--------|----------------|-------|
| BUG-1.1 | PENDING | | |
| BUG-1.3 | PENDING | | |
| BUG-1.5 | PENDING | | |
| BUG-1.6 | PENDING | | Code may already handle correctly |
| BUG-1.7 | PENDING | | |
| BUG-1.8 | PENDING | | |
| BUG-1.9 | PENDING | | |
| BUG-1.10 | PENDING | | |
| BUG-1.11 | PENDING | | |
| BUG-1.13 | PENDING | | |
| TASK-2.2 | PENDING | | |
| TASK-2.3 | PENDING | | |
| TASK-2.4 | PENDING | | |
| TASK-2.5 | PENDING | | |
| TASK-2.6 | PENDING | | |
| TASK-2.8 | PENDING | | |
| TASK-2.9 | PENDING | | |
| TASK-2.10 | PENDING | | |
| TASK-2.11 | PENDING | | |
| TASK-2.12 | PENDING | | |
| TASK-2.13 | PENDING | | |
| TASK-2.14 | PENDING | | Decision needed |
| TASK-2.15 | PENDING | | Decision needed |
| TASK-2.16 | PENDING | | Decision needed |
| TASK-2.17 | PENDING | | |
| TASK-2.18 | PENDING | | Decision needed |
| TASK-2.19 | PENDING | | |
| TASK-2.20 | PENDING | | |
| TASK-2.21 | PENDING | | |
| TASK-2.22 | PENDING | | |
| TASK-2.23 | PENDING | | |
| TASK-3.x | PENDING | | |
| TASK-4.x | PENDING | | |

---

*End of file*
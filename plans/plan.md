# AINews Implementation Plan

**Status:** IN PROGRESS (Consolidated from architecture review - 2026-05-22)
**Last Updated:** 2026-05-22

---

## Overview

This plan consolidates findings from 10 architecture review files across all modules. Items are organized into waves based on priority and parallelization potential.

**Parallelization Strategy:**
- WAVE 2 items (all code fixes) can be implemented in parallel by separate agents
- WAVE 3-5 items (documentation) can be parallelized by module area
- Within each wave, agents can claim different items independently

---

## WAVE 1 - Critical Bug Fixes (Sequential/High Risk)

No critical bugs currently pending - WAVE1-1 (XSS) has been fixed.

---

## WAVE 2 - High Priority Fixes

### WAVE2-1
**Module:** Routes
**Location:** `routes/admin/api_tokens.py:7`
**Description:** Layering issue - api_tokens.py imports require_auth from parent
**Issue:** `api_tokens.py` imports `require_auth` from `routes.admin.__init__.py`. This creates circular dependency risk since `__init__.py` imports all submodules including `api_tokens`.
**Implementation Notes:** Move `require_auth` to `routes/decorators.py` or create `routes/admin/auth.py` for auth utilities. Alternative: use `from routes.decorators import require_auth` directly.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE2-2
**Module:** Adapters
**Location:** `adapters/api.py:63-71`
**Description:** item_url external_id validation bug
**Issue:** The `item_url` template uses `{id}` placeholder but no validation exists to ensure `fields.external_id` is configured when `item_url` is used. Silently returns empty results if `external_id` not configured.
**Implementation Notes:** Add validation that `fields.external_id` is configured when `item_url` is set; return clear error or log warning.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE2-3
**Module:** Tasks
**Location:** `services/subagent/chain.py:36,62`
**Description:** Schema validation bypass for chain steps
**Issue:** `run_subagent_chain()` accepts `steps: list[dict]` parameter which bypasses schema validation. At line 65, code accesses `step_config.task_type` without validation - dict objects don't have `.task_type` attribute access, so this fails with unclear `AttributeError`.
**Implementation Notes:** Add runtime validation: `SubagentChainStep.model_validate(step_config)` at the start of the for loop, or change parameter type from `list[dict]` to `list[SubagentChainStep]`.
**Dependencies:** None
**Severity:** HIGH

### WAVE2-4
**Module:** Subagent
**Location:** `services/subagent/runner.py:346-348`
**Description:** Middleware mutation bug - tool.fn compounding on cached ToolDefinition objects
**Issue:** `apply_middleware` mutates `tool.fn` on cached `ToolDefinition` objects. `initialize_tool_registry` returns cached tool definitions that are reused across calls. When `copy.deepcopy(tool.fn)` is applied, the wrapped function is copied but then re-assigned to `tool.fn` which is still the cached object. Second call wraps the already-wrapped function.
**Implementation Notes:** Clone the ToolDefinition object itself before modifying, not just the fn. The current `copy.deepcopy(tool.fn)` only copies the function, not the containing ToolDefinition. Change to:
```python
for tool in tools:
    if tool.fn:
        tool_copy = ToolDefinition(name=tool.name, description=tool.description,
                                   parameters=tool.parameters, required=tool.required,
                                   fn=copy.deepcopy(tool.fn))
        tool_copy.fn = apply_middleware(tool_copy.fn, middleware_chain)
        # Replace in tools list, but this doesn't fix the cached registry
```
The real fix: modify `initialize_tool_registry()` to apply middleware at registration time, or make it return copies of tool definitions.
**Dependencies:** None
**Severity:** MEDIUM

---

## WAVE 3 - Documentation Fixes (Can parallelize)

### WAVE3-1
**Module:** Architecture
**Location:** `architecture/subagent.md:143-147`
**Description:** Tool results ARE re-injected (doc is wrong)
**Issue:** Document says "Tool results are NOT re-injected into messages" but actual behavior at `services/llm/base.py:490,557-558` shows they ARE re-injected via `all_messages.append(tool_result_msg)`. This creates a multi-turn conversation loop.
**Implementation Notes:** Update documentation to reflect actual multi-turn behavior. Clarify the distinction between single-shot vs multi-turn tool calling.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE3-2
**Module:** Architecture
**Location:** `architecture/pipeline.md:53-64`
**Description:** Add pending→review, editing→review transitions to valid transitions table
**Issue:** The valid transitions table doesn't show transitions TO `review` status. Articles can transition to `review` from `PENDING` (via disabled select) and `EDITING` (quality gate failure).
**Implementation Notes:** Update table to show `PENDING → REVIEW` and `EDITING → REVIEW` transitions.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE3-3
**Module:** Architecture
**Location:** `architecture/pipeline.md:74-76`
**Description:** Document select stage requires BOTH selected=True AND score >= min_score
**Issue:** Document implies score is the primary driver but implementation requires BOTH `selected=True` AND `score >= min_score`. If LLM returns `selected=False`, article goes to `SKIPPED` regardless of score.
**Implementation Notes:** Update documentation to clarify both conditions must be met.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE3-4
**Module:** Architecture
**Location:** `architecture/pipeline.md:244-251`
**Description:** Document edit degradation routing rules correctly
**Issue:** Document says edit degradation routes to review, but actual implementation routes to `DONE` if `degradation_count < 2` AND `_should_route_to_review()` returns False.
**Implementation Notes:** Update to clarify edit degradation may finalize to `DONE` if auto-publish threshold is met.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE3-5
**Module:** Architecture
**Location:** `architecture/pipeline.md:253-255`
**Description:** Document selector's retry_countdown=15 parameter
**Issue:** Document mentions `retry_max=20` for selector but not the more aggressive `retry_countdown=15` parameter at `tasks/select.py:193-202`.
**Implementation Notes:** Update to mention `retry_countdown=15` for selector stage.
**Dependencies:** None
**Severity:** LOW

### WAVE3-6
**Module:** Architecture
**Location:** `architecture/pipeline.md:261-269`
**Description:** Document pipeline monitor limitations
**Issue:** Known gaps (p95/p99 percentiles, queue depth per stage, source health correlation) not documented as future work.
**Implementation Notes:** Add "Known Limitations" section documenting what monitor does NOT track.
**Dependencies:** None
**Severity:** LOW

### WAVE3-7
**Module:** Architecture
**Location:** `architecture/overview.md:11-21`
**Description:** Fix Module Index table paths
**Issue:** Table shows pipeline.md and subagent.md at root level but actual deep-dive documents are in `architecture/` directory.
**Implementation Notes:** Update paths to `architecture/pipeline.md`, `architecture/subagent.md`, etc.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE3-8
**Module:** Architecture
**Location:** `architecture/overview.md:280`
**Description:** Verify "14 scheduled tasks" claim
**Issue:** Overview states "Celery Beat schedule (14 scheduled tasks)" but actual count needs verification against `config.py`.
**Implementation Notes:** Count actual tasks in `config.py:get_beat_schedule()` and update claim.
**Dependencies:** None
**Severity:** LOW

### WAVE3-9
**Module:** Architecture
**Location:** `architecture/tasks.md`
**Description:** Document aggregate_crawl_results task
**Issue:** `aggregate_crawl_results` is a chord callback task in `crawl.py:215-253` but not documented in file inventory.
**Implementation Notes:** Add to file inventory table in tasks.md.
**Dependencies:** None
**Severity:** LOW

### WAVE3-10
**Module:** Architecture
**Location:** `architecture/tasks.md`
**Description:** Fix task name retry-stuck-articles vs actual retry_stuck
**Issue:** Document uses `retry-stuck-articles` but actual task function is `retry_stuck`. Beat schedule key is `retry-stuck-articles` which is correct, but doc should clarify this.
**Implementation Notes:** Note the beat schedule uses `retry-stuck-articles` key while the function is named `retry_stuck`.
**Dependencies:** None
**Severity:** LOW

### WAVE3-11
**Module:** Architecture
**Location:** `architecture/services.md`
**Description:** Document known layering exceptions
**Issue:** `services/crawling.py` imports from `adapters.base` and `services/subagent/tools.py` imports from `models` and `extensions` are documented in AGENTS.md but not in architecture/services.md.
**Implementation Notes:** Add section documenting known layering exceptions per AGENTS.md.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE3-12
**Module:** Architecture
**Location:** `architecture/services.md`
**Description:** Document BaseProvider base class
**Issue:** `services/provider_base.py` with `BaseProvider` and `ProviderManager` classes not listed in architecture document. `BaseLLMProvider` inherits from `BaseProvider` at `services/llm/base.py:111`.
**Implementation Notes:** Add `provider_base.py` to file inventory and document `BaseProvider` base class.
**Dependencies:** None
**Severity:** LOW

### WAVE3-13
**Module:** Architecture
**Location:** `architecture/services.md`
**Description:** Add article_parser.py to architecture
**Issue:** `services/article_parser.py` exists but is not listed in architecture document file inventory.
**Implementation Notes:** Add `article_parser.py` to file inventory.
**Dependencies:** None
**Severity:** LOW

---

## WAVE 4 - Medium Priority (Can parallelize)

### WAVE4-1
**Module:** Adapters
**Location:** `adapters/api.py:196-210`
**Description:** contains filter not implemented
**Issue:** `contains` filter operation in `_passes_filters()` is NOT implemented. If config uses `{"contains": "value"}`, it is silently ignored.
**Implementation Notes:** Add to `_passes_filters`:
```python
if "contains" in f:
    if f["contains"] not in str(current):
        return False
```
**Dependencies:** None
**Severity:** MEDIUM

### WAVE4-2
**Module:** Schemas
**Location:** `schemas/source.py:84`
**Description:** date_attribute default documentation mismatch
**Issue:** Document says `date_attribute: str = "datetime"` but code has `date_attribute: Optional[str] = None`.
**Implementation Notes:** Update `date_attribute` default to `None` in documentation.
**Dependencies:** None
**Severity:** LOW

### WAVE4-3
**Module:** Models
**Location:** `models/article.py:22`
**Description:** Missing index on original_published_at
**Issue:** Document says index `ix_articles_published` on `original_published_at` but code has no index on this column. `published_at` has `index=True` but no explicit index name.
**Implementation Notes:** If `original_published_at` is intended column for published article listings, add `db.Index("ix_articles_published", "original_published_at")` to `__table_args__`.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE4-4
**Module:** Models
**Location:** `models/context.py:44`
**Description:** last_accessed_at onupdate lambda may not work correctly
**Issue:** `onupdate=lambda: datetime.now(timezone.utc)` may not work correctly with SQLAlchemy. `onupdate` callback should receive current time directly, not via lambda.
**Implementation Notes:** Verify `onupdate` works correctly; consider using `default` callable syntax instead.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE4-5
**Module:** Architecture
**Location:** `architecture/services.md`
**Description:** Add article_parser.py and provider_base.py to architecture doc
**Issue:** Both files exist but not listed in architecture document file inventory.
**Implementation Notes:** Add both files to inventory.
**Dependencies:** WAVE3-12, WAVE3-13
**Severity:** LOW

### WAVE4-6
**Module:** Services
**Location:** `services/limiter.py:132-138`
**Description:** get_active() silent failure on Redis error
**Issue:** `get_active()` returns `None` instead of raising or logging a warning when Redis is unavailable. Silent failure mode could mask connectivity issues.
**Implementation Notes:** Consider changing to raise on Redis error or log warning.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE4-7
**Module:** Adapters
**Location:** `adapters/web.py:180-182`
**Description:** Retry-After header not respected
**Issue:** WebAdapter uses fixed exponential backoff (2^attempt * 5 + jitter) and does NOT read `Retry-After` header from 429 responses.
**Implementation Notes:** Consider reading `Retry-After` header when present; document limitation if not implemented.
**Dependencies:** None
**Severity:** LOW

---

## WAVE 5 - Low Priority (Can parallelize)

### WAVE5-1
**Module:** Utils
**Location:** `utils/text.py:83-131`
**Description:** sanitize_html unused in production - add test coverage or deprecate
**Issue:** `sanitize_html` is not imported anywhere in production code. Newsletter routes use `nh3` instead. The function exists but is orphaned.
**Implementation Notes:** Either add comprehensive test coverage to verify XSS protection works correctly, or deprecate and remove the function.
**Dependencies:** None
**Severity:** LOW

### WAVE5-2
**Module:** Utils
**Location:** `utils/url.py:74-77`
**Description:** Port stripping behavior undocumented
**Issue:** Code strips port 443 for HTTPS and port 80 for HTTP, but this is undocumented. Could cause issues if site serves both HTTP and HTTPS on different ports.
**Implementation Notes:** Document this behavior in arch doc or add code comment.
**Dependencies:** None
**Severity:** LOW

### WAVE5-3
**Module:** Routes
**Location:** `routes/admin/api/articles.py`
**Description:** Missing GET /api/v1/articles list endpoint
**Issue:** Document lists `GET /api/v1/articles` - List articles but this endpoint doesn't exist. Closest is `articles/ids` which returns only IDs.
**Implementation Notes:** Add article list endpoint or update documentation to clarify the actual API surface.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE5-4
**Module:** Routes
**Location:** `routes/admin/trend_memory.py:117`
**Description:** trend-memory/semantic-search wrong URL prefix
**Issue:** Document says `/api/v1/trend-memory/semantic-search` but actual URL is `/admin/api/trend-memory/semantic-search` (registered on `admin_bp` prefix `/admin`).
**Implementation Notes:** Move endpoint to `admin_api_bp` or update documentation.
**Dependencies:** None
**Severity:** MEDIUM

### WAVE5-5
**Module:** Architecture
**Location:** `architecture/routes.md:44,47`
**Description:** Duplicate route documentation
**Issue:** `/admin/articles/<id>/original` appears twice in document (lines 44 and 47).
**Implementation Notes:** Remove duplicate entry.
**Dependencies:** None
**Severity:** LOW

### WAVE5-6
**Module:** Architecture
**Location:** `architecture/routes.md:72-78`
**Description:** shares routes differ between doc and code
**Issue:** Document shows `/admin/shares/<id>/edit-form` and separate `row` routes but code uses different pattern (`POST /admin/shares/<id>/edit`, `POST /admin/shares/<id>/row`).
**Implementation Notes:** Update documentation to match actual routes.
**Dependencies:** None
**Severity:** LOW

### WAVE5-7
**Module:** Architecture
**Location:** `architecture/routes.md:265-293`
**Description:** Newsletter endpoints not in API table
**Issue:** `/api/v1/newsletter/preview` endpoint exists but is not listed in API table at lines 265-293.
**Implementation Notes:** Add missing endpoints to API table.
**Dependencies:** None
**Severity:** LOW

### WAVE5-8
**Module:** Utils
**Location:** `schemas/source.py:33`
**Description:** Typo "AINwsBot" → "AINewsBot"
**Issue:** Default user_agent shows "AINwsBot" typo.
**Implementation Notes:** Fix typo to "AINewsBot".
**Dependencies:** None
**Severity:** LOW

### WAVE5-9
**Module:** Adapters
**Location:** `adapters/api.py:63-71`
**Description:** Sequential item fetching performance consideration
**Issue:** `_fetch_item` fetches individual items sequentially with no parallelization or batching when `item_url` is configured.
**Implementation Notes:** Consider async/threaded fetching for `item_url` when many items. Low priority since this is a performance optimization, not a bug.
**Dependencies:** None
**Severity:** LOW

### WAVE5-10
**Module:** Schemas
**Location:** `schemas/source.py`
**Description:** auth_type limitation undocumented (APIAdapter only supports Bearer)
**Issue:** AGENTS.md documents APIAdapter only supports Bearer token, but schema documentation doesn't clarify this limitation.
**Implementation Notes:** Document auth_type limitation in schema docstring or architecture doc.
**Dependencies:** None
**Severity:** LOW

### WAVE5-11
**Module:** Schemas
**Location:** `adapters/api.py:163`
**Description:** item_url placeholder format undocumented
**Issue:** `item_url` is a Python format string using `{id}` placeholder but documentation doesn't specify this format.
**Implementation Notes:** Document `{id}` placeholder format in schema docstring.
**Dependencies:** None
**Severity:** LOW

### WAVE5-12
**Module:** Models
**Location:** `models/article.py:45-49`
**Description:** updated_at has index=True (doc says no index)
**Issue:** Document says `updated_at` has no index but code has `index=True`.
**Implementation Notes:** Update documentation to note `updated_at` has `index=True`.
**Dependencies:** None
**Severity:** LOW

### WAVE5-13
**Module:** Models
**Location:** `models/source.py:12`
**Description:** source_key has nullable=False (doc omits constraint)
**Issue:** Document shows `source_key = Column(String(64), unique=True)` but actual has `nullable=False`.
**Implementation Notes:** Update documentation to show `nullable=False`.
**Dependencies:** None
**Severity:** LOW

---

## Deferred Items

None currently pending.

---

## Implementation Summary

| Wave | Items | Description |
|------|-------|-------------|
| WAVE 1 | 0 | No critical bugs pending (XSS fix was verified complete) |
| WAVE 2 | 4 | High priority (api_tokens layering, item_url validation, chain validation, middleware mutation) |
| WAVE 3 | 13 | Documentation fixes (subagent, pipeline, overview, services, tasks) |
| WAVE 4 | 7 | Medium priority (contains filter, indexes, limiter, web adapter) |
| WAVE 5 | 13 | Low priority (unused code, typos, minor doc updates) |
| **Total** | **37** | Items consolidated from architecture reviews |

**Corrections/Verification:**
- WAVE1-1 (XSS): FIXED - `sanitize_html` now properly handles SVG script content and CSS `expression()`
- WAVE1-2/WAVE1-3: Moved to WAVE2-3 and WAVE2-4 (still pending bugs, not critical)
- edit.py `_dispatch_next`: NOT a bug - properly imported at line 188
- retry.py `_dead_letter`/`_apply_fallback`: NOT bugs - imports verified correct in current code
- DeepSeek: Not a search provider - correctly documented as regex pattern in trend_detector.py
- tasks_review.md retry bug claims: ERRONEOUS - current code verified correct

---

## Original Plan Files

The following files were consolidated into this plan and should be deleted:
- `plans/adapters_review.md`
- `plans/models_review.md`
- `plans/overview_review.md`
- `plans/pipeline_review.md`
- `plans/routes_review.md`
- `plans/schemas_review.md`
- `plans/services_review.md`
- `plans/subagent_review.md`
- `plans/tasks_review.md`
- `plans/utils_review.md`

---

*Plan in progress - 2026-05-22*
# AINews Consolidated Implementation Plan

**Status:** IN PROGRESS
**Last Updated:** 2026-05-13
**Goal:** Consolidate findings from 9 architecture review documents into actionable items.

---

## Executive Summary

This plan consolidates action items from architecture reviews of: schemas, pipeline, routes, tasks, services, models, subagent, adapters, and utils modules. Items are organized by priority and phase to enable parallel implementation via "waves."

### Priority Summary

| Priority | Count | Items |
|----------|-------|-------|
| HIGH | 3 | Critical bugs affecting functionality |
| MEDIUM | 8 | Bugs and implementation improvements |
| LOW | 5 | Documentation fixes |

---

## Items Already Completed (VERIFIED AS FIXED)

The following were marked as bugs but have been verified as FIXED:
- **CRIT-2 (newsletter_pipeline limiter slot leak)**: Already uses `provider_id` from `get_provider_for_role()` - verified at `services/newsletter_pipeline.py:109-123`
- **MED-3 (ThreadPoolExecutor shutdown)**: `atexit.register(shutdown_executor)` already in `services/subagent/config.py:21`
- **MED-4 (Tool registry race condition)**: `_TOOL_REGISTRY_LOCK` already protects initialization at `services/subagent/registry.py:59`
- **MED-5 (retry_stuck missing SELECTING status)**: `SELECTING` already in the filter list at `tasks/retry.py:122-123`
- **HIGH-2 (Source adapter config docs)**: This is a DOCUMENTATION task, not a code bug

---

## Phase 1: Critical Bug Fixes

### CRIT-1: SSRFSafeRedirectHandler Redirect Counter Accumulates Across Requests **[HIGH]**
**Location:** `adapters/session.py:21-23, 30-32`
**Issue:** The `_redirect_count` instance variable on `SSRFSafeRedirectHandler` persists across ALL requests when using the shared `get_crawl_session()` singleton. After 30 successful redirects across ANY requests, subsequent redirects will fail with `TooManyRedirects`.
**Fix:** The counter should only reset in `__init__`, not after each redirect validation. Currently there is NO reset between requests - this is the bug. After 30 total redirects across all requests, subsequent redirects fail incorrectly.
**Verification:** Check that `_redirect_count` only resets in `__init__`, not after each redirect validation. The bug is that the counter is never reset between requests.

**Implementation Detail:**
- The `SSRFSafeRedirectHandler` is created once per session (line 63) and persists for the lifetime of the application
- `_redirect_count` accumulates across ALL requests using the shared session
- After 30 total redirects (not per-request), subsequent redirects will falsely fail
- To fix: Consider using thread-local storage for the counter, OR make the handler request-scoped, OR increase the threshold if 30 is too low for batch crawling

### CRIT-2: Duplicate `_finalize_subagent_result()` Function Definition **[HIGH]**
**Location:** `services/subagent/runner.py:277-328 and 498-501`
**Issue:** The function `_finalize_subagent_result` is defined TWICE in the same file. This is dead code - one definition is never used (or both may be called in different contexts).
**Fix:** Remove the duplicate definition. Keep the one that is actually used by `run_subagent_with_tools()`.

**Verification:** Search for all references to `_finalize_subagent_result` to determine which one is called.

### CRIT-3: No Adapter-Specific Config Validation **[HIGH]**
**Location:** `schemas/source.py:105-121`
**Issue:** `SourceConfig.config` is typed as `dict[str, Any]` with no validation. An RSS source with API-config fields will pass validation silently and fail at runtime.
**Fix:** Add a `field_validator` to `SourceConfig` that validates `config` against the appropriate adapter schema based on `type`.

**Implementation:**
```python
@field_validator("config")
@classmethod
def validate_adapter_config(cls, v, info):
    source_type = info.data.get("type")
    if source_type == "rss":
        return RSSConfig.model_validate(v).model_dump()
    elif source_type == "api":
        return APIConfig.model_validate(v).model_dump()
    elif source_type == "web":
        return WebConfig.model_validate(v).model_dump()
    return v
```
Note: `ADAPTER_CONFIGS` dict already exists at line 98-102 mapping type to config class.

---

## Phase 2: Medium Priority Items

### MED-1: sanitize_html Uses Bare `except Exception` **[MEDIUM]**
**Location:** `utils/text.py:100-103`
**Issue:** Catches ALL exceptions including `KeyboardInterrupt`, `SystemExit`. Should be more specific.
**Fix:** Change to `except (ValueError, Exception)` or use `html.parser.HTMLParseError` if available.
```python
except Exception:  # noqa: BLE001 - return original on any parse error
    return html
```
Note: BLE001 noqa is present, suggesting this is a known issue.

### MED-2: strip_tags Fallback Uses Bare Exception **[MEDIUM]**
**Location:** `utils/html.py:41`
**Issue:** Same issue - catches too broad exceptions in fallback path.
**Fix:** Change to specific exception types (e.g., `except (ValueError, Exception)`).

### MED-3: extract_text Silently Swallows trafilatura ImportError **[MEDIUM]**
**Location:** `utils/html.py:62-68`
**Issue:** `extract_text` silently passes on `ImportError` for trafilatura. This could mask installation issues or dependency problems.
**Fix:** At minimum, log a warning when trafilatura is not available. Consider raising an error if trafilatura is required.

### MED-4: truncate No Input Validation for Negative Length **[MEDIUM]**
**Location:** `utils/text.py:53-65`
**Issue:** If `length` is negative, `truncate("hello", -5)` returns `"..."` unexpectedly.
**Fix:** Add validation at start of function:
```python
if length < 0:
    raise ValueError("length must be non-negative")
```

### MED-5: utils/url.py Docstring Claims Pure But Has Global Mutable State **[MEDIUM]**
**Location:** `utils/url.py` (docstring at line 77)
**Issue:** Docstring claims "pure functions" but module has `_dns_executor`, `_dns_cache`, `_dns_cache_lock` global mutable state.
**Fix:** Update docstring to note that some functions have side effects (DNS caching with global state).

### MED-6: StageConfig Serves No Purpose **[MEDIUM]**
**Location:** `schemas/pipeline.py:140-141`
**Issue:** `StageConfig` only has `tools: list[str]` - it's a stub with no actual stage configuration. `PipelineRootConfig.stages` appears unused.
**Fix:** Either remove `StageConfig` and `stages` field from `PipelineRootConfig`, or expand it to contain meaningful configuration, or add a comment explaining why it's a stub.

### MED-7: ToolDefinition Schema Mismatch with Architecture **[MEDIUM]**
**Location:** `services/llm/base.py:80-86` / `architecture/subagent.md`
**Issue:** Architecture shows `cached: bool` field and `BaseModel`, but actual is a `@dataclass` with `required: list[str]` and `fn: Callable` fields. `cached` does not exist.
**Fix:** Update architecture doc to match actual ToolDefinition implementation.

### MED-8: Layer Violation in schemas/common.py **[MEDIUM]**
**Location:** `schemas/common.py`
**Issue:** `cached_config` functions import from `services.config_cache`, violating the rule that utils should be minimal dependencies.
**Fix:** This needs architectural decision - either move config caching to utils, or accept this as a necessary violation.

---

## Phase 3: Low Priority / Documentation Items

### LOW-1: NewsletterBrief Missing `preamble` and `footer` Fields **[LOW]**
**Location:** `schemas/llm_responses.py:142-148` vs `architecture/schemas.md`
**Issue:** Documentation describes `preamble: str` and `footer: str | None` fields, but actual `NewsletterBrief` only has `themes`, `highlights`, `connections`.
**Fix:** Update `architecture/schemas.md` to match actual implementation (remove undocumented fields).

### LOW-2: Tasks Schema Differs from Documentation **[LOW]**
**Location:** `schemas/tasks.py` vs `architecture/schemas.md`
**Issue:** `ProcessItemTask`, `GenerateNewsletterTask`, `SendEmailTask`, `CleanupArticleVersionsTask` all have field name differences from docs.
**Fix:** Update `architecture/schemas.md` to match actual task schemas.

### LOW-3: Source Health Tracking Documentation Incorrect **[LOW]**
**Location:** `architecture/adapters.md` vs `services/crawling.py`
**Issue:** Architecture doc claims adapters update `Source.consecutive_failures/successes`, but these are updated by `services/crawling.py`.
**Fix:** Update architecture documentation to clarify adapters only fetch/parse, `services/crawling.py` handles health tracking.

### LOW-4: WebAdapter "Retry-After Headers" Not Respected **[LOW]**
**Location:** `adapters/web.py:180-182`
**Issue:** WebAdapter does NOT read or respect `Retry-After` header. Uses fixed exponential backoff.
**Fix:** This is BY DESIGN per current implementation. Document this behavior or add header parsing if needed.

### LOW-5: APIAdapter Pagination Differs from Documentation **[LOW]**
**Location:** `adapters/api.py` vs architecture docs
**Issue:** Docs claim "Pagination support (cursor, offset, page-based)" but APIAdapter uses `item_url`, `list_items_path`, `list_method` pattern.
**Fix:** Update architecture docs to reflect actual APIAdapter implementation.

### LOW-6: Architecture Doc References Non-Existent schemas/article.py **[LOW]**
**Location:** `architecture/schemas.md`
**Issue:** Architecture doc references `schemas/article.py` which does not exist.
**Fix:** Update documentation to reference correct location or remove reference.

---

## Wave Organization for Parallelization

### Wave A: Critical Bugs (Can run in parallel)
| ID | Location | Issue | Implementation Notes |
|----|----------|-------|---------------------|
| CRIT-1 | adapters/session.py:21-32 | SSRFSafeRedirectHandler counter | Fix _redirect_count persistence across requests |
| CRIT-2 | services/subagent/runner.py:277-328, 498-501 | Duplicate function definition | Remove duplicate `_finalize_subagent_result` |
| CRIT-3 | schemas/source.py:105-121 | Adapter config validation | Add field_validator to SourceConfig |

### Wave B: Medium Priority Fixes (Parallelizable)
| ID | Location | Issue | Implementation Notes |
|----|----------|-------|---------------------|
| MED-1 | utils/text.py:100-103 | sanitize_html bare except | Use specific exception types |
| MED-2 | utils/html.py:41 | strip_tags bare except | Use specific exception types |
| MED-3 | utils/html.py:62-68 | extract_text ImportError | Log warning when trafilatura missing |
| MED-4 | utils/text.py:53-65 | truncate negative length | Add validation for negative length |
| MED-5 | utils/url.py (docstring) | Docstring purity claim | Update docstring to note side effects |
| MED-6 | schemas/pipeline.py:140-141 | StageConfig stub | Remove or expand StageConfig |
| MED-7 | services/llm/base.py:80-86 | ToolDefinition schema | Update architecture docs |
| MED-8 | schemas/common.py | Layer violation | Architectural decision needed |

### Wave C: Documentation Updates (Parallelizable)
| ID | Location | Issue | Implementation Notes |
|----|----------|-------|---------------------|
| LOW-1 | schemas/llm_responses.py vs arch | NewsletterBrief fields | Update architecture docs |
| LOW-2 | schemas/tasks.py vs arch | Tasks schema | Update architecture docs |
| LOW-3 | architecture/adapters.md | Source health tracking | Clarify adapters vs crawling.py |
| LOW-4 | adapters/web.py:180-182 | Retry-After header | Document BY DESIGN or implement |
| LOW-5 | adapters/api.py vs arch | APIAdapter pagination | Update architecture docs |
| LOW-6 | architecture/schemas.md | Non-existent article.py | Fix documentation reference |

---

## Previously Completed Items

The following items were in the prior plan and are now COMPLETED:

| Item | Status | Date Completed |
|------|--------|----------------|
| BUG-1.1 (idempotency_key) | COMPLETED | 2026-05-09 |
| BUG-1.3 (VALID_TRANSITIONS) | COMPLETED | 2026-05-09 |
| BUG-1.5 (Limiter model mismatch) | COMPLETED | 2026-05-09 |
| BUG-1.6 (provider_id None guard) | COMPLETED | 2026-05-09 |
| BUG-1.7 (SSRF redirect counter) | COMPLETED | 2026-05-09 |
| BUG-1.8 (Date parsing log) | COMPLETED | 2026-05-09 |
| BUG-1.9 (trafilatura ImportError) | COMPLETED | 2026-05-09 |
| BUG-1.10 (api_tokens_bp) | COMPLETED | 2026-05-09 |
| BUG-1.11 (JSON 401 for /api) | COMPLETED | 2026-05-09 |
| BUG-1.13 (Duplicate import) | COMPLETED | 2026-05-09 |
| TASK-2.12 (URL validation dedup) | COMPLETED | 2026-05-09 |
| TASK-2.14 (adapter_config decision) | N/A | - |
| TASK-2.15 (GIN index decision) | COMPLETED | 2026-05-09 |
| TASK-2.16 (IP binding) | COMPLETED | 2026-05-09 |
| TASK-3.15 (Two-tier retry) | COMPLETED | 2026-05-09 |
| TASK-3.16 (Degradation) | COMPLETED | 2026-05-09 |
| TASK-4.4 (YAML config) | COMPLETED | 2026-05-09 |

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

**Critical Bug Fixes:**
- `adapters/session.py` - SSRFSafeRedirectHandler (CRIT-1)
- `services/subagent/runner.py` - Duplicate function, subagent execution (CRIT-2)
- `schemas/source.py` - Source config schemas (CRIT-3)

**Medium Priority Fixes:**
- `utils/text.py` - Text utilities sanitize_html, truncate (MED-1, MED-4)
- `utils/html.py` - HTML utilities strip_tags, extract_text (MED-2, MED-3)
- `utils/url.py` - URL utilities docstring (MED-5)
- `schemas/pipeline.py` - StageConfig stub (MED-6)
- `services/llm/base.py` - ToolDefinition (MED-7)
- `schemas/common.py` - Layer violation (MED-8)

**Documentation Updates:**
- `architecture/schemas.md` - Schema documentation (LOW-1, LOW-2, LOW-6)
- `architecture/adapters.md` - Adapter documentation (LOW-3)
- `adapters/web.py` - WebAdapter retry behavior (LOW-4)
- `adapters/api.py` - APIAdapter pagination (LOW-5)

### Wave Execution Recommendation
For fastest execution, assign agents to waves as follows:
- **Agent 1**: Wave A (CRIT-1, CRIT-2, CRIT-3) - Critical bugs
- **Agent 2**: Wave B (MED-1 through MED-8) - Medium priority fixes
- **Agent 3**: Wave C (LOW-1 through LOW-6) - Documentation updates

---

## Progress Tracking

| Item | Status | Completed Date | Notes |
|------|--------|----------------|-------|
| CRIT-1 | PENDING | - | SSRFSafeRedirectHandler counter persists |
| CRIT-2 | PENDING | - | Duplicate function definition |
| CRIT-3 | PENDING | - | Adapter config validation |
| MED-1 | PENDING | - | sanitize_html bare except |
| MED-2 | PENDING | - | strip_tags bare except |
| MED-3 | PENDING | - | extract_text ImportError |
| MED-4 | PENDING | - | truncate negative length |
| MED-5 | PENDING | - | utils/url.py docstring |
| MED-6 | PENDING | - | StageConfig stub |
| MED-7 | PENDING | - | ToolDefinition schema |
| MED-8 | PENDING | - | Layer violation in schemas/common |
| LOW-1 | PENDING | - | NewsletterBrief docs |
| LOW-2 | PENDING | - | Tasks schema docs |
| LOW-3 | PENDING | - | Source health docs |
| LOW-4 | PENDING | - | Retry-After header |
| LOW-5 | PENDING | - | APIAdapter pagination docs |
| LOW-6 | PENDING | - | Non-existent schemas/article.py ref |

---

## New Findings for Future Agents

The following issues were discovered during this review session and added to the plan:

1. **CRIT-2 (NEW)**: Duplicate `_finalize_subagent_result()` function at lines 277-328 and 498-501 in `services/subagent/runner.py`. One is dead code.

2. **MED-3 (NEW)**: `extract_text()` in `utils/html.py:62-68` silently swallows trafilatura ImportError - could mask dependency issues.

3. **MED-8 (NEW)**: Layer violation - `schemas/common.py` imports from `services.config_cache`, which violates the principle that schemas/utils should have minimal dependencies.

---

*End of file*
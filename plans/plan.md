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
| MEDIUM | 6 | Documentation fixes, implementation improvements |
| LOW | 5 | Cleanup, minor documentation fixes |

### Items Already Completed (VERIFIED AS FIXED)
The following were marked as bugs but have been verified as FIXED:
- **CRIT-3**: urlparse NameError - import already exists in `routes/admin/api/articles.py`
- **CRIT-2**: newsletter_pipeline limiter slot leak - already uses `provider_id` from `get_provider_for_role()`
- **MED-1**: ThreadPoolExecutor shutdown - `atexit.register(shutdown_executor)` already in `services/subagent/config.py`
- **MED-2**: Tool registry race condition - `_TOOL_REGISTRY_LOCK` already protects initialization
- **MED-4**: `retry_stuck` missing SELECTING status - `SELECTING` already in the filter list
- **MED-9**: RSSAdapter session/handler - This is BY DESIGN (RSSAdapter needs its own session)
- **HIGH-2**: Source adapter config docs - This is a DOCUMENTATION task, not a code bug

---

## Phase 1: Critical Bug Fixes (REMAINING ITEMS)

### CRIT-1: SSRFSafeRedirectHandler Redirect Counter Accumulates Across Requests **[HIGH]**
**Location:** `adapters/session.py:21-23, 30-32`
**Issue:** The `_redirect_count` instance variable on `SSRFSafeRedirectHandler` persists across ALL requests when using the shared `get_crawl_session()` singleton. After 30 successful redirects across ANY requests, subsequent redirects will fail with `TooManyRedirects`.
**Fix:** The counter should NOT be reset after each successful validation. Instead, it should only be reset at the start of a new redirect chain (i.e., in `__init__`). Remove the reset at line 41.
**Verification:** Check that `_redirect_count` only resets in `__init__`, not after each redirect validation.

### CRIT-2: Tool Results Not Re-injected in Tool Loop **[HIGH]**
**Location:** `services/subagent/runner.py:384-407`
**Issue:** The architecture doc states tool results should be added back to messages for follow-up LLM calls, but `run_subagent_with_tools()` only makes a single `chat_with_tools()` call. Tool results are not appended to `messages` before subsequent iterations.
**Fix:** Either implement the documented multi-step message injection pattern, or update architecture to reflect actual single-call behavior. This is a design decision - document which behavior is correct.
**Note:** This may be intentional (single-call tool execution). Verify with architecture docs.

### CRIT-3: No Adapter-Specific Config Validation **[HIGH]**
**Location:** `schemas/source.py:285-287`
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

---

## Phase 2: Medium Priority Items (REMAINING ITEMS)

### MED-1: sanitize_html Uses Bare `except Exception` **[MEDIUM]**
**Location:** `utils/text.py:102`
**Issue:** Catches ALL exceptions including `KeyboardInterrupt`, `SystemExit`. Should be more specific.
**Fix:** Change to `except (ValueError, Exception)` for HTMLParseError or similar specific exception types.
```python
except Exception:
    return html
```
Note: BLE001 noqa is present, suggesting this is a known issue. Consider using `html.parser.HTMLParseError` if available.

### MED-2: strip_tags Fallback Uses Bare Exception **[MEDIUM]**
**Location:** `utils/html.py:41`
**Issue:** Same issue - catches too broad exceptions in fallback path.
**Fix:** Change to specific exception types (e.g., `except (ValueError, Exception)`).

### MED-3: No Input Validation for Negative Length in truncate **[MEDIUM]**
**Location:** `utils/text.py:53`
**Issue:** If `length` is negative, `truncate("hello", -5)` returns `"..."` unexpectedly.
**Fix:** Add validation at start of function:
```python
if length < 0:
    raise ValueError("length must be non-negative")
```

### MED-4: utils/url.py Docstring Claims Pure But Has Global Mutable State **[MEDIUM]**
**Location:** `utils/url.py:77` (docstring)
**Issue:** Docstring claims "pure functions" but module has `_dns_executor`, `_dns_cache`, `_dns_cache_lock` global mutable state.
**Fix:** Update docstring at line 77 to note that some functions have side effects (DNS caching).

### MED-5: StageConfig Serves No Purpose **[LOW]**
**Location:** `schemas/pipeline.py:140-141`
**Issue:** `StageConfig` only has `tools: list[str]` - it's a stub with no actual stage configuration. `PipelineRootConfig.stages` appears unused.
**Fix:** Either remove `StageConfig` and `stages` field from `PipelineRootConfig`, or expand it to contain meaningful configuration, or add a comment explaining why it's a stub.

### MED-6: ToolDefinition Schema Mismatch with Architecture **[LOW]**
**Location:** `services/llm/base.py:80-86` / `architecture/subagent.md`
**Issue:** Architecture shows `cached: bool` field and `BaseModel`, but actual is a `@dataclass` with `required: list[str]` and `fn: Callable` fields. `cached` does not exist.
**Fix:** Update architecture doc to match actual ToolDefinition implementation, or add `cached` field to ToolDefinition if needed.

---

## Phase 3: Low Priority / Documentation Items (REMAINING ITEMS)

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

---

## Wave Organization for Parallelization

### Wave A: Critical Bugs (Can run in parallel)
| ID | Location | Issue | Status |
|----|----------|-------|--------|
| CRIT-1 | adapters/session.py:21-23 | SSRFSafeRedirectHandler counter | PENDING |
| CRIT-2 | services/subagent/runner.py:384-407 | Tool results not re-injected | DECISION |
| CRIT-3 | schemas/source.py:285-287 | Adapter config validation | PENDING |

### Wave B: Medium Priority Fixes (Parallelizable)
| ID | Location | Issue | Status |
|----|----------|-------|--------|
| MED-1 | utils/text.py:102 | sanitize_html bare except | PENDING |
| MED-2 | utils/html.py:41 | strip_tags bare except | PENDING |
| MED-3 | utils/text.py:53 | truncate negative length | PENDING |
| MED-4 | utils/url.py:77 | Docstring purity claim | PENDING |
| MED-5 | schemas/pipeline.py:140-141 | StageConfig stub | PENDING |
| MED-6 | services/llm/base.py:80-86 | ToolDefinition schema | PENDING |

### Wave C: Documentation Updates
| ID | Location | Issue | Status |
|----|----------|-------|--------|
| LOW-1 | schemas/llm_responses.py:142-148 | NewsletterBrief fields | PENDING |
| LOW-2 | schemas/tasks.py | Tasks schema | PENDING |
| LOW-3 | architecture/adapters.md | Source health tracking | PENDING |
| LOW-4 | adapters/web.py:180-182 | Retry-After header | BY DESIGN |
| LOW-5 | adapters/api.py | Pagination | PENDING |

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
- `adapters/session.py` - SSRFSafeRedirectHandler (CRIT-1)
- `services/subagent/runner.py` - Subagent execution (CRIT-2)
- `schemas/source.py` - Source config schemas (CRIT-3)
- `utils/text.py` - Text utilities (MED-1, MED-3)
- `utils/html.py` - HTML utilities (MED-2)
- `utils/url.py` - URL utilities (MED-4)
- `schemas/pipeline.py` - Pipeline schemas (MED-5)
- `services/llm/base.py` - ToolDefinition (MED-6)
- `architecture/` - Architecture documentation (LOW-1 through LOW-5)

### Wave Execution Recommendation
For fastest execution, assign agents to waves as follows:
- **Agent 1**: Wave A (CRIT-1, CRIT-2, CRIT-3)
- **Agent 2**: Wave B (MED-1 through MED-6)
- **Agent 3**: Wave C (LOW-1 through LOW-5)

---

## Progress Tracking

| Item | Status | Completed Date | Notes |
|------|--------|----------------|-------|
| CRIT-1 | PENDING | - | SSRFSafeRedirectHandler counter |
| CRIT-2 | DECISION | - | Tool results re-injection - decide if fix or docs |
| CRIT-3 | PENDING | - | Adapter config validation |
| MED-1 | PENDING | - | sanitize_html bare except |
| MED-2 | PENDING | - | strip_tags bare except |
| MED-3 | PENDING | - | truncate negative length |
| MED-4 | PENDING | - | utils/url.py docstring |
| MED-5 | PENDING | - | StageConfig stub |
| MED-6 | PENDING | - | ToolDefinition schema |
| LOW-1 | PENDING | - | NewsletterBrief docs |
| LOW-2 | PENDING | - | Tasks schema docs |
| LOW-3 | PENDING | - | Source health docs |
| LOW-4 | BY DESIGN | - | Retry-After header |
| LOW-5 | PENDING | - | APIAdapter pagination docs |

---

*End of file*
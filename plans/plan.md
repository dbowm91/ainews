# AINews Implementation Plan

**Status:** IN PROGRESS (Consolidated from architecture review - 2026-05-22)
**Last Updated:** 2026-05-22

---

## Overview

This plan consolidates findings from 10 architecture review files across all modules. Items are organized into waves based on priority and parallelization potential.

---

## Wave 1: CRITICAL (Must Fix)

### SUB-1: Self-Correction Never Executes
**Module:** Services / Subagent
**Location:** `services/subagent/runner.py:428`
**Issue:** `ValidationError` is NOT in `retryable_exceptions` tuple. The self-correction code block (lines 393-409) raises to trigger retry, but `_retry_with_backoff` won't retry on `ValidationError`.

**Fix:** Add `ValidationError` to `retryable_exceptions` tuple at line 428:
```python
retryable_exceptions=(ProviderTimeoutError, ValidationError, TimeoutError, ConnectionError),
```

### TASKS-1: Newsletter Lock Release Scope Bug
**Module:** Tasks
**Location:** `tasks/newsletter.py:466-472`
**Issue:** `lock_key` is a local variable inside `_check_newsletter_lock` function (line 398) but the `finally` block in `_generate_daily_newsletters_core` references an undefined `lock_key`.

**Fix:** Modify `_check_newsletter_lock` to return `lock_key` as third return value:
```python
# At line 409, change:
return lock_status, None
# To:
return lock_status, lock_key, None

# Update caller at line 419:
lock_status, lock_key, skip_result = _check_newsletter_lock(redis_client, task_id)
```

### SCHEMA-1: search.py Missing from Documentation
**Module:** Schemas
**Location:** `architecture/schemas.md`
**Issue:** `schemas/search.py` exists but is not documented. `SearchConfig` schema is missing.

**Fix:** Add to file inventory and document `SearchConfig`:
```python
# schemas/search.py exports:
from schemas.search import SearchConfig, SearchResult, SemanticSearchConfig
```

---

## Wave 2: HIGH Priority

### SUB-2: run_subagent_chain Ignores steps Parameter
**Module:** Services / Subagent
**Location:** `services/subagent/chain.py:36-57`
**Issue:** Function accepts `steps: list[dict]` parameter but completely ignores it. Steps come only from `chain_config.steps`.

**Fix:** Use passed steps if provided, fall back to config:
```python
def run_subagent_chain(..., steps: list[dict] | None = None, ...):
    ...
    step_list = steps if steps is not None else chain_config.steps
    for i, step_config in enumerate(step_list[:max_length]):
```

### SCHEMA-2: APIConfig request_timeout Missing from Doc
**Module:** Schemas
**Location:** `schemas/source.py:53`, `architecture/schemas.md`
**Issue:** `request_timeout: int = 15` field exists but is not documented.

**Fix:** Add to APIConfig documentation:
```python
request_timeout: int = 15  # Request timeout in seconds
```

### SCHEMA-3: APIConfig auth_header Description Misleading
**Module:** Schemas
**Location:** `schemas/source.py:56`
**Issue:** Comment says "Header name for Bearer auth" - unclear.

**Fix:** Clarify comment:
```python
auth_header: str = "Authorization"  # Header name for Bearer auth token
```

### MODELS-1: TrendMemory.topic Size Mismatch
**Module:** Models
**Location:** `models/context.py:31`, `architecture/models.md`
**Issue:** Code uses `String(128)` but documentation says `String(200)`.

**Fix:** Update architecture/models.md to reflect actual code: `topic = db.Column(db.String(128), ...)`

### MODELS-2: TrendMemory Fields Undocumented
**Module:** Models
**Location:** `models/context.py:33,37,38`, `architecture/models.md`
**Issue:** `importance`, `expires_at`, `last_consolidated_at` fields exist but are not documented.

**Fix:** Add to TrendMemory documentation in architecture/models.md.

### ADPT-1: SSRFSafeRedirectHandler Interface Concern
**Module:** Adapters
**Location:** `adapters/session.py:37`
**Issue:** `__call__` signature is `(self, request: requests.Request, response: requests.Response, **kwargs) -> requests.PreparedRequest | None`. Documentation质疑 whether this properly intercepts all redirects.

**Verification:** This signature matches the standard `requests` redirect handler interface. Verify works with actual redirect scenarios.

### ADPT-2: APIAdapter Pagination Off-by-One
**Module:** Adapters
**Location:** `adapters/api.py:85`
**Issue:** First page already uses `page=2` - pagination starts at page 2 instead of page 1.

**Fix:** Review pagination logic at line 85 and correct if needed.

---

## Wave 3: MEDIUM Priority

### TASKS-2: Edit Stage Missing _dispatch_next
**Module:** Tasks
**Location:** `tasks/edit.py:185,205`
**Issue:** When validation fails and `_should_route_to_review` returns True, the function returns `{"status": "review"}` but never calls `_dispatch_next()` to advance the pipeline.

**Fix:** Add `_dispatch_next` before returning review status at lines 185 and 205:
```python
if _should_route_to_review(article):
    _transition_article_status(article, PipelineStatus.REVIEW)
    if run_id:
        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)
    try:
        db.session.commit()
    ...
```

### TASKS-3: Error Dicts Not Logged/Metrics
**Module:** Tasks
**Location:** `tasks/pipeline.py:390-391`
**Issue:** `_run_stage_core()` returns error dicts without logging or metrics.

**Fix:** Add logging before returning error dicts:
```python
if error_dict:
    logger.error("Stage %s failed for article %d: %s", stage, article_id, error_dict.get("error"))
return error_dict
```

### SUB-3: Chain Uses provider.chat() Not chat_with_tools
**Module:** Services / Subagent
**Location:** `services/subagent/chain.py:118-125`
**Issue:** Chain execution doesn't support tools - uses `provider.chat()` instead of `chat_with_tools()`.

**Fix:** Either document that chains don't support tools, OR implement `chat_with_tools` support.

### SUB-4: Layering Violation in tools.py (Documented)
**Module:** Services / Subagent
**Location:** `services/subagent/tools.py:12-16,105-106,128-129,146-147`
**Issue:** `tools.py` imports directly from `models` and `extensions` - violates layering rules.

**Status:** Documented in AGENTS.md as known issue. Long-term fix: create service-layer helpers.

### SVC-1: DeepSeek Search Provider Missing from Doc
**Module:** Services
**Location:** `architecture/services.md`
**Issue:** DeepSeek search provider exists at `services/search/duckduckgo.py`, `services/search/google.py`, `services/search/searxng.py`, `services/search/hybrid.py` (enabled), `services/search/sqlite_fts.py`, `services/search/deepseek.py` - but not documented.

**Fix:** Add DeepSeek to search provider table in architecture/services.md.

### SCHEMA-4: ReviewConfig Default Inconsistent
**Module:** Schemas
**Location:** `schemas/pipeline.py:38-40`
**Issue:** `auto_publish_threshold` defaults to `None` but description says "Default: 80".

**Fix:** Either change default to `80` or fix description to say "Default: None (disabled)".

### SCHEMA-5: ProcessItemTask Structure Inaccurate
**Module:** Schemas
**Location:** `schemas/tasks.py:87-117`, `architecture/schemas.md`
**Issue:** Documentation doesn't match actual field list.

**Fix:** Update architecture/schemas.md with accurate ProcessItemTask fields.

### SCHEMA-6: Layer Violation in common.py Not Documented
**Module:** Schemas
**Location:** `schemas/common.py:75,89`
**Issue:** Imports from `services.config_cache` - intentional violation but not documented.

**Fix:** Document explicitly in architecture rather than hiding in code comments.

### ROUTES-1: Duplicate /admin/metrics Entry
**Module:** Routes
**Location:** `architecture/routes.md:78-79`
**Issue:** Second entry should be `/admin/verify-2fa`, not `/admin/metrics`.

**Fix:** Correct the duplicate entry in documentation.

### ROUTES-2: Misleading api_tokens_bp Documentation
**Module:** Routes
**Location:** `architecture/routes.md:224-241`
**Issue:** Duplicate code block; unclear about registration in app.py.

**Fix:** Remove duplicate code block; clarify registration.

### ROUTES-3: Missing /admin/pipelines/trigger-crawl
**Module:** Routes
**Location:** `routes/admin/pipelines.py:84`
**Issue:** Route exists in code but not documented.

**Fix:** Add to architecture/routes.md.

### ROUTES-4: Missing /admin/articles/<id>/original
**Module:** Routes
**Location:** `routes/admin/articles.py:426`
**Issue:** Route exists in code but not documented.

**Fix:** Add to architecture/routes.md.

### ROUTES-5: Missing /admin/articles/<id>/versions/<version_id>/rollback
**Module:** Routes
**Location:** `routes/admin/articles.py:458`
**Issue:** Route exists in code but not documented.

**Fix:** Add to architecture/routes.md.

### ROUTES-6: Missing /admin/api/trend-memory/semantic-search
**Module:** Routes
**Location:** `routes/admin/trend_memory.py:117`
**Issue:** Route exists in code but not documented.

**Fix:** Add to architecture/routes.md.

### ROUTES-7: Missing /admin/topic-notes/row/<topic>
**Module:** Routes
**Location:** `routes/admin/topic_notes.py:172`
**Issue:** Route exists in code but not documented.

**Fix:** Add to architecture/routes.md.

### ROUTES-8: Missing /admin/shares/<id>/edit-form and /admin/shares/<id>/row
**Module:** Routes
**Location:** `routes/admin/shares.py:142,152`
**Issue:** Routes exist in code but not documented.

**Fix:** Add to architecture/routes.md.

---

## Wave 4: LOW Priority (Documentation & Polish)

### UTIL-1: Missing __all__ Exports
**Module:** Utils
**Location:** `utils/url.py:21-28`
**Issue:** `__all__` exports 6 items but only 4 are functions. `TRACKING_PARAMS` is a constant, `UnsafeURLError` is an exception class.

**Fix:** Document that `__all__` includes types alongside functions, or split into separate exports for clarity.

### UTIL-2: Missing __init__.py in utils/
**Module:** Utils
**Location:** `utils/__init__.py`
**Issue:** All other packages have `__init__.py` but `utils/` doesn't.

**Fix:** Add `__init__.py` or document why intentional.

### UTIL-3: TRACKING_PARAMS Not in File Inventory
**Module:** Utils
**Location:** `architecture/utils.md`
**Issue:** `TRACKING_PARAMS` constant not listed in file inventory.

**Fix:** Add to documentation.

### TASKS-4: AGENTS.override.md Outdated
**Module:** Tasks
**Location:** `tasks/AGENTS.override.md:26-36`
**Issue:** Documentation about retry.py imports may be outdated.

**Fix:** Review and update.

### TASKS-5: Task Name Discrepancy
**Module:** Tasks
**Location:** `retry.py`
**Issue:** Documented as `retry_stuck_articles` vs actual task name `retry_stuck`.

**Fix:** Update documentation to match actual task name.

### SUB-5: Documentation Clarity for Schema Definitions
**Module:** Services / Subagent
**Location:** `architecture/subagent.md:115-125`
**Issue:** `SubagentChainStep` and `SubagentChainConfig` location could be clearer.

**Fix:** Improve presentation in architecture documentation.

### SVC-2: circuit_breaker.py Not in File Inventory
**Module:** Services
**Location:** `architecture/services.md`
**Issue:** `services/circuit_breaker.py` exists but not listed.

**Fix:** Add to file inventory.

### SVC-3: search/ Subdirectory Structure Not Documented
**Module:** Services
**Location:** `architecture/services.md`
**Issue:** Search provider organization not clearly documented.

**Fix:** Add subdirectory listing for search providers.

### SCHEMA-7: TopicMatchConfig Not Documented
**Module:** Schemas
**Location:** `schemas/source.py:23-27`, `architecture/schemas.md`
**Issue:** `TopicMatchConfig` exists but not documented.

**Fix:** Add to source.py documentation section.

### SCHEMA-8: admin.py Depends on constants.py
**Module:** Schemas
**Location:** `schemas/admin.py:48-49`
**Issue:** Schema validators depend on `constants.VALID_PIPELINE_STATUSES` but not documented.

**Fix:** Document the dependency.

### MODELS-3: Article.created_at Only Composite Index
**Module:** Models
**Location:** `models/article.py:68`
**Issue:** Queries on `created_at` alone may use full scan.

**Fix:** Optional: Add standalone index on `created_at` if performance is critical.

### MODELS-4: PipelineRun.started_at Missing Index
**Module:** Models
**Location:** `models/pipeline.py:20`
**Issue:** Sorting by start time may be slower without index.

**Fix:** Optional: Add index if sorting by started_at is frequent.

### OVERVIEW-1: utils/url.py Not Pure
**Module:** Architecture
**Location:** `utils/url.py:130-194`, `architecture/overview.md`
**Issue:** Global mutable state (`_dns_cache`, `_dns_executor`) not documented.

**Fix:** Add note to "Known Architecture Notes": `utils/url.py Not Pure` - global DNS cache and executor.

### OVERVIEW-2: TYPE_CHECKING Imports Not Documented
**Module:** Architecture
**Location:** `architecture/overview.md`
**Issue:** Layering rules don't document TYPE_CHECKING exception.

**Fix:** Add note: Services may use TYPE_CHECKING imports from adapters for type hints only.

---

## Already Fixed (Verification Complete)

The following items were verified as already fixed in the codebase:

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| APIAdapter item_url | `adapters/api.py:63-71` | FIXED | Now extracts ID before calling `_fetch_item` |
| Article.updated_at index | `models/article.py:48` | FIXED | Index exists |
| services/crawling.py TYPE_CHECKING | `services/crawling.py:15` | FIXED | Uses TYPE_CHECKING block |
| SSRFSafeRedirectHandler interface | `adapters/session.py:37` | VERIFIED | Signature matches requests interface |
| Schema SearchConfig | `schemas/search.py` | EXISTS | File exists, just missing from docs |
| Workers health endpoint | `routes/admin/api/health.py:54` | EXISTS | Endpoint exists |
| Task status endpoint | `routes/admin/api/health.py:102` | EXISTS | Endpoint exists |
| Newsletters stats endpoint | `routes/admin/newsletters.py:177` | EXISTS | Endpoint exists |
| Newsletter preview endpoint | `routes/admin/newsletters.py:221` | EXISTS | Endpoint exists |

---

## Implementation Notes

### Parallelization Opportunities

**Wave 1-2 items can be parallelized across modules:**
- SUB-1 (runner.py) and SUB-2 (chain.py) are independent subagent fixes
- SCHEMA-1, SCHEMA-2, SCHEMA-3 can be done in parallel (schema docs)
- MODELS-1, MODELS-2 are documentation fixes (architecture/models.md)
- ADPT-1, ADPT-2 are independent adapter fixes

**Wave 3 has the most parallelization potential:**
- TASKS-2 (edit.py) and TASKS-3 (pipeline.py) are independent task fixes
- ROUTES-1 through ROUTES-8 are all documentation fixes that can run in parallel
- SCHEMA-4, SCHEMA-5, SCHEMA-6 are independent schema doc fixes
- SVC-1, SVC-2, SVC-3 are service documentation fixes

### Known Intentional Layering Violations

The following are documented as intentional and should NOT be "fixed":
- `services/crawling.py` uses TYPE_CHECKING import from `adapters.base` - documented in AGENTS.md
- `tasks/crawl.py` imports directly from `adapters.base` - documented in AGENTS.md
- `schemas/common.py` imports from `services.config_cache` - documented with inline comment
- `services/subagent/tools.py` imports from `models` and `extensions` - documented in AGENTS.md

---

*Plan consolidated from architecture review findings - 2026-05-22*
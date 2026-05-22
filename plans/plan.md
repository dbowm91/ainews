# AINews Implementation Plan

**Status:** IN PROGRESS (Consolidated from architecture review - 2026-05-22)
**Last Updated:** 2026-05-22

---

## Overview

This plan consolidates findings from 10 architecture review files across all modules. Items are organized into waves based on priority and parallelization potential. Future agents should read this plan before implementing any items and refer to the original architecture documents for context.

---

## Wave 1: CRITICAL (Must Fix - 4 items)

These bugs cause functional failures and must be fixed before any other work.

### SUB-1: Self-Correction Never Executes
**Module:** Services / Subagent
**Location:** `services/subagent/runner.py:428`
**Issue:** `ValidationError` is NOT in `retryable_exceptions` tuple. The self-correction code block (lines 393-409) raises to trigger retry, but `_retry_with_backoff` won't retry on `ValidationError`.

**Fix:** Add `ValidationError` to `retryable_exceptions` tuple at line 428:
```python
retryable_exceptions=(ProviderTimeoutError, ValidationError, TimeoutError, ConnectionError),
```

**Verification:**
```bash
ruff check services/subagent/runner.py
python -m pytest tests/test_subagent*.py -v -k "self_correct"  # if exists
```

---

### TASKS-1: Newsletter Lock Release Scope Bug
**Module:** Tasks
**Location:** `tasks/newsletter.py:398-409, 466-472`
**Issue:** `lock_key` is a local variable inside `_check_newsletter_lock` function (line 398: `lock_key = "ainews:newsletter_lock"`) but the `finally` block in `_generate_daily_newsletters_core` (line 470) references `lock_key` which is undefined.

**Fix:** Modify `_check_newsletter_lock` to return `lock_key` as third return value:
```python
# At line 409, change:
return lock_status, None
# To:
return lock_status, lock_key, None

# Update caller at line 419:
lock_status, lock_key, skip_result = _check_newsletter_lock(redis_client, task_id)
```

**Verification:** Run newsletter generation twice in succession - second run should not skip due to stale lock.

---

### SUB-2: run_subagent_chain Ignores steps Parameter
**Module:** Services / Subagent
**Location:** `services/subagent/chain.py:62`
**Issue:** Function accepts `steps: list[dict]` parameter but completely ignores it. Steps come only from `chain_config.steps`.

**Fix:** Use passed steps if provided, fall back to config:
```python
# Line 62, change:
for i, step_config in enumerate(chain_config.steps[:max_length]):
# To:
step_list = steps if steps is not None else chain_config.steps
for i, step_config in enumerate(step_list[:max_length]):
```

**Verification:**
```bash
ruff check services/subagent/chain.py
mypy services/subagent/chain.py --ignore-missing-imports
```

---

### TASKS-2: Edit Stage Missing _dispatch_next
**Module:** Tasks
**Location:** `tasks/edit.py:185,205`
**Issue:** When `_should_route_to_review()` returns True, the function transitions status to `REVIEW` but does NOT call `_dispatch_next()`. Other stages (select, research, write) all call `_dispatch_next` after transitioning to `REVIEW`.

**Fix:** Add `_dispatch_next` before returning review status at lines 185 and 205:
```python
# After _transition_article_status and db.session.commit at line 192/196:
if run_id:
    _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)
```

Compare with `tasks/research.py:230` and `tasks/write.py:153` for correct pattern.

**Verification:** Articles routed to review from edit stage should appear in review queue.

---

## Wave 2: HIGH Priority (6 items)

### MODELS-1: TrendMemory.topic Size Mismatch
**Module:** Models
**Location:** `models/context.py:31`, `architecture/models.md`
**Issue:** Documentation says `String(200)` but code uses `String(128)`.
**Fix:** Update `architecture/models.md` to reflect actual code: `topic = db.Column(db.String(128), ...)`

---

### MODELS-2: TrendMemory Fields Undocumented
**Module:** Models
**Location:** `models/context.py:33,37,38`, `architecture/models.md`
**Issue:** `importance`, `expires_at`, `last_consolidated_at` fields exist but not documented.
**Fix:** Add to TrendMemory documentation in `architecture/models.md`.

---

### SCHEMA-1: search.py Missing from Documentation
**Module:** Schemas
**Location:** `architecture/schemas.md`
**Issue:** `schemas/search.py` exists but not documented.
**Fix:** Add to file inventory in `architecture/schemas.md`:
```python
# schemas/search.py exports:
from schemas.search import SearchConfig, SearchResult, SemanticSearchConfig
```

---

### SCHEMA-2: APIConfig request_timeout Missing from Doc
**Module:** Schemas
**Location:** `schemas/source.py:53`, `architecture/schemas.md`
**Issue:** `request_timeout: int = 15` field exists but not documented.
**Fix:** Add to APIConfig documentation in `architecture/schemas.md`.

---

### SCHEMA-3: APIConfig auth_header Description Misleading
**Module:** Schemas
**Location:** `schemas/source.py:56`
**Issue:** Comment says "Header name for Bearer auth" - unclear.
**Fix:** Clarify comment:
```python
auth_header: str = "Authorization"  # Header name for Bearer auth token
```

---

### ADPT-1: SSRFSafeRedirectHandler Interface Concern
**Module:** Adapters
**Location:** `adapters/session.py:37`
**Issue:** `__call__` signature `(self, request, response, **kwargs)` may not match `requests.Session` expectations.
**Status:** Verified works with requests library in practice.
**Fix:** Document verification result in `architecture/adapters.md`.

---

## Wave 3: MEDIUM Priority (12 items)

### ADPT-2: APIAdapter Pagination Off-by-One
**Module:** Adapters
**Location:** `adapters/api.py:85`
**Issue:** First page already uses `page=2` - pagination starts at page 2 instead of page 1.
**Fix:** Review pagination logic at line 85 and correct if needed.

---

### SVC-1: DeepSeek Search Provider Missing from Doc
**Module:** Services
**Location:** `architecture/services.md`
**Issue:** DeepSeek search provider exists at `services/search/deepseek.py` but not documented.
**Fix:** Add DeepSeek to search provider table in `architecture/services.md`.

---

### SVC-2: circuit_breaker.py Not in File Inventory
**Module:** Services
**Location:** `architecture/services.md`
**Issue:** `services/circuit_breaker.py` exists but not listed.
**Fix:** Add to file inventory in `architecture/services.md`.

---

### SVC-3: search/ Subdirectory Structure Not Documented
**Module:** Services
**Location:** `architecture/services.md`
**Issue:** Search provider organization not clearly documented.
**Fix:** Add subdirectory listing for search providers in `architecture/services.md`.

---

### SCHEMA-4: ReviewConfig Default Inconsistent
**Module:** Schemas
**Location:** `schemas/pipeline.py:38-40`
**Issue:** `auto_publish_threshold` defaults to `None` but description says "Default: 80".
**Fix:** Update description to say "Default: None (disabled)" or change default to `80`.

---

### SCHEMA-5: ProcessItemTask Structure Inaccurate
**Module:** Schemas
**Location:** `schemas/tasks.py:87-117`, `architecture/schemas.md`
**Issue:** Documentation doesn't match actual field list.
**Fix:** Update `architecture/schemas.md` with accurate ProcessItemTask fields.

---

### SCHEMA-6: Layer Violation in common.py Not Documented
**Module:** Schemas
**Location:** `schemas/common.py:75,89`
**Issue:** Imports from `services.config_cache` - intentional violation but not documented.
**Fix:** Document explicitly in `architecture/schemas.md`.

---

### ROUTES-1: Duplicate /admin/metrics Entry
**Module:** Routes
**Location:** `architecture/routes.md:78-79`
**Issue:** Second entry should be `/admin/verify-2fa`, not `/admin/metrics`.
**Fix:** Correct the duplicate entry in documentation.

---

### ROUTES-2: Misleading api_tokens_bp Documentation
**Module:** Routes
**Location:** `architecture/routes.md:224-241`
**Issue:** Duplicate code block; unclear about registration in app.py.
**Fix:** Remove duplicate code block; clarify registration.

---

### ROUTES-3: Missing /admin/pipelines/trigger-crawl
**Module:** Routes
**Location:** `routes/admin/pipelines.py:84`
**Issue:** Route exists in code but not documented.
**Fix:** Add to `architecture/routes.md`.

---

### ROUTES-4: Missing /admin/articles/<id>/original
**Module:** Routes
**Location:** `routes/admin/articles.py:426`
**Issue:** Route exists in code but not documented.
**Fix:** Add to `architecture/routes.md`.

---

### ROUTES-5: Missing /admin/articles/<id>/versions/<version_id>/rollback
**Module:** Routes
**Location:** `routes/admin/articles.py:458`
**Issue:** Route exists in code but not documented.
**Fix:** Add to `architecture/routes.md`.

---

### ROUTES-6: Missing /admin/api/trend-memory/semantic-search
**Module:** Routes
**Location:** `routes/admin/trend_memory.py:117`
**Issue:** Route exists in code but not documented.
**Fix:** Add to `architecture/routes.md`.

---

### ROUTES-7: Missing /admin/topic-notes/row/<topic>
**Module:** Routes
**Location:** `routes/admin/topic_notes.py:172`
**Issue:** Route exists in code but not documented.
**Fix:** Add to `architecture/routes.md`.

---

### ROUTES-8: Missing /admin/shares/<id>/edit-form and /admin/shares/<id>/row
**Module:** Routes
**Location:** `routes/admin/shares.py:142,152`
**Issue:** Routes exist in code but not documented.
**Fix:** Add to `architecture/routes.md`.

---

## Wave 4: LOW Priority - Documentation & Polish (13 items)

### UTIL-1: Missing __all__ Exports
**Module:** Utils
**Location:** `utils/url.py:21-28`
**Issue:** `__all__` exports 6 items but only 4 are functions. `TRACKING_PARAMS` is a constant, `UnsafeURLError` is an exception class.
**Fix:** Document that `__all__` includes types alongside functions, or split into separate exports.

---

### UTIL-2: Missing __init__.py in utils/
**Module:** Utils
**Location:** `utils/__init__.py`
**Issue:** All other packages have `__init__.py` but `utils/` has empty one (0 bytes).
**Fix:** Either add content or document why intentionally empty.

---

### UTIL-3: TRACKING_PARAMS Not in File Inventory
**Module:** Utils
**Location:** `architecture/utils.md`
**Issue:** `TRACKING_PARAMS` constant not listed in file inventory.
**Fix:** Add to documentation.

---

### TASKS-4: AGENTS.override.md Outdated
**Module:** Tasks
**Location:** `tasks/AGENTS.override.md:26-36`
**Issue:** Documentation about retry.py imports may be outdated.
**Fix:** Review and update.

---

### TASKS-5: Task Name Discrepancy
**Module:** Tasks
**Location:** `retry.py`
**Issue:** Documented as `retry_stuck_articles` vs actual task name `retry_stuck`.
**Fix:** Update documentation to match actual task name (`retry_stuck`).

---

### SUB-3: Chain Uses provider.chat() Not chat_with_tools
**Module:** Services / Subagent
**Location:** `services/subagent/chain.py:118-125`
**Issue:** Chain execution doesn't support tools - uses `provider.chat()` instead of `chat_with_tools()`.
**Fix:** Either document that chains don't support tools, OR implement `chat_with_tools` support.

---

### SUB-4: Layering Violation in tools.py (Documented)
**Module:** Services / Subagent
**Location:** `services/subagent/tools.py:12-16,105-106,128-129,146-147`
**Issue:** `tools.py` imports directly from `models` and `extensions` - violates layering rules.
**Status:** Documented in AGENTS.md as known issue. Long-term fix: create service-layer helpers.
**Fix:** No immediate fix needed - documented as intentional.

---

### SUB-5: Documentation Clarity for Schema Definitions
**Module:** Services / Subagent
**Location:** `architecture/subagent.md:115-125`
**Issue:** `SubagentChainStep` and `SubagentChainConfig` location could be clearer.
**Fix:** Improve presentation in architecture documentation.

---

### SCHEMA-7: TopicMatchConfig Not Documented
**Module:** Schemas
**Location:** `schemas/source.py:23-27`, `architecture/schemas.md`
**Issue:** `TopicMatchConfig` exists but not documented.
**Fix:** Add to source.py documentation section.

---

### SCHEMA-8: admin.py Depends on constants.py
**Module:** Schemas
**Location:** `schemas/admin.py:48-49`
**Issue:** Schema validators depend on `constants.VALID_PIPELINE_STATUSES` but not documented.
**Fix:** Document the dependency.

---

### MODELS-3: Article.created_at Only Composite Index
**Module:** Models
**Location:** `models/article.py:68`
**Issue:** Queries on `created_at` alone may use full scan.
**Fix:** Optional: Add standalone index on `created_at` if performance is critical.

---

### MODELS-4: PipelineRun.started_at Missing Index
**Module:** Models
**Location:** `models/pipeline.py:20`
**Issue:** Sorting by start time may be slower without index.
**Fix:** Optional: Add index if sorting by `started_at` is frequent.

---

### OVERVIEW-1: utils/url.py Not Pure
**Module:** Architecture
**Location:** `utils/url.py:130-194`, `architecture/overview.md`
**Issue:** Global mutable state (`_dns_cache`, `_dns_executor`) not documented.
**Fix:** Add note to `architecture/overview.md`: "utils/url.py Not Pure - global DNS cache and executor".

---

### OVERVIEW-2: TYPE_CHECKING Imports Not Documented
**Module:** Architecture
**Location:** `architecture/overview.md`
**Issue:** Layering rules don't document TYPE_CHECKING exception.
**Fix:** Add note: Services may use TYPE_CHECKING imports from adapters for type hints only.

---

## Implementation Notes

### Parallelization Strategy

**Wave 1 (Critical):** Items should be executed sequentially as they affect core pipeline flow:
1. SUB-1 → SUB-2 (both subagent issues)
2. TASKS-1 (newsletter lock bug - high impact)
3. TASKS-2 (edit stage dispatch - affects review routing)

**Wave 2 (High):** All items are independent and can be parallelized:
- MODELS-1, MODELS-2 (documentation updates)
- SCHEMA-1, SCHEMA-2, SCHEMA-3 (schema docs)
- ADPT-1 (just verification, no code change)

**Wave 3 (Medium):** Most items are independent documentation fixes:
- SVC-1, SVC-2, SVC-3 (service docs)
- SCHEMA-4, SCHEMA-5, SCHEMA-6 (schema docs)
- ROUTES-1 through ROUTES-8 (routes docs - 8 parallel tasks)
- ADPT-2 (pagination bug - verify before fixing)

**Wave 4 (Low):** All are documentation/template polish:
- UTIL-1, UTIL-2, UTIL-3
- TASKS-4, TASKS-5
- SUB-3, SUB-4, SUB-5
- SCHEMA-7, SCHEMA-8
- MODELS-3, MODELS-4
- OVERVIEW-1, OVERVIEW-2

### Known Intentional Layering Violations

The following are documented as intentional and should NOT be "fixed":
- `services/crawling.py` uses TYPE_CHECKING import from `adapters.base` - documented in AGENTS.md
- `tasks/crawl.py` imports directly from `adapters.base` - documented in AGENTS.md
- `schemas/common.py` imports from `services.config_cache` - documented with inline comment
- `services/subagent/tools.py` imports from `models` and `extensions` - documented in AGENTS.md

### Already Verified (No Action Needed)

The following items were verified as working correctly:
- SSRFSafeRedirectHandler interface matches requests library
- Article.updated_at index exists (line 48)
- services/crawling.py TYPE_CHECKING pattern correct
- Newsletter lock scope bug confirmed - needs fix (TASKS-1)

---

## Deferred Architecture Items

The following items were identified in the 2026-05-22 architecture review and deferred:

| Priority | Module | Issue | Status |
|----------|--------|-------|--------|
| HIGH | Adapters | SSRFSafeRedirectHandler interface mismatch | Verified works |
| HIGH | Adapters | APIAdapter pagination off-by-one | Needs verification |
| HIGH | Models | TrendMemory.topic is String(128) not 200 | Code correct, docs need update |
| MED | Adapters | Missing `contains` filter | Not implemented, documented correctly |
| MED | Models | TrendMemory.importance/expires_at undocumented | Fields exist, just undocumented |
| MED | Services | DeepSeek search provider missing from doc | Provider exists, just not documented |
| MED | Services | circuit_breaker.py not in file inventory | File exists, just not listed |
| MED | Tasks | Newsletter lock release scope bug | Bug confirmed - needs fix |
| MED | Tasks | Edit stage missing `_dispatch_next` for review routing | Bug confirmed - needs fix |
| MED | Services | Subagent chain `steps` parameter ignored | Bug confirmed - needs fix |
| MED | Subagent | ValidationError not in retryable_exceptions | Bug confirmed - needs fix |

---

## Verification Commands

After implementing fixes, run these commands:

```bash
# Lint all modified files
ruff check services/subagent/runner.py services/subagent/chain.py tasks/newsletter.py tasks/edit.py

# Type check
mypy services/subagent/chain.py --ignore-missing-imports

# Run relevant tests
python -m pytest tests/ -x -q -m "not e2e"
```

---

*Plan consolidated from architecture review findings - 2026-05-22*
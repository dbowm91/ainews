# AINews Consolidated Implementation Plan

**Status:** COMPLETED (2026-05-22)
**Last Updated:** 2026-05-22
**Goal:** Consolidate all remaining items from architecture reviews into actionable tasks.

---

## Summary

All items from this plan have been completed:

| Wave | Items | Commit |
|------|-------|--------|
| Wave 1 (CRIT) | SUB-1, TASK-1, SERVICE-1 | `b60aca9`, `b054081` |
| Wave 2 (HIGH) | MODELS-1, MODELS-2, OVERVIEW-1, SCHEMA-1, SCHEMA-2, ROUTES-1, ADPT-1 | `88ee46e` |
| Wave 3 (MED) | UTIL-1, SUB-2-SUB-6, MODELS-3, TASK-3, SCHEMA-3-5 | `dc176ca`, `ec2f45a`, `47f8063`, `5f9e445` |
| Wave 4 (LOW) | ADPT-3 | `9f28d65` |

See below for original plan details (preserved for reference).

---

## Verified Items (No Action Needed)

The following items were verified as already correct or already fixed:

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| SSRF redirect counter | `adapters/session.py:47-49` | ✅ FIXED | Counter decrements before raising UnsafeURLError |
| Duplicate except block | `schemas/common.py` | ✅ FIXED | File is 97 lines, no duplicate block |
| _should_route_to_review export | `tasks/pipeline.py:26` | ✅ FIXED | Re-export with noqa comment |
| track_share_click JSON | `routes/public/links.py:125` | ✅ FIXED | Returns `{"success": True}` |
| Chain escaping | `services/subagent/chain.py` | ✅ FIXED | Uses escape_prompt_data |
| utils/url.py docstring | `utils/url.py:1-5` | ✅ FIXED | Now clarifies impure DNS functions |
| Session key | `routes/admin/__init__.py:76` | ✅ FIXED | Uses `user_agent` not `ua` |
| SubagentChainStep/Config | `schemas/pipeline.py:107-117` | ✅ VERIFIED | Correctly located in schemas/pipeline.py |
| RawItem schema | `schemas/item.py` | ✅ VERIFIED | Exists and documented |
| trafilatura failure | `adapters/web.py:119-120` | ✅ VERIFIED | Only logs warning |
| request_delay per-article | `adapters/web.py:174-175` | ✅ VERIFIED | Per-article delay confirmed |
| Dashboard cache TTL | `routes/admin/dashboard.py:188` | ✅ VERIFIED | 60 seconds |
| updated_at index | `models/article.py:48` | ✅ VERIFIED | Inline index |
| TrendMemory index name | `models/context.py:49` | ✅ VERIFIED | ix_trend_memory_topic_importance |
| Source.source_key constraint | `architecture/models.md:118` | ✅ VERIFIED | Documented |
| Provider chain iteration | `services/llm/__init__.py:57-97` | ✅ VERIFIED | Generator pattern documented |
| TrendMemory semantic search | `services/trend_memory.py:414-430` | ✅ VERIFIED | 500 limit confirmed |
| retry_max=20 selector | `tasks/select.py:202` | ✅ VERIFIED | Aggressive retry behavior documented |

### Known Issues (Not Fixed but Acceptable)

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| raw_token_hash security | `routes/admin/api_tokens.py:43-45` | ⚠️ ACCEPTABLE | Field stores unhashed hash; not displayed externally; acceptable risk |
| Limiter release fallback | `tasks/pipeline.py:436-437` | ⚠️ ACCEPTABLE | `provider_id or rc.provider` pattern correctly handles None case |

---

## Wave 1: Critical Bugs (Parallelizable)

These issues can be fixed independently across different modules.

### 1.1 Subagent Runner — Recursive _finalize_subagent_result
| Item | ID | Location |
|------|----|----------|
| Bug | SUB-1 | `services/subagent/runner.py:277-297` |

**Problem:** `_finalize_subagent_result()` at line 288 recursively calls itself with same parameters - infinite loop bug. The `run_subagent()` function manually constructs `SubagentResponse` at lines 270-274 (not calling the broken function), while `run_subagent_with_tools()` at line 467 would hit infinite recursion if it called `_finalize_subagent_result()`.

**Fix:** Rewrite `_finalize_subagent_result()` to actually finalize the result without recursion:
```python
def _finalize_subagent_result(
    result: BaseModel | None,
    used_fallback: bool,
    fallback_stages: list[str],
    last_exc: BaseException | None,
    stage: str,
    task_type: str,
    article_id: int | None,
    stage_config: SubagentStageConfig,
) -> SubagentResponse:
    """Finalize subagent result, handling fallback logic and metrics."""
    synthesis = result.synthesis if result else ""
    return SubagentResponse(
        synthesis=synthesis,
        used_fallback=used_fallback,
        fallback_stages=fallback_stages,
    )
```

**Why the bug exists:** The original function was supposed to do something more complex (metrics, error handling) but instead just recursively called itself with no base case.

**Verification:** After fix, `run_subagent_with_tools()` should correctly call this function without infinite recursion. Test by calling `run_subagent_with_tools()` with a valid task - it should return a `SubagentResponse` without hanging.

---

### 1.2 Tasks — Error Dicts From _run_stage_core Not Properly Handled
| Item | ID | Location |
|------|----|----------|
| Bug | TASK-1 | `tasks/pipeline.py:346-387` |

**Problem:** `_run_stage_core()` returns error dicts like `{"article_id": article_id, "error": "pipeline_timeout"}` at lines 351 and 368. These are returned directly without proper error handling - they're treated as success results instead of failures.

**Code path:**
```python
# Line 351: Article not found
return {"article_id": article_id, "error": "not found"}, None, None

# Line 368: Pipeline timeout
return {"article_id": article_id, "error": "pipeline_timeout"}, None, None
```

When `run_stage()` unpacks at line 426:
```python
result, provider_id, model = _run_stage_core(stage, article_id, work_fn, rc, t0, run_id)
return result  # Returns the error dict directly!
```

**Fix:** Check for `error` key in returned dict and handle appropriately:
```python
result, provider_id, model = _run_stage_core(stage, article_id, work_fn, rc, t0, run_id)
if isinstance(result, dict) and "error" in result:
    return result  # Or wrap in proper error response
return result
```

**Verification:** Add test case for article not found scenario - should return error dict, not treat as success.

---

### 1.3 Services — Duplicate _degrade_and_advance Definition
| Item | ID | Location |
|------|----|----------|
| Design | SERVICE-1 | `tasks/pipeline.py:36`, `services/pipeline_degradation.py:183` |

**Problem:** Two separate definitions of `_degrade_and_advance` exist:
- `tasks/pipeline.py:36` - local version used by `retry.py`
- `services/pipeline_degradation.py:183` - public API version

The `tasks/__init__.py` exports the services version:
```python
from services.pipeline_degradation import degrade_stage as _degrade_and_advance
```

But `retry.py:47-48` imports from `tasks.pipeline` which has the local version.

**Fix Options:**
1. **Option A (Recommended):** Remove local definition from `tasks/pipeline.py` and have `retry.py` import from `services.pipeline_degradation` directly
2. **Option B:** Keep local definition but document why duplication exists

**Verification:** Check that `retry.py` still works after refactoring. The degradation behavior should remain the same.

---

## Wave 2: High Priority Issues (Parallelizable)

### 2.1 Models — Article→PipelineRun Relationship Docs Wrong
| Item | ID | Location |
|------|----|----------|
| Docs | MODELS-1 | `architecture/models.md:33` |

**Problem:** Docs claim `Article.pipeline_run_id` exists - it does not. Relationship is indirect via `PipelineLog`.

**Fix:** Update `architecture/models.md` to show:
```
PipelineRun → PipelineLog → Article
```
NOT `PipelineRun → Article` via `pipeline_run_id`

**Verification:** Check `models/article.py` - no `pipeline_run_id` field exists.

---

### 2.2 Models — TrendMemory Field Name Docs Wrong
| Item | ID | Location |
|------|----|----------|
| Docs | MODELS-2 | `architecture/models.md:176` |

**Problem:** Docs claim `TrendMemory.source_articles` (plural) - actual field is `source_article_id` (singular integer FK).

**Fix:** Update to `source_article_id` and clarify it's a single FK, not JSON array.

**Actual code in `models/context.py:27-30`:**
```python
source_article_id = Column(
    Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
)
```

**Verification:** Check TrendMemory model for actual field name.

---

### 2.3 Overview — providers.yaml Missing hybrid Search Provider
| Item | ID | Location |
|------|----|----------|
| Config | OVERVIEW-1 | `providers.yaml` |

**Problem:** `hybrid` search provider exists in `services/search/hybrid.py` (FTS5 + vector similarity) but is not configured in `providers.yaml`.

**Fix:** Add `hybrid` to `providers.yaml` search_providers section:
```yaml
search_providers:
  - duckduckgo
  - google
  - searxng
  - hybrid  # FTS5 + vector similarity - ENABLED
```

**Verification:** Check that hybrid provider can be loaded and used.

---

### 2.4 schemas — validate_adapter_config Returns Dict
| Item | ID | Location |
|------|----|----------|
| Bug | SCHEMA-1 | `schemas/source.py:124-131` |

**Problem:** `validate_adapter_config` returns `model_dump()` dict, loses type info. Callers may expect a validated model instance.

**Fix:** Return the validated Pydantic model instance instead of dict:
```python
# Change from:
return adapter_config.model_dump()

# To:
return adapter_config  # Return the validated model
```

**Note:** If dict is intentionally returned for serialization, document the contract clearly.

**Verification:** Check all callers of `validate_adapter_config` to ensure they handle the return type correctly.

---

### 2.5 schemas — ReviewConfig.auto_publish_threshold Not Documented
| Item | ID | Location |
|------|----|----------|
| Docs | SCHEMA-2 | `schemas/pipeline.py:35-40` |

**Problem:** `ReviewConfig.auto_publish_threshold` field exists but not documented in architecture.

**Fix:** Document this field in `architecture/pipeline.md` and add docstring to the schema.

**Verification:** Verify field is used correctly in edit stage.

---

### 2.6 Routes — Undocumented Routes in Architecture
| Item | ID | Location |
|------|----|----------|
| Docs | ROUTES-1 | `architecture/routes.md` |

**Problem:** 6 public routes, 35+ admin HTML routes, and 5 API endpoints not documented.

**Fix:** Add undocumented routes to `architecture/routes.md`:
- Public: `/sitemap.xml`, `/robots.txt`, feeds, links
- Admin HTML: All admin pages at `/admin/*`
- API: `/api/v1/track/*` endpoints

**Verification:** Compare route list in doc vs actual routes in code.

---

### 2.7 Adapters — Session Ownership Documentation Missing
| Item | ID | Location |
|------|----|----------|
| Docs | ADPT-1 | `adapters/rss.py:47-52`, `api.py:22-23`, `web.py:35` |

**Problem:** RSSAdapter creates own session; API/WebAdapter share global session - poorly documented.

**Session ownership pattern:**
- `RSSAdapter`: Creates own `requests.Session` with own `SSRFSafeRedirectHandler`
- `APIAdapter` and `WebAdapter`: Share global session from `get_crawl_session()`

**Fix:** Document session ownership per adapter type in `architecture/adapters.md`.

**Verification:** Verify session creation patterns in each adapter.

---

## Wave 3: Medium Priority Issues (Parallelizable)

### 3.1 utils — sanitize_html XSS Vulnerability
| Item | ID | Location |
|------|----|----------|
| Security | UTIL-1 | `utils/text.py:70-108` |

**Problem:** `sanitize_html()` only strips dangerous **tags** via `_TagStripper` but doesn't filter **attributes**. XSS vectors like `<img onerror=alert(1)>` pass through. The code uses `_DANGEROUS_TAGS` constant (not `_DANGEROUS_ATTRS` which doesn't exist).

**Current behavior:**
- Strips dangerous tags like `<script>`, `<iframe>`, etc.
- Does NOT strip event handler attributes like `onerror`, `onclick`, etc.
- Does NOT filter `javascript:` in `href` or `src` attributes

**Fix:** Add attribute filtering to strip event handlers and javascript: URIs:
```python
def sanitize_html(html: str) -> str:
    # Existing tag stripping logic...
    # NEW: Attribute filtering
    # Strip event handler attributes (onerror, onclick, onload, etc.)
    # Strip javascript: from href, src, action attributes
```

**Verification:** Test with:
- `<img onerror=alert(1)>` → should be stripped or sanitized
- `<a href="javascript:alert(1)">` → javascript: should be removed
- `<div onclick="alert(1)">` → onclick should be stripped

---

### 3.2 subagent — tools.py Layering Violation
| Item | ID | Location |
|------|----|----------|
| Layering | SUB-2 | `services/subagent/tools.py:100-101,123,141-142` |

**Problem:** `tools.py` imports directly from `models` - violates layering rules (services should not import from adapters, but models is a separate layer).

**Fix:** Move model imports to TYPE_CHECKING block if only used for type hints, or create a service layer helper:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from models.article import Article
```

**Note:** This is a known layering issue per AGENTS.md.

**Verification:** Check if models import can be moved to TYPE_CHECKING block.

---

### 3.3 subagent — Inconsistent Prompt Formatting
| Item | ID | Location |
|------|----|----------|
| Consistency | SUB-3 | `services/subagent/runner.py:64-67` vs `utils.py:30-41` |

**Problem:** `run_subagent()` and `run_subagent_with_tools()` use different prompt formatting.

**Fix:** Unify prompt formatting to use consistent approach in both functions.

**Verification:** Compare outputs of both functions for same input article.

---

### 3.4 subagent — SubagentChainStep/Config Location Docs Wrong
| Item | ID | Location |
|------|----|----------|
| Docs | SUB-4 | `architecture/subagent.md` |

**Problem:** Docs show `SubagentChainStep`/`SubagentChainConfig` in `runner.py` but they're actually in `schemas/pipeline.py:107-124`.

**Fix:** Update `architecture/subagent.md` to reflect correct location.

**Verification:** Check `schemas/pipeline.py` for these classes.

---

### 3.5 subagent — Documentation Retry Count Wrong
| Item | ID | Location |
|------|----|----------|
| Docs | SUB-5 | `architecture/subagent.md:268` |

**Problem:** Doc says "max 3 attempts" but actual is `stage_config.max_retries + 1` (default 2).

**Fix:** Update documentation to reflect actual retry logic.

**Verification:** Check `run_subagent()` retry loop.

---

### 3.6 models — datetime.utcnow Deprecation
| Item | ID | Location |
|------|----|----------|
| Modernization | MODELS-3 | `models/context.py:44` |

**Problem:** `datetime.utcnow` deprecated in Python 3.12+. Multiple files may have this issue.

**Fix:** Replace with `datetime.now(timezone.utc)` across the codebase:
```python
# Before (deprecated):
from datetime import datetime, utcnow

# After (Python 3.12+):
from datetime import datetime, timezone
datetime.now(timezone.utc)
```

**Files to check:** `models/context.py`, any other files using `datetime.utcnow`

**Verification:** Run `grep -r "datetime.utcnow" --include="*.py"` to find all occurrences.

---

### 3.7 Pipeline — finalized_at Not Set
| Item | ID | Location |
|------|----|----------|
| Bug | TASK-2 | `services/pipeline_degradation.py:209-239` |

**Problem:** `finalized_at` not set in `_finalize()` - docs say it should be. Note: `Article.finalized_at` doesn't exist - use `published_at` instead.

**Fix:** The `_finalize()` function should not set `finalized_at` since the field doesn't exist. Update documentation to clarify this.

**Contrast with `edit.py:219`** where `published_at` IS set:
```python
article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
```

**Verification:** Check article finalization - `published_at` should be set.

---

### 3.8 Pipeline — Invalid pending→skipped Transition
| Item | ID | Location |
|------|----|----------|
| Docs | TASK-3 | `constants.py:52-63` |

**Problem:** Docs show `pending → skipped` transition but not in `VALID_TRANSITIONS`. `SKIPPED` status is only reachable from `FAILED → pending` (for reprocessing), not directly from pending.

**Fix:** Either add `skipped` as valid transition to `VALID_TRANSITIONS` if intentional, or update docs to remove it.

**Current valid transitions from PENDING:**
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
```

**Verification:** Check `constants.py` for `VALID_TRANSITIONS`.

---

### 3.9 services — Provider Chain Performance
| Item | ID | Location |
|------|----|----------|
| Performance | SERVICE-2 | `services/llm/__init__.py:57-97` |

**Problem:** Provider chain iterates on every call to check circuit breaker state.

**Fix:** Consider caching the filtered provider chain with short TTL, but ensure circuit breaker state is still checked on each call (state can change dynamically).

**Verification:** Profile provider selection overhead.

---

### 3.10 services — TrendMemory Semantic Search Memory
| Item | ID | Location |
|------|----|----------|
| Performance | SERVICE-3 | `services/trend_memory.py:414-430` |

**Problem:** Semantic search loads 500 memories into memory for similarity calculation.

**Fix:** Use database-side similarity calculation or chunked processing to reduce memory usage.

**Current:** Loads all 500 memories then computes cosine similarity in Python.

**Verification:** Monitor memory usage during trend searches.

---

### 3.11 schemas — RawItem Not Documented
| Item | ID | Location |
|------|----|----------|
| Docs | SCHEMA-3 | `schemas/item.py` |

**Problem:** `RawItem` schema not documented in architecture.

**Fix:** Add `RawItem` schema to architecture documentation.

**Verification:** Check for RawItem usage in codebase.

---

### 3.12 schemas — Admin Schemas Not Documented
| Item | ID | Location |
|------|----|----------|
| Docs | SCHEMA-4 | `schemas/admin.py` |

**Problem:** `schemas/admin.py` not documented - critical for admin API.

**Fix:** Add admin schemas to architecture documentation.

**Verification:** Check admin API responses match schemas.

---

### 3.13 schemas — ListConfig Validation Missing
| Item | ID | Location |
|------|----|----------|
| Bug | SCHEMA-5 | `schemas/source.py:74-75` |

**Problem:** `ListConfig.card_selector`/`link_selector` have no `min_length=1` validation.

**Fix:** Add `min_length=1` validation to prevent empty selectors:
```python
card_selector: str = Field(..., min_length=1)
link_selector: str = Field(..., min_length=1)
```

**Verification:** Test with empty selector value - should fail validation.

---

### 3.14 routes — Dashboard Cache TTL May Be Too Aggressive
| Item | ID | Location |
|------|----|----------|
| Performance | ROUTES-2 | `routes/admin/dashboard.py:188` |

**Problem:** Dashboard stats cache TTL of 60s may be too aggressive for slow queries.

**Fix:** Increase to 120-300s based on query cost. Monitor dashboard load times.

**Verification:** Measure actual dashboard load times.

---

## Wave 4: Low Priority / Documentation Issues

### 4.1 utils — Document URL Validation Duplication
| Item | ID | Location |
|------|----|----------|
| Docs | UTIL-2 | `architecture/utils.md` |

**Problem:** URL validation duplication between `utils/url.py` and `services/url.py` not documented.

**Fix:** Document the difference:
- `utils/url.py`: For adapters (pure functions, no config dependency)
- `services/url.py`: Config-aware for services (has TTL/max_size from config)

**Verification:** Check architecture docs.

---

### 4.2 adapters — trafilatura Failure Alerting Missing
| Item | ID | Location |
|------|----|----------|
| Alerting | ADPT-2 | `adapters/web.py:119-120` |

**Problem:** `trafilatura` missing logs only warning, no operator alert.

**Fix:** Add alerting for trafilatura extraction failures (may be handled by article fallback already).

**Verification:** Check if article fallback handles this gracefully.

---

### 4.3 adapters — WebAdapter Request Delay Per-Article Not Per-Page
| Item | ID | Location |
|------|----|----------|
| Docs | ADPT-3 | `adapters/web.py:174-175` |

**Problem:** `request_delay_min/max` is per-article not per-page - may be too aggressive.

**Fix:** Document this behavior clearly so rate limiting expectations are correct.

**Verification:** Check how delay is applied in web adapter.

---

### 4.4 subagent — Documentation Shows Tool Iteration Incorrectly
| Item | ID | Location |
|------|----|----------|
| Docs | SUB-6 | `architecture/subagent.md:136-144` |

**Problem:** Docs show tool iteration in `run_subagent_with_tools()` but it happens inside `BaseLLMProvider.chat_with_tools()`.

**Fix:** Update execution flow diagram to reflect actual implementation.

**Verification:** Trace tool execution path.

---

### 4.5 adapters — Global Session Handler Sharing
| Item | ID | Location |
|------|----|----------|
| Docs | ADPT-4 | `adapters/session.py:57-75` |

**Problem:** Global session shares handler instance across all requests.

**Fix:** Document this behavior and its implications.

**Verification:** Check session handler usage.

---

### 4.6 tasks — Missing aggregate_crawl_results Task Documentation
| Item | ID | Location |
|------|----|----------|
| Docs | TASK-5 | `tasks/crawl.py:215-253` |

**Problem:** `aggregate_crawl_results` task (chord callback) not documented in architecture.

**Fix:** Document this task in `architecture/tasks.md` as a chord callback for aggregating crawl results.

**Verification:** Check task exists and works.

---

### 4.7 tasks — cleanup_old_article_versions days_to_keep Not Documented
| Item | ID | Location |
|------|----|----------|
| Docs | TASK-6 | `tasks/cleanup.py:268` |

**Problem:** `cleanup_old_article_versions` has configurable `days_to_keep` param not documented.

**Fix:** Document this configurable parameter.

**Actual signature:**
```python
def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
```

**Verification:** Check task signature.

---

### 4.8 services — Missing Services Documentation
| Item | ID | Location |
|------|----|----------|
| Docs | SERVICE-4 | `services/` |

**Problem:** Not documented in architecture/services.md:
- `article_validation.py` - Article quality validation
- `article_fallback.py` - Fallback content extraction
- `trend_detector.py` - Trend detection logic
- `pipeline_monitor.py` - Pipeline health monitoring
- `pipeline_degradation.py` - Graceful degradation logic

**Fix:** Add these services to `architecture/services.md`.

**Verification:** Check these files exist.

---

### 4.9 services — TYPE_CHECKING Import Layering Issue
| Item | ID | Location |
|------|----|----------|
| Layering | SERVICE-5 | `services/crawling.py:12-13` |

**Problem:** `TYPE_CHECKING` import from adapters violates layering (even though pattern is correct per AGENTS.md).

**Fix:** Document that this is intentional for type hints only, or replace with protocol definition in schemas.

**Current code:**
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from adapters.base import RawItem
```

**Verification:** Check import pattern.

---

### 4.10 models — Complex Import Lambda in Source.created_at
| Item | ID | Location |
|------|----|----------|
| Readability | MODELS-4 | `Source.created_at` |

**Problem:** Complex import lambda in `Source.created_at` is hard to read.

**Fix:** Simplify or add comment explaining the lambda.

**Verification:** Review Source model import.

---

## Implementation Order

### Wave 1 (Critical) - Can fix in parallel:
- **SUB-1:** Subagent runner recursive _finalize_subagent_result fix
- **TASK-1:** Error dicts from _run_stage_core not properly handled
- **SERVICE-1:** Duplicate _degrade_and_advance definition

### Wave 2 (High) - Can fix in parallel:
- **MODELS-1:** Article→PipelineRun relationship docs wrong
- **MODELS-2:** TrendMemory field name docs wrong
- **OVERVIEW-1:** providers.yaml missing hybrid
- **SCHEMA-1:** validate_adapter_config returns dict
- **SCHEMA-2:** ReviewConfig.auto_publish_threshold not documented
- **ROUTES-1:** Undocumented routes
- **ADPT-1:** Session ownership documentation missing

### Wave 3 (Medium) - Can fix in parallel:
- **UTIL-1:** sanitize_html XSS vulnerability
- **SUB-2:** tools.py layering violation
- **SUB-3:** Inconsistent prompt formatting
- **SUB-4:** SubagentChainStep/Config location docs wrong
- **SUB-5:** Documentation retry count wrong
- **MODELS-3:** datetime.utcnow deprecation
- **TASK-2:** finalized_at not set (doc clarification needed)
- **TASK-3:** Invalid pending→skipped transition
- **SERVICE-2:** Provider chain performance
- **SERVICE-3:** TrendMemory semantic search memory
- **SCHEMA-3:** RawItem not documented
- **SCHEMA-4:** Admin schemas not documented
- **SCHEMA-5:** ListConfig validation missing
- **ROUTES-2:** Dashboard cache TTL

### Wave 4 (Low/Docs) - Can fix in parallel:
- **UTIL-2:** URL validation duplication documented
- **ADPT-2:** trafilatura failure alerting
- **ADPT-3:** WebAdapter delay per-article documented
- **SUB-6:** Tool iteration docs wrong
- **ADPT-4:** Global session handler sharing
- **TASK-5:** aggregate_crawl_results not documented
- **TASK-6:** days_to_keep parameter not documented
- **SERVICE-4:** Missing services documentation
- **SERVICE-5:** TYPE_CHECKING import layering
- **MODELS-4:** Complex import lambda

---

## Verification Commands

After implementing changes, run:
```bash
ruff check . --exclude .venv
python -m mypy . --ignore-missing-imports
pytest tests/ -v
```

---

## Notes for Future Agents

### Parallelization Opportunities
- Wave 1 items (SUB-1, TASK-1, SERVICE-1) are independent - can assign to 3 agents in parallel
- Wave 2 items are mostly documentation fixes - can parallelize with 3-4 agents
- Wave 3 has some dependencies (SCHEMA fixes may affect SCHEMA-1) but mostly parallelizable
- Within subagent module, SUB-2 through SUB-6 are all independent

### Dependencies to Watch
1. SCHEMA-1 (validate_adapter_config returns dict) - check all callers before changing return type
2. SERVICE-1 (duplicate _degrade_and_advance) - ensure retry.py still works after refactoring
3. MODELS-1/MODELS-2 (docs) - only documentation, no code impact

### Security Items (Handle First in Wave)
- UTIL-1 (XSS vulnerability) - should be prioritized for security review

### Test Recommendations
- SUB-1: Test `run_subagent_with_tools()` doesn't infinite loop
- TASK-1: Test error dict handling for article not found
- UTIL-1: Test XSS vectors are sanitized

---

*Plan consolidated from architecture review findings - 2026-05-22*
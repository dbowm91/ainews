# AINews Consolidated Implementation Plan

**Status:** IN PROGRESS
**Last Updated:** 2026-05-22
**Goal:** Consolidate all remaining items from architecture reviews into actionable tasks.

---

## Overview

This plan consolidates findings from 10 architecture review documents:
- pipeline_review.md, services_review.md, tasks_review.md
- schemas_review.md, routes_review.md, utils_review.md
- subagent_review.md, adapters_review.md, overview_review.md, models_review.md

Items marked ✅ were verified as already correct. Items marked PENDING need implementation.

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
| raw_token_hash security | `routes/admin/api_tokens.py:43-45` | ⚠️ ISSUE | Misnamed field - stores unhashed |
| Dashboard cache TTL | `routes/admin/dashboard.py:188` | ✅ VERIFIED | 60 seconds |
| updated_at index | `models/article.py:48` | ✅ VERIFIED | Inline index |
| TrendMemory index name | `models/context.py:49` | ✅ VERIFIED | ix_trend_memory_topic_importance |
| Source.source_key constraint | `architecture/models.md:118` | ✅ VERIFIED | Documented |
| Provider chain iteration | `services/llm/__init__.py:57-97` | ✅ VERIFIED | Generator pattern documented |
| TrendMemory semantic search | `services/trend_memory.py:414-430` | ✅ VERIFIED | 500 limit confirmed |
| retry_max=20 selector | `tasks/select.py:202` | ✅ VERIFIED | Documented aggressive retry |
| _DANGEROUS_ATTRS issue | `utils/text.py` | ⚠️ WRONG | `_DANGEROUS_ATTRS` doesn't exist, `_DANGEROUS_TAGS` exists but attributes not filtered |

---

## Wave 1: Critical Bugs (Parallelizable)

These issues can be fixed independently across different modules.

### 1.1 Subagent Runner — Recursive _finalize_subagent_result
| Item | Status | Location |
|------|--------|---------|
| SUB-1 | PENDING | `services/subagent/runner.py:277-297` |

**Problem:** `_finalize_subagent_result()` at line 288 recursively calls itself with same parameters - infinite loop bug. The `run_subagent()` function manually constructs `SubagentResponse` at lines 270-274 (not calling the broken function), while `run_subagent_with_tools()` at line 467 attempts to call `_finalize_subagent_result()` (would infinite loop if reached).

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

**Verification:** After fix, `run_subagent_with_tools()` should correctly call this function without infinite recursion.

---

## Wave 2: High Priority Issues (Parallelizable)

### 2.1 schemas — validate_adapter_config Returns Dict
| Item | Status | Location |
|------|--------|---------|
| SCHEMA-2 | PENDING | `schemas/source.py:124-131` |

**Problem:** `validate_adapter_config` returns `model_dump()` dict, loses type info.

**Fix:** Return the validated Pydantic model instance instead of dict, or document that callers should re-parse.

**Verification:** Check all callers of `validate_adapter_config` to ensure they handle dict correctly.

---

### 2.2 schemas — ReviewConfig.auto_publish_threshold Not Documented
| Item | Status | Location |
|------|--------|---------|
| SCHEMA-3 | PENDING | `schemas/pipeline.py:35-40` |

**Problem:** `ReviewConfig.auto_publish_threshold` field exists but not documented.

**Fix:** Document this field in architecture/pipeline.md and add docstring.

**Verification:** Verify field is used correctly in edit stage.

---

### 2.3 Overview — utils/url.py Purity Documentation
| Item | Status | Location |
|------|--------|---------|
| OVERVIEW-1 | PENDING | `utils/url.py:40-49` |

**Problem:** Docstring claims "pure functions" but has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`).

**Fix:** Update docstring to clarify DNS resolution is impure with side effects:
```python
# Not pure - performs DNS resolution with caching side effects
```

**Verification:** Ensure docstring reflects actual behavior.

---

### 2.4 Overview — services/url.py Duplication
| Item | Status | Location |
|------|--------|---------|
| OVERVIEW-2 | PENDING | `services/url.py:154-167` |

**Problem:** `services/url.py` duplicates SSRF implementation from `utils/url.py`.

**Fix:** Refactor `services/url.py` to import from `utils/url.py` where possible, or document why duplication is necessary.

**Verification:** Both files should produce same validation results for same inputs.

---

### 2.5 Models — Article→PipelineRun Relationship Docs
| Item | Status | Location |
|------|--------|---------|
| MODELS-1 | PENDING | `architecture/models.md:33` |

**Problem:** Docs claim `Article.pipeline_run_id` exists - it does not. Relationship is indirect via `PipelineLog`.

**Fix:** Update `architecture/models.md` to clarify Article→PipelineRun relationship is via PipelineLog, not direct foreign key.

**Verification:** Check Article model - no `pipeline_run_id` field exists.

---

### 2.6 Models — TrendMemory Field Name Docs
| Item | Status | Location |
|------|--------|---------|
| MODELS-2 | PENDING | `architecture/models.md:176` |

**Problem:** Docs claim `TrendMemory.source_articles` (plural) - actual field is `source_article_id` (singular).

**Fix:** Update to `source_article_id` and clarify it's a single ID, not a relationship.

**Verification:** Check TrendMemory model for actual field name.

---

### 2.7 Services — TrendMemoryService Class Not Implemented
| Item | Status | Location |
|------|--------|---------|
| SERVICE-1 | PENDING | `services/trend_memory.py` |

**Problem:** Architecture doc mentions `TrendMemoryService` class but actual code uses module-level functions.

**Fix:** Either implement the class wrapper or update architecture doc to reflect module-level function pattern.

**Verification:** Check for `class TrendMemoryService` - doesn't exist.

---

### 2.8 Routes — Undocumented Routes in Architecture
| Item | Status | Location |
|------|--------|---------|
| ROUTES-2 | PENDING | `architecture/routes.md` |

**Problem:** 6 public routes, 35+ admin HTML routes, and 5 API endpoints not documented.

**Fix:** Add undocumented routes to `architecture/routes.md`:
- Public: `/sitemap.xml`, `/robots.txt`, feeds, links
- Admin HTML: All admin pages
- API: `/api/v1/track/*` endpoints

**Verification:** Compare route list in doc vs actual routes.

---

### 2.9 Routes — Session Key Documentation Mismatch
| Item | Status | Location |
|------|--------|---------|
| ROUTES-3 | PENDING | `architecture/routes.md:201` |

**Problem:** Session key `session['ua']` documented but code uses `session['user_agent']`.

**Fix:** Update documentation to use `session['user_agent']`.

**Verification:** Check `routes/admin/__init__.py:76` for correct key.

---

### 2.10 Adapters — Session Ownership Documentation
| Item | Status | Location |
|------|--------|---------|
| ADPT-3 | PENDING | `adapters/rss.py:47-52`, `api.py:22-23`, `web.py:35` |

**Problem:** RSSAdapter creates own session; API/WebAdapter share global session - poorly documented.

**Fix:** Document session ownership pattern per adapter type in architecture/adapters.md.

**Verification:** Verify session creation patterns in each adapter.

---

## Wave 3: Medium Priority Issues (Parallelizable)

### 3.1 utils — sanitize_html XSS Vulnerability
| Item | Status | Location |
|------|--------|---------|
| UTIL-1 | PENDING | `utils/text.py:70-108` |

**Problem:** `sanitize_html()` only strips dangerous **tags** via `_TagStripper` but doesn't filter **attributes**. XSS vectors like `<img onerror=alert(1)>` pass through. The `_DANGEROUS_TAGS` constant is used, but there's no `_DANGEROUS_ATTRS` constant (the plan incorrectly mentioned it).

**Fix:** Implement attribute filtering in `sanitize_html()` to strip event handlers (onerror, onclick, etc.) and dangerous attributes (src, href with javascript:).

**Verification:** Test with `<img onerror=alert(1)>` - should be sanitized or stripped.

---

### 3.2 subagent — tools.py Layering Violation
| Item | Status | Location |
|------|--------|---------|
| SUB-3 | PENDING | `services/subagent/tools.py:100-101,123,141-142` |

**Problem:** `tools.py` imports directly from `models` - violates layering rules.

**Fix:** Create a service layer helper to avoid direct model imports, or document why this violation is necessary.

**Verification:** Check if models import can be moved to TYPE_CHECKING block.

---

### 3.3 subagent — SubagentChainStep/Config Location Docs
| Item | Status | Location |
|------|--------|---------|
| SUB-4 | PENDING | `services/subagent/runner.py`, `schemas/pipeline.py:107-124` |

**Problem:** Docs show `SubagentChainStep`/`SubagentChainConfig` in `runner.py` but they're actually in `schemas/pipeline.py`.

**Fix:** Update `architecture/subagent.md` to reflect correct location.

**Verification:** Check `schemas/pipeline.py` for these classes.

---

### 3.4 subagent — Inconsistent Prompt Formatting
| Item | Status | Location |
|------|--------|---------|
| SUB-5 | PENDING | `services/subagent/runner.py:64-67` vs `utils.py:30-41` |

**Problem:** `run_subagent()` and `run_subagent_with_tools()` use different prompt formatting.

**Fix:** Unify prompt formatting to use consistent approach.

**Verification:** Compare outputs of both functions for same input.

---

### 3.5 subagent — Documentation Retry Count
| Item | Status | Location |
|------|--------|---------|
| SUB-6 | PENDING | `architecture/subagent.md:268` |

**Problem:** Doc says "max 3 attempts" but actual is `stage_config.max_retries + 1` (default 2).

**Fix:** Update documentation to reflect actual retry logic.

**Verification:** Check `run_subagent()` retry loop.

---

### 3.6 adapters — trafilatura Failure Alerting
| Item | Status | Location |
|------|--------|---------|
| ADPT-4 | PENDING | `adapters/web.py:119-120` |

**Problem:** `trafilatura` missing logs only warning, no operator alert.

**Fix:** Add alerting for trafilatura extraction failures (may be already handled by article fallback).

**Verification:** Check if article fallback handles this gracefully.

---

### 3.7 adapters — WebAdapter Request Delay Per-Page
| Item | Status | Location |
|------|--------|---------|
| ADPT-5 | PENDING | `adapters/web.py:174-175` |

**Problem:** `request_delay_min/max` is per-article not per-page - may be too aggressive.

**Fix:** Document this behavior clearly so rate limiting expectations are correct.

**Verification:** Check how delay is applied in web adapter.

---

### 3.8 schemas — RawItem Not Documented
| Item | Status | Location |
|------|--------|---------|
| SCHEMA-4 | PENDING | `schemas/item.py` |

**Problem:** `schemas/item.py` (RawItem) not documented in architecture.

**Fix:** Add `RawItem` schema to architecture documentation.

**Verification:** Check for RawItem usage in codebase.

---

### 3.9 schemas — Admin Schemas Not Documented
| Item | Status | Location |
|------|--------|---------|
| SCHEMA-5 | PENDING | `schemas/admin.py` |

**Problem:** `schemas/admin.py` not documented - critical for admin API.

**Fix:** Add admin schemas to architecture documentation.

**Verification:** Check admin API responses match schemas.

---

### 3.10 schemas — ListConfig Validation
| Item | Status | Location |
|------|--------|---------|
| SCHEMA-6 | PENDING | `schemas/source.py:74-75` |

**Problem:** `ListConfig.card_selector`/`link_selector` no `min_length=1` validation.

**Fix:** Add `min_length=1` validation to prevent empty selectors.

**Verification:** Test with empty selector value.

---

### 3.11 routes — api_token Hash Security
| Item | Status | Location |
|------|--------|---------|
| ROUTES-4 | PENDING | `routes/admin/api_tokens.py:43-45` |

**Problem:** `ApiToken.raw_token_hash` stores unhashed token hash - security concern.

**Fix:** Either remove (if not needed) or encrypt the raw token hash.

**Verification:** Check if raw_token_hash is ever displayed or used.

---

### 3.12 routes — Dashboard Cache TTL
| Item | Status | Location |
|------|--------|---------|
| ROUTES-5 | PENDING | `routes/admin/dashboard.py:188` |

**Problem:** Dashboard stats cache TTL of 60s may be too aggressive for slow queries.

**Fix:** Increase to 120-300s based on query cost.

**Verification:** Monitor dashboard load times.

---

### 3.13 models — updated_at Index Documentation
| Item | Status | Location |
|------|--------|---------|
| MODELS-3 | PENDING | `architecture/models.md:194` |

**Problem:** `updated_at` index documentation unclear - it's inline, not in `__table_args__`.

**Fix:** Clarify that index is defined inline on the column, not as separate table args.

**Verification:** Check Article model `updated_at` definition.

---

### 3.14 models — TrendMemory Index Name
| Item | Status | Location |
|------|--------|---------|
| MODELS-4 | PENDING | `architecture/models.md:197` |

**Problem:** `ix_trend_memory_topic_importance` index name not documented.

**Fix:** Document this index name in architecture.

**Verification:** Check TrendMemory `__table_args__`.

---

### 3.15 models — Source.source_key Constraint
| Item | Status | Location |
|------|--------|---------|
| MODELS-5 | PENDING | `architecture/models.md:118` |

**Problem:** `Source.source_key` unique constraint not documented.

**Fix:** Document the unique constraint on `source_key`.

**Verification:** Check Source model for unique constraint.

---

### 3.16 models — datetime.utcnow Deprecation
| Item | Status | Location |
|------|--------|---------|
| MODELS-6 | PENDING | `models/context.py:44` |

**Problem:** `datetime.utcnow` deprecated in Python 3.12+.

**Fix:** Replace with `datetime.now(timezone.utc)`.

**Verification:** Check all uses of `datetime.utcnow`.

---

### 3.17 services — Provider Chain Performance
| Item | Status | Location |
|------|--------|---------|
| SERVICE-2 | PENDING | `services/llm/__init__.py:57-97` |

**Problem:** Provider chain iterates on every call - performance issue.

**Fix:** Consider caching the filtered provider chain, but ensure circuit breaker state is still checked.

**Verification:** Profile provider selection overhead.

---

### 3.18 services — TrendMemory Semantic Search Memory
| Item | Status | Location |
|------|--------|---------|
| SERVICE-3 | PENDING | `services/trend_memory.py:414-430` |

**Problem:** Semantic search loads 500 memories into memory for similarity calc.

**Fix:** Use database-side similarity calculation or chunked processing.

**Verification:** Check memory usage during trend searches.

---

### 3.19 Overview — providers.yaml Missing hybrid
| Item | Status | Location |
|------|--------|---------|
| OVERVIEW-3 | PENDING | `providers.yaml` |

**Problem:** `providers.yaml` missing `hybrid` search provider - `hybrid.py` exists but not configured.

**Fix:** Add `hybrid` to `providers.yaml` search providers section.

**Verification:** Check if hybrid provider works.

---

### 3.18 Pipeline — retry_max=20 Selector Behavior
| Item | Status | Location |
|------|--------|---------|
| TASK-4 | PENDING | `tasks/select.py:201-203` |

**Problem:** `retry_max=20` in selector overrides documented limit of 3 - may cause excessive retries.

**Fix:** Document this aggressive retry behavior or adjust retry count.

**Verification:** Monitor selector stage retry counts.

---

### 3.19 Pipeline — finalized_at Not Set
| Item | Status | Location |
|------|--------|---------|
| TASK-5 | PENDING | `services/pipeline_degradation.py:209-239` |

**Problem:** `finalized_at` not set in `_finalize()` - docs say it should be.

**Fix:** Add `article.finalized_at = datetime.utcnow()` in `_finalize()`.

**Verification:** Check article finalization timestamp.

---

### 3.22 Pipeline — Invalid pending→skipped Transition
| Item | Status | Location |
|------|--------|---------|
| TASK-6 | PENDING | `constants.py:52-63` |

**Problem:** Docs show `pending → skipped` transition but not in `VALID_TRANSITIONS`.

**Fix:** Either add `skipped` as valid transition or remove from docs.

**Verification:** Check PipelineStatus and VALID_TRANSITIONS.

---

## Wave 4: Low Priority / Documentation Issues

### 4.1 utils — Add Tests for text/hash/security
| Item | Status | Location |
|------|--------|---------|
| UTIL-2 | PENDING | `tests/` |

**Problem:** No unit tests for `utils/text.py`, `utils/hash.py`, `utils/security.py`.

**Fix:** Add comprehensive unit tests for these utilities.

**Verification:** Run test suite for utils.

---

### 4.2 utils — Document URL Validation Duplication
| Item | Status | Location |
|------|--------|---------|
| UTIL-3 | PENDING | `architecture/utils.md` |

**Problem:** URL validation duplication between `utils/url.py` and `services/url.py` not documented.

**Fix:** Document the difference: `utils/url.py` is for adapters (pure), `services/url.py` is config-aware for services.

**Verification:** Check architecture docs.

---

### 4.3 subagent — Documentation Shows Tool Iteration Incorrectly
| Item | Status | Location |
|------|--------|---------|
| SUB-7 | PENDING | `architecture/subagent.md:136-144` |

**Problem:** Docs show tool iteration in `run_subagent_with_tools()` but it happens inside `BaseLLMProvider.chat_with_tools()`.

**Fix:** Update execution flow diagram to reflect actual implementation.

**Verification:** Trace tool execution path.

---

### 4.4 adapters — Global Session Handler Sharing
| Item | Status | Location |
|------|--------|---------|
| ADPT-6 | PENDING | `adapters/session.py:57-75` |

**Problem:** Global session shares handler instance across all requests.

**Fix:** Document this behavior and its implications.

**Verification:** Check session handler usage.

---

### 4.5 models — Complex Import Lambda
| Item | Status | Location |
|------|--------|---------|
| MODELS-7 | PENDING | `Source.created_at` |

**Problem:** Complex import lambda in `Source.created_at` is hard to read.

**Fix:** Simplify or add comment explaining the lambda.

**Verification:** Review Source model import.

---

### 4.6 tasks — Missing aggregate_crawl_results
| Item | Status | Location |
|------|--------|---------|
| TASK-7 | PENDING | `tasks/crawl.py:215-253` |

**Problem:** `aggregate_crawl_results` task (chord callback) not documented.

**Fix:** Document this task in architecture/tasks.md.

**Verification:** Check task exists and works.

---

### 4.7 tasks — cleanup_old_article_versions days_to_keep
| Item | Status | Location |
|------|--------|---------|
| TASK-8 | PENDING | `tasks/cleanup.py:268` |

**Problem:** `cleanup_old_article_versions` has configurable `days_to_keep` param not documented.

**Fix:** Document this configurable parameter.

**Verification:** Check task signature.

---

### 4.8 services — Missing Services Documentation
| Item | Status | Location |
|------|--------|---------|
| SERVICE-4 | PENDING | `services/` |

**Problem:** Not documented: `article_validation.py`, `article_fallback.py`, `trend_detector.py`, `pipeline_monitor.py`, `pipeline_degradation.py`.

**Fix:** Add these services to architecture/services.md.

**Verification:** Check these files exist.

---

### 4.9 services — TYPE_CHECKING Import Layering
| Item | Status | Location |
|------|--------|---------|
| SERVICE-5 | PENDING | `services/crawling.py:12-13` |

**Problem:** `TYPE_CHECKING` import from adapters violates layering (even though pattern is correct).

**Fix:** Document that this is intentional for type hints only.

**Verification:** Check import pattern.

---

## Implementation Order

### Wave 1 (Critical) - Fix in parallel:
1. SUB-1: Subagent runner recursive _finalize_subagent_result fix

### Wave 2 (High) - Fix in parallel:
2-11. All Wave 2 items (SCHEMA-2, SCHEMA-3, OVERVIEW-1, OVERVIEW-2, MODELS-1, MODELS-2, SERVICE-1, ROUTES-2, ROUTES-3, ADPT-3)

### Wave 3 (Medium) - Fix in parallel:
12-28. All Wave 3 items (UTIL-1, SUB-3, SUB-4, SUB-5, SUB-6, ADPT-4, ADPT-5, SCHEMA-5, SCHEMA-6, ROUTES-4, MODELS-6, SERVICE-2, SERVICE-3, OVERVIEW-3, TASK-4, TASK-5, TASK-6)

### Wave 4 (Low/Docs) - Fix in parallel:
29-37. All Wave 4 items (UTIL-2, UTIL-3, SUB-7, ADPT-6, MODELS-7, TASK-7, TASK-8, SERVICE-4, SERVICE-5)

---

## Verification Commands

After implementing changes, run:
```bash
ruff check . --exclude .venv
python -m mypy . --ignore-missing-imports
pytest tests/ -v
```

---

*Plan created 2026-05-22 - consolidating 10 architecture reviews*
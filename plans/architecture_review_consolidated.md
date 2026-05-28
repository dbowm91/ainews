# Architecture Documentation Review - Consolidated Findings

**Date:** 2026-05-28
**Status:** COMPLETE

## Summary

| Category | Count |
|----------|-------|
| Documents Reviewed | 15 |
| Verified Claims | ~250+ |
| Incorrect Claims Fixed | 65+ |
| Bugs Found | 5 |
| Improvement Opportunities | 45+ |
| Stale Content Removed | 15+ |

## Review Results by Document

### 1. models.md & schemas.md (Data Layer)
**Review File:** `plans/data_layer_review.md`
**Key Fixes Applied:**
- Fixed `datetime.utcnow` → `datetime.now(timezone.utc)` (deprecated since Python 3.12)
- Added `ondelete="CASCADE"` to Article `source_id` FK
- Fixed Source `name` to include `nullable=False, index=True`
- Fixed AdminUser `username` to include `index=True`
- Fixed PipelineStatus transitions diagram to match `VALID_TRANSITIONS`
- Fixed TrendMemory field order to match actual code
- Added TopicNote model documentation
- Added Subscriber unique constraint on `(email, newsletter_type)`
- Fixed `NewsletterPipelineConfig` to show default factories
- Fixed `SelectArticleInput` → `SelectArticleTask` in usage example
- Noted missing email validator on `SendEmailTask`

### 2. adapters.md & utils.md (Adapters & Utils)
**Review File:** `plans/adapter_utils_review.md`
**Key Fixes Applied:**
- Fixed `BaseSourceAdapter.__init__` signature to take `SourceConfig`
- Fixed `fetch()` return type to `list[Any]`
- Fixed `parse_item()` parameter name and return type
- Fixed `SSRFSafeRedirectHandler` to show `__call__` instead of `redirect_request`
- Added missing adapter methods (`match_topics`, `get_adapter_class`, `_classify_topics`)
- Added context manager support documentation
- Fixed `validate_url_safe()` exception documentation (`ValueError` vs `UnsafeURLError`)
- Fixed `services/url.py` description to note re-exports

### 3. llm-providers.md, search-providers.md, subagent.md (LLM & Search)
**Review File:** `plans/llm_search_subagent_review.md`
**Key Fixes Applied:**
- Fixed `get_provider_for_role()` return type to 4-tuple
- Fixed `get_provider_chain()` return type to generator of tuples
- Fixed `cost_tracker.py` function names (`get_cost_summary`, not `record_usage`)
- Fixed `_retry_with_backoff` signature to match actual code
- Fixed `CircuitOpenError` location note (`circuit_breaker.py`, not `errors.py`)
- Fixed `SearchResult` to remove non-existent `score` field
- Fixed `SearxNGProvider` class name to `SearXNGSearchProvider`
- Fixed `_context_tool_search_web` function name to `_search_web`
- Fixed `HybridSearchProvider` base class (`SearchProvider`, not `BaseSearchProvider`)
- Fixed `get_article_search_provider` return type
- Fixed `ErrorHandlingMiddleware` to document re-raise behavior

### 4. pipeline.md, tasks.md, prompts.md (Pipeline & Tasks)
**Review File:** `plans/pipeline_tasks_review.md`
**Key Fixes Applied:**
- Fixed `get_system_prompt()` signature (role + yaml_prompt params)
- Fixed `load_prompt_file()` signature (returns `str | None`)
- Fixed `count_tokens()` default (`None`, not `gpt-4`)
- Fixed truncation function parameter names (`max_chars`, not `max_tokens`)
- Fixed `smart_truncate_context()` return type (`tuple[str, bool]`)
- Fixed `summarize_context()` signature (text, llm_provider params)
- Fixed `escape_prompt_data()` location reference
- Fixed task signatures to include `run_id` parameter

### 5. infrastructure.md, config.md, overview.md (Infrastructure & Config)
**Review File:** `plans/infra_config_overview_review.md`
**Key Fixes Applied:**
- Fixed Redis DB allocation table (DB 0 has limiter, DB 2 unused)
- Fixed `get_redis()` signature (no `db` parameter)
- Fixed SQLite pragma function name
- Removed fabricated Celery task time limits
- Fixed `HealthResult` field types (`checks: dict[str, Any]`, `version` field)
- Fixed health check function name (`run_health_checks`, not `check_health`)
- Fixed `ModelLimiter` interface (provider/model-aware with pub/sub)
- Fixed `ResponseCache` methods (`invalidate`/`invalidate_prefix`, ttl=120)
- Fixed `CircuitBreaker` constructor (requires `name` param)
- Fixed `CircuitBreaker.can_execute()` method name
- Fixed `dispatch_webhook` signature
- Fixed `MetricsCollector` method names (`counter_inc`, `gauge_set`, `histogram_observe`, `get_prometheus`)
- Fixed logging function signatures (parameter order)
- Fixed `RoleConfig` defaults (required fields, temperature=0.0)
- Fixed `SubagentStageConfig` defaults (enabled=False, timeout=120) and added missing fields
- Fixed `NewsletterConfig` field names (`send_time`, not `daily_send_time`)
- Fixed provider count (14, not 16)
- Fixed session binding location (`routes/decorators.py`)

### 6. routes.md (Routes)
**Review File:** `plans/routes_review.md`
**Key Fixes Applied:**
- Fixed trigger-crawl path (`/admin/trigger-crawl`, not `/admin/pipelines/trigger-crawl`)
- Added missing admin routes (sources/add, trend-memory CRUD, semantic search)
- Fixed session hijacking pseudocode (`session['user_agent']`, not `session['ua']`)
- Fixed rate limiting claim (only login/verify-2fa have explicit limits)

## Bugs Found

### 1. Missing `UnsafeURLError` import in `routes/admin/sources.py` (MEDIUM)
- **File:** `routes/admin/sources.py:59`
- **Issue:** `except UnsafeURLError as e:` but `UnsafeURLError` is never imported
- **Impact:** `NameError` will be raised when URL validation fails

### 2. `validate_url_safe()` exception type mismatch (HIGH)
- **File:** `utils/url.py:245-264`
- **Issue:** Function raises `ValueError` for most invalid inputs but docstring claims `UnsafeURLError`
- **Impact:** Callers catching `UnsafeURLError` will miss `ValueError` for empty URLs, unsupported schemes

### 3. `generate_daily_newsletters` missing `@shared_task` decorator (HIGH)
- **File:** `tasks/newsletter.py:476`
- **Issue:** Function takes `self` as first parameter but has no `@shared_task` decorator
- **Impact:** May cause silent failure of scheduled newsletter generation

### 4. `ErrorHandlingMiddleware` behavior mismatch (MEDIUM)
- **File:** `services/subagent/middleware.py:64-80`
- **Issue:** Doc says returns error dict, code re-raises exceptions
- **Impact:** Tool execution errors propagate instead of being caught

### 5. `_context_tool_search_web` function name wrong (MEDIUM)
- **File:** `services/subagent/tools.py:165`
- **Issue:** Actual function is `_search_web`, not `_context_tool_search_web`
- **Impact:** Documentation references non-existent function

## Remaining Work

The following items were identified but not yet addressed:

1. **Stale Content Pruning** - Some outdated references remain in overview.md directory listings
2. **Missing Documentation** - Several service files not listed in overview.md directory structure
3. **Duplicate Endpoint Tables** - routes.md has duplicate admin API endpoint documentation

## Next Steps

1. Run `ruff check . --exclude .venv` to verify no syntax errors
2. Update AGENTS.md with any new conventions discovered
3. Update skills in `.opencode/skills/` directory
4. Commit all changes

# Review: services.md

**Reviewed:** 2026-05-31
**Source:** `architecture/services.md`
**Reviewer:** Subagent 7 (Services Layer)
**Status:** COMPLETE

---

## Verified Claims

### Provider System
- `BaseLLMProvider` inherits from `BaseProvider` (line 82 of `services/llm/base.py`)
- `BaseProvider` provides `provider_id` and `config` fields (lines 17-19 of `services/provider_base.py`)
- `BaseLLMProvider.__init__` accepts `provider_id: str, config: dict` (line 89 of `services/llm/base.py`)
- `default_model: str = ""` class attribute (line 83)
- `client` property with lazy-loaded double-checked locking (lines 94-100)
- `_create_client()` abstract method (line 187)
- `chat()` abstract method with correct signature (lines 191-202)
- `chat_streaming()` abstract method with correct signature (lines 204-213)
- `_chat_with_schema()` abstract method with correct signature (lines 417-429)
- `_call_api_with_tools()` abstract method with correct signature (lines 431-447)
- `_extract_text_and_tool_calls()` abstract method (lines 449-461)
- `_format_tool_result()` abstract method (lines 463-476)

### Rate Limiter
- `ModelLimiter` class (line 32 of `services/limiter.py`)
- `acquire(provider_id, model, max_concurrent, timeout=300)` signature matches (lines 39-45)
- `release(provider_id, model, timeout=300)` signature matches (lines 95-99)
- `get_active(provider_id, model)` returns `int | None` (lines 132-139)
- `cleanup_stale_slots()` exists (line 141)
- `is_healthy()` exists (line 163)

### Email
- `SMTPConnectionPool` class at `services/email.py:13` (line 13)
- `__init__(pool_size: int = 5)` (line 16)
- `get_connection()` returns `smtplib.SMTP` (line 64)
- `return_connection(server: smtplib.SMTP)` (line 91)
- `close_all()` (line 117)
- `_is_healthy(server)` (line 56)
- `_compute_cfg_hash(cfg: dict)` (line 27)
- Global `_smtp_pool` singleton via `_get_smtp_pool()` (lines 128-141)
- `send_newsletter_email(email, subject, html_content, unsubscribe_url)` (lines 286-291)
- `send_verification_email(email, newsletter_type, verification_url, unsubscribe_url, site_name="ainews//")` (lines 185-191)
- `send_welcome_email(email, newsletter_type, unsubscribe_url, site_name="ainews//")` (lines 240-245)

### Trend Memory
- Module-level functions (not a class) - confirmed
- `propose_trend_memory(article, engagement_data=None)` exists (line 217)
- `get_memory_for_topics(topics, min_importance=1, max_age_days=None)` (lines 106-110)
- `consolidate_all_topics()` (line 351)
- `purge_expired()` returns `int` (line 368)

### Content Extraction
- `trafilatura` used as primary extractor (line 9, 95)
- `readability` used as fallback (line 12, 106-118)

### Search Providers
- All files exist in `services/search/` directory
- `__init__.py`, `base.py`, `duckduckgo.py`, `google.py`, `searxng.py`, `hybrid.py`, `session.py`, `sqlite_fts.py` - all verified

### Circuit Breaker
- `CircuitBreaker` class (line 31 of `services/circuit_breaker.py`)
- `get_breaker(name, failure_threshold=5, ...)` (lines 388-406)
- `circuit_protected(breaker_name, fallback=None)` decorator (lines 415-448)

### Metrics
- `MetricsCollector.counter_inc(name, value=1, labels=None)` (lines 44-58)
- `MetricsCollector.gauge_set(name, value, labels=None)` (lines 60-75)
- `MetricsCollector.histogram_observe(name, value, labels=None)` (lines 77-97)

### Health
- `run_health_checks(include_celery=True, detailed=False)` (lines 121-123)
- NOT `check_health()` - confirmed no such function exists

### Logging
- `PipelineLogger` class (line 159 of `services/logging_utils.py`)
- `log_pipeline_event(stage, event, article_id=None, run_id=None, level="info", **extra)` (lines 85-92)
- `log_article_event(article_id, event, level="info", **extra)` (lines 114-119)

### Validation
- `ValidationError(ValueError)` (line 9 of `services/article_validation.py`)
- `validate_final_article(final_article)` (lines 13-62)

### Cost Tracking
- `get_cost_summary()` reads from `MetricsCollector` (line 83 of `services/cost_tracker.py`)

### Layering Exceptions
- `services/crawling.py` TYPE_CHECKING import from `adapters.base` (lines 12-15)
- `services/subagent/tools.py` direct imports from `models` and `extensions` (lines 12-13 comment)
- `schemas/common.py` imports from `services.config_cache` (lines 75, 89)
- `tasks/crawl.py` imports from `adapters.base` (documented in AGENTS.md)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 258 | `propose_trend_memory(article, engagement_data) -> list[TrendMemory]` | `services/trend_memory.py:217` -- returns `SubagentResponse`, not `list[TrendMemory]` | HIGH |
| 87-96 | `chat_structured` shows `**kwargs` parameter and returns `BaseModel` | `services/llm/base.py:217-227` -- has `max_validation_retries: int = 2, stage: str = ""` params (no `**kwargs`), returns `T` (TypeVar bound to BaseModel) | MEDIUM |
| 279-281 | Content extractor: "Final fallback: Raw HTML with boilerplate removal" | `services/content_extractor.py:123` -- returns `ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)`, no raw HTML extraction | MEDIUM |

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | `propose_trend_memory` documented return type is wrong - could mislead callers expecting `list[TrendMemory]` instead of `SubagentResponse` | `architecture/services.md:258` vs `services/trend_memory.py:217` | HIGH | Document says `-> list[TrendMemory]`, actual returns `SubagentResponse(synthesis=..., used_fallback=..., fallback_stages=[])` |

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | `chat_structured` signature in docs should include `max_validation_retries` and `stage` params, remove `**kwargs`, and show `T` return type | documentation | P1 |
| 2 | Document that `propose_trend_memory` uses the editor role's LLM provider (line 199 of trend_memory.py) | documentation | P2 |
| 3 | Document `validate_and_raise()` helper in `article_validation.py` alongside `validate_final_article()` | documentation | P2 |
| 4 | Document `semantic_search_trends()` function in `trend_memory.py` (line 392) | documentation | P3 |
| 5 | Document `get_pipeline_logger()` factory function in `logging_utils.py` | documentation | P3 |

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 8-46 | File inventory | Missing ~30 modules: `health.py`, `totp.py`, `prompts.py`, `url.py`, `topic_gap.py`, `stage_cost.py`, `source_intelligence.py`, `quality_report.py`, `pipeline_replay.py`, `quality.py`, `newsletter.py`, `quality_report_service.py`, `dedup_service.py`, `article.py`, `alerts.py`, `config_utils.py`, `audit.py`, `subscribers.py`, `degradation.py`, `redis_utils.py`, `task_security.py`, `tracing.py`, `config_cache.py`, `utils.py`, `date_utils.py`, `rss.py`, `validation.py`, `pagination.py`, `config_unified.py` | update inventory or add "see `ls services/` for full list" |
| 279-281 | "Final fallback: Raw HTML with boilerplate removal" | No such fallback exists - code returns EMPTY status | remove claim |

---

## Summary

- Verified: 38 claims
- Incorrect: 3 claims
- Bugs: 1 (HIGH: 1, MEDIUM: 0, LOW: 0)
- Improvements: 5
- Stale items: 2 (inventory incomplete, fallback claim false)

### Key Findings

1. **HIGH: Wrong return type for `propose_trend_memory`** - The document claims it returns `list[TrendMemory]` but it actually returns `SubagentResponse`. This could cause runtime errors for callers following the documentation.

2. **MEDIUM: `chat_structured` signature is outdated** - Missing `max_validation_retries` and `stage` parameters, includes non-existent `**kwargs`.

3. **MEDIUM: False fallback claim** - Content extractor does NOT have a "raw HTML with boilerplate removal" fallback. It returns `ExtractionStatus.EMPTY` when both trafilatura and readability fail.

4. **File inventory is significantly incomplete** - The document lists ~30 modules but the actual `services/` directory contains ~60 Python files. The "..." at line 46 is too vague.

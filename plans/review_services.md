# Services Module Architecture Review

**Document reviewed:** `architecture/services.md`
**Review date:** 2026-05-29
**Cross-referenced with:** `plans/plan.md` (completed 2026-05-29)

---

## Verified Claims

### Service Module Structure
- All service modules listed in `architecture/services.md` exist in `services/` directory
- `services/llm/` contains: `base.py`, `anthropic.py`, `openai.py`, `gemini.py`, `ollama.py`, `errors.py`, `types.py`, `json_utils.py`
- `services/subagent/` contains: `config.py`, `runner.py`, `chain.py`, `tools.py`, `registry.py`, `utils.py`, `conditions.py`, `prompt_templates.py`, `middleware.py`
- `services/search/` contains: `duckduckgo.py`, `google.py`, `searxng.py`, `hybrid.py`, `sqlite_fts.py`, `base.py`, `session.py`

### config_cache.py Patterns
- **mtime-based invalidation:** Verified at `services/config_cache.py:241-274` (`invalidate_if_stale()` and `_record_mtime()`)
- **Redis DB 1:** Verified at line 300 (`CELERY_BROKER_URL...replace("/0", "/1").replace("/2", "/1")`)
- **L1 memory cache:** 500 entries max (`_MAX_MEMORY_ENTRIES = 500`)

### config_unified.py
- Unified config loading verified via `AppConfig` class with `from_flask()` and `from_env()` methods
- Provides `PipelineConfig`, `SecurityConfig`, `SourceConfig` dataclasses

### circuit_breaker.py Interface
- `name` param required in `__init__()`: line 42
- `can_execute()` method: lines 155-170 (not `is_open()`)
- `get_breaker()` factory function: lines 388-406
- `CircuitOpenError` exception: line 451

### limiter.py ModelLimiter Interface
- `acquire(provider_id, model, max_concurrent, timeout)` signature: lines 39-45
- `release(provider_id, model, timeout)`: lines 95-130
- `get_active(provider_id, model)`: lines 132-139
- `cleanup_stale_slots()`: lines 141-161
- `is_healthy()`: lines 163-169

### cache.py ResponseCache
- L1 + L2 cache verified: L1 in-memory (`_memory` OrderedDict), L2 Redis
- LRU eviction: `_evict_batch()` method with `popitem(last=False)`
- Stampede protection via pub/sub: `get_or_set()` method lines 143-189

### metrics.py MetricsCollector Methods
- `counter_inc()`: lines 44-58
- `gauge_set()`: lines 60-75
- `histogram_observe()`: lines 77-97
- `get_metrics()`: lines 179-217
- `get_prometheus()`: lines 219-271

### health.py run_health_checks()
- Function signature verified at `services/health.py:121-165`
- `include_celery=True, detailed=False` parameters
- Returns `HealthResult` dataclass with `status`, `checks`, `version`

### logging_utils.py
- `PipelineLogger` class: lines 159-192
- `log_pipeline_event()`: lines 85-111
- `log_article_event()`: lines 114-132

### article_validation.py ValidationError
- `ValidationError(ValueError)`: line 9 - confirmed inherits from ValueError

### url.py SSRF Protection
- `validate_url_safe()`: lines 178-192
- Uses `get_config_with_default()` for config support (line 14, 61-62)
- `UnsafeURLError(ValueError)`: line 132
- `_BLOCKED_NETWORKS` private IP detection: lines 32-47

### pipeline_monitor.py Redis Minute-Bucket Metrics
- `_PIPELINE_WINDOW_SECONDS = 60`: line 20
- `record_stage_result()`: lines 30-66
- Success/failure counters per stage per minute bucket

### LLM Provider System
- `BaseLLMProvider` inherits from `BaseProvider`: line 55 in `llm/base.py`
- `BaseProvider` has `provider_id` and `config` fields: `services/provider_base.py:17-19`
- `ToolDefinition` is `@dataclass` with fields: `name`, `description`, `parameters`, `required`, `fn` (no `cached` field)

### Subagent Tools (14 total)
- 12 context tools + 2 search tools verified at `services/subagent/tools.py:306-603`
- Context tools: `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost`
- Search tools: `web_search`, `get_search_provider`

### Email Module Functions
- `send_newsletter_email()`: line 286
- `send_verification_email()`: line 185
- `send_welcome_email()`: line 240

### Known Layering Exceptions (Documented)
- `services/crawling.py` imports from `adapters.base` (TYPE_CHECKING only)
- `services/subagent/tools.py` imports from `models` and `extensions`
- `schemas/common.py` imports from `services.config_cache`
- `tasks/crawl.py` imports from `adapters.base`

---

## Incorrect Claims

None found. All claims in `architecture/services.md` verified against actual codebase.

---

## Bugs Found

**NONE** - No bugs identified in reviewed service module documentation.

---

## Improvement Opportunities

1. **Minor: Email module class documentation**
   - The docs state email module has "module-level functions (not a class)" which is technically accurate for the send_* functions, but `SMTPConnectionPool` is a useful class in that module
   - Not a bug, just could be more precisely worded to acknowledge the `SMTPConnectionPool` class

2. **Minor: trend_memory.py layering note**
   - Document correctly notes "This module uses module-level functions, not a class"
   - However, the module does import from `models` (line 14), which is a documented layering exception

---

## Stale Content

None. Document is current with codebase.

---

## Priority for Each Finding

| Finding | Priority | Type |
|---------|----------|------|
| No issues found | N/A | N/A |

---

## Summary

The `architecture/services.md` document is **ACCURATE** and requires no corrections. All claims were verified against the actual codebase:
- Service module structure matches exactly
- All function signatures, class interfaces, and method names match
- Configuration patterns (mtime invalidation, DB 1, L1+L2 cache) verified
- Interface patterns (circuit breaker, limiter, metrics collector) verified
- Known layering exceptions correctly documented
- DeepSeek is correctly noted as NOT a search provider
- Tool count (14) correctly documented

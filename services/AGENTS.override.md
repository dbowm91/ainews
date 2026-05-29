# Services Agent Context

## Architectural Rules
- Services must be decoupled from Adapters.
- Use `schemas/` for data structures shared across services.
- Business logic should reside in services, not in models or routes.
- **IMPORTANT:** Do NOT import from `adapters/` in services. If shared types are needed, use `schemas/` or `models/`. Exception: `TYPE_CHECKING` blocks are acceptable for type hints only.

## LLM Interaction
- All LLM calls should go through the providers defined in `services/llm/`.
- Use `CircuitBreaker` for all external API calls.
- Implement token budgeting for subagent loops to prevent context overflow.

## Specific Service Notes
- **Limiter:** Uses Redis pub/sub for waiting. Do not use `time.sleep()`. Ensure `pubsub` objects are reused or properly closed to avoid Redis connection bloat.
- **Logging:** `services/logging_utils.py` contains implicit `Optional` parameters that trigger Mypy errors. Use `Optional[Type] = None` explicitly.
- **Audit:** Harden against database connection issues; logging an action should not crash the request.
- **Prompts:** Use `@lru_cache` for prompt file loading and truncation summaries.

## Provider Notes
- **SubagentStageConfig vs StageConfig:** The actual stage configuration class is `SubagentStageConfig` in `schemas/pipeline.py`, NOT `StageConfig` which is an empty stub with only `tools` field.
- **DeepSeek Provider:** Not implemented as a search provider. DeepSeek is only an LLM provider (in providers.yaml) and a regex pattern for URL sanitization and trend detection. Do NOT document DeepSeek as a search provider without implementing `services/search/deepseek.py`.

## Quality Report
- **QualityReport model:** `models/quality.py:10-51` with fields: `article_id`, `article_version_id`, `stage`, `overall_score`, `groundedness`, `coherence`, `completeness`, `safety`, `citation_score`, `claim_score`, `passed`, `needs_review`, `findings` (JSON), `meta` (JSON), `created_at`.
- **Quality report service:** `services/quality_report.py` with `build_quality_report()` (line 438) and `persist_quality_report()` (line 531).
- **Edit stage integration:** `tasks/edit.py:378-419` runs quality report after final article is produced. If `quality_result.passed` is False, article routes to `PipelineStatus.REVIEW`.

## Source Intelligence
- `services/source_intelligence.py` provides: `get_source_performance()` (line 58), `get_topic_coverage()` (line 175), `get_source_recommendations()` (line 230).
- API endpoints in `routes/admin/api/source_intelligence.py`.

## Topic Gap
- `services/topic_gap.py` provides topic gap analysis.
- API endpoint in `routes/admin/api/topic_gap.py`.
- Subagent tool `get_topic_gap_report` registered in `services/subagent/tools.py:451`.

## Hybrid Search
- The hybrid search function is `search_articles()` in `services/search/hybrid.py:329`, NOT `hybrid_search()`.
- Also has `cosine_similarity` (line 41) and `reciprocal_rank_fusion` (line 67).

## Subagent Notes
- **Tool Execution:** `run_subagent_with_tools()` in `services/subagent/runner.py` makes a single `chat_with_tools()` call. Tool results ARE re-injected into messages for subsequent LLM calls within the `max_iterations` loop (`services/llm/base.py:475`). This creates a multi-turn conversation pattern where the LLM can call tools, see results, and call more tools.
- **ToolDefinition:** Actual class in `services/llm/base.py` is a `@dataclass` with fields: `name`, `description`, `parameters`, `required`, `fn`. It does NOT have a `cached` field.
- **Tool Registry:** Thread-safe via `_TOOL_REGISTRY_LOCK`. `_subagent_executor` shutdown via `atexit.register(shutdown_executor)`.
- **Tool Count:** 14 tools total (12 context + 2 search). Registered in `services/subagent/tools.py:306-603`.
- **Tool Middleware Clone:** `run_subagent_with_tools()` at lines 349-355 creates a new `ToolDefinition` object when wrapping functions, preventing middleware compounding on cached tool definitions. Uses `copy.deepcopy(tool.fn)`.
- **Self-Correction Mechanism:** `run_subagent_with_tools()` at lines 401-417 implements a `self_corrected` flag that retries on `ValidationError`. The LLM is given a chance to self-correct its output.
- **_format_subagent_prompt() Helper:** `services/subagent/utils.py` helper function used by `run_subagent_with_tools()` for template formatting with error recovery. Not extensively documented elsewhere.
- **Subagent Chain steps parameter:** `run_subagent_chain()` in `services/subagent/chain.py:62` properly uses passed `steps` parameter or falls back to `chain_config.steps`.
- **Middleware Chain Order:** The middleware chain order is `Logging -> Timing -> ErrorHandling` and they're applied in reverse via `apply_middleware()` in `services/subagent/runner.py`. Application order is reversed: ErrorHandling applied first (innermost), Logging applied last (outermost).
- **ErrorHandlingMiddleware:** Applied at `services/subagent/runner.py:344` to handle errors during tool execution. Note: It re-raises exceptions after logging, does NOT return error dicts.
- **run_stage signature:** `tasks/pipeline.py:353-362` - Selector stage uses `retry_max=20` (hardcoded in `tasks/select.py:202`), not the default 15.
- **max_iterations default:** Both `run_subagent()` and `run_subagent_with_tools()` default `max_iterations` to 5 when not specified in stage_config.

## Dual-Provider Search Architecture
The search system has two parallel provider systems:
1. **`_manager` (web search):** duckduckgo, google, searxng - used by `search_web()` in `services/search/__init__.py`
2. **`_db_search_manager` (article search):** sqlite_fts, hybrid - used by `search_articles()` in `services/search/__init__.py`

DuckDuckGo is the default for web search; Hybrid is for internal article search (hybrid FTS5 + vector similarity).

## Utils Notes
- **utils/text.py:** Contains `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`, `truncate`, `sanitize_html`, `extract_hashtags`. The `sanitize_html()` function strips event handler attributes (onerror, onclick, etc.) and javascript: URIs from HTML content. This was previously a known XSS vulnerability but has been fixed.
- **utils/datetime.py:** Contains `parse_date`, `format_date`, `time_ago` (alias for format_date).
- **utils/security.py:** Contains `generate_token` (using `secrets.token_urlsafe`), `constant_time_compare` (using `hmac.compare_digest`).
- **utils/hash.py:** Contains `generate_hash`, `verify_hash`.
- **utils/html.py:** Contains `strip_tags`, `linkify`, `extract_text`. Note: `strip_tags` fallback uses bare `except Exception` with noqa: BLE001. Also `extract_text` logs a warning when trafilatura is not available.
- **utils/url.py:** Contains global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). Do not assume pure function behavior. Docstring now clarifies this after architecture review.
- **Two truncate() functions:** `utils/text.py:truncate()` breaks on word boundaries; `BaseSourceAdapter._truncate()` (adapters/base.py:104) does not - it just slices.

## services/url.py vs utils/url.py
- **`utils/url.py`:** For adapters (clean layering). Contains SSRF protection implementation.
- **`services/url.py`:** For services (has config support). Re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py`.
- **Config support is dead code:** `_get_dns_cache_config()` function in `services/url.py:60-63` exists but is NEVER called. Both `utils/url.py` and `services/url.py` initialize `_TTLCache` with hardcoded values (`_DNS_CACHE_TTL`, `_DNS_CACHE_MAX`), not from config. Documentation may claim config support but it's not implemented.

## Layer Violation Note
- **schemas/common.py:** This module imports from `services.config_cache`, violating the principle that schemas should have minimal dependencies. This is a known architectural issue requiring decision - either move config caching to utils or accept the violation.

## Known Bugs (RESOLVED)
- **SearchConfig caching bug:** FIXED - `load_search_config()` in `schemas/search.py:31` now uses `config_path = Path(path)` for proper mtime-based cache invalidation when custom paths are passed.

## Known Bugs (OPEN)
- **ResponseCache pubsub leak:** `ResponseCache.get_or_set()` in `services/cache.py:172-183` leaks Redis pubsub connections. When `set(nx=True)` fails, `pubsub.close()` is never called. Compare with `ModelLimiter.acquire()` at `services/limiter.py:81-85` which correctly closes in a `finally` block. Fix: add `pubsub.close()` in the finally block.

## Fixed Bug Patterns

The following bugs were previously encountered and fixed - do not re-fix these:

### ValidationError in Subagent Retry
`services/subagent/runner.py:428` - `ValidationError` must be in `retryable_exceptions` tuple for self-correction to work:
```python
retryable_exceptions=(ProviderTimeoutError, ValidationError, TimeoutError, ConnectionError),
```

### Subagent Chain steps Parameter
`services/subagent/chain.py:62` - `run_subagent_chain` must use passed `steps` parameter:
```python
step_list = steps if steps is not None else chain_config.steps
for i, step_config in enumerate(step_list[:max_length]):
```
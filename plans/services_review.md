# Services Architecture Review Plan

## Verified Claims
- **LLM Provider System**: `services/llm/` exists with `anthropic.py`, `openai.py`, `gemini.py`, `ollama.py` implementations - VERIFIED
- **Circuit Breaker Pattern**: Implemented in `services/circuit_breaker.py` with `CircuitBreaker` and `RedisCircuitBreaker` classes - VERIFIED
- **Rate Limiter (Redis-based)**: Implemented in `services/limiter.py` with Lua scripts for atomic acquire/release and pub/sub notification - VERIFIED
- **Newsletter Pipeline (reader -> writer -> editor)**: `services/newsletter_pipeline.py` implements 3-stage pipeline - VERIFIED
- **Trend Memory Service**: `services/trend_memory.py` with `propose()`, `consolidate()`, `search()` methods - VERIFIED
- **Content Extractor (trafilatura + readability)**: `services/content_extractor.py` uses trafilatura primary, readability fallback - VERIFIED
- **Cost Tracking**: `services/cost_tracker.py` tracks tokens and costs per provider/model - VERIFIED
- **Email Service (SMTP pool)**: `services/email.py` with `SMTPConnectionPool` and connection health checking - VERIFIED
- **Webhook Service (HMAC-SHA256, retry)**: `services/webhooks.py` with encrypted secrets, exponential backoff, idempotency - VERIFIED
- **Cache Service (Redis + in-memory L1)**: `services/cache.py` with `ResponseCache` using LRU eviction - VERIFIED
- **Provider Manager Pattern**: `services/provider_base.py` with `BaseProvider` and `ProviderManager` registry - VERIFIED
- **Search Providers**: `services/search/` with DuckDuckGo, Google, SearxNG, SQLite FTS - VERIFIED
- **Article Services**: `article_parser.py`, `article_validation.py`, `article_fallback.py` all exist - VERIFIED
- **Clean Layering (mostly)**: Most services do NOT import from adapters - VERIFIED (with one exception)

## Discrepancies
- **File naming mismatch**: Architecture doc references `llm/provider_base.py` but actual file is `services/llm/base.py`
- **BaseLLMProvider interface mismatch**: Architecture doc shows abstract methods `complete()` and `embed()`, but actual interface is `chat()`, `chat_streaming()`, `_chat_with_schema()`, `_call_api_with_tools()`, `_extract_text_and_tool_calls()`, `_format_tool_result()`
- **Subagent location**: Architecture doc says subagent is at `subagent/` but AGENTS.md correctly notes it's at `services/subagent/`
- **Limiter provider mismatch**: Architecture doc shows generic `RateLimiter` interface, but newsletter_pipeline.py passes `stage_config.provider` to limiter acquire/release while `get_provider_for_role()` may return a different provider due to fallback - potential bug

## Improvement Recommendations
1. **[MEDIUM]** Rename `services/llm/base.py` to `services/llm/provider_base.py` to match architecture documentation
2. **[MEDIUM]** Update architecture doc to reflect actual `BaseLLMProvider` interface - replace `complete()`/`embed()` with actual methods
3. **[MEDIUM]** Fix limiter provider tracking: When `_run_pipeline_stage` calls `get_provider_for_role()`, it returns `(provider, model, max_tokens, provider_id)` but then uses `stage_config.provider` (configured provider) instead of `provider_id` (actual provider used) for limiter acquire/release. This causes slot leaks when fallback occurs.
4. **[LOW]** Add `embed()` method to `BaseLLMProvider` interface or remove it from architecture docs if not needed
5. **[LOW]** Document the actual 3-stage newsletter pipeline flow more precisely

## Bugs Found
1. **Limiter Slot Leak on Fallback** - `services/newsletter_pipeline.py:122-124`: When provider fallback occurs, `limiter.release()` is called with `stage_config.provider` instead of the actual `provider_id` returned by `get_provider_for_role()`. The slot is acquired under one provider but released under another, causing a slot leak.
2. **Duplicate Import** - `services/llm/__init__.py:11-12`: `load_providers_config` is imported twice from `schemas.llm`

## Layer Violations
- **TYPE_CHECKING import (acceptable)**: `services/crawling.py:13` imports `from adapters.base import RawItem` inside `TYPE_CHECKING` block. Per AGENTS.md, this is the correct pattern for type hints without runtime coupling. Not a violation.
- **URL validation duplication**: `services/url.py` implements URL validation that duplicates `utils/url.py`. AGENTS.md mentions this as a known issue. Adapters correctly import from `utils/url.py` per layering rules.

## Additional Observations
- **`services/url.py` as adapter utility**: Despite being in services/, `url.py` provides SSRF protection that should be used by adapters per layering rules ("Adapters import from utils/url.py for clean layering"). This file should arguably be in `utils/` or the architecture should clarify its role.
- **Email service `get_smtp_config()`**: Uses both Flask `current_app` config and environment variables fallback, which is appropriate for flexibility
- **Circuit breaker in-memory fallback**: `RedisCircuitBreaker` correctly falls back to in-memory when Redis is unavailable, consistent with AGENTS.md fail-closed principle
- **Newsletter pipeline idempotency**: Uses locally-defined `idempotency_key` before use (mentioned in AGENTS.md as a known pattern)

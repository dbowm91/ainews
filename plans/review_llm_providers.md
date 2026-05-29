# Review: LLM Providers Architecture

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- File structure in `services/llm/` matches documentation (`__init__.py`, `base.py`, `openai.py`, `anthropic.py`, `gemini.py`, `ollama.py`, `errors.py`, `types.py`, `json_utils.py`) — all files exist
- `BaseLLMProvider` abstract methods: `_create_client()`, `chat()`, `chat_streaming()` are `@abstractmethod` — `services/llm/base.py:223-252`
- `BaseLLMProvider` concrete methods: `chat_structured()`, `chat_with_tools()` — `services/llm/base.py:254-595`
- `ToolDefinition` dataclass fields: `name`, `description`, `parameters`, `required`, `fn` — no `cached` field — `services/llm/base.py:84-90`
- `ToolCall` dataclass: `id`, `name`, `arguments` — `services/llm/base.py:93-97`
- `ToolCallingResponse` dataclass: `text`, `model`, `tool_calls`, token fields — `services/llm/base.py:107-116`
- `LLMResponse` dataclass: `text`, `model`, token fields, `latency_ms` — `services/llm/base.py:73-81`
- All four provider implementations exist and register via decorators — `services/llm/openai.py`, `anthropic.py`, `gemini.py`, `ollama.py`
- `get_provider_for_role()` signature: `role: str -> Tuple[BaseLLMProvider, str, int, str]` — `services/llm/__init__.py:45-54`
- `get_provider_chain()` is dynamic, determined by `providers.yaml` config order — `services/llm/__init__.py:57-97`
- Circuit breaker integration: `get_breaker()` called in `get_provider_chain()` — `services/llm/__init__.py:64-68`
- `CircuitOpenError` defined in `services/circuit_breaker.py:451-454`, imported into LLM package — `services/llm/__init__.py:13`
- Error classes: `AuthError`, `RateLimitError`, `ProviderServerError`, `ProviderTimeoutError` all exist — `services/llm/errors.py:38-61`
- `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` — `constants.py:17`
- Retry constants: `RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY=1.0`, `RETRY_MAX_DELAY=30.0` — `services/llm/base.py:122-124`
- Retryable errors: `RateLimitError`, `ProviderTimeoutError`, `ProviderServerError`; non-retryable: `AuthError`, `CircuitOpenError` — `services/llm/base.py:169-170`
- `record_provider_success()` signature matches documented `stage` parameter — `services/llm/__init__.py:100-132`
- `record_provider_failure()` exists — `services/llm/__init__.py:135-149`
- `health_check()` method exists on all four providers — `services/llm/openai.py:314`, `anthropic.py:302`, `gemini.py:325`, `ollama.py:285`
- `services/cost_tracker.py` exists with `get_cost_summary()`, `_load_rates()`, `_parse_metric_key()` — `services/cost_tracker.py:69-200`
- `_extract_json()` helper handles markdown-wrapped JSON — `services/llm/base.py:31-62`
- `chat_structured()` validates against `response_model` and retries on failure — `services/llm/base.py:254-341`
- `chat_with_tools()` implements tool-calling iteration loop — `services/llm/base.py:480-595`
- `BaseLLMProvider` inherits from `BaseProvider` — `services/llm/base.py:119`
- `BatchError` exception for batch operations — `services/llm/base.py:65-70`
- `chat_structured_batch()` for parallel structured calls — `services/llm/base.py:343-417`
- `ToolResult` dataclass exists — `services/llm/base.py:100-104`
- Provider manager pattern via `ProviderManager` from `services/provider_base.py` — `services/llm/base.py:608-609`
- `RedisCircuitBreaker` with in-memory fallback — `services/circuit_breaker.py:183-381`
- `_retry_with_backoff` uses `time.sleep()` with exponential backoff — `services/llm/base.py:139-193`
- `_build_messages()` prepends system prompt — `services/llm/base.py:597-605`

## Incorrect Claims

- **`health_check()` listed as key method of `BaseLLMProvider`**
  - Priority: LOW
  - The doc table at line 89 lists `health_check()` as a key method. It's actually inherited from `BaseProvider` (`services/provider_base.py:21-22`), not defined on `BaseLLMProvider`. Each provider overrides it, but the base implementation is on `BaseProvider`. Misleading but not wrong.

- **`record_provider_success()` documented signature incomplete**
  - Priority: MEDIUM
  - The doc at lines 273-279 shows a simplified signature. The actual function accepts additional parameters: `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `article_id` — `services/llm/__init__.py:100-110`. These are important for cost tracking and should be documented.

- **`chat_structured()` retry count description inaccurate**
  - Priority: MEDIUM
  - Doc at line 257 says "Retry up to 2 times on validation failure." The actual behavior: `max_validation_retries` defaults to 2, but the check is `if max_validation_retries > 0:` which means only 1 retry is attempted (not 2). The retry append also increments the counter. — `services/llm/base.py:310`

## Bugs Found

- **`get_provider_chain()` logs warning on every primary provider check**
  - Priority: LOW
  - At `services/llm/__init__.py:74-76`, a `logger.warning()` fires unconditionally after the primary provider check, even when the primary circuit is healthy and was yielded successfully. This produces noise logs. Should only log when actually falling back.

- **`chat_with_tools()` doesn't count tokens on max_iterations exhaustion**
  - Priority: LOW
  - When the tool-calling loop exhausts `max_iterations` (`services/llm/base.py:590-595`), the returned `ToolCallingResponse` has `tokens_used=0`. Token usage from prior iterations is lost. Not a correctness bug but affects cost tracking accuracy.

- **`_retry_with_backoff` catches `ConnectionError` but doc doesn't list it**
  - Priority: LOW
  - `runner.py:193` includes `ConnectionError` in retryable exceptions for subagent, but `base.py:171` does not include `ConnectionError` in the LLM provider retry. Inconsistent behavior.

## Improvement Opportunities

- **Document `chat_structured_batch()` and `BatchError`**
  - Priority: MEDIUM
  - These are significant features (`services/llm/base.py:65-70`, `343-417`) for parallel LLM calls, not mentioned in the doc at all.

- **Document `ToolResult` dataclass**
  - Priority: LOW
  - `services/llm/base.py:100-104` exists but is undocumented.

- **Document `RedisCircuitBreaker` as the default breaker type**
  - Priority: MEDIUM
  - `get_breaker()` creates `RedisCircuitBreaker` instances (`services/circuit_breaker.py:400-405`), not plain `CircuitBreaker`. The doc only describes the basic circuit breaker pattern without mentioning the Redis-backed distributed implementation.

- **Document full `record_provider_success()` signature**
  - Priority: MEDIUM
  - The function now accepts `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `article_id` — important for cost tracking and debugging.

- **Document `_extract_json()` markdown handling**
  - Priority: LOW
  - The function at `services/llm/base.py:31-62` handles markdown-wrapped JSON and brace-extracted JSON. Useful for understanding LLM output parsing behavior.

## Stale Content

- **None detected**
  - All referenced files, classes, and functions exist and are current.

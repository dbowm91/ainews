# Review: LLM Providers

**Reviewed:** 2026-05-31
**Source:** `architecture/llm-providers.md`
**Reviewer:** Subagent 3 (LLM & Search Layer)
**Status:** COMPLETE

---

## Verified Claims

### File Structure
- `services/llm/` directory exists with `__init__.py`, `base.py`, `openai.py`, `anthropic.py`, `gemini.py`, `ollama.py`, `errors.py`, `json_utils.py` — **VERIFIED**
- All 9 files exist at documented paths — **VERIFIED**

### Provider Base Class
- `BaseLLMProvider` inherits from `BaseProvider` and `abc.ABC` — **VERIFIED** (`base.py:82`)
- `default_model: str = ""` class attribute — **VERIFIED** (`base.py:83`)
- `client` property with lazy-loaded singleton and double-checked locking — **VERIFIED** (`base.py:94-100`)
- `_create_client()` abstract method — **VERIFIED** (`base.py:186-189`)
- `chat()` abstract method — **VERIFIED** (`base.py:191-202`)
- `chat_streaming()` abstract method — **VERIFIED** (`base.py:204-215`)
- `chat_structured()` concrete method (not abstract) — **VERIFIED** (`base.py:217-339`)
- `chat_with_tools()` concrete method with tool-calling iteration loop — **VERIFIED** (`base.py:478-593`)

### ToolDefinition Dataclass
- Fields: `name`, `description`, `parameters`, `required`, `fn` — **VERIFIED** (`base.py:47-53`)
- No `cached` field exists — **VERIFIED** (doc's NOTE is accurate)

### Provider Implementations
- `OpenAIProvider` registered as `"openai"` — **VERIFIED** (`openai.py:53`)
- `AnthropicProvider` registered as `"anthropic"` — **VERIFIED** (`anthropic.py:51`)
- `GeminiProvider` registered as `"gemini"` — **VERIFIED** (`gemini.py:35`)
- `OllamaProvider` registered as `"ollama"` — **VERIFIED** (`ollama.py:41`)

### Provider Registry
- `get_provider_for_role()` returns `(provider, model, max_tokens, provider_id)` — **VERIFIED** (`__init__.py:45-54`)
- `get_provider_chain()` is dynamic, determined by providers.yaml config order — **VERIFIED** (`__init__.py:57-97`)
- Circuit breaker integration with `CircuitOpenError` from `services/circuit_breaker.py` — **VERIFIED** (`__init__.py:13`)

### Error Classification
- `AuthError` in `services/llm/errors.py` — **VERIFIED** (`errors.py:46-49`)
- `RateLimitError` with `retry_after` field — **VERIFIED** (`errors.py:38-43`)
- `ProviderServerError` — **VERIFIED** (`errors.py:58-61`)
- `ProviderTimeoutError` — **VERIFIED** (`errors.py:52-55`)
- `CircuitOpenError` in `services/circuit_breaker.py` — **VERIFIED** (`circuit_breaker.py:451-454`)

### Constants
- `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` in `constants.py` — **VERIFIED** (`constants.py:17`)

### Retry Logic
- `_retry_with_backoff()` retries `RateLimitError`, `ProviderTimeoutError`, `ProviderServerError` — **VERIFIED** (`base.py:134`)
- Does NOT retry `AuthError` or `CircuitOpenError` — **VERIFIED** (`base.py:132-133`)
- Uses server `Retry-After` header when available — **VERIFIED** (`base.py:139`)
- Class constants: `RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY=1.0`, `RETRY_MAX_DELAY=30.0` — **VERIFIED** (`base.py:85-87`)

### Cost Tracking
- `services/cost_tracker.py` exists — **VERIFIED**
- `get_cost_summary()` reads from `MetricsCollector` counters — **VERIFIED** (`cost_tracker.py:83-183`)
- `_load_rates()` loads from `COST_RATES` env var — **VERIFIED** (`cost_tracker.py:69-80`)
- `_parse_metric_key()` parses keys like `llm.tokens{model=gpt-4o,provider=openai}` — **VERIFIED** (`cost_tracker.py:186-200`)

### Provider Count
- 14 LLM providers in `providers.yaml` — **VERIFIED** (ollama-local, openai, anthropic, gemini, deepseek, groq, openrouter, xai, togetherai, fireworks, cerebras, zai, minimax, opencode)

### Circuit Breaker Integration
- Circuit breaker keys use role convention: `llm:{provider}:{model}:{role}` — **VERIFIED** (`__init__.py:65,84,114`)
- `record_provider_success()` accepts `stage` parameter — **VERIFIED** (`__init__.py:100-109`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 88-89 | `health_check()` listed as an abstract method in "Key Methods" table | `health_check()` is NOT abstract on `BaseLLMProvider`; it's a concrete method on `BaseProvider` (`provider_base.py:21-22`) returning `{"status": "unknown"}`. Providers override it. | LOW |
| 162 | `get_provider_for_role()` returns `Tuple[BaseLLMProvider, str, int, str]` | Signature is correct but the doc shows a type-hinted signature while actual code (`__init__.py:45`) has no return type annotation | LOW |
| 248 | Doc references `_extract_json()` helper | The actual function is `extract_json()` (no leading underscore) in `json_utils.py:10` | LOW |
| 264-267 | Doc shows simplified `record_provider_success(provider_id, model, tokens_used, stage="")` | Actual signature has additional params: `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `article_id` | MEDIUM |
| 185-188 | `get_provider_chain()` type hint shows `Generator[Tuple[...], None, None]` | Actual function (`__init__.py:57`) has no return type annotation | LOW |
| 216-220 | `_retry_with_backoff()` docstring says "Uses class constants: RETRY_MAX_ATTEMPTS=3, RETRY_BASE_DELAY=1.0, RETRY_MAX_DELAY=30.0" but shows a simplified function signature | Actual signature includes `*args, **kwargs` and type annotations not shown in doc | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | No actual bugs found in the documented architecture. The doc accurately describes the implementation. | — | — | — |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | `chat_structured_batch()` and `BatchError` are undocumented in the Key Files table and architecture overview | maintainability | P2 |
| 2 | `ToolCall`, `ToolResult`, and `ToolCallingResponse` dataclasses are not documented in the "Key Types" section | maintainability | P2 |
| 3 | `chat_structured()` has `max_validation_retries` and `stage` parameters not shown in the doc's signature block | documentation | P2 |
| 4 | The circuit breaker diagram shows hardcoded values (5 failures, 60s timeout) but these are configurable via env vars (`CIRCUIT_BREAKER_FAILURE_THRESHOLD`) | documentation | P3 |
| 5 | `_record_success()` and `_record_failure()` methods on `BaseLLMProvider` are not documented | documentation | P3 |
| 6 | `get_provider()` (without role) and `get_provider_by_id()` functions are not documented | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 248 | References `_extract_json()` helper function | Function is named `extract_json()` (no underscore prefix) in `json_utils.py:10` | update |
| 162-169 | Shows `get_provider_for_role()` and `get_provider_chain()` with type-hinted signatures | Actual code lacks type annotations on these functions | update |

---

## Summary

- Verified: 32 claims
- Incorrect: 6 claims (all LOW/MEDIUM severity, no HIGH)
- Bugs: 0 (HIGH: 0, MEDIUM: 0, LOW: 0)
- Improvements: 6
- Stale items: 2

The document is highly accurate. The main issues are: (1) `health_check()` is incorrectly listed as abstract when it's a concrete method, (2) some function signatures are simplified/omitted compared to actual code, (3) `extract_json` function name has a typo (extra underscore prefix), and (4) `record_provider_success()` signature is incomplete. None of these are critical bugs — they are documentation accuracy issues.

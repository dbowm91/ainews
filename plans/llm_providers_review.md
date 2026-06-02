# LLM Providers Architecture Review

## Summary
The `architecture/llm-providers.md` document is **mostly accurate** but contains several discrepancies and one stale file reference. Most claims about the LLM provider architecture are correct, including the fallback chain dynamics, circuit breaker behavior, retry logic, and error classification.

## Verified Claims

### File Inventory - PARTIALLY CORRECT
**Claim**: "services/llm/ includes `types.py`"
- **Reality**: `types.py` does not exist in `services/llm/`. The directory contains: `__init__.py`, `base.py`, `openai.py`, `anthropic.py`, `gemini.py`, `ollama.py`, `errors.py`, `json_utils.py`
- **Severity**: Minor
- **Location**: `architecture/llm-providers.md:17`
- **Suggested fix**: Remove `types.py` from the architecture diagram. The types `ToolCall`, `ToolResult`, `ToolCallingResponse` are defined in both `services/llm/base.py` (dataclasses, lines 56-79) and `schemas/llm_responses.py` (Pydantic models, lines 186-202).

### BaseLLMProvider Interface - VERIFIED ACCURATE
The abstract methods and properties match the implementation:
- `default_model: str = ""` - `services/llm/base.py:83`
- `client` property (lazy-loaded) - `services/llm/base.py:94-100`
- `_create_client()` abstract - `services/llm/base.py:188-191`
- `chat()` abstract - `services/llm/base.py:193-204`
- `chat_streaming()` abstract - `services/llm/base.py:206-217`
- `chat_structured()` - `services/llm/base.py:219-341` (not abstract, has implementation)
- `chat_with_tools()` - `services/llm/base.py:480-595` (not abstract, has implementation)

### Provider Implementations - VERIFIED ACCURATE
All four providers exist and are properly registered:
- `OpenAIProvider` in `services/llm/openai.py` - registered via `@register_provider("openai")`
- `AnthropicProvider` in `services/llm/anthropic.py` - registered via `@register_provider("anthropic")`
- `GeminiProvider` in `services/llm/gemini.py` - registered via `@register_provider("gemini")`
- `OllamaProvider` in `services/llm/ollama.py` - registered via `@register_provider("ollama")`

### OpenAI-Compatible Providers - VERIFIED ACCURATE
The claim that OpenAIProvider "Handles all providers using the OpenAI API format: OpenAI, DeepSeek, Groq, OpenRouter, xAI, TogetherAI, Fireworks, Cerebras, ZAI, MiniMax, OpenCode" is confirmed by `providers.yaml` which shows all 12 providers using `type: openai`.

### ToolDefinition - VERIFIED ACCURATE
**Claim**: "NOTE: No `cached` field exists on ToolDefinition"
- **Reality**: Confirmed. `ToolDefinition` at `services/llm/base.py:47-53` has fields: `name`, `description`, `parameters`, `required`, `fn`. No `cached` field.
- **Severity**: N/A - this is a correction, not a bug

### Fallback Chain - VERIFIED ACCURATE
**Claim**: "The fallback chain is **dynamic** — determined by enabled providers in `providers.yaml` configuration order"
- **Reality**: Confirmed by `get_provider_chain()` at `services/llm/__init__.py:57-97`. The function:
  1. Gets role config from `pipeline.yaml`
  2. Creates circuit breaker for primary provider
  3. If circuit can execute, yields primary provider
  4. Iterates through all enabled providers in `providers.yaml` order, skipping the primary
  5. Yields each enabled fallback provider that has an open circuit

### Circuit Breaker Constants - VERIFIED ACCURATE
**Claim**: "5 failures, 60s recovery, 120s window"
- **Reality**: Confirmed at `services/llm/__init__.py:19-21`:
  ```python
  _LLM_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
  _LLM_RECOVERY_TIMEOUT = 60.0
  ```
  Default `window_seconds=120.0` is in `services/circuit_breaker.py:46`.

**Claim**: "Closed (normal) ──5 failures──→ Open (blocking) ──60s timeout──→ Half-Open"
- **Reality**: Confirmed by state transition diagram in `services/circuit_breaker.py:25-28` (State enum) and `record_failure()` at lines 124-153.

**Claim**: "Each provider has a circuit breaker"
- **Reality**: Circuit breakers are created per-provider-per-role in `get_provider_chain()` with keys like `f"llm:{provider_id}:{model}:{role}"` at `services/llm/__init__.py:64-68`.

### Retry with Backoff - VERIFIED ACCURATE
**Claim**: "RETRY_MAX_ATTEMPTS=3, RETRY_BASE_DELAY=1.0, RETRY_MAX_DELAY=30.0"
- **Reality**: Confirmed at `services/llm/base.py:85-87`:
  ```python
  RETRY_BASE_DELAY = 1.0
  RETRY_MAX_DELAY = 30.0
  RETRY_MAX_ATTEMPTS = 3
  ```

**Claim**: "Retries on: RateLimitError, ProviderTimeoutError, ProviderServerError"
- **Reality**: Confirmed at `services/llm/base.py:134`:
  ```python
  except (RateLimitError, ProviderTimeoutError, ProviderServerError) as e:
  ```

**Claim**: "Does NOT retry: AuthError, CircuitOpenError"
- **Reality**: Confirmed at `services/llm/base.py:132-133`:
  ```python
  except (AuthError, CircuitOpenError):
      raise
  ```

**Claim**: "Uses server Retry-After header when available"
- **Reality**: Confirmed at `services/llm/base.py:139-140`:
  ```python
  if isinstance(e, RateLimitError) and e.retry_after is not None:
      delay = min(e.retry_after, self.RETRY_MAX_DELAY)
  ```

### Error Classification - VERIFIED ACCURATE
**Claim**: "AuthError, RateLimitError, ProviderServerError, ProviderTimeoutError in services/llm/errors.py"
- **Reality**: Confirmed at `services/llm/errors.py:38-61`

**Claim**: "CircuitOpenError is defined in services/circuit_breaker.py"
- **Reality**: Confirmed at `services/circuit_breaker.py:451-453`

### Cost Tracking - VERIFIED ACCURATE
**Claim**: "get_cost_summary() reads LLM token and call counters from MetricsCollector"
- **Reality**: Confirmed at `services/cost_tracker.py:83-183`. The function reads from `get_metrics().get_metrics()` and parses `llm.tokens`, `llm.input_tokens`, `llm.output_tokens`, `llm.calls` counters.

**Claim**: "_load_rates() loads cost rates from COST_RATES env var or uses defaults"
- **Reality**: Confirmed at `services/cost_tracker.py:69-80`

**Claim**: "_parse_metric_key() parses metric keys like 'llm.tokens{model=gpt-4o,provider=openai}'"
- **Reality**: Confirmed at `services/cost_tracker.py:186-199`

### Timeouts - VERIFIED ACCURATE
**Claim**: "DEFAULT_LLM_TIMEOUT_SECONDS = 120.0 from constants.py"
- **Reality**: Confirmed at `constants.py:17`. All providers import and use this constant.

### Provider Registry - VERIFIED ACCURATE
**Claim**: "get_provider_for_role() returns (provider, model, max_tokens, provider_id)"
- **Reality**: Confirmed at `services/llm/__init__.py:45-54`

**Claim**: "get_provider_chain() yields (provider, model, max_tokens, provider_id) tuples"
- **Reality**: Confirmed at `services/llm/__init__.py:57-97`

### LLM Stage Metrics - VERIFIED ACCURATE
**Claim**: "record_provider_success() accepts stage parameter"
- **Reality**: Confirmed at `services/llm/__init__.py:100-133`. The function records to circuit breaker with stage-aware key and emits metrics with stage label.

### Structured Output - VERIFIED ACCURATE
**Claim**: "chat_structured() uses extract_json() helper"
- **Reality**: Confirmed at `services/llm/base.py:284` (`extract_json(resp)`)

**Claim**: "Retry up to 2 times on validation failure"
- **Reality**: Confirmed at `services/llm/base.py:227` (`max_validation_retries: int = 2`)

### Batch Operations - VERIFIED ACCURATE
**Claim**: "chat_structured_batch() at services/llm/base.py:341"
- **Reality**: `chat_structured_batch` actually starts at line **343** (not 341). The doc is off by 2 lines, but the description is accurate.

### Key Types Table - VERIFIED ACCURATE
**Claim**: "BatchError at services/llm/base.py:28"
- **Reality**: Confirmed at `services/llm/base.py:28-33`

**Claim**: "ToolCall at schemas/llm_responses.py:186"
- **Reality**: Confirmed at `schemas/llm_responses.py:186-189`

**Claim**: "ToolResult at schemas/llm_responses.py:192"
- **Reality**: Confirmed at `schemas/llm_responses.py:192-195`

**Claim**: "ToolCallingResponse at schemas/llm_responses.py:198"
- **Reality**: Confirmed at `schemas/llm_responses.py:198-202`

## Discrepancies Found

### 1. Stale File Reference: `types.py`
- **Claim**: "services/llm/types.py - LLM response types" appears in the architecture diagram
- **Reality**: `services/llm/types.py` does not exist. The equivalent types are:
  - `LLMResponse`, `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolCallingResponse` in `services/llm/base.py` (dataclasses)
  - `ToolCall`, `ToolResult`, `ToolCallingResponse` also in `schemas/llm_responses.py` (Pydantic models)
- **Severity**: Minor (documentation only)
- **Location**: `architecture/llm-providers.md:17`
- **Suggested fix**: Remove `types.py` from the file inventory listing. Add a note clarifying that `ToolCall`, `ToolResult`, and `ToolCallingResponse` exist as both dataclasses in `services/llm/base.py` and Pydantic models in `schemas/llm_responses.py`.

### 2. Line Number Inaccuracy: `chat_structured_batch`
- **Claim**: "`chat_structured_batch()` at `services/llm/base.py:341`"
- **Reality**: The method starts at line **343** (the decorator `@abc.abstractmethod` is at line 343, the def at line 344)
- **Severity**: Minor (documentation only)
- **Location**: `architecture/llm-providers.md:96`
- **Suggested fix**: Update line reference to `:343`

### 3. Missing `health_check()` Documentation
- **Claim**: Table lists `health_check()` as a method but does not document it
- **Reality**: `health_check()` exists on all providers and returns `dict[str, Any]` with provider status
- **Severity**: Minor (gap in documentation)
- **Location**: `architecture/llm-providers.md:89`
- **Suggested fix**: Add `health_check()` to the Key Methods table

## Bugs Identified

No bugs identified. The implementation is consistent with the documented behavior.

## Improvement Opportunities

### 1. Documentation Could Clarify Dual Type Definitions
- **Improvement**: The document notes `ToolCall`, `ToolResult`, `ToolCallingResponse` in `schemas/llm_responses.py` but doesn't mention they also exist as dataclasses in `services/llm/base.py`
- **Location**: `architecture/llm-providers.md:97-99`
- **Benefit**: Clearer understanding of which types to use when

### 2. Document `circuit_protected` Decorator
- **Improvement**: The circuit breaker section mentions "Metrics: Emits circuit state changes" but doesn't document the `@circuit_protected` decorator used by all provider methods
- **Location**: `services/llm/openai.py:73` (example usage)
- **Benefit**: Help developers understand how individual methods are protected

### 3. Document Provider Error Handler Pattern
- **Improvement**: Each provider has a `_handle_*_error()` function that converts SDK exceptions to our custom exceptions. This pattern is documented in `services/llm/errors.py` but not in the architecture doc
- **Location**: `services/llm/openai.py:28-50` (example)
- **Benefit**: Understanding error flow through the provider layer

## Stale Items Found

### 1. `types.py` Reference
- **Item**: Architecture diagram lists `services/llm/types.py`
- **Status**: File does not exist and has never existed (based on git history check)
- **Action**: Remove from documentation

### 2. Provider Count in providers.yaml Header
- **Claim**: "14 LLM providers + 4 search providers" in providers.yaml description
- **Reality**: providers.yaml shows 14 LLM provider entries (ollama-local, openai, anthropic, gemini, deepseek, groq, openrouter, xai, togetherai, fireworks, cerebras, zai, minimax, opencode) and 4 search providers (duckduckgo, google, searxng, hybrid)
- **Status**: ACCURATE - 14 LLM providers confirmed

## Recommendations

1. **High Priority**: Remove `types.py` from the architecture diagram in `architecture/llm-providers.md:17`

2. **Medium Priority**: Update line reference for `chat_structured_batch` from `:341` to `:343` at `architecture/llm-providers.md:96`

3. **Low Priority**: Add `health_check()` to the Key Methods table with description "Provider readiness probe"

4. **Low Priority**: Add note clarifying that `ToolCall`, `ToolResult`, `ToolCallingResponse` exist in both `services/llm/base.py` (dataclasses for internal use) and `schemas/llm_responses.py` (Pydantic models for pipeline responses)

5. **Informational**: Consider adding a section documenting the `@circuit_protected` decorator pattern for future maintainers
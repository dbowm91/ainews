---
name: llm_fallback_chain
description: "LLM provider fallback chain, circuit breaker integration, and provider selection — covering get_provider_chain(), get_provider_for_role(), circuit breaker keys, and stage metrics. Triggers: llm, provider, fallback, circuit breaker, rate limit, openai, anthropic."
---

## Provider Architecture

All LLM providers implement `BaseLLMProvider` from `services/llm/base.py`. Providers are registered in `providers.yaml` and selected dynamically based on circuit breaker state.

## Provider Selection

### get_provider_chain()

`services/llm/__init__.py:get_provider_chain()` iterates through enabled providers in `providers.yaml` order and filters out those with open circuits:

```python
def get_provider_chain(role: str) -> list[tuple[BaseLLMProvider, str, str]]:
    # Returns list of (provider_instance, provider_id, model)
    # Filtered by circuit breaker state
```

### get_provider_for_role()

```python
def get_provider_for_role(role: str) -> tuple[BaseLLMProvider, str, str]:
    """Returns (provider, provider_id, model) tuple for the role."""
```

This is the main entry point for getting an LLM provider. It returns a tuple of (provider_instance, provider_id, model).

## Circuit Breaker Integration

### Circuit Breaker Key Convention

Circuit breaker keys use the **role** convention: `llm:{provider}:{model}:{role}`

```python
# Example keys:
"llm:openai:gpt-4:selector"
"llm:anthropic:claude-3-opus:researcher"
"llm:openai:gpt-4:writer"
"llm:anthropic:claude-3-haiku:editor"
```

### Recording Success/Failure

`record_provider_success(provider_id, model, tokens_used, stage="")` and `record_provider_failure(provider_id, model, stage="", reason="")` in `services/llm/__init__.py` accept `stage=` parameter which must use the role name (e.g., `"selector"`, NOT `"select"`).

### Circuit Breaker Interface

The `CircuitBreaker` in `services/circuit_breaker.py`:
- Constructor requires `name` param: `__init__(self, name: str, failure_threshold=5, ...)`
- Method is `can_execute()` — NOT `is_open()`
- Factory function: `get_breaker(name, failure_threshold=5, ...)`
- Decorator: `circuit_protected(breaker_name, fallback=None)`

## Provider Fallback Chain

The fallback chain is **dynamic** — determined by enabled providers in `providers.yaml` configuration order, not hardcoded. When one provider's circuit opens, the next provider in the chain is used.

### Example Configuration

```yaml
llm_providers:
  - id: openai
    type: openai
    enabled: true
    models:
      - id: gpt-4
        enabled: true
  - id: anthropic
    type: anthropic
    enabled: true
    models:
      - id: claude-3-opus
        enabled: true
  - id: ollama
    type: ollama
    enabled: false
    models:
      - id: llama3
        enabled: false
```

### Fallback Behavior

1. Provider chain is built from enabled providers in order
2. Each provider is checked via `can_execute()` on its circuit breaker
3. First provider with closed circuit is used
4. If all circuits are open, `CircuitOpenError` is raised
5. On success, `record_provider_success()` is called
6. On failure, `record_provider_failure()` is called (may open circuit)

## LLM Stage Metrics

`record_provider_success(provider_id, model, tokens_used, stage="")` includes `stage` label when provided:
- `llm.calls` metric increments with `stage` label
- `llm.tokens` metric tracks `stage`-labeled usage

All pipeline tasks pass `stage=` parameter to `record_provider_success()`:
- select → `selector`
- research → `researcher`
- write → `writer`
- edit → `editor`

## Timeout Handling

All LLM providers use `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` from `constants.py`.

Provider files should import and use this constant rather than hardcoding values.

## Retry with Backoff

`BaseLLMProvider._retry_with_backoff()` retries on `RateLimitError`, `ProviderTimeoutError`, `ProviderServerError` with exponential backoff (base=1s, max=30s). Does NOT retry on `AuthError` or `CircuitOpenError`.

When `RateLimitError` carries a `retry_after` attribute (from server's Retry-After header), that value is used instead of exponential backoff.

Applied to all provider methods via `_do_*` / `_*` internal method pattern.

## Key Files

| File | Purpose |
|------|---------|
| `services/llm/__init__.py` | Provider registry, `get_provider_chain()`, `get_provider_for_role()`, circuit breaker |
| `services/llm/base.py` | `BaseLLMProvider`, `LLMResponse`, `ToolDefinition` |
| `services/llm/openai.py` | OpenAI + OpenAI-compatible (MiniMax, DeepSeek, Zai) |
| `services/llm/anthropic.py` | Native Anthropic API |
| `services/circuit_breaker.py` | `CircuitBreaker`, `get_breaker()`, `circuit_protected()` |
| `services/llm/errors.py` | Error classification (rate limit, auth, server error, timeout) |
| `providers.yaml` | Provider configuration with enabled/disabled state |
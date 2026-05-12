# Services Architecture Review

## Verified Claims

### 1. Clean Layering (Services NOT importing from Adapters)
**VERIFIED** - The clean layering rule is properly implemented:
- `services/crawling.py` uses `TYPE_CHECKING` block for `RawItem` type hint (line 12-13):
  ```python
  if TYPE_CHECKING:
      from adapters.base import RawItem
  ```
  This is the correct pattern - type hints only, no runtime import.

### 2. LLM Provider System (BaseLLMProvider Interface)
**VERIFIED** - The interface is correctly implemented in `services/llm/base.py`:
- Abstract methods: `_create_client`, `chat`, `chat_streaming`, `_chat_with_schema`, `_call_api_with_tools`, `_extract_text_and_tool_calls`, `_format_tool_result`
- Concrete implementations: `chat_structured`, `chat_with_tools`, `_retry_with_backoff`
- Properties: `client` (lazy-loaded)
- All providers (anthropic, openai, gemini, ollama) implement this interface

### 3. Circuit Breaker Pattern
**VERIFIED** - `services/circuit_breaker.py` implements the full circuit breaker:
- States: CLOSED, OPEN, HALF_OPEN with proper transitions
- `CircuitBreaker` (in-memory) and `RedisCircuitBreaker` (distributed) classes
- Sliding window failure counting with `_prune_old_failures()`
- `circuit_protected` decorator for easy integration
- Redis-backed coordination for distributed systems

### 4. Rate Limiter with acquire()/release() in finally block
**VERIFIED** - `services/limiter.py` has proper `ModelLimiter` class:
- `acquire()` returns bool, uses pub/sub for slot coordination
- `release()` properly decrements counters
- Uses Lua scripts for atomic Redis operations

**VERIFIED** - `newsletter_pipeline.py` `_run_pipeline_stage()` uses finally block (lines 118-124):
```python
try:
    result = llm_call(provider, model, max_tokens)
    return result, True
finally:
    limiter.release(
        stage_config.provider, model, stage_config.timeout_seconds,
    )
```

### 5. Cost Tracking Implementation
**VERIFIED** - `services/cost_tracker.py`:
- Tracks tokens used via metrics counters (`llm.tokens`, `llm.calls`)
- Supports configurable rates via `COST_RATES` environment variable
- Default rates for major providers (OpenAI, Anthropic, Gemini, etc.)
- Provides `get_cost_summary()` for aggregated reporting

---

## Discrepancies

### 1. Architecture Document File Location Error
**File**: `architecture/services.md`

The architecture document lists the provider base at:
```
services/llm/provider_base.py    # Abstract base class
```

**Reality**:
- `BaseProvider` (generic provider base) is at `services/provider_base.py`
- `BaseLLMProvider` (LLM-specific abstract class) is at `services/llm/base.py`

The architecture should be updated to reflect the actual file structure.

### 2. utils/url.py Not Pure (Docstring Mismatch)
**File**: `utils/url.py`

The docstring claims:
```python
"""URL normalization and SSRF protection - pure functions and DNS resolution."""
```

**Reality**: Contains global mutable state:
- `_dns_cache` (line 178) - module-level global
- `_dns_cache_lock` (line 179) - module-level global  
- `_dns_executor` (line 126) - ThreadPoolExecutor

This is noted in AGENTS.md but contradicts the docstring. Should either:
- Remove "pure" from docstring, OR
- Refactor to pass cache/executor as parameters

### 3. URL Validation Duplication
**Files**: `utils/url.py` and `services/url.py`

Both implement SSRF protection. As noted in AGENTS.md:
- `utils/url.py` - for adapters (clean layering)
- `services/url.py` - for services (has config support + re-exports from utils)

This is a known duplication but functionally necessary for layer separation.

---

## Improvement Recommendations

### 1. newsletter_pipeline.py: Use actual provider_id from get_provider_for_role
**File**: `services/newsletter_pipeline.py`, lines 106-124

**Current Code**:
```python
provider, model, max_tokens, _ = get_provider_for_role(
    f"newsletter_pipeline.{role}",
)
if limiter.acquire(
    stage_config.provider,  # Uses configured provider
    model,
    ...
):
    try:
        result = llm_call(provider, model, max_tokens)
        return result, True
    finally:
        limiter.release(
            stage_config.provider, model, stage_config.timeout_seconds,
        )
```

**Issue**: When fallback occurs (primary circuit open), the actual provider used differs from `stage_config.provider`. The code discards the returned `provider_id` via `_` and uses the configured `stage_config.provider` for both acquire and release.

**Impact**: Slot leak - the limiter slot is acquired under the fallback provider's key but released under the configured provider's key.

**Recommendation**: Use the actual `provider_id` returned:
```python
provider, model, max_tokens, actual_provider_id = get_provider_for_role(
    f"newsletter_pipeline.{role}",
)
if limiter.acquire(
    actual_provider_id,  # Use actual provider
    model,
    ...
):
    try:
        result = llm_call(provider, model, max_tokens)
        return result, True
    finally:
        limiter.release(
            actual_provider_id, model, stage_config.timeout_seconds,
        )
```

Note: `services/newsletter.py` (line 209-225) already does this correctly - it uses `provider_id` from `get_provider_for_role` for limiter operations.

### 2. services/url.py: Add docstring noting duplication with utils/url.py
**File**: `services/url.py`

Add a note that this module duplicates SSRF protection from `utils/url.py` to provide config support for services layer.

### 3. Circuit Breaker: Consider per-stage circuit keys
**File**: `services/llm/__init__.py`

Currently circuit breakers are keyed by `"llm:{provider}:{model}:{stage}"`. When a provider falls back to another provider, the fallback provider doesn't accumulate failure history for that stage, potentially causing rapid oscillation between providers.

---

## Bugs Found

### BUG-1: Rate Limiter Slot Leak on LLM Fallback
**Severity**: Medium
**File**: `services/newsletter_pipeline.py`, lines 106-124

When the primary LLM provider's circuit is open and a fallback provider is used:
1. `limiter.acquire("anthropic", ...)` is called (using `stage_config.provider`)
2. But the slot is actually acquired under the fallback provider's key (e.g., "openai")
3. `limiter.release("anthropic", ...)` is called (using `stage_config.provider` again)
4. This decrements the "anthropic" counter, NOT the "openai" counter where the slot was acquired

**Result**: Slot leak - the fallback provider's slot counter remains incremented until TTL expires.

**Note**: The AGENTS.md mentions "Limiter Model Mismatch: FIXED" but this appears to be about the model being correct, not the provider_id. The provider_id issue described here remains.

---

## Layer Violations

### LAYER-1: TYPE_CHECKING import from adapters (Acceptable Pattern)
**File**: `services/crawling.py`, line 13

```python
if TYPE_CHECKING:
    from adapters.base import RawItem
```

**Status**: NOT A VIOLATION - This is the correct pattern for type hints without runtime imports. The `TYPE_CHECKING` constant is `False` at runtime, so the import never executes. This follows the pattern described in `AGENTS.md` under "Architecture Conventions - Type Checking Pattern".

---

## Summary

| Aspect | Status |
|--------|--------|
| Clean Layering | PASS |
| BaseLLMProvider Interface | PASS |
| Circuit Breaker Pattern | PASS |
| Rate Limiter finally block | PASS |
| Cost Tracking | PASS |
| Architecture Document Accuracy | PARTIAL (file location error) |
| Rate Limiter provider_id on fallback | FAIL (slot leak bug) |
| utils/url.py purity claim | INACCURATE (docstring) |
| URL validation duplication | KNOWN (by design) |

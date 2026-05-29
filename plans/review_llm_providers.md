# LLM Providers Documentation Review

**Document:** `architecture/llm-providers.md`
**Review Date:** 2026-05-29

---

## Verified Claims

| Claim | Location | Status |
|-------|----------|--------|
| `BaseLLMProvider` abstract methods (`chat`, `chat_streaming`, `_chat_with_schema`, `_call_api_with_tools`, `_extract_text_and_tool_calls`, `_format_tool_result`) | `services/llm/base.py:223-478` | ✅ VERIFIED |
| `ToolDefinition` dataclass fields: `name`, `description`, `parameters`, `required`, `fn` — NO `cached` field | `services/llm/base.py:84-90` | ✅ VERIFIED |
| Provider implementations: `openai.py`, `anthropic.py`, `gemini.py`, `ollama.py` | `services/llm/` | ✅ VERIFIED |
| `get_provider_for_role()` and `get_provider_chain()` in `services/llm/__init__.py` | `services/llm/__init__.py:45-97` | ✅ VERIFIED |
| Circuit breaker integration via `@circuit_protected` decorator | All provider files (e.g., `openai.py:73,128,157,210`) | ✅ VERIFIED |
| Error classification: `AuthError`, `RateLimitError`, `ProviderServerError`, `ProviderTimeoutError` in `services/llm/errors.py` | `services/llm/errors.py:38-61` | ✅ VERIFIED |
| `CircuitOpenError` defined in `services/circuit_breaker.py:451-452`, imported in LLM package | `services/llm/__init__.py:13` | ✅ VERIFIED |
| `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` | `constants.py:17` | ✅ VERIFIED |
| `_retry_with_backoff()` with `RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY=1.0`, `RETRY_MAX_DELAY=30.0` | `services/llm/base.py:122-124,139-193` | ✅ VERIFIED |
| Retry behavior: retries `RateLimitError`, `ProviderTimeoutError`, `ProviderServerError`; does NOT retry `AuthError`, `CircuitOpenError` | `services/llm/base.py:169` | ✅ VERIFIED |
| `CircuitOpenError` is raised only when ALL enabled providers fail | `services/llm/__init__.py:54` | ✅ VERIFIED |
| `get_provider_chain()` is a generator yielding `(provider, model, max_tokens, provider_id)` | `services/llm/__init__.py:57-97` | ✅ VERIFIED |
| `record_provider_success()` with optional `stage` parameter | `services/llm/__init__.py:100-133` | ✅ VERIFIED |
| `record_provider_failure()` exists | `services/llm/__init__.py:135-149` | ✅ VERIFIED |
| `BaseLLMProvider._build_messages()` helper | `services/llm/base.py:597-605` | ✅ VERIFIED |

---

## Incorrect Claims

### 1. Stale Architecture Listing (MEDIUM)
**Location:** `architecture/llm-providers.md:9-18`

**Claim:** The architecture listing shows:
```
├── __init__.py       # Provider registry, get_provider_for_role(), fallback chain
├── base.py           # BaseLLMProvider, LLMResponse, ToolDefinition, ToolCall
├── openai.py         # OpenAI + OpenAI-compatible (DeepSeek, Groq, OpenRouter, xAI, etc.)
├── anthropic.py      # Anthropic Claude (native API)
├── gemini.py         # Google Gemini (native API)
├── ollama.py         # Local Ollama models
├── errors.py         # Error classification (AuthError, RateLimitError, etc.)
├── types.py          # LLM response types
└── json_utils.py     # JSON parsing for structured LLM output
```

**Issue:** `types.py` and `json_utils.py` are listed but:
- `types.py` (50 lines) contains duplicate class definitions (`LLMResponse`, `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolCallingResponse`, `BatchError`) that are ALSO defined in `base.py:73-117`. The primary definitions are in `base.py`.
- `json_utils.py` (41 lines) contains `extract_json()` which is similar to `_extract_json()` in `base.py:31-62` but is a separate file with the same functionality duplicated.

This creates confusion about which types to import. The architecture implies these are core distinct modules when actually `types.py` is orphaned/dead code and `json_utils.py` is a partial duplicate.

**Reference:** `services/llm/types.py`, `services/llm/json_utils.py`

---

### 2. Provider Count Claim Cannot Be Verified (LOW)
**Location:** `architecture/llm-providers.md:310`

**Claim:** "providers.yaml (16 providers)"

**Issue:** The document claims 16 providers but this count cannot be verified from the architecture doc alone. The exact count should be confirmed against `providers.yaml`.

---

## Bugs Found

### 1. Orphaned Duplicate Types File (MEDIUM)
**Location:** `services/llm/types.py`

**Issue:** This file contains class definitions that are duplicates of those in `base.py`:
- `LLMResponse` (base.py:73-81 vs types.py:7-12 — different field sets)
- `ToolDefinition` (base.py:84-90 vs types.py:15-20 — same)
- `ToolCall` (base.py:93-97 vs types.py:23-27 — same)
- `ToolResult` (base.py:100-104 vs types.py:30-34 — same)
- `ToolCallingResponse` (base.py:107-116 vs types.py:37-42 — different field sets)
- `BatchError` (base.py:65-70 vs types.py:45-50 — same)

The `LLMResponse` in `types.py` only has 3 fields (`text`, `model`, `tokens_used`) while `base.py:73-81` has 7 fields. This could cause import confusion.

**Priority:** MEDIUM — creates ambiguity about which types to use

---

### 2. Duplicate JSON Extraction Utilities (LOW)
**Location:** `services/llm/json_utils.py` and `services/llm/base.py:31-62`

**Issue:** `json_utils.py` has `extract_json()` which is nearly identical to `_extract_json()` in `base.py`. The `base.py` version is used internally; `json_utils.py` appears unused or only for specific consumers.

**Priority:** LOW — dead code or underutilized utility

---

## Improvement Opportunities

### 1. Document `_build_messages()` Helper
**Location:** `services/llm/base.py:597-605`

The doc lists key methods in a table (lines 81-89) but `_build_messages()` is a useful helper that isn't documented. Consider adding it.

---

### 2. Clarify `chat_with_tools()` Tool Result Re-injection
**Location:** `services/llm/base.py:480-595`

The document does NOT mention that `chat_with_tools()` re-injects tool results into messages for subsequent LLM calls within the same invocation (line 568-588). The subagent.md correctly notes this at line 155, but llm-providers.md should document it too since it's a key architectural feature.

---

### 3. Document `chat_structured_batch()` Method
**Location:** `services/llm/base.py:343-417`

This method (batch processing with ThreadPoolExecutor) is not documented in llm-providers.md.

---

## Summary

The LLM providers documentation is largely accurate. The main issues are:
1. **Orphaned `types.py`** with duplicate definitions creates import ambiguity (MEDIUM)
2. **Duplicate `json_utils.py`** content (LOW)
3. Architecture listing slightly misleading about `types.py` and `json_utils.py` being primary modules

All functional claims about provider interfaces, error handling, circuit breakers, retry logic, and timeout constants are correct.

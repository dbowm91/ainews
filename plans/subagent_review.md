# Subagent Architecture Review

## Summary

Document `architecture/subagent.md` is **largely accurate** but has several discrepancies and some significant bugs.
The file structure (lines 7-19) is VERIFIED CORRECT. Most claims about ToolDefinition, tool implementations, execution flow, chain system, middleware, and error handling are accurate.

---

## Verified Claims ✅

| Claim | Location | Status |
|-------|----------|--------|
| File inventory matches actual structure | `services/subagent/` | ✅ Verified (10 files) |
| `ToolDefinition` dataclass has name, description, parameters, required, fn | `services/llm/base.py:80-86` | ✅ |
| `ToolDefinition` does NOT have a `cached` field | `services/llm/base.py:80-86` | ✅ Verified |
| Tool functions match documented signatures | `services/subagent/tools.py:18-192` | ✅ |
| `run_subagent()` signature is correct | `services/subagent/runner.py:38-44` | ✅ |
| `run_subagent_with_tools()` signature | `services/subagent/runner.py:296-302` | ✅ |
| `SubagentChainStep` / `SubagentChainConfig` in `schemas/pipeline.py` not runner/chain | `schemas/pipeline.py:108-125` | ✅ Verified |
| Chains use `provider.chat()` not `chat_with_tools()` | `services/subagent/chain.py:120` | ✅ Verified |
| Chain conditions use AST from `conditions.py` | `services/subagent/chain.py:69` | ✅ Verified |
| Middleware uses sync `wrap()` pattern | `services/subagent/middleware.py:13-15` | ✅ |
| `LoggingMiddleware`, `TimingMiddleware` present | `services/subagent/middleware.py:18-61` | ✅ |
| Retry with exponential backoff in `run_subagent_with_tools` | `services/subagent/runner.py:423-429` | ✅ |
| Task revocation checking | `services/subagent/utils.py:19-27` | ✅ |
| Error handling — LLM error retries `max_retries + 1` | `services/subagent/runner.py:189` | ✅ |
| Self-correction re-injects error message | `services/subagent/runner.py:401-408` | ✅ |

---

## Discrepancies & Issues

### 1. CRITICAL: Tool results ARE re-injected into messages (not as documented)

**Document says (line 143-147)**:
> Tool results are NOT re-injected into messages for subsequent LLM calls.

**Actual code** (`services/llm/base.py:490, 557-558`):
```python
if text_content:
    all_messages.append({"role": "assistant", "content": text_content})   # line 490

# ... after tool execution ...
tool_result_msg = self._format_tool_result(tc, result_content)
all_messages.append(tool_result_msg)                                        # line 558
```

This creates a multi-turn conversation loop inside `chat_with_tools()`. The LLM receives tool results and can respond with more tool calls. The loop only exits when the LLM returns no tool calls.

**Impact**: This is the OPPOSITE of what the document claims. The current implementation supports multi-turn tool conversations; the document says it does not. This is a documentation bug, not an implementation bug — but it means users expecting single-shot tool calls will be surprised.

**Recommendation**: Update the document to reflect the actual behavior, or clarify the single-shot vs multi-turn distinction in `run_subagent_with_tools` specifically.

---

### 2. MEDIUM: `_finalize_subagent_result` is defined but unused

**Location**: `services/subagent/runner.py:277-293`

The function is defined in `runner.py` and properly exported in `__init__.py` (line 15-19), but it is NEVER CALLED from within `runner.py`. Instead, the finalization logic is inlined in `run_subagent()` (lines 270-274) and the returned result from `_finalize_subagent_result` is called in `run_subagent_with_tools()` (line 463), but with a different code path for `run_subagent()`.

In `run_subagent()`:
```python
return SubagentResponse(
    synthesis=result.synthesis if result else "",   # inlined
    used_fallback=used_fallback,
    fallback_stages=fallback_stages,
)
```

In `run_subagent_with_tools()`:
```python
return _finalize_subagent_result(...)   # uses the function
```

This inconsistency means `_finalize_subagent_result` is effectively dead code for `run_subagent()` path. Not a bug, but inconsistent.

---

### 3. MEDIUM: `apply_middleware` in `run_subagent_with_tools` mutates tool.fn

**Location**: `services/subagent/runner.py:346-347`
```python
for tool in tools:
    if tool.fn:
        tool.fn = apply_middleware(tool.fn, middleware_chain)
```

This mutates the `fn` attribute on the `ToolDefinition` objects passed in. Since `tools` comes from `initialize_tool_registry()` which returns cached tool definitions (via `_get_all_tools_cached()`), this means the cached tool definitions' `fn` attributes are permanently modified after the first call with middleware applied.

**Impact**: 
1. First call applies middleware; subsequent calls have middleware applied to already-wrapped functions (compounding wrappers)
2. `run_subagent()` (line 117) also calls with tools but the middleware application doesn't happen there — this creates inconsistent state between the two entry points

**Recommendation**: Clone tool definitions before applying middleware, or apply middleware at registration time in `initialize_tool_registry()`.

---

### 4. MEDIUM: Chain execution uses direct `provider.chat()`, not tool-aware

**Verified correct**: Document says chains use `provider.chat()` directly, not `chat_with_tools()`. This is correct — `chain.py:120` uses `provider.chat()`.

But the document doesn't mention that chain steps also don't use the executor's timeout properly. At `chain.py:130-133`:
```python
resp = _retry_with_backoff(
    lambda: _subagent_executor.submit(_chain_call).result(
        timeout=stage_config.timeout_seconds
    ),
    ...
)
```

The `_chain_call()` captures `provider` from a closure. If the provider was obtained via `get_provider_for_role()` which involves the circuit breaker, this could lead to issues if the provider is not thread-safe or if the captured provider state becomes stale across retries.

---

### 5. LOW: `tool.fn` check uses `hasattr` + `callable`

**Location**: `services/llm/base.py:471`
```python
if hasattr(tool, "fn") and callable(tool.fn):
```

The document doesn't specify how `fn` is checked. This works but could be simplified to just check if `fn` is not None since `ToolDefinition` always has `fn` as an optional field.

---

### 6. LOW: `get_registered_tools` in registry.py not referenced elsewhere

The function `get_registered_tools()` in `registry.py:24-26` is defined but not used by any caller. It returns the raw `_TOOL_REGISTRY` dict values. The `initialize_tool_registry()` function is the one actually used. This is dead code but harmless.

---

### 7. LOW: `_TOOL_REGISTRY` initialization is lazy on first `initialize_tool_registry` call

**Location**: `registry.py:59-62`
```python
with _TOOL_REGISTRY_LOCK:
    if not _TOOL_REGISTRY:
        for tool in all_tools:
            register_tool(tool)
```

If someone calls `get_registered_tools()` before `initialize_tool_registry()`, they get an empty dict. This is not a problem currently since `get_registered_tools()` is unused, but it's a latent issue if that function is used in the future.

---

### 8. LOW: `run_subagent_with_tools` doesn't log `subagent.start` for mid-execution events

The `log_pipeline_event` calls at lines 316-322 only log at start, not when self-correction happens. When the validation error triggers a retry with re-injected message (lines 401-408), no pipeline event is logged for that intermediate step.

---

### 9. CRITICAL BUG: `chain.py` doesn't use `SubagentChainStep` from `schemas/pipeline.py`

**Location**: `services/subagent/chain.py:65`

The `for` loop iterates over `step_list` (which comes from either `steps` parameter or `chain_config.steps`) and accesses `step_config.task_type`, `step_config.prompt_data_template`, `step_config.condition`.

The schema `SubagentChainStep` (in `schemas/pipeline.py:108-112`) defines these fields. But `chain.py` uses `step_config` attributes directly without validation against the schema. If an invalid step config is passed (e.g., missing `task_type`), the code will fail with an `AttributeError` rather than a validation error.

More critically, `run_subagent_chain()` at line 36 has signature:
```python
def run_subagent_chain(
    chain_name: str,
    steps: list[dict],
    ...
```

But `chain_config.steps` is `list[SubagentChainStep]` (schema-validated). The parameter `steps: list[dict]` allows any dict, bypassing schema validation. When called from `run_subagent_chain()` with the default `steps=None`, it uses `chain_config.steps` which IS properly typed. But when called with a custom `steps` list, no validation occurs.

---

### 10. HIGH: `chat_with_tools` silent fallback returns empty on max iterations

**Location**: `services/llm/base.py:560-565`
```python
return ToolCallingResponse(
    text="",
    model=model,
    tool_calls=[],
    tokens_used=0,
)
```

When `max_iterations` is reached (the LLM keeps calling tools), `chat_with_tools` returns an empty response. The `run_subagent_with_tools` at line 388 does:
```python
tc_resp = future.result(timeout=stage_config.timeout_seconds)
```

And then at line 390-392:
```python
return response_model.model_validate(
    {"synthesis": tc_resp.text},   # tc_resp.text is ""
)
```

This will cause a `ValidationError` which triggers self-correction logic. But if `self_corrected` is already True (we've already retried once), at line 394 it raises the error. So after max iterations of tool calls, the response is an empty string that fails validation and triggers fallback.

**Impact**: This is actually correct behavior (empty tool result = fallback), but it's not documented.

---

## Layering Violations

### 1. `services/subagent/tools.py` imports from `models` and `extensions`

**Location**: `services/subagent/tools.py:105-106, 127-128, 146-147`

```python
from extensions import db      # line 105
from models import Article    # line 106
from models import Article    # line 128
from extensions import db     # line 146
from models import Source      # line 147
```

This is documented in a comment at lines 12-15:
> Layering note: tools.py imports directly from models and extensions for runtime use (not just type hints). This is a known layering violation per AGENTS.md.

**Assessment**: Acceptable given documented constraints, but fragile. If the models layer changes, tools break without adapter-layer protection.

---

### 2. `services/subagent/chain.py` imports from `schemas.pipeline` at runtime

**Location**: `services/subagent/chain.py:48`

```python
from schemas.pipeline import load_pipeline_config, resolve_subagent_config
```

This happens inside the function, not at module level, which is fine for avoiding circular imports. No actual layering violation.

---

## Specific Bugs (file:line)

| Bug | File | Line | Severity |
|-----|------|------|----------|
| Tool definitions mutated after first `run_subagent_with_tools` call (middleware compounding) | `services/subagent/runner.py` | 346-347 | MEDIUM |
| `_finalize_subagent_result` unused in `run_subagent()` path | `services/subagent/runner.py` | 270-274 vs 463 | MEDIUM |
| `run_subagent_chain()` accepts `list[dict]` bypassing schema validation for `steps` param | `services/subagent/chain.py` | 36, 62 | HIGH |
| Silent empty return when `chat_with_tools` hits max iterations | `services/llm/base.py` | 560-565 | MEDIUM (documented behavior but unclear) |
| `get_registered_tools()` returns empty before `initialize_tool_registry()` called | `services/subagent/registry.py` | 24-26 | LOW |

---

## Recommendations

| Priority | Issue | Recommendation |
|----------|-------|----------------|
| CRIT | Document says "tool results NOT re-injected" but they ARE re-injected | Update `architecture/subagent.md` line 143-147 to reflect actual multi-turn behavior |
| CRIT | `run_subagent_chain` accepts `list[dict]` for `steps` bypassing schema validation | Add runtime validation: `SubagentChainStep.model_validate(step_config)` in the loop, or change `steps: list[dict]` to `steps: list[SubagentChainStep]` parameter type |
| HIGH | Middleware application mutates cached `ToolDefinition.fn` | Clone tools before applying middleware: `tool_fn = copy(tool.fn)` or apply middleware at registration time in `initialize_tool_registry()` |
| MED | `_finalize_subagent_result` inconsistent usage | Either remove the function (dead code) or use it consistently in `run_subagent()` as well |
| MED | `get_registered_tools()` returns empty before initialization | Document the initialization order dependency, or add lazy initialization |
| LOW | No pipeline event logged during self-correction retry | Add `log_pipeline_event(..., event="subagent.retry")` before re-injecting the correction message |

---

## Performance Concerns

1. **Middleware compounding**: The mutation issue (runner.py:346-347) could cause performance degradation over time as middleware wrappers compound on cached tool definitions.

2. **LRU cache on `_get_all_tools_cached`**: Uses `maxsize=1` which is fine (only caches the tuple of all tools), but the cache is never invalidated. If tools are added dynamically, the cache won't reflect changes.

3. **Thread pool `_subagent_executor`**: Created at module load in `config.py:11`. If `SUBAGENT_WORKERS` env var is set very high, could cause memory issues. Default of 8 is reasonable.

---

## Security Concerns

1. **AST-based condition evaluation** (`conditions.py`): Uses allowlist of operators, blocks dunder access. This is a good pattern. ✅

2. **`escape_prompt_data`** used in both `runner.py:66` and `utils.py:32`. This prevents XML injection. ✅

3. **`_context_tool_get_article_by_id`** returns JSON with `article_id` as integer — no SQL injection possible via SQLAlchemy parameterized queries. ✅

4. **No SSRF concerns** in subagent tools — web search goes through `services/search/` which has its own validation.

---

## Conclusion

The document `architecture/subagent.md` is mostly accurate and well-structured. The primary issues are:

1. **Documentation bug**: Claims tool results are NOT re-injected, when they actually ARE
2. **Schema validation bypass**: `run_subagent_chain()` accepts unvalidated `list[dict]` for steps
3. **Mutation of cached tool definitions**: Middleware application permanently changes cached `ToolDefinition.fn`

These should be addressed to bring documentation and implementation into alignment.
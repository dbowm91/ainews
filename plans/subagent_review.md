# Subagent Architecture Review - Improvement Plan

## Summary

Reviewed `architecture/subagent.md` against the actual codebase in `services/subagent/`. Most claims are accurate, but several issues were found.

---

## Verified Claims

### File Inventory ✅
All files match exactly:
- `__init__.py`, `chain.py`, `conditions.py`, `config.py`, `middleware.py`, `prompt_templates.py`, `registry.py`, `runner.py`, `tools.py`, `utils.py`

### ToolDefinition Structure ✅
`services/llm/base.py:80-86` - No `cached` field - matches documentation.

### Tool Registry ✅
`services/subagent/registry.py:15-16` - `_TOOL_REGISTRY: dict[str, ToolDefinition] = {}` - matches.

### Built-in Tools ✅
All 9 tool names and functions match implementation:
- `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `web_search`, `get_search_provider`

### Schema Location ✅
`schemas/pipeline.py:108-125` - `SubagentChainStep` and `SubagentChainConfig` are correctly documented as being in `schemas/pipeline.py`, not `runner.py` or `chain.py`.

### Middleware Classes ✅
`middleware.py:10-81` - All three middleware classes (`LoggingMiddleware`, `TimingMiddleware`, `ErrorHandlingMiddleware`) match documentation.

### Chain Config ✅
`pipeline.yaml:178+` has `subagent.chains` section.

---

## Discrepancies and Issues

### 1. BUG: Self-Correction in `run_subagent_with_tools` Never Executes

**Location:** `services/subagent/runner.py:422-429`

**Issue:** The self-correction code (lines 393-409) appends an error message to `messages` and sets `self_corrected = True`, then re-raises. However, the re-raised `ValidationError` is caught by the exception handler at line 449, which sets `used_fallback = True` and returns. The `_retry_with_backoff` at line 423 only retries on `(ProviderTimeoutError, TimeoutError, ConnectionError)` - `ValidationError` is NOT in `retryable_exceptions`.

```python
# Line 422-429
try:
    result = _retry_with_backoff(
        _attempt,
        max_retries=stage_config.max_retries + 1,
        base_delay=1.0,
        max_delay=stage_config.retry_delay,
        retryable_exceptions=(ProviderTimeoutError, TimeoutError, ConnectionError),  # ValidationError NOT included!
    )
except (ValidationError, json.JSONDecodeError, ValueError, AttributeError) as e:  # ValidationError caught here
    last_exc = e
    ...
    used_fallback = True
    fallback_stages = [stage]
```

**Impact:** Self-correction never triggers on validation errors - the code appends a user correction message but then immediately returns with fallback instead of letting the retry loop continue with the corrected messages.

**CRIT**

### 2. BUG: `run_subagent_chain` Ignores `steps` Parameter

**Location:** `services/subagent/chain.py:36-57`

**Issue:** The `steps` parameter is completely ignored:

```python
def run_subagent_chain(
    chain_name: str,
    steps: list[dict],  # This parameter is never used!
    initial_prompt_data: dict,
    article_id: int | None = None,
) -> dict[str, Any]:
    ...
    config = load_pipeline_config()
    chain_config = config.subagent.chains.get(chain_name)  # Steps come from config, not parameter
```

**Impact:** Callers cannot pass steps programmatically - they must configure chains in `pipeline.yaml`. This makes the API inflexible.

**HIGH**

### 3. BUG: Middleware Wrapping Ineffective for Tool Calls via `chat_with_tools`

**Location:** `services/subagent/runner.py:340-347` and `services/llm/base.py:469-558`

**Issue:** In `run_subagent_with_tools`, middleware wraps `tool.fn`:

```python
for tool in tools:
    if tool.fn:
        tool.fn = apply_middleware(tool.fn, middleware_chain)
```

However, `provider.chat_with_tools()` in `base.py:469-472` builds its own `tool_call_map`:

```python
tool_call_map: dict[str, tuple[str, Callable]] = {}
for tool in tools:
    if hasattr(tool, "fn") and callable(tool.fn):
        tool_call_map[tool.name] = (tool.name, tool.fn)
```

The middleware wrapping happens BEFORE the tool is passed to the provider, and the provider copies the `fn` reference. When `_call_api_with_tools` executes (line 528), it calls `fn(**fn_args)` directly from the map, so the wrapped function IS called.

Actually, upon closer inspection, the wrapping DOES work because `tool.fn` is modified in place before being passed to the provider. The provider then copies the reference to `tool_call_map`. So this is NOT a bug. 

**VERIFIED - NOT AN ISSUE**

### 4. Chain Execution Uses `provider.chat()`, Not `chat_with_tools`

**Location:** `services/subagent/chain.py:118-125`

**Issue:** `run_subagent_chain` uses `provider.chat()` instead of `provider.chat_with_tools()`:

```python
def _chain_call():
    return provider.chat(  # Not chat_with_tools!
        messages=[{"role": "user", "content": prompt}],
        model=model,
        system=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

The documentation implies chains support multi-step tool calling, but chains only support simple chat completion.

**MED**

### 5. Documentation Shows Code Blocks for Schema Definitions

**Location:** `architecture/subagent.md:115-125`

**Issue:** The document shows `SubagentChainStep` and `SubagentChainConfig` defined with Pydantic-like syntax in a code block labeled as being in `runner.py`, which is misleading. While the note at line 127 says "These schemas are defined in `schemas/pipeline.py`", the code block presentation is confusing.

**LOW** (documentation clarity issue)

### 6. Layering Violation: `tools.py` Imports from `models` and `extensions`

**Location:** `services/subagent/tools.py:12-16`

**Issue:** Despite AGENTS.md documentation noting this as a known issue:

```python
# Layering note: tools.py imports directly from models and extensions for runtime
# use (not just type hints). This is a known layering violation per AGENTS.md.
```

The violation exists in:
- `tools.py:105-106` (imports `extensions` and `models`)
- `tools.py:128-129` (imports `models`)
- `tools.py:146-147` (imports `extensions` and `models`)

**MED** (documented but still a concern)

---

## Specific Bugs

| # | File | Line | Issue |
|---|------|------|-------|
| 1 | `runner.py` | 422-429 | Self-correction never executes because `ValidationError` is not in `retryable_exceptions` |
| 2 | `chain.py` | 36-57 | `steps` parameter is ignored entirely |

---

## Recommendations

### CRIT
1. **Fix self-correction retry logic** (`runner.py:422-429`)
   - Add `ValidationError` to `retryable_exceptions` OR
   - Remove the self-correction code block since it never executes (lines 393-409)

### HIGH
2. **Honor `steps` parameter in `run_subagent_chain`** (`chain.py:36-57`)
   - Use passed steps if provided, fall back to config steps
   - Or document that chains are config-only

### MED
3. **Consider adding tool support to chains** (`chain.py:118-125`)
   - Either document that chains don't support tools, or implement `chat_with_tools` support

4. **Document middleware limitations** for tool-calling in `run_subagent_with_tools`

### LOW
5. **Improve documentation clarity** for schema definitions in `architecture/subagent.md`

6. **Resolve layering violation** in `tools.py` by creating service-layer helpers (long-term)

---

## Verification Commands

Run these to verify fixes:
```bash
ruff check services/subagent/
mypy services/subagent/ --ignore-missing-imports
pytest tests/test_subagent*.py -v
```
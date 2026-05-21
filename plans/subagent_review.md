# Subagent Architecture Review - Improvement Plan

## Summary

The `architecture/subagent.md` document is largely accurate but has several discrepancies between documented patterns and actual implementation. Key issues include: duplicate code, incorrect execution flow documentation, layering violations, and missing implementations.

---

## Verified Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| File inventory (10 files) | ✅ VERIFIED | All files present: `__init__.py`, `chain.py`, `conditions.py`, `config.py`, `middleware.py`, `prompt_templates.py`, `registry.py`, `runner.py`, `tools.py`, `utils.py` |
| `ToolDefinition` has no `cached` field | ✅ VERIFIED | `services/llm/base.py:81-86` confirms dataclass fields: `name`, `description`, `parameters`, `required`, `fn` |
| `_TOOL_REGISTRY` is `dict[str, ToolDefinition]` | ✅ VERIFIED | `services/subagent/registry.py:15` |
| AST-based condition evaluation | ✅ VERIFIED | `services/subagent/conditions.py` uses `ast.parse()` with allowlisted operators |
| Middleware uses sync `wrap()` pattern | ✅ VERIFIED | `services/subagent/middleware.py:10-90` |
| Tool functions are module-level | ✅ VERIFIED | All tool functions in `tools.py` are module-level |
| `SubagentChainStep` and `SubagentChainConfig` exist | ✅ VERIFIED | Defined in `schemas/pipeline.py:107-124` (NOT in runner.py) |

---

## Discrepancies and Issues

### 1. CRIT: Duplicate `_finalize_subagent_result()` Function (Not Called)

**Location:** `services/subagent/runner.py:277-335`

**Issue:** The function `_finalize_subagent_result()` is defined at line 277 but `run_subagent()` at line 270 manually implements the same logic inline instead of calling the helper. Only `run_subagent_with_tools()` at line 505 actually calls `_finalize_subagent_result()`.

```python
# Line 270-274 in run_subagent():
return SubagentResponse(
    synthesis=result.synthesis if result else "",
    used_fallback=used_fallback,
    fallback_stages=fallback_stages,
)
```

This is duplicate code - the same return value construction is done by `_finalize_subagent_result()` at line 331-335 but NOT called by `run_subagent()`.

**Fix:** Have `run_subagent()` call `_finalize_subagent_result()` instead of inline construction.

---

### 2. CRIT: Documentation Inaccurately Describes Tool Execution Flow

**Location:** `architecture/subagent.md:136-144`

**Issue:** The "Execution Flow" section states:
```
3. If tool_calls:
   a. Execute tools in parallel
   b. Add results to messages
   c. Goto 2 (max iterations)
```

This describes re-injecting tool results into messages for subsequent LLM calls. However, actual implementation:
- `run_subagent_with_tools()` makes a **single** call to `provider.chat_with_tools()`
- The iteration loop is **inside** `BaseLLMProvider.chat_with_tools()` (`services/llm/base.py:475`)
- Tool results ARE re-injected in `base.py:537-558` within the loop

So the loop exists, but it's in the base provider class, not as a separate step in the runner. The documentation is misleading because it shows `run_subagent_with_tools` doing the loop, when actually `chat_with_tools()` does it.

**Fix:** Update execution flow diagram to show that tool iteration happens inside `chat_with_tools()`.

---

### 3. HIGH: `chain.py` Uses Manual Escaping Instead of `escape_prompt_data()`

**Location:** `services/subagent/chain.py:99-107`

**Issue:** Chain's `_resolve_template_variables()` and prompt building use manual `esc_xml_text()` instead of the recommended `escape_prompt_data()` utility:

```python
from utils.text import esc_xml_text

prompt_data_escaped = {}
for key, value in prompt_data.items():
    if isinstance(value, str):
        prompt_data_escaped[key] = esc_xml_text(value)
    else:
        prompt_data_escaped[key] = value
```

This doesn't handle nested dicts/lists properly, while `escape_prompt_data()` in `utils/text.py:36-50` does.

**Fix:** Use `escape_prompt_data(prompt_data)` instead of manual loop.

---

### 4. MED: Layering Violation - `tools.py` Imports From `models` Directly

**Location:** `services/subagent/tools.py:100-101, 123, 141-142`

**Issue:** Tools import directly from `extensions` and `models`:
```python
from extensions import db
from models import Article

from models import Article

from extensions import db
from models import Source
```

According to `AGENTS.md` principles, services should not import directly from models. However, `tools.py` is part of `services/subagent`, so this is a self-violation. The imports are done inside functions to avoid circular dependency issues, but the layering is still violated.

**Fix:** Move database access to a helper in `services/` layer (e.g., a new `context_service.py` function or use existing service functions).

---

### 5. MED: Documentation Shows Classes in Wrong Location

**Location:** `architecture/subagent.md:115-124`

**Issue:** The documentation shows `SubagentChainStep` and `SubagentChainConfig` as part of `runner.py`:
```python
class SubagentChainStep(BaseModel):  # line 115
class SubagentChainConfig(BaseModel):  # line 121
```

These are actually defined in `schemas/pipeline.py:107-124`. The documentation implies they're in `runner.py` but they're schema models, not runner logic.

**Fix:** Update documentation to reference `schemas/pipeline.py` for these classes, or note that they're in `schemas/` not `services/subagent/runner.py`.

---

### 6. MED: `run_subagent()` Doesn't Use `_format_subagent_prompt()`

**Location:** `services/subagent/runner.py:64-67`

**Issue:** `run_subagent()` does its own escaping and template resolution:
```python
prompt_data_escaped = escape_prompt_data(prompt_data)
prompt = template.format(**prompt_data_escaped)
```

But `run_subagent_with_tools()` uses `_format_subagent_prompt()` from `utils.py:30-41`:
```python
prompt = _format_subagent_prompt(template, prompt_data, stage, task_type)
```

The two functions handle template errors differently - `run_subagent()` catches `KeyError` and returns fallback, while `_format_subagent_prompt()` returns `None` on error. This inconsistency could cause confusion.

**Fix:** Use consistent prompt formatting approach in both functions.

---

### 7. LOW: Missing `max_iterations` in Direct `run_subagent()` Path

**Location:** `services/subagent/runner.py:143-151`

**Issue:** In `run_subagent()` without tools, it calls `provider.chat_structured()` instead of `chat_with_tools()`. There's no `max_iterations` because there's no tool loop. But the doc claims all subagent paths support tool calling with iteration.

The tool-calling path (with tools) at line 119-128 does pass `max_iterations` to `chat_with_tools()`, but this is only when `stage_config.tools` is configured. The documentation doesn't clarify this conditional behavior.

**Fix:** Document that tool iteration only occurs when tools are configured.

---

### 8. LOW: Doc Says "max 3 attempts" but Actual is `stage_config.max_retries + 1`

**Location:** `architecture/subagent.md:268`

**Issue:** Document says "LLM error: Retries with exponential backoff (max 3 attempts)". Actual implementation uses:
```python
result = _retry_with_backoff(
    _attempt,
    max_retries=stage_config.max_retries + 1,  # default is 1, so 2 attempts
    ...
)
```

Default `max_retries` is 1 (see `schemas/pipeline.py:100`), so actual max attempts is 2, not 3.

**Fix:** Update to reflect actual config: `max_retries + 1` from stage config (default 2 attempts).

---

## Specific Bugs

### BUG-1: Duplicate Return Value Construction

**File:** `services/subagent/runner.py:270-274` vs `services/subagent/runner.py:331-335`

The same `SubagentResponse` construction is done twice:
- Inline at lines 270-274 in `run_subagent()`
- In `_finalize_subagent_result()` at lines 331-335

`run_subagent()` should call `_finalize_subagent_result()` to avoid duplication.

---

### BUG-2: Inconsistent Error Handling Between `run_subagent` and `run_subagent_with_tools`

**Files:** `services/subagent/runner.py:68-94` vs `services/subagent/runner.py:366-373`

`run_subagent()` catches `KeyError` during template formatting and returns fallback. `run_subagent_with_tools()` uses `_format_subagent_prompt()` which returns `None` on error, then checks for `None` and returns fallback. The error messages and logging differ between these paths.

---

## Improvement Recommendations

| Priority | Issue | Recommendation |
|----------|-------|-----------------|
| CRIT | Duplicate `_finalize_subagent_result()` | Refactor `run_subagent()` to call `_finalize_subagent_result()` |
| CRIT | Documentation execution flow | Update arch doc to reflect that tool iteration is inside `chat_with_tools()` |
| HIGH | chain.py manual escaping | Replace manual escaping with `escape_prompt_data()` |
| MED | tools.py model imports | Create service layer helper to avoid direct model imports |
| MED | Class location in doc | Fix doc to reference `schemas/pipeline.py` for chain classes |
| MED | Inconsistent prompt formatting | Unify `run_subagent()` and `run_subagent_with_tools()` prompt handling |
| LOW | Missing max_iterations doc | Clarify that iteration only occurs with tools configured |
| LOW | Retry count doc | Fix "max 3 attempts" to reflect actual config |

---

## Files Reviewed

- `services/subagent/__init__.py`
- `services/subagent/runner.py`
- `services/subagent/tools.py`
- `services/subagent/registry.py`
- `services/subagent/chain.py`
- `services/subagent/conditions.py`
- `services/subagent/config.py`
- `services/subagent/middleware.py`
- `services/subagent/utils.py`
- `services/subagent/prompt_templates.py`
- `services/llm/base.py`
- `schemas/pipeline.py`
- `utils/text.py`
- `tests/test_subagent_chain.py`
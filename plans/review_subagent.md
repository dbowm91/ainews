# Subagent System Documentation Review

**Document:** `architecture/subagent.md`
**Review Date:** 2026-05-29

---

## Verified Claims

| Claim | Location | Status |
|-------|----------|--------|
| Tool registry in `registry.py` with `_TOOL_REGISTRY` dict | `services/subagent/registry.py:15` | ✅ VERIFIED |
| **14 tools total**: 12 context + 2 search | `services/subagent/tools.py:306-603` | ✅ VERIFIED |
| Context tools: `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost` | `services/subagent/tools.py:306-558` | ✅ VERIFIED |
| Search tools: `web_search`, `get_search_provider` | `services/subagent/tools.py:563-603` | ✅ VERIFIED |
| `run_subagent()` signature: `(task_type, stage, prompt_data, response_model, article_id)` | `services/subagent/runner.py:39-45` | ✅ VERIFIED |
| `run_subagent_with_tools()` signature | `services/subagent/runner.py:297-304` | ✅ VERIFIED |
| `SubagentChainStep` and `SubagentChainConfig` are defined in `schemas/pipeline.py`, NOT in `runner.py` or `chain.py` | `schemas/pipeline.py:108-125` | ✅ VERIFIED |
| Chain uses `provider.chat()` directly, not `chat_with_tools()` — no tool support in chains | `services/subagent/chain.py:121-128` | ✅ VERIFIED |
| Middleware classes: `LoggingMiddleware`, `TimingMiddleware`, `ErrorHandlingMiddleware` | `services/subagent/middleware.py:18-80` | ✅ VERIFIED |
| Middleware chain applied in reverse via `apply_middleware()` | `services/subagent/middleware.py:83-91` | ✅ VERIFIED |
| Middleware `wrap()` pattern with sync wrapping | `services/subagent/middleware.py:13-15` | ✅ VERIFIED |
| Prompt templates in `prompt_templates.py` with `SUBAGENT_TASK_TEMPLATES` dict | `services/subagent/prompt_templates.py:7-45` | ✅ VERIFIED |
| `load_prompt_template()` function | `services/subagent/prompt_templates.py:48-56` | ✅ VERIFIED |
| Conditions AST-based evaluation via `_evaluate_condition()` | `services/subagent/conditions.py:128-157` | ✅ VERIFIED |
| Chain execution uses index, not name | `services/subagent/chain.py:63` (`step_name = f"{chain_name}_step_{i}"`) | ✅ VERIFIED |
| `ErrorHandlingMiddleware` re-raises exceptions (not return error dicts) | `services/subagent/middleware.py:70-78` | ✅ VERIFIED |
| Tool results ARE re-injected into messages within `chat_with_tools()` | `services/llm/base.py:567-588` | ✅ VERIFIED |
| Tool iteration happens in `chat_with_tools()` while loop at `services/llm/base.py:505` | `services/llm/base.py:504-595` | ✅ VERIFIED |

---

## Incorrect Claims

### 1. Middleware Chain Order Description is Confusing (MEDIUM)
**Location:** `architecture/subagent.md:200-203`

**Claim:**
```
**Middleware chain order (outer to inner):**
1. `LoggingMiddleware` - logs tool call start/completion/failure
2. `TimingMiddleware` - measures and logs execution time
3. `ErrorHandlingMiddleware` - catches exceptions, logs them with traceback, then re-raises
```

**Issue:** The doc says "outer to inner" with this order. But `apply_middleware()` at `middleware.py:83-91` applies in **reverse** order:

```python
for middleware in reversed(middleware_chain):
    wrapped = middleware.wrap(wrapped)
```

So with `[LoggingMiddleware, TimingMiddleware, ErrorHandlingMiddleware]` as the list, the actual execution order (outermost to innermost) is:
1. `LoggingMiddleware` (outermost - applied last)
2. `TimingMiddleware` (middle)
3. `ErrorHandlingMiddleware` (innermost - applied first)

The execution order is: Logging → Timing → ErrorHandling (which re-raises). The doc's "outer to inner" description is correct for execution order but the numbering suggests 1 is outermost. However, the execution trace through the code shows ErrorHandling is actually the innermost wrapper.

**Priority:** MEDIUM — technically correct about execution flow but numbering in doc could mislead readers about application order

---

### 2. Architecture Diagram Missing `__init__.py` (LOW)
**Location:** `architecture/subagent.md:7-18`

**Claim:**
```
services/subagent/
├── __init__.py
├── chain.py             # Multi-step subagent chains with conditions
├── conditions.py       # AST-based condition evaluation
├── config.py           # Executor setup, provider config
├── middleware.py        # Logging, timing, error handling middleware
├── prompt_templates.py # Task prompt templates
├── registry.py         # _TOOL_REGISTRY with cached tool definitions
├── runner.py           # run_subagent() and run_subagent_with_tools()
├── tools.py            # Tool implementations
└── utils.py            # Retry, task revocation helpers
```

**Issue:** The doc is missing `middleware.py` file reference — the actual file is `services/subagent/middleware.py`. The diagram shows `middleware.py` but the file is `middleware.py`. Actually, the doc shows `middleware.py` which is correct. Wait, let me re-check — the doc shows `middleware.py` at line 13 which matches the actual file `services/subagent/middleware.py`.

Actually looking more carefully: the doc shows `middleware.py` at line 13 which IS the actual filename. But the architecture listing at line 7-18 is actually correct since it shows `middleware.py` (the file) and the doc's structure matches the actual files.

However, the listing is missing `__init__.py` details. The `__init__.py` DOES export the key functions.

**Priority:** LOW — mostly correct, slight confusion about file naming

---

### 3. Chain Schema Location Documentation (LOW)
**Location:** `architecture/subagent.md:134` and `architecture/subagent.md:174`

**Claim (twice):** "These schemas are defined in `schemas/pipeline.py`, not in `runner.py` or `chain.py`."

**Issue:** This is **correct** — the note is accurate. But it appears TWICE (lines 134 and 174) which is redundant. Also, `chain.py` DOES import from `schemas/pipeline.py` at line 48:
```python
from schemas.pipeline import SubagentChainStep, load_pipeline_config, resolve_subagent_config
```

The schemas are only defined in `schemas/pipeline.py`, imported everywhere else.

**Priority:** INFORMATIONAL — the duplication is harmless

---

## Bugs Found

### 1. Missing Tool: `_context_tool_get_source_performance` Listed but Implemented Differently (LOW)
**Location:** `architecture/subagent.md:94`

**Claim (from doc example):**
```python
def _context_tool_get_source_performance(source_key: str | None = None, days: int = 7) -> str:
```

**Issue:** The doc at line 94 shows this function as taking `(source_key, days)` but the actual implementation at `services/subagent/tools.py:218-238` has:
```python
def _context_tool_get_source_performance(
    source_key: str | None = None, days: int = 7,
) -> str:
```

This IS correct — the doc listing matches. Let me re-verify...

Actually the doc shows at line 94:
```python
def _context_tool_get_source_performance(source_key: str | None = None, days: int = 7) -> str:
```

And the actual code at tools.py:218 is:
```python
def _context_tool_get_source_performance(
    source_key: str | None = None, days: int = 7,
) -> str:
```

These match. I was confused — the doc is correct.

**Priority:** N/A — no bug, I misread

---

## Improvement Opportunities

### 1. Document `apply_middleware()` Clone Fix
**Location:** `services/subagent/runner.py:348`

```python
wrapped_fn = apply_middleware(copy.deepcopy(tool.fn), middleware_chain)
```

The `copy.deepcopy(tool.fn)` prevents middleware compounding on cached tool definitions. This is an important architectural detail that prevents bugs but isn't documented.

**Priority:** MEDIUM — important for maintainers to understand why deepcopy is needed

---

### 2. Document Self-Correction in `run_subagent_with_tools()`
**Location:** `services/subagent/runner.py:401-417`

The `self_corrected` flag and retry logic for validation errors is not documented. This is a key feature.

---

### 3. Document `_format_subagent_prompt()` in `run_subagent_with_tools()`
The `run_subagent_with_tools()` uses `_format_subagent_prompt()` from utils but the doc only shows `_format_subagent_prompt` being used, not defined. Actually, looking at `runner.py:326`:
```python
prompt = _format_subagent_prompt(template, prompt_data, stage, task_type)
```

And `_format_subagent_prompt` is imported from `services/subagent/utils.py` at line 26. This helper function handles template formatting with error recovery and is not documented.

---

### 4. Clarify `max_iterations` Default
Both `run_subagent()` and `run_subagent_with_tools()` get `max_iterations` from stage_config:
```python
max_iterations = getattr(stage_config, 'max_iterations', 5)
```

The default of 5 is not explicitly documented in the subagent.md.

---

## Summary

The subagent documentation is **largely accurate** — all 14 tools are correctly listed, the chain system is correctly described, and the middleware system is correctly characterized (with minor confusion about numbering).

Key findings:
1. **14 tools correctly documented** (12 context + 2 search) ✅
2. **Chain uses `provider.chat()` (no tools)** ✅
3. **Middleware applies in reverse** ✅  
4. **`SubagentChainStep` in schemas/pipeline.py** ✅
5. **ErrorHandlingMiddleware re-raises** ✅
6. **Tool results re-injected into messages** ✅

The main improvement opportunities are clarifying the middleware chain order description and documenting the `copy.deepcopy()` fix for cached tool definitions.

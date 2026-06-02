# Subagent Architecture Review

## Summary
The subagent architecture document is mostly accurate but has several discrepancies ranging from documentation errors to functional bugs. Most critically, the self-correction mechanism is documented incorrectly, and the middleware chain order description is misleading despite being functionally correct.

## Verified Claims

### File Inventory
All files exist with correct names in `services/subagent/`:
- `__init__.py` ✅
- `chain.py` ✅
- `conditions.py` ✅
- `config.py` ✅
- `middleware.py` ✅
- `prompt_templates.py` ✅
- `registry.py` ✅
- `runner.py` ✅
- `tools.py` ✅
- `utils.py` ✅

### Tool Registry - All 14 Tools Verified
| Tool | Registered Name | Location |
|------|-----------------|----------|
| `get_topic_note` | `get_topic_note` | `tools.py:312` |
| `context_notes` | `context_notes` | `tools.py:331` |
| `related_articles` | `related_articles` | `tools.py:350` |
| `get_trend_memory` | `get_trend_memory` | `tools.py:377` |
| `get_article_by_id` | `get_article_by_id` | `tools.py:404` |
| `search_articles` | `search_articles` | `tools.py:422` |
| `get_source_health` | `get_source_health` | `tools.py:441` |
| `get_topic_gap_report` | `get_topic_gap_report` | `tools.py:453` |
| `get_source_performance` | `get_source_performance` | `tools.py:475` |
| `get_quality_report` | `get_quality_report` | `tools.py:496` |
| `find_dedupe_candidates` | `find_dedupe_candidates` | `tools.py:514` |
| `estimate_stage_cost` | `estimate_stage_cost` | `tools.py:540` |
| `web_search` | `web_search` | `tools.py:569` |
| `get_search_provider` | `get_search_provider` | `tools.py:588` |

### ToolDefinition Confirmed NO `cached` Field
`services/llm/base.py:48-53` shows ToolDefinition has only: `name`, `description`, `parameters`, `required`, `fn`. The `cached` field note in the documentation is accurate.

### Middleware Chain - Functionally Correct
`middleware.py:83-90` applies middleware in reverse order:
```python
for middleware in reversed(middleware_chain):
    wrapped = middleware.wrap(wrapped)
```
Execution flow: LoggingMiddleware(outer) → TimingMiddleware → ErrorHandlingMiddleware(inner) → tool → ErrorHandling → Timing → Logging

### run_subagent Signatures
- `run_subagent(task_type, stage, prompt_data, response_model, article_id=None)` - `runner.py:209-215` ✅
- `run_subagent_with_tools(task_type, stage, prompt_data, response_model, tools, article_id=None)` - `runner.py:334-341` ✅

### Chain System Schemas Location
- `SubagentChainStep` at `schemas/pipeline.py:108` ✅
- `SubagentChainConfig` at `schemas/pipeline.py:115` ✅
- Documentation correctly notes these are in `schemas/pipeline.py`, not `chain.py`

### Global Registry Write-Once Behavior
`registry.py:59-62`:
```python
with _TOOL_REGISTRY_LOCK:
    if not _TOOL_REGISTRY:
        for tool in all_tools:
            register_tool(tool)
```
- Tool definitions cached with `@functools.lru_cache(maxsize=1)` at `registry.py:29` ✅
- Thread-safe registration via `_TOOL_REGISTRY_LOCK` at `registry.py:16` ✅

### Tool Function Wrapping (No Middleware Compounding)
`runner.py:383-392` creates new ToolDefinition objects for each tool, preventing middleware compounding:
```python
for i, tool in enumerate(tools):
    if tool.fn:
        wrapped_fn = apply_middleware(tool.fn, middleware_chain)
        tools[i] = ToolDefinition(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            required=tool.required,
            fn=wrapped_fn,
        )
```

### Chain Uses `provider.chat()` Not `chat_with_tools()`
`chain.py:122` confirms chains do not support tool calling:
```python
def _chain_call():
    return provider.chat(...)
```

### chat_with_tools Re-injects Tool Results
`services/llm/base.py:505-588` shows the while loop with tool result re-injection via `all_messages.append(tool_result_msg)` at line 588.

## Discrepancies Found

### 1. Self-Correction Mechanism - Incorrect Line References
- **Claim**: "At runner.py:401-417: self_corrected = False, for attempt in range(max_attempts)..."
- **Reality**: No such code exists at lines 401-417. Self-correction logic exists in `_run_subagent_core` at lines 88-109 but uses a different pattern with `corrected` flag and no explicit attempt loop.
- **Severity**: Major
- **Location**: `architecture/subagent.md:155-167` vs `services/subagent/runner.py:88-109`
- **Suggested fix**: Update documentation to reflect actual implementation:
  - Self-correction happens in `_run_subagent_core` inside `_attempt()` (lines 72-109)
  - Uses `corrected` flag (not `self_corrected`)
  - Validation failure triggers a single retry by appending correction message and raising
  - The retry loop is in `_retry_with_backoff`, not an explicit `for attempt in range`

### 2. Middleware Chain Description - Misleading Wording
- **Claim**: "Middleware chain (as applied to tool function): LoggingMiddleware (outermost) - TimingMiddleware (middle) - ErrorHandlingMiddleware (innermost)"
- **Reality**: The description "LoggingMiddleware (outermost)" is ambiguous. The chain is built in reverse, so LoggingMiddleware wraps TimingMiddleware which wraps ErrorHandlingMiddleware. The description is technically correct about the final nesting but misleading about how the chain is constructed.
- **Severity**: Minor
- **Location**: `architecture/subagent.md:228-235`
- **Suggested fix**: Clarify that middleware are applied in reverse order, so the first middleware in the list ends up as the outermost wrapper after the reversal.

### 3. Tool Function Wrapping - Mechanism Mismatch
- **Claim**: "`copy.deepcopy()` for tool functions: Prevents middleware compounding on cached tool definitions. Each invocation wraps the tool function fresh rather than re-wrapping an already-wrapped function."
- **Reality**: No `copy.deepcopy()` is used. Instead, `runner.py:383-392` creates a brand new `ToolDefinition` object with the wrapped function, which achieves the same goal but via a different mechanism.
- **Severity**: Minor
- **Location**: `architecture/subagent.md:148` vs `services/subagent/runner.py:383-392`
- **Suggested fix**: Update to say: "Creates new ToolDefinition objects with wrapped functions: Prevents middleware compounding..."

### 4. Tool Implementation Signatures - Missing Parameters
- **Claim**: `_search_web(query: str, max_results: int = 5) -> str:` and `_context_tool_get_search_provider(provider_id: str | None = None) -> str:`
- **Reality**: Both function signatures match correctly in code.
- **Severity**: No discrepancy - signatures match

### 5. Missing Tool Function Parameters in Documentation
- **Claim**: `_context_tool_get_topic_gap_report` signature in doc shows only `topics: list[str] | None = None`
- **Reality**: Actual function at `tools.py:165-186` has signature `topics: list[str] | None = None, days: int = 30`. The `days` parameter is missing from the doc example.
- **Severity**: Minor
- **Location**: `architecture/subagent.md:83-86` vs `services/subagent/tools.py:165-167`
- **Suggested fix**: Update signature to `_context_tool_get_topic_gap_report(topics: list[str] | None = None, days: int = 30) -> str:`

### 6. Missing Tool Function Parameters - get_source_performance
- **Claim**: Doc at lines 218-219 shows `_context_tool_get_source_performance(source_key: str | None = None) -> str:`
- **Reality**: Actual function at `tools.py:218-220` has signature `source_key: str | None = None, days: int = 7`. The `days` parameter is missing.
- **Severity**: Minor
- **Location**: `architecture/subagent.md:218-219` vs `services/subagent/tools.py:218-220`
- **Suggested fix**: Update signature to `_context_tool_get_source_performance(source_key: str | None = None, days: int = 7) -> str:`

## Bugs Identified

### ToolDefinition Import Path Mismatch in Documentation
- **Bug**: `architecture/subagent.md:340` imports `ToolDefinition` from `services.llm.base`, but `runner.py:13` also imports from `services.llm.base`. This is correct.
- **Impact**: None - this is actually correct in the docs
- **Suggested fix**: N/A

## Stale Items Found

1. **Self-correction mechanism documentation** (lines 151-167): References non-existent line numbers and incorrect implementation details. Should reference `runner.py:88-109` with actual implementation details.

2. **copy.deepcopy() claim** (line 148): Implementation uses `ToolDefinition(...)` constructor instead. Mechanism is different but outcome is the same.

3. **Middleware chain application description** (lines 228-235): While functionally correct, the description could mislead readers about how the chain is constructed.

4. **Tool signatures in doc examples** (lines 71-102): Several signatures are incomplete - `get_topic_gap_report` and `get_source_performance` are missing parameters that exist in actual implementations.

## Improvement Opportunities

### 1. Add Type Hints to Middleware.wrap() Return
- **Improvement**: `ToolMiddleware.wrap()` at `middleware.py:13` declares return as `Callable[..., Any]` but the actual wrapped functions maintain their original signatures. Could be more precise.
- **Location**: `services/subagent/middleware.py:13`
- **Benefit**: Better type safety for IDE autocompletion

### 2. Document Self-Correction in _run_subagent_core
- **Improvement**: The self-correction mechanism in `_run_subagent_core` (lines 88-109) is well-implemented but not easily discoverable. Add docstring explaining the flow.
- **Location**: `services/subagent/runner.py:48-62`
- **Benefit**: Better maintainability for future developers

### 3. Tool Function Parameter Consistency
- **Improvement**: Some tools have default parameters that aren't documented in the doc examples (e.g., `get_topic_gap_report(days=30)`, `get_source_performance(days=7)`).
- **Location**: `services/subagent/tools.py:165, 218`
- **Benefit**: More accurate documentation for API users

## Recommendations

1. **High Priority**: Fix self-correction mechanism documentation (lines 151-167) - currently references non-existent code and describes incorrect implementation pattern.

2. **Medium Priority**: Update tool function signatures in documentation to show all parameters including defaults.

3. **Low Priority**: Clarify middleware chain construction wording to clarify that "first in list" becomes "outermost after reversal".

4. **Low Priority**: Replace `copy.deepcopy()` reference with accurate description of creating new ToolDefinition objects.

5. **Informational**: Consider adding inline documentation to `_run_subagent_core` explaining the self-correction flow since it's a key architectural pattern.
# Subagent Architecture Review

## Verified Claims

### Subagent Location
- **VERIFIED**: The subagent module is correctly located at `services/subagent/` (not top-level).

### Tool Registry Mechanism
- **VERIFIED**: `registry.py` defines `_TOOL_REGISTRY: dict[str, ToolDefinition] = {}` (line 14).
- **VERIFIED**: `initialize_tool_registry()` function registers tools (lines 36-66).
- **VERIFIED**: `get_registered_tools()` returns all registered tools (lines 22-24).
- **VERIFIED**: Caching mechanism exists via `_get_all_tools_cached()` using `functools.lru_cache` (lines 27-33).

### Chain System
- **VERIFIED**: `SubagentChainStep` and `SubagentChainConfig` exist in `schemas/pipeline.py` (lines 107-117).
- **VERIFIED**: `run_subagent_chain()` in `chain.py` implements multi-step chains.
- **VERIFIED**: Chain configuration loaded from `pipeline.yaml` under `subagent.chains`.
- **VERIFIED**: Conditions use AST-based evaluation via `_evaluate_condition()` from `conditions.py`.

### Middleware
- **VERIFIED**: `ToolMiddleware` base class exists with `wrap()` pattern (middleware.py lines 10-15).
- **VERIFIED**: `LoggingMiddleware`, `TimingMiddleware`, `ErrorHandlingMiddleware` all implement sync `wrap()` pattern.
- **VERIFIED**: `apply_middleware()` function chains middleware in reverse order (lines 83-91).

### run_subagent() Function Signature
- **VERIFIED**: `run_subagent(task_type, str, prompt_data: dict, response_model: Type[BaseModel], article_id: int | None = None)` - exact match to architecture doc (runner.py lines 38-44).
- **VERIFIED**: `run_subagent_with_tools()` has matching signature with `tools: list[ToolDefinition]` parameter (runner.py lines 331-338).

### Built-in Tools
All 9 tools are correctly implemented in `tools.py`:
| Tool Name | Function | Lines |
|-----------|----------|-------|
| `get_topic_note` | `_context_tool_get_topic_note` | 13-31 |
| `context_notes` | `_context_tool_get_topic_notes_for_topics` | 34-49 |
| `related_articles` | `_context_tool_get_related_articles` | 52-76 |
| `get_trend_memory` | `_context_tool_get_trend_memory` | 79-96 |
| `get_article_by_id` | `_context_tool_get_article_by_id` | 99-119 |
| `search_articles` | `_context_tool_search_articles` | 122-137 |
| `get_source_health` | `_context_tool_get_source_health` | 140-157 |
| `web_search` | `_search_web` | 160-173 |
| `get_search_provider` | `_get_search_provider` | 176-187 |

## Discrepancies

### 1. ToolDefinition Schema Mismatch
**Architecture Doc** claims `ToolDefinition` has:
```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for tool
    cached: bool = True  # Cache tool definition?
```

**Actual Code** (`services/llm/base.py` lines 80-86):
```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
```

**Issues**:
- No `cached` field exists in the actual `ToolDefinition`
- `required` field exists but is not documented
- The architecture doc shows `BaseModel` but actual is `@dataclass`
- `fn` field is runtime-only (not JSON serializable) but not documented

### 2. Execution Flow Documentation Incomplete
**Architecture Doc** shows:
```
1. Build messages with system prompt + context
2. Call LLM with tool definitions
3. If tool_calls:
   a. Execute tools in parallel
   b. Add results to messages
   c. Goto 2 (max iterations)
4. Return final response
```

**Actual Implementation Issues**:
- The actual flow in `run_subagent_with_tools()` does NOT add tool results back to messages for subsequent LLM calls - tools are executed but results are NOT appended to `messages` before the next iteration
- The loop structure in `runner.py` lines 384-407 calls `provider.chat_with_tools()` once, not iteratively with result re-injection

### 3. Missing `SubagentChainStep` Fields in Doc
**Architecture Doc** only shows:
```python
class SubagentChainStep(BaseModel):
    task_type: str
    prompt_data_template: str
    response_model: Optional[str] = None
    condition: Optional[str] = None
```

**Actual Schema** has no additional fields, but the chain implementation references `step_config.condition` which is correctly documented.

## Bugs Found

### BUG 1: Dead Code - `_finalize_subagent_result()` is Defined Twice
In `runner.py`:
- Lines 277-328: `_finalize_subagent_result()` function is defined
- Lines 498-501: The same function is called to finalize results

**Issue**: This function is defined but the same logic appears earlier in `run_subagent()` (lines 227-268) where it's inline, not extracted. The extracted version in `run_subagent_with_tools()` is used, but the duplicate definition creates confusion and maintenance burden.

### BUG 2: Tool Results Not Re-injected in Tool Loop
In `run_subagent_with_tools()` (runner.py lines 384-407):
```python
messages = [{"role": "user", "content": prompt}]
...
tc_resp = provider.chat_with_tools(
    messages=messages,  # Only initial prompt
    tools=tools,
    ...
)
```

**Issue**: If the LLM returns `tool_calls`, the actual tool execution happens inside `provider.chat_with_tools()`, but the tool results are NOT added back to `messages` for a follow-up LLM call. The architecture document says step 3b says "Add results to messages" but this is NOT happening.

**Expected behavior** according to doc:
```python
# If tool_calls:
#   a. Execute tools in parallel
#   b. Add results to messages  
#   c. Goto 2 (max iterations)
```

**Actual behavior**: Single `chat_with_tools()` call handles everything internally; no message re-injection occurs.

### BUG 3: `_TOOL_REGISTRY` is Module-Level Global with Potential Race Condition
In `registry.py`:
```python
_TOOL_REGISTRY: dict[str, ToolDefinition] = {}

def initialize_tool_registry(...) -> list[ToolDefinition]:
    global _TOOL_REGISTRY
    if not _TOOL_REGISTRY:  # Race condition window
        for tool in all_tools:
            register_tool(tool)  # Modifies global
```

**Issue**: If multiple threads call `initialize_tool_registry()` concurrently before any registration completes, the `if not _TOOL_REGISTRY` check could pass for multiple threads, leading to duplicate registrations or race conditions. The `_get_all_tools_cached()` is cached but `_TOOL_REGISTRY` population is not thread-safe.

### BUG 4: `_subagent_executor` ThreadPoolExecutor Never Shut Down
In `config.py` line 10:
```python
_subagent_executor = ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS, thread_name_prefix="subagent")
```

**Issue**: This executor is created at module import time but never has `shutdown()` called. In long-running applications like Celery workers, this can lead to resource leaks.

## Improvement Recommendations

### 1. Document `run_subagent_with_tools()` in Architecture
The architecture doc shows `run_subagent_with_tools()` as a public API entry point (lines 96-104), but it should be clearly documented that `run_subagent()` is the primary entry point and `run_subagent_with_tools()` is for advanced use cases.

### 2. Clarify Tool Execution Flow
The tool execution flow in the architecture doc does not match implementation. Recommend either:
- Update doc to reflect actual single-call behavior with internal tool loop
- Update code to match documented multi-step message injection pattern

### 3. Add `cached` Field to ToolDefinition or Remove from Doc
The `cached` field is documented in `ToolDefinition` but doesn't exist. Either:
- Add the field to `ToolDefinition` in `services/llm/base.py`
- Remove from architecture documentation

### 4. Add `StageAwareToolSelector` to Architecture
The `run_subagent()` function uses `StageAwareToolSelector` (runner.py line 105-110) but this is not mentioned in the architecture doc. This is an important piece of the stage-aware tool selection mechanism.

### 5. Document `resolve_subagent_config()` Function
The `resolve_subagent_config()` function in `schemas/pipeline.py` (lines 187-218) is central to the subagent configuration resolution but is not documented in the architecture.

### 6. Add Timeout and Retry Configuration Details
The architecture mentions retry with exponential backoff but doesn't detail the configuration options. The actual implementation uses:
- `stage_config.max_retries`
- `stage_config.retry_delay`
- `stage_config.timeout_seconds`

These should be documented.

## Layer Violations

### No Direct Layer Violations Detected

The subagent module is correctly located in `services/` and the architecture rules state:
- "Tasks→Services Layer: Tasks layer IS allowed to import from services layer"
- The subagent module imports from other services (`services.cache`, `services.context_service`, `services.trend_memory`, `services.search`, etc.) which is **service-to-service** communication, not services importing from adapters.

### Import Dependencies Summary

```
services/subagent/
├── registry.py → services.tool_selection, services.llm.base
├── tools.py → services.cache, services.context_service, services.trend_memory, services.search, models
├── runner.py → services.llm.base, services.llm.errors, services.tool_selection
├── chain.py → services.llm.errors
├── config.py → services.llm
├── conditions.py → (no services imports, pure utility)
├── middleware.py → (no services imports, pure utility)
├── utils.py → utils.text, celery (import guard)
└── __init__.py → services.logging_utils, services.metrics, services.llm
```

All imports are within the services layer or to utilities/schemas, which complies with the architecture's layering rules.

## Summary

| Category | Status |
|----------|--------|
| Location | ✅ Correct (`services/subagent/`) |
| Tool Registry | ✅ Implemented |
| run_subagent() Signature | ✅ Matches doc |
| Chain System | ✅ Implemented |
| Middleware Pattern | ✅ Implemented |
| Discrepancies Found | 3 |
| Bugs Found | 4 |
| Layer Violations | 0 |

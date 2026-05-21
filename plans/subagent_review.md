# Subagent Architecture Review

Review Date: 2026-05-21
Document: `architecture/subagent.md`
Codebase: `services/subagent/`

---

## Verified Correct

### 1. Tool Registry Completeness (9 tools)
All 9 tools listed in the documentation are present in `services/subagent/tools.py`:

| Tool | Function | Location |
|------|----------|----------|
| `get_topic_note` | `_context_tool_get_topic_note` | tools.py:13 |
| `context_notes` | `_context_tool_get_topic_notes_for_topics` | tools.py:34 |
| `related_articles` | `_context_tool_get_related_articles` | tools.py:52 |
| `get_trend_memory` | `_context_tool_get_trend_memory` | tools.py:79 |
| `get_article_by_id` | `_context_tool_get_article_by_id` | tools.py:99 |
| `search_articles` | `_context_tool_search_articles` | tools.py:122 |
| `get_source_health` | `_context_tool_get_source_health` | tools.py:140 |
| `web_search` | `_search_web` | tools.py:160 |
| `get_search_provider` | `_get_search_provider` | tools.py:176 |

### 2. `run_subagent` Signature
```python
# Documented (lines 87-93):
def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:

# Actual (runner.py:38-44):
def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:
```
**MATCHES**

### 3. `run_subagent_with_tools` Signature
```python
# Documented (lines 96-104):
def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:

# Actual (runner.py:277-284):
def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:
```
**MATCHES**

### 4. Chain System Schemas
Both `SubagentChainStep` and `SubagentChainConfig` in `schemas/pipeline.py` (lines 107-117) match the documented structure exactly:

```python
class SubagentChainStep(BaseModel):
    task_type: str
    prompt_data_template: str
    response_model: Optional[str] = None
    condition: Optional[str] = None

class SubagentChainConfig(BaseModel):
    enabled: bool = False
    max_length: int = Field(default=5, ge=1, le=10)
    steps: list[SubagentChainStep] = Field(default_factory=list)
```

### 5. Middleware Sync Wrap Pattern
The middleware pattern in `services/subagent/middleware.py` uses the documented sync `wrap()` pattern:
- `ToolMiddleware` base class with `wrap()` method (line 10-15)
- `LoggingMiddleware` (lines 18-35)
- `TimingMiddleware` (lines 38-61)

---

## Discrepancies Found

### 1. ToolDefinition Schema (Major Discrepancy)

**Documented** (lines 24-29):
```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for tool
    cached: bool = True  # Cache tool definition?
```

**Actual** (`services/llm/base.py:80-86`):
```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
```

**Issues:**
- Document says `BaseModel`, actual is `@dataclass`
- Document shows `cached: bool = True` field - **this field does NOT exist**
- Document shows `required` as part of the JSON schema dict, but actual has separate `required: list[str]` field
- Document doesn't mention `fn` field

### 2. ErrorHandlingMiddleware Missing from Documentation

The document only lists two middleware classes (lines 182-209):
- `LoggingMiddleware`
- `TimingMiddleware`

**But** `ErrorHandlingMiddleware` exists in `middleware.py:64-80` and is **actively used** in `run_subagent_with_tools` (runner.py:321-328):

```python
middleware_chain = [
    LoggingMiddleware(logger),
    TimingMiddleware(logger),
    ErrorHandlingMiddleware(logger),  # NOT DOCUMENTED
]
```

### 3. Tool Timeout Configuration Does Not Exist

**Documented** (line 219):
```yaml
subagent:
  tool_timeout: 30.0
```

**Actual:**
- No `tool_timeout` field exists in `SubagentStageConfig` (`schemas/pipeline.py:92-104`)
- The `timeout_seconds` field (default=120) is the **subagent-level timeout**, not per-tool timeout
- No per-tool timeout mechanism exists in `middleware.py` or tool implementations

The document claims: "Tool timeout: Skips tool, continues with available context" - this behavior is **NOT implemented**.

### 4. Retry Configuration Description Mismatch

**Documented** (line 259):
> LLM error: Retries with exponential backoff (max 3 attempts)

**Actual** (`SubagentStageConfig`):
```python
max_retries: int = Field(default=1, ge=0, le=5)
```

The default is 1 retry (2 total attempts), not 3. The AGENTS.md documentation confirms this is configurable up to 5.

---

## Bugs Identified

### BUG-1: Missing `_finalize_subagent_result` Function (CRITICAL)

**Location:** `services/subagent/runner.py:444`

```python
return _finalize_subagent_result(
    result, used_fallback, fallback_stages, last_exc,
    stage, task_type, article_id, stage_config,
)
```

The function `_finalize_subagent_result` is **called but does not exist** anywhere in the codebase. This will cause a `NameError` at runtime whenever `run_subagent_with_tools()` completes successfully (i.e., doesn't early-return or raise an exception).

**Note:** The AGENTS.override.md mentions "CRIT-2: Duplicate Function Definition in subagent/runner.py" which suggested a function was defined twice. However, in the current codebase:
- Only 447 lines exist in runner.py
- No `_finalize_subagent_result` function definition exists
- The bug appears to have evolved - now the function is simply missing entirely

**Impact:** `run_subagent_with_tools()` will crash with `NameError: name '_finalize_subagent_result' is not defined`

---

## Improvement Suggestions

### 1. Implement Missing Tool Timeout Mechanism
The documented `tool_timeout: 30.0` config and "skip tool on timeout" behavior is not implemented. Consider:
- Adding `tool_timeout_seconds` to `SubagentStageConfig`
- Implementing timeout handling in middleware's `wrap()` function
- Allowing pipeline to continue with partial results when tools timeout

### 2. Add `ErrorHandlingMiddleware` to Documentation
The middleware section should document all three middleware classes including `ErrorHandlingMiddleware`.

### 3. Fix ToolDefinition Schema Documentation
Update `architecture/subagent.md` to accurately reflect:
- `ToolDefinition` is a `@dataclass`, not `BaseModel`
- No `cached` field exists
- Include the `fn` field in the schema
- `required` is a separate field, not embedded in `parameters`

### 4. Align Retry Defaults in Documentation
Document that max retries is configurable with a default of 1 (2 total attempts), rather than stating a fixed "max 3 attempts".

### 5. Clarify Self-Correction Behavior
The document says (line 123): "Self-correction: Re-validates output and retries on failure"

This IS implemented in `run_subagent_with_tools` (lines 374-390) - when a validation error occurs, it sends an error message back to the LLM and retries once. However, this only happens on JSON/schema validation failures, not general "self-correction" as implied.

---

## Questions for Architecture

1. **Was `_finalize_subagent_result` intentionally removed or is this a bug?**
   The function was referenced in `run_subagent_with_tools` but never defined. It seems like the code intended to refactor common result finalization logic but never completed the implementation.

2. **Is the `cached` field on `ToolDefinition` planned for future implementation?**
   The document shows this field but it doesn't exist. Is this a planned feature or outdated documentation?

3. **What is the intended behavior for tool timeouts?**
   The document describes skipping timed-out tools and continuing. Is this desired behavior that should be implemented, or was the documentation incorrect about the intended design?

4. **Should `run_subagent_with_tools` share more code with `run_subagent`?**
   Both functions have very similar error handling and finalization logic. The missing `_finalize_subagent_result` suggests there was an intent to share this code.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct | 5 |
| Discrepancies Found | 4 |
| Bugs Identified | 1 (Critical) |
| Improvement Suggestions | 5 |
| Questions for Architecture | 4 |

**Critical Issue:** `run_subagent_with_tools` will crash at runtime due to missing `_finalize_subagent_result` function.

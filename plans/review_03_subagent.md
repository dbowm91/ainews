# Subagent System Architecture Review (review_03_subagent.md)

**Date:** 2026-05-07
**Reviewer:** Architecture Review Agent
**Document:** `architecture/subagent.md`
**Codebase:** `/home/sugarwookie/projects/ainews/services/subagent/`

---

## Executive Summary

The `architecture/subagent.md` document describes the subagent system but contains **significant discrepancies** between documented design and actual implementation. The most critical issues are:

1. **Wrong function signatures** - Documentation shows async functions with `task/context/tools/model` parameters, but actual implementation uses `task_type/stage/prompt_data/response_model`
2. **Missing tool classes** - Docs show `Tool` classes with `async execute()`, but actual implementation uses plain functions
3. **Inaccurate middleware API** - Middleware classes shown with async `on_request/on_response` methods, actual implementation uses sync `wrap()` pattern
4. **Tool naming inconsistencies** - Table shows `get_topic_note` as `context_notes` tool name, but actual tool name is `get_topic_note`

Overall, the document provides a reasonable high-level overview but is **not safe to use as a reference for implementation**.

---

## 1. Verification of Major Claims

### 1.1 File Structure

| Documented (line 8-15) | Actual | Status |
|------------------------|--------|--------|
| `registry.py` | `services/subagent/registry.py` | MATCH |
| `tools.py` | `services/subagent/tools.py` | MATCH |
| `runner.py` | `services/subagent/runner.py` | MATCH |
| `chain.py` | `services/subagent/chain.py` | MATCH |
| `prompt_templates.py` | `services/subagent/prompt_templates.py` | MATCH |
| `middleware.py` | `services/subagent/middleware.py` | MATCH |
| `utils.py` | `services/subagent/utils.py` | **MISSING FROM DOC** |
| `conditions.py` | `services/subagent/conditions.py` | **MISSING FROM DOC** |
| `config.py` | `services/subagent/config.py` | **MISSING FROM DOC** |

**DISCREPANCY 1.1.1: Missing source files in documentation**
- **Location:** `architecture/subagent.md` lines 8-15
- **Problem:** Three files (`utils.py`, `conditions.py`, `config.py`) exist but are not documented
- **Impact:** Developers using the doc will not know these components exist
- **Recommendation:** Update the architecture diagram to include all source files

**DISCREPANCY 1.1.2: utilities.py exists but not in doc**
- **Location:** `services/subagent/utils.py`
- **Contains:** `_retry_with_backoff`, `_is_task_revoked`, `_format_subagent_prompt`
- **Recommendation:** Document utility functions in a separate section

---

### 1.2 Tool Registry (`registry.py`)

**DISCREPANCY 1.2.1: ToolDefinition class source mismatch**
- **Documented (line 24-29):** Uses `BaseModel` (Pydantic)
- **Actual (line 81-86 in `services/llm/base.py`):** Uses `@dataclass`
- **Code Reference:**
  ```python
  # Documented (incorrect):
  class ToolDefinition(BaseModel):
      name: str
      description: str
      parameters: dict
      cached: bool = True
  
  # Actual in services/llm/base.py (line 81-86):
  @dataclass
  class ToolDefinition:
      name: str
      description: str
      parameters: dict
      required: list[str] = field(default_factory=list)
      fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
  ```

**DISCREPANCY 1.2.2: `cached` field doesn't exist**
- **Documented:** `cached: bool = True`
- **Actual:** No `cached` field; caching is done via `functools.lru_cache` on `_get_all_tools_cached()` in `registry.py` line 27

---

### 1.3 Tool Implementations (`tools.py`)

**DISCREPANCY 1.3.1: No Tool classes - plain functions instead**
- **Documented (line 46-77):** Shows class-based tools with `async execute()` methods
- **Actual:** Tools are implemented as module-level functions (e.g., `_context_tool_get_topic_note` at line 13)
- **Code Reference:**
  ```python
  # Documented (incorrect - no such classes exist):
  class ContextNotesTool(Tool):
      name = "context_notes"
      async def execute(self, topic: str) -> dict:
          ...
  
  # Actual - function-based:
  def _context_tool_get_topic_note(topic: str, source: str | None = None) -> str:
      ...
  ```

**DISCREPANCY 1.3.2: Tool naming mismatch**
- **Documented table (line 33-41):**
  | Table shows | Actual name |
  |-------------|--------------|
  | `context_notes` | `get_topic_note` |
  | `related_articles` | `related_articles` (MATCH) |
  | `trend_memory` | `get_trend_memory` |
  | `article_lookup` | `get_article_by_id` |
  | `article_search` | `search_articles` |
  | `source_health` | `get_source_health` |
  | `web_search` | `web_search` (MATCH) |
- **Impact:** Only 2 of 7 tool names match exactly

**ISSUE 1.3.3: Doc mentions `article_lookup` but actual tool is `get_article_by_id`**
- **Documented:** `article_lookup` (line 38)
- **Actual:** Tool is named `get_article_by_id` (tools.py line 287)

---

### 1.4 Subagent Runner (`runner.py`)

**CRITICAL DISCREPANCY 1.4.1: Function signatures completely wrong**

Documented (line 83-98):
```python
async def run_subagent(
    task: str,
    context: dict | None = None,
    tools: list[str] | None = None,
    model: str | None = None,
) -> SubagentResult

async def run_subagent_with_tools(
    task: str,
    context: dict | None = None,
    tools: list[str] | None = None,
    max_iterations: int = 5,
) -> SubagentResult
```

Actual (runner.py lines 38-44, 331-338):
```python
def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse

def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse
```

**Differences:**
- `task` vs `task_type` + `stage` split
- `context` vs `prompt_data`
- `tools: list[str]` vs `tools: list[ToolDefinition]` (and different placement)
- Missing `response_model` parameter
- Missing `article_id` parameter
- Not async
- Return type `SubagentResult` vs `SubagentResponse`

**DISCREPANCY 1.4.2: Return type mismatch**
- **Documented:** `SubagentResult`
- **Actual:** `SubagentResponse` from `schemas.llm_responses`

---

### 1.5 Chain System (`chain.py`)

**DISCREPANCY 1.5.1: ChainStep class doesn't exist**
- **Documented (line 125-131):** Shows Pydantic models `ChainStep` and `Chain`
- **Actual:** No such classes. Chain execution uses `SubagentChainStep` and `SubagentChainConfig` from `schemas/pipeline.py` (lines 107-117)
- **Code Reference:**
  ```python
  # Documented (doesn't exist):
  class ChainStep(BaseModel):
      name: str
      task: str
      tools: list[str] | None = None
      next_step: str | None = None
      condition: str | None = None
  
  # Actual schema (schemas/pipeline.py line 107-117):
  class SubagentChainStep(BaseModel):
      task_type: str
      prompt_data_template: str
      response_model: Optional[str] = None
      condition: Optional[str] = None
  ```

**DISCREPANCY 1.5.2: Execution model differs**
- **Documented:** Shows `next_step` field for sequential execution
- **Actual:** `run_subagent_chain()` iterates through steps by index, no `next_step` field used

---

### 1.6 Middleware (`middleware.py`)

**DISCREPANCY 1.6.1: Middleware API completely different**
- **Documented (line 157-170):** Shows async methods `on_request`, `on_response`, `on_error`
- **Actual (middleware.py lines 10-91):** Uses sync `wrap()` pattern
- **Code Reference:**
  ```python
  # Documented (doesn't exist):
  class LoggingMiddleware:
      async def on_request(self, task: str, context: dict): ...
      async def on_response(self, result: SubagentResult): ...
      async def on_error(self, error: Exception): ...
  
  # Actual:
  class LoggingMiddleware(ToolMiddleware):
      def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
          def wrapped(*args, **kwargs):
              self.logger.info("Tool %s called", func.__name__)
              ...
          return wrapped
  ```

**ISSUE 1.6.2: Middleware applies to tools, not subagent requests**
- **Documented:** Implies middleware wraps subagent execution
- **Actual:** `apply_middleware()` (line 382 in runner.py) wraps tool functions, not subagent calls
- **Code Reference:** `runner.py` line 380-382:
  ```python
  for tool in tools:
      if tool.fn:
          tool.fn = apply_middleware(tool.fn, middleware_chain)
  ```

---

### 1.7 Configuration Section

**DISCREPANCY 1.7.1: Configuration example is stale**
- **Location:** `architecture/subagent.md` lines 175-190
- **Documented:**
  ```yaml
  subagent:
    enabled: true
    max_iterations: 5
    tool_timeout: 30.0
    default_model: "ollama-local"
    tools:
      - context_notes
      - related_articles
      ...
  ```
- **Actual (pipeline.yaml lines 178-227):** Configuration uses `subagent.default`, `subagent.research`, `subagent.edit` sections with different structure. `tool_timeout` doesn't exist; it's `timeout_seconds`. `default_model` doesn't exist - uses `model` per stage.

---

### 1.8 Usage Example

**DISCREPANCY 1.8.1: Example code doesn't match actual API**
- **Location:** `architecture/subagent.md` lines 196-207
- **Documented:** Shows `run_subagent_with_tools()` with `task`, `context`, `tools` parameters
- **Actual:** Function signature is completely different (see 1.4.1)
- **Code Reference (tasks/edit.py lines 112-125):**
  ```python
  context_result = run_subagent_with_tools(
      task_type="edit_contextualization",
      stage="edit",
      prompt_data={...},
      response_model=EditContextualizationResponse,
      tools=tools,
      article_id=article.id,
  )
  ```

---

## 2. Bugs and Issues Discovered

### BUG 2.1: Dead code in `runner.py` - `_finalize_subagent_result`

**Location:** `services/subagent/runner.py` lines 277-328

**Issue:** This function is defined but never called directly. The code path uses inline logic instead (lines 244-268 and 498-501). The function has duplicate logic that could lead to maintenance issues.

**Code Evidence:**
- Line 277: Function defined
- Line 498: `return _finalize_subagent_result(...)` is called
- But the same logic is inlined at lines 227-268

**Recommendation:** Remove `_finalize_subagent_result` and use it consistently, or refactor to avoid duplication.

---

### BUG 2.2: Middleware never actually applied in `run_subagent`

**Location:** `services/subagent/runner.py` lines 38-274 (`run_subagent` function)

**Issue:** Middleware chain is defined at lines 375-379 but only applied in `run_subagent_with_tools`. The `run_subagent` function does not apply any middleware.

**Code Evidence:**
```python
# In run_subagent_with_tools (lines 375-382):
middleware_chain = [LoggingMiddleware(logger), TimingMiddleware(logger), ErrorHandlingMiddleware(logger)]
for tool in tools:
    if tool.fn:
        tool.fn = apply_middleware(tool.fn, middleware_chain)

# In run_subagent (lines 38-274): No middleware application
```

---

### BUG 2.3: Retry logic doesn't reset `self_corrected` flag on retry

**Location:** `services/subagent/runner.py` lines 409-444

**Issue:** When `_attempt()` is retried via `_retry_with_backoff`, the `self_corrected` flag is not reset between attempts. This could cause the self-correction message to be sent incorrectly on a retry.

**Code Evidence:**
```python
def _attempt():
    nonlocal self_corrected, future
    ...
    except (json.JSONDecodeError, ValidationError) as validation_err:
        if self_corrected:  # This flag was set in a previous attempt
            raise validation_err
        ...  # Sets self_corrected = True
        raise  # Triggers retry
```

---

## 3. Improvement Recommendations

### REC 3.1: Update documentation to match actual implementation

**Priority:** HIGH
**Effort:** MEDIUM

Update `architecture/subagent.md` to accurately reflect:
1. Function signatures from `runner.py`
2. Tool implementation as functions, not classes
3. Middleware sync `wrap()` pattern
4. Actual tool names and parameters
5. Configuration from `pipeline.yaml`

---

### REC 3.2: Add missing source files to architecture diagram

**Priority:** MEDIUM
**Effort:** LOW

Update line 8-15 to include:
```
├── registry.py          # _TOOL_REGISTRY with cached tool definitions
├── tools.py             # Tool implementations (as functions)
├── runner.py            # run_subagent() and run_subagent_with_tools()
├── chain.py             # Multi-step subagent chains with conditions
├── conditions.py        # AST-based condition evaluation
├── config.py            # Subagent executor and provider config
├── prompt_templates.py  # Task prompt templates
├── middleware.py        # Logging, timing, error handling middleware
└── utils.py             # Retry, revocation, formatting utilities
```

---

### REC 3.3: Add missing tools to documentation table

**Priority:** MEDIUM
**Effort:** LOW

Add the two missing tools from actual implementation:
- `get_topic_note` (single topic lookup)
- `get_search_provider` (search provider info)

---

### REC 3.4: Fix ChainStep documentation

**Priority:** MEDIUM
**Effort:** LOW

The chain example at lines 140-153 shows `name`, `task`, `tools`, `next_step`, `condition` but actual schema uses `task_type`, `prompt_data_template`, `response_model`, `condition`. Update to show actual YAML config format used in `pipeline.yaml` lines 229-247.

---

### REC 3.5: Document actual return types

**Priority:** MEDIUM
**Effort:** LOW

Update return type from `SubagentResult` to `SubagentResponse` throughout. Document the `SubagentResponse` schema with its fields: `synthesis`, `used_fallback`, `fallback_stages`.

---

### REC 3.6: Remove dead code - `_finalize_subagent_result`

**Priority:** LOW
**Effort:** LOW

Consider removing `_finalize_subagent_result` or using it consistently to avoid maintenance burden.

---

### REC 3.7: Add middleware to `run_subagent`

**Priority:** LOW
**Effort:** MEDIUM

Either document that middleware only applies to `run_subagent_with_tools`, or add middleware support to `run_subagent` for consistency.

---

### REC 3.8: Reset `self_corrected` flag on retry

**Priority:** LOW
**Effort:** LOW

In `run_subagent_with_tools`, reset `self_corrected = False` at the start of each retry attempt in `_attempt()`.

---

### REC 3.9: Add configuration section based on actual pipeline.yaml

**Priority:** MEDIUM
**Effort:** LOW

Replace lines 175-190 with actual config structure showing `subagent.default`, `subagent.research`, `subagent.edit` sections with their actual fields.

---

## 4. Summary of Discrepancies by Severity

| Severity | Issue | Location |
|----------|-------|----------|
| CRITICAL | Function signatures completely wrong | lines 83-98 |
| CRITICAL | Tool class implementation doesn't exist | lines 46-77 |
| HIGH | Return type `SubagentResult` doesn't exist | lines 89, 97 |
| HIGH | Middleware async API doesn't exist | lines 157-171 |
| MEDIUM | Missing files in architecture diagram | lines 8-15 |
| MEDIUM | Tool naming table is mostly wrong | lines 33-41 |
| MEDIUM | ChainStep class doesn't exist | lines 125-136 |
| MEDIUM | Configuration example is stale | lines 175-190 |
| LOW | Missing utility functions documented | - |
| LOW | Usage example code doesn't match API | lines 196-207 |

---

## 5. Verification Checklist

| Claim | Verification | Status |
|-------|--------------|--------|
| File structure (line 8-15) | Partially matches - missing 3 files | PARTIAL |
| ToolDefinition class (line 24-29) | Wrong - uses dataclass not BaseModel | WRONG |
| Tool table names (line 33-41) | 2/7 match actual names | WRONG |
| Tool classes (line 46-77) | No such classes exist | WRONG |
| run_subagent signature (line 84-89) | Completely different | WRONG |
| run_subagent_with_tools signature (line 92-98) | Completely different | WRONG |
| ChainStep class (line 125-131) | Doesn't exist | WRONG |
| Middleware async API (line 160-170) | Doesn't exist | WRONG |
| Configuration example (line 175-190) | Stale/inaccurate | WRONG |
| Usage example (line 196-207) | Doesn't match actual API | WRONG |

---

## 6. Conclusion

The `architecture/subagent.md` document provides a reasonable high-level overview of the subagent system purpose but is **not safe to use as an implementation reference** due to multiple critical discrepancies. The actual implementation is well-structured and functional, but the documentation does not accurately reflect the code.

**Key Takeaway:** The subagent system works correctly in practice (as evidenced by tests passing and usage in `tasks/research.py` and `tasks/edit.py`), but anyone following the documentation would produce incorrect code.


# Architecture Review: subagent.md vs Actual Codebase

**Review Date:** 2026-05-08
**Reviewer:** Architecture Review Agent
**Document Reviewed:** `architecture/subagent.md`
**Workspace:** `/Users/davidbowman/projects/ainews`

---

## Executive Summary

This review compares the subagent architecture documentation (`architecture/subagent.md`) against the actual implementation in the `services/subagent/` directory. The document is **~60% accurate** with several significant discrepancies that should be addressed.

---

## 1. Verified Items (Correct)

### Directory Structure
The actual structure matches the documented structure:

```
services/subagent/
├── registry.py          # VERIFIED - _TOOL_REGISTRY with cached tool definitions
├── tools.py             # VERIFIED - Tool implementations
├── runner.py            # VERIFIED - run_subagent() and run_subagent_with_tools()
├── chain.py             # VERIFIED - Multi-step subagent chains with conditions
├── prompt_templates.py  # VERIFIED - Task prompt templates
└── middleware.py        # VERIFIED - Logging, timing, error handling middleware
```

Additional files found: `__init__.py`, `config.py`, `utils.py`, `conditions.py`

### Tool Registry (`registry.py`)
- `_TOOL_REGISTRY: dict[str, ToolDefinition] = {}` - VERIFIED (line 14)
- `ToolDefinition` imported from `services.llm.base` - VERIFIED (line 7)

### Tool Definitions (tools.py)
All documented tool functions exist as module-level functions (not classes):
- `_context_tool_get_topic_note` - VERIFIED
- `_context_tool_get_topic_notes_for_topics` - VERIFIED
- `_context_tool_get_related_articles` - VERIFIED
- `_context_tool_get_trend_memory` - VERIFIED
- `_context_tool_get_article_by_id` - VERIFIED
- `_context_tool_search_articles` - VERIFIED
- `_context_tool_get_source_health` - VERIFIED
- `_context_tool_search_web` - VERIFIED (named `_search_web` in actual)
- `_context_tool_get_search_provider` - VERIFIED (named `_get_search_provider` in actual)

### Middleware (`middleware.py`)
Middleware uses sync `wrap()` pattern as documented - VERIFIED:
- `ToolMiddleware` base class with `wrap()` method - VERIFIED
- `LoggingMiddleware` - VERIFIED
- `TimingMiddleware` - VERIFIED
- `ErrorHandlingMiddleware` - VERIFIED (undocumented but present)

### Return Type
`SubagentResponse` is the correct return type - VERIFIED (from `schemas.llm_responses`)

### Retry & Backoff
Exponential backoff with retry is implemented - VERIFIED (in `utils.py`)

### Task Revocation Checking
`_is_task_revoked()` function exists - VERIFIED (in `utils.py`)

---

## 2. Discrepancies

### Discrepancy #1: `run_subagent_with_tools` Signature Wrong

**Document says (lines 94-101):**
```python
def run_subagent_with_tools(
    stage: str,
    task_type: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    max_iterations: int = 5,
) -> SubagentResponse:
```

**Actual code (runner.py lines 331-338):**
```python
def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:
```

**Differences:**
1. Parameter order: doc says `(stage, task_type)`, actual is `(task_type, stage)`
2. `tools: list[ToolDefinition]` is required in actual but MISSING from doc
3. `article_id: int | None = None` is MISSING from doc
4. `max_iterations` is NOT a parameter - it is read from `stage_config.max_iterations`

**Impact:** High - Documentation would cause integration failures

---

### Discrepancy #2: Chain Classes Do Not Exist

**Document says (lines 128-139):**
```python
class ChainStep(BaseModel):
    name: str
    task: str
    tools: list[str] | None = None
    next_step: str | None = None
    condition: str | None = None

class Chain(BaseModel):
    name: str
    steps: list[ChainStep]
    final_step: str
```

**Actual code:**
These classes do NOT exist in the codebase. The chain functionality is defined in `schemas/pipeline.py` as:

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

**Differences:**
- `ChainStep.name` -> does not exist (step is identified by index)
- `ChainStep.task` -> renamed to `task_type`
- `ChainStep.tools` -> does not exist
- `ChainStep.next_step` -> does not exist (use condition-based branching)
- `Chain.final_step` -> does not exist (chains end when steps exhausted)
- `Chain.steps` -> is `SubagentChainStep` not `ChainStep`

**Impact:** Medium - Documentation describes a different (non-existent) API

---

### Discrepancy #3: Tool Definition in Registry Is Wrong

**Document says (lines 22-29):**
```python
_TOOL_REGISTRY: dict[str, ToolDefinition] = {}

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for tool
    cached: bool = True  # Cache tool definition?
```

**Actual code:**
- `ToolDefinition` is defined in `services/llm/base.py` (line 81) or `services/llm/types.py` (line 15), NOT inline
- The `cached` field does NOT exist in actual `ToolDefinition`

**Impact:** Medium - Documentation describes a non-existent class definition

---

### Discrepancy #4: Chain YAML Example Uses Wrong Fields

**Document shows (lines 142-156):**
```yaml
chains:
  contextualize_article:
    steps:
      - name: research
        task: "Research {article_title}"
        tools: ["web_search", "trend_memory"]
        next_step: synthesize
        condition: "result.has_new_findings"

      - name: synthesize
        task: "Synthesize findings into context"
        next_step: null
```

**Actual config structure (from SubagentChainStep):**
- `name` field does not exist - steps are identified by index
- `task` -> should be `task_type`
- `tools` field does not exist in SubagentChainStep
- `next_step` -> does not exist, conditions handle branching

**Impact:** Medium - Example config would fail validation

---

### Discrepancy #5: Usage Example Has Wrong Parameter Names

**Document says (lines 220-232):**
```python
async def _contextualize(self, article: Article, context: dict) -> str:
    """Use subagent to contextualize article"""
    return await run_subagent_with_tools(
        task=f"Contextualize this article for readers: {article.title}",
        context={
            "article": article,
            "related": context.get("related_articles", []),
            "trends": context.get("trend_memory", []),
        },
        tools=["related_articles", "trend_memory", "web_search"],
    )
```

**Actual issues:**
1. Function is NOT async (run_subagent_with_tools is sync)
2. Parameter names do not match actual signature
3. `task` parameter does not exist (should be `task_type`)
4. `context` parameter does not exist (should be `prompt_data`)
5. `tools` should be `list[ToolDefinition]` not `list[str]`

**Impact:** High - Example code would not work

---

## 3. Issues Found

### Issue #1: `_finalize_subagent_result` Is Dead Code

**Location:** `runner.py` lines 277-328

The function `_finalize_subagent_result` is defined but never called. The actual result finalization happens inline in the `run_subagent` function (lines 227-269). This function appears to be orphaned code.

**Recommendation:** Remove dead code or integrate it properly.

---

### Issue #2: ErrorHandlingMiddleware Is Undocumented

**Location:** `middleware.py` lines 64-80

The `ErrorHandlingMiddleware` class exists but is not mentioned in the documentation. It provides exception catching and logging for tool execution.

**Recommendation:** Add to documentation or confirm it is an internal implementation detail.

---

### Issue #3: Missing `config.py` Documentation

**Location:** `services/subagent/config.py`

The configuration file exists with:
- `SUBAGENT_WORKERS` environment variable (default: 8)
- `_subagent_executor` ThreadPoolExecutor
- `_get_subagent_provider_and_config()` function

None of this is documented.

---

### Issue #4: Missing `conditions.py` Documentation

**Location:** `services/subagent/conditions.py`

The conditions module provides AST-based condition evaluation for chain steps. This is completely undocumented.

---

### Issue #5: Missing `utils.py` Documentation

**Location:** `services/subagent/utils.py`

The utils module provides:
- `_retry_with_backoff()` - exponential backoff
- `_is_task_revoked()` - Celery task revocation check
- `_format_subagent_prompt()` - prompt formatting with error handling

The revocation checking is documented, but the other utilities are not.

---

### Issue #6: `__init__.py` Has Extensive Re-exports

**Location:** `services/subagent/__init__.py`

The `__init__.py` re-exports many internal functions and classes for backward compatibility. This creates a large public API surface that differs from what is documented. For example:
- `_SUBAGENT_TASK_TEMPLATES` alias
- `_escape_prompt_data` alias
- Various internal utilities

**Recommendation:** Document the intended public API vs internal modules.

---

## 4. Recommendations

### High Priority

1. **Fix `run_subagent_with_tools` documentation** - The signature, parameter order, and required parameters are all wrong. Update to reflect actual implementation.

2. **Fix usage example** - The `_contextualize` example is completely non-functional. Either fix it or remove it.

3. **Document `tools` parameter** - This required parameter is completely missing from the documentation.

### Medium Priority

4. **Document actual chain configuration** - The `SubagentChainStep` and `SubagentChainConfig` classes should be documented with their actual field names.

5. **Remove or fix Chain class examples** - The `ChainStep` and `Chain` classes do not exist. Remove or update the YAML example.

6. **Document `ErrorHandlingMiddleware`** - Either add to documentation or clarify it is internal-only.

7. **Document `ToolDefinition` correctly** - It is imported from `services.llm.base`, not defined inline.

### Low Priority

8. **Clean up dead code** - Remove `_finalize_subagent_result` if it is not used.

9. **Document `config.py`** - Add configuration section for SUBAGENT_WORKERS and executor settings.

10. **Document `conditions.py`** - Add AST-based condition evaluation to the chain documentation.

11. **Clarify public API** - The `__init__.py` re-exports create a larger API surface than documented.

---

## Summary

| Category | Count |
|----------|-------|
| Verified (correct) items | 12 |
| Discrepancies | 5 |
| Issues (bugs, missing docs) | 6 |
| Total findings | 23 |

**Overall accuracy:** ~60%

The documentation has significant issues with function signatures, class definitions, and usage examples. The core architecture (middleware pattern, tool registry, basic flow) is correctly documented, but the details are wrong in several important places.

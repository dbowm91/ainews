# Subagent System Architecture Review

Review date: 2026-05-22
Documentation: `architecture/subagent.md`

---

## Verified Claims

### 1. File Inventory
**Status: VERIFIED**

All files listed in the documentation exist in `services/subagent/`:

| File | Status |
|------|--------|
| `__init__.py` | Verified |
| `chain.py` | Verified |
| `conditions.py` | Verified |
| `config.py` | Verified |
| `middleware.py` | Verified |
| `prompt_templates.py` | Verified |
| `registry.py` | Verified |
| `runner.py` | Verified |
| `tools.py` | Verified |
| `utils.py` | Verified |

### 2. ToolDefinition Dataclass
**Status: VERIFIED**

The `ToolDefinition` dataclass in `services/llm/base.py:80-86` confirms:
- No `cached` field exists
- Fields: `name`, `description`, `parameters`, `required`, `fn`

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
```

### 3. Tool Registry
**Status: VERIFIED**

All 9 tools are registered in `_TOOL_REGISTRY` with correct names:

| Registry Name | Function | Purpose |
|--------------|----------|---------|
| `get_topic_note` | `_context_tool_get_topic_note` | Fetch editor note for topic |
| `context_notes` | `_context_tool_get_topic_notes_for_topics` | Get notes for multiple topics |
| `related_articles` | `_context_tool_get_related_articles` | Find related articles |
| `get_trend_memory` | `_context_tool_get_trend_memory` | Retrieve trend memory |
| `get_article_by_id` | `_context_tool_get_article_by_id` | Fetch article by ID |
| `search_articles` | `_context_tool_search_articles` | Search articles by query |
| `get_source_health` | `_context_tool_get_source_health` | Get source status summary |
| `web_search` | `_search_web` | External web search |
| `get_search_provider` | `_get_search_provider` | Get configured search provider |

### 4. SubagentChainStep Location
**Status: VERIFIED**

`SubagentChainStep` and `SubagentChainConfig` are defined in `schemas/pipeline.py:108-118`, NOT in `runner.py` or `chain.py`. The documentation correctly states this.

### 5. Chain Execution Method
**Status: VERIFIED**

`chain.py:122` uses `provider.chat()` directly, not `chat_with_tools()`:
```python
def _chain_call():
    return provider.chat(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        system=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

### 6. Tool Iteration in chat_with_tools
**Status: VERIFIED**

`services/llm/base.py:475` confirms while loop iteration:
```python
while iteration < max_iterations:
    iteration += 1
    # ... tool calling logic ...
```

### 7. Tool Result Re-injection
**Status: VERIFIED**

Tool results are appended to `all_messages` for subsequent LLM calls within `chat_with_tools()` (lines 537-558 in `base.py`).

### 8. Middleware Pattern
**Status: VERIFIED**

Middleware uses synchronous `wrap()` pattern in `middleware.py`.

---

## Discrepancies

### 1. ErrorHandlingMiddleware Not Documented
**Severity: Low**

The documentation shows `LoggingMiddleware` and `TimingMiddleware` in code examples, but `ErrorHandlingMiddleware` is also used in `run_subagent_with_tools()` (`runner.py:344`):

```python
middleware_chain = [
    LoggingMiddleware(logger),
    TimingMiddleware(logger),
    ErrorHandlingMiddleware(logger),  # <-- Not documented
]
```

**Recommendation:** Add `ErrorHandlingMiddleware` to the Middleware section documentation.

### 2. Tool Function Names in Documentation Table
**Severity: Low**

The documentation's "Built-in Tools" table shows function names like `get_topic_note`, but the actual implementation functions are prefixed with `_context_tool_` or `_search_`. The public names (without prefix) are what gets registered in the registry, so the documentation is technically correct about the tool names that external callers would use. However, this could be confusing when tracing through the code.

**Recommendation:** Add a note clarifying that tool implementations use internal naming convention (e.g., `_context_tool_get_topic_note`) but are registered under public names (e.g., `get_topic_note`).

---

## Bugs

**No bugs identified.** The implementation correctly follows the documented architecture.

---

## Improvements

### 1. Document Middleware Chain Order
The documentation would benefit from explaining the middleware chain order (Logging -> Timing -> ErrorHandling) and that they are applied in reverse order via `apply_middleware()`.

### 2. Document Self-Correction Behavior
The `run_subagent_with_tools()` function implements self-correction on validation errors by re-injecting an error message into the conversation (lines 401-417 in `runner.py`). This behavior is mentioned in "Error Handling" but could be more explicitly documented.

### 3. Add Configuration Example
The configuration section references `pipeline.yaml` but doesn't show a complete example. A fuller example with all available fields would improve usability.

### 4. Clarify Tool Timeout Behavior
The documentation states "Tool timeout: Skips tool, continues with available context" but the actual implementation uses `stage_config.timeout_seconds` which applies to the entire LLM call, not individual tools. If a tool times out, the entire subagent call fails, triggering a retry. This should be clarified.

---

## Summary

| Category | Result |
|----------|--------|
| File Inventory | Match |
| ToolDefinition (no cached field) | Match |
| Tool Registry | Match |
| Schema Location | Match |
| Chain Execution Method | Match |
| Tool Iteration | Match |
| Tool Result Re-injection | Match |
| Middleware Pattern | Match |
| **Overall** | **Documentation is accurate with minor omissions** |

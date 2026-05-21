# Subagent Architecture Review

## Summary

Reviewed `architecture/subagent.md` against actual implementation in `services/subagent/`. Found several discrepancies including one critical bug.

---

## Verified Claims

### File Structure (PARTIALLY ACCURATE)
**Document says:**
```
services/subagent/
├── registry.py          # _TOOL_REGISTRY with cached tool definitions
├── tools.py             # Tool implementations
├── runner.py            # run_subagent() and run_subagent_with_tools()
├── chain.py             # Multi-step subagent chains with conditions
├── prompt_templates.py  # Task prompt templates
└── middleware.py        # Logging, timing, error handling middleware
```

**Actual structure:**
```
services/subagent/
├── __init__.py
├── chain.py
├── conditions.py        # NOT DOCUMENTED
├── config.py            # NOT DOCUMENTED
├── middleware.py
├── prompt_templates.py
├── registry.py
├── runner.py
├── tools.py
└── utils.py             # NOT DOCUMENTED
```

**Issue:** Document omits `__init__.py`, `config.py`, `conditions.py`, and `utils.py`.

---

## Discrepancies and Issues

### CRIT-1: `_finalize_subagent_result` Called But Never Defined (BUG)

**Location:** `services/subagent/runner.py:444`

```python
    return _finalize_subagent_result(
        result, used_fallback, fallback_stages, last_exc,
        stage, task_type, article_id, stage_config,
    )
```

The function `run_subagent_with_tools()` at line 277 calls `_finalize_subagent_result()` which does **not exist** anywhere in the codebase. The similar function `run_subagent()` (line 38) does NOT call this function - it returns directly at line 270.

**Impact:** `run_subagent_with_tools()` will raise `NameError: name '_finalize_subagent_result' is not defined` at runtime.

---

### CRIT-2: ToolDefinition Has NO `cached` Field

**Document says (line 24-29):**
```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for tool
    cached: bool = True  # Cache tool definition?
```

**Actual implementation in `services/llm/base.py:80-86`:**
```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
```

The `cached` field does not exist. This was noted in `AGENTS.md` but the architecture document still shows it as part of the schema.

**Issue:** Document is inaccurate about ToolDefinition schema.

---

### MED-1: Middleware Classes Incomplete Documentation

**Document shows:** `LoggingMiddleware`, `TimingMiddleware`

**Actual code has:** `LoggingMiddleware`, `TimingMiddleware`, `ErrorHandlingMiddleware` (line 64-80)

**Issue:** Document omits `ErrorHandlingMiddleware`.

---

### MED-2: Tool Registry Internal Naming Mismatch

**Document's table (lines 33-43):**
| Tool | Name | Purpose |
|------|------|---------|
| `get_topic_note` | `get_topic_note` | Fetch editor note for a topic |

The left column appears to be the internal function name, but the document doesn't clarify the actual internal function names differ (e.g., `_context_tool_get_topic_note`).

**Actual function names in `services/subagent/tools.py`:**
- `_context_tool_get_topic_note` (line 13)
- `_context_tool_get_topic_notes_for_topics` (line 34)
- `_context_tool_get_related_articles` (line 52)
- `_context_tool_get_trend_memory` (line 79)
- `_context_tool_get_article_by_id` (line 99)
- `_context_tool_search_articles` (line 122)
- `_context_tool_get_source_health` (line 140)
- `_search_web` (line 160)
- `_get_search_provider` (line 176)

**Issue:** Document doesn't accurately represent the internal naming.

---

### MED-3: Chain Config Models Defined Elsewhere, Not in `chain.py`

**Document says in `chain.py` section (lines 142-151):**
```python
class SubagentChainStep(BaseModel):
    task_type: str
    ...

class SubagentChainConfig(BaseModel):
    enabled: bool = False
    ...
```

**Actual location:** These models are in `schemas/pipeline.py`, not `chain.py`. The `chain.py` imports them from `schemas.pipeline`.

**Issue:** Document incorrectly attributes model definition location.

---

### MED-4: Missing `config.py` Documentation

**Document doesn't mention `services/subagent/config.py`** which contains:
- `SUBAGENT_WORKERS` configuration (line 10)
- `_subagent_executor` ThreadPoolExecutor (line 11)
- `shutdown_executor()` function (line 14)
- `_get_subagent_provider_and_config()` (line 24)

**Issue:** Important configuration details are undocumented.

---

### MED-5: Missing `utils.py` Documentation

**Document doesn't mention `services/subagent/utils.py`** which contains:
- `_retry_with_backoff()` (line 9)
- `_is_task_revoked()` (line 19)
- `_format_subagent_prompt()` (line 30)

**Issue:** Utility functions used by runner are undocumented.

---

### MED-6: Missing `conditions.py` Documentation

**Document doesn't mention `services/subagent/conditions.py`** which contains:
- `_evaluate_condition()` - AST-based condition evaluation (line 128)

**Issue:** Condition evaluation system for chains is undocumented.

---

### MED-7: Conditions Use `result.has_new_findings` But No Such Field

**Document shows example (lines 164-165):**
```yaml
condition: "result.has_new_findings"
```

**Actual code in `conditions.py`:** The context for evaluation contains `results` (dict of step results) and `previous`. There's no `has_new_findings` attribute access pattern demonstrated.

**Issue:** Example condition may not be valid syntax.

---

## Tool Registry Verification

| Documented Tool | Actual Tool Name | Status |
|-----------------|------------------|--------|
| `get_topic_note` | `get_topic_note` | ✓ |
| `context_notes` | `context_notes` | ✓ |
| `related_articles` | `related_articles` | ✓ |
| `get_trend_memory` | `get_trend_memory` | ✓ |
| `get_article_by_id` | `get_article_by_id` | ✓ |
| `search_articles` | `search_articles` | ✓ |
| `get_source_health` | `get_source_health` | ✓ |
| `web_search` | `web_search` | ✓ |
| `get_search_provider` | `get_search_provider` | ✓ |

All 9 documented tools exist in implementation.

---

## Recommendations

1. **Fix CRIT-1:** Define `_finalize_subagent_result` function or refactor to match `run_subagent` pattern.

2. **Fix CRIT-2:** Remove `cached: bool = True` from architecture document. ToolDefinition does not have this field.

3. **Update file inventory:** Add `__init__.py`, `config.py`, `conditions.py`, `utils.py` to the documented structure.

4. **Add ErrorHandlingMiddleware:** To middleware documentation.

5. **Clarify model locations:** Note that `SubagentChainStep` and `SubagentChainConfig` are defined in `schemas/pipeline.py`.

6. **Document config.py:** Add configuration details including executor setup.

7. **Document utils.py:** Add utility functions documentation.

8. **Document conditions.py:** Add condition evaluation system documentation.

9. **Fix example condition:** Verify or correct `result.has_new_findings` example.
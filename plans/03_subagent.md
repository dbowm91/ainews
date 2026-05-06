# Subagent Architecture Verification Plan

**Review Date:** 2026-05-06  
**Architecture Document:** `architecture/subagent.md`

---

## Verification Results

### Files in `services/subagent/`

| File | Status |
|------|--------|
| registry.py | VERIFIED |
| tools.py | VERIFIED |
| runner.py | VERIFIED |
| chain.py | VERIFIED |
| prompt_templates.py | VERIFIED |
| middleware.py | VERIFIED |
| config.py | VERIFIED (extra) |
| conditions.py | VERIFIED (extra) |
| utils.py | VERIFIED (extra) |

---

### Claim: `_TOOL_REGISTRY` exists with `ToolDefinition` class

**Status:** DISCREPANCY

**Details:**
- `_TOOL_REGISTRY: dict[str, ToolDefinition]` exists in `registry.py` (line 14) - VERIFIED
- `ToolDefinition` is NOT defined in `registry.py` - it is imported from `services.llm.base`
- The doc shows `class ToolDefinition(BaseModel)` but actual implementation is a `@dataclass` in `services.llm.base` (line 81)
- `ToolDefinition` fields: `name`, `description`, `parameters`, `required`, `fn`
- **Missing field:** `cached` field mentioned in doc does not exist
- **Extra field:** `required` field not mentioned in doc

---

### Claim: Built-in tools exist with documented names

**Status:** DISCREPANCY

| Doc Tool Name | Doc Function | Actual Tool Name | Actual Function | Match |
|--------------|--------------|------------------|-----------------|-------|
| `context_notes` | `get_topic_note` | `context_notes` | `_context_tool_get_topic_notes_for_topics` | **MISMATCH** |
| `related_articles` | (implicit) | `related_articles` | `_context_tool_get_related_articles` | VERIFIED |
| `trend_memory` | `get_trend_memory` | `get_trend_memory` | `_context_tool_get_trend_memory` | VERIFIED |
| `article_lookup` | `get_article_by_id` | `get_article_by_id` | `_context_tool_get_article_by_id` | VERIFIED |
| `article_search` | `search_articles` | `search_articles` | `_context_tool_search_articles` | VERIFIED |
| `source_health` | `get_source_health` | `get_source_health` | `_context_tool_get_source_health` | VERIFIED |
| `web_search` | (implicit) | `web_search` | `_search_web` | VERIFIED |

**Bug:** The `context_notes` tool does NOT call `get_topic_note`. There is a separate tool called `get_topic_note` (line 196-210 in tools.py) that takes `topic` and `source` parameters. The `context_notes` tool actually calls `_context_tool_get_topic_notes_for_topics` which takes `topics: list[str]`.

---

### Claim: Tool implementations have `execute()` methods

**Status:** DISCREPANCY

The documented architecture shows:
```python
class ContextNotesTool(Tool):
    async def execute(self, topic: str) -> dict:
```

**Actual implementation:** Tools in `tools.py` are NOT classes - they are module-level functions:
```python
def _context_tool_get_topic_note(topic: str, source: str | None = None) -> str:
```

Each function is wrapped in a `ToolDefinition` with a `fn` field, but there is no `Tool` base class and no `execute()` method pattern.

---

### Claim: `run_subagent` and `run_subagent_with_tools` functions exist

**Status:** VERIFIED with DISCREPANCIES in signatures

**Actual signatures:**
```python
def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:

def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:
```

**Doc signatures:**
```python
def run_subagent(
    task: str,
    context: dict | None = None,
    tools: list[str] | None = None,
    model: str | None = None,
) -> SubagentResult:

def run_subagent_with_tools(
    task: str,
    context: dict | None = None,
    tools: list[str] | None = None,
    max_iterations: int = 5,
) -> SubagentResult:
```

The actual implementation has a completely different signature - it uses `task_type` + `stage` + `prompt_data` pattern instead of `task` + `context` + `tools` pattern.

---

### Claim: `ChainStep` and `Chain` classes exist in `chain.py`

**Status:** DISCREPANCY

- `ChainStep` class does NOT exist in `chain.py`
- `Chain` class does NOT exist in `chain.py`
- Actual chain schema is `SubagentChainStep` and `SubagentChainConfig` in `schemas/pipeline.py`

**Schema mismatch:**
```python
# Documented (chain.py):
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

# Actual (schemas/pipeline.py):
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

Field names differ: `name` vs `task_type`, `task` vs `prompt_data_template`, `tools` not present, `next_step` not present, `final_step` not present.

---

### Claim: `LoggingMiddleware` and `TimingMiddleware` exist

**Status:** DISCREPANCY

**Documented interface:**
```python
class LoggingMiddleware:
    async def on_request(self, task: str, context: dict): ...
    async def on_response(self, result: SubagentResult): ...
    async def on_error(self, error: Exception): ...

class TimingMiddleware:
    async def on_request(self, task: str, context: dict):
        self.start_time = time.time()
    async def on_response(self, result: SubagentResult):
        duration = time.time() - self.start_time
        logger.info(f"Subagent took {duration:.2f}s")
```

**Actual implementation:**
```python
class LoggingMiddleware(ToolMiddleware):
    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        # Synchronous wrapper, not async

class TimingMiddleware(ToolMiddleware):
    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        # Synchronous wrapper, not async
```

**Critical issues:**
1. No `on_request`, `on_response`, `on_error` methods exist
2. Middleware is synchronous `wrap()` pattern, not async request/response hooks
3. Middleware operates on tool functions, not subagent requests/responses
4. `ErrorHandlingMiddleware` exists but is not documented

---

## Bug Findings

### HIGH: Tool name-function mismatch for `context_notes`
- **File:** `services/subagent/tools.py`
- **Issue:** Document says `context_notes` tool calls `get_topic_note` function
- **Reality:** `context_notes` calls `_context_tool_get_topic_notes_for_topics`, and `get_topic_note` is a separate tool with different parameters
- **Impact:** Anyone using the documented API will get incorrect behavior
- **Fix:** Either rename tools to match doc, or update documentation

### HIGH: Chain/ChainStep classes do not exist where documented
- **File:** `services/subagent/chain.py`, `schemas/pipeline.py`
- **Issue:** Document references `ChainStep` and `Chain` in `chain.py`, but actual classes are `SubagentChainStep` and `SubagentChainConfig` in `schemas/pipeline.py`
- **Impact:** Code referencing `from services.subagent.chain import ChainStep, Chain` will fail
- **Fix:** Add backward-compat aliases or update documentation

### HIGH: Middleware has wrong interface
- **File:** `services/subagent/middleware.py`
- **Issue:** Documented `on_request`, `on_response`, `on_error` async methods do not exist
- **Reality:** Only `wrap()` synchronous method exists for tool wrapping
- **Impact:** Cannot use middleware for subagent request/response logging as documented
- **Fix:** Implement request/response middleware pattern or update documentation

### MEDIUM: `run_subagent` signature mismatch
- **File:** `services/subagent/runner.py`
- **Issue:** Document shows `run_subagent(task, context, tools, model)` but actual is `run_subagent(task_type, stage, prompt_data, response_model, article_id)`
- **Impact:** API users will use wrong parameters
- **Fix:** Update documentation or add wrapper function for legacy API

### MEDIUM: Tool implementations are functions, not classes with `execute()`
- **File:** `services/subagent/tools.py`
- **Issue:** Document shows `ContextNotesTool(Tool)` class with `async def execute()`, but actual tools are module-level functions
- **Impact:** Cannot use OOP tool pattern documented
- **Note:** Current function-based approach is actually cleaner for the use case

### LOW: `cached` field missing from `ToolDefinition`
- **File:** `services/llm/base.py`
- **Issue:** Document shows `cached: bool = True` field in `ToolDefinition`
- **Reality:** Field does not exist in actual `ToolDefinition`
- **Impact:** Documentation is misleading about caching behavior

### LOW: `SubagentResult` return type incorrect
- **File:** `services/subagent/runner.py`
- **Issue:** Document says `run_subagent` returns `SubagentResult`
- **Reality:** Returns `SubagentResponse` from `schemas.llm_responses`

---

## Improvement Opportunities

### 1. Standardize tool naming conventions
Current tools mix `get_*`, `*_tool_*`, and bare names. Consider:
- `get_topic_note` (singular) vs `context_notes` (plural) for batch operations
- Document which is for what

### 2. Add chain execution to `chain.py`
`chain.py` has `run_subagent_chain()` but no `Chain` or `ChainStep` classes. Consider:
- Add Pydantic models for type-safe chain definitions
- Or ensure `schemas/pipeline.py` models are imported for convenience

### 3. Implement request/response middleware pattern
Current middleware only wraps tools. For true request/response middleware:
```python
class RequestResponseMiddleware:
    async def on_request(self, task: str, context: dict): ...
    async def on_response(self, result: SubagentResponse): ...
    async def on_error(self, error: Exception): ...
```

### 4. Add comprehensive docstrings
Many functions lack documentation. Add docstrings explaining:
- Tool parameters and return values
- Middleware behavior
- Chain execution flow

### 5. Add `Tool` base class (optional)
If the documented `Tool` class pattern is desired:
```python
class Tool(ABC):
    @abstractmethod
    async def execute(self, **kwargs) -> dict: ...
```

---

## Action Items

| Priority | Item | Files Affected |
|----------|------|----------------|
| HIGH | Fix or document `context_notes` tool mismatch | `architecture/subagent.md`, `services/subagent/tools.py` |
| HIGH | Add `ChainStep` and `Chain` aliases to `chain.py` | `services/subagent/chain.py` |
| HIGH | Document actual middleware interface (`wrap()` vs `on_request`) | `architecture/subagent.md` |
| MEDIUM | Update `run_subagent` signature in documentation | `architecture/subagent.md` |
| MEDIUM | Document actual tool implementation pattern (functions not classes) | `architecture/subagent.md` |
| LOW | Add `cached` field to `ToolDefinition` or remove from doc | `services/llm/base.py`, `architecture/subagent.md` |
| LOW | Fix `SubagentResult` -> `SubagentResponse` return type in doc | `architecture/subagent.md` |
| LOW | Add chain classes with proper field names to `chain.py` | `services/subagent/chain.py` |

# Subagent System

The `services/subagent/` package contains tool-enabled LLM agents that can search for context, fetch related articles, and provide editorial contextualization.

## Architecture

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

**Note:** File inventory differs from older documentation. Current structure includes `__init__.py`, `config.py`, `conditions.py`, and `utils.py`.

## Tool Registry (`registry.py`)

Tools are registered in `_TOOL_REGISTRY`:

```python
_TOOL_REGISTRY: dict[str, ToolDefinition] = {}

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema for tool
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
    # Note: ToolDefinition does NOT have a `cached` field
```

### Built-in Tools

| Tool | Name | Purpose |
|------|------|---------|
| `get_topic_note` | `get_topic_note` | Fetch editor note for a topic |
| `context_notes` | `context_notes` | Get topic notes for multiple topics |
| `related_articles` | `related_articles` | Find related articles by topics |
| `get_trend_memory` | `get_trend_memory` | Retrieve trend memory entries |
| `get_article_by_id` | `get_article_by_id` | Fetch article by ID |
| `search_articles` | `search_articles` | Search articles by query |
| `get_source_health` | `get_source_health` | Get source status summary |
| `get_topic_gap_report` | `get_topic_gap_report` | Analyze topic coverage gaps |
| `get_source_performance` | `get_source_performance` | Get source performance metrics |
| `get_quality_report` | `get_quality_report` | Get article quality report |
| `find_dedupe_candidates` | `find_dedupe_candidates` | Find potential duplicate articles |
| `estimate_stage_cost` | `estimate_stage_cost` | Estimate LLM cost for a stage |
| `web_search` | `web_search` | External web search |
| `get_search_provider` | `get_search_provider` | Get configured search provider |

## Tool Implementations (`tools.py`)

Tools are module-level functions registered in `_TOOL_REGISTRY`:

**Note on naming:** Tool implementations use internal naming convention (prefixed with `_context_tool_` or `_search_`), but are registered under public names (e.g., `get_topic_note`, `web_search`). The public names are what external callers use.

```python
def _context_tool_get_topic_note(topic: str, source: str | None = None) -> str:
    """Returns note content or 'No note found for this topic.'"""

def _context_tool_get_topic_notes_for_topics(topics: list[str]) -> str:
    """Returns formatted string of topic->notes mappings"""

def _context_tool_get_related_articles(
    topics: list[str], exclude_id: int, limit: int = 5,
) -> str:
    """Returns formatted list of related articles"""

def _context_tool_get_trend_memory(
    topics: list[str], min_importance: int = 1, max_age_days: int | None = None,
) -> str:
    """Returns formatted trend memory entries"""

def _context_tool_get_article_by_id(article_id: int) -> str:
    """Returns JSON string of article metadata"""

def _context_tool_search_articles(query: str, limit: int = 5) -> str:
    """Returns JSON array of matching articles"""

def _context_tool_get_source_health() -> str:
    """Returns JSON array of source health summaries"""

def _search_web(query: str, max_results: int = 5) -> str:
    """Returns formatted web search results"""

def _context_tool_get_search_provider(provider_id: str | None = None) -> str:
    """Returns name of search provider in use"""
```

## Subagent Runner (`runner.py`)

### Main Entry Points

```python
def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:
    """Run a single-step subagent with optional tools"""

def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:
    """Run a multi-step subagent with tool calling loop"""

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

**Location**: These schemas are defined in `schemas/pipeline.py`, not in `runner.py` or `chain.py`.

### Features

- **Retry with exponential backoff**: Handles transient failures
- **Task revocation checking**: Stops if Celery task is revoked
- **Tool-calling support**: Via `chat_with_tools()`
- **Self-correction**: Re-validates output and retries on failure
- **`copy.deepcopy()` for tool functions**: Prevents middleware compounding on cached tool definitions. Each invocation wraps the tool function fresh rather than re-wrapping an already-wrapped function.
- **max_iterations default**: `max_iterations` defaults to 5 (ge=1, le=20)

### Self-Correction Mechanism

The subagent runner uses a `self_corrected` flag to track whether the LLM output required self-correction:

```python
# At runner.py:401-417:
self_corrected = False
for attempt in range(max_attempts):
    response = llm_provider.chat_with_tools(...)
    if validation_success:
        return response
    # Adjust prompt with correction hint
    self_corrected = True
# Return fallback or raise
```

Self-correction occurs when structured output validation fails. The runner adjusts the prompt with correction hints and retries with `max_retries + 1` total attempts.

### Helper Functions (`utils.py`)

`_format_subagent_prompt(template, prompt_data, stage, task_type)` - Formats subagent prompt templates by escaping prompt_data via `escape_prompt_data()` and substituting into the template. Returns `None` if template key is missing (logs warning with stage/task_type context). Used by `run_subagent_with_tools()` to build context-rich prompts.

### Execution Flow

```
1. Build messages with system prompt + context
2. Call LLM with tool definitions via chat_with_tools()
3. If tool_calls:
   a. Execute tools in the LLM provider
   b. Re-inject tool results into messages for next turn
   c. Continue to next iteration (up to max_iterations)
4. Return final response
```

**Note**: Tool iteration happens inside `BaseLLMProvider.chat_with_tools()` via a while loop (line 475 in `services/llm/base.py`). Tool results ARE re-injected into `all_messages` for subsequent LLM calls within the same `chat_with_tools()` invocation. This enables multi-turn tool use within a single API call, up to `max_iterations` limit.

## Chain System (`chain.py`)

Multi-step chains with conditional branching:

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

**Location**: These schemas are defined in `schemas/pipeline.py`, not in `runner.py` or `chain.py`.

**Note on chain execution**: Chains use `provider.chat()` directly, not `chat_with_tools()`. This means chains do not support tool calling - they are for simple multi-step prompts without tool use. If tool support is needed, use `run_subagent_with_tools()` instead.

Chain configuration is loaded from `pipeline.yaml` under the `subagent.chains` section:

```yaml
subagent:
  chains:
    contextualize_article:
      enabled: true
      max_length: 5
      steps:
        - task_type: "research"
          prompt_data_template: "Research {article_title}"
          condition: "result.has_new_findings"
        - task_type: "synthesize"
          prompt_data_template: "Synthesize findings into context"
```

**Note:** Steps are identified by index, not name. Conditions use AST-based evaluation from `services/subagent/conditions.py`.

## Middleware (`middleware.py`)

Middleware uses a sync `wrap()` pattern to intercept tool execution. The middleware chain is applied in reverse order via `apply_middleware()`, so the first middleware in the list wraps the outermost layer.

**Middleware chain (as applied to tool function):**
- `LoggingMiddleware` (outermost) - logs tool call start/completion/failure
- `TimingMiddleware` (middle) - measures and logs execution time
- `ErrorHandlingMiddleware` (innermost) - catches exceptions, logs them with traceback, then re-raises

Execution flow: Logging → Timing → ErrorHandling → tool function → ErrorHandling → Timing → Logging

```python
class ToolMiddleware:
    """Base class for tool execution middleware."""
    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a tool function with middleware behavior."""

class LoggingMiddleware(ToolMiddleware):
    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.logger.info("Tool %s called", func.__name__)
            try:
                result = func(*args, **kwargs)
                self.logger.info("Tool %s completed", func.__name__)
                return result
            except Exception as e:
                self.logger.error("Tool %s failed: %s", func.__name__, e)
                raise
        return wrapped

class TimingMiddleware(ToolMiddleware):
    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                self.logger.debug("Tool %s executed in %.3fs", func.__name__, elapsed)
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                self.logger.debug("Tool %s failed after %.3fs: %s", func.__name__, elapsed, e)
                raise
        return wrapped

class ErrorHandlingMiddleware(ToolMiddleware):
    """Logs exceptions from tool execution and re-raises them."""
    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error("Tool %s failed: %s", func.__name__, e)
                raise
        return wrapped
```

## Configuration

From `pipeline.yaml`:

```yaml
subagent:
  max_iterations: 5
  tool_timeout: 30.0  # Timeout for individual tool execution (seconds)
  default_model: "ollama-local"
  default:
    enabled: true
    tools:
      - context_notes
      - related_articles
      - get_trend_memory
      - get_article_by_id
      - search_articles
      - web_search
```

## Usage in Editor

The editor service uses subagent for contextualization:

## Usage Example

```python
from services.subagent import run_subagent_with_tools
from services.llm.base import ToolDefinition

def contextualize_article(article: Article, context: dict) -> str:
    """Use subagent to contextualize article"""
    return run_subagent_with_tools(
        task_type="contextualize",
        stage="edit",
        prompt_data={
            "article": article,
            "related": context.get("related_articles", []),
            "trends": context.get("trend_memory", []),
        },
        response_model=ContextualizedResult,
        tools=[tool_definition for tool_definition in _TOOL_REGISTRY.values()],
    )
```

## Error Handling

- **Validation failure**: Self-corrects by retrying with adjusted prompt
- **Tool timeout**: Skips tool, continues with available context
- **LLM error**: Retries with exponential backoff (`stage_config.max_retries + 1` attempts, default 2)
- **Revocation**: Checks `current_task.request.id` and stops if revoked

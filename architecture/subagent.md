# Subagent System

The `services/subagent/` package contains tool-enabled LLM agents that can search for context, fetch related articles, and provide editorial contextualization.

## Architecture

```
services/subagent/
├── registry.py          # _TOOL_REGISTRY with cached tool definitions
├── tools.py             # Tool implementations
├── runner.py            # run_subagent() and run_subagent_with_tools()
├── chain.py             # Multi-step subagent chains with conditions
├── prompt_templates.py  # Task prompt templates
└── middleware.py        # Logging, timing, error handling middleware
```

## Tool Registry (`registry.py`)

Tools are registered in `_TOOL_REGISTRY`:

```python
_TOOL_REGISTRY: dict[str, ToolDefinition] = {}

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for tool
    cached: bool = True  # Cache tool definition?
```

### Built-in Tools

| Tool | Name | Purpose |
|------|------|---------|
| `context_notes` | `get_topic_note` | Fetch editor notes for a topic |
| `related_articles` | `related_articles` | Find related articles by topics |
| `trend_memory` | `get_trend_memory` | Retrieve trend memory entries |
| `article_lookup` | `get_article_by_id` | Fetch article by ID |
| `article_search` | `search_articles` | Search articles by query |
| `source_health` | `get_source_health` | Get source status summary |
| `web_search` | `web_search` | External web search |

## Tool Implementations (`tools.py`)

Tools are module-level functions registered in `_TOOL_REGISTRY`:

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

def _context_tool_search_web(query: str, max_results: int = 5) -> str:
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
    stage: str,
    task_type: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    max_iterations: int = 5,
) -> SubagentResponse:
    """Run a multi-step subagent with tool calling loop"""
```

### Features

- **Retry with exponential backoff**: Handles transient failures
- **Task revocation checking**: Stops if Celery task is revoked
- **Tool-calling support**: Via `chat_with_tools()`
- **Self-correction**: Re-validates output and retries on failure

### Execution Flow

```
1. Build messages with system prompt + context
2. Call LLM with tool definitions
3. If tool_calls:
   a. Execute tools in parallel
   b. Add results to messages
   c. Goto 2 (max iterations)
4. Return final response
```

## Chain System (`chain.py`)

Multi-step chains with conditional branching:

```python
class ChainStep(BaseModel):
    name: str
    task: str
    tools: list[str] | None = None
    next_step: str | None = None
    condition: str | None = None  # "result.contains_key('needs_research')"

class Chain(BaseModel):
    name: str
    steps: list[ChainStep]
    final_step: str
```

### Chain Example

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
        next_step: null  # Ends chain
```

## Middleware (`middleware.py`)

Middleware uses a sync `wrap()` pattern to intercept tool execution:

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
```

## Configuration

From `pipeline.yaml`:

```yaml
subagent:
  enabled: true
  max_iterations: 5
  tool_timeout: 30.0
  default_model: "ollama-local"
  tools:
    - context_notes
    - related_articles
    - trend_memory
    - article_lookup
    - article_search
    - web_search
```

## Usage in Editor

The editor service uses subagent for contextualization:

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

## Error Handling

- **Validation failure**: Self-corrects by retrying with adjusted prompt
- **Tool timeout**: Skips tool, continues with available context
- **LLM error**: Retries with exponential backoff (max 3 attempts)
- **Revocation**: Checks `current_task.request.id` and stops if revoked

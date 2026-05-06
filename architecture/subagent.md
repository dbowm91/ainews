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

```python
class ContextNotesTool(Tool):
    name = "context_notes"
    description = "Get editor notes for a topic"

    async def execute(self, topic: str) -> dict:
        # Queries TopicNote model
        # Returns {notes: [...], topic: str}

class RelatedArticlesTool(Tool):
    name = "related_articles"
    description = "Find related articles by topics"

    async def execute(self, topics: list[str], limit: int = 5) -> dict:
        # Uses RelatedService
        # Returns {articles: [...]}

class TrendMemoryTool(Tool):
    name = "trend_memory"
    description = "Retrieve trend memory entries"

    async def execute(self, topic: str, limit: int = 5) -> dict:
        # Queries TrendMemory
        # Returns {entries: [...]}

class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information"

    async def execute(self, query: str, limit: int = 5) -> dict:
        # Uses DuckDuckGo by default
        # Returns {results: [...]}
```

## Subagent Runner (`runner.py`)

### Main Entry Points

```python
async def run_subagent(
    task: str,
    context: dict | None = None,
    tools: list[str] | None = None,
    model: str | None = None,
) -> SubagentResult:
    """Run a single-step subagent with optional tools"""

async def run_subagent_with_tools(
    task: str,
    context: dict | None = None,
    tools: list[str] | None = None,
    max_iterations: int = 5,
) -> SubagentResult:
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

Request/response middleware for logging and error handling:

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

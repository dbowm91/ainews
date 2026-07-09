# Subagent System

## Overview

The subagent system provides lightweight LLM-backed contextualization for pipeline stages. It runs synchronously within parent Celery tasks using a thread pool (`_subagent_executor`), allowing pipeline stages to request additional context without blocking the main task execution.

Subagents enhance pipeline stages by:

- Fetching relevant topic notes from the context service
- Retrieving related articles for editorial context
- Accessing trend memory for pattern recognition
- Searching internal articles by keyword
- Providing source health information
- Performing web searches for research synthesis

The `SUBAGENT_WORKERS` environment variable controls the thread pool size (default: 8).

## Tool Registry

Tools are registered via `initialize_tool_registry()` at application startup. This function populates the global tool registry with all built-in tools. The registry holds `ToolDefinition` objects that define the tool's name, description, JSON schema, and Python function.

To retrieve all available tools, call `get_registered_tools()` which returns `list[ToolDefinition]`.

### Available Tools

The subagent system provides 14 built-in tools (12 context + 2 search):

| Tool Name | Description |
|-----------|-------------|
| `get_topic_note` | Retrieve a topic note from the context service for a given topic and optional source |
| `context_notes` | Batch retrieval of topic notes for multiple topics |
| `related_articles` | Find related articles based on topics, excluding a specific article ID |
| `get_trend_memory` | Get trend memory entries for topics with optional importance filtering |
| `get_article_by_id` | Get article details (ID, title, pipeline_status, impact_score, created_at) |
| `search_articles` | Full-text search via ILIKE against article titles |
| `get_source_health` | Get summary of all source health status |
| `get_topic_gap_report` | Identify topic coverage gaps |
| `get_source_performance` | Get source performance metrics |
| `get_quality_report` | Get quality report for an article |
| `find_dedupe_candidates` | Find potential duplicate articles |
| `estimate_stage_cost` | Estimate LLM cost for a pipeline stage |
| `web_search` | Search the web for information on a topic |
| `get_search_provider` | Get the current search provider being used |

### Tool Function Signatures

```python
def _get_topic_note(topic: str, source: str | None = None) -> str:
    """Returns note content or 'No note found for this topic.'"""

def _context_notes(topics: list[str]) -> str:
    """Returns formatted string of topic->notes mappings"""

def _related_articles(topics: list[str], exclude_id: int, limit: int = 5) -> str:
    """Returns formatted list of related articles"""

def _get_trend_memory(topics: list[str], min_importance: int = 1, max_age_days: int | None = None) -> str:
    """Returns formatted trend memory entries with importance tiers"""

def _get_article_by_id(article_id: int) -> str:
    """Returns JSON string of article metadata"""

def _search_articles(query: str, limit: int = 5) -> str:
    """Returns JSON array of matching articles"""

def _get_source_health() -> str:
    """Returns JSON array of source health summaries"""

def _web_search(query: str, max_results: int = 5) -> str:
    """Returns formatted web search results"""

def _get_search_provider(provider_id: str | None = None) -> str:
    """Returns name of search provider in use"""
```

## Chain Execution

`run_subagent_chain()` in `services/subagent.py` executes multi-step chains defined in `pipeline.yaml`. Each chain step:

1. **Provider Resolution**: Calls `_get_subagent_provider_and_config()` to obtain a fresh LLM provider instance. This supports provider fallback if one fails.

2. **Prompt Escaping**: Uses `_escape_prompt_data()` to safely embed user-supplied or LLM-generated content in XML-formatted prompts, preventing injection attacks.

3. **Provider Fallback**: If a provider fails, execution moves to the next provider in the chain. This ensures resilience against transient provider failures.

### Chain Configuration

Each pipeline stage can define a `subagent:` section in `pipeline.yaml`:

```yaml
stages:
  edit:
    subagent:
      role: editor
      prompt: path/to/prompt.txt
      max_retries: 3
      timeout_seconds: 120
      retry_delay: 5
      tools:
        - context_notes
        - related_articles
        - get_trend_memory
```

## Tool-Calling Infrastructure

`run_subagent_with_tools()` at `services/subagent.py:610` wires the tool-calling infrastructure into pipeline tasks. When a pipeline stage has `tools:` configured in its subagent block, the system uses this function instead of `run_subagent()`.

### Current Integrations

- **Research Stage**: Uses web synthesis tools for pulling in external context
- **Edit Stage**: Uses contextualization tools (topic notes, related articles, trend memory) for editor contextualization

The function uses the registered tools and invokes them based on LLM tool calls, returning structured responses.

## Built-in Task Templates

Two task templates are built into the subagent system:

### `research_synthesis`

```xml
<source_article>
  <title>{title}</title>
  <body>{body}</body>
</source_article>

<web_results>
{web_results}
</web_results>

Synthesize the external sources into a coherent summary...
```

### `edit_contextualization`

```xml
<draft_article>
{draft}
</draft_article>

<research_brief>
{brief}
</research_brief>

<topic_notes>
{topic_notes}
</topic_notes>

<related_articles>
{related_articles}
</related_articles>

<trend_memory>
{trend_memory}
</trend_memory>

Review the draft in light of the research brief...
```

Custom templates can be specified via the `task_template` field in the stage configuration, loaded from the `schemas/pipeline.py` `BASE_DIR` directory.

## Failure Scenarios

Subagent failures degrade gracefully and **never crash the parent pipeline**. Common failure scenarios:

| Scenario | Behavior |
|----------|----------|
| Provider timeout | Retries with next available provider or returns fallback |
| Invalid tool call | Returns error message to LLM for retry |
| Tool function error | Catches exception, returns error string |
| All providers fail | Returns fallback content, pipeline continues |

The subagent system is designed to be fault-tolerant. Even complete subagent failure results in graceful degradation rather than pipeline failure.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SUBAGENT_WORKERS` | 8 | Thread pool size for subagent execution |

### Pipeline Configuration

Each pipeline stage in `pipeline.yaml` supports the following subagent options:

| Option | Type | Description |
|--------|------|-------------|
| `role` | string | LLM role to use (e.g., "editor", "researcher") |
| `prompt` | string | Path to prompt template file |
| `max_retries` | int | Maximum retry attempts |
| `timeout_seconds` | int | Timeout for subagent execution |
| `retry_delay` | int | Delay between retries |
| `tools` | list | List of tool names to enable |
| `task_template` | string | Path to custom task template |
| `provider` | string | Specific LLM provider ID |
| `model` | string | Specific model name |
| `temperature` | float | Sampling temperature |
| `max_tokens` | int | Maximum tokens in response |

## Usage in Pipeline Tasks

To use the subagent system in a pipeline task:

```python
from services.subagent import run_subagent_chain, run_subagent_with_tools

# For simple chain execution
result = run_subagent_chain(
    stage_config=stage_config,
    prompt_data={"title": "...", "body": "..."},
    task_type="research_synthesis"
)

# For tool-calling mode
result = run_subagent_with_tools(
    stage_config=stage_config,
    prompt_data={"draft": "...", "brief": "..."},
    task_type="edit_contextualization"
)
```

## Known Issues

1. **Hardcoded iteration limit**: `max_iterations=5` is hardcoded in `_run_chain()` loop (line ~516). This limits the number of chain iterations.

2. **Retry loop provider fallback**: The retry loop in `run_subagent_chain()` correctly moves to the next provider on timeout. This was fixed in wave3_4 - earlier versions would not properly fall back on timeout.

3. **Function signature mismatch**: `initialize_tool_registry()` signature may need updating to support filtered tool registration (documented in `plans/plan.md`).
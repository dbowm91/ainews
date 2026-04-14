---
name: aiharness
description: "AI harness, subagent system, and trend memory — covering LLM provider architecture, subagent orchestration, tool registry, tiered memory, and agentic patterns. Triggers: subagent, editor, trend memory, LLM tools, AI harness, agentic, memory system, propose memory."
---

## Overview

This codebase has a layered AI pipeline: pipeline stages (selector → researcher → writer → editor) run as Celery tasks with circuit breakers and rate limiting. Within stages, lightweight subagents run synchronously via `services/subagent.py` to handle specific tasks like contextualization and research synthesis. A tiered trend memory system (`services/trend_memory.py`) gives the editor persistent, LLM-judged memory across articles.

## LLM Provider Architecture

All LLM providers implement `BaseLLMProvider` (`services/llm/base.py`) with:
- `chat()` — plain completions
- `chat_structured()` — Pydantic-validated output via `response_model`
- `chat_with_tools()` — tool/function calling
- `health_check()` — readiness probe

Providers are registered in `providers.yaml` and loaded via `services/llm/__init__.py:get_provider_for_role()` which integrates circuit breakers. Any provider with `type: openai` works via the OpenAI-compatible adapter (`services/llm/openai.py`), including MiniMax, DeepSeek, and Zai (BigModel.cn).

**Key provider files:**
- `services/llm/openai.py` — OpenAI + all OpenAI-compatible providers
- `services/llm/anthropic.py` — native Anthropic API
- `services/llm/gemini.py` — native Google Gemini API
- `services/llm/ollama.py` — local Ollama models

## Subagent System

`services/subagent.py` runs lightweight agentic tasks synchronously inside Celery workers. It is NOT a general-purpose agent framework — it is designed for pipeline-specific tasks.

**Core functions:**
- `run_subagent(task_type, stage, prompt_data, response_model, article_id)` — single-step subagent
- `run_subagent_with_tools(task_type, stage, prompt_data, response_model, tools, article_id)` — with tool calling (max 5 iterations)
- `run_subagent_chain(chain_name, steps, initial_prompt_data, article_id)` — multi-step chains with conditional execution
- `initialize_tool_registry()` — registers built-in tools; call once at startup

**Built-in tools** (`_build_context_tools()` + `_build_search_tools()`):
- `get_topic_note(topic, source)` — single topic note lookup
- `get_topic_notes_for_topics(topics)` — batch topic note lookup
- `get_related_articles(topics, exclude_id, limit)` — related article search
- `get_trend_memory(topics, min_importance, max_age_days)` — tiered trend memory retrieval
- `search_web(query, max_results)` — web search

**Tool registration pattern:**
```python
from services.llm.base import ToolDefinition

def register_tool(definition: ToolDefinition) -> None: ...

tools.append(ToolDefinition(
    name="my_tool",
    description="What it does",
    parameters={...},  # JSON Schema
    fn=my_function,   # callable
))
```

After defining tools, call `register_tool()` in `initialize_tool_registry()` and add the tool name to the `tools:` list in `pipeline.yaml` for the relevant stage.

**Prompt templates** are defined in `_SUBAGENT_TASK_TEMPLATES` and resolved at call time. The `edit_contextualization` template receives: `{draft}`, `{brief}`, `{topic_notes}`, `{related_articles}`, `{trend_memory}`.

**Adding a new tool to the subagent:**
1. Define the tool function and `ToolDefinition` in `services/subagent.py:_build_context_tools()` or a new `_build_*_tools()` function
2. Register it in `initialize_tool_registry()`
3. Add the tool name to `pipeline.yaml: subagent.<stage>.tools`

## Tiered Trend Memory System

`services/trend_memory.py` provides persistent, LLM-judged memory for the editor agent. Unlike manual topic notes, the LLM itself decides what to store based on signal quality.

**Design principles:**
- **LLM-as-judge**: After an article is finalized, `propose_trend_memory(article)` asks the LLM to extract 0–3 high-signal entries. The LLM decides importance tier — not rules.
- **Tiered TTL**: Low=7 days, medium=30 days, high=no expiry (configurable in `pipeline.yaml:memory:`)
- **Automatic consolidation**: Nightly Celery task `consolidate_trend_memory` promotes low→medium when a high-importance entry exists for the same topic
- **Editor-only (initially)**: The writer does not yet have trend memory access; the system is designed to generalize

**Key functions:**

| Function | Purpose |
|----------|---------|
| `propose_trend_memory(article)` | Post-finalization LLM extraction; calls `_call_llm_for_memory()` then `_save_memory_entries()` |
| `get_memory_for_topics(topics, min_importance, max_age_days)` | Retrieve valid memory entries filtered by topic, tier, freshness |
| `_format_memory_for_prompt(memory_entries)` | Formats entries as `<high_importance_trends>`, `<medium_importance_trends>`, `<recent_trends>` XML sections |
| `consolidate_topic(topic)` | When high-importance entry exists, promote overlapping low entries to medium + set TTL |
| `consolidate_all_topics()` | Run consolidation across all topics with high-importance entries |
| `purge_expired()` | Delete all rows where `expires_at <= now` |

**The `TrendMemory` model** has: `topic`, `signal`, `importance` (1-3), `source_article_id`, `expires_at`, `last_consolidated_at`, `created_at`.

**How it integrates into the editor:**
1. `tasks/edit.py` calls `_format_memory_for_prompt(get_memory_for_topics(article.topics))` and passes it as `{trend_memory}` in the `edit_contextualization` prompt
2. After the article transitions to `DONE`, `propose_trend_memory(article)` fires in a non-blocking try/except — failures are logged but never crash the pipeline
3. The nightly `consolidate_trend_memory` Celery task runs at 3:30 AM

**Configuration in `pipeline.yaml`:**
```yaml
memory:
  ttl_days_low: 7          # Low-importance entries expire after 7 days
  ttl_days_medium: 30       # Medium-importance entries expire after 30 days
  ttl_days_high: 0          # High-importance entries never expire (0 = no TTL)
  consolidation_cooldown_hours: 24   # Don't re-consolidate a topic within 24h
  max_entries_per_propose: 3         # LLM extracts max 3 entries per article
  consolidation_merge_window_hours: 72  # Low entries within 72h of a high entry get promoted
```

**Adding trend memory to the writer (future):**
1. In `services/writer.py`, add a `build_writer_prompt_with_memory()` variant that fetches `get_memory_for_topics(topics)` and formats it
2. In `tasks/write.py`, call the memory fetch before building the writer prompt
3. Add `trend_memory` to the `tools:` list in `pipeline.yaml: subagent.research` if the research subagent also needs access
4. Wire into `propose_trend_memory` after the writer stage finalizes (change the call site from `tasks/edit.py` to the finalize hook)

## Agentic Patterns to Know

**Subagent vs. pipeline stage**: Subagents run *within* a pipeline stage for contextual tasks. Pipeline stages are Celery tasks with full retry budgets, circuit breakers, and degradation. Subagents are synchronous function calls with a timeout and fallback response.

**Graceful degradation**: `run_subagent()` always returns a `SubagentResponse` — on failure it returns `used_fallback=True` and the parent pipeline continues without crashing. This is intentional.

**Tool calling iteration limit**: `run_subagent_with_tools()` caps at 5 iterations to prevent infinite loops. If the limit is reached, the accumulated text is returned as the synthesis.

**Prompt template resolution**: `_get_task_template()` checks `stage_config.task_template` first (can reference a file in `prompts/`), then falls back to `_SUBAGENT_TASK_TEMPLATES` in `subagent.py`. Missing template keys are caught and logged — no crash.

**Security — prompt data escaping**: All prompt_data passed to subagent templates is automatically escaped via `_escape_prompt_data()`. This helper recursively escapes string values using `esc_xml_text()` before `template.format()` is called. This prevents XML structure injection (e.g., `</source_article>` closing tags in malicious content).

**Security — condition evaluation**: `run_subagent_chain()` uses `_evaluate_condition()` to gate conditional step execution. This uses AST-based parsing (NOT `eval()`) with an allowlist of operators (`==`, `!=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `not`, `in`, `not in`). Dunder access (`__class__`, `__init__`, etc.) is blocked. This is safer than `eval()` even with empty `__builtins__`.

**Memory config caching**: `_get_config()` in `trend_memory.py` reads `load_pipeline_config().memory` each call. The pipeline config itself is cached via mtime-based invalidation in `schemas/pipeline.py` — no need to add an additional cache layer.

## Key Files

| File | Purpose |
|------|---------|
| `services/llm/__init__.py` | Provider registry, `get_provider_for_role()`, circuit breaker integration |
| `services/llm/base.py` | `BaseLLMProvider`, `LLMResponse`, `ToolDefinition`, `ToolCall` |
| `services/subagent.py` | `run_subagent()`, tool registry, `initialize_tool_registry()`, prompt templates |
| `services/trend_memory.py` | `propose_trend_memory()`, `get_memory_for_topics()`, `consolidate_all_topics()`, `purge_expired()` |
| `services/context_service.py` | `TopicNote` CRUD (manual notes), `get_related_articles_for_edit()` |
| `models.py` | `TrendMemory` and `TopicNote` SQLAlchemy models |
| `schemas/pipeline.py` | `MemoryConfig`, `SubagentConfig`, `SubagentStageConfig` Pydantic models |
| `pipeline.yaml` | `memory:` section, `subagent:` section with `tools:` lists |
| `tasks/edit.py` | Editor Celery task — injects trend memory into contextualization prompt, calls `propose_trend_memory()` |
| `tasks/cleanup.py` | `consolidate_trend_memory` nightly Celery task |
| `config.py` | `CELERY_BEAT_SCHEDULE` — includes `consolidate-trend-memory` at 3:30 AM |
| `migrations/versions/016_trend_memory.py` | DB migration for `trend_memory` table |

## Extending the Subagent System

**To add a new subagent stage** (e.g., `writer_contextualization`):
1. Add a new `SubagentStageConfig` section in `schemas/pipeline.py` (or use the `chains:` mechanism)
2. Register tool names in `pipeline.yaml: subagent.<stage>.tools`
3. Add a prompt template key in `_SUBAGENT_TASK_TEMPLATES`
4. Call `run_subagent()` with the new `task_type` in the appropriate Celery task

**To add a new tool callable** (for `run_subagent_with_tools`):
1. Define the function in the appropriate `_build_*_tools()` function
2. Create a `ToolDefinition` with JSON Schema `parameters` and the function as `fn`
3. Register via `register_tool()` in `initialize_tool_registry()`
4. Add to `tools:` list in `pipeline.yaml` for stages that need it

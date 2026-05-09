# Subagent Architecture Review Plan

## Verified Claims

### Tool Registry (`registry.py`)
- `_TOOL_REGISTRY` is a dict[str, ToolDefinition] - CORRECT
- `ToolDefinition` imported from `services.llm.base` - CORRECT
- `get_registered_tools()` returns list of all tools - CORRECT
- `initialize_tool_registry()` supports optional filtering via `tool_names` - CORRECT
- Uses `functools.lru_cache` on `_get_all_tools_cached()` - CORRECT

### Tool Implementations (`tools.py`)
- `_context_tool_get_topic_note(topic, source)` - CORRECT
- `_context_tool_get_topic_notes_for_topics(topics)` - CORRECT
- `_context_tool_get_related_articles(topics, exclude_id, limit)` - CORRECT
- `_context_tool_get_trend_memory(topics, min_importance, max_age_days)` - CORRECT
- `_context_tool_get_article_by_id(article_id)` - CORRECT
- `_context_tool_search_articles(query, limit)` - CORRECT
- `_context_tool_get_source_health()` - CORRECT
- `_search_web(query, max_results)` - CORRECT
- `_get_search_provider(provider_id)` - CORRECT

### Runner (`runner.py`)
- `run_subagent(task_type, stage, prompt_data, response_model, article_id)` main entry point - CORRECT
- `run_subagent_with_tools(...)` with tools parameter - CORRECT
- Retry with exponential backoff via `_retry_with_backoff()` - CORRECT
- Task revocation checking via `_is_task_revoked()` - CORRECT
- Self-correction logic for validation failures in `run_subagent_with_tools()` - CORRECT

### Chain System (`chain.py`)
- `run_subagent_chain()` function exists and takes chain_name, steps, initial_prompt_data, article_id - CORRECT
- Conditions use AST-based evaluation via `conditions.py` - CORRECT
- Steps identified by index - CORRECT
- Chain configuration via `SubagentChainConfig` from `schemas/pipeline.py` - CORRECT

### Middleware (`middleware.py`)
- `ToolMiddleware` base class with `wrap()` method - CORRECT
- `LoggingMiddleware` logs tool call start/completion/failure - CORRECT
- `TimingMiddleware` records execution time at DEBUG level - CORRECT
- `ErrorHandlingMiddleware` catches and logs errors - CORRECT
- `apply_middleware()` applies chain in reversed order - CORRECT

### Configuration (`config.py`)
- ThreadPoolExecutor with `SUBAGENT_WORKERS` from env (default 8) - CORRECT
- `_get_subagent_provider_and_config()` function exists - CORRECT

## Discrepancies

### Tool Names in Documentation vs Implementation
| Documented Tool Name | Documented Function | Actual Tool Name | Actual Function |
|---------------------|---------------------|------------------|-----------------|
| `context_notes` | `get_topic_note` | `get_topic_note` | `_context_tool_get_topic_note` |
| `related_articles` | `related_articles` | `related_articles` | `_context_tool_get_related_articles` |
| `trend_memory` | `get_trend_memory` | `get_trend_memory` | `_context_tool_get_trend_memory` |
| `article_lookup` | `get_article_by_id` | `get_article_by_id` | `_context_tool_get_article_by_id` |
| `article_search` | `search_articles` | `search_articles` | `_context_tool_search_articles` |
| `source_health` | `get_source_health` | `get_source_health` | `_context_tool_get_source_health` |
| `web_search` | `web_search` | `web_search` | `_search_web` |

**Issue**: The architecture doc at lines 35-41 claims tool names map to different function names (e.g., `context_notes` -> `get_topic_note`). In reality, the tool names themselves ARE the canonical names (e.g., `get_topic_note` is the tool name for `_context_tool_get_topic_note`). The doc's mapping table is misleading.

### Chain System Documentation
- Document shows YAML config format (lines 144-155) but chain.py actually uses `SubagentChainConfig` from `schemas/pipeline.py` loaded via `load_pipeline_config()`, not raw YAML parsing

### Missing `SubagentChainStep` and `SubagentChainConfig` in Documentation
- The doc shows these as inline Python classes (lines 104-113) but they are actually defined in `schemas/pipeline.py`

### Schema Definitions
- `StageConfig` documented as stub in AGENTS.md (only has `tools` field) but actual `SubagentStageConfig` has many more fields

## Improvement Recommendations

1. [HIGH] **Update architecture doc tool mapping table**: The table at lines 35-41 shows "Tool | Name | Purpose" with a "Name" column that incorrectly implies `get_topic_note` is a separate function name from `context_notes`. Fix to accurately reflect actual tool names.

2. [HIGH] **Document chain configuration source**: The architecture doc shows inline YAML for chain config (lines 144-155) but should clarify that chains are loaded from `pipeline.yaml` via `SubagentChainConfig` in `schemas/pipeline.py`.

3. [MEDIUM] **Document actual tool function naming convention**: Add note that tool functions in `tools.py` use `_context_tool_*` or `_search_*` prefix convention and the canonical tool name is the `name` field in `ToolDefinition`.

4. [MEDIUM] **Add `conditions.py` to architecture overview**: The conditions module (AST-based condition evaluation) is mentioned but not listed in the architecture diagram at lines 7-15.

5. [MEDIUM] **Document `utils.py` contents**: The utils module contains `_retry_with_backoff`, `_is_task_revoked`, `_format_subagent_prompt` which are core utilities but not documented.

6. [LOW] **Update `__init__.py` exports**: The `__init__.py` exports many internal functions (prefixed with `_`) and backward-compat aliases. Consider documenting which are public API vs internal.

7. [LOW] **Add ErrorHandlingMiddleware to runner.py**: `run_subagent_with_tools()` applies middleware chain (line 375-382) but `run_subagent()` does not. This inconsistency should be documented or harmonized.

## Bugs Found

1. **Inconsistent middleware application**: `run_subagent()` (runner.py:113-151) does NOT apply middleware, while `run_subagent_with_tools()` (runner.py:375-382) DOES apply LoggingMiddleware, TimingMiddleware, and ErrorHandlingMiddleware. This is a behavioral inconsistency - tools used via `run_subagent()` won't have logging/timing even if they would via `run_subagent_with_tools()`.

2. **Unused `_finalize_subagent_result` function**: runner.py:277-328 defines `_finalize_subagent_result()` which is never called - the finalization logic is inlined in the main function instead. Dead code.

3. **Schema field mismatch**: `ToolDefinition` in `services/llm/base.py:81-86` has fields `(name, description, parameters, required, fn)` but documentation at arch/subagent.md:24-29 shows `cached: bool = True` field which does NOT exist in actual implementation. The `cached` field is documented but not implemented.

4. **Middleware import inconsistency**: `run_subagent_with_tools()` imports and applies `ErrorHandlingMiddleware` (runner.py:18, 378) but the architecture doc (subagent.md:64-80) describes only `LoggingMiddleware` and `TimingMiddleware` in the middleware section. `ErrorHandlingMiddleware` is missing from docs.

## Layer Violations

1. **Adapter-layer imports in tools.py**: `tools.py` imports from `extensions` and `models` (lines 100-101, 123, 141-142) which are database/infrastructure components. According to clean layering, adapters should NOT import from services, but tools.py is in `services/subagent/` (a service layer component). This is actually correct placement since tools are service-layer utilities that access the database directly - the violation would be if adapters imported from services. No violation here.

2. **No services imports in adapters**: Verified that `adapters/` directory does not import from `services/`. Confirmed clean layering is maintained.

3. **Circular-like import pattern**: `runner.py` line 45 does `from . import resolve_subagent_config, log_pipeline_event` which are re-exported from `services.logging_utils` and `services.metrics`. This creates an indirect dependency path that could cause issues if not carefully managed.

4. **`__init__.py` re-exports from multiple layers**: The `__init__.py` at line 44-46 imports from `services.logging_utils`, `services.metrics`, `services.llm.base`, `services.llm`. Since this is the `services/subagent/` package itself, these are forward references within the services layer, not cross-layer violations.

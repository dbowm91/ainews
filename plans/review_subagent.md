# Review: Subagent System Architecture

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- File structure in `services/subagent/` matches documentation — all files exist: `__init__.py`, `chain.py`, `conditions.py`, `config.py`, `middleware.py`, `prompt_templates.py`, `registry.py`, `runner.py`, `tools.py`, `utils.py`
- Tool registry: `_TOOL_REGISTRY: dict[str, ToolDefinition]` — `services/subagent/registry.py:15`
- `ToolDefinition` in registry matches `services/llm/base.py` — `services/subagent/registry.py:8`
- `run_subagent()` signature: `(task_type, stage, prompt_data, response_model, article_id)` — `services/subagent/runner.py:39-45`
- `run_subagent_with_tools()` signature: `(task_type, stage, prompt_data, response_model, tools, article_id)` — `services/subagent/runner.py:297-304`
- `SubagentChainStep` schema: `task_type`, `prompt_data_template`, `response_model`, `condition` — `schemas/pipeline.py:108-112`
- `SubagentChainConfig` schema: `enabled`, `max_length`, `steps` — `schemas/pipeline.py:115-118`
- Chain uses `provider.chat()` directly, not `chat_with_tools()` — `services/subagent/chain.py:122-128`
- Middleware chain applied in reverse via `apply_middleware()` — `services/subagent/middleware.py:83-91`
- `LoggingMiddleware` logs tool call start/completion/failure — `services/subagent/middleware.py:18-35`
- `TimingMiddleware` measures execution time — `services/subagent/middleware.py:38-61`
- `ErrorHandlingMiddleware` catches exceptions, logs, re-raises — `services/subagent/middleware.py:64-80`
- `ErrorHandlingMiddleware` uses `exc_info=True` for traceback — `services/subagent/middleware.py:76`
- `prompt_templates.py` exists with `SUBAGENT_TASK_TEMPLATES` dict — `services/subagent/prompt_templates.py:7-45`
- `conditions.py` implements AST-based evaluation — `services/subagent/conditions.py:1-157`
- `_evaluate_condition()` parses condition strings safely via AST — `services/subagent/conditions.py:128-157`
- Tool implementations use internal naming (`_context_tool_*`, `_search_*`) registered under public names — `services/subagent/tools.py`
- `registry.py` uses `initialize_tool_registry()` with optional tool filtering — `services/subagent/registry.py:38-69`
- `utils.py` contains `_retry_with_backoff()`, `_is_task_revoked()`, `_format_subagent_prompt()` — `services/subagent/utils.py`
- `config.py` has `_get_subagent_provider_and_config()` and executor setup — `services/subagent/config.py`
- Tool calling iteration happens inside `BaseLLMProvider.chat_with_tools()` — `services/llm/base.py:480-595`
- Middleware is applied per-tool in `run_subagent_with_tools()` — `services/subagent/runner.py:341-355`
- `run_subagent_with_tools()` creates new `ToolDefinition` objects to prevent middleware compounding — `services/subagent/runner.py:349-355`

## Incorrect Claims

- **Tool count: documented as 9, actual is 14**
  - Priority: HIGH
  - Doc at lines 42-52 lists 9 tools. Actual tool count is 14. Missing from doc:
    - `get_topic_gap_report` — `services/subagent/tools.py:453`
    - `get_source_performance` — `services/subagent/tools.py:475`
    - `get_quality_report` — `services/subagent/tools.py:496`
    - `find_dedupe_candidates` — `services/subagent/tools.py:514`
    - `estimate_stage_cost` — `services/subagent/tools.py:540`

- **Documented tool function signatures don't match actual implementations**
  - Priority: HIGH
  - Doc at lines 61-91 shows simplified signatures. Actual implementations differ:
    - `_context_tool_get_related_articles` requires `exclude_id` parameter (doc shows it as optional) — `services/subagent/tools.py:57-58`
    - `_context_tool_get_trend_memory` has `min_importance` and `max_age_days` params not shown in doc — `services/subagent/tools.py:84-85`
    - `_context_tool_get_article_by_id` returns JSON string, not article object — `services/subagent/tools.py:104-124`
    - `_context_tool_search_articles` returns JSON array, not formatted list — `services/subagent/tools.py:127-142`

- **Pipeline.yaml configuration example has wrong tool names**
  - Priority: MEDIUM
  - Doc at lines 256-263 lists tools: `context_notes`, `related_articles`, `trend_memory`, `article_lookup`, `article_search`, `web_search`. The actual registered tool names are: `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost`, `web_search`, `get_search_provider`. `article_lookup` and `article_search` don't exist as tool names.

- **Doc describes `_finalize_subagent_result` as unused**
  - Priority: LOW
  - While the function exists at `services/subagent/runner.py:278-294`, it IS called from `run_subagent_with_tools()` at line 471. However, `run_subagent()` has its own inline finalization at lines 271-275, making the function partially redundant.

## Bugs Found

- **`run_subagent()` has duplicated finalization logic**
  - Priority: MEDIUM
  - `run_subagent()` (lines 271-275) builds `SubagentResponse` inline, while `run_subagent_with_tools()` (line 471) calls `_finalize_subagent_result()`. The two functions handle result construction differently, which could lead to inconsistencies. `run_subagent()` should also use `_finalize_subagent_result()`.

- **`_retry_with_backoff` in subagent lacks jitter**
  - Priority: LOW
  - `services/subagent/utils.py:9-16` uses `min(base_delay * 2**attempt, max_delay)` without jitter. The LLM provider's `_retry_with_backoff` (`services/llm/base.py:179-182`) adds `random.uniform(0, 0.5)` jitter. The subagent version may cause thundering herd on concurrent retries.

- **Middleware `exc_info=True` may leak sensitive data**
  - Priority: LOW
  - `services/subagent/middleware.py:76` logs full tracebacks with `exc_info=True`. Tool functions may process sensitive data (API keys, user content). Tracebacks could appear in logs.

- **`conditions.py` allows attribute access on context objects**
  - Priority: LOW
  - `services/subagent/conditions.py:55-70` resolves attributes via `getattr()` on context objects. While protected attributes (`__`, `_` prefix) are blocked at line 62, this could still expose internal object state if context objects have sensitive attributes.

- **Chain step exception handling catches `TimeoutError` twice**
  - Priority: LOW
  - `services/subagent/chain.py:142` and `154` both catch `TimeoutError` and `ProviderTimeoutError`. The second `except` clause at line 154 includes `TimeoutError` again, which is redundant (already caught at line 142).

## Improvement Opportunities

- **Document `ToolSelector` and `StageAwareToolSelector`**
  - Priority: MEDIUM
  - `services/tool_selection.py` exists and is used in `runner.py:106-112` for stage-aware tool selection. Not documented.

- **Document `_is_task_revoked()` utility**
  - Priority: LOW
  - `services/subagent/utils.py:19-27` checks Celery task revocation. Important for understanding cancellation behavior.

- **Document `_format_subagent_prompt()` utility**
  - Priority: LOW
  - `services/subagent/utils.py:30-41` handles template formatting with error handling. Used by `run_subagent_with_tools()`.

- **Document `config.py` executor setup**
  - Priority: LOW
  - `services/subagent/config.py` sets up `ThreadPoolExecutor` with configurable `SUBAGENT_WORKERS` (default 8) and registers `atexit` shutdown. Not documented.

- **Document tool caching in `registry.py`**
  - Priority: LOW
  - `services/subagent/registry.py:29-35` uses `@functools.lru_cache(maxsize=1)` to cache built tool definitions. Performance optimization not documented.

- **Document middleware chain order semantics**
  - Priority: MEDIUM
  - The doc says chain is applied in reverse but doesn't explain what "outer to inner" means in practice. With `[Logging, Timing, ErrorHandling]` applied in reverse, the actual call order is `ErrorHandling -> Timing -> Logging -> tool`. This should be explicit.

- **Document `SubagentStageConfig` schema**
  - Priority: MEDIUM
  - `schemas/pipeline.py:93-105` defines `SubagentStageConfig` with fields: `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `timeout_seconds`, `system_prompt`, `max_retries`, `retry_delay`, `task_template`, `tools`, `max_iterations`. Not documented in the subagent doc.

## Stale Content

- **Tool names in pipeline.yaml config example**
  - Priority: HIGH
  - The example at lines 256-263 references `article_lookup` and `article_search` which are not registered tool names. Should be updated to `get_article_by_id` and `search_articles`.

- **Tool function signatures in code examples**
  - Priority: MEDIUM
  - The function signatures at lines 61-91 don't match actual implementations. Should be updated to reflect current parameter lists.

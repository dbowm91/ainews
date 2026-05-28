# LLM, Search & Subagent Architecture Documentation Review

Review date: 2026-05-28

## Verified Claims

### LLM Providers (`architecture/llm-providers.md`)

| Claim | Status | Evidence |
|-------|--------|----------|
| `BaseLLMProvider` abstract methods (`_create_client`, `chat`, `chat_streaming`) exist | **Verified** | `services/llm/base.py:195-224` |
| `chat_structured()` signature matches | **Verified** | `services/llm/base.py:226-236` |
| `chat_with_tools()` signature matches | **Verified** | `services/llm/base.py:450-459` |
| `ToolDefinition` has no `cached` field | **Verified** | `services/llm/base.py:81-86` |
| `LLMResponse` dataclass fields | **Verified** | `services/llm/base.py:73-77` |
| `ToolCall` dataclass fields | **Verified** | `services/llm/base.py:89-92` |
| `ToolCallingResponse` dataclass fields | **Verified** | `services/llm/base.py:103-108` |
| `OpenAIProvider` exists and extends `BaseLLMProvider` | **Verified** | `services/llm/openai.py:53` |
| `AnthropicProvider` exists and extends `BaseLLMProvider` | **Verified** | `services/llm/anthropic.py:51` |
| `GeminiProvider` exists and extends `BaseLLMProvider` | **Verified** | `services/llm/gemini.py:35` |
| `OllamaProvider` exists and extends `BaseLLMProvider` | **Verified** | `services/llm/ollama.py:41` |
| `get_provider_for_role()` exists | **Verified** | `services/llm/__init__.py:45` |
| `get_provider_chain()` exists | **Verified** | `services/llm/__init__.py:57` |
| `CircuitOpenError` defined | **Verified** | `services/circuit_breaker.py:451` |
| `AuthError`, `RateLimitError`, `ProviderServerError`, `ProviderTimeoutError` defined | **Verified** | `services/llm/errors.py:38-61` |
| `CircuitOpenError` in `services/llm/errors.py` | **Incorrect** | `CircuitOpenError` is in `services/circuit_breaker.py:451`, not `errors.py` (doc references it as if in `errors.py` table) |
| `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` exists | **Verified** | `constants.py:17` |
| Circuit breaker state diagram (Closed→Open→Half-Open) | **Verified** | `services/circuit_breaker.py:25-28` (states match) |
| `_retry_with_backoff()` retries on `RateLimitError`, `ProviderTimeoutError`, `ProviderServerError` | **Verified** | `services/llm/base.py:163` |
| Does NOT retry `AuthError`, `CircuitOpenError` | **Verified** | `services/llm/base.py:161` |
| `_extract_json()` handles markdown-wrapped JSON | **Verified** | `services/llm/base.py:31-62` |
| `record_provider_success()` accepts `stage` parameter | **Verified** | `services/llm/__init__.py:100` |
| Cost tracker `record_usage()` / `get_usage_summary()` functions | **Incorrect** | Actual functions are `get_cost_summary()` and `_load_rates()` (see below) |
| `services/cost_tracker.py` exists | **Verified** | `services/cost_tracker.py` exists |
| All referenced files in key files table exist | **Verified** | All paths checked |

### Search Providers (`architecture/search-providers.md`)

| Claim | Status | Evidence |
|-------|--------|----------|
| `SearchResult` dataclass fields (title, url, snippet, source, score) | **Incorrect** | `services/search/base.py:10-15`: `SearchResult` has `title`, `url`, `snippet`, `source` — no `score` field |
| `DuckDuckGoProvider` exists | **Verified** | `services/search/duckduckgo.py:46` |
| `GoogleSearchProvider` exists | **Verified** | `services/search/google.py:59` |
| `SearxNGProvider` (actually `SearXNGSearchProvider`) | **Incorrect** | Class name is `SearXNGSearchProvider`, not `SearxNGProvider` |
| `HybridSearchProvider` exists | **Verified** | `services/search/hybrid.py:78` |
| `SQLiteFTSProvider` exists | **Verified** | `services/search/sqlite_fts.py:53` |
| `get_search_provider()` exists | **Verified** | `services/search/__init__.py:34` |
| `search_web()` exists | **Verified** | `services/search/__init__.py:44` |
| `get_article_search_provider()` exists | **Verified** | `services/search/__init__.py:56` |
| DuckDuckGo timeout is 20 seconds | **Verified** | `services/search/duckduckgo.py:52` (via `future.result(timeout=20)`) |
| DuckDuckGo default/enabled | **Verified** | Provider registered via `@register_search_provider("duckduckgo")` |
| Hybrid FTS5 + vector enabled | **Verified** | `services/search/hybrid.py:78` registered as db_search_provider |
| Google disabled, requires API key | **Verified** | `services/search/google.py:69-71` returns empty when unconfigured |
| SearxNG disabled | **Verified** | Requires `host` config, defaults to localhost |
| `_context_tool_search_web` function name | **Incorrect** | Actual function is `_search_web` (not `_context_tool_search_web`) |
| `get_article_search_provider()` return type is `SearchProvider` | **Verified** | `services/search/__init__.py:56` |

### Subagent System (`architecture/subagent.md`)

| Claim | Status | Evidence |
|-------|--------|----------|
| All files in architecture tree exist | **Verified** | `__init__.py`, `chain.py`, `conditions.py`, `config.py`, `middleware.py`, `prompt_templates.py`, `registry.py`, `runner.py`, `tools.py`, `utils.py` all exist |
| `_TOOL_REGISTRY` dict exists | **Verified** | `services/subagent/registry.py:15` |
| 9 built-in tools documented | **Incorrect** | Actual count is 9 tool definitions in `_build_context_tools()` (7) + `_build_search_tools()` (2) = 9, but naming of some differs (see below) |
| `get_topic_note` tool | **Verified** | `services/subagent/tools.py:199` |
| `context_notes` tool | **Verified** | `services/subagent/tools.py:218` |
| `related_articles` tool | **Verified** | `services/subagent/tools.py:237` |
| `get_trend_memory` tool | **Verified** | `services/subagent/tools.py:264` |
| `get_article_by_id` tool | **Verified** | `services/subagent/tools.py:291` |
| `search_articles` tool | **Verified** | `services/subagent/tools.py:309` |
| `get_source_health` tool | **Verified** | `services/subagent/tools.py:328` |
| `web_search` tool | **Verified** | `services/subagent/tools.py:347` |
| `get_search_provider` tool | **Verified** | `services/subagent/tools.py:366` |
| `run_subagent()` signature matches | **Verified** | `services/subagent/runner.py:39-44` |
| `run_subagent_with_tools()` signature matches | **Verified** | `services/subagent/runner.py:297-304` |
| `SubagentChainStep` and `SubagentChainConfig` in `schemas/pipeline.py` | **Verified** | `schemas/pipeline.py:108-118` |
| Middleware chain order (Logging→Timing→ErrorHandling) | **Verified** | `services/subagent/runner.py:341-345` |
| `apply_middleware()` applies in reverse | **Verified** | `services/subagent/middleware.py:89` |
| Chain uses `provider.chat()` not `chat_with_tools()` | **Verified** | `services/subagent/chain.py:122` |
| `prompt_templates.py` exists | **Verified** | `services/subagent/prompt_templates.py` exists |
| `conditions.py` AST-based evaluation | **Verified** | `services/subagent/conditions.py:128` uses `ast.parse` |
| Tool iteration inside `BaseLLMProvider.chat_with_tools()` | **Verified** | `services/llm/base.py:475` while loop |
| Tool results re-injected into `all_messages` | **Verified** | `services/llm/base.py:537-558` |

## Incorrect Claims

### HIGH Priority

1. **`SearchResult` dataclass missing `score` field** — `architecture/search-providers.md:135-141` documents `score: float = 0.0` but `services/search/base.py:10-15` does NOT have a `score` field. The actual class is:
   ```python
   @dataclass
   class SearchResult:
       title: str
       url: str
       snippet: str
       source: str = ""
   ```

2. **`cost_tracker.py` function names wrong** — `architecture/llm-providers.md:285-289` documents `record_usage()` and `get_usage_summary()`. Actual functions are `get_cost_summary()` and `_load_rates()`. There is no `record_usage()` function. The `get_cost_summary()` reads from metrics counters, not from a `record_usage()` call.

3. **`_context_tool_search_web` function name wrong** — Both `architecture/search-providers.md:170` and `architecture/subagent.md:86` reference `_context_tool_search_web()`. The actual function is `_search_web()` (defined at `services/subagent/tools.py:165`).

4. **`SearxNGProvider` class name wrong** — `architecture/search-providers.md:100` documents `SearxNGProvider`. Actual class is `SearXNGSearchProvider` (at `services/search/searxng.py:59`).

### MEDIUM Priority

5. **`get_provider_chain()` return type wrong** — `architecture/llm-providers.md:166-168` documents it as returning `list[str]`. Actual return is a **generator** yielding `(provider, model, max_tokens, provider_id)` tuples (`services/llm/__init__.py:57-97`).

6. **`get_provider_for_role()` return type wrong** — `architecture/llm-providers.md:162-164` documents it as returning `BaseLLMProvider`. Actual return is `Tuple[BaseLLMProvider, str, int, str]` (provider, model, max_tokens, provider_id) at `services/llm/__init__.py:45`.

7. **`CircuitOpenError` location in error table** — `architecture/llm-providers.md:233-241` lists `CircuitOpenError` alongside errors defined in `services/llm/errors.py`, but `CircuitOpenError` is actually defined in `services/circuit_breaker.py:451`. It's imported into `services/llm/__init__.py` from there. The table heading says "services/llm/errors.py defines provider error types" which is misleading for `CircuitOpenError`.

8. **`ErrorHandlingMiddleware` behavior wrong** — `architecture/subagent.md:234-242` documents `ErrorHandlingMiddleware` as returning `{"error": str(e), "tool": func.__name__}` (catching and returning error dict). Actual implementation at `services/subagent/middleware.py:64-80` **re-raises** the exception after logging it. The documented behavior matches what would be a different (catching) middleware, not the current implementation.

9. **`HybridSearchProvider` architecture description** — `architecture/search-providers.md:62-68` says `HybridSearchProvider` is a `BaseSearchProvider`. It's actually a `SearchProvider` (different base class for database-backed search). The `BaseSearchProvider` is for external web search providers.

10. **`get_article_search_provider()` return type** — `architecture/search-providers.md:30` says returns `BaseSearchProvider`. Actual return type is `SearchProvider` (at `services/search/__init__.py:56`).

### LOW Priority

11. **`_TOOL_REGISTRY` is populated lazily** — `architecture/subagent.md:15` says `_TOOL_REGISTRY` is where tools are "registered". In reality, `_TOOL_REGISTRY` starts empty and is populated on first call to `initialize_tool_registry()` via `_get_all_tools_cached()` (using `@lru_cache`). The `register_tool()` function just puts things in the dict but isn't used for initial registration.

12. **Tool naming convention note** — `architecture/subagent.md:58` correctly notes the `_context_tool_` prefix convention, but the search tools (`web_search`, `get_search_provider`) use `_search_web` and `_get_search_provider` — the naming isn't fully consistent. The doc's table at line 52 lists `get_search_provider` as a tool name but the function is `_get_search_provider`.

## Bugs Found

### HIGH Priority

1. **`ErrorHandlingMiddleware` doesn't match documented behavior** — The architecture doc says it "returns error-formatted result instead of raising" (`architecture/subagent.md:235`). The actual implementation re-raises exceptions (`services/subagent/middleware.py:78`). This means tool execution errors will propagate up instead of being caught and formatted. This could be intentional (documented behavior is stale) or a missing feature. If the documented behavior is intended, the middleware needs to catch and return error dicts.

### MEDIUM Priority

2. **`_retry_with_backoff` default parameter mismatch** — `architecture/llm-providers.md:216` documents `max_retries=3, base_delay=1.0, max_delay=30.0` as parameter defaults. The actual signature at `services/llm/base.py:131-137` is `_retry_with_backoff(self, func, model, *args, **kwargs)` — it takes positional `model` arg and `*args/**kwargs`, not named `max_retries`/`base_delay`/`max_delay`. The actual defaults are `RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY=1.0`, `RETRY_MAX_DELAY=30.0` as class attributes. The doc implies these are function parameters when they're class constants.

## Improvement Opportunities

### MEDIUM Priority

1. **Document `ToolResult` and `BatchError` dataclasses** — `services/llm/base.py` defines `ToolResult` (lines 96-100) and `BatchError` (lines 65-70) which are not documented in the architecture docs.

2. **Document `chat_structured_batch()` method** — `services/llm/base.py:313-387` implements batch structured chat with ThreadPoolExecutor. Not mentioned in architecture docs.

3. **Document `_chat_with_schema()` abstract method** — All providers implement this abstract method (`services/llm/base.py:389-401`) for provider-specific schema-guided chat. Not mentioned in the docs.

4. **Document `_call_api_with_tools()` and `_extract_text_and_tool_calls()` and `_format_tool_result()` abstract methods** — These are the provider hooks used by `chat_with_tools()`. Not documented.

5. **Document `ToolMiddleware` base class** — The middleware base class and its `wrap()` pattern (`services/subagent/middleware.py:10-15`) is mentioned but the base class docstring details aren't shown.

6. **Document `_format_subagent_prompt()` utility** — `services/subagent/utils.py:30-41` handles prompt formatting with error handling. Not documented.

7. **Document `_is_task_revoked()` utility** — `services/subagent/utils.py:19-27` checks Celery task revocation. Not documented.

8. **Document `SubagentStageConfig` schema** — `schemas/pipeline.py:93-105` defines all configurable fields including `max_iterations`, `tools`, `task_template`, etc. The doc only references this schema indirectly.

9. **Document `_resolve_template_variables()` function** — `services/subagent/chain.py:19-33` resolves template variables including references to previous step results. Not documented.

10. **Document `initialize_tool_registry()` function** — `services/subagent/registry.py:38-69` handles tool initialization with optional filtering by name or ToolSelector. Not documented.

### LOW Priority

11. **Document `services/llm/types.py` duplicate definitions** — `services/llm/types.py` duplicates `LLMResponse`, `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolCallingResponse`, and `BatchError` from `services/llm/base.py`. This is a maintenance concern.

12. **Document `services/llm/json_utils.py`** — This file has an `extract_json()` function that's essentially a duplicate of `_extract_json()` in `services/llm/base.py`. The doc mentions `_extract_json()` but not this standalone module.

13. **Document `config.py` executor shutdown** — `services/subagent/config.py:14-21` registers an `atexit` handler to shutdown the executor. Not documented.

## Stale Content

### HIGH Priority

1. **`_context_tool_search_web` in architecture docs** — Both `architecture/search-providers.md:170` and `architecture/subagent.md:86` reference `_context_tool_search_web()` which doesn't exist. Should be `_search_web()`.

2. **`ErrorHandlingMiddleware` catch behavior** — `architecture/subagent.md:234-242` documents behavior (returning error dict) that doesn't match implementation (re-raises). Either the doc is stale or the implementation needs updating.

### MEDIUM Priority

3. **`cost_tracker.py` API names** — `architecture/llm-providers.md:285-289` documents `record_usage()` and `get_usage_summary()` which don't exist. Should reference `get_cost_summary()`.

4. **`SearchResult.score` field** — `architecture/search-providers.md:141` documents `score: float = 0.0` which doesn't exist on the actual dataclass.

5. **`get_provider_for_role()` docstring says "returns BaseLLMProvider"** — The doc implies a single return value but actual return is a 4-tuple.

6. **`get_provider_chain()` docstring says "returns list[str]"** — Actual return is a generator of tuples.

7. **"Services/llm/errors.py defines provider error types"** — The table includes `CircuitOpenError` which is defined in `services/circuit_breaker.py`.

### LOW Priority

8. **`HybridSearchProvider` described as `BaseSearchProvider`** — Actually extends `SearchProvider` (different base class).

9. **SearxNG config field** — `architecture/search-providers.md:111` says `SEARXNG_BASE_URL` env var. Actual config uses `host` field in YAML (`services/search/searxng.py:62`), not an env var.

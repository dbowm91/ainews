# Services Agent Context

## Architectural Rules
- Services must be decoupled from Adapters.
- Use `schemas/` for data structures shared across services.
- Business logic should reside in services, not in models or routes.
- **IMPORTANT:** Do NOT import from `adapters/` in services. If shared types are needed, use `schemas/` or `models/`. Exception: `TYPE_CHECKING` blocks are acceptable for type hints only.

## LLM Interaction
- All LLM calls should go through the providers defined in `services/llm/`.
- Use `CircuitBreaker` for all external API calls.
- Implement token budgeting for subagent loops to prevent context overflow.

## Specific Service Notes
- **Limiter:** Uses Redis pub/sub for waiting. Do not use `time.sleep()`. Ensure `pubsub` objects are reused or properly closed to avoid Redis connection bloat.
- **Logging:** `services/logging_utils.py` contains implicit `Optional` parameters that trigger Mypy errors. Use `Optional[Type] = None` explicitly.
- **Audit:** Harden against database connection issues; logging an action should not crash the request.
- **Prompts:** Use `@lru_cache` for prompt file loading and truncation summaries.

## Provider Notes
- **SubagentStageConfig vs StageConfig:** The actual stage configuration class is `SubagentStageConfig` in `schemas/pipeline.py`, NOT `StageConfig` which is an empty stub with only `tools` field.
- **DeepSeek Provider:** Not implemented. References in `cost_tracker.py` and documentation have been removed.

## Subagent Notes
- **Tool Execution:** `run_subagent_with_tools()` in `services/subagent/runner.py` makes a single `chat_with_tools()` call. Tool results are NOT re-injected into messages for subsequent LLM calls. The architecture doc suggesting multi-step message injection is outdated.
- **ToolDefinition:** Actual class in `services/llm/base.py` is a `@dataclass` with fields: `name`, `description`, `parameters`, `required`, `fn`. It does NOT have a `cached` field.
- **Tool Registry:** Thread-safe via `_TOOL_REGISTRY_LOCK`. `_subagent_executor` shutdown via `atexit.register(shutdown_executor)`.
- **_finalize_subagent_result():** Defined at line 277 in `services/subagent/runner.py`. **NOTE:** This function has a recursive bug - it calls itself at line 288 with the same parameters. `run_subagent()` manually constructs the response instead of calling this function. `run_subagent_with_tools()` at line 467 calls this function but would hit infinite recursion.

## Utils Notes
- **utils/text.py:** Contains `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`, `truncate`, `sanitize_html`, `extract_hashtags`. **NOTE:** `sanitize_html()` only strips dangerous **tags** via `_TagStripper` but does NOT filter **attributes** - XSS vectors like `<img onerror=alert(1)>` pass through. The `_DANGEROUS_TAGS` constant is used for tag stripping, but there is no attribute filtering implemented.
- **utils/datetime.py:** Contains `parse_date`, `format_date`, `time_ago` (alias for format_date).
- **utils/security.py:** Contains `generate_token` (using `secrets.token_urlsafe`), `constant_time_compare` (using `hmac.compare_digest`).
- **utils/hash.py:** Contains `generate_hash`, `verify_hash`.
- **utils/html.py:** Contains `strip_tags`, `linkify`, `extract_text`. Note: `strip_tags` fallback uses bare `except Exception` with noqa: BLE001. Also `extract_text` logs a warning when trafilatura is not available.
- **utils/url.py:** Contains global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). Do not assume pure function behavior. Docstring now clarifies this after architecture review.

## Layer Violation Note
- **schemas/common.py:** This module imports from `services.config_cache`, violating the principle that schemas should have minimal dependencies. This is a known architectural issue requiring decision - either move config caching to utils or accept the violation.

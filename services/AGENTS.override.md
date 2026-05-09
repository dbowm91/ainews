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

## Utils Notes
- **utils/text.py:** Contains `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`, `truncate`, `sanitize_html`, `extract_hashtags` - these functions all exist.
- **utils/datetime.py:** Contains `parse_date`, `format_date`, `time_ago` (alias for format_date).
- **utils/security.py:** Contains `generate_token` (using `secrets.token_urlsafe`), `constant_time_compare` (using `hmac.compare_digest`).
- **utils/hash.py:** Contains `generate_hash`, `verify_hash`.
- **utils/html.py:** Contains `strip_tags`, `linkify`, `extract_text`.
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
- **DeepSeek Provider Missing:** `services/llm/deepseek.py` does not exist but is referenced in `cost_tracker.py` and architecture docs. Either implement it or remove references.
- **SubagentStageConfig vs StageConfig:** The actual stage configuration class is `SubagentStageConfig` in `schemas/pipeline.py`, NOT `StageConfig` which is an empty stub with only `tools` field.

## Utils Notes
- **Date Utils:** `services/date_utils.py` contains pure date formatting functions that should be moved to `utils/datetime.py` per architecture (planned).
- **Security Utils:** No `utils/security.py` exists. Token generation is inline using `secrets.token_urlsafe(32)`. Consider creating utils/security.py for consistency.
- **Text Utils:** `utils/text.py` contains XML escaping functions (`esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`) not the documented `truncate`/`sanitize_html`/`extract_hashtags`. This is intentional - XML escaping is the actual purpose of that module.
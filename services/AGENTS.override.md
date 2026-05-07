# Services Agent Context

## Architectural Rules
- Services must be decoupled from Adapters.
- Use `schemas/` for data structures shared across services.
- Business logic should reside in services, not in models or routes.
- **IMPORTANT:** Do NOT import from `adapters/` in services. If shared types are needed, use `schemas/` or `models/`.

## LLM Interaction
- All LLM calls should go through the providers defined in `services/llm/`.
- Use `CircuitBreaker` for all external API calls.
- Implement token budgeting for subagent loops to prevent context overflow.

## Specific Service Notes
- **Limiter:** Uses Redis pub/sub for waiting. Do not use `time.sleep()`. Ensure `pubsub` objects are reused or properly closed to avoid Redis connection bloat.
- **Logging:** `services/logging_utils.py` contains implicit `Optional` parameters that trigger Mypy errors. Use `Optional[Type] = None` explicitly.
- **Audit:** Harden against database connection issues; logging an action should not crash the request.
- **Prompts:** Use `@lru_cache` for prompt file loading and truncation summaries.
- **Crawling Service:** `services/crawling.py` imports `RawItem` from `adapters.base` - this is a layering violation that should be fixed by moving `RawItem` to `schemas/item.py`.
- **DeepSeek Provider:** `services/llm/deepseek.py` does not exist but is referenced in `cost_tracker.py` and architecture docs. Either implement it or remove references.
- **Date Utils:** `services/date_utils.py` contains pure date formatting functions that should be in `utils/datetime.py` per architecture.

## LLM Provider Notes
- **DeepSeek Provider Missing:** `services/llm/deepseek.py` does not exist but is referenced in `cost_tracker.py` and architecture docs. Either implement it or remove references.
- **SubagentStageConfig vs StageConfig:** The actual stage configuration class is `SubagentStageConfig` in `schemas/pipeline.py`, NOT `StageConfig` which is an empty stub with only `tools` field.

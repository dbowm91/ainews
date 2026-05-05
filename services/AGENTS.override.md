# Services Agent Context

## Architectural Rules
- Services must be decoupled from Adapters.
- Use `schemas/` for data structures shared across services.
- Business logic should reside in services, not in models or routes.

## LLM Interaction
- All LLM calls should go through the providers defined in `services/llm/`.
- Use `CircuitBreaker` for all external API calls.
- Implement token budgeting for subagent loops to prevent context overflow.

## Specific Service Notes
- **Limiter:** Uses Redis pub/sub for waiting. Do not use `time.sleep()`.
- **Audit:** Harden against database connection issues; logging an action should not crash the request.
- **Prompts:** Use `@lru_cache` for prompt file loading and truncation summaries.

# LLM Provider Conventions

Contextual conventions for agents working in the `services/llm/` directory.

## LLM Stage Metrics

`record_provider_success(provider_id, model, tokens_used, stage="")` in `services/llm/__init__.py` includes `stage` label (select, research, write, edit) in metrics. All pipeline tasks pass `stage=` parameter.

## LLM Structured Output

`BaseLLMProvider.chat_structured()` in `base.py` uses `extract_json()` helper from `json_utils.py` to handle markdown-wrapped JSON from Ollama, includes schema in retry messages, defaults to 2 validation retries.

## Streaming Support

`chat_streaming()` method in `BaseLLMProvider` with implementations in OpenAI, Anthropic, Ollama, Gemini adapters.

## Architecture Review Findings (From Wave 9 Review)

### services/llm/types.py Does Not Exist
Both `architecture/llm-providers.md:17` and `architecture/services.md:17` list `services/llm/types.py` but this file doesn't exist. The types `ToolCall`, `ToolResult`, `ToolCallingResponse` exist as:
- Dataclasses in `services/llm/base.py:56-79` (for internal use)
- Pydantic models in `schemas/llm_responses.py:186-202` (for pipeline responses)

### Subagent Self-Correction Documentation Wrong
`architecture/subagent.md:151-167` references non-existent code at lines 401-417. Actual self-correction is in `services/subagent/runner.py:88-109` using `corrected` flag (not `self_corrected`). The retry loop is in `_retry_with_backoff`, not an explicit `for attempt in range`.

### Middleware Chain Applied in Reverse
`services/subagent/runner.py:83-90` applies middleware in reverse order via `reversed(middleware_chain)`. The first middleware in the list ends up as the outermost wrapper after the reversal.
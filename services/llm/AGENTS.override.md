# LLM Provider Conventions

Contextual conventions for agents working in the `services/llm/` directory.

## LLM Stage Metrics

`record_provider_success(provider_id, model, tokens_used, stage="")` in `services/llm/__init__.py` includes `stage` label (select, research, write, edit) in metrics. All pipeline tasks pass `stage=` parameter.

## LLM Structured Output

`BaseLLMProvider.chat_structured()` in `base.py` uses `extract_json()` helper from `json_utils.py` to handle markdown-wrapped JSON from Ollama, includes schema in retry messages, defaults to 2 validation retries.

## Streaming Support

`chat_streaming()` method in `BaseLLMProvider` with implementations in OpenAI, Anthropic, Ollama, Gemini adapters.
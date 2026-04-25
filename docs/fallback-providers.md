# Fallback LLM Provider Configuration

This guide covers enabling fallback providers, configuring fallback chains per pipeline stage, and testing circuit breaker failover.

## Overview

The application supports multiple LLM providers defined in `providers.yaml`. By default, only the primary provider is enabled. Fallback providers allow the pipeline to continue when the primary provider is unavailable.

## Provider Configuration

### providers.yaml Structure

Each provider in `providers.yaml` has the following structure:

```yaml
providers:
  - id: ollama-local
    name: Ollama (Local)
    type: ollama
    enabled: true
    config:
      host: "http://localhost:11434"
      model: "qwen3:8b"
      max_tokens: 4096

  - id: openai-backup
    name: OpenAI (Backup)
    type: openai
    enabled: false
    config:
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"
      model: "gpt-4o-mini"
      max_tokens: 4096
```

### Enabling a Fallback Provider

1. Set `enabled: true` for the provider in `providers.yaml`
2. Ensure required environment variables are set (e.g., `OPENAI_API_KEY`)
3. Assign the provider to one or more `roles` if using multi-provider fallback
4. Reload config via `POST /admin/api/config/reload` or restart workers

## Supported Provider Types

| Type | Adapter | Providers |
|------|---------|-----------|
| `ollama` | `services/llm/ollama.py` | Ollama (local models) |
| `openai` | `services/llm/openai.py` | OpenAI, DeepSeek, MiniMax, Groq, TogetherAI, Fireworks, Cerebras, xAI, Zai, OpenRouter, OpenCode |
| `anthropic` | `services/llm/anthropic.py` | Anthropic Claude |
| `gemini` | `services/llm/gemini.py` | Google Gemini |

All `openai`-type providers use the OpenAI-compatible adapter and work with any API that follows the OpenAI chat completions format.

## Provider List

### Local Providers

| ID | Model | Cost | Notes |
|----|------|------|-------|
| `ollama-local` | `qwen3:8b` | Free | Local Ollama instance |

### OpenAI-Compatible Providers

| ID | Base URL | Models | Cost |
|----|---------|--------|-------|
| `openai` | api.openai.com | gpt-4o, gpt-4o-mini, gpt-4-turbo | $2.50/$10.00 per 1M tokens |
| `deepseek` | api.deepseek.com | deepseek-chat | $0.27/$1.10 per 1M tokens |
| `minimax` | api.minimax.io | MiniMax-M2.5 | $0.20/$1.10 per 1M tokens |
| `gemini` | Google API | gemini-2.0-flash | $0.10/$0.40 per 1M tokens |
| `groq` | api.groq.com | llama-3.3-70b-versatile | $0.59/$0.79 per 1M tokens |
| `openrouter` | openrouter.ai | claude-3.5-sonnet | $3.00/$15.00 per 1M tokens |
| `xai` | api.x.ai | grok-2-1212 | $2.00/$10.00 per 1M tokens |
| `togetherai` | api.togetherai.com | llama-3-70b-chat-hf | $0.80/$0.80 per 1M tokens |
| `fireworks` | api.fireworks.ai | llama-v3-70b-instruct | $0.80/$0.80 per 1M tokens |
| `cerebras` | api.cerebras.ai | llama-3.3-70b | $0.85/$1.20 per 1M tokens |
| `zai` | open.bigmodel.cn | glm-4 | $1.40/$1.40 per 1M tokens |
| `opencode` | api.opencode.ai | opencode | varies |

### Anthropic Provider

| ID | Models | Cost |
|----|--------|-------|
| `anthropic` | claude-sonnet-4-5-20250929 | Pricing from anthropic.com |

## Circuit Breaker

### Configuration

The circuit breaker is configured per provider:

```yaml
  - id: openai-backup
    type: openai
    enabled: true
    circuit_breaker:
      failure_threshold: 5      # failures before opening
      recovery_timeout: 60        # seconds before attempting recovery
      half_open_max_calls: 1    # test calls in half-open state
```

### States

- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Provider is considered unhealthy, requests are rejected immediately
- **HALF_OPEN**: Testing if provider has recovered, limited test calls allowed

### Metrics

Circuit breaker state changes are emitted as:
- `circuit_breaker.state_change` counter with `provider`, `from`, `to` labels
- `circuit_breaker.opened` counter on OPEN transitions

## Testing Circuit Breaker Failover

### Manual Testing

1. Start the application with multiple providers enabled
2. Make the primary provider unavailable (e.g., stop Ollama)
3. Trigger a pipeline run
4. Check logs for circuit breaker state changes

### Verifying Failover in Production

1. Check circuit breaker metrics at the admin stats endpoint
2. Monitor `circuit_breaker.state_change` counter
3. Set up alerts for OPEN transitions

## Troubleshooting

### All Providers Unavailable

If all providers for a role are unavailable, the pipeline degrades:
- Research stage: Uses source text only, sets impact_score to 30
- Write stage: Generates minimal draft from extracted text
- Edit stage: Routes article to REVIEW status

Check degradation metrics via `pipeline.degradation` counter.

### Provider Health Checks

```python
from services.llm import get_provider_for_role

provider, model, max_tokens, provider_id = get_provider_for_role("researcher")
health = provider.health_check()
```

### Reloading Configuration

```bash
curl -X POST http://localhost:5000/admin/api/config/reload \
  -H "X-CSRFToken: ..."
```

This clears the provider cache and reinitializes all providers.
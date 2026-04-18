# Fallback LLM Provider Configuration

This guide covers enabling fallback providers, configuring fallback chains per pipeline stage, and testing circuit breaker failover.

## Overview

The application supports multiple LLM providers defined in `providers.yaml`. By default, only the primary provider is enabled. Fallback providers allow the pipeline to continue operating when the primary provider is unavailable.

## Provider Configuration

### providers.yaml Structure

Each provider in `providers.yaml` has the following structure:

```yaml
providers:
  - id: ollama-local
    name: Ollama (Local)
    type: ollama
    enabled: true
    models:
      - name: qwen3:8b
        max_tokens: 4096
    roles:
      - researcher
      - writer
      - editor

  - id: openai-backup
    name: OpenAI (Backup)
    type: openai
    enabled: false
    api_key_env: OPENAI_API_KEY
    models:
      - name: gpt-4o-mini
        max_tokens: 4096
    roles:
      - researcher
      - writer
      - editor
```

### Enabling a Fallback Provider

1. Set `enabled: true` for the provider in `providers.yaml`
2. Ensure required environment variables are set (e.g., `OPENAI_API_KEY`)
3. Assign the provider to one or more `roles` (researcher, writer, editor)
4. Reload config via `POST /admin/api/config/reload` or restart workers

## Fallback Chains Per Stage

The circuit breaker in `services/llm/base.py` automatically falls back to the next available provider for a given role when the primary provider fails.

### How Fallback Selection Works

1. `get_provider_for_role(stage)` returns the first enabled provider for the stage's role
2. If that provider's circuit breaker is OPEN, the next enabled provider is tried
3. If all providers for a role are unavailable, the stage degrades per `services/pipeline_degradation.py`

### Configuring Stage-Specific Fallbacks

To create a fallback chain for a specific stage:

```yaml
# providers.yaml - multiple providers for the same role
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    roles: [researcher]

  - id: openai-backup
    type: openai
    enabled: true
    roles: [researcher]

  - id: anthropic-backup
    type: anthropic
    enabled: true
    roles: [researcher]
```

Priority is determined by order in `providers.yaml` — earlier entries are tried first.

## Circuit Breaker

### Configuration

The circuit breaker is configured per provider in `providers.yaml`:

```yaml
  - id: openai-backup
    type: openai
    enabled: true
    circuit_breaker:
      failure_threshold: 5      # failures before opening
      recovery_timeout: 60      # seconds before attempting recovery
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
3. Trigger a pipeline run via `POST /admin/api/pipeline/run`
4. Check logs for circuit breaker state changes:
   ```
   Circuit breaker for ollama-local: CLOSED -> OPEN
   Falling back to openai-backup for researcher role
   ```

### Automated Testing

```python
# tests/test_circuit_breaker.py
def test_circuit_breaker_failover():
    """Verify fallback provider is used when primary fails."""
    # Configure primary with circuit breaker that opens after 1 failure
    # Trigger a request that fails
    # Verify secondary provider was used
    pass
```

### Verifying Failover in Production

1. Check circuit breaker metrics at the admin stats endpoint
2. Monitor `circuit_breaker.state_change` counter in your metrics dashboard
3. Set up alerts for OPEN transitions:
   ```
   alert: CircuitBreakerOpen
   expr: rate(circuit_breaker.opened[5m]) > 0
   for: 1m
   ```

## Troubleshooting

### All Providers Unavailable

If all providers for a role are unavailable, the pipeline degrades:
- Research stage: Uses source text only, sets impact_score to 30
- Write stage: Generates minimal draft from extracted text
- Edit stage: Routes article to REVIEW status

Check degradation metrics via `pipeline.degradation` counter.

### Provider Health Checks

Each provider exposes a `health_check()` method. Check provider status:

```python
from services.llm import get_provider_for_role

provider, model, max_tokens, provider_id = get_provider_for_role("researcher")
health = provider.health_check()
```

### Reloading Configuration

After modifying `providers.yaml`, reload without restarting:

```bash
curl -X POST http://localhost:5000/admin/api/config/reload \
  -H "Authorization: Bearer <token>"
```

This clears the provider cache and reinitializes all providers.

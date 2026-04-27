# Cost Tracking

The cost tracking system monitors LLM usage across the pipeline to provide budgeting and cost analytics.

## Overview

`services/cost_tracker.py` provides cost aggregation by reading token usage from `MetricsCollector` counters and applying configurable pricing rates.

The system:

1. Reads `llm.tokens` and `llm.calls` counters from metrics
2. Parses provider/model labels from counter keys
3. Applies pricing rates to calculate estimated costs
4. Returns `CostSummary` with per-model breakdown

## Token Counting Flow

LLM providers return a response object with `tokens_used` attribute:

```python
result = provider.chat_structured(...)
tokens = result.tokens_used  # Total tokens (or input/output tuple)
```

Pipeline tasks record tokens via `MetricsCollector`:

```python
metrics.counter_inc(
    "llm.tokens",
    labels={"provider": provider_id, "model": model},
    value=tokens
)
metrics.counter_inc(
    "llm.calls",
    labels={"provider": provider_id, "model": model},
    value=1
)
```

The metrics collector aggregates these counters in Redis (for multi-worker deployments).

## Cost Calculation

Since most providers don't distinguish input vs output tokens, a blended rate is used:

- `COST_INPUT_RATIO`: Percentage treated as input (default: 0.6 = 60%)
- `COST_OUTPUT_RATIO`: Percentage treated as output (default: 0.4 = 40%)

Formula:

```
estimated_cost = total_tokens * (input_rate * input_ratio + output_rate * output_ratio) / 1_000_000
```

## Default Rates

Pricing per 1 million tokens (USD). Override via `COST_RATES` env var:

```bash
export COST_RATES='{"openai/gpt-4o": {"input": 2.50, "output": 10.00}}'
```

| Provider | Model | Input $/M | Output $/M |
|---------|-------|-----------|-----------|
| OpenAI | gpt-4o | $2.50 | $10.00 |
| OpenAI | gpt-4o-mini | $0.15 | $0.60 |
| OpenAI | gpt-4-turbo | $10.00 | $30.00 |
| Anthropic | claude-sonnet-4-20250514 | $3.00 | $15.00 |
| Anthropic | claude-haiku-20241022 | $0.25 | $1.25 |
| Anthropic | claude-opus-4-20250514 | $15.00 | $75.00 |
| DeepSeek | deepseek-chat | $0.27 | $1.10 |
| MiniMax | MiniMax-M2.5 | $0.20 | $1.10 |
| Google | gemini-2.0-flash | $0.10 | $0.40 |
| Groq | llama-3.3-70b-versatile | $0.59 | $0.79 |
| XAI | grok-2-1212 | $2.00 | $10.00 |
| Zai | glm-4 | $1.40 | $1.40 |
| Cerebras | llama-3.3-70b | $0.85 | $1.20 |
| TogetherAI | meta-llama/Llama-3-70b-chat-hf | $0.80 | $0.80 |
| Fireworks | llama-v3-70b-instruct | $0.80 | $0.80 |

Rates are periodically updated as providers change pricing. Check provider documentation for latest rates.

## Admin Endpoint

`GET /admin/api/costs` returns a JSON breakdown:

```json
{
  "total_tokens": 1250000,
  "total_cost_usd": 45.32,
  "total_calls": 1250,
  "period_start": "2026-04-01",
  "period_end": "2026-04-30",
  "models": [
    {
      "provider": "openai",
      "model": "gpt-4o",
      "total_tokens": 800000,
      "estimated_cost_usd": 32.50,
      "call_count": 800
    },
    ...
  ]
}
```

Query parameters:

- `date_from`: Start date (ISO format)
- `date_end`: End date (ISO format)
- `provider`: Filter by provider name

## Integration Points

Pipeline stages record costs automatically via their metrics counters:

- `tasks/select.py` — Selection stage LLM calls
- `tasks/research.py` — Research stage LLM calls
- `tasks/write.py` — Writing stage LLM calls
- `tasks/edit.py` — Editing stage LLM calls
- `services/newsletter_pipeline.py` — Newsletter pipeline LLM calls

Each task wraps LLM calls with metrics recording:

```python
with traced_llm_call(provider, model, stage):
    result = provider.chat_structured(...)
```

This records both tokens and calls for cost tracking.

## Limitations

1. **Blended rates**: Input/output token distinction is not available for most providers. The 60/40 split is an approximation.

2. **Missing rates**: Some newer providers may not have rates defined. They appear as $0.00 cost until rates are added.

3. **Approximate costs**: Calculated costs are estimates. Actual bills from providers may differ slightly due to rounding, prompts, or metering differences.

4. **No per-request breakdown**: Costs are aggregated; individual request costs are not stored.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COST_RATES` | (see Default Rates) | JSON pricing rates |
| `COST_INPUT_RATIO` | 0.6 | Input token ratio (0.0-1.0) |
| `COST_OUTPUT_RATIO` | 0.4 | Output token ratio (0.0-1.0) |

Example custom rates:

```bash
export COST_RATES='{
  "openai/gpt-4o": {"input": 2.50, "output": 10.00},
  "anthropic/claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00}
}'
export COST_INPUT_RATIO=0.5
export COST_OUTPUT_RATIO=0.5
```

## Alerting

Consider adding cost alerts based on the `llm.tokens` counters:

```python
# Pseudocode for alerting
cost_summary = get_cost_summary()
daily_cost = cost_summary.total_cost_usd / 30  # Approximate daily
if daily_cost > DAILY_COST_THRESHOLD:
    send_alert(f"Daily LLM cost ${daily_cost:.2f} exceeds ${DAILY_COST_THRESHOLD}")
```

This is a manual integration point; cost alerting is not built into the pipeline.
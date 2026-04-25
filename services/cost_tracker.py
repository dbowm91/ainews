"""LLM cost tracking service.

Aggregates token usage from metrics counters and provides per-provider,
per-model cost estimates. Pricing is configurable via environment variables
or uses sensible defaults.
"""

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default pricing per 1M tokens (USD). Override via COST_RATES env var.
# Format: COST_RATES='{"openai/gpt-4o": {"input": 2.50, "output": 10.00}}'
_DEFAULT_RATES = {
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "anthropic/claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "anthropic/claude-haiku-20241022": {"input": 0.25, "output": 1.25},
    "anthropic/claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
    "minimax/MiniMax-M2.5": {"input": 0.20, "output": 1.10},
    "gemini/gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "groq/llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "openrouter/anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "xai/grok-2-1212": {"input": 2.00, "output": 10.00},
    "togetherai/meta-llama/Llama-3-70b-chat-hf": {"input": 0.80, "output": 0.80},
    "fireworks/accounts/fireworks/models/llama-v3-70b-instruct": {"input": 0.80, "output": 0.80},
    "cerebras/llama-3.3-70b": {"input": 0.85, "output": 1.20},
    "zai/glm-4": {"input": 1.40, "output": 1.40},
}


@dataclass
class ModelCost:
    """Cost breakdown for a single model."""

    provider: str
    model: str
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    call_count: int = 0


@dataclass
class CostSummary:
    """Aggregated cost summary."""

    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_calls: int = 0
    models: list[ModelCost] = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""


def _load_rates() -> dict[str, dict[str, float]]:
    """Load cost rates from env var or use defaults."""
    raw = os.environ.get("COST_RATES", "")
    if raw:
        try:
            custom = json.loads(raw)
            rates = dict(_DEFAULT_RATES)
            rates.update(custom)
            return rates
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to parse COST_RATES: %s, using defaults", e)
    return dict(_DEFAULT_RATES)


def get_cost_summary() -> CostSummary:
    """Get cost summary from current metrics counters.

    Reads LLM token and call counters from MetricsCollector and estimates
    costs using configured rates. Since we don't distinguish input vs output
    tokens in the counter, we use a blended rate (60% input, 40% output).

    Returns:
        CostSummary with per-model breakdown.
    """
    from services.metrics import get_metrics

    metrics = get_metrics().get_metrics()
    counters = metrics.get("counters", {})
    rates = _load_rates()

    summary = CostSummary()
    model_costs: dict[str, ModelCost] = {}

    for key, value in counters.items():
        # Parse keys like: llm.tokens{model=gpt-4o,provider=openai}
        # or: llm.calls{model=gpt-4o,provider=openai}
        if not key.startswith("llm."):
            continue

        metric_type, labels_str = _parse_metric_key(key)
        if metric_type is None:
            continue

        provider = labels_str.get("provider", "unknown")
        model = labels_str.get("model", "unknown")
        model_key = f"{provider}/{model}"

        if model_key not in model_costs:
            model_costs[model_key] = ModelCost(provider=provider, model=model)

        mc = model_costs[model_key]
        if metric_type == "llm.tokens":
            mc.total_tokens += value
        elif metric_type == "llm.calls":
            mc.call_count += value

    # Estimate costs
    input_ratio_str = os.environ.get("COST_INPUT_RATIO", "0.6")
    output_ratio_str = os.environ.get("COST_OUTPUT_RATIO", "0.4")
    try:
        input_ratio = float(input_ratio_str)
    except ValueError:
        logger.warning("Invalid COST_INPUT_RATIO: %r, using 0.6", input_ratio_str)
        input_ratio = 0.6
    try:
        output_ratio = float(output_ratio_str)
    except ValueError:
        logger.warning("Invalid COST_OUTPUT_RATIO: %r, using 0.4", output_ratio_str)
        output_ratio = 0.4
    for model_key, mc in model_costs.items():
        rate = rates.get(model_key)
        if rate and mc.total_tokens > 0:
            blended = rate["input"] * input_ratio + rate["output"] * output_ratio
            mc.estimated_cost_usd = round(mc.total_tokens / 1_000_000 * blended, 4)
        else:
            logger.debug("No pricing found for model: %s", model_key)
        summary.total_tokens += mc.total_tokens
        summary.total_cost_usd += mc.estimated_cost_usd
        summary.total_calls += mc.call_count
        summary.models.append(mc)

    summary.models.sort(key=lambda m: m.estimated_cost_usd, reverse=True)
    summary.total_cost_usd = round(summary.total_cost_usd, 4)
    return summary


def _parse_metric_key(key: str) -> tuple[str | None, dict[str, str]]:
    """Parse a metric key like 'llm.tokens{model=gpt-4o,provider=openai}'.

    Returns (metric_name, labels_dict) or (None, {}) if not parseable.
    """
    if "{" in key:
        name, rest = key.split("{", 1)
        labels_str = rest.rstrip("}")
        labels = {}
        for part in labels_str.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k.strip()] = v.strip()
        return name, labels
    return key, {}

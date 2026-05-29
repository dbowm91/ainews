"""Stage cost estimation service for pipeline planning.

Provides read-only cost estimates for pipeline stages based on aggregate
metrics counters. Used by subagents to estimate approximate cost before
running a stage.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.cost_tracker import get_cost_summary

logger = logging.getLogger(__name__)

STAGE_NAMES = frozenset({"select", "research", "write", "edit", "finalize", "publish"})


def estimate_stage_cost(
    stage: str,
    model: Optional[str] = None,
) -> dict:
    """Estimate the cost of running a pipeline stage.

    Args:
        stage: Pipeline stage name (select, research, write, edit, finalize, publish).
        model: Optional specific model ID (e.g. "openai/gpt-4o").

    Returns:
        Dict with stage, model, estimated_cost_usd, call_count, token_count.
    """
    if stage not in STAGE_NAMES:
        return {"error": f"Unknown stage: {stage}. Valid: {sorted(STAGE_NAMES)}"}

    summary = get_cost_summary()

    if model:
        matching = [m for m in summary.models if f"{m.provider}/{m.model}" == model]
        if not matching:
            return {
                "stage": stage,
                "model": model,
                "estimated_cost_usd": 0.0,
                "call_count": 0,
                "token_count": 0,
                "note": f"No metrics found for model {model}",
            }
        mc = matching[0]
        stage_calls = mc.stages.get(stage, 0)
        avg_cost_per_call = (
            mc.estimated_cost_usd / mc.call_count if mc.call_count > 0 else 0.0
        )
        return {
            "stage": stage,
            "model": model,
            "estimated_cost_usd": round(avg_cost_per_call * stage_calls, 4),
            "call_count": stage_calls,
            "token_count": 0,
        }

    stage_cost = summary.stages.get(stage, 0.0)
    total_calls_for_stage = 0
    for mc in summary.models:
        total_calls_for_stage += mc.stages.get(stage, 0)

    return {
        "stage": stage,
        "model": None,
        "estimated_cost_usd": round(stage_cost, 4),
        "call_count": total_calls_for_stage,
        "token_count": 0,
    }

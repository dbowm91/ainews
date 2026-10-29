"""Atomic Redis budget for optional per-article and daily LLM calls."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.exceptions

logger = logging.getLogger(__name__)

_RESERVE_SCRIPT = """
local article_count = tonumber(redis.call('GET', KEYS[1]) or '0')
local daily_count = tonumber(redis.call('GET', KEYS[2]) or '0')
if article_count >= tonumber(ARGV[1]) or daily_count >= tonumber(ARGV[2]) then
    return 0
end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 1
"""


def reserve_optional_llm_call(article_id: int, stage: str) -> bool:
    """Reserve one optional invocation, including retries, before dispatch.

    If Redis is unavailable, preserve the pre-optimization pipeline behavior
    and allow the call. A configured cap must never turn a storage outage into
    a failed article.
    """
    from schemas.pipeline import load_pipeline_config

    config = load_pipeline_config().optimizations
    if not config.optional_llm_call_caps_enabled:
        return True
    article_cap = config.max_optional_llm_calls_per_article_per_day
    daily_cap = config.max_optional_llm_calls_per_day
    if article_cap == 0 or daily_cap == 0:
        _record_decision(stage, allowed=False, reason="zero_cap")
        return False

    day = datetime.now(timezone.utc).date().isoformat()
    article_key = f"ainews:optional-llm:{day}:article:{int(article_id)}"
    daily_key = f"ainews:optional-llm:{day}:all"
    try:
        from extensions import get_redis

        reserve = get_redis().register_script(_RESERVE_SCRIPT)
        allowed = bool(reserve(
            keys=[article_key, daily_key],
            args=[article_cap, daily_cap, 172800],
        ))
    except redis.exceptions.RedisError as exc:
        logger.warning("Optional LLM budget unavailable; allowing stage %s: %s", stage, type(exc).__name__)
        _record_decision(stage, allowed=True, reason="redis_unavailable")
        return True
    except (AttributeError, ImportError, RuntimeError, ValueError) as exc:
        logger.warning("Optional LLM budget could not initialize; allowing stage %s: %s", stage, type(exc).__name__)
        _record_decision(stage, allowed=True, reason="budget_unavailable")
        return True

    _record_decision(stage, allowed=allowed, reason="reserved" if allowed else "cap_reached")
    return allowed


def _record_decision(stage: str, *, allowed: bool, reason: str) -> None:
    try:
        from services.metrics import get_metrics

        get_metrics().counter_inc(
            "pipeline.optional_llm_budget",
            labels={"stage": stage, "decision": "allowed" if allowed else "denied", "reason": reason},
        )
    except (ImportError, AttributeError, ValueError):
        logger.debug("Could not record optional LLM budget decision", exc_info=True)

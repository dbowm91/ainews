"""Pipeline monitoring and failure rate tracking.

Provides Redis minute-bucket counters for each pipeline stage
(crawl, select, research, write, edit) to track success/failure counts.
"""

import time
import logging
from typing import Optional

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Redis key prefix for pipeline counters
_PIPELINE_COUNTER_PREFIX = "ainews:pipeline:counters:"
_PIPELINE_WINDOW_SECONDS = 60  # 1 minute buckets


def _get_redis():
    """Get Redis client for pipeline monitoring."""
    from extensions import get_redis

    return get_redis()


def record_stage_result(
    stage: str, success: bool, run_id: Optional[int] = None
) -> None:
    """Record a pipeline stage result (success or failure).

    Args:
        stage: Pipeline stage name (crawl, select, research, write, edit)
        success: True if stage succeeded, False if failed
        run_id: Optional pipeline run ID for additional context
    """
    try:
        redis_client = _get_redis()
        current_minute = int(time.time() // _PIPELINE_WINDOW_SECONDS)

        success_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{current_minute}:success"
        failure_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{current_minute}:failure"

        pipe = redis_client.pipeline()
        if success:
            pipe.incr(success_key)
            pipe.expire(success_key, 1800)
        else:
            pipe.incr(failure_key)
            pipe.expire(failure_key, 1800)
        pipe.execute()

        logger.debug(
            "Pipeline stage %s: %s", stage, "success" if success else "failure"
        )

    except RedisError as e:
        logger.warning("Failed to record pipeline stage result: %s", e)


def get_stage_stats(stage: str, minutes: int = 15) -> dict:
    """Get pipeline stage statistics for recent minutes.

    Uses a single mget call instead of 2*N individual gets.

    Args:
        stage: Pipeline stage name (crawl, select, research, write, edit)
        minutes: Number of recent minutes to aggregate (default 15)

    Returns:
        dict with keys:
            - success_count: Total successes in window
            - failure_count: Total failures in window
            - success_rate: Success rate as percentage (0-100)
            - window_minutes: Actual window size in minutes
    """
    try:
        redis_client = _get_redis()
        current_minute = int(time.time() // _PIPELINE_WINDOW_SECONDS)

        keys = []
        for i in range(minutes):
            minute = current_minute - i
            keys.append(f"{_PIPELINE_COUNTER_PREFIX}{stage}:{minute}:success")
            keys.append(f"{_PIPELINE_COUNTER_PREFIX}{stage}:{minute}:failure")

        values = redis_client.mget(keys)

        total_success = 0
        total_failure = 0

        for i in range(minutes):
            success_val = values[i * 2]
            failure_val = values[i * 2 + 1]
            if success_val:
                total_success += int(success_val)
            if failure_val:
                total_failure += int(failure_val)

        total = total_success + total_failure
        success_rate = (total_success / total * 100) if total > 0 else 100.0

        return {
            "success_count": total_success,
            "failure_count": total_failure,
            "success_rate": round(success_rate, 2),
            "window_minutes": minutes,
        }

    except RedisError as e:
        logger.error("Failed to get pipeline stage stats: %s", e)
        return {
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 100.0,
            "window_minutes": minutes,
        }


def get_all_stages_stats(minutes: int = 15) -> dict:
    """Get statistics for all pipeline stages.

    Args:
        minutes: Number of recent minutes to aggregate (default 15)

    Returns:
        dict mapping stage names to their stats
    """
    stages = ["crawl", "select", "research", "write", "edit"]
    return {stage: get_stage_stats(stage, minutes) for stage in stages}


def clear_stage_stats(stage: Optional[str] = None) -> None:
    """Clear pipeline stage statistics.

    Args:
        stage: If provided, clear only this stage's stats.
               If None, clear all stages.
    """
    try:
        redis_client = _get_redis()

        if stage:
            pattern = f"{_PIPELINE_COUNTER_PREFIX}{stage}:*"
        else:
            pattern = f"{_PIPELINE_COUNTER_PREFIX}*"

        # Use scan_iter to avoid blocking Redis with keys()
        keys = list(redis_client.scan_iter(match=pattern, count=500))
        if keys:
            redis_client.delete(*keys)
            logger.info("Cleared %d pipeline counter keys", len(keys))

    except RedisError as e:
        logger.error("Failed to clear pipeline stats: %s", e)

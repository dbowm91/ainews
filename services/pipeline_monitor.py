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
        redis = _get_redis()
        current_minute = int(time.time() // _PIPELINE_WINDOW_SECONDS)

        # Keys for success and failure counters in current minute
        success_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{current_minute}:success"
        failure_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{current_minute}:failure"

        if success:
            redis.incr(success_key)
        else:
            redis.incr(failure_key)

        # Set expiration to keep only recent data (30 minutes)
        redis.expire(success_key, 1800)
        redis.expire(failure_key, 1800)

        logger.debug(f"Pipeline stage {stage}: {'success' if success else 'failure'}")

    except RedisError as e:
        logger.warning(f"Failed to record pipeline stage result: {e}")


def get_stage_stats(stage: str, minutes: int = 15) -> dict:
    """Get pipeline stage statistics for recent minutes.

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
        redis = _get_redis()
        current_minute = int(time.time() // _PIPELINE_WINDOW_SECONDS)

        total_success = 0
        total_failure = 0

        for i in range(minutes):
            minute = current_minute - i
            success_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{minute}:success"
            failure_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{minute}:failure"

            success_str = redis.get(success_key)
            failure_str = redis.get(failure_key)

            if success_str:
                total_success += int(success_str)
            if failure_str:
                total_failure += int(failure_str)

        total = total_success + total_failure
        success_rate = (total_success / total * 100) if total > 0 else 100.0

        return {
            "success_count": total_success,
            "failure_count": total_failure,
            "success_rate": round(success_rate, 2),
            "window_minutes": minutes,
        }

    except RedisError as e:
        logger.error(f"Failed to get pipeline stage stats: {e}")
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
        redis = _get_redis()

        if stage:
            pattern = f"{_PIPELINE_COUNTER_PREFIX}{stage}:*"
        else:
            pattern = f"{_PIPELINE_COUNTER_PREFIX}*"

        # Get all matching keys
        keys = redis.keys(pattern)
        if keys:
            redis.delete(*keys)
            logger.info(f"Cleared {len(keys)} pipeline counter keys")

    except RedisError as e:
        logger.error(f"Failed to clear pipeline stats: {e}")

"""Shared cancellation state and Celery task tracking for pipeline runs."""

from __future__ import annotations

import logging
import ast
from typing import Any

logger = logging.getLogger(__name__)
_TASK_SET_PREFIX = "ainews:pipeline_run:tasks:"
_CANCEL_KEY_PREFIX = "ainews:pipeline_run:cancelled:"


def task_set_key(run_id: int) -> str:
    return f"{_TASK_SET_PREFIX}{int(run_id)}"


def cancel_key(run_id: int) -> str:
    return f"{_CANCEL_KEY_PREFIX}{int(run_id)}"


def mark_pipeline_cancelled(run_id: int) -> None:
    from extensions import get_redis

    get_redis().set(cancel_key(run_id), "1", ex=7 * 24 * 60 * 60)


def is_pipeline_run_cancelled(run_id: int | None) -> bool:
    if run_id is None:
        return False
    from extensions import db, get_redis
    from models import PipelineRun

    try:
        if get_redis().exists(cancel_key(run_id)):
            return True
    except Exception:  # noqa: BLE001 - retain the database status fallback
        logger.debug("Could not read cancellation flag for run %s", run_id, exc_info=True)

    # Use an independent connection so this check cannot return a stale ORM
    # identity-map object held across a long-running inference call.
    from sqlalchemy import select

    with db.engine.connect() as connection:
        status = connection.execute(
            select(PipelineRun.status).where(PipelineRun.id == int(run_id)),
        ).scalar_one_or_none()
    return status == "cancelled"


def track_published_task(sender: str | None, body: Any, headers: dict | None) -> None:
    """Index task ids by run before publish, including queued/reserved tasks."""
    task_id = (headers or {}).get("id")
    if not task_id:
        return

    task_kwargs: dict = {}
    if isinstance(body, dict):
        task_kwargs = body.get("kwargs") or {}
    elif isinstance(body, (tuple, list)) and len(body) >= 2:
        candidate = body[1]
        if isinstance(candidate, dict):
            task_kwargs = candidate
    run_id = task_kwargs.get("run_id")
    if run_id is None:
        return

    try:
        from extensions import get_redis

        client = get_redis()
        key = task_set_key(int(run_id))
        client.sadd(key, str(task_id))
        client.expire(key, 86400)
    except Exception as exc:  # noqa: BLE001 - task publication must survive index failures
        logger.warning("Could not track pipeline task %s for cancellation: %s", task_id, exc)


def get_pipeline_task_ids(run_id: int) -> set[str]:
    from extensions import get_redis

    try:
        values = get_redis().smembers(task_set_key(run_id))
    except Exception:  # noqa: BLE001 - cancellation still uses the root task id
        logger.warning("Could not read task index for pipeline run %s", run_id, exc_info=True)
        return set()
    return {
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in values
    }


def inspect_pipeline_task_ids(celery_app, run_id: int) -> set[str]:
    """Find already active or reserved tasks if the publish index is absent."""
    try:
        inspector = celery_app.control.inspect(timeout=1)
        states = [inspector.active(), inspector.reserved(), inspector.scheduled()]
    except Exception:  # noqa: BLE001 - the persisted run status still prevents future stages
        logger.warning("Could not inspect Celery tasks for pipeline run %s", run_id, exc_info=True)
        return set()

    found: set[str] = set()
    for worker_state in states:
        if not isinstance(worker_state, dict):
            continue
        for tasks in worker_state.values():
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict) or not task.get("id"):
                    continue
                kwargs = task.get("kwargs")
                args = task.get("args")
                for name, value in (("kwargs", kwargs), ("args", args)):
                    if isinstance(value, str):
                        try:
                            parsed = ast.literal_eval(value)
                        except (SyntaxError, ValueError):
                            parsed = None
                        if name == "kwargs":
                            kwargs = parsed
                        else:
                            args = parsed
                candidate = kwargs.get("run_id") if isinstance(kwargs, dict) else None
                if candidate is None and isinstance(args, (tuple, list)):
                    candidate = next(
                        (arg for arg in args if isinstance(arg, int) and not isinstance(arg, bool)),
                        None,
                    )
                try:
                    matches = candidate is not None and int(candidate) == int(run_id)
                except (TypeError, ValueError):
                    matches = False
                if matches:
                    found.add(str(task["id"]))
    return found

"""Shared pipeline utilities extracted to break circular imports."""

import threading

from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

logger = get_task_logger(__name__)

_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "written": ("tasks.edit", "edit_article"),
    "editing": ("tasks.edit", "edit_article"),
}

_task_fn_cache: dict[str, tuple] = {}
_task_fn_cache_lock = threading.Lock()


def clear_task_fn_cache() -> None:
    """Clear the task function cache.

    Called after config reload to ensure stale task references are refreshed.
    """
    _task_fn_cache.clear()


def _dispatch_next(
    article_id: int,
    run_id: int | None = None,
    next_status: str | None = None,
    article=None,
    request_id: str | None = None,
) -> None:
    """Dispatch the next pipeline stage based on article status.

    Looks up the Celery task corresponding to the article's current (or
    provided) pipeline status and calls ``.delay()`` to enqueue it.

    Args:
        article_id: ID of the article to process.
        run_id: Optional pipeline-run ID for log correlation.
        next_status: Override status; if ``None``, uses ``article.pipeline_status``.
        article: Article model instance (used only when *next_status* is ``None``).
        request_id: Optional request ID for log correlation (extracted from context if not provided).
    """
    from services.logging_utils import get_task_request_id

    if request_id is None:
        request_id = get_task_request_id()

    status = next_status or (article.pipeline_status if article else None)
    if not status:
        return
    with _task_fn_cache_lock:
        if status not in _task_fn_cache:
            module_path, task_name = _STAGE_TASKS.get(status, (None, None))
            if module_path:
                import importlib

                module = importlib.import_module(module_path)
                _task_fn_cache[status] = (module, task_name)
            else:
                return
        module, task_name = _task_fn_cache[status]
    task_fn = getattr(module, task_name)
    headers = {"request_id": request_id} if request_id else None
    task_fn.apply_async(args=[article_id], kwargs={"run_id": run_id}, headers=headers)


def _dispatch_for_status(article) -> None:
    """Re-dispatch the task matching the article's current pipeline status.

    Convenience wrapper around :func:`_dispatch_next` that reads the status
    from the article object directly.

    Args:
        article: Article model instance with a populated ``pipeline_status``.
    """
    _dispatch_next(article.id, article=article)


def _log_pipeline(run_id, stage, level, message, *args, article_id=None):
    """Create a PipelineLog entry without committing outer transactions.

    Uses a nested transaction (savepoint) so that a log-write failure does not
    roll back the caller's work.  Fatal-level (``"error"``) log failures are
    re-raised after the failed savepoint is rolled back.

    Args:
        run_id: Pipeline-run ID.
        stage: Pipeline stage name (e.g. ``"select"``, ``"write"``).
        level: Log level — ``"info"``, ``"warning"``, or ``"error"``.
        message: Human-readable log message, optionally with %-format placeholders.
        *args: Positional args for message formatting.
        article_id: Optional article ID for correlation.

    Raises:
        No exceptions are re-raised. Errors are logged and a metric is
        incremented.
    """
    from extensions import db
    from models import PipelineLog
    from services.metrics import get_metrics

    if args:
        message = message % args

    metrics = get_metrics()
    savepoint = db.session.begin_nested()
    try:
        log = PipelineLog(
            run_id=run_id,
            article_id=article_id,
            stage=stage,
            level=level,
            message=message,
        )
        db.session.add(log)
        savepoint.commit()
    except (SQLAlchemyError, ImportError) as e:
        savepoint.rollback()
        logger.error("Failed to write pipeline log: %s", e)
        metrics.counter_inc(
            "pipeline.log_write_failed", labels={"stage": stage, "level": level},
        )
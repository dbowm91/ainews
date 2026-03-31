"""Structured logging helpers for pipeline and article operations.

Wraps standard logging with consistent structured context for
pipeline stages, article processing, and admin actions.
"""

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


def log_pipeline_event(
    stage: str,
    event: str,
    article_id: Optional[int] = None,
    run_id: Optional[int] = None,
    level: str = "info",
    **extra: Any,
) -> None:
    """Log a pipeline event with structured context.

    Args:
        stage: Pipeline stage name (crawl, select, research, write, edit)
        event: Event description
        article_id: Optional article ID
        run_id: Optional pipeline run ID
        level: Log level (debug, info, warning, error)
        **extra: Additional context fields
    """
    msg = f"Pipeline [{stage}]: {event}"
    ctx = {"stage": stage, "event": event}
    if article_id is not None:
        ctx["article_id"] = article_id
    if run_id is not None:
        ctx["run_id"] = run_id
    ctx.update(extra)

    log_fn = getattr(logger, level, logger.info)
    log_fn(msg, extra=ctx)


def log_article_event(
    article_id: int,
    event: str,
    level: str = "info",
    **extra: Any,
) -> None:
    """Log an article-related event with structured context.

    Args:
        article_id: Article ID
        event: Event description
        level: Log level
        **extra: Additional context fields
    """
    msg = f"Article {article_id}: {event}"
    ctx = {"article_id": article_id, "event": event}
    ctx.update(extra)

    log_fn = getattr(logger, level, logger.info)
    log_fn(msg, extra=ctx)


def log_admin_event(
    action: str,
    user: str = "admin",
    target: Optional[str] = None,
    **extra: Any,
) -> None:
    """Log an admin event with structured context.

    For audit-grade logging with persistence, use services.audit.log_admin_action.

    Args:
        action: Action performed
        user: User performing the action
        target: Optional target of the action
        **extra: Additional context fields
    """
    msg = f"Admin [{user}] {action}"
    ctx = {"action": action, "user": user}
    if target:
        ctx["target"] = target
    ctx.update(extra)

    logger.info(msg, extra=ctx)


class PipelineLogger:
    """Wraps a logger and adds structured pipeline context to messages."""

    def __init__(self, stage: str, base_logger: logging.Logger = None):
        self.stage = stage
        self.logger = base_logger or logger

    def _format(self, msg: str, **context) -> str:
        if context:
            ctx = json.dumps(context, default=str)
            return f"[{self.stage}] {msg} | {ctx}"
        return f"[{self.stage}] {msg}"

    def info(self, msg: str, **context):
        self.logger.info(self._format(msg, **context))

    def warning(self, msg: str, **context):
        self.logger.warning(self._format(msg, **context))

    def error(self, msg: str, **context):
        self.logger.error(self._format(msg, **context))


def get_pipeline_logger(
    stage: str, base_logger: logging.Logger = None
) -> PipelineLogger:
    """Get a structured logger for a pipeline stage."""
    return PipelineLogger(stage, base_logger)


@contextmanager
def log_duration(operation: str, **extra: Any):
    """Context manager that logs the duration of an operation.

    Usage:
        with log_duration("fetch_articles", source="hn"):
            articles = fetch_from_source()
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "%s completed in %sms",
            operation,
            duration_ms,
            extra={"operation": operation, "duration_ms": duration_ms, **extra},
        )

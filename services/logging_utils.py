"""Structured logging helpers for pipeline and article operations.

Wrappers for standard logging with consistent structured context for
pipeline stages, article processing, and admin actions. Also provides
OpenTelemetry tracing integration for distributed tracing.
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.trace import SpanKind, Tracer
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    trace = None
    Tracer = object
    SpanKind = None
    TraceContextTextMapPropagator = None

logger = logging.getLogger(__name__)

_task_request_id_var: ContextVar[str] = ContextVar("task_request_id", default="")

_tracer: Optional[Tracer] = None
_propagator = None


def _setup_opentelemetry():
    """Configure OpenTelemetry with OTLP exporter if endpoint is set."""
    if not _OTEL_AVAILABLE:
        return

    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set, skipping OTel setup")
        return

    from opentelemetry.exporter.otlp import OTLPSpanExporter

    exporter = OTLPSpanExporter(endpoint=endpoint)
    span_processor = BatchSpanProcessor(exporter)

    trace.set_tracer_provider(TracerProvider(resource=Resource.create({ResourceAttributes.SERVICE_NAME: "ainews"})))
    trace.get_tracer_provider().add_span_processor(span_processor)


def get_tracer(name: str = __name__) -> Optional[Tracer]:
    """Get or create an OpenTelemetry tracer.

    Returns None if OpenTelemetry is not available.
    """
    global _tracer
    if not _OTEL_AVAILABLE:
        return None
    if _tracer is None:
        _setup_opentelemetry()
        if trace.get_tracer_provider() is None:
            return None
        _tracer = trace.get_tracer(name)
    return _tracer


def get_propagator():
    """Get the trace context propagator."""
    global _propagator
    if _propagator is None and _OTEL_AVAILABLE:
        _propagator = TraceContextTextMapPropagator()
    return _propagator


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
    ctx = {"stage": stage, "event": event}
    if article_id is not None:
        ctx["article_id"] = article_id
    if run_id is not None:
        ctx["run_id"] = run_id
    ctx.update(extra)

    log_fn = getattr(logger, level, logger.info)
    log_fn("Pipeline [%s]: %s", stage, event, extra=ctx)


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
    ctx = {"article_id": article_id, "event": event}
    ctx.update(extra)

    log_fn = getattr(logger, level, logger.info)
    log_fn("Article %s: %s", article_id, event, extra=ctx)


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
    ctx = {"action": action, "user": user}
    if target:
        ctx["target"] = target
    ctx.update(extra)

    logger.info("Admin [%s] %s", user, action, extra=ctx)


class PipelineLogger:
    """Wraps a logger and adds structured pipeline context to messages."""

    def __init__(
        self,
        stage: str,
        base_logger: logging.Logger = None,
        task_id: str = None,
    ):
        self.stage = stage
        self.logger = base_logger or logger
        self.task_id = task_id

    def _format(self, msg: str, **context) -> str:
        if context:
            ctx = json.dumps(context, default=str).replace("%", "%%")
            return "[%s] %s | %s" % (self.stage, msg, ctx)
        return "[%s] %s" % (self.stage, msg)

    def _build_context(self, **context):
        ctx = dict(context)
        if self.task_id:
            ctx["task_id"] = self.task_id
        return ctx

    def info(self, msg: str, **context):
        self.logger.info(self._format(msg, **context), extra=self._build_context(**context))

    def warning(self, msg: str, **context):
        self.logger.warning(self._format(msg, **context), extra=self._build_context(**context))

    def error(self, msg: str, **context):
        self.logger.error(self._format(msg, **context), extra=self._build_context(**context))


def get_pipeline_logger(
    stage: str,
    base_logger: logging.Logger = None,
    task_id: str = None,
) -> PipelineLogger:
    """Get a structured logger for a pipeline stage.

    Args:
        stage: Pipeline stage name
        base_logger: Optional base logger to wrap
        task_id: Optional Celery task ID for request tracing
    """
    return PipelineLogger(stage, base_logger, task_id=task_id)


def get_task_request_id() -> str:
    """Get the current task request ID from context."""
    return _task_request_id_var.get()


def set_task_request_id(request_id: str) -> None:
    """Set the task request ID in context."""
    _task_request_id_var.set(request_id)


@contextmanager
def task_request_id_context(request_id: str):
    """Context manager to set task request ID for the duration of a block."""
    token = _task_request_id_var.set(request_id)
    try:
        yield
    finally:
        _task_request_id_var.reset(token)


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


@contextmanager
def traced_llm_call(provider: str, model: str, stage: str):
    """Context manager for tracing LLM calls.

    Creates an OpenTelemetry span for an LLM provider call if tracing
    is available. Works as a no-op when OpenTelemetry is not installed.

    Args:
        provider: LLM provider name (e.g., "ollama", "openai")
        model: Model name being used
        stage: Pipeline stage (selector, researcher, writer, editor)

    Usage:
        with traced_llm_call("ollama", "qwen3:8b", "selector"):
            result = provider.chat_structured(...)
    """
    tracer = get_tracer()
    if tracer is None:
        yield
        return

    with tracer.start_as_current_span(f"llm.{stage}") as span:
        span.set_attribute("llm.provider", provider)
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.stage", stage)
        yield


@contextmanager
def traced_stage(stage: str, operation: str = "execute"):
    """Context manager for tracing pipeline stage execution.

    Args:
        stage: Pipeline stage name
        operation: Operation being performed within the stage

    Usage:
        with traced_stage("selector", "evaluate_article"):
            result = work_fn(article, provider, model, max_tokens)
    """
    tracer = get_tracer()
    if tracer is None:
        yield
        return

    with tracer.start_as_current_span(f"pipeline.{stage}.{operation}") as span:
        span.set_attribute("pipeline.stage", stage)
        span.set_attribute("pipeline.operation", operation)
        yield

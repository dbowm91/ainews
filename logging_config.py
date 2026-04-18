"""Structured logging configuration for the application."""

import logging
import json
import sys
import time
import uuid
import os
from datetime import datetime, timezone
from contextvars import ContextVar

# Context variable to store request ID across async contexts
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Slow query threshold in milliseconds
SLOW_QUERY_THRESHOLD_MS = 500

# Correlation ID for pipeline/lifecycle tracking
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current correlation ID from context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in context."""
    correlation_id_var.set(correlation_id)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return uuid.uuid4().hex[:12]


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID in context."""
    request_id_var.set(request_id)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging with request ID support."""

    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include request ID if available
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include any extra fields passed via logger.info("msg", extra={"key": "value"})
        for key, value in record.__dict__.items():
            if key not in log_data and key not in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
            ):
                try:
                    # Only include JSON-serializable values
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    pass

        return json.dumps(log_data)


class PlainFormatter(logging.Formatter):
    """Plain text formatter with optional request ID."""

    def format(self, record):
        request_id = get_request_id()
        if request_id:
            record.request_id = request_id
        return super().format(record)


class RequestIDMiddleware:
    """WSGI middleware that assigns a unique request ID to each request.

    The request ID is stored in contextvars for use in logging and
    is returned in the X-Request-ID response header. The context is
    properly cleaned up after each request via token reset.
    Also logs request timing for performance monitoring.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Generate or use existing request ID
        request_id = environ.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        request_logger = logging.getLogger("request")
        start_time = time.monotonic()

        def start_response_with_request_id(status, headers, *args, **kwargs):
            # Convert to list if tuple (WSGI allows any iterable)
            # Filter out any existing X-Request-ID to avoid duplicates
            headers = [(k, v) for k, v in headers if k.lower() != "x-request-id"] + [
                ("X-Request-ID", request_id)
            ]
            return start_response(status, headers, *args, **kwargs)

        try:
            return self.app(environ, start_response_with_request_id)
        finally:
            duration_ms = round((time.monotonic() - start_time) * 1000, 1)
            method = environ.get("REQUEST_METHOD", "?")
            path = environ.get("PATH_INFO", "/")
            request_logger.info(
                "%s %s completed in %sms",
                method,
                path,
                duration_ms,
                extra={"method": method, "path": path, "duration_ms": duration_ms},
            )
            request_id_var.reset(token)


def setup_logging(app=None, level=logging.INFO, config_name=None):
    """Configure structured logging for the application.

    Args:
        app: Flask application instance (optional)
        level: Logging level (default: INFO)
        config_name: Configuration name for environment-specific settings
    """
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler with configurable formatting
    console_handler = logging.StreamHandler(sys.stdout)
    log_format = os.environ.get("LOG_FORMAT", "json").lower()
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        # Plain text format with request ID
        formatter = PlainFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set specific loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    if config_name == "production":
        db_log_level = os.environ.get("DB_QUERY_LOG_LEVEL", "WARNING").upper()
        if hasattr(logging, db_log_level):
            logging.getLogger("sqlalchemy.engine").setLevel(getattr(logging, db_log_level))

    if app:
        # Configure Flask app logger
        app.logger.handlers = []
        app.logger.addHandler(console_handler)
        app.logger.setLevel(level)

        # Wrap app with request ID middleware
        app.wsgi_app = RequestIDMiddleware(app.wsgi_app)

    return root_logger


def setup_query_logging(engine):
    """Set up SQLAlchemy query logging with slow query detection.

    Args:
        engine: SQLAlchemy engine to attach listeners to
    """
    import traceback

    query_logger = logging.getLogger("db.query")
    slow_logger = logging.getLogger("db.slow_query")

    def before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        conn.info.setdefault("query_start_time", []).append(time.monotonic())

    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total_time_ms = (time.monotonic() - conn.info["query_start_time"].pop()) * 1000

        request_id = get_request_id()
        corr_id = get_correlation_id()

        log_data = {
            "duration_ms": round(total_time_ms, 2),
            "statement": statement[:500] if statement else "",
            "request_id": request_id or None,
            "correlation_id": corr_id or None,
        }

        if total_time_ms > SLOW_QUERY_THRESHOLD_MS:
            log_data["stack"] = traceback.format_stack()
            slow_logger.warning(
                "Slow query: %.2fms",
                total_time_ms,
                extra=log_data,
            )
        else:
            query_logger.debug(
                "Query: %.2fms",
                total_time_ms,
                extra=log_data,
            )

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)

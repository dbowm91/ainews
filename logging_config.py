"""Structured logging configuration for the application."""

import logging
import json
import sys
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar

# Context variable to store request ID across async contexts
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


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


class RequestIDMiddleware:
    """WSGI middleware that assigns a unique request ID to each request.

    The request ID is stored in contextvars for use in logging and
    is returned in the X-Request-ID response header. The context is
    properly cleaned up after each request via token reset.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Generate or use existing request ID
        request_id = environ.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)

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
            request_id_var.reset(token)


def setup_logging(app=None, level=logging.INFO):
    """Configure structured logging for the application.

    Args:
        app: Flask application instance (optional)
        level: Logging level (default: INFO)
    """
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)

    # Set specific loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    if app:
        # Configure Flask app logger
        app.logger.handlers = []
        app.logger.addHandler(console_handler)
        app.logger.setLevel(level)

        # Wrap app with request ID middleware
        app.wsgi_app = RequestIDMiddleware(app.wsgi_app)

    return root_logger

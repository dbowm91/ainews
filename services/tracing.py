"""Trace ID utilities for pipeline observability.

Provides trace ID generation and context management for distributed tracing
across pipeline stages (research, write, edit).
"""

import uuid
from contextvars import ContextVar
from typing import Optional

_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def generate_trace_id() -> str:
    """Generate a new unique trace ID.

    Returns:
        A unique trace ID string using UUID4
    """
    return str(uuid.uuid4())


def get_current_trace_id() -> str:
    """Get the current trace ID from context.

    Returns:
        The current trace ID, or a new one if not set
    """
    trace_id = _trace_id_var.get()
    if trace_id is None:
        trace_id = generate_trace_id()
        set_current_trace_id(trace_id)
    return trace_id


def set_current_trace_id(trace_id: str) -> None:
    """Set the current trace ID in context.

    Args:
        trace_id: The trace ID to set
    """
    _trace_id_var.set(trace_id)


def clear_current_trace_id() -> None:
    """Clear the current trace ID from context."""
    _trace_id_var.set(None)


class TraceContext:
    """Context manager for setting trace ID for a block of code."""

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or generate_trace_id()
        self._token = None

    def __enter__(self):
        self._token = _trace_id_var.set(self.trace_id)
        return self

    def __exit__(self, *args):
        if self._token:
            _trace_id_var.reset(self._token)

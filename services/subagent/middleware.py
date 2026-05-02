from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ToolMiddleware:
    """Base class for tool execution middleware."""

    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a tool function with middleware behavior."""
        return func


class LoggingMiddleware(ToolMiddleware):
    """Middleware that logs all tool executions."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        self.logger = log or logger

    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.logger.info("Tool %s called", func.__name__)
            try:
                result = func(*args, **kwargs)
                self.logger.info("Tool %s completed", func.__name__)
                return result
            except Exception as e:
                self.logger.error("Tool %s failed: %s", func.__name__, e)
                raise

        return wrapped


class TimingMiddleware(ToolMiddleware):
    """Middleware that records tool execution time."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        self.logger = log or logger

    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                self.logger.debug(
                    "Tool %s executed in %.3fs", func.__name__, elapsed,
                )
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                self.logger.debug(
                    "Tool %s failed after %.3fs: %s", func.__name__, elapsed, e,
                )
                raise

        return wrapped


class ErrorHandlingMiddleware(ToolMiddleware):
    """Middleware that handles and logs tool errors."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        self.logger = log or logger

    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error(
                    "Tool %s error: %s", func.__name__, e, exc_info=True,
                )
                raise

        return wrapped


def apply_middleware(
    func: Callable[..., Any],
    middleware_chain: list[ToolMiddleware],
) -> Callable[..., Any]:
    """Apply a chain of middleware to a function."""
    wrapped = func
    for middleware in reversed(middleware_chain):
        wrapped = middleware.wrap(wrapped)
    return wrapped

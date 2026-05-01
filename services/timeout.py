"""Timeout enforcement utilities.

Provides decorators and context managers for enforcing timeouts
on long-running operations (HTTP fetches, LLM calls, DB queries).
"""

import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Optional

logger = logging.getLogger(__name__)


class OperationTimeoutError(TimeoutError):
    """Raised when an operation exceeds its timeout."""

    def __init__(self, operation: str, timeout: float):
        self.operation = operation
        self.timeout = timeout
        super().__init__(f"Operation '{operation}' timed out after {timeout}s")


def timeout(seconds: float, operation: Optional[str] = None):
    """Decorator to enforce a timeout on a function.

    Uses ThreadPoolExecutor for cross-platform timeout support.
    The decorated function runs in a separate thread and is abandoned
    (not cancelled) if it exceeds the timeout. The thread continues
    in the background but its result is discarded.

    Args:
        seconds: Maximum execution time in seconds.
        operation: Descriptive name for logging (defaults to function name).

    Usage:
        @timeout(30, operation="fetch_url")
        def fetch_url(url):
            ...
    """

    def decorator(func):
        op_name = operation or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=seconds)
                except FuturesTimeout:
                    logger.warning(
                        "Operation '%s' timed out after %.1fs", op_name, seconds,
                    )
                    raise OperationTimeoutError(op_name, seconds)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return wrapper

    return decorator


class TimeoutBudget:
    """Tracks remaining time budget across multiple operations.

    Useful when multiple sequential operations share an overall timeout.

    Usage:
        budget = TimeoutBudget(total=60)
        result1 = step1(timeout=budget.remaining)
        result2 = step2(timeout=budget.remaining)
    """

    def __init__(self, total: float):
        self._total = total
        self._start = time.monotonic()

    @property
    def remaining(self) -> float:
        """Get remaining time budget in seconds."""
        elapsed = time.monotonic() - self._start
        return self._total - elapsed

    @property
    def is_expired(self) -> bool:
        """Check if the time budget is exhausted."""
        return self.remaining <= 0

    def check(self, operation: Optional[str] = None) -> None:
        """Raise OperationTimeoutError if budget is exhausted.

        Args:
            operation: Name of the operation for error message.
        """
        if self.is_expired:
            raise OperationTimeoutError(operation or "operation", self._total)

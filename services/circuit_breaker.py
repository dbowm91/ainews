"""Circuit breaker pattern for external service calls.

States:
- CLOSED: requests flow normally, failures are counted
- OPEN: requests are rejected immediately
- HALF_OPEN: a limited number of requests are allowed through to test recovery
"""

import time
import logging
from enum import Enum
from threading import Lock
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """A circuit breaker that prevents cascading failures.

    When failures exceed a threshold within a time window, the circuit opens
    and rejects requests for a recovery timeout. After the timeout, it allows
    a probe request through (half-open). If the probe succeeds, the circuit
    closes; if it fails, the circuit re-opens.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        window_seconds: float = 120.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.window_seconds = window_seconds

        self._state = State.CLOSED
        self._failure_count = 0
        self._failure_times: list[float] = []
        self._opened_at: float = 0
        self._half_open_calls = 0
        self._lock = Lock()

    @property
    def state(self) -> State:
        with self._lock:
            if self._state == State.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = State.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN")
            return self._state

    def _prune_old_failures(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        self._failure_times = [t for t in self._failure_times if t > cutoff]
        self._failure_count = len(self._failure_times)

    def record_success(self) -> None:
        with self._lock:
            if self._state == State.HALF_OPEN:
                self._state = State.CLOSED
                self._failure_count = 0
                self._failure_times.clear()
                self._half_open_calls = 0
                logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED (recovered)")
            elif self._state == State.CLOSED:
                self._prune_old_failures()

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()

            if self._state == State.HALF_OPEN:
                self._state = State.OPEN
                self._opened_at = now
                self._half_open_calls = 0
                logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (probe failed)")
                return

            self._failure_times.append(now)
            self._prune_old_failures()

            if self._failure_count >= self.failure_threshold:
                self._state = State.OPEN
                self._opened_at = now
                logger.warning(
                    f"Circuit {self.name}: CLOSED -> OPEN "
                    f"({self._failure_count} failures in {self.window_seconds}s)"
                )

    def can_execute(self) -> bool:
        state = self.state
        if state == State.CLOSED:
            return True
        if state == State.OPEN:
            return False
        if state == State.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
        return False

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# Global registry of circuit breakers
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = Lock()


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    **kwargs,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    with _registry_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                **kwargs,
            )
        return _breakers[name]


def get_all_breaker_status() -> list[dict]:
    """Get status of all registered circuit breakers."""
    with _registry_lock:
        return [b.get_status() for b in _breakers.values()]


def circuit_protected(breaker_name: str, fallback: Optional[Callable] = None):
    """Decorator to wrap a function with circuit breaker protection.

    Args:
        breaker_name: Name of the circuit breaker to use
        fallback: Optional fallback function to call when circuit is open
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            breaker = get_breaker(breaker_name)
            if not breaker.can_execute():
                logger.warning(
                    f"Circuit {breaker_name} is {breaker.state.value}, rejecting call"
                )
                if fallback:
                    return fallback(*args, **kwargs)
                raise CircuitOpenError(
                    f"Circuit {breaker_name} is {breaker.state.value}"
                )
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                raise

        return wrapper

    return decorator


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejects a call."""

    pass

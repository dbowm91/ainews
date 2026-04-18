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
from typing import Callable, Optional
from functools import wraps

from services.metrics import get_metrics

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

    def _check_state_transition(self) -> None:
        """Check and perform OPEN -> HALF_OPEN transition if timeout elapsed.

        Must be called while holding ``_lock``.
        """
        if self._state == State.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                old = self._state
                self._state = State.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit %s: OPEN -> HALF_OPEN", self.name)
                self._on_state_change(old, self._state)

    @property
    def state(self) -> State:
        with self._lock:
            self._check_state_transition()
            return self._state

    def _on_state_change(self, old_state: State, new_state: State) -> None:
        try:
            metrics = get_metrics()
            metrics.counter_inc(
                "circuit_breaker.state_change",
                labels={
                    "provider": self.name,
                    "from": old_state.value,
                    "to": new_state.value,
                },
            )
            if new_state == State.OPEN:
                metrics.counter_inc(
                    "circuit_breaker.opened",
                    labels={"provider": self.name},
                )
        except Exception:
            logger.debug("Failed to emit circuit breaker metric", exc_info=True)

    def _prune_old_failures(self) -> None:
        """Remove failure timestamps older than the sliding window.

        Recomputes ``_failure_count`` from the pruned list so that the
        circuit can transition back to CLOSED once enough time has passed.
        Must be called while holding ``_lock``.
        """
        cutoff = time.monotonic() - self.window_seconds
        self._failure_times = [t for t in self._failure_times if t > cutoff]
        self._failure_count = len(self._failure_times)

    def record_success(self) -> None:
        """Record a successful call.

        In CLOSED state the sliding window of failures is pruned (no other
        action is needed — successes don't reduce the failure count while
        inside the window).  In HALF_OPEN state a success transitions the
        circuit back to CLOSED, clearing all failure tracking.
        """
        with self._lock:
            if self._state == State.HALF_OPEN:
                old = self._state
                self._state = State.CLOSED
                self._failure_count = 0
                self._failure_times.clear()
                self._half_open_calls = 0
                logger.info("Circuit %s: HALF_OPEN -> CLOSED (recovered)", self.name)
                self._on_state_change(old, self._state)
            elif self._state == State.CLOSED:
                self._prune_old_failures()

    def record_failure(self) -> None:
        """Record a failed call.

        In HALF_OPEN state any failure immediately re-opens the circuit.  In
        CLOSED state the failure timestamp is appended to the sliding window;
        if the count meets or exceeds ``failure_threshold``, the circuit
        transitions to OPEN.
        """
        with self._lock:
            now = time.monotonic()

            if self._state == State.HALF_OPEN:
                old = self._state
                self._state = State.OPEN
                self._opened_at = now
                self._half_open_calls = 0
                logger.warning(
                    "Circuit %s: HALF_OPEN -> OPEN (probe failed)", self.name
                )
                self._on_state_change(old, self._state)
                return

            self._failure_times.append(now)
            self._prune_old_failures()

            if self._failure_count >= self.failure_threshold:
                old = self._state
                self._state = State.OPEN
                self._opened_at = now
                logger.warning(
                    "Circuit %s: CLOSED -> OPEN (%s failures in %ss)",
                    self.name,
                    self._failure_count,
                    self.window_seconds,
                )
                self._on_state_change(old, self._state)

    def can_execute(self) -> bool:
        """Check whether a call is permitted under the current circuit state.

        In CLOSED state calls always pass.  In OPEN state calls are rejected.
        In HALF_OPEN state a limited number of probe calls (up to
        ``half_open_max_calls``) are allowed through; each call that checks
        this method increments the half-open counter atomically.

        Returns:
            ``True`` if the call may proceed, ``False`` if it should be
            short-circuited.
        """
        with self._lock:
            self._check_state_transition()

            if self._state == State.OPEN:
                return False

            if self._state == State.CLOSED:
                return True
            if self._state == State.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
        return False

    def get_status(self) -> dict:
        """Return a serialisable snapshot of the circuit breaker state.

        Useful for health-check endpoints and admin dashboards.

        Returns:
            Dict with ``name``, ``state``, ``failure_count``,
            ``failure_threshold``, and ``recovery_timeout``.
        """
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
                    "Circuit %s is %s, rejecting call",
                    breaker_name,
                    breaker.state.value,
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

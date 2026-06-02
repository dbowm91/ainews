"""Circuit breaker pattern for external service calls.

States:
- CLOSED: requests flow normally, failures are counted
- OPEN: requests are rejected immediately
- HALF_OPEN: a limited number of requests are allowed through to test recovery
"""

import logging
import time
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Callable, Optional, cast

import os
import redis
from redis.exceptions import RedisError

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
        except (RedisError, ImportError, AttributeError, ValueError, RuntimeError):
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
        """Record a successful call."""
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
        """Record a failed call."""
        with self._lock:
            now = time.monotonic()

            if self._state == State.HALF_OPEN:
                old = self._state
                self._state = State.OPEN
                self._opened_at = now
                self._half_open_calls = 0
                logger.warning(
                    "Circuit %s: HALF_OPEN -> OPEN (probe failed)", self.name,
                )
                self._on_state_change(old, self._state)
                return

            self._failure_times.append(now)
            self._prune_old_failures()

            if self._failure_count >= self.failure_threshold:
                prev_state: State = self._state  # type: ignore[assignment]
                self._state = State.OPEN
                self._opened_at = now
                logger.warning(
                    "Circuit %s: CLOSED -> OPEN (%s failures in %ss)",
                    self.name,
                    self._failure_count,
                    self.window_seconds,
                )
                self._on_state_change(prev_state, self._state)

    def can_execute(self) -> bool:
        """Check whether a call is permitted under the current circuit state."""
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
        """Return a serialisable snapshot of the circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class RedisCircuitBreaker(CircuitBreaker):
    """Distributed circuit breaker backed by Redis.

    Extends CircuitBreaker to store state in Redis for distributed coordination.
    Falls back to in-memory CircuitBreaker if Redis is unavailable
    (fail-closed behavior per AGENTS.md).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        window_seconds: float = 120.0,
        redis_client: Optional["redis.Redis"] = None,
    ):
        super().__init__(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            window_seconds=window_seconds,
        )
        self._key = f"ainews:circuit:{name}"
        self._redis_client = redis_client
        self._local_lock = Lock()

    def _get_redis(self) -> Optional["redis.Redis"]:
        """Get Redis client, initializing from env if needed."""
        if self._redis_client is not None:
            return self._redis_client
        try:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            self._redis_client = redis.from_url(redis_url, decode_responses=True)
            return self._redis_client
        except (RedisError, ImportError, AttributeError, ValueError, RuntimeError):
            logger.debug("Failed to connect to Redis", exc_info=True)
            return None

    def record_success(self) -> None:
        """Record a successful call."""
        r = self._get_redis()
        if r is None:
            super().record_success()
            return
        try:
            key = self._key
            state = r.hget(key, "state")

            if state == "half_open":
                r.hset(key, "state", "closed")
                r.hset(key, "opened_at", "-1")
                r.hset(key, "half_open_calls", "0")
                fail_key = f"{key}:fails"
                r.delete(fail_key)
                logger.info("Circuit %s: HALF_OPEN -> CLOSED (recovered via Redis)", self.name)
                self._on_state_change(State.HALF_OPEN, State.CLOSED)
            else:
                super().record_success()

            self._emit_metric("success")
        except RedisError:
            logger.debug("Redis unavailable, falling back to in-memory", exc_info=True)
            super().record_success()

    def record_failure(self) -> None:
        """Record a failed call."""
        r = self._get_redis()
        if r is None:
            super().record_failure()
            return
        try:
            import uuid
            now = time.monotonic()
            key = self._key

            state = r.hget(key, "state")

            if state == "half_open":
                r.hset(key, "state", "open")
                r.hset(key, "opened_at", str(now))
                r.expire(key, int(self.recovery_timeout * 3))
                logger.warning("Circuit %s: HALF_OPEN -> OPEN (via Redis)", self.name)
                self._on_state_change(State.HALF_OPEN, State.OPEN)
                self._emit_metric("failure")
                return

            fail_key = f"{key}:fails"
            r.zadd(fail_key, {f"{now}:{uuid.uuid4()}": now})
            r.zremrangebyscore(fail_key, "-inf", now - self.window_seconds)
            r.expire(fail_key, int(self.window_seconds * 2))

            count: int = int(r.zcard(fail_key))  # type: ignore[arg-type]
            if count >= self.failure_threshold:
                r.hset(key, "state", "open")
                r.hset(key, "opened_at", str(now))
                r.expire(key, int(self.recovery_timeout * 3))
                logger.warning("Circuit %s: CLOSED -> OPEN (via Redis)", self.name)
                self._on_state_change(State.CLOSED, State.OPEN)

            super().record_failure()
            self._emit_metric("failure")
        except RedisError:
            logger.debug("Redis unavailable, falling back to in-memory", exc_info=True)
            super().record_failure()

    def can_execute(self) -> bool:
        """Check whether a call is permitted."""
        r = self._get_redis()
        if r is None:
            return super().can_execute()
        try:
            now = time.monotonic()
            key = self._key

            state = r.hget(key, "state")
            if state is None:
                return super().can_execute()

            if state == "open":
                opened_at_val = cast("str | None", r.hget(key, "opened_at"))
                if opened_at_val is None:
                    opened_at_val = "-1"
                opened_at = float(opened_at_val)

                if now - opened_at >= self.recovery_timeout:
                    r.hset(key, "state", "half_open")
                    r.hset(key, "half_open_calls", "0")
                else:
                    return False

            if state == "half_open":
                calls_val = cast("str | None", r.hget(key, "half_open_calls"))
                if calls_val is None:
                    calls_val = "0"
                calls = int(calls_val)

                if calls < self.half_open_max_calls:
                    r.hincrby(key, "half_open_calls", 1)
                    return True
                else:
                    return False

            return super().can_execute()
        except RedisError:
            logger.debug("Redis unavailable, falling back to in-memory", exc_info=True)
            return super().can_execute()

    @property
    def state(self) -> State:
        """Return the current circuit state."""
        r = self._get_redis()
        if r is None:
            return super().state
        try:
            state_str = r.hget(self._key, "state")
            if state_str is None:
                return super().state
            return State(state_str)
        except RedisError:
            return super().state

    def _emit_metric(self, outcome: str) -> None:
        """Emit a call outcome metric."""
        try:
            metrics = get_metrics()
            metrics.counter_inc(
                f"circuit_breaker.call.{outcome}",
                labels={"provider": self.name},
            )
        except (RedisError, ImportError, AttributeError, ValueError, RuntimeError):
            logger.debug("Failed to emit circuit breaker metric", exc_info=True)

    def get_status(self) -> dict:
        """Return a serialisable snapshot of the circuit breaker state."""
        r = self._get_redis()
        if r is None:
            status = super().get_status()
            status["backend"] = "memory"
            return status
        try:
            state = r.hget(self._key, "state")
            if state is None:
                state = "closed"
            failure_count = r.zcard(f"{self._key}:fails")
            return {
                "name": self.name,
                "state": state,
                "failure_count": failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "backend": "redis",
            }
        except RedisError:
            status = super().get_status()
            status["backend"] = "memory"
            return status


# Global registry of circuit breakers
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = Lock()


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    **kwargs,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name.

    Uses Redis-backed circuit breaker with in-memory fallback.
    """
    with _registry_lock:
        if name not in _breakers:
            _breakers[name] = RedisCircuitBreaker(
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
                    f"Circuit {breaker_name} is {breaker.state.value}",
                )
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except (RedisError, ImportError, AttributeError, ValueError, RuntimeError):
                breaker.record_failure()
                raise

        return wrapper

    return decorator


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejects a call."""

    pass

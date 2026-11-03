"""Provider-wide concurrency and retry dispatcher for model requests."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar

from services.circuit_breaker import CircuitOpenError
from services.llm.errors import (
    AuthError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitError,
)

if TYPE_CHECKING:
    from services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T")

_TRANSIENT_ERRORS = (
    RateLimitError,
    ProviderTimeoutError,
    ProviderServerError,
    ConnectionError,
    TimeoutError,
)


class ProviderDispatcher:
    """Serialize and retry outbound calls according to provider settings.

    One dispatcher is owned by each cached provider instance. The Redis slot is
    provider scoped, so calls using different models or pipeline stages share
    the same total-concurrency budget.
    """

    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider

    def _acquire(self) -> bool:
        from services.limiter import get_limiter

        return get_limiter().acquire_provider(
            self.provider.provider_id,
            self.provider.max_concurrent,
            timeout=self.provider.dispatcher_wait_timeout_seconds,
            slot_ttl=self.provider.dispatcher_slot_ttl_seconds,
        )

    def _release(self) -> None:
        try:
            from services.limiter import get_limiter

            get_limiter().release_provider(
                self.provider.provider_id,
                timeout=self.provider.dispatcher_slot_ttl_seconds,
            )
        except Exception:
            # The limiter key has a bounded TTL. A Redis outage during release
            # must not mask a successful provider response or its real error.
            logger.exception(
                "Provider %s dispatcher could not release its concurrency slot",
                self.provider.provider_id,
            )

    def _delay(self, error: Exception, attempt: int) -> float:
        base = self.provider.retry_base_delay_seconds
        maximum = self.provider.retry_max_delay_seconds
        retry_after = error.retry_after if isinstance(error, RateLimitError) else None
        if retry_after is not None:
            try:
                return min(maximum, max(base, float(retry_after)))
            except (TypeError, ValueError):
                pass
        ceiling = min(maximum, base * (2**attempt))
        return random.uniform(max(base, ceiling * 0.8), max(base, ceiling))  # noqa: S311 - non-security retry jitter

    def _run_attempt(self, operation: Callable[[], T]) -> T:
        try:
            acquired = self._acquire()
        except Exception as exc:  # noqa: BLE001 - Redis client errors vary by backend
            logger.warning(
                "Provider %s dispatcher could not acquire its concurrency slot",
                self.provider.provider_id,
                exc_info=exc,
            )
            acquired = False
        if not acquired:
            raise ProviderTimeoutError(
                f"Provider {self.provider.provider_id} concurrency wait timed out",
            )
        try:
            return operation()
        finally:
            self._release()

    def call(self, operation: Callable[..., T], model: str | None, *args: Any, **kwargs: Any) -> T:
        """Call a provider operation with bounded transient retries."""
        attempts = self.provider.retry_attempts
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._run_attempt(lambda: operation(*args, **kwargs))
            except (AuthError, CircuitOpenError):
                raise
            except _TRANSIENT_ERRORS as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    self.provider._record_failure(model or self.provider.default_model or "unknown")
                    break
                delay = self._delay(exc, attempt)
                logger.warning(
                    "Provider %s attempt %d/%d failed (%s); retrying in %.1fs",
                    self.provider.provider_id,
                    attempt + 1,
                    attempts,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Provider dispatcher completed without a result")

    def stream(self, operation: Callable[[], Iterator[str]], model: str | None) -> Iterator[str]:
        """Retry a stream only until its first chunk, then yield it intact."""
        attempts = self.provider.retry_attempts
        for attempt in range(attempts):
            try:
                acquired = self._acquire()
            except Exception as exc:  # noqa: BLE001 - Redis client errors vary by backend
                logger.warning(
                    "Provider %s dispatcher could not acquire its concurrency slot",
                    self.provider.provider_id,
                    exc_info=exc,
                )
                acquired = False
            if not acquired:
                error = ProviderTimeoutError(
                    f"Provider {self.provider.provider_id} concurrency wait timed out",
                )
            else:
                try:
                    iterator = operation()
                    first_chunk = next(iterator)
                except StopIteration:
                    self._release()
                    return
                except (AuthError, CircuitOpenError):
                    self._release()
                    raise
                except _TRANSIENT_ERRORS as exc:
                    self._release()
                    error = exc
                except BaseException:
                    self._release()
                    raise
                else:
                    try:
                        yield first_chunk
                        yield from iterator
                    finally:
                        self._release()
                    return

            if attempt + 1 >= attempts:
                self.provider._record_failure(model or self.provider.default_model or "unknown")
                raise error
            delay = self._delay(error, attempt)
            logger.warning(
                "Provider %s stream attempt %d/%d failed (%s); retrying in %.1fs",
                self.provider.provider_id,
                attempt + 1,
                attempts,
                type(error).__name__,
                delay,
            )
            time.sleep(delay)

"""Graceful degradation utilities.

Provides decorators and helpers for implementing fallback behavior
when external services or internal components fail.
"""

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def degrade_on_failure(
    fallback: Callable,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    log_level: str = "warning",
):
    """Decorator that calls a fallback function when the primary fails.

    Args:
        fallback: Function to call if primary fails. Receives same args/kwargs.
        exceptions: Tuple of exception types to catch.
        log_level: Log level for failure messages.

    Usage:
        @degrade_on_failure(fallback=get_cached_articles, exceptions=(SQLAlchemyError,))
        def get_articles_from_db():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                log_fn = getattr(logger, log_level, logger.warning)
                log_fn(
                    "%s failed, using fallback: %s",
                    func.__name__,
                    e,
                    exc_info=True,
                )
                return fallback(*args, **kwargs)

        return wrapper

    return decorator


def fallback_chain(*functions: Callable):
    """Try multiple functions in order, returning the first successful result.

    Raises the last exception if all functions fail.

    Usage:
        result = fallback_chain(
            lambda: fetch_from_primary(),
            lambda: fetch_from_replica(),
            lambda: get_cached_value(),
        )()

    Note: Each function should be a zero-arg callable. Use lambdas to bind args.
    """

    def execute():
        last_exc = None
        for fn in functions:
            try:
                return fn()
            except Exception as e:
                last_exc = e
                logger.debug("Fallback chain: %s failed with %s", fn.__name__, e)
        raise last_exc

    return execute


def safe_default(
    default: Any = None, exceptions: tuple[type[Exception], ...] = (Exception,)
):
    """Decorator that returns a default value on any exception.

    Args:
        default: Value to return on failure.
        exceptions: Tuple of exception types to catch.

    Usage:
        @safe_default(default=[], exceptions=(SQLAlchemyError,))
        def get_tags():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.warning("%s failed, returning default: %s", func.__name__, e)
                return default

        return wrapper

    return decorator

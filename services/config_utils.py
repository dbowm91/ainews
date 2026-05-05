"""Utilities for accessing Flask configuration with sensible defaults."""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_config_with_default(
    key: str,
    default: T,
    converter: Callable[[Any], T] | None = None,
    log_missing: bool = True,
) -> T:
    """Get a configuration value from Flask config with a fallback default.

    This helper avoids repetitive patterns like::
        def _get_foo() -> int:
            try:
                from flask import current_app
                return current_app.config.get("FOO", FOO_DEFAULT)
            except RuntimeError:
                return FOO_DEFAULT

    Args:
        key: Configuration key to look up in ``current_app.config``.
        default: Default value to return when not in config or Flask is
            not active (e.g., in unit tests).
        converter: Optional callable to transform the retrieved value (e.g.,
            ``int`` or ``float``). If the conversion fails, ``default`` is
            returned.
        log_missing: If ``True``, log a warning when the key is not found
            in the config.

    Returns:
        The configuration value, converted, or ``default`` if not found or
        conversion failed.
    """
    try:
        from flask import current_app

        value = current_app.config.get(key)
        if value is None:
            if log_missing:
                logger.warning(
                    "Config key '%s' not found, using default: %s", key, default,
                )
            return default

        if converter is not None:
            try:
                return converter(value)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Config value for '%s' (%r) could not be converted with %s: %s. "
                    "Using default: %s",
                    key,
                    value,
                    converter.__name__,
                    e,
                    default,
                )
                return default

        return cast(T, value)
    except RuntimeError:
        return default

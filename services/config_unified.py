"""Unified configuration access layer.

Provides a single point of access to all application configuration,
abstracting Flask config, environment variables, and YAML configs.
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

from constants import MAX_STAGE_RETRIES, MAX_TOTAL_RETRIES

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 200
STUCK_THRESHOLD_MINUTES = 60
RETRY_SOFT_CUTOFF_MINUTES = 15


def safe_int(key: str, default: int) -> int:
    """Safely parse an environment variable as an integer.

    Returns default if the value is missing or not a valid integer.
    """
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(
            "Invalid integer value for %s: %r, using default %d", key, value, default
        )
        return default


def get_min_content_length() -> int:
    """Get min content length from Flask config or environment."""
    try:
        from flask import current_app

        return current_app.config.get("MIN_CONTENT_LENGTH", MIN_CONTENT_LENGTH)
    except RuntimeError:
        return MIN_CONTENT_LENGTH


def get_stuck_threshold_minutes() -> int:
    """Get stuck threshold from Flask config or environment."""
    try:
        from flask import current_app

        return current_app.config.get(
            "STUCK_THRESHOLD_MINUTES", STUCK_THRESHOLD_MINUTES
        )
    except RuntimeError:
        return STUCK_THRESHOLD_MINUTES


def get_retry_soft_cutoff_minutes() -> int:
    """Get retry soft cutoff from Flask config or environment."""
    try:
        from flask import current_app

        return current_app.config.get(
            "RETRY_SOFT_CUTOFF_MINUTES", RETRY_SOFT_CUTOFF_MINUTES
        )
    except RuntimeError:
        return RETRY_SOFT_CUTOFF_MINUTES


@dataclass
class PipelineConfig:
    """Pipeline-related configuration."""

    max_stage_retries: int = MAX_STAGE_RETRIES
    max_total_retries: int = MAX_TOTAL_RETRIES
    stuck_threshold_minutes: int = 60
    min_content_length: int = 200


@dataclass
class SecurityConfig:
    """Security-related configuration."""

    session_cookie_secure: bool = False
    session_cookie_httponly: bool = True
    session_cookie_samesite: str = "Lax"
    max_content_length: int = 64 * 1024
    verification_expiry_seconds: int = 3600


@dataclass
class SourceConfig:
    """Source health configuration."""

    max_consecutive_failures: int = 10


@dataclass
class AppConfig:
    """Unified application configuration.

    Aggregates configuration from Flask config and environment variables
    into a single typed object with sensible defaults.
    """

    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    sources: SourceConfig = field(default_factory=SourceConfig)

    @classmethod
    def from_flask(cls) -> "AppConfig":
        """Build config from current Flask app context.

        Falls back to environment variables and defaults outside Flask context.
        """
        try:
            from flask import current_app

            cfg = current_app.config
            return cls(
                pipeline=PipelineConfig(
                    max_stage_retries=cfg.get("MAX_STAGE_RETRIES", 3),
                    max_total_retries=cfg.get("MAX_TOTAL_RETRIES", 10),
                    stuck_threshold_minutes=cfg.get("STUCK_THRESHOLD_MINUTES", 60),
                    min_content_length=cfg.get("MIN_CONTENT_LENGTH", 200),
                ),
                security=SecurityConfig(
                    session_cookie_secure=cfg.get("SESSION_COOKIE_SECURE", False),
                    session_cookie_httponly=cfg.get("SESSION_COOKIE_HTTPONLY", True),
                    session_cookie_samesite=cfg.get("SESSION_COOKIE_SAMESITE", "Lax"),
                    max_content_length=cfg.get("MAX_CONTENT_LENGTH", 64 * 1024),
                    verification_expiry_seconds=cfg.get(
                        "VERIFICATION_EXPIRY_SECONDS", 3600
                    ),
                ),
                sources=SourceConfig(
                    max_consecutive_failures=cfg.get("MAX_CONSECUTIVE_FAILURES", 10),
                ),
            )
        except RuntimeError:
            return cls.from_env()

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build config from environment variables only (no Flask context)."""
        return cls(
            pipeline=PipelineConfig(
                max_stage_retries=safe_int("MAX_STAGE_RETRIES", 3),
                max_total_retries=safe_int("MAX_TOTAL_RETRIES", 10),
                stuck_threshold_minutes=safe_int("STUCK_THRESHOLD_MINUTES", 60),
                min_content_length=safe_int("MIN_CONTENT_LENGTH", 200),
            ),
            security=SecurityConfig(
                session_cookie_secure=os.environ.get("SESSION_COOKIE_SECURE", "false")
                .lower()
                .startswith("t"),
                max_content_length=safe_int("MAX_CONTENT_LENGTH", 64 * 1024),
                verification_expiry_seconds=safe_int(
                    "VERIFICATION_EXPIRY_SECONDS", 3600
                ),
            ),
            sources=SourceConfig(
                max_consecutive_failures=safe_int("MAX_CONSECUTIVE_FAILURES", 10),
            ),
        )


_instance: Optional[AppConfig] = None
_config_lock = threading.Lock()


def get_config() -> AppConfig:
    """Get the unified app config (cached singleton)."""
    global _instance
    if _instance is not None:
        return _instance
    with _config_lock:
        if _instance is not None:
            return _instance
        _instance = AppConfig.from_flask()
        return _instance


def reset_config() -> None:
    """Reset cached config (for testing)."""
    global _instance
    with _config_lock:
        _instance = None


def validate_config() -> tuple[bool, list[str]]:
    """Validate current configuration.

    Returns:
        (is_valid, errors) tuple. errors is empty if valid.
    """
    errors = []

    try:
        from schemas.pipeline import load_pipeline_config

        load_pipeline_config()
    except Exception as e:
        errors.append(f"Pipeline config error: {e}")

    try:
        from schemas.topic import load_topics

        load_topics()
    except Exception as e:
        errors.append(f"Topic config error: {e}")

    try:
        from schemas.source import load_sources

        load_sources()
    except Exception as e:
        errors.append(f"Source config error: {e}")

    try:
        from schemas.llm import load_providers_config

        load_providers_config()
    except Exception as e:
        errors.append(f"LLM providers config error: {e}")

    return (len(errors) == 0, errors)

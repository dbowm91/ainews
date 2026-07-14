from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from schemas.common import ProviderDef
    from schemas.llm import LLMProvidersConfig

from celery.schedules import crontab
from dotenv import load_dotenv

from constants import (
    MAX_STAGE_RETRIES as _DEFAULT_STAGE_RETRIES,
)
from constants import (
    MAX_TOTAL_RETRIES as _DEFAULT_TOTAL_RETRIES,
)
from constants import (
    PIPELINE_TIMEOUT_SECONDS as _DEFAULT_PIPELINE_TIMEOUT_SECONDS,
)
from schemas.pipeline import PipelineRootConfig
from services.config_unified import safe_int

load_dotenv()

BASE_DIR = Path(__file__).parent


@dataclass
class ConfigValidationIssue:
    """A single configuration validation issue."""

    field: str
    message: str
    fix_hint: str = ""
    severity: str = "error"  # "error" | "warning"


@dataclass
class ConfigValidationResult:
    """Collects validation issues from production config checks."""

    issues: list[ConfigValidationIssue] = field(default_factory=list)

    def add(
        self,
        field: str,
        message: str,
        fix_hint: str = "",
        severity: str = "error",
    ) -> None:
        self.issues.append(
            ConfigValidationIssue(
                field=field,
                message=message,
                fix_hint=fix_hint,
                severity=severity,
            )
        )

    @property
    def errors(self) -> list[ConfigValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ConfigValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def raise_on_errors(self) -> None:
        """Raise RuntimeError if any error-severity issues exist.

        Includes all error messages and fix hints in the exception so
        operators see every problem at once instead of fixing one at a time.
        """
        if not self.has_errors:
            return
        lines: list[str] = []
        for issue in self.errors:
            line = f"  - {issue.field}: {issue.message}"
            if issue.fix_hint:
                line += f"\n    Fix: {issue.fix_hint}"
            lines.append(line)
        raise RuntimeError(
            "Production config validation failed:\n" + "\n".join(lines)
        )


def _is_strong_secret_key(key: str) -> bool:
    """Check if SECRET_KEY is a valid 64-character hex string (32 bytes)."""
    if not key or not isinstance(key, str):
        return False
    if len(key) != 64:
        return False
    try:
        int(key, 16)
        return True
    except ValueError:
        return False


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SECRET_KEY_FALLBACKS = [
        os.environ.get("SECRET_KEY_PREVIOUS_1", ""),
        os.environ.get("SECRET_KEY_PREVIOUS_2", ""),
    ]
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year for static assets

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # overridden in ProductionConfig
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_PATH = "/"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Celery task security
    CELERY_TASK_SECRET = os.environ.get("CELERY_TASK_SECRET", "")

    # Request size limits
    MAX_CONTENT_LENGTH = 64 * 1024  # 64KB

    # Pipeline retry limits
    MAX_STAGE_RETRIES = safe_int("MAX_STAGE_RETRIES", _DEFAULT_STAGE_RETRIES)
    MAX_TOTAL_RETRIES = safe_int("MAX_TOTAL_RETRIES", _DEFAULT_TOTAL_RETRIES)
    PIPELINE_TIMEOUT_SECONDS = safe_int(
        "PIPELINE_TIMEOUT_SECONDS", _DEFAULT_PIPELINE_TIMEOUT_SECONDS
    )
    MAX_CONSECUTIVE_FAILURES = safe_int("MAX_CONSECUTIVE_FAILURES", 10)
    STUCK_THRESHOLD_MINUTES = safe_int("STUCK_THRESHOLD_MINUTES", 60)
    RETRY_SOFT_CUTOFF_MINUTES = safe_int("RETRY_SOFT_CUTOFF_MINUTES", 15)
    # Safe fetch client
    SAFE_FETCH_MAX_REDIRECTS = safe_int("SAFE_FETCH_MAX_REDIRECTS", 5)
    SAFE_FETCH_MAX_BYTES = safe_int("SAFE_FETCH_MAX_BYTES", 2_000_000)
    SAFE_FETCH_CONNECT_TIMEOUT = safe_int("SAFE_FETCH_CONNECT_TIMEOUT", 5)
    SAFE_FETCH_READ_TIMEOUT = safe_int("SAFE_FETCH_READ_TIMEOUT", 10)
    SAFE_FETCH_TOTAL_TIMEOUT = safe_int("SAFE_FETCH_TOTAL_TIMEOUT", 20)

    DNS_CACHE_TTL = safe_int("DNS_CACHE_TTL", 300)
    DNS_CACHE_MAX = safe_int("DNS_CACHE_MAX", 1024)
    L1_CACHE_MAXSIZE = safe_int("L1_CACHE_MAXSIZE", 1000)
    LOGIN_MAX_ATTEMPTS = safe_int("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_LOCKOUT_SECONDS = safe_int("LOGIN_LOCKOUT_SECONDS", 900)
    MIN_CONTENT_LENGTH = safe_int("MIN_CONTENT_LENGTH", 200)
    VERIFICATION_EXPIRY_SECONDS = safe_int("VERIFICATION_EXPIRY_SECONDS", 3600)

    THEMES_ENABLED = os.environ.get("THEMES_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    THEMES_CUSTOM_DIR = os.environ.get("THEMES_CUSTOM_DIR", "")
    THEMES_ALLOW_CUSTOM = os.environ.get("THEMES_ALLOW_CUSTOM", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    THEMES_DEFAULT = os.environ.get("THEMES_DEFAULT", "")
    THEMES_DEFAULT_DARK = os.environ.get("THEMES_DEFAULT_DARK", "catppuccin-mocha")
    THEMES_DEFAULT_LIGHT = os.environ.get("THEMES_DEFAULT_LIGHT", "catppuccin-latte")
    THEMES_MAX_FILE_BYTES = safe_int("THEMES_MAX_FILE_BYTES", 256 * 1024)
    THEMES_STRICT_CONTRAST = os.environ.get(
        "THEMES_STRICT_CONTRAST", "false"
    ).lower() in ("1", "true", "yes", "on")

    # Database query logging
    DB_QUERY_LOG_LEVEL = os.environ.get("DB_QUERY_LOG_LEVEL", "WARNING").upper()

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    # SMTP
    SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
    SMTP_PORT = safe_int("SMTP_PORT", 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@ainews.dev")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_POOL_SIZE = safe_int("SMTP_POOL_SIZE", 5)

    # Celery
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
    )
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_TIMEZONE = "UTC"
    CELERY_ENABLE_UTC = True
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_ACKS_LATE = True
    CELERY_TASK_REJECT_ON_WORKER_LOST = True
    CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
    CELERY_RESULT_EXPIRES = timedelta(hours=24)
    CELERY_TASK_SEND_SENT_EVENT = True
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_BROKER_CONNECTION_RETRY = True
    CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

    # DEPRECATED: Use get_beat_schedule() instead. Actual schedule is loaded from pipeline.yaml.
    CELERY_BEAT_SCHEDULE: dict[str, Any] = {}

    @classmethod
    def get_beat_schedule(cls, pipeline_cfg: PipelineRootConfig | None = None) -> dict:
        """Build beat schedule from pipeline.yaml config.

        Args:
            pipeline_cfg: Optional pipeline config object from pipeline.yaml.
                         If None, reads from file.

        Returns:
            Beat schedule dict compatible with Celery beat.
        """
        if pipeline_cfg is None:
            from schemas.pipeline import load_pipeline_config

            pipeline_cfg = load_pipeline_config()

        sched = pipeline_cfg.schedule
        crawl_interval = int(sched.get("crawl_interval_minutes", 30))
        retry_interval = int(sched.get("retry_stuck_interval_minutes", 60))
        cleanup_logs_hour = int(sched.get("cleanup_old_logs_hour", 3))
        cleanup_versions_hour = int(sched.get("cleanup_old_versions_hour", 3))
        cleanup_expired_interval = int(sched.get("cleanup_expired_verifications_interval_minutes", 15))
        publish_interval = int(sched.get("publish_scheduled_interval_minutes", 5))
        cleanup_limiter_interval = int(sched.get("cleanup_stale_limiter_interval_minutes", 5))
        newsletters_hour = int(sched.get("generate_newsletters_hour", 8))
        trend_memory_hour = int(sched.get("consolidate_trend_memory_hour", 3))
        cleanup_subscribers_hour = int(sched.get("cleanup_inactive_subscribers_hour", 1))
        cleanup_subscribers_minute = int(sched.get("cleanup_inactive_subscribers_minute", 0))

        return {
            "run-all-sources": {
                "task": "tasks.crawl.run_all_sources",
                "schedule": timedelta(minutes=crawl_interval),
            },
            "retry-stuck-articles": {
                "task": "tasks.retry.retry_stuck",
                "schedule": timedelta(minutes=retry_interval),
            },
            "generate-newsletters": {
                "task": "tasks.newsletter.generate_daily_newsletters",
                "schedule": crontab(hour=newsletters_hour, minute=0),
            },
            "cleanup-old-logs": {
                "task": "tasks.cleanup.cleanup_old_pipeline_logs",
                "schedule": crontab(hour=cleanup_logs_hour, minute=0),
            },
            "consolidate-trend-memory": {
                "task": "tasks.cleanup.consolidate_trend_memory",
                "schedule": crontab(hour=trend_memory_hour, minute=30),
            },
            "purge-trend-memory": {
                "task": "tasks.cleanup.purge_trend_memory",
                "schedule": crontab(hour=trend_memory_hour, minute=45),
            },
            "cleanup-old-versions": {
                "task": "tasks.cleanup.cleanup_old_article_versions",
                "schedule": crontab(hour=cleanup_versions_hour, minute=45),
            },
            "cleanup-expired-verifications": {
                "task": "tasks.cleanup.cleanup_expired_verifications",
                "schedule": timedelta(minutes=cleanup_expired_interval),
            },
            "publish-scheduled-articles": {
                "task": "tasks.scheduler.publish_scheduled_articles",
                "schedule": timedelta(minutes=publish_interval),
            },
            "cleanup-stale-limiter-slots": {
                "task": "tasks.cleanup.cleanup_stale_limiter_slots",
                "schedule": timedelta(minutes=cleanup_limiter_interval),
            },
            "retry-failed-newsletter-deliveries": {
                "task": "tasks.newsletter.retry_failed_newsletter_deliveries",
                "schedule": timedelta(hours=2),
            },
            "recalculate-impact-scores": {
                "task": "tasks.cleanup.recalculate_impact_scores",
                "schedule": crontab(hour=4, minute=0),
            },
            "cleanup-inactive-subscribers": {
                "task": "tasks.subscribers.cleanup_inactive_subscribers",
                "schedule": crontab(hour=cleanup_subscribers_hour, minute=cleanup_subscribers_minute),
            },
            "backfill-embeddings": {
                "task": "tasks.embeddings.backfill_embeddings",
                "schedule": crontab(hour=2, minute=0),
            },
        }

    @classmethod
    def reload_beat_schedule(cls, celery_app) -> dict:
        """Reload beat schedule from pipeline.yaml and update Celery beat.

        Args:
            celery_app: The Celery app instance.

        Returns:
            The new beat schedule dict.
        """
        from schemas.pipeline import load_pipeline_config

        pipeline_cfg: PipelineRootConfig = load_pipeline_config()
        new_schedule = cls.get_beat_schedule(pipeline_cfg)
        celery_app.conf.beat_schedule = new_schedule
        return new_schedule


class DevelopmentConfig(Config):
    DEBUG = True
    _secret_key_val: str | None = os.environ.get("SECRET_KEY")
    if _secret_key_val is None:
        raise RuntimeError("SECRET_KEY environment variable must be set")
    if _secret_key_val == "dev-secret-key-change-me":
        raise RuntimeError("SECRET_KEY must be changed from default value")
    SECRET_KEY: str = _secret_key_val
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"


class TestingConfig(DevelopmentConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'prod.db'}"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 15},
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

    @classmethod
    def validate(cls) -> ConfigValidationResult:
        """Validate all production requirements.

        Returns:
            ConfigValidationResult with collected issues.

        Raises:
            RuntimeError: If any error-severity issues are found.
        """
        result = ConfigValidationResult()
        _validate_debug(result)
        _validate_session_security(result)
        _validate_secrets(result)
        _validate_llm_providers(result)
        _validate_docker_ollama_host(result)
        _validate_safe_fetch(result)
        _validate_themes(result)
        result.raise_on_errors()
        return result


def _validate_debug(result: ConfigValidationResult) -> None:
    """Check DEBUG is disabled in production."""
    if ProductionConfig.DEBUG:
        result.add(
            field="DEBUG",
            message="DEBUG must be False in production",
            fix_hint="Set DEBUG=False in your environment or remove it entirely",
        )


def _validate_session_security(result: ConfigValidationResult) -> None:
    """Check session cookie security settings."""
    if not ProductionConfig.SESSION_COOKIE_SECURE:
        result.add(
            field="SESSION_COOKIE_SECURE",
            message="SESSION_COOKIE_SECURE must be True in production",
            fix_hint="Set SESSION_COOKIE_SECURE=true in your .env file",
        )


def _validate_secrets(result: ConfigValidationResult) -> None:
    """Validate SECRET_KEY, ADMIN_PASSWORD, and CELERY_TASK_SECRET."""
    # SECRET_KEY
    sk = ProductionConfig.SECRET_KEY
    if not sk:
        result.add(
            field="SECRET_KEY",
            message="SECRET_KEY must be set in production",
            fix_hint="Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"",
        )
    elif len(sk) < 32:
        result.add(
            field="SECRET_KEY",
            message=f"SECRET_KEY is {len(sk)} characters; must be at least 32",
            fix_hint="Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"",
        )
    elif not _is_strong_secret_key(sk):
        result.add(
            field="SECRET_KEY",
            message="SECRET_KEY must be a 64-character hex string (32 bytes)",
            fix_hint="Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"",
        )

    # ADMIN_PASSWORD
    pw = ProductionConfig.ADMIN_PASSWORD
    if not pw:
        result.add(
            field="ADMIN_PASSWORD",
            message="ADMIN_PASSWORD must be set in production",
            fix_hint="Run: python scripts/hash_password.py",
        )
    else:
        from services.validation import _is_password_hash

        if not _is_password_hash(pw):
            result.add(
                field="ADMIN_PASSWORD",
                message="ADMIN_PASSWORD must be a hashed password (scrypt/pbkdf2/argon2)",
                fix_hint="Run: python scripts/hash_password.py",
            )

    # CELERY_TASK_SECRET
    cs = ProductionConfig.CELERY_TASK_SECRET
    if not cs:
        result.add(
            field="CELERY_TASK_SECRET",
            message="CELERY_TASK_SECRET must be set in production",
            fix_hint="Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"",
        )
    elif len(cs) < 32:
        result.add(
            field="CELERY_TASK_SECRET",
            message=f"CELERY_TASK_SECRET is {len(cs)} characters; must be at least 32",
            fix_hint="Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"",
        )


def _validate_provider_type(
    result: ConfigValidationResult,
    pdef: ProviderDef,
    provider_type: str,
    adapter_configs: dict,
) -> bool:
    """Check provider type is known. Returns True if valid."""
    if provider_type in adapter_configs:
        return True
    known_types = ", ".join(sorted(adapter_configs.keys()))
    result.add(
        field=f"providers.{pdef.id}.type",
        message=(
            f"Provider '{pdef.id}' has unknown type '{provider_type}'. "
            f"Known types: {known_types}"
        ),
        fix_hint=(
            f"Set type to one of: {known_types}. "
            "Use 'openai' for OpenAI-compatible providers"
        ),
    )
    return False


def _validate_provider_config(
    result: ConfigValidationResult,
    pdef: ProviderDef,
    provider_type: str,
    adapter_configs: dict,
) -> bool:
    """Validate provider config with Pydantic schema. Returns True if valid."""
    config_cls = adapter_configs[provider_type]
    try:
        config_cls(**pdef.config)
    except ValueError as e:
        error_str = str(e)
        if "api_key" in error_str and "required" in error_str.lower():
            result.add(
                field=f"providers.{pdef.id}.config.api_key",
                message=(
                    f"Provider '{pdef.id}' ({provider_type}) is missing "
                    "required field 'api_key'"
                ),
                fix_hint=(
                    f"Set api_key in providers.yaml or via env var "
                    f"(e.g., ${{UPPERCASE_PROVIDER_ID}}_API_KEY)"
                ),
            )
        elif "model" in error_str and "required" in error_str.lower():
            result.add(
                field=f"providers.{pdef.id}.config.model",
                message=(
                    f"Provider '{pdef.id}' ({provider_type}) is missing "
                    "required field 'model'"
                ),
                fix_hint="Set 'model' in providers.yaml for this provider",
            )
        else:
            result.add(
                field=f"providers.{pdef.id}.config",
                message=(
                    f"Provider '{pdef.id}' ({provider_type}) config "
                    f"validation failed: {error_str}"
                ),
                fix_hint="Check providers.yaml and environment variables",
            )
        return False
    return True


def _validate_cloud_api_key(
    result: ConfigValidationResult,
    pdef: ProviderDef,
    provider_type: str,
) -> None:
    """Check cloud provider api_key env var is set."""
    from schemas.common import resolve_env_var

    api_key = pdef.config.get("api_key", "")
    if api_key.startswith("${"):
        resolved_key = resolve_env_var(api_key)
        if not resolved_key:
            result.add(
                field=f"providers.{pdef.id}.config.api_key",
                message=(
                    f"Provider '{pdef.id}' ({provider_type}) api_key "
                    f"env var {api_key} is not set"
                ),
                fix_hint=(
                    f"Set {api_key} in your environment or update "
                    "providers.yaml"
                ),
            )


def _validate_default_provider(
    result: ConfigValidationResult,
    config: LLMProvidersConfig,
    all_provider_ids: list[str],
    provider_by_id: dict[str, ProviderDef],
    enabled_providers: list[str],
    valid_provider_ids: set[str] | None = None,
) -> None:
    """Validate default_provider exists, is enabled, and is valid."""
    if valid_provider_ids is None:
        valid_provider_ids = set()

    if not config or not config.default_provider:
        if not enabled_providers:
            return  # Already reported "no providers enabled"
        result.add(
            field="default_provider",
            message="default_provider is not set",
            fix_hint="Set default_provider in providers.yaml",
        )
        return

    dp = config.default_provider
    if dp not in all_provider_ids:
        result.add(
            field="default_provider",
            message=(
                f"default_provider '{dp}' does not exist in providers list. "
                f"Available: {', '.join(all_provider_ids) or '(none)'}"
            ),
            fix_hint=(
                f"Set default_provider to one of: "
                f"{', '.join(all_provider_ids) or '(none)'}"
            ),
        )
    else:
        dp_def = provider_by_id[dp]
        if not getattr(dp_def, "enabled", False):
            result.add(
                field="default_provider",
                message=(
                    f"default_provider '{dp}' exists but is disabled. "
                    "A pipeline cannot use a disabled provider as default"
                ),
                fix_hint=(
                    f"Enable '{dp}' in providers.yaml or set "
                    "default_provider to an enabled provider"
                ),
            )
        elif valid_provider_ids is not None and dp not in valid_provider_ids:
            result.add(
                field="default_provider",
                message=(
                    f"default_provider '{dp}' is enabled but has invalid "
                    "configuration (e.g., missing api_key or model)"
                ),
                fix_hint=(
                    f"Fix the configuration for '{dp}' in providers.yaml "
                    "or set default_provider to a valid provider"
                ),
            )


def _detect_docker_environment() -> bool:
    """Detect if running inside a Docker container."""
    # Explicit env var (set in Dockerfile/Compose)
    if os.environ.get("AINEWS_RUNNING_IN_DOCKER") == "1":
        return True
    # Standard Docker indicator file
    if Path("/.dockerenv").exists():
        return True
    # Check cgroup for Docker/containerd
    try:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            text = cgroup.read_text()
            if "docker" in text or "containerd" in text:
                return True
    except (OSError, PermissionError):
        pass
    return False


def _validate_docker_ollama_host(result: ConfigValidationResult) -> None:
    """Warn when Ollama uses localhost inside Docker containers.

    Inside a Docker container, localhost refers to the container itself,
    not the host machine. The LLM pipeline will fail at call time if
    Ollama is running on the host but the provider points to localhost.
    """
    if not _detect_docker_environment():
        return

    try:
        from schemas.llm import load_providers_config

        config = load_providers_config()
        for pdef in config.providers:
            if not pdef.enabled or pdef.type != "ollama":
                continue
            host = pdef.config.get("host", "http://localhost:11434")
            if "localhost" in host or "127.0.0.1" in host:
                result.add(
                    field=f"providers.{pdef.id}.config.host",
                    message=(
                        f"Ollama provider '{pdef.id}' host is '{host}' "
                        "but the app appears to be running inside Docker. "
                        "localhost inside a container refers to the container "
                        "itself, not the host machine."
                    ),
                    fix_hint=(
                        "Use 'http://ollama:11434' if Ollama runs as a Compose "
                        "service (see docker-compose.ollama.yml), or "
                        "'http://host.docker.internal:11434' if Ollama runs "
                        "on the host machine."
                    ),
                    severity="warning",
                )
    except Exception:  # noqa: BLE001
        pass  # Don't fail startup on Docker detection issues


def _parse_env_int_for_validation(
    result: ConfigValidationResult,
    name: str,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Parse an int env var for production validation, reporting issues via result."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (ValueError, TypeError):
        result.add(
            field=name,
            message=f"{name} must be an integer, got {raw!r}",
            fix_hint=f"Set {name} to a valid integer (default: {default})",
        )
        return default
    if min_value is not None and value < min_value:
        result.add(
            field=name,
            message=f"{name} must be >= {min_value}, got {value}",
            fix_hint=f"Set {name} to {min_value} or higher (default: {default})",
        )
    if max_value is not None and value > max_value:
        result.add(
            field=name,
            message=f"{name} must be <= {max_value}, got {value}",
            fix_hint=f"Set {name} to {max_value} or lower (default: {default})",
        )
    return value


def _parse_env_float_for_validation(
    result: ConfigValidationResult,
    name: str,
    default: float,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    """Parse a float env var for production validation, reporting issues via result."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (ValueError, TypeError):
        result.add(
            field=name,
            message=f"{name} must be a number, got {raw!r}",
            fix_hint=f"Set {name} to a valid number (default: {default})",
        )
        return default
    if min_value is not None and value < min_value:
        result.add(
            field=name,
            message=f"{name} must be >= {min_value}, got {value}",
            fix_hint=f"Set {name} to {min_value} or higher (default: {default})",
        )
    if max_value is not None and value > max_value:
        result.add(
            field=name,
            message=f"{name} must be <= {max_value}, got {value}",
            fix_hint=f"Set {name} to {max_value} or lower (default: {default})",
        )
    return value


def _validate_safe_fetch(result: ConfigValidationResult) -> None:
    """Validate safe-fetch configuration values."""
    max_redirects = _parse_env_int_for_validation(
        result, "SAFE_FETCH_MAX_REDIRECTS", 5, min_value=1
    )
    max_bytes = _parse_env_int_for_validation(
        result, "SAFE_FETCH_MAX_BYTES", 2_000_000, min_value=1, max_value=10_000_000
    )
    connect_timeout = _parse_env_float_for_validation(
        result, "SAFE_FETCH_CONNECT_TIMEOUT", 5.0, min_value=0.1, max_value=30
    )
    read_timeout = _parse_env_float_for_validation(
        result, "SAFE_FETCH_READ_TIMEOUT", 10.0, min_value=0.1, max_value=60
    )
    total_timeout = _parse_env_float_for_validation(
        result, "SAFE_FETCH_TOTAL_TIMEOUT", 20.0, min_value=0.1
    )

    if total_timeout < connect_timeout + read_timeout:
        result.add(
            field="SAFE_FETCH_TOTAL_TIMEOUT",
            message=(
                f"SAFE_FETCH_TOTAL_TIMEOUT ({total_timeout}) must be >= "
                f"connect + read ({connect_timeout} + {read_timeout})"
            ),
            fix_hint=f"Set SAFE_FETCH_TOTAL_TIMEOUT >= {connect_timeout + read_timeout}",
        )


def _validate_llm_providers(result: ConfigValidationResult) -> None:
    """Validate LLM provider configuration at startup.

    In production, missing/invalid provider config is an error that prevents
    startup. All exceptions from provider loading are surfaced as validation
    issues rather than silently logged warnings.

    Validates:
    - Provider type is known (in ADAPTER_CONFIGS)
    - Enabled providers have valid config for their type
    - Cloud providers have api_key set
    - Ollama providers have model set
    - default_provider is set, exists in providers, is enabled, and passes validation
    """
    import logging

    logger = logging.getLogger(__name__)
    enabled_providers: list[str] = []
    all_provider_ids: list[str] = []
    provider_by_id: dict[str, ProviderDef] = {}
    valid_provider_ids: set[str] = set()
    config = None

    try:
        from schemas.llm import ADAPTER_CONFIGS, load_providers_config

        config = load_providers_config()

        for pdef in config.providers:
            all_provider_ids.append(pdef.id)
            provider_by_id[pdef.id] = pdef

        for pdef in config.providers:
            if not pdef.enabled:
                continue
            enabled_providers.append(pdef.id)
            provider_type = pdef.type

            if not _validate_provider_type(result, pdef, provider_type, ADAPTER_CONFIGS):
                continue

            if not _validate_provider_config(result, pdef, provider_type, ADAPTER_CONFIGS):
                continue

            if provider_type in ("openai", "anthropic", "gemini"):
                _validate_cloud_api_key(result, pdef, provider_type)

            valid_provider_ids.add(pdef.id)

    except FileNotFoundError as e:
        result.add(
            field="providers.yaml",
            message=f"LLM providers config file not found: {e}",
            fix_hint="Create providers.yaml or set LLM_PROVIDERS_FILE env var",
        )
    except Exception as e:
        logger.exception("Unexpected error loading LLM provider config")
        result.add(
            field="providers.yaml",
            message=f"Failed to load LLM provider config: {e}",
            fix_hint="Check providers.yaml syntax and environment variables",
        )

    if not enabled_providers:
        result.add(
            field="providers",
            message="No LLM providers enabled",
            fix_hint="Enable at least one provider in providers.yaml",
        )

    if config is not None:
        _validate_default_provider(
            result, config, all_provider_ids, provider_by_id, enabled_providers,
            valid_provider_ids=valid_provider_ids,
        )


def _validate_themes(result: ConfigValidationResult) -> None:
    """Validate theme subsystem configuration values.

    Reads env vars at call time so tests can patch them with ``monkeypatch``.
    The theme registry will fall back through configured defaults to the
    emergency theme at runtime, so missing/wrong default IDs are non-fatal
    warnings rather than production-startup-blockers. The byte limit must be
    parseable so malformed input surfaces immediately.
    """
    enabled_raw = os.environ.get("THEMES_ENABLED", "true").lower()
    if enabled_raw not in ("1", "true", "yes", "on"):
        return

    raw = os.environ.get("THEMES_MAX_FILE_BYTES")
    if raw is not None:
        try:
            value = int(raw)
            if value < 1024:
                result.add(
                    field="THEMES_MAX_FILE_BYTES",
                    message=(
                        f"THEMES_MAX_FILE_BYTES must be >= 1024, got {value}"
                    ),
                    fix_hint="Set THEMES_MAX_FILE_BYTES to 1024 or higher",
                )
            elif value > 1024 * 1024:
                result.add(
                    field="THEMES_MAX_FILE_BYTES",
                    message=(
                        f"THEMES_MAX_FILE_BYTES must be <= 1048576, got {value}"
                    ),
                    fix_hint="Set THEMES_MAX_FILE_BYTES to 1048576 or lower",
                )
        except ValueError:
            result.add(
                field="THEMES_MAX_FILE_BYTES",
                message=(
                    f"THEMES_MAX_FILE_BYTES must be an integer, got {raw!r}"
                ),
                fix_hint="Set THEMES_MAX_FILE_BYTES to a valid integer (default: 262144)",
            )

    custom_dir = os.environ.get("THEMES_CUSTOM_DIR", "").strip()
    allow_custom_raw = os.environ.get("THEMES_ALLOW_CUSTOM", "true").lower()
    allow_custom = allow_custom_raw in ("1", "true", "yes", "on")
    if custom_dir and not allow_custom:
        result.add(
            field="THEMES_ALLOW_CUSTOM",
            message=(
                "THEMES_CUSTOM_DIR is set but THEMES_ALLOW_CUSTOM is false; "
                "the custom directory will be ignored"
            ),
            fix_hint=(
                "Set THEMES_ALLOW_CUSTOM=true to load themes from the "
                "configured directory"
            ),
            severity="warning",
        )


def _flatten_pipeline_config(effective: Any) -> dict[str, Any]:
    """Extract pipeline config keys into flat dict for Flask app.config."""
    flat: dict[str, Any] = {}
    pipeline_section = effective.pipeline.get("pipeline", {})
    if not isinstance(pipeline_section, dict):
        return flat
    for role in ("selector", "researcher", "writer", "editor"):
        role_cfg = pipeline_section.get(role, {})
        if not isinstance(role_cfg, dict):
            continue
        prefix = role.upper()
        for rk, rv in role_cfg.items():
            flat[f"{prefix}_{rk.upper()}"] = rv
    schedule = effective.pipeline.get("schedule", {})
    if isinstance(schedule, dict):
        for sk, sv in schedule.items():
            flat[f"SCHEDULE_{sk.upper()}"] = sv
    newsletter = effective.pipeline.get("newsletter", {})
    if isinstance(newsletter, dict):
        for nk, nv in newsletter.items():
            flat[f"NEWSLETTER_{nk.upper()}"] = nv
    return flat


def _log_loader_diagnostics(diagnostics: list, logger: Any) -> None:
    """Log shared loader diagnostics at appropriate levels."""
    relevant = [d for d in diagnostics if d.severity in ("error", "warning")]
    if not relevant:
        return
    error_count = sum(1 for d in relevant if d.severity == "error")
    warning_count = sum(1 for d in relevant if d.severity == "warning")
    logger.info(
        "Shared loader diagnostics: %d issues (%d errors, %d warnings)",
        len(relevant),
        error_count,
        warning_count,
    )
    for d in relevant:
        if d.severity == "error":
            logger.warning("[%s] %s", d.code, d.message)
        else:
            logger.info("[%s] %s", d.code, d.message)


def load_from_shared_loader() -> dict[str, Any]:
    """Load configuration via the shared ainews_config loader.

    Compatibility wrapper that bridges the shared config system with Flask's
    app.config dict. Existing code paths continue to work unchanged; this
    function provides an additional configuration source that can be used
    alongside or instead of the legacy config classes.

    Returns:
        Dict suitable for ``app.config.update()``. Returns empty dict on
        failure so that existing behavior is never broken.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        from ainews_config.loader import load_config_for_app
    except ImportError:
        logger.debug("ainews_config not available, skipping shared loader")
        return {}

    try:
        effective = load_config_for_app()
    except Exception:
        logger.exception("Shared config loader failed")
        return {}

    flat: dict[str, Any] = dict(effective.environment)
    flat.update(_flatten_pipeline_config(effective))
    _log_loader_diagnostics(effective.diagnostics, logger)

    return flat


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

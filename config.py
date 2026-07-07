import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

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
    DNS_CACHE_TTL = safe_int("DNS_CACHE_TTL", 300)
    DNS_CACHE_MAX = safe_int("DNS_CACHE_MAX", 1024)
    L1_CACHE_MAXSIZE = safe_int("L1_CACHE_MAXSIZE", 1000)
    LOGIN_MAX_ATTEMPTS = safe_int("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_LOCKOUT_SECONDS = safe_int("LOGIN_LOCKOUT_SECONDS", 900)
    MIN_CONTENT_LENGTH = safe_int("MIN_CONTENT_LENGTH", 200)
    VERIFICATION_EXPIRY_SECONDS = safe_int("VERIFICATION_EXPIRY_SECONDS", 3600)

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


def _validate_llm_providers(result: ConfigValidationResult) -> None:
    """Validate LLM provider configuration at startup.

    In production, missing/invalid provider config is an error that prevents
    startup. All exceptions from provider loading are surfaced as validation
    issues rather than silently logged warnings.
    """
    import logging

    logger = logging.getLogger(__name__)
    enabled_providers: list[str] = []

    try:
        from schemas.common import resolve_env_var
        from schemas.llm import ADAPTER_CONFIGS, load_providers_config

        config = load_providers_config()

        for pdef in config.providers:
            if not pdef.enabled:
                continue
            enabled_providers.append(pdef.id)
            provider_type = pdef.type

            # Check required api_key for cloud providers
            if provider_type in ("openai", "anthropic", "gemini"):
                api_key = pdef.config.get("api_key", "")
                missing_key = not api_key or (
                    api_key.startswith("${") and not resolve_env_var(api_key)
                )
                if missing_key:
                    result.add(
                        field=f"providers.{pdef.id}.api_key",
                        message=f"Provider '{pdef.id}' ({provider_type}) is missing api_key",
                        fix_hint=f"Set {api_key} in your environment or update providers.yaml",
                    )
                    continue

            # Check required model for ollama
            if provider_type == "ollama" and not pdef.config.get("model"):
                result.add(
                    field=f"providers.{pdef.id}.model",
                    message=f"Provider '{pdef.id}' (ollama) is missing model",
                    fix_hint="Set 'model' in providers.yaml for this provider",
                )
                continue

            # Validate the provider config with Pydantic schema
            config_cls = ADAPTER_CONFIGS.get(provider_type)
            if config_cls:
                try:
                    config_cls(**pdef.config)
                except ValueError as e:
                    result.add(
                        field=f"providers.{pdef.id}.config",
                        message=f"Provider '{pdef.id}' config invalid: {e}",
                        fix_hint="Check providers.yaml and environment variables",
                    )

    except FileNotFoundError as e:
        result.add(
            field="providers.yaml",
            message=f"LLM providers config file not found: {e}",
            fix_hint="Create providers.yaml or set LLM_PROVIDERS_FILE env var",
        )
    except Exception as e:
        # Catch-all for unexpected errors during config loading.
        # Log full traceback for debugging but surface a clean message.
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


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

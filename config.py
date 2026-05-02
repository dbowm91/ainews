import os
from datetime import timedelta
from pathlib import Path

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
from services.config_unified import safe_int

load_dotenv()

BASE_DIR = Path(__file__).parent


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
    CELERY_BEAT_SCHEDULE = {}

    @classmethod
    def get_beat_schedule(cls, pipeline_cfg: dict | None = None) -> dict:
        """Build beat schedule from pipeline.yaml config.

        Args:
            pipeline_cfg: Optional pipeline config dict from pipeline.yaml.
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

        pipeline_cfg = load_pipeline_config()
        new_schedule = cls.get_beat_schedule(pipeline_cfg)
        celery_app.conf.beat_schedule = new_schedule
        return new_schedule


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if SECRET_KEY is None:
        raise RuntimeError("SECRET_KEY environment variable must be set")
    if SECRET_KEY == "dev-secret-key-change-me":
        raise RuntimeError("SECRET_KEY must be changed from default value")
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
    def validate(cls):
        if cls.DEBUG:
            raise RuntimeError("DEBUG must be False in production")
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set in production")
        if len(cls.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters")
        if not _is_strong_secret_key(cls.SECRET_KEY):
            raise ValueError("SECRET_KEY must be a 64-character hex string (32 bytes)")
        if not cls.SESSION_COOKIE_SECURE:
            raise RuntimeError("SESSION_COOKIE_SECURE must be True in production")
        if not cls.ADMIN_PASSWORD:
            raise RuntimeError("ADMIN_PASSWORD must be set in production")
        from services.validation import _is_password_hash

        if not _is_password_hash(cls.ADMIN_PASSWORD):
            raise RuntimeError(
                "ADMIN_PASSWORD must be a hashed password. "
                "Run: python scripts/hash_password.py"
            )
        if not cls.CELERY_TASK_SECRET:
            raise RuntimeError("CELERY_TASK_SECRET must be set in production")
        if len(cls.CELERY_TASK_SECRET) < 32:
            raise RuntimeError("CELERY_TASK_SECRET must be at least 32 characters")
        _validate_llm_providers()


def _validate_llm_providers():
    """Validate LLM provider configuration at startup.

    Raises RuntimeError if enabled providers are missing required config.
    """
    import logging

    logger = logging.getLogger(__name__)
    enabled_providers = []
    try:
        from schemas.common import resolve_env_var
        from schemas.llm import load_providers_config

        config = load_providers_config()
        for pdef in config.providers:
            if not pdef.enabled:
                continue
            enabled_providers.append(pdef.id)
            # Check for required config based on provider type
            provider_type = pdef.type
            if provider_type in ("openai", "anthropic", "gemini"):
                api_key = pdef.config.get("api_key", "")
                if not api_key or api_key.startswith("${") and not resolve_env_var(api_key):
                    raise RuntimeError(f"Provider '{pdef.id}': missing api_key")
            if provider_type == "ollama" and not pdef.config.get("model"):
                raise RuntimeError(f"Provider '{pdef.id}': missing model")
            # Validate the provider config with Pydantic (includes field validators)
            from schemas.llm import ADAPTER_CONFIGS
            config_cls = ADAPTER_CONFIGS.get(provider_type)
            if config_cls:
                config_cls(**pdef.config)
    except (ImportError, RuntimeError, KeyError, ValueError) as e:
        logger.warning("Could not validate LLM providers: %s", e)

    if not enabled_providers:
        raise RuntimeError(
            "No LLM providers enabled. Configure at least one in providers.yaml"
        )


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

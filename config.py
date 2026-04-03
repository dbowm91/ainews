import logging
import os
from pathlib import Path
from datetime import timedelta
from celery.schedules import crontab
from constants import (
    MAX_STAGE_RETRIES as _DEFAULT_STAGE_RETRIES,
    MAX_TOTAL_RETRIES as _DEFAULT_TOTAL_RETRIES,
)
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


def _safe_int(env_var, default):
    """Parse an environment variable as int with fallback on failure."""
    try:
        return int(os.environ.get(env_var, default))
    except (ValueError, TypeError):
        logging.getLogger(__name__).warning(
            "Invalid %s value '%s', using default %s",
            env_var,
            os.environ.get(env_var),
            default,
        )
        return int(default)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year for static assets

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # overridden in ProductionConfig
    SESSION_COOKIE_PATH = "/"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Request size limits
    MAX_CONTENT_LENGTH = 64 * 1024  # 64KB

    # Pipeline retry limits
    MAX_STAGE_RETRIES = _safe_int("MAX_STAGE_RETRIES", str(_DEFAULT_STAGE_RETRIES))
    MAX_TOTAL_RETRIES = _safe_int("MAX_TOTAL_RETRIES", str(_DEFAULT_TOTAL_RETRIES))

    # Source health
    MAX_CONSECUTIVE_FAILURES = _safe_int("MAX_CONSECUTIVE_FAILURES", "10")

    # Dead-letter threshold
    STUCK_THRESHOLD_MINUTES = _safe_int("STUCK_THRESHOLD_MINUTES", "60")

    # Soft cutoff for retry stuck (minutes)
    RETRY_SOFT_CUTOFF_MINUTES = _safe_int("RETRY_SOFT_CUTOFF_MINUTES", "15")

    # DNS cache (SSRF prevention)
    DNS_CACHE_TTL = _safe_int("DNS_CACHE_TTL", "300")
    DNS_CACHE_MAX = _safe_int("DNS_CACHE_MAX", "1024")

    # L1 cache size (ResponseCache in-memory layer)
    L1_CACHE_MAXSIZE = _safe_int("L1_CACHE_MAXSIZE", "1000")

    # Login lockout
    LOGIN_MAX_ATTEMPTS = _safe_int("LOGIN_MAX_ATTEMPTS", "5")
    LOGIN_LOCKOUT_SECONDS = _safe_int("LOGIN_LOCKOUT_SECONDS", "900")

    # Content extraction
    MIN_CONTENT_LENGTH = _safe_int("MIN_CONTENT_LENGTH", "200")

    # Email verification
    VERIFICATION_EXPIRY_SECONDS = _safe_int("VERIFICATION_EXPIRY_SECONDS", "3600")

    # Database query logging
    DB_QUERY_LOG_LEVEL = os.environ.get("DB_QUERY_LOG_LEVEL", "WARNING").upper()

    # SMTP
    SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
    SMTP_PORT = _safe_int("SMTP_PORT", "587")
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@ainews.dev")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

    # Celery
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
    )
    CELERY_ACCEPT_CONTENT = ["json"]
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

    CELERY_BEAT_SCHEDULE = {
        "run-all-sources": {
            "task": "tasks.crawl.run_all_sources",
            "schedule": timedelta(minutes=30),
        },
        "retry-stuck-articles": {
            "task": "tasks.retry.retry_stuck",
            "schedule": timedelta(minutes=60),
        },
        "generate-newsletters": {
            "task": "tasks.newsletter.generate_daily_newsletters",
            "schedule": crontab(hour=8, minute=0),
        },
        "cleanup-old-logs": {
            "task": "tasks.cleanup.cleanup_old_pipeline_logs",
            "schedule": crontab(hour=3, minute=0),
        },
        "cleanup-expired-verifications": {
            "task": "tasks.cleanup.cleanup_expired_verifications",
            "schedule": timedelta(minutes=15),
        },
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"

    def __init__(self):
        super().__init__()
        logger = logging.getLogger(__name__)
        if not self.ADMIN_PASSWORD:
            logger.warning("ADMIN_PASSWORD not set - admin login disabled")
        if self.SECRET_KEY == "dev-secret-key-change-me":
            logger.warning(
                "SECRET_KEY is using default value 'dev-secret-key-change-me' — "
                "sessions are insecure. Set SECRET_KEY env var for production."
            )


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
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

    @classmethod
    def validate(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set in production")
        if not cls.ADMIN_PASSWORD:
            raise RuntimeError("ADMIN_PASSWORD must be set in production")
        from services.validation import _is_password_hash

        if not _is_password_hash(cls.ADMIN_PASSWORD):
            raise RuntimeError(
                "ADMIN_PASSWORD must be a hashed password. "
                "Run: python scripts/hash_password.py"
            )
        _validate_llm_providers()


def _validate_llm_providers():
    """Validate LLM provider configuration at startup.

    Raises RuntimeError if enabled providers are missing required config.
    """
    import logging

    logger = logging.getLogger(__name__)
    enabled_providers = []
    try:
        from schemas.llm import load_providers_config

        config = load_providers_config()
        for pdef in config.providers:
            if not pdef.enabled:
                continue
            enabled_providers.append(pdef.id)
            if pdef.type == "openai" and not pdef.config.get("api_key"):
                raise RuntimeError(f"Provider '{pdef.id}': missing api_key")
            elif pdef.type == "anthropic" and not pdef.config.get("api_key"):
                raise RuntimeError(f"Provider '{pdef.id}': missing api_key")
            elif pdef.type == "ollama" and not pdef.config.get("model"):
                raise RuntimeError(f"Provider '{pdef.id}': missing model")
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

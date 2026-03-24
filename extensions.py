import os
import logging

from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

logger = logging.getLogger(__name__)

db = SQLAlchemy()
limiter = Limiter(get_remote_address, default_limits=["200 per minute"])
csrf = CSRFProtect()
migrate = Migrate()

_redis_client = None


def get_redis():
    """Return a singleton Redis client.

    Reads the connection URL from CELERY_BROKER_URL env var.
    Works in both Flask request contexts and Celery task contexts.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    import redis

    url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    _redis_client = redis.from_url(url)
    return _redis_client


def reset_redis():
    """Reset the cached Redis client (for testing)."""
    global _redis_client
    _redis_client = None

import os
import logging
import threading

from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

logger = logging.getLogger(__name__)

db = SQLAlchemy()
csrf = CSRFProtect()
migrate = Migrate()


def _get_limiter_storage_uri() -> str:
    """Get Redis storage URI for rate limiting.

    Uses a separate Redis DB (15) to avoid conflicting with Celery's broker.
    Falls back to in-memory if Redis is unavailable.
    """
    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    # Parse broker URL and use DB 15 for rate limiting
    if "://" in broker_url:
        base = broker_url.rsplit("/", 1)[0]
        return f"{base}/15"
    return "memory://"


limiter = Limiter(
    get_remote_address,
    storage_uri=_get_limiter_storage_uri(),
    default_limits=["200 per minute"],
)

_redis_client = None
_redis_pool = None
_redis_lock = threading.Lock()


def get_redis():
    """Return a singleton Redis client backed by a shared connection pool.

    Reads the connection URL from CELERY_BROKER_URL env var.
    Works in both Flask request contexts and Celery task contexts.
    Thread-safe via locking on first initialization.
    """
    global _redis_client, _redis_pool
    if _redis_client is not None:
        return _redis_client

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client

        import redis

        url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        _redis_pool = redis.ConnectionPool.from_url(url, max_connections=20)
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        return _redis_client


def reset_redis():
    """Reset the cached Redis client (for testing)."""
    global _redis_client, _redis_pool
    with _redis_lock:
        if _redis_pool is not None:
            _redis_pool.disconnect()
        _redis_client = None
        _redis_pool = None

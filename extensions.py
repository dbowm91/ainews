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
    from urllib.parse import urlparse, urlunparse

    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    if "://" in broker_url:
        parsed = urlparse(broker_url)
        new_parsed = parsed._replace(path="/15")
        return urlunparse(new_parsed)
    return "memory://"


_limiter: Limiter | None = None
_limiter_lock = threading.Lock()


def get_limiter_flask() -> Limiter:
    """Get or create the singleton Flask Limiter instance."""
    global _limiter
    if _limiter is not None:
        return _limiter
    with _limiter_lock:
        if _limiter is not None:
            return _limiter
        _limiter = Limiter(
            get_remote_address,
            storage_uri=_get_limiter_storage_uri(),
            default_limits=[os.environ.get("RATELIMIT_DEFAULT", "60 per minute")],
        )
        return _limiter


def reset_limiter() -> None:
    """Reset the limiter singleton (for testing)."""
    global _limiter
    with _limiter_lock:
        _limiter = None


limiter = get_limiter_flask()

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
        from urllib.parse import urlparse, urlunparse

        url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")

        # Add Redis password if REDIS_PASSWORD env var is set
        redis_password = os.environ.get("REDIS_PASSWORD")
        if redis_password:
            parsed = urlparse(url)
            if not parsed.password:
                # Reconstruct URL with password
                netloc = f":{redis_password}@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                url = urlunparse((
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                ))

        _redis_pool = redis.ConnectionPool.from_url(
            url,
            max_connections=100,
            socket_timeout=5,
            socket_connect_timeout=3,
            socket_keepalive=True,
        )
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

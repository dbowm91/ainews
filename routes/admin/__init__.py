import logging
import threading
import time

import redis.exceptions
from flask import Blueprint

from services.validation import _is_password_hash

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/api/v1")


def verify_api_token(token_str):
    """Verify an API token and return True if valid.

    Uses constant-time comparison via services.api_tokens. Does not leak
    whether the prefix exists — returns False on any failure.
    """
    from datetime import datetime, timezone

    from extensions import db
    from models import ApiToken
    from services.api_tokens import parse_api_token, verify_api_token_secret

    parsed = parse_api_token(token_str)
    if parsed is None:
        return False

    prefix, secret = parsed

    api_token = ApiToken.query.filter(ApiToken.token_prefix == prefix).first()
    if api_token is None:
        return False

    if api_token.revoked_at is not None:
        return False

    if api_token.expires_at is not None and api_token.expires_at < datetime.now(timezone.utc):
        return False

    if not verify_api_token_secret(api_token.token_hash, secret):
        return False

    api_token.last_used_at = datetime.now(timezone.utc)
    db.session.commit()
    return True


from routes.decorators import require_auth  # noqa: F401, E402

# Login attempt lockout
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes
_LOGIN_ATTEMPT_PREFIX = "ainews:login_attempts:"


def _get_login_max_attempts() -> int:
    """Get max login attempts from Flask config, falling back to default."""
    from services.config_utils import get_config_with_default

    return get_config_with_default("LOGIN_MAX_ATTEMPTS", _LOGIN_MAX_ATTEMPTS)


def _get_login_lockout_seconds() -> int:
    """Get login lockout seconds from Flask config, falling back to default."""
    from services.config_utils import get_config_with_default

    return get_config_with_default("LOGIN_LOCKOUT_SECONDS", _LOGIN_LOCKOUT_SECONDS)


# In-memory fallback when Redis is unavailable (per-worker protection)
_login_attempts_memory: dict[str, tuple[int, float]] = {}
_memory_lock = threading.Lock()
_MAX_MEMORY_ENTRIES = 1000


def _cleanup_stale_entries() -> None:
    """Remove expired entries from memory to prevent unbounded growth."""
    with _memory_lock:
        now = time.monotonic()
        stale_keys = []
        for ip, (_count, first_time) in _login_attempts_memory.items():
            if now - first_time >= _get_login_lockout_seconds():
                stale_keys.append(ip)

        for ip in stale_keys:
            del _login_attempts_memory[ip]

        if len(_login_attempts_memory) > _MAX_MEMORY_ENTRIES:
            sorted_entries = sorted(
                _login_attempts_memory.items(),
                key=lambda x: x[1][1],
                reverse=True,
            )
            _login_attempts_memory.clear()
            for ip, entry in sorted_entries[:_MAX_MEMORY_ENTRIES]:
                _login_attempts_memory[ip] = entry


_LOCKOUT_LUA_SCRIPT = """
local count = redis.call('HINCRBY', KEYS[1], 'count', 1)
redis.call('HSETNX', KEYS[1], 'first_attempt', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])

if count >= tonumber(ARGV[3]) then
    return 1
end
return 0
"""


def _get_redis():
    """Get Redis client for login attempt tracking."""
    from extensions import get_redis

    return get_redis()


def _verify_password(stored: str, provided: str) -> bool:
    """Verify a password against a stored hash."""
    if not stored:
        return False
    if _is_password_hash(stored):
        from werkzeug.security import check_password_hash

        return check_password_hash(stored, provided)
    logger.error(
        "ADMIN_PASSWORD is not a valid hash. "
        "Run 'python scripts/hash_password.py' and update your .env file.",
    )
    return False


def _admin_categories():
    """Get category names from pipeline config, with fallback."""
    from services.utils import get_admin_categories

    return get_admin_categories()


def _is_locked_out(ip: str) -> bool:
    """Check if an IP is locked out due to too many failed login attempts.

    Uses Redis for multi-worker safety. Falls back to in-memory tracking
    when Redis is unavailable (provides per-worker protection).
    """
    try:
        r = _get_redis()
        key = f"{_LOGIN_ATTEMPT_PREFIX}{ip}"
        data = r.hgetall(key)
        if not data:
            return False
        count = int(data.get(b"count", 0))
        return count >= _get_login_max_attempts()
    except redis.exceptions.RedisError as e:
        logger.warning("Redis error checking lockout for %s: %s", ip, e)
        # Fallback to in-memory tracking
        return _is_locked_out_memory(ip)


def _is_locked_out_memory(ip: str) -> bool:
    """In-memory fallback for lockout check."""
    _cleanup_stale_entries()  # Periodic cleanup
    with _memory_lock:
        entry = _login_attempts_memory.get(ip)
        if entry is None:
            return False
        count, first_time = entry
        if time.monotonic() - first_time >= _get_login_lockout_seconds():
            del _login_attempts_memory[ip]
            return False
        return count >= _get_login_max_attempts()


def _check_and_record_attempt(ip: str) -> bool:
    """Atomically check if locked out AND record a failed attempt.

    Returns True if locked out (attempt was recorded but threshold exceeded).
    Uses Redis Lua script for atomicity — eliminates TOCTOU race condition
    between separate check and record calls.
    Falls back to in-memory tracking when Redis is unavailable.
    """
    try:
        r = _get_redis()
        key = f"{_LOGIN_ATTEMPT_PREFIX}{ip}"
        result = r.eval(
            _LOCKOUT_LUA_SCRIPT,
            1,
            key,
            str(time.time()),
            str(_get_login_lockout_seconds()),
            str(_get_login_max_attempts()),
        )
        is_locked: bool = result == 1
        return is_locked
    except redis.exceptions.RedisError as e:
        logger.warning("Redis error in check_and_record for %s: %s", ip, e)
        _record_failed_attempt_memory(ip)
        return _is_locked_out_memory(ip)


def _record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for an IP in Redis.

    Uses a pipeline for atomic operations. HINCRBY and HSETNX run
    inside the pipeline to avoid race conditions on concurrent requests.
    Falls back to in-memory tracking when Redis is unavailable.
    """
    try:
        r = _get_redis()
        key = f"{_LOGIN_ATTEMPT_PREFIX}{ip}"

        pipe = r.pipeline()
        pipe.hincrby(key, "count", 1)
        pipe.hsetnx(key, "first_attempt", str(time.time()))
        pipe.expire(key, _get_login_lockout_seconds())
        pipe.execute()
    except redis.exceptions.RedisError as e:
        logger.warning("Redis error recording attempt for %s: %s", ip, e)
        _record_failed_attempt_memory(ip)


def _record_failed_attempt_memory(ip: str) -> None:
    """In-memory fallback for recording failed attempts."""
    _cleanup_stale_entries()  # Periodic cleanup
    with _memory_lock:
        now = time.monotonic()
        entry = _login_attempts_memory.get(ip)
        if entry is None:
            _login_attempts_memory[ip] = (1, now)
        else:
            count, first_time = entry
            if now - first_time >= _get_login_lockout_seconds():
                _login_attempts_memory[ip] = (1, now)
            else:
                _login_attempts_memory[ip] = (count + 1, first_time)


def _clear_attempts(ip: str) -> None:
    """Clear failed login attempts for an IP after successful login.

    Clears both Redis and in-memory fallback.
    """
    try:
        r = _get_redis()
        r.delete(f"{_LOGIN_ATTEMPT_PREFIX}{ip}")
    except redis.exceptions.RedisError as e:
        logger.warning("Redis error clearing attempts for %s: %s", ip, e)
    # Always clear in-memory fallback (used when Redis is unavailable)
    with _memory_lock:
        _login_attempts_memory.pop(ip, None)


# Import all sub-modules to register routes with the blueprint
# These must come after Blueprint creation to avoid circular imports
from routes.admin import (  # noqa: E402
    api as api,
)
from routes.admin import (  # noqa: E402
    api_tokens as api_tokens,
)
from routes.admin import (  # noqa: E402
    articles as articles,
)
from routes.admin import (  # noqa: E402
    auth as auth,
)
from routes.admin import (  # noqa: E402
    dashboard as dashboard,
)
from routes.admin import (  # noqa: E402
    metrics as metrics,
)
from routes.admin import (  # noqa: E402
    newsletters as newsletters,
)
from routes.admin import (  # noqa: E402
    pipelines as pipelines,
)
from routes.admin import (  # noqa: E402
    review as review,
)
from routes.admin import (  # noqa: E402
    shares as shares,
)
from routes.admin import (  # noqa: E402
    sources as sources,
)
from routes.admin import (  # noqa: E402
    subscribers as subscribers,
)
from routes.admin import (  # noqa: E402
    topic_notes as topic_notes,
)
from routes.admin import (  # noqa: E402
    trend_memory as trend_memory,
)
from routes.admin import (  # noqa: E402
    webhooks as webhooks,
)

from functools import wraps
import logging
import os
import re
import time
import redis.exceptions
from flask import Blueprint, redirect, url_for, session, request
from logging_config import get_request_id

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Login attempt lockout
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes
_LOGIN_ATTEMPT_PREFIX = "ainews:login_attempts:"

# In-memory fallback when Redis is unavailable (per-worker protection)
_login_attempts_memory: dict[str, tuple[int, float]] = {}
_memory_lock = __import__("threading").Lock()
_MAX_MEMORY_ENTRIES = 1000


def _cleanup_stale_entries() -> None:
    """Remove expired entries from memory to prevent unbounded growth."""
    with _memory_lock:
        now = time.monotonic()
        stale_keys = []
        for ip, (count, first_time) in _login_attempts_memory.items():
            if now - first_time >= _LOGIN_LOCKOUT_SECONDS:
                stale_keys.append(ip)

        for ip in stale_keys:
            del _login_attempts_memory[ip]

        # If still too many entries, remove oldest
        if len(_login_attempts_memory) > _MAX_MEMORY_ENTRIES:
            # Sort by first_time and keep newest
            sorted_entries = sorted(
                _login_attempts_memory.items(),
                key=lambda x: x[1][1],  # first_time
                reverse=True,
            )
            _login_attempts_memory.clear()
            for ip, entry in sorted_entries[:_MAX_MEMORY_ENTRIES]:
                _login_attempts_memory[ip] = entry


# Load Lua script for atomic login lockout
_LUA_SCRIPT = None


def _get_lockout_lua_script():
    """Load the login lockout Lua script (cached after first load)."""
    global _LUA_SCRIPT
    if _LUA_SCRIPT is None:
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "services", "login_lockout.lua"
        )
        with open(script_path) as f:
            _LUA_SCRIPT = f.read()
    return _LUA_SCRIPT


def _get_redis():
    """Get Redis client for login attempt tracking."""
    from extensions import get_redis

    return get_redis()


def _is_password_hash(value: str) -> bool:
    """Check if a value is a Werkzeug password hash (scrypt:, pbkdf2:, or argon2:)."""
    return bool(re.match(r"^(scrypt|pbkdf2|argon2):", value))


def _verify_password(stored: str, provided: str) -> bool:
    """Verify a password against a stored hash."""
    if not stored:
        return False
    if _is_password_hash(stored):
        from werkzeug.security import check_password_hash

        return check_password_hash(stored, provided)
    logger.error(
        "ADMIN_PASSWORD is not a valid hash. "
        "Run 'python scripts/hash_password.py' and update your .env file."
    )
    return False


def _admin_categories():
    """Get category names from pipeline config, with fallback."""
    try:
        from schemas.topic import load_topics

        return list(load_topics().topics.keys())
    except Exception:
        return ["ai", "privacy", "security", "programming", "hardware"]


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
        return count >= _LOGIN_MAX_ATTEMPTS
    except redis.exceptions.RedisError as e:
        logger.warning(f"Redis error checking lockout for {ip}: {e}")
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
        if time.monotonic() - first_time >= _LOGIN_LOCKOUT_SECONDS:
            del _login_attempts_memory[ip]
            return False
        return count >= _LOGIN_MAX_ATTEMPTS


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
            _get_lockout_lua_script(),
            1,
            key,
            str(time.time()),
            str(_LOGIN_LOCKOUT_SECONDS),
            str(_LOGIN_MAX_ATTEMPTS),
        )
        return result == 1
    except redis.exceptions.RedisError as e:
        logger.warning(f"Redis error in check_and_record for {ip}: {e}")
        # Fallback: record in memory and check
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
        pipe.expire(key, _LOGIN_LOCKOUT_SECONDS)
        pipe.execute()
    except redis.exceptions.RedisError as e:
        logger.warning(f"Redis error recording attempt for {ip}: {e}")
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
            if now - first_time >= _LOGIN_LOCKOUT_SECONDS:
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
        logger.warning(f"Redis error clearing attempts for {ip}: {e}")
    # Always clear in-memory fallback (used when Redis is unavailable)
    with _memory_lock:
        _login_attempts_memory.pop(ip, None)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login"))
        # Log admin access with context
        request_id = get_request_id()
        logger.info(
            f"Admin access: {request.method} {request.path}",
            extra={
                "user": "admin",
                "ip": request.remote_addr,
                "request_id": request_id,
                "admin": True,
            },
        )
        return f(*args, **kwargs)

    return decorated


# Import all sub-modules to register routes with the blueprint
from routes.admin import (  # noqa: E402, F401
    auth as auth,
    dashboard as dashboard,
    pipelines as pipelines,
    articles as articles,
    review as review,
    newsletters as newsletters,
    subscribers as subscribers,
    metrics as metrics,
    shares as shares,
    sources as sources,
    api as api,
)

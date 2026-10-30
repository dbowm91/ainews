"""Separate read-only agent credentials and fail-closed fixed-hour quotas."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from flask import current_app, jsonify, request
from sqlalchemy import select
from redis.exceptions import RedisError

from extensions import db, get_redis
from models import AgentAccessConfig, AgentCredential


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def get_policy() -> dict[str, int | bool]:
    stored = db.session.get(AgentAccessConfig, 1)
    return {
        "api_enabled": bool(stored.public_api_enabled) if stored else bool(current_app.config.get("PUBLIC_API_ENABLED", False)),
        "mcp_enabled": bool(stored.public_mcp_enabled) if stored else bool(current_app.config.get("PUBLIC_MCP_ENABLED", False)),
        "anonymous_enabled": bool(stored.anonymous_enabled) if stored else bool(current_app.config.get("PUBLIC_ANONYMOUS_ENABLED", False)),
        "requests_per_hour": int(stored.requests_per_hour) if stored else int(current_app.config.get("PUBLIC_AGENT_REQUESTS_PER_HOUR", 600)),
        "anonymous_requests_per_hour": int(stored.anonymous_requests_per_hour) if stored else int(current_app.config.get("PUBLIC_ANONYMOUS_REQUESTS_PER_HOUR", 120)),
    }


def _quota(identity: str, limit: int) -> tuple[bool, int, int]:
    """Atomic fixed-hour quota plus a smaller per-minute burst ceiling."""
    redis = get_redis()
    now = datetime.now(timezone.utc)
    bucket = int(now.timestamp()) // 3600
    hour_key = f"ainews:public-api:quota:{identity}:{bucket}"
    minute_key = f"ainews:public-api:burst:{identity}:{int(now.timestamp()) // 60}"
    burst_limit = max(5, min(60, (limit + 9) // 10))
    pipe = redis.pipeline()
    pipe.incr(hour_key)
    pipe.expire(hour_key, 3700)
    pipe.incr(minute_key)
    pipe.expire(minute_key, 70)
    hour_count, _hour_expiry, minute_count, _minute_expiry = map(int, pipe.execute())
    if hour_count > limit:
        retry_after = 3600 - int(now.timestamp()) % 3600
    elif minute_count > burst_limit:
        retry_after = 60 - now.second
    else:
        retry_after = 0
    return hour_count <= limit and minute_count <= burst_limit, max(0, min(limit - hour_count, burst_limit - minute_count)), retry_after


def admit_bearer(bearer: str) -> tuple[bool, int, str, int, int]:
    """Validate a reader key and consume the same fixed-hour budget as REST."""
    policy = get_policy()
    if not policy["api_enabled"] and not policy["mcp_enabled"]:
        return False, 404, "disabled", 0, 0
    if not bearer.startswith("agent_") or "." not in bearer:
        return False, 401, "unauthorized", 0, 0
    public_id, secret = bearer[6:].split(".", 1)
    credential = db.session.scalar(select(AgentCredential).where(AgentCredential.public_id == public_id))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if (credential is None or not credential.enabled or credential.revoked_at is not None
            or (credential.expires_at is not None and credential.expires_at <= now)
            or not secrets.compare_digest(credential.secret_hash, _digest(secret))
            or "public.read" not in (credential.scopes or [])):
        return False, 401, "unauthorized", 0, 0
    limit = credential.requests_per_hour or int(policy["requests_per_hour"])
    try:
        allowed, remaining, retry_after = _quota(f"key:{credential.public_id}", limit)
        if allowed:
            global_allowed, global_remaining, global_retry = _quota("global", int(current_app.config.get("PUBLIC_GLOBAL_REQUESTS_PER_HOUR", 60000)))
            allowed = global_allowed
            remaining = min(remaining, global_remaining)
            retry_after = global_retry
    except RedisError:
        return False, 503, "quota_unavailable", 0, 0
    if not allowed:
        return False, 429, "rate_limited", 0, retry_after
    credential.last_used_at = now
    db.session.commit()
    return True, 200, "ok", remaining, 0


def admit_request():
    policy = get_policy()
    if not policy["api_enabled"]:
        return jsonify({"error": {"code": "disabled", "message": "Public API is disabled"}}), 404
    authorization = request.headers.get("Authorization", "")
    bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    if authorization and not bearer.startswith("agent_"):
        return jsonify({"error": {"code": "unauthorized", "message": "A valid reader credential is required"}}), 401
    identity = "anonymous"
    limit = int(policy["anonymous_requests_per_hour"])
    if bearer.startswith("agent_"):
        allowed, code, message, remaining, retry_after = admit_bearer(bearer)
        if not allowed:
            response = jsonify({"error": {"code": message, "message": "Reader access denied"}})
            response.status_code = code
            if code == 429:
                response.headers["Retry-After"] = str(retry_after)
            return response
        request.agent_quota_remaining = remaining
        return None
    elif not policy["anonymous_enabled"]:
        return jsonify({"error": {"code": "unauthorized", "message": "A reader credential is required"}}), 401
    else:
        # Deliberately use REMOTE_ADDR only; untrusted forwarded headers are ignored.
        identity = f"ip:{request.remote_addr or 'unknown'}"
    try:
        allowed, remaining, retry_after = _quota(identity, limit)
        if allowed:
            global_allowed, global_remaining, global_retry = _quota("global", int(current_app.config.get("PUBLIC_GLOBAL_REQUESTS_PER_HOUR", 60000)))
            allowed = global_allowed
            remaining = min(remaining, global_remaining)
            retry_after = global_retry
    except RedisError:
        return jsonify({"error": {"code": "quota_unavailable", "message": "Request quota is temporarily unavailable"}}), 503
    if not allowed:
        response = jsonify({"error": {"code": "rate_limited", "message": "Hourly request limit reached"}})
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        response.headers["X-RateLimit-Remaining"] = "0"
        return response
    request.agent_quota_remaining = remaining
    return None


def create_credential(label: str, *, expires_at=None, requests_per_hour=None) -> tuple[AgentCredential, str]:
    public_id = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")[:16]
    secret = secrets.token_urlsafe(32)
    credential = AgentCredential(public_id=public_id, secret_hash=_digest(secret), label=label.strip()[:120],
        scopes=["public.read"], expires_at=expires_at, requests_per_hour=requests_per_hour)
    db.session.add(credential)
    db.session.commit()
    return credential, f"agent_{public_id}.{secret}"

"""Shared helpers for route handlers."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal

from flask import Response, g, jsonify, redirect, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError
from wtforms.validators import ValidationError

from logging_config import get_request_id

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Result of authentication check."""

    ok: bool
    mode: Literal["session", "bearer"] | None = None
    response: Response | tuple[Response, int] | None = None


def authenticate_request():
    """Check authentication for the current request.

    Returns None if the request is authenticated (success).
    Returns a Flask response tuple if authentication fails (401 or redirect).

    This helper is used by both the ``require_auth`` decorator and blueprint
    ``before_request`` hooks to avoid duplicating auth logic.
    """
    from routes.admin import verify_api_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if verify_api_token(token):
            g.auth_mode = "bearer"
            request_id = get_request_id()
            logger.info(
                "Admin API access via token: %s %s",
                request.method,
                request.path,
                extra={
                    "user": "api_token",
                    "ip": request.remote_addr,
                    "request_id": request_id,
                    "admin": True,
                },
            )
            return None
        return jsonify({"error": "Invalid API token"}), 401

    if not session.get("admin"):
        if request.path.startswith("/api"):
            return jsonify({"error": "Unauthorized", "message": "Authentication required"}), 401
        return redirect(url_for("admin.login"))
    stored_ip = session.get("ip")
    stored_user_agent = session.get("user_agent")
    current_ip = request.remote_addr or "unknown"
    current_user_agent = request.headers.get("User-Agent", "")
    if stored_ip and stored_ip != current_ip:
        session.pop("admin", None)
        logger.warning("Session hijacking detected: IP mismatch (%s vs %s)", stored_ip, current_ip)
        return redirect(url_for("admin.login"))
    if stored_user_agent and stored_user_agent != current_user_agent:
        session.pop("admin", None)
        logger.warning("Session hijacking detected: User-Agent mismatch")
        return redirect(url_for("admin.login"))
    request_id = get_request_id()
    logger.info(
        "Admin access: %s %s",
        request.method,
        request.path,
        extra={
            "user": "admin",
            "ip": request.remote_addr,
            "request_id": request_id,
            "admin": True,
        },
    )
    g.auth_mode = "session"
    return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_result = authenticate_request()
        if auth_result is not None:
            return auth_result
        return f(*args, **kwargs)

    return decorated


def validate_csrf_json(f):
    """Decorator to validate CSRF token for JSON API endpoints.

    Flask-WTF CSRF only validates form/multipart requests.
    Use this decorator on JSON endpoints to validate X-CSRFToken header.

    Respects WTF_CSRF_ENABLED = False in TestingConfig.
    """
    from flask import current_app
    from flask_wtf.csrf import CSRFError, validate_csrf
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_app.config.get("WTF_CSRF_ENABLED", True):
            return f(*args, **kwargs)
        token = request.headers.get("X-CSRFToken")
        if not token:
            return jsonify({"error": "CSRF token missing"}), 400
        try:
            validate_csrf(token)
        except (CSRFError, ValidationError):
            return jsonify({"error": "CSRF token invalid"}), 400
        return f(*args, **kwargs)
    return decorated


def csrf_for_session_auth(f):
    """Decorator to validate CSRF token for session-authenticated requests.

    Skips CSRF validation for verified bearer-token authenticated requests
    (browsers do not automatically attach bearer credentials). Requires
    ``g.auth_mode`` to be set by ``authenticate_request()`` — if auth
    has not run, returns 401.

    Respects WTF_CSRF_ENABLED = False in TestingConfig.
    """
    from flask import current_app
    from flask_wtf.csrf import CSRFError, validate_csrf

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_app.config.get("WTF_CSRF_ENABLED", True):
            return f(*args, **kwargs)

        mode = getattr(g, "auth_mode", None)
        if mode == "bearer":
            return f(*args, **kwargs)
        if mode != "session":
            return jsonify({"error": "Authentication required before CSRF validation"}), 401

        # Validate CSRF for session-authenticated requests
        token = request.headers.get("X-CSRFToken")
        if not token:
            return jsonify({"error": "CSRF token missing"}), 400
        try:
            validate_csrf(token)
        except (CSRFError, ValidationError):
            return jsonify({"error": "CSRF token invalid"}), 400
        return f(*args, **kwargs)

    return decorated


def commit(db: Any, error_message: str = "Operation failed") -> tuple[Response, int] | None:
    """Commit the database session, rolling back on error.

    Returns None on success, or a JSON error response tuple on failure.

    Usage in route handlers:
        error = commit(db, "Failed to update articles")
        if error:
            return error

    This eliminates the repetitive try/except/rollback pattern in admin API routes.
    """
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": error_message}), 500
    return None


@contextmanager
def commit_or_rollback():
    """Context manager for db.session.commit() that re-raises on error.

    Usage in route handlers or tasks:
        with commit_or_rollback():
            db.session.commit()

    Rolls back on SQLAlchemyError and re-raises. Use this when the caller
    needs to handle the error response format (HTML, redirect, etc.) or
    when used in Celery tasks that re-raise for retry.
    """
    from extensions import db

    try:
        yield
    except SQLAlchemyError:
        db.session.rollback()
        raise

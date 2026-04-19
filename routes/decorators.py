"""Shared helpers for route handlers."""

from functools import wraps
from contextlib import contextmanager

from flask import jsonify, request
from sqlalchemy.exc import SQLAlchemyError


def validate_csrf_json(f):
    """Decorator to validate CSRF token for JSON API endpoints.

    Flask-WTF CSRF only validates form/multipart requests.
    Use this decorator on JSON endpoints to validate X-CSRFToken header.

    Respects WTF_CSRF_ENABLED = False in TestingConfig.
    """
    from flask import current_app
    from flask_wtf.csrf import validate_csrf
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_app.config.get("WTF_CSRF_ENABLED", True):
            return f(*args, **kwargs)
        token = request.headers.get("X-CSRFToken")
        if not token:
            return jsonify({"error": "CSRF token missing"}), 400
        try:
            validate_csrf(token)
        except Exception:
            return jsonify({"error": "CSRF token invalid"}), 400
        return f(*args, **kwargs)
    return decorated


def commit(db, error_message="Operation failed"):
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

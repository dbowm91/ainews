"""Shared helpers for route handlers."""

from contextlib import contextmanager

from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError


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

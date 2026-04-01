"""Shared route utilities."""

from functools import wraps

from flask import jsonify, request


def limit_content_length(max_bytes: int):
    """Decorator to limit request Content-Length per route."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            content_length = request.content_length
            if content_length and content_length > max_bytes:
                return jsonify({"error": "Request too large"}), 413
            return f(*args, **kwargs)

        return wrapped

    return decorator

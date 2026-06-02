"""Utilities for admin API routes."""

from typing import Any

from flask import Response, jsonify


def api_response(
    data: Any = None,
    error: str | None = None,
    status: int = 200,
    meta: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    """Standardize JSON API responses with consistent envelope.

    Args:
        data: The main response data (will be wrapped in {"data": ...})
        error: Error message string (will be wrapped in {"error": ...})
        status: HTTP status code
        meta: Optional metadata dict (will be wrapped in {"meta": ...})

    Returns:
        Tuple of (jsonified response, status code)
    """
    payload: dict[str, Any] = {}
    if data is not None:
        payload["data"] = data
    if meta:
        payload["meta"] = meta
    if error:
        payload["error"] = error
    return jsonify(payload), status

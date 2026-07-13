"""Theme CSS delivery routes.

Serves pre-generated theme CSS from the startup-built registry.
Blueprint: themes_bp
"""
from __future__ import annotations

import logging

from flask import Blueprint, Response, abort, request

from services.themes.loader import get_app_registry

logger = logging.getLogger(__name__)

themes_bp = Blueprint("themes", __name__)


@themes_bp.route("/assets/themes/<theme_id>.css")
def serve_theme_css(theme_id: str) -> Response:
    """Serve pre-generated CSS for a registered theme.

    Validates the theme_id against the registry (never the filesystem).
    Returns 404 for unknown IDs so stale selections are detectable.
    Sets cache headers appropriate for process-lifetime content.
    """
    registry = get_app_registry()
    if registry is None:
        abort(503, description="Theme system not available")

    if "/" in theme_id or "\\" in theme_id or ".." in theme_id:
        abort(404, description="Invalid theme ID")

    registered = registry.get_exact(theme_id)
    if registered is None:
        abort(404, description=f"Theme '{theme_id}' not found")

    css = registered.css
    if not css:
        abort(404, description=f"Theme '{theme_id}' has no CSS output")

    etag = f'"{registered.content_digest}"'

    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status=304)

    response = Response(
        css,
        mimetype="text/css",
        headers={
            "Content-Type": "text/css; charset=utf-8",
            "Cache-Control": "public, max-age=300",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
        },
    )

    return response

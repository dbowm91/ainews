"""Theme CSS delivery routes.

Serves pre-generated theme CSS from the startup-built registry.
Blueprint: themes_bp
"""
from __future__ import annotations

import logging

from flask import Blueprint, Response, abort, jsonify, request

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

    response = Response(
        css,
        mimetype="text/css",
        headers={
            "Content-Type": "text/css; charset=utf-8",
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
    response.set_etag(registered.content_digest)
    return response.make_conditional(request)


def _build_safe_metadata() -> dict | None:
    """Build safe theme metadata dict for browser consumption.

    Returns None if the theme registry is not available.
    Excludes emergency themes — they are internal fallbacks.
    Display names are plain validated strings; Jinja tojson and Flask
    jsonify handle serialization safely without pre-escaping.
    """
    registry = get_app_registry()
    if registry is None:
        return None
    return {
        "defaults": {
            "dark": registry.default_dark_id,
            "light": registry.default_light_id,
        },
        "themes": {
            theme_id: {
                "name": theme.display_name,
                "appearance": theme.appearance,
                "css_url": f"/assets/themes/{theme_id}.css",
                "origin": theme.origin.kind,
            }
            for theme_id, theme in registry.themes.items()
            if theme.origin.kind != "emergency"
        },
    }


@themes_bp.app_context_processor
def inject_theme_metadata() -> dict:
    """Inject safe theme metadata for browser consumption."""
    metadata = _build_safe_metadata()
    if metadata is None:
        return {}
    return {"theme_metadata": metadata}


@themes_bp.route("/api/v1/themes/metadata")
def theme_metadata() -> Response:
    """Return safe theme metadata as JSON for browser consumption.

    Excludes emergency themes and internal state. Only exposes safe fields
    (id, name, appearance, css_url, origin).
    """
    metadata = _build_safe_metadata()
    if metadata is None:
        return jsonify({"error": "Theme system not available"}), 503

    response = jsonify(metadata)
    response.headers["Cache-Control"] = "public, max-age=60"
    return response

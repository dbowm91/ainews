import logging

from flask import Response, jsonify, request

from routes.admin import admin_bp, require_auth
from routes.decorators import commit, validate_csrf_json

logger = logging.getLogger(__name__)

VALID_SOURCE_TYPES = frozenset({
    "rss",
    "atom",
    "web",
    "twitter",
    "reddit",
})


@admin_bp.route("/api/sources", methods=["GET"])
@require_auth
def list_sources() -> Response:
    """List all sources."""
    from models import Source

    sources = Source.query.order_by(Source.name.asc()).all()
    return jsonify(
        {
            "sources": [
                {
                    "id": s.id,
                    "source_key": s.source_key,
                    "name": s.name,
                    "url": s.url,
                    "feed_url": s.feed_url,
                    "source_type": s.source_type,
                    "active": s.active,
                    "last_crawled": s.last_crawled.isoformat() if s.last_crawled else None,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "consecutive_failures": s.consecutive_failures or 0,
                    "consecutive_successes": s.consecutive_successes or 0,
                    "last_success_at": (
                        s.last_success_at.isoformat() if s.last_success_at else None
                    ),
                    "last_error": s.last_error,
                    "disabled_at": s.disabled_at.isoformat() if s.disabled_at else None,
                }
                for s in sources
            ]
        }
    )


@admin_bp.route("/api/sources", methods=["POST"])
@require_auth
@validate_csrf_json
def create_source() -> tuple[Response, int] | Response:
    """Create a new source."""
    from extensions import db
    from models import Source

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    source_key = data.get("source_key", "").strip()
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    feed_url = data.get("feed_url", "").strip()
    source_type = data.get("source_type", "").strip()

    if not source_key:
        return jsonify({"error": "source_key is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not source_type:
        return jsonify({"error": "source_type is required"}), 400
    if source_type not in VALID_SOURCE_TYPES:
        return jsonify({"error": f"source_type must be one of: {sorted(VALID_SOURCE_TYPES)}"}), 400

    existing = Source.query.filter_by(source_key=source_key).first()
    if existing:
        return jsonify({"error": f"source_key '{source_key}' already exists"}), 409

    if url:
        try:
            from services.url import validate_url_safe

            validate_url_safe(url)
        except Exception as e:
            logger.debug("Invalid source URL: %s", e)
            return jsonify({"error": f"Invalid URL: {e}"}), 400

    source = Source(
        source_key=source_key,
        name=name,
        url=url or None,
        feed_url=feed_url or None,
        source_type=source_type,
        active=data.get("active", True),
    )
    db.session.add(source)
    error = commit(db, "Failed to create source")
    if error:
        return error

    return jsonify(
        {
            "message": "Source created",
            "source": {
                "id": source.id,
                "source_key": source.source_key,
                "name": source.name,
                "url": source.url,
                "feed_url": source.feed_url,
                "source_type": source.source_type,
                "active": source.active,
            },
        }
    ), 201


@admin_bp.route("/api/sources/<int:source_id>", methods=["GET"])
@require_auth
def get_source(source_id: int) -> Response:
    """Get a specific source."""
    from extensions import db
    from models import Source

    source = db.get_or_404(Source, source_id)
    return jsonify(
        {
            "source": {
                "id": source.id,
                "source_key": source.source_key,
                "name": source.name,
                "url": source.url,
                "feed_url": source.feed_url,
                "source_type": source.source_type,
                "active": source.active,
                "last_crawled": source.last_crawled.isoformat() if source.last_crawled else None,
                "created_at": source.created_at.isoformat() if source.created_at else None,
                "updated_at": source.updated_at.isoformat() if source.updated_at else None,
                "consecutive_failures": source.consecutive_failures or 0,
                "consecutive_successes": source.consecutive_successes or 0,
                "last_success_at": (
                    source.last_success_at.isoformat() if source.last_success_at else None
                ),
                "last_error": source.last_error,
                "disabled_at": source.disabled_at.isoformat() if source.disabled_at else None,
            }
        }
    )


@admin_bp.route("/api/sources/<int:source_id>", methods=["PUT"])
@require_auth
@validate_csrf_json
def update_source(source_id: int) -> tuple[Response, int] | Response:
    """Update a source."""
    from extensions import db
    from models import Source

    source = db.get_or_404(Source, source_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    if "source_key" in data:
        new_key = data["source_key"].strip()
        existing = Source.query.filter(
            Source.source_key == new_key,
            Source.id != source_id,
        ).first()
        if existing:
            return jsonify({"error": f"source_key '{new_key}' already exists"}), 409
        source.source_key = new_key

    if "name" in data:
        source.name = data["name"].strip()
    if "url" in data:
        if data["url"]:
            try:
                from services.url import validate_url_safe

                validate_url_safe(data["url"])
            except Exception as e:
                logger.debug("Invalid source URL update: %s", e)
                return jsonify({"error": f"Invalid URL: {e}"}), 400
        source.url = data["url"] or None
    if "feed_url" in data:
        source.feed_url = data["feed_url"] or None
    if "source_type" in data:
        if data["source_type"] not in VALID_SOURCE_TYPES:
            return jsonify({"error": f"source_type must be one of: {sorted(VALID_SOURCE_TYPES)}"}), 400
        source.source_type = data["source_type"]
    if "active" in data:
        source.active = bool(data["active"])

    error = commit(db, "Failed to update source")
    if error:
        return error

    return jsonify({"message": "Source updated"})


@admin_bp.route("/api/sources/<int:source_id>", methods=["DELETE"])
@require_auth
@validate_csrf_json
def delete_source(source_id: int) -> tuple[Response, int] | Response:
    """Delete a source."""
    from extensions import db
    from models import Source

    source = db.get_or_404(Source, source_id)
    db.session.delete(source)
    error = commit(db, "Failed to delete source")
    if error:
        return error

    return jsonify({"message": "Source deleted"})
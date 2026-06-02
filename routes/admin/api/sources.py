import logging

from flask import Response, request
from pydantic import ValidationError

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response
from routes.decorators import commit, validate_csrf_json
from schemas.admin import CreateSourceRequest, UpdateSourceRequest
from services.audit import log_admin_action
from services.url import UnsafeURLError

logger = logging.getLogger(__name__)


@admin_api_bp.route("/sources", methods=["GET"])
@require_auth
def list_sources() -> tuple[Response, int]:
    """List all sources."""
    from models import Source

    sources = Source.query.order_by(Source.name.asc()).all()
    return api_response(
        data=[
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
        ],
    )


@admin_api_bp.route("/sources", methods=["POST"])
@require_auth
@validate_csrf_json
def create_source() -> tuple[Response, int] | Response:
    """Create a new source."""
    from extensions import db
    from models import Source

    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    try:
        validated = CreateSourceRequest(**data)
    except ValidationError as e:
        return api_response(error=str(e), status=400)

    existing = Source.query.filter_by(source_key=validated.source_key).first()
    if existing:
        return api_response(error=f"source_key '{validated.source_key}' already exists", status=409)

    if validated.url:
        try:
            from services.url import validate_url_safe

            validate_url_safe(validated.url)
        except (UnsafeURLError, ValueError) as e:
            logger.debug("Invalid source URL: %s", e)
            return api_response(error=f"Invalid URL: {e}", status=400)

    source = Source(
        source_key=validated.source_key,
        name=validated.name,
        url=validated.url or None,
        feed_url=validated.feed_url or None,
        source_type=validated.source_type,
        active=validated.active,
    )
    db.session.add(source)
    error = commit(db, "Failed to create source")
    if error:
        return error

    try:
        log_admin_action(
            "source_create",
            target_type="source",
            target_id=source.id,
            details={
                "source_key": source.source_key,
                "name": source.name,
                "url": source.url,
                "source_type": source.source_type,
                "active": source.active,
            },
            category="config",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for source_create")

    return api_response(
        data={
            "id": source.id,
            "source_key": source.source_key,
            "name": source.name,
            "url": source.url,
            "feed_url": source.feed_url,
            "source_type": source.source_type,
            "active": source.active,
        },
        status=201,
        meta={"message": "Source created"},
    )


@admin_api_bp.route("/sources/<int:source_id>", methods=["GET"])
@require_auth
def get_source(source_id: int) -> tuple[Response, int]:
    """Get a specific source."""
    from extensions import db
    from models import Source

    source = db.get_or_404(Source, source_id)
    return api_response(
        data={
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
        },
    )


@admin_api_bp.route("/sources/<int:source_id>", methods=["PUT"])
@require_auth
@validate_csrf_json
def update_source(source_id: int) -> tuple[Response, int] | Response:
    """Update a source."""
    from extensions import db
    from models import Source

    source = db.get_or_404(Source, source_id)
    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    try:
        validated = UpdateSourceRequest(**data)
    except ValidationError as e:
        return api_response(error=str(e), status=400)

    if validated.source_key is not None:
        new_key = validated.source_key
        existing = Source.query.filter(
            Source.source_key == new_key,
            Source.id != source_id,
        ).first()
        if existing:
            return api_response(error=f"source_key '{new_key}' already exists", status=409)
        source.source_key = new_key

    if validated.name is not None:
        source.name = validated.name
    if validated.url is not None:
        if validated.url:
            try:
                from services.url import validate_url_safe

                validate_url_safe(validated.url)
            except (UnsafeURLError, ValueError) as e:
                logger.debug("Invalid source URL update: %s", e)
                return api_response(error=f"Invalid URL: {e}", status=400)
        source.url = validated.url or None
    if validated.feed_url is not None:
        source.feed_url = validated.feed_url or None
    if validated.source_type is not None:
        source.source_type = validated.source_type
    if validated.active is not None:
        source.active = validated.active

    error = commit(db, "Failed to update source")
    if error:
        return error

    try:
        log_admin_action(
            "source_update",
            target_type="source",
            target_id=source.id,
            details={
                "source_key": source.source_key,
                "name": source.name,
                "url": source.url,
                "source_type": source.source_type,
                "active": source.active,
            },
            category="config",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for source_update")

    return api_response(meta={"message": "Source updated"})


@admin_api_bp.route("/sources/<int:source_id>", methods=["PATCH"])
@require_auth
@validate_csrf_json
def update_source_partial(source_id: int) -> tuple[Response, int] | Response:
    """Partially update a source."""
    from extensions import db
    from models import Source

    source = db.get_or_404(Source, source_id)
    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    if "source_key" in data:
        new_key = data["source_key"]
        existing = Source.query.filter(
            Source.source_key == new_key,
            Source.id != source_id,
        ).first()
        if existing:
            return api_response(error=f"source_key '{new_key}' already exists", status=409)
        source.source_key = new_key

    if "name" in data:
        source.name = data["name"]

    if "url" in data:
        new_url = data["url"]
        if new_url:
            try:
                from services.url import validate_url_safe
                validate_url_safe(new_url)
            except (UnsafeURLError, ValueError) as e:
                logger.debug("Invalid source URL in PATCH: %s", e)
                return api_response(error=f"Invalid URL: {e}", status=400)
        source.url = new_url or None

    if "feed_url" in data:
        source.feed_url = data["feed_url"] or None

    if "source_type" in data:
        source.source_type = data["source_type"]

    if "active" in data:
        source.active = data["active"]

    error = commit(db, "Failed to update source via PATCH")
    if error:
        return error

    try:
        log_admin_action(
            "source_update_partial",
            target_type="source",
            target_id=source.id,
            details={
                "source_key": source.source_key,
                "name": source.name,
                "url": source.url,
                "source_type": source.source_type,
                "active": source.active,
            },
            category="config",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for source_update_partial")

    return api_response(
        data={
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
            "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
            "last_error": source.last_error,
            "disabled_at": source.disabled_at.isoformat() if source.disabled_at else None,
        },
        meta={"message": "Source partially updated"},
    )


@admin_api_bp.route("/sources/<int:source_id>", methods=["DELETE"])
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

    try:
        log_admin_action(
            "source_delete",
            target_type="source",
            target_id=source_id,
            details={"source_key": source.source_key},
            category="config",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for source_delete")

    return api_response(meta={"message": "Source deleted"})


@admin_api_bp.route("/sources/<int:source_id>/refresh", methods=["POST"])
@require_auth
@validate_csrf_json
def refresh_source(source_id: int) -> tuple[Response, int] | Response:
    """Trigger an immediate crawl of a specific source."""
    from tasks.crawl import crawl_source

    from extensions import db
    from models import Source
    from logging_config import get_request_id

    source = db.get_or_404(Source, source_id)
    # Convert Source model to config dict for crawl_source task
    source_config: dict[str, object] = {
        "id": source.source_key,
        "name": source.name,
        "type": source.source_type,
        "enabled": source.active,
        "config": {},
    }

    headers: dict[str, str] = {}
    request_id = get_request_id()
    if request_id:
        headers["request_id"] = request_id

    try:
        signed_kwargs = (
            __import__("services.task_security", fromlist=["get_signed_kwargs"])
            .get_signed_kwargs("crawl_source", (source_config, None), {})
        )
    except Exception:  # noqa: BLE001 - use unsigned if security not configured
        signed_kwargs = {"source_config": source_config, "run_id": None}

    crawl_source.apply_async(kwargs=signed_kwargs, headers=headers)

    try:
        log_admin_action(
            "source_refresh",
            target_type="source",
            target_id=source_id,
            details={"source_key": source.source_key},
            category="config",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for source_refresh")

    return api_response(meta={"message": "Source refresh triggered", "source_id": source_id})

import re
import time
import logging
from flask import render_template, jsonify, request, Response
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth
from routes.decorators import commit

logger = logging.getLogger(__name__)

_SOURCE_KEY_STRIP_RE = re.compile(r"[^a-z0-9\s-]")
_SOURCE_KEY_DASH_RE = re.compile(r"[\s]+")


def _generate_source_key(name: str) -> str:
    key = name.lower().strip()
    key = _SOURCE_KEY_STRIP_RE.sub("", key)
    key = _SOURCE_KEY_DASH_RE.sub("-", key)
    return key[:64] or "source"


@admin_bp.route("/sources")
@require_auth
def sources() -> str:
    from models import Source

    sources = Source.query.order_by(Source.name).all()

    return render_template(
        "admin/sources.html",
        sources=sources,
    )


@admin_bp.route("/sources/add", methods=["POST"])
@require_auth
def add_source() -> str:
    from models import Source
    from extensions import db

    name = (request.form.get("name") or "").strip()
    source_type = (request.form.get("source_type") or "").strip()
    source_url = (request.form.get("source_url") or "").strip()

    if not name:
        return '<div class="form-error" role="alert">name is required</div>', 400
    if source_type not in ("rss", "web", "api"):
        return '<div class="form-error" role="alert">invalid source type</div>', 400

    if source_url:
        try:
            from services.url import validate_url_safe

            validate_url_safe(source_url)
        except Exception as e:
            logger.warning("Source URL validation failed: %s", e)
            return (
                '<div class="form-error" role="alert">Invalid source URL</div>',
                400,
            )

    source_key = _generate_source_key(name)
    existing = Source.query.filter_by(source_key=source_key).first()
    if existing:
        source_key = f"{source_key}-{int(time.time()) % 10000:04d}"

    source = Source(
        source_key=source_key,
        name=name,
        source_type=source_type,
        active=True,
    )
    if source_url:
        if source_type == "rss":
            source.feed_url = source_url
        else:
            source.url = source_url

    try:
        db.session.add(source)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return '<div class="form-error" role="alert">failed to create source</div>', 500

    return render_template("admin/partials/source_row.html", s=source)


@admin_bp.route("/sources/<int:source_id>/enable", methods=["POST"])
@require_auth
def enable_source(source_id: int) -> tuple[Response, int]:
    from models import Source
    from extensions import db

    source = db.get_or_404(Source, source_id)
    source.active = True
    source.disabled_at = None
    source.consecutive_failures = 0
    source.last_error = None
    error = commit(db, "Failed to enable source")
    if error:
        return error
    return jsonify({"message": f"Source {source.name} enabled"}), 200


@admin_bp.route("/sources/<int:source_id>/disable", methods=["POST"])
@require_auth
def disable_source(source_id: int) -> tuple[Response, int]:
    from models import Source
    from extensions import db
    from datetime import datetime, timezone

    source = db.get_or_404(Source, source_id)
    source.active = False
    source.disabled_at = datetime.now(timezone.utc)
    error = commit(db, "Failed to disable source")
    if error:
        return error
    return jsonify({"message": f"Source {source.name} disabled"}), 200

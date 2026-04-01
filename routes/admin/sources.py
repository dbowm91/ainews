import re
from flask import render_template, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth


def _generate_source_key(name: str) -> str:
    key = name.lower().strip()
    key = re.sub(r"[^a-z0-9\s-]", "", key)
    key = re.sub(r"[\s]+", "-", key)
    return key[:64] or "source"


@admin_bp.route("/sources")
@require_auth
def sources():
    from models import Source

    sources = Source.query.order_by(Source.name).all()

    return render_template(
        "admin/sources.html",
        sources=sources,
    )


@admin_bp.route("/sources/add", methods=["POST"])
@require_auth
def add_source():
    from models import Source
    from extensions import db

    name = (request.form.get("name") or "").strip()
    source_type = (request.form.get("source_type") or "").strip()
    source_url = (request.form.get("source_url") or "").strip()

    if not name:
        return '<div class="form-error" role="alert">name is required</div>', 400
    if source_type not in ("rss", "web", "api"):
        return '<div class="form-error" role="alert">invalid source type</div>', 400

    source_key = _generate_source_key(name)
    existing = Source.query.filter_by(source_key=source_key).first()
    if existing:
        source_key = f"{source_key}-{existing.id + 1}"

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
def enable_source(source_id):
    from models import Source
    from extensions import db

    source = Source.query.get_or_404(source_id)
    source.active = True
    source.disabled_at = None
    source.consecutive_failures = 0
    source.last_error = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to enable source"}), 500
    return jsonify({"message": f"Source {source.name} enabled"}), 200


@admin_bp.route("/sources/<int:source_id>/disable", methods=["POST"])
@require_auth
def disable_source(source_id):
    from models import Source
    from extensions import db
    from datetime import datetime, timezone

    source = Source.query.get_or_404(source_id)
    source.active = False
    source.disabled_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to disable source"}), 500
    return jsonify({"message": f"Source {source.name} disabled"}), 200

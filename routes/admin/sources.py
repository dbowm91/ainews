from flask import render_template, jsonify
from routes.admin import admin_bp, require_auth


@admin_bp.route("/sources")
@require_auth
def sources():
    from models import Source

    sources = Source.query.order_by(Source.name).all()

    return render_template(
        "admin/sources.html",
        sources=sources,
    )


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
    except Exception:
        db.session.rollback()
        return jsonify({"message": "Failed to enable source"}), 500
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
    except Exception:
        db.session.rollback()
        return jsonify({"message": "Failed to disable source"}), 500
    return jsonify({"message": f"Source {source.name} disabled"}), 200

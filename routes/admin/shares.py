from flask import render_template, request, redirect, url_for, jsonify
from routes.admin import admin_bp, require_auth


@admin_bp.route("/shares")
@require_auth
def shares():
    from models import ShareConfig

    configs = ShareConfig.query.order_by(ShareConfig.sort_order).all()
    return render_template("admin/shares.html", configs=configs)


@admin_bp.route("/shares/<int:config_id>/toggle", methods=["POST"])
@require_auth
def toggle_share(config_id):
    from models import ShareConfig
    from extensions import db

    config = db.get_or_404(ShareConfig, config_id)
    config.active = not config.active
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to toggle share config"}), 500

    if request.headers.get("HX-Request"):
        return render_template("admin/partials/share_row.html", config=config)
    return redirect(url_for("admin.shares"))

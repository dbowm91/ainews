from flask import render_template, request, redirect, url_for, Response
from routes.admin import admin_bp, require_auth
from routes.decorators import commit


@admin_bp.route("/shares")
@require_auth
def shares() -> str:
    from models import ShareConfig

    configs = ShareConfig.query.order_by(ShareConfig.sort_order).all()
    return render_template("admin/shares.html", configs=configs)


@admin_bp.route("/shares/<int:config_id>/toggle", methods=["POST"])
@require_auth
def toggle_share(config_id: int) -> str | Response:
    from models import ShareConfig
    from extensions import db

    config = db.get_or_404(ShareConfig, config_id)
    config.active = not config.active
    error = commit(db, "Failed to toggle share config")
    if error:
        return error
    if request.headers.get("HX-Request"):
        return render_template("admin/partials/share_row.html", config=config)
    return redirect(url_for("admin.shares"))

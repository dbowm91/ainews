"""Admin webhooks page routes."""

from flask import render_template

from routes.admin import admin_bp, require_auth


@admin_bp.route("/webhooks")
@require_auth
def webhooks():
    """Webhooks management page."""
    from models import Webhook

    webhooks = Webhook.query.order_by(Webhook.created_at.desc()).all()

    return render_template(
        "admin/webhooks.html",
        webhooks=webhooks,
    )

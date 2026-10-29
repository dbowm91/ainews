from flask import redirect, render_template, request, url_for
from werkzeug.wrappers.response import Response

from routes.admin import admin_bp, require_auth
from routes.decorators import commit, validate_csrf_token


@admin_bp.route("/shares")
@require_auth
def shares() -> str:
    from models import ShareConfig

    configs = ShareConfig.query.order_by(ShareConfig.sort_order).all()
    return render_template("admin/shares.html", configs=configs)


@admin_bp.route("/shares/add", methods=["POST"])
@require_auth
@validate_csrf_token
def add_share() -> str | Response | tuple[str, int] | tuple[Response, int]:
    from extensions import db
    from models import ShareConfig

    platform_key = (request.form.get("platform_key") or "").strip()
    label = (request.form.get("label") or "").strip()
    url_template = (request.form.get("url_template") or "").strip()
    icon_name = (request.form.get("icon_name") or "").strip()
    sort_order = request.form.get("sort_order", "0").strip()

    if not platform_key:
        return '<div class="form-error" role="alert">platform_key is required</div>', 400
    if not label:
        return '<div class="form-error" role="alert">label is required</div>', 400
    if not url_template:
        return '<div class="form-error" role="alert">url_template is required</div>', 400
    if not icon_name:
        return '<div class="form-error" role="alert">icon_name is required</div>', 400

    existing = ShareConfig.query.filter_by(platform_key=platform_key).first()
    if existing:
        return '<div class="form-error" role="alert">platform_key already exists</div>', 400

    try:
        sort_order_int = int(sort_order) if sort_order.isdigit() else 0
    except ValueError:
        sort_order_int = 0

    config = ShareConfig(
        platform_key=platform_key,
        label=label,
        url_template=url_template,
        icon_name=icon_name,
        sort_order=sort_order_int,
    )
    db.session.add(config)
    error = commit(db, "Failed to create share config")
    if error:
        return error

    from services.audit import log_admin_action

    log_admin_action("share_config_create", target_type="share_config", target_id=config.id, details={"platform_key": platform_key})

    if request.headers.get("HX-Request"):
        return render_template("admin/partials/share_row.html", config=config)
    return redirect(url_for("admin.shares"))


@admin_bp.route("/shares/<int:config_id>/edit", methods=["POST"])
@require_auth
@validate_csrf_token
def edit_share(config_id: int) -> str | Response | tuple[str, int] | tuple[Response, int]:
    from extensions import db
    from models import ShareConfig

    config = db.get_or_404(ShareConfig, config_id)

    platform_key = (request.form.get("platform_key") or "").strip()
    label = (request.form.get("label") or "").strip()
    url_template = (request.form.get("url_template") or "").strip()
    icon_name = (request.form.get("icon_name") or "").strip()
    sort_order = request.form.get("sort_order", "0").strip()

    if not platform_key:
        return '<div class="form-error" role="alert">platform_key is required</div>', 400
    if not label:
        return '<div class="form-error" role="alert">label is required</div>', 400
    if not url_template:
        return '<div class="form-error" role="alert">url_template is required</div>', 400
    if not icon_name:
        return '<div class="form-error" role="alert">icon_name is required</div>', 400

    if platform_key != config.platform_key:
        existing = ShareConfig.query.filter_by(platform_key=platform_key).first()
        if existing:
            return '<div class="form-error" role="alert">platform_key already exists</div>', 400

    config.platform_key = platform_key
    config.label = label
    config.url_template = url_template
    config.icon_name = icon_name
    try:
        config.sort_order = int(sort_order) if sort_order.isdigit() else 0
    except ValueError:
        pass

    error = commit(db, "Failed to update share config")
    if error:
        return error

    from services.audit import log_admin_action

    log_admin_action("share_config_update", target_type="share_config", target_id=config.id, details={"platform_key": platform_key})

    if request.headers.get("HX-Request"):
        return render_template("admin/partials/share_row.html", config=config)
    return redirect(url_for("admin.shares"))


@admin_bp.route("/shares/<int:config_id>/delete", methods=["POST"])
@require_auth
@validate_csrf_token
def delete_share(config_id: int) -> str | Response | tuple[str, int] | tuple[Response, int]:
    from extensions import db
    from models import ShareConfig

    config = db.get_or_404(ShareConfig, config_id)
    platform_key = config.platform_key
    db.session.delete(config)
    error = commit(db, "Failed to delete share config")
    if error:
        return error

    from services.audit import log_admin_action

    log_admin_action("share_config_delete", target_type="share_config", target_id=config_id, details={"platform_key": platform_key})

    if request.headers.get("HX-Request"):
        return ""
    return redirect(url_for("admin.shares"))


@admin_bp.route("/shares/<int:config_id>/edit-form", methods=["GET"])
@require_auth
def edit_share_form(config_id: int) -> str:
    from extensions import db
    from models import ShareConfig

    config = db.get_or_404(ShareConfig, config_id)
    return render_template("admin/partials/share_edit_form.html", config=config)


@admin_bp.route("/shares/<int:config_id>/row", methods=["GET"])
@require_auth
def share_row(config_id: int) -> str:
    from extensions import db
    from models import ShareConfig

    config = db.get_or_404(ShareConfig, config_id)
    return render_template("admin/partials/share_row.html", config=config)


@admin_bp.route("/shares/<int:config_id>/toggle", methods=["POST"])
@require_auth
@validate_csrf_token
def toggle_share(config_id: int) -> str | Response | tuple[str, int] | tuple[Response, int]:
    from extensions import db
    from models import ShareConfig

    config = db.get_or_404(ShareConfig, config_id)
    config.active = not config.active
    error = commit(db, "Failed to toggle share config")
    if error:
        return error

    from services.audit import log_admin_action

    log_admin_action("share_config_toggle", target_type="share_config", target_id=config.id, details={"active": config.active})

    if request.headers.get("HX-Request"):
        return render_template("admin/partials/share_row.html", config=config)
    return redirect(url_for("admin.shares"))

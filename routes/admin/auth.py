import logging
from urllib.parse import urlparse

from flask import Response, current_app, redirect, render_template, request, session, url_for

from extensions import limiter
from models import AdminUser
from routes import limit_content_length
from routes.admin import (
    _check_and_record_attempt,
    _clear_attempts,
    _verify_password,
    admin_bp,
)
from services.totp import (
    consume_backup_code,
    generate_backup_codes,
    generate_secret,
    get_provisioning_uri,
    verify_backup_code,
    verify_token,
)

logger = logging.getLogger(__name__)


def _safe_redirect_url(next_url: str) -> str:
    """Return a safe redirect target, falling back to admin dashboard.

    Uses Werkzeug's safe_url_for to prevent open redirect attacks.
    Only allows relative paths within the application.
    """
    if not next_url:
        return url_for("admin.dashboard")
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return url_for("admin.dashboard")
    if not next_url.startswith("/") or next_url.startswith("//"):
        return url_for("admin.dashboard")
    return next_url


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@limit_content_length(1024)
def login() -> str | Response:
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))

    ip = request.remote_addr or "unknown"

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        admin_password = current_app.config.get("ADMIN_PASSWORD", "")
        if admin_password and _verify_password(admin_password, password):
            _clear_attempts(ip)
            admin_user = AdminUser.query.filter_by(username="admin").first()
            if admin_user and admin_user.totp_enabled:
                session["partial_login"] = True
                session["ip"] = ip
                session["user_agent"] = request.headers.get("User-Agent", "")
                return redirect(url_for("admin.verify_2fa"))
            session.clear()
            session["admin"] = True
            session["ip"] = ip
            session["user_agent"] = request.headers.get("User-Agent", "")
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_login", user="admin")
            except (SQLAlchemyError, RuntimeError) as e:
                logger.error("Failed to log admin login action: %s", e)
            next_url = request.args.get("next", "")
            return redirect(_safe_redirect_url(next_url))
        locked = _check_and_record_attempt(ip)
        if locked:
            error = "Too many failed attempts. Try again later."
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_login_failed_locked", user="admin", details={"ip": ip})
            except (SQLAlchemyError, RuntimeError) as e:
                logger.error("Failed to log admin login failure: %s", e)
            return render_template("admin/login.html", error=error), 429
        else:
            error = "Invalid password"
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_login_failed", user="admin", details={"ip": ip})
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to log admin login failure: %s", e)
    return render_template("admin/login.html", error=error)


@admin_bp.route("/verify-2fa", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@limit_content_length(1024)
def verify_2fa() -> str | Response:
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))
    if not session.get("partial_login"):
        return redirect(url_for("admin.login"))

    error = None
    admin_user = AdminUser.query.filter_by(username="admin").first()

    if request.method == "POST":
        token = request.form.get("token", "")
        backup_code = request.form.get("backup_code", "")

        if admin_user and admin_user.totp_secret and verify_token(admin_user.totp_secret, token):
            session.clear()
            session["admin"] = True
            session["ip"] = session.get("ip")
            session["user_agent"] = session.get("user_agent")
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_login_2fa", user="admin")
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to log admin 2FA login: %s", e)
            return redirect(url_for("admin.dashboard"))

        if admin_user and admin_user.backup_codes and backup_code:
            if verify_backup_code(admin_user.backup_codes, backup_code):
                new_codes = consume_backup_code(admin_user.backup_codes, backup_code)
                if new_codes is not None:
                    admin_user.backup_codes = new_codes
                    from extensions import db

                    db.session.commit()
                session.clear()
                session["admin"] = True
                session["ip"] = session.get("ip")
                session["user_agent"] = session.get("user_agent")
                try:
                    from services.audit import log_admin_action

                    log_admin_action("admin_login_backup_code", user="admin")
                except Exception as e:  # noqa: BLE001
                    logger.error("Failed to log admin backup code login: %s", e)
                return redirect(url_for("admin.dashboard"))
            error = "Invalid backup code"

        error = "Invalid 2FA token"
    return render_template("admin/verify_2fa.html", error=error)


@admin_bp.route("/setup-2fa", methods=["GET", "POST"])
def setup_2fa() -> str | Response:
    if not session.get("admin"):
        return redirect(url_for("admin.login"))

    admin_user = AdminUser.query.filter_by(username="admin").first()
    if not admin_user:
        return redirect(url_for("admin.dashboard"))

    error = None
    if request.method == "POST":
        token = request.form.get("token", "")
        if admin_user.totp_secret and verify_token(admin_user.totp_secret, token):
            admin_user.totp_enabled = True
            admin_user.backup_codes = generate_backup_codes()
            from extensions import db

            db.session.commit()
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_2fa_enabled", user="admin")
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to log 2FA enable: %s", e)
            return redirect(url_for("admin.dashboard"))
        error = "Invalid 2FA token"

    if not admin_user.totp_secret:
        admin_user.totp_secret = generate_secret()
        from extensions import db

        db.session.commit()

    qr_uri = get_provisioning_uri(admin_user.totp_secret, "admin", "ainews")
    return render_template("admin/setup_2fa.html", qr_uri=qr_uri, error=error)


@admin_bp.route("/logout", methods=["POST"])
def logout() -> Response:
    try:
        from services.audit import log_admin_action

        log_admin_action("admin_logout", user="admin")
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to log admin logout action: %s", e)
    session.pop("admin", None)
    return redirect("/")

import logging
from urllib.parse import urlparse

from flask import Response, current_app, redirect, render_template, request, session, url_for

from extensions import limiter
from routes import limit_content_length
from routes.admin import (
    _check_and_record_attempt,
    _clear_attempts,
    _verify_password,
    admin_bp,
)

logger = logging.getLogger(__name__)


def _safe_redirect_url(next_url: str) -> str:
    """Return a safe redirect target, falling back to admin dashboard.

    Uses Werkzeug's safe_url_for to prevent open redirect attacks.
    Only allows relative paths within the application.
    """
    if not next_url:
        return url_for("admin.dashboard")
    # Parse and validate: only allow path-only URLs (no scheme, no netloc)
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return url_for("admin.dashboard")
    # Must start with / but not //
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
            session.clear()
            session["admin"] = True
            session["ip"] = ip
            session["user_agent"] = request.headers.get("User-Agent", "")
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_login", user="admin")
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to log admin login action: %s", e)
            next_url = request.args.get("next", "")
            return redirect(_safe_redirect_url(next_url))
        locked = _check_and_record_attempt(ip)
        if locked:
            error = "Too many failed attempts. Try again later."
            try:
                from services.audit import log_admin_action

                log_admin_action("admin_login_failed_locked", user="admin", details={"ip": ip})
            except Exception as e:  # noqa: BLE001
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


@admin_bp.route("/logout", methods=["POST"])
def logout() -> Response:
    try:
        from services.audit import log_admin_action

        log_admin_action("admin_logout", user="admin")
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to log admin logout action: %s", e)
    session.pop("admin", None)
    return redirect("/")

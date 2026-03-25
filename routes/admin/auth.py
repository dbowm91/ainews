from urllib.parse import urlparse

from flask import render_template, request, redirect, url_for, session, current_app

from routes.admin import (
    admin_bp,
    _is_locked_out,
    _record_failed_attempt,
    _clear_attempts,
    _verify_password,
    _LOGIN_MAX_ATTEMPTS,
)
from extensions import limiter


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
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))

    ip = request.remote_addr or "unknown"
    if _is_locked_out(ip):
        error = "Too many failed attempts. Try again later."
        return render_template("admin/login.html", error=error), 429

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if _verify_password(current_app.config["ADMIN_PASSWORD"], password):
            _clear_attempts(ip)
            # Clear session to prevent fixation, then set admin flag
            session.clear()
            session["admin"] = True
            next_url = request.args.get("next", "")
            return redirect(_safe_redirect_url(next_url))
        _record_failed_attempt(ip)
        # Check remaining attempts from Redis
        try:
            from extensions import get_redis

            r = get_redis()
            key = f"ainews:login_attempts:{ip}"
            count = int(r.hget(key, "count") or 0)
        except Exception:
            count = 1  # Fallback if Redis unavailable
        remaining = _LOGIN_MAX_ATTEMPTS - count
        if remaining > 0:
            error = "Invalid password"
        else:
            error = "Too many failed attempts. Try again later."
    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin", None)
    return redirect("/")

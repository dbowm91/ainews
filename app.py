import os
import logging
import time
from flask import Flask, render_template, jsonify, request, g
from sqlalchemy import event
from config import config
from extensions import db, limiter, csrf, migrate
from logging_config import setup_logging
from services.metrics import record_request

logger = logging.getLogger(__name__)


def _seed_share_configs():
    from models import ShareConfig

    defaults = [
        {
            "platform_key": "x",
            "label": "X (Twitter)",
            "url_template": "https://twitter.com/intent/tweet?url={url}&text={title}",
            "icon_name": "x",
            "sort_order": 1,
        },
        {
            "platform_key": "facebook",
            "label": "Facebook",
            "url_template": "https://www.facebook.com/sharer/sharer.php?u={url}",
            "icon_name": "facebook",
            "sort_order": 2,
        },
        {
            "platform_key": "linkedin",
            "label": "LinkedIn",
            "url_template": "https://www.linkedin.com/sharing/share-offsite/?url={url}",
            "icon_name": "linkedin",
            "sort_order": 3,
        },
        {
            "platform_key": "reddit",
            "label": "Reddit",
            "url_template": "https://reddit.com/submit?url={url}&title={title}",
            "icon_name": "reddit",
            "sort_order": 4,
        },
    ]
    for d in defaults:
        existing = ShareConfig.query.filter_by(platform_key=d["platform_key"]).first()
        if not existing:
            db.session.add(ShareConfig(**d))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning("Failed to seed share configs", exc_info=True)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_CONFIG", "development")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config[config_name])

    # Development config warnings
    if config_name == "development":
        dev_cfg = config["development"]
        if not dev_cfg.ADMIN_PASSWORD:
            logger.warning("ADMIN_PASSWORD not set - admin login disabled")
        if dev_cfg.SECRET_KEY == "dev-secret-key-change-me":
            logger.warning(
                "SECRET_KEY is using a default value — "
                "sessions are insecure. Set SECRET_KEY env var for production."
            )

    # Setup structured logging
    setup_logging(
        app,
        level=logging.DEBUG if config_name == "development" else logging.INFO,
        config_name=config_name,
    )

    # Production secret validation
    if config_name == "production":
        config["production"].validate()

    db.init_app(app)

    # CSRF protection
    csrf.init_app(app)

    # Rate limiting
    limiter.init_app(app)

    # Response compression (gzip + brotli)
    from flask_compress import Compress

    Compress(app)

    # Security headers
    from flask_talisman import Talisman

    csp = {
        "default-src": "'self'",
        "style-src": "'self' 'unsafe-inline'",
        "script-src": "'self'",
        "img-src": "'self' data:",
    }
    Talisman(
        app,
        content_security_policy=csp,
        frame_options="SAMEORIGIN",
        referrer_policy="strict-origin-when-cross-origin",
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=False,
        permissions_policy={
            "camera": "()",
            "microphone": "()",
            "geolocation": "()",
        },
    )

    @app.before_request
    def start_request_timer():
        from logging_config import get_request_id

        request._request_start_time = time.monotonic()
        g.request_id = get_request_id()

    @app.after_request
    def record_request_metrics(response):
        duration_ms = (time.monotonic() - getattr(request, "_request_start_time", time.monotonic())) * 1000
        record_request(request.method, request.path, response.status_code, duration_ms)
        return response

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    import models  # noqa: F401

    with app.app_context():
        if db.engine.url.drivername == "sqlite":

            @event.listens_for(db.engine, "connect")
            def set_sqlite_pragma(dbapi_conn, _):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA cache_size=-64000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=268435456")
                cursor.close()

        # Always register migrations; create_all as fallback for fresh installs
        migrate.init_app(app, db)
        if config_name != "production":
            db.create_all()

        # Wire query logging after engine is ready (inside app context)
        from logging_config import setup_query_logging
        setup_query_logging(db.engine)

        _seed_share_configs()

    from routes.public import public_bp
    from routes.admin import admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    def _wants_json() -> bool:
        """Detect if the client expects a JSON response."""
        return (
            request.path.startswith("/api/")
            or request.path.startswith("/admin/api/")
            or request.is_json
            or "application/json" in request.accept_mimetypes
        )

    # Global error handlers
    @app.errorhandler(404)
    def not_found(e):
        logger.warning("404 Not Found: %s %s", request.method, request.path)
        if _wants_json():
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(
            "500 Internal Server Error: %s %s",
            request.method,
            request.path,
            exc_info=True,
        )
        if _wants_json():
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def rate_limited(e):
        logger.warning(
            "429 Rate Limited: %s %s from %s",
            request.method,
            request.path,
            request.remote_addr,
        )
        retry_after = None
        response = e.get_response()
        if response:
            retry_after = response.headers.get("Retry-After")
        if _wants_json():
            return jsonify({"error": "Rate limited", "retry_after": retry_after}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(413)
    def request_entity_too_large(e):
        logger.warning("413 Request too large: %s %s", request.method, request.path)
        if _wants_json():
            return jsonify({"error": "Request too large"}), 413
        return "Request too large", 413

    @app.template_filter("urlencode")
    def urlencode_filter(value):
        from urllib.parse import quote

        return quote(str(value), safe="")

    @app.template_filter("safe_href")
    def safe_href_filter(value):
        """Return URL only if it uses an http/https scheme and passes SSRF checks."""
        if not value:
            return "#"
        url = str(value).strip().lower()
        if not url.startswith(("http://", "https://")):
            return "#"
        try:
            from services.url import validate_url_safe

            validate_url_safe(value)
            return value
        except Exception as e:
            logger.warning("safe_href validation failed for %s: %s", value, e)
            return "#"

    return app

import logging
import os
import time
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from config import config
from extensions import csrf, db, limiter, migrate
from logging_config import setup_logging
from services.metrics import record_request

logger = logging.getLogger(__name__)


def _seed_share_configs():
    from sqlalchemy import inspect as sa_inspect

    from models import ShareConfig

    # Skip seeding if the table doesn't exist yet (e.g., during flask db upgrade
    # before migrations have run). Alembic migrations will create the table.
    try:
        inspector = sa_inspect(db.engine)
        if "share_configs" not in inspector.get_table_names():
            return
    except Exception:  # noqa: BLE001
        return

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
    except SQLAlchemyError:
        db.session.rollback()
        logger.warning("Failed to seed share configs", exc_info=True)


def _validate_config(app, config_name):
    """Validate configuration and emit warnings."""
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

    # Check .env file permissions
    env_path = os.path.join(app.root_path, ".env")
    if os.path.exists(env_path):
        mode = oct(os.stat(env_path).st_mode)[-3:]
        if mode not in ("600", "640"):
            msg = (
                f".env file permissions are {mode}, should be 600 or 640 "
                "(owner read/write only, group read for 640)"
            )
            if config_name == "production":
                raise RuntimeError(f"Fail-closed security: {msg}")
            logger.warning(msg)
    else:
        logger.warning(".env file not found at %s", env_path)

    # Production secret validation
    if config_name == "production":
        config["production"].validate()

    # Warn if DEBUG is enabled in production context
    if app.config.get("DEBUG") and config_name == "production":
        logger.warning("DEBUG mode is enabled - do not use in production")


def _setup_security(app):
    """Setup security headers, CSP, and response compression."""
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
        "connect-src": "'self'",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
    }
    Talisman(
        app,
        content_security_policy=csp,
        content_security_policy_nonce_in=["script-src"],
        force_https=not app.debug,
        session_cookie_secure=app.config.get("SESSION_COOKIE_SECURE", True),
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


def _setup_middleware(app):
    """Setup request middleware (before/after request handlers)."""

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

    @app.after_request
    def vary_on_htmx_request(response):
        """Keep the HTMX fragment and the full page in separate cache entries.

        A route that answers an HTMX request returns a bare fragment, and the
        same URL returns a complete page for a normal navigation. Both are
        cacheable, and without a ``Vary`` header the browser's HTTP cache
        keys them only by URL -- so the fragment cached by an in-page swap is
        handed to a later full page load. The reader then gets a document
        with no header, no footer and no navigation, which looks nothing
        like the rest of the site.
        """
        response.vary.add("HX-Request")
        return response


def _setup_database(app, config_name):
    """Initialize database, run migrations, and seed data."""
    import models  # noqa: F401 - register all models with SQLAlchemy before create_all()

    with app.app_context():
        if db.engine.url.drivername == "sqlite":
            database_path = db.engine.url.database
            if database_path and database_path != ":memory:":
                Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

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


def _register_blueprints(app):
    """Register Flask blueprints."""
    from routes.admin import admin_bp, admin_api_bp
    from routes.admin.api_tokens import api_tokens_bp
    from routes.public import public_bp
    from routes.themes import themes_bp
    from routes.tts import tts_bp

    # Exempt API blueprints from global Flask-WTF CSRF protection.
    # These blueprints use auth-aware decorators (csrf_for_session_auth,
    # validate_csrf_json) that handle CSRF policy correctly, including
    # bypassing CSRF for bearer-token requests.
    csrf.exempt(admin_api_bp)
    csrf.exempt(api_tokens_bp)

    app.register_blueprint(themes_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(tts_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_api_bp)
    app.register_blueprint(api_tokens_bp)


def _wants_json() -> bool:
    """Detect if the client expects a JSON response.

    Content negotiation must use the *best* match, not membership. Werkzeug's
    ``MIMEAccept`` treats the ``*/*`` wildcard as matching
    ``application/json``, and every browser navigation sends an ``Accept``
    header ending in ``*/*;q=0.8``. A membership test therefore classified
    every browser page view as a JSON client and served raw JSON in place of
    the styled HTML error pages.
    """
    if request.path.startswith("/api/v1/"):
        return True
    if request.is_json:
        return True
    return request.accept_mimetypes.best_match(["text/html", "application/json"]) == (
        "application/json"
    )


def _register_error_handlers(app):
    """Register global error handlers."""

    @app.errorhandler(404)
    def not_found(e):
        logger.warning("404 Not Found: %s %s", request.method, request.path)
        if _wants_json():
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        from flask import g
        logger.error(
            "500 Internal Server Error: %s %s",
            request.method,
            request.path,
            exc_info=True,
        )
        request_id = getattr(g, "request_id", None)
        if _wants_json():
            resp = {"error": "Internal server error"}
            if request_id:
                resp["request_id"] = request_id
            return jsonify(resp), 500
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


def _register_template_filters(app):
    """Register custom template filters."""

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
            from services.url import UnsafeURLError, validate_url_safe

            validate_url_safe(value)
            return value
        except (UnsafeURLError, ValueError) as e:
            logger.warning("safe_href validation failed for %s: %s", value, e)
            return "#"

    @app.template_filter("format_date")
    def format_date_filter(dt):
        from services.date_utils import format_date

        return format_date(dt)

    @app.template_filter("reading_time")
    def reading_time_filter(article):
        """Return a human reading time for an article.

        The word count is derived from the article body rather than stored:
        a derived value does not belong in a column, and the body is the
        thing the reader is about to read.
        """
        from services.article_provenance import reading_time_minutes

        minutes = reading_time_minutes(article)
        if not minutes:
            return ""
        if minutes == 1:
            return "1 min read"
        return f"{minutes} min read"

    @app.template_filter("agent_provenance")
    def agent_provenance_filter(article):
        """Return the machine-provenance view model, or None."""
        from services.article_provenance import agent_provenance

        return agent_provenance(article)

    @app.template_filter("agent_name")
    def agent_name_filter(article):
        """Return the name the site attributes this article's summary to.

        An operator can set a site-wide agent name and a per-topic
        override. Without one, the article names the model that wrote it.
        """
        from services.agent_identity import agent_display_name

        return agent_display_name(article)


def _register_markup_filters(app):
    """Register the filters that render LLM-authored article content."""

    @app.template_filter("body_html")
    def body_html_filter(value):
        """Render an article body (Markdown or HTML) as sanitized HTML."""
        from markupsafe import Markup

        from services.markup import render_body

        if not value:
            return Markup("")
        return Markup(render_body(str(value)))

    @app.template_filter("inline_html")
    def inline_html_filter(value):
        """Render Markdown as sanitized HTML without a wrapping paragraph."""
        from markupsafe import Markup

        from services.markup import render_inline

        if not value:
            return Markup("")
        return Markup(render_inline(str(value)))

    @app.template_filter("markdown_html")
    def markdown_html_filter(value):
        """Render Markdown as sanitized block HTML."""
        from markupsafe import Markup

        from services.markup import render_markdown

        if not value:
            return Markup("")
        return Markup(render_markdown(str(value)))


def _register_template_globals(app):
    """Register the global helpers templates can call."""

    @app.template_global("now")
    def now_global():
        """Return the current UTC time.

        The value is naive on purpose. ``db.DateTime`` columns are declared
        without a timezone and SQLite returns them naive, so an aware value
        here would raise ``TypeError: can't subtract offset-naive and
        offset-aware datetimes`` the moment a template compares the two.
        """
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).replace(tzinfo=None)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_CONFIG", "development")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config[config_name])

    # Overlay shared config loader values (ainews_config). This bridges
    # the shared config system with Flask's app.config dict. The loader
    # returns empty dict on failure so existing behavior is never broken.
    from config import load_from_shared_loader
    shared_overrides = load_from_shared_loader()
    if shared_overrides:
        app.config.update(shared_overrides)

    # Secrets supplied through the process environment must remain authoritative.
    # The shared loader can contain empty placeholders, which must not disable
    # admin login or replace runtime secret values.
    for secret_key in ("SECRET_KEY", "ADMIN_PASSWORD", "CELERY_TASK_SECRET"):
        if secret_key in os.environ:
            app.config[secret_key] = os.environ[secret_key]

    # Local development and test servers are served over plain HTTP.
    # Keep their session cookie compatible with localhost; production stays secure.
    if config_name in {"development", "testing"}:
        app.config["SESSION_COOKIE_SECURE"] = False

    # Scope the shared response cache to this application's database, so two
    # deployments that share a Redis instance never read each other's cached
    # documents.
    from services.cache import scope_for_database, set_cache_scope

    set_cache_scope(
        scope_for_database(app.config.get("SQLALCHEMY_DATABASE_URI", "") or "")
    )

    # Setup structured logging
    setup_logging(
        app,
        level=logging.DEBUG if config_name == "development" else logging.INFO,
        config_name=config_name,
    )

    # Validate configuration and emit warnings
    _validate_config(app, config_name)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Setup security (Talisman, CSP, compression)
    _setup_security(app)

    # Setup middleware (before/after request handlers)
    _setup_middleware(app)

    # Setup database (migrations, SQLite pragmas, query logging, seed)
    _setup_database(app, config_name)

    # Register blueprints
    _register_blueprints(app)

    # Register error handlers
    _register_error_handlers(app)

    # Register template filters
    _register_template_filters(app)
    _register_markup_filters(app)
    _register_template_globals(app)

    # Initialize tool registry
    from services.subagent import initialize_tool_registry

    initialize_tool_registry()

    # Build the theme registry (Phase 2). The registry is independent of the
    # database / Celery / LLM providers, so it lives here rather than next to
    # the other subsystems. Failures degrade gracefully to the emergency theme.
    from services.themes import build_app_registry

    build_app_registry(app)

    return app

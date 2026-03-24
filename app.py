import os
import logging
from flask import Flask
from sqlalchemy import event
from config import config
from extensions import db, limiter, csrf, migrate
from logging_config import setup_logging


def _seed_share_configs():
    from models import ShareConfig

    defaults = [
        {"platform_key": "x", "label": "X (Twitter)", "url_template": "https://twitter.com/intent/tweet?url={url}&text={title}", "icon_name": "x", "sort_order": 1},
        {"platform_key": "facebook", "label": "Facebook", "url_template": "https://www.facebook.com/sharer/sharer.php?u={url}", "icon_name": "facebook", "sort_order": 2},
        {"platform_key": "linkedin", "label": "LinkedIn", "url_template": "https://www.linkedin.com/sharing/share-offsite/?url={url}", "icon_name": "linkedin", "sort_order": 3},
        {"platform_key": "reddit", "label": "Reddit", "url_template": "https://reddit.com/submit?url={url}&title={title}", "icon_name": "reddit", "sort_order": 4},
    ]
    for d in defaults:
        existing = ShareConfig.query.filter_by(platform_key=d["platform_key"]).first()
        if not existing:
            db.session.add(ShareConfig(**d))
    db.session.commit()


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_CONFIG", "development")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config[config_name])

    # Setup structured logging
    setup_logging(app, level=logging.DEBUG if config_name == "development" else logging.INFO)

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
    )

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

        # Use migrations in production, create_all in development
        if config_name == "production":
            migrate.init_app(app, db)
        else:
            db.create_all()

        _seed_share_configs()

    from routes.public import public_bp
    from routes.admin import admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.template_filter("urlencode")
    def urlencode_filter(value):
        from urllib.parse import quote
        return quote(str(value), safe="")

    @app.template_filter("safe_href")
    def safe_href_filter(value):
        """Return URL only if it uses an http/https scheme."""
        if not value:
            return "#"
        url = str(value).strip().lower()
        if url.startswith(("http://", "https://")):
            return value
        return "#"

    return app

"""Public-facing routes.

Blueprint: public_bp

Submodules:
- feeds: index, topic, tag, RSS feeds, sitemap
- subscribe: subscribe, unsubscribe, verify
- links: article detail, short URLs, share tracking
"""

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
    session,
)

from services.config_cache import get_config_cache

logger = logging.getLogger(__name__)

public_bp = Blueprint("public", __name__)


def _render_feed_or_page(ctx: dict, full_template: str) -> str:
    """Render HTMX partial or full page based on request type."""
    if request.headers.get("HX-Request"):
        if ctx.get("page", 1) > 1:
            return render_template("partials/cards.html", **ctx)
        return render_template("partials/feed.html", **ctx)
    return render_template(full_template, **ctx)


def _get_categories() -> list[str]:
    from schemas.topic import load_topics

    return get_config_cache().get(
        "categories", lambda: list(load_topics().topics.keys()), ttl=300,
    )


def _get_topic_icons() -> dict[str, str]:
    def _load() -> dict[str, str]:
        try:
            from schemas.topic import load_topics

            topics = load_topics().topics
            return {k: v.icon for k, v in topics.items() if v.icon}
        except Exception:
            logger.exception("Failed to load topic icons")
            return {}

    return get_config_cache().get("topic_icons", _load, ttl=300)


def _get_tag_cloud() -> list[dict]:
    def _load() -> list[dict]:
        from sqlalchemy import func

        from extensions import db
        from models import Tag, article_tags

        results = (
            db.session.query(
                Tag.id,
                Tag.name,
                Tag.slug,
                func.count(article_tags.c.article_id).label("count"),
            )
            .outerjoin(article_tags, Tag.id == article_tags.c.tag_id)
            .group_by(Tag.id)
            .order_by(func.count(article_tags.c.article_id).desc())
            .all()
        )

        return [
            {"id": r.id, "name": r.name, "slug": r.slug, "count": r.count}
            for r in results
        ]

    return get_config_cache().get("tag_cloud", _load, ttl=600)


def _get_share_configs() -> list[dict]:
    def _load() -> list[dict]:
        from models import ShareConfig

        configs = (
            ShareConfig.query.filter_by(active=True)
            .order_by(ShareConfig.sort_order)
            .all()
        )
        return [
            {
                "platform_key": c.platform_key,
                "label": c.label,
                "url_template": c.url_template,
                "icon_name": c.icon_name,
                "sort_order": c.sort_order,
            }
            for c in configs
        ]

    return get_config_cache().get("share_configs", _load, ttl=300)


@public_bp.route("/health")
def health() -> tuple[Response, int]:
    from services.health import run_health_checks

    detailed = request.args.get("detailed", "false").lower() == "true"
    if detailed and not session.get("admin"):
        detailed = False
    result = run_health_checks(include_celery=True, detailed=detailed)
    code = 200 if result.is_healthy else 503
    return jsonify(result.to_dict()), code


# Import submodules to register routes
# These must come after Blueprint creation to avoid circular imports
from routes.public import feeds as feeds  # noqa: E402
from routes.public import links as links  # noqa: E402
from routes.public import subscribe as subscribe  # noqa: E402

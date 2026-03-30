from flask import (
    Blueprint,
    render_template,
    request,
    Response,
    redirect,
    jsonify,
    current_app,
)
from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy.exc import SQLAlchemyError
import redis.exceptions
from models import Article, Tag, ShareConfig, ArticleMetric
from extensions import limiter, csrf
from constants import PER_PAGE_PUBLIC, PipelineStatus
from services.article import (
    parse_article_json,
    parse_articles,
    track_metric,
    get_articles_paginated,
)
from services.utils import is_valid_email
from services.config_cache import get_config_cache
from routes import limit_content_length
import logging
import secrets

logger = logging.getLogger(__name__)

public_bp = Blueprint("public", __name__)
PER_PAGE = PER_PAGE_PUBLIC


def _render_feed_or_page(ctx: dict[str, Any], full_template: str) -> str:
    """Render HTMX partial or full page based on request type."""
    if request.headers.get("HX-Request"):
        if ctx.get("page", 1) > 1:
            return render_template("partials/cards.html", **ctx)
        return render_template("partials/feed.html", **ctx)
    return render_template(full_template, **ctx)


def _get_categories() -> list[str]:
    from schemas.topic import load_topics

    return get_config_cache().get(
        "categories", lambda: list(load_topics().topics.keys()), ttl=300
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


def _get_tag_cloud() -> list[dict[str, Any]]:
    def _load() -> list[dict[str, Any]]:
        from sqlalchemy import func
        from extensions import db
        from models import article_tags

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

    return get_config_cache().get("tag_cloud", _load, ttl=60)


def _get_top_impact(limit: int = 3) -> list:
    from sqlalchemy import or_

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return (
        Article.query.filter(
            Article.pipeline_status == PipelineStatus.DONE,
            Article.impact_score > 0,
            or_(
                Article.original_published_at >= cutoff,
                Article.original_published_at.is_(None),
            ),
            Article.created_at >= cutoff,
        )
        .order_by(Article.impact_score.desc())
        .limit(limit)
        .all()
    )


def _get_share_configs() -> list[dict[str, Any]]:
    def _load() -> list[dict[str, Any]]:
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


@public_bp.route("/")
def index():
    page = max(1, request.args.get("page", 1, type=int))
    category = request.args.get("category", "", type=str).strip()
    query = request.args.get("q", "", type=str).strip()

    articles, has_next, next_page = get_articles_paginated(
        page=page,
        per_page=PER_PAGE,
        category=category if category else None,
        query=query if query else None,
    )

    share_configs = _get_share_configs()

    ctx = dict(
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        category=category,
        query=query,
        categories=_get_categories(),
        topic_icons=_get_topic_icons(),
        top_impact=parse_articles(_get_top_impact())
        if page == 1 and not category and not query
        else [],
        newsletter_type="main",
        share_configs=share_configs,
    )

    return _render_feed_or_page(ctx, "index.html")


@public_bp.route("/topic/<category>")
def topic_feed(category):
    page = max(1, request.args.get("page", 1, type=int))

    from schemas.topic import load_topics

    topics = load_topics().topics
    topic_def = topics.get(category)

    articles, has_next, next_page = get_articles_paginated(
        page=page,
        per_page=PER_PAGE,
        category=category,
    )

    share_configs = _get_share_configs()

    ctx = dict(
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        category=category,
        query="",
        categories=_get_categories(),
        topic_icons=_get_topic_icons(),
        topic_def=topic_def,
        newsletter_type=category,
        share_configs=share_configs,
    )

    return _render_feed_or_page(ctx, "topic.html")


@public_bp.route("/article/<int:article_id>")
def article_detail(article_id):
    from schemas.topic import load_topics
    from services.related import find_related_articles

    article = Article.query.get_or_404(article_id)
    parse_article_json(article)

    # Track page load
    track_metric(article_id, ArticleMetric.page_loads)

    topics = load_topics().topics
    topic_def = topics.get(article.category) if article.category else None
    max_key_points = 5
    related = parse_articles(find_related_articles(article, limit=5))
    share_configs = _get_share_configs()

    ctx = dict(
        article=article,
        topic_def=topic_def,
        max_key_points=max_key_points,
        related_articles=related,
        share_configs=share_configs,
    )
    if request.headers.get("HX-Request"):
        response = render_template("partials/article_detail.html", **ctx)
    else:
        response = render_template("article.html", **ctx)

    # Add cache headers - short TTL since article content can be edited
    from flask import make_response

    if not isinstance(response, Response):
        resp = make_response(response)
    else:
        resp = response
    resp.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    if article.updated_at:
        resp.headers["Last-Modified"] = article.updated_at.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
    return resp


@public_bp.route("/tag/<slug>")
def tag_feed(slug):
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))

    tag = Tag.query.filter_by(slug=slug).first_or_404()

    q = Article.query.filter(
        Article.tags.any(Tag.id == tag.id),
        Article.pipeline_status.in_(["done", "skipped"]),
    ).order_by(Article.created_at.desc())

    articles, has_next, next_page = paginate_query(q, page, PER_PAGE)
    parse_articles(articles)

    share_configs = _get_share_configs()

    ctx = dict(
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        category="",
        query="",
        categories=_get_categories(),
        topic_icons=_get_topic_icons(),
        tag=tag,
        all_tags=_get_tag_cloud(),
        tag_slug=slug,
        share_configs=share_configs,
    )

    return _render_feed_or_page(ctx, "tag.html")


# ──────────────────────────────────────────────
#  Short URLs + Share Tracking
# ──────────────────────────────────────────────


@public_bp.route("/s/<short_id>")
def short_url_redirect(short_id):
    article = Article.query.filter_by(short_id=short_id).first_or_404()
    track_metric(article.id, ArticleMetric.share_link_views)
    return redirect(f"/article/{article.id}")


@public_bp.route("/a/<short_id>")
def short_url_tracking_page(short_id):
    article = Article.query.filter_by(short_id=short_id).first_or_404()
    parse_article_json(article)
    track_metric(article.id, ArticleMetric.share_link_views)
    share_configs = _get_share_configs()
    return render_template(
        "share_redirect.html",
        article=article,
        share_configs=share_configs,
    )


@public_bp.route("/api/track/share-click/<int:article_id>", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute")
def track_share_click(article_id):
    Article.query.get_or_404(article_id)
    track_metric(article_id, ArticleMetric.share_button_clicks)
    return "", 204


# ──────────────────────────────────────────────
#  Feeds
# ──────────────────────────────────────────────


@public_bp.route("/health")
def health():
    from extensions import db
    from sqlalchemy import text
    from services.limiter import get_limiter
    from celery_app import celery_app

    checks = {}
    overall = "ok"

    # Database check
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "error"
        overall = "degraded"

    # Redis check
    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        checks["redis"] = "ok"
    except redis.exceptions.RedisError:
        checks["redis"] = "error"
        overall = "degraded"

    # Celery workers check
    try:
        inspect = celery_app.control.inspect()
        # Ping all workers
        ping_response = inspect.ping()
        if ping_response and any(ping_response.values()):
            checks["celery"] = "ok"
        else:
            checks["celery"] = "no_workers"
            # missing workers is not considered degradation for health endpoint
    except Exception:
        logger.exception("Health check: Celery inspect failed")
        checks["celery"] = "error"
        overall = "degraded"

    # Rate limiter check
    limiter_ok = get_limiter().is_healthy()
    checks["limiter"] = "ok" if limiter_ok else "degraded"
    if not limiter_ok:
        overall = "degraded"

    code = 200 if overall == "ok" else 503
    return jsonify({"status": overall, "checks": checks}), code


@public_bp.route("/feed")
def feed_all():
    from services.rss import generate_rss_feed
    from services.cache import get_response_cache

    cache = get_response_cache()
    site_url = request.host_url.rstrip("/")
    cache_key = f"rss_feed:all:{site_url}"

    xml = cache.get(cache_key)
    if xml is None:
        articles = (
            Article.query.filter(Article.pipeline_status.in_(["done", "skipped"]))
            .order_by(Article.created_at.desc())
            .limit(50)
            .all()
        )
        xml = generate_rss_feed(
            articles,
            title="ainews// — Condensed Tech News",
            description="Autonomous AI-curated condensed news across AI, privacy, security, programming, and hardware.",
            site_url=site_url,
        )
        cache.set(cache_key, xml, ttl=120)

    return Response(
        xml,
        mimetype="application/rss+xml",
        headers={"Cache-Control": "public, max-age=120, stale-while-revalidate=600"},
    )


@public_bp.route("/feed/<category>")
def feed_topic(category):
    from services.rss import generate_rss_feed
    from schemas.topic import load_topics
    from services.cache import get_response_cache

    cache = get_response_cache()
    site_url = request.host_url.rstrip("/")
    cache_key = f"rss_feed:{category}:{site_url}"

    xml = cache.get(cache_key)
    if xml is None:
        topics = load_topics().topics
        topic_def = topics.get(category)
        topic_name = topic_def.display_name if topic_def else category

        articles = (
            Article.query.filter(
                Article.category == category,
                Article.pipeline_status.in_(["done", "skipped"]),
            )
            .order_by(Article.created_at.desc())
            .limit(50)
            .all()
        )

        xml = generate_rss_feed(
            articles,
            title=f"ainews// — {topic_name}",
            description=f"Condensed tech news: {topic_name}",
            site_url=site_url,
        )
        cache.set(cache_key, xml, ttl=120)

    return Response(
        xml,
        mimetype="application/rss+xml",
        headers={"Cache-Control": "public, max-age=120, stale-while-revalidate=600"},
    )


@public_bp.route("/sitemap.xml")
def sitemap():
    from services.rss import generate_sitemap
    from collections import namedtuple

    rows = (
        Article.query.filter(Article.pipeline_status.in_(["done", "skipped"]))
        .with_entities(Article.id, Article.created_at)
        .order_by(Article.created_at.desc())
        .limit(200)
        .all()
    )

    _SitemapEntry = namedtuple("SitemapEntry", ["id", "created_at"])
    articles = [_SitemapEntry(id=r.id, created_at=r.created_at) for r in rows]

    site_url = request.host_url.rstrip("/")
    xml = generate_sitemap(articles, site_url=site_url)
    return Response(
        xml,
        mimetype="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ──────────────────────────────────────────────
#  Subscribe / Unsubscribe
# ──────────────────────────────────────────────


@public_bp.route("/subscribe", methods=["POST"])
@limiter.limit("3 per minute")
@limit_content_length(1024)
def subscribe():
    from models import Subscriber
    from extensions import db
    from services.email import send_verification_email

    email = request.form.get("email", "").strip().lower()
    newsletter_type = request.form.get("newsletter_type", "main").strip()

    # Validate newsletter_type against known topic keys
    valid_types = set(_get_categories()) | {"main"}
    if newsletter_type not in valid_types:
        newsletter_type = "main"

    if not is_valid_email(email):
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_error="Please enter a valid email.",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    existing = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(email=email, newsletter_type=newsletter_type)
        .first()
    )

    # Already subscribed and verified
    if existing and existing.active and existing.confirmed_at is not None:
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_success="Already subscribed!",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    unsub_token = secrets.token_urlsafe(32)
    verify_token = secrets.token_urlsafe(32)

    if existing and not existing.active:
        # Reactivate previously unsubscribed subscriber — needs re-verification
        existing.active = True
        existing.unsubscribe_token = unsub_token
        existing.verification_token = verify_token
        existing.confirmed_at = None
    elif existing and existing.active and existing.confirmed_at is None:
        # Already pending verification — rotate token and resend
        existing.verification_token = verify_token
        unsub_token = existing.unsubscribe_token
    else:
        subscriber = Subscriber(
            email=email,
            newsletter_type=newsletter_type,
            unsubscribe_token=unsub_token,
            verification_token=verify_token,
        )
        db.session.add(subscriber)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to subscribe %s", email)
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_error="Something went wrong. Please try again.",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    site_url = request.host_url.rstrip("/")
    verification_url = f"{site_url}/verify/{verify_token}"
    unsubscribe_url = f"{site_url}/unsubscribe/{unsub_token}"
    email_failed = False
    try:
        send_verification_email(
            email, newsletter_type, verification_url, unsubscribe_url
        )
    except Exception as e:
        logger.warning(f"Verification email failed for {email}: {e}")
        email_failed = True

    if request.headers.get("HX-Request"):
        return render_template(
            "partials/subscribe_box.html",
            subscribe_info="Check your email to confirm your subscription."
            if not email_failed
            else None,
            subscribe_warning="Verification email could not be sent. Please try again later."
            if email_failed
            else None,
            newsletter_type=newsletter_type,
        )
    return redirect("/")


@public_bp.route("/unsubscribe/<token>")
@limiter.limit("20 per minute")
def unsubscribe(token):
    """Show unsubscribe confirmation page (GET)."""
    from models import Subscriber

    subscriber = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(unsubscribe_token=token, active=True)
        .first()
    )

    return render_template(
        "unsubscribe.html", token=token, found=subscriber is not None
    )


@public_bp.route("/unsubscribe/<token>", methods=["POST"])
@limiter.limit("10 per minute")
def unsubscribe_confirm(token):
    """Process unsubscribe request (POST with CSRF protection)."""
    from models import Subscriber
    from extensions import db

    subscriber = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(unsubscribe_token=token, active=True)
        .first()
    )

    commit_failed = False
    if subscriber:
        subscriber.active = False
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception(f"Failed to unsubscribe token {token}")
            commit_failed = True

    return render_template(
        "unsubscribe.html",
        token=token,
        found=subscriber is not None,
        confirmed=subscriber is not None and not commit_failed,
        error=commit_failed,
    )


@public_bp.route("/verify/<token>")
@limiter.limit("20 per minute")
def verify(token):
    """Verify a subscriber's email address via token link."""
    from models import Subscriber
    from extensions import db

    subscriber = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter(Subscriber.confirmed_at.is_(None))
        .filter_by(verification_token=token)
        .first()
    )

    if not subscriber:
        return render_template("verify.html", found=False)

    expiry = current_app.config.get("VERIFICATION_EXPIRY_SECONDS", 3600)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=expiry)
    subscribed_at = subscriber.subscribed_at
    if subscribed_at.tzinfo is None:
        subscribed_at = subscribed_at.replace(tzinfo=timezone.utc)
    if subscribed_at < cutoff:
        return render_template("verify.html", found=False, expired=True)

    subscriber.confirmed_at = datetime.now(timezone.utc)
    subscriber.verification_token = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to verify subscriber token %s", token)
        return render_template("verify.html", found=False)

    # Send welcome email
    site_url = request.host_url.rstrip("/")
    unsubscribe_url = f"{site_url}/unsubscribe/{subscriber.unsubscribe_token}"
    try:
        from services.email import send_welcome_email

        send_welcome_email(
            subscriber.email, subscriber.newsletter_type, unsubscribe_url
        )
    except Exception as e:
        logger.warning(f"Welcome email failed for {subscriber.email}: {e}")

    return render_template("verify.html", found=True, subscriber=subscriber)

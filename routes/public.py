from flask import Blueprint, render_template, request, Response, redirect, jsonify
from datetime import datetime, timezone, timedelta
from models import Article, Tag, ShareConfig, ArticleMetric
from extensions import limiter, csrf, get_redis
from constants import PER_PAGE_PUBLIC
from services.article import (
    parse_article_json,
    parse_articles,
    track_metric,
    get_articles_paginated,
)
import json
import logging
import secrets

logger = logging.getLogger(__name__)

public_bp = Blueprint("public", __name__)
PER_PAGE = PER_PAGE_PUBLIC


def _cached(key, ttl_seconds, fn):
    try:
        r = get_redis()
        cached = r.get(f"ainews:cache:{key}")
        if cached is not None:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Cache read failed for {key}: {e}")

    value = fn()

    try:
        r = get_redis()
        r.setex(f"ainews:cache:{key}", ttl_seconds, json.dumps(value))
    except Exception as e:
        logger.warning(f"Cache write failed for {key}: {e}")

    return value


def _get_categories():
    from schemas.topic import load_topics

    return _cached("categories", 300, lambda: list(load_topics().topics.keys()))


def _get_topic_icons():
    def _load():
        try:
            from schemas.topic import load_topics

            topics = load_topics().topics
            return {k: v.icon for k, v in topics.items() if v.icon}
        except Exception:
            return {}

    return _cached("topic_icons", 300, _load)


def _get_tag_cloud():
    def _load():
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

    return _cached("tag_cloud", 60, _load)


def _get_top_impact(limit: int = 3) -> list:
    from sqlalchemy import or_

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return (
        Article.query.filter(
            Article.pipeline_status == "done",
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


def _get_share_configs():
    def _load():
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

    return _cached("share_configs", 300, _load)


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

    if request.headers.get("HX-Request"):
        if page > 1:
            return render_template("partials/cards.html", **ctx)
        return render_template("partials/feed.html", **ctx)
    return render_template("index.html", **ctx)


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

    if request.headers.get("HX-Request"):
        if page > 1:
            return render_template("partials/cards.html", **ctx)
        return render_template("partials/feed.html", **ctx)
    return render_template("topic.html", **ctx)


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
        return render_template("partials/article_detail.html", **ctx)
    return render_template("article.html", **ctx)


@public_bp.route("/tag/<slug>")
def tag_feed(slug):
    page = max(1, request.args.get("page", 1, type=int))

    tag = Tag.query.filter_by(slug=slug).first_or_404()

    q = Article.query.filter(
        Article.tags.any(Tag.id == tag.id),
        Article.pipeline_status.in_(["done", "skipped"]),
    ).order_by(Article.created_at.desc())

    articles = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE + 1).all()
    has_next = len(articles) > PER_PAGE
    if has_next:
        articles = articles[:PER_PAGE]
    parse_articles(articles)

    share_configs = _get_share_configs()

    ctx = dict(
        articles=articles,
        has_next=has_next,
        next_page=page + 1,
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

    if request.headers.get("HX-Request"):
        if page > 1:
            return render_template("partials/cards.html", **ctx)
        return render_template("partials/feed.html", **ctx)
    return render_template("tag.html", **ctx)


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
    article = Article.query.get_or_404(article_id)
    track_metric(article_id, ArticleMetric.share_button_clicks)
    return "", 204


# ──────────────────────────────────────────────
#  Feeds
# ──────────────────────────────────────────────


@public_bp.route("/health")
def health():
    from extensions import db
    from sqlalchemy import text

    status = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        status = "degraded"
    code = 200 if status == "ok" else 503
    return jsonify({"status": status}), code


@public_bp.route("/feed")
def feed_all():
    from services.rss import generate_rss_feed

    articles = (
        Article.query.filter(Article.pipeline_status.in_(["done", "skipped"]))
        .order_by(Article.created_at.desc())
        .limit(50)
        .all()
    )

    site_url = request.host_url.rstrip("/")
    xml = generate_rss_feed(
        articles,
        title="ainews// — Condensed Tech News",
        description="Autonomous AI-curated condensed news across AI, privacy, security, programming, and hardware.",
        site_url=site_url,
    )
    return Response(
        xml,
        mimetype="application/rss+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_bp.route("/feed/<category>")
def feed_topic(category):
    from services.rss import generate_rss_feed
    from schemas.topic import load_topics

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

    site_url = request.host_url.rstrip("/")
    xml = generate_rss_feed(
        articles,
        title=f"ainews// — {topic_name}",
        description=f"Condensed tech news: {topic_name}",
        site_url=site_url,
    )
    return Response(
        xml,
        mimetype="application/rss+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_bp.route("/sitemap.xml")
def sitemap():
    from services.rss import generate_sitemap

    articles = (
        Article.query.filter(Article.pipeline_status.in_(["done", "skipped"]))
        .order_by(Article.created_at.desc())
        .limit(200)
        .all()
    )

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
def subscribe():
    from models import Subscriber
    from extensions import db
    from services.email import send_confirmation_email

    email = request.form.get("email", "").strip().lower()
    newsletter_type = request.form.get("newsletter_type", "main").strip()

    if not email or "@" not in email:
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_error="Please enter a valid email.",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    existing = Subscriber.query.filter_by(
        email=email, newsletter_type=newsletter_type
    ).first()

    if existing and existing.active:
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_success=f"Already subscribed!",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    token = secrets.token_urlsafe(32)

    if existing and not existing.active:
        existing.active = True
        existing.unsubscribe_token = token
    else:
        subscriber = Subscriber(
            email=email,
            newsletter_type=newsletter_type,
            unsubscribe_token=token,
        )
        db.session.add(subscriber)

    try:
        db.session.commit()
    except Exception:
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
    unsubscribe_url = f"{site_url}/unsubscribe/{token}"
    try:
        send_confirmation_email(email, newsletter_type, unsubscribe_url)
    except Exception as e:
        logger.warning(f"Confirmation email failed for {email}: {e}")

    if request.headers.get("HX-Request"):
        return render_template(
            "partials/subscribe_box.html",
            subscribe_success=f"Subscribed!",
            newsletter_type=newsletter_type,
        )
    return redirect("/")


@public_bp.route("/unsubscribe/<token>")
def unsubscribe(token):
    from models import Subscriber
    from extensions import db

    subscriber = Subscriber.query.filter_by(
        unsubscribe_token=token, active=True
    ).first()

    if subscriber:
        subscriber.active = False
        db.session.commit()

    return render_template("unsubscribe.html", found=subscriber is not None)

"""Short URL, article detail, and share tracking routes."""

import logging
import re

from flask import Response, abort, make_response, redirect, render_template, request
from sqlalchemy.orm import joinedload

from extensions import db
from models import Article, ArticleMetric
from routes.decorators import validate_csrf_token
from routes.public import (
    _get_categories,
    _rail_stats,
    _get_share_configs,
    _request_variant,
    public_bp,
)
from services.article import parse_article_json, track_metric
from services.publication import published_article_query

logger = logging.getLogger(__name__)

_SHORT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


@public_bp.route("/article/<public_id>")
def article_detail(public_id: str) -> Response:
    from schemas.topic import load_topics
    from services.article import parse_articles
    from services.cache import get_response_cache
    from services.related import find_related_articles_cached

    cache = get_response_cache()
    from services.publication import get_public_article
    article = get_public_article(public_id)
    if article is None:
        abort(404)
    article_id = article.id
    cache_key = f"pub:article_detail:view:{_request_variant()}:{public_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        resp = make_response(cached)
        resp.headers["Cache-Control"] = (
            "public, max-age=300, stale-while-revalidate=600"
        )
        return resp

    article = db.session.scalar(published_article_query().options(
        joinedload(Article.tags), joinedload(Article.source),  # type: ignore[arg-type]
    ).where(Article.id == article_id))
    if article is None:
        abort(404)
    parse_article_json(article)

    track_metric(article_id, ArticleMetric.page_loads)

    topics = load_topics().topics
    topic_def = topics.get(article.category) if article.category else None
    max_key_points = 5
    related = parse_articles(find_related_articles_cached(article, limit=5))
    share_configs = _get_share_configs()

    word_count = 0
    if article.final_article:
        try:
            import json
            fa_data = json.loads(article.final_article)
            text_fields = [fa_data.get("body", ""), fa_data.get("tldr", ""), fa_data.get("why_it_matters", ""), fa_data.get("what_to_watch", "")]
            text_content = " ".join(str(f) for f in text_fields if f)
            word_count = len(text_content.split())
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed to parse final_article for reading time: %s", e)
            word_count = 0
    reading_time = max(1, word_count // 200)

    ctx = {
        "article": article,
        "topic_def": topic_def,
        "max_key_points": max_key_points,
        "related_articles": related,
        "share_configs": share_configs,
        "reading_time": reading_time,
        # The navigation lists the topic taxonomy. Without it the article
        # page renders a shorter header than every other page, so the frame
        # jumps when the reader moves between the feed and an article.
        "categories": _get_categories(),
        # The article page keeps the sidebar so that the page frame does not
        # change when the reader moves between the index, a topic tab and an
        # article.
        "show_rail": True,
        "feed_stats": _rail_stats(),
    }
    if request.headers.get("HX-Request"):
        response = render_template("partials/article_detail.html", **ctx)
    else:
        response = render_template("article.html", **ctx)

    if not isinstance(response, Response):
        resp = make_response(response)
    else:
        resp = response
    resp.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    if article.updated_at:
        resp.headers["Last-Modified"] = article.updated_at.strftime(
            "%a, %d %b %Y %H:%M:%S GMT",
        )
    # ResponseCache stores JSON values; cache the rendered HTML as text rather
    # than the bytes returned by Response.get_data().
    cache.set(cache_key, resp.get_data(as_text=True), ttl=300)
    return resp


@public_bp.route("/article/<int:article_id>")
def legacy_article_detail(article_id: int) -> Response:
    """Temporary legacy URL resolution; set PUBLIC_LEGACY_NUMERIC_ARTICLE_URLS=false to harden."""
    from flask import current_app
    if not current_app.config.get("PUBLIC_LEGACY_NUMERIC_ARTICLE_URLS", False):
        abort(404)
    article = db.session.scalar(published_article_query().where(Article.id == article_id))
    if article is None:
        abort(404)
    return redirect(f"/article/{article.public_id}", code=301)  # type: ignore[return-value]


@public_bp.route("/s/<short_id>")
def short_url_redirect(short_id: str) -> Response:
    if not _SHORT_ID_RE.match(short_id):
        abort(404)
    article = db.session.scalar(published_article_query().where(Article.short_id == short_id))
    if article is None:
        abort(404)
    track_metric(article.id, ArticleMetric.share_link_views)
    return redirect(f"/article/{article.public_id}")  # type: ignore[return-value]


@public_bp.route("/a/<short_id>")
def short_url_tracking_page(short_id: str) -> str:
    if not _SHORT_ID_RE.match(short_id):
        abort(404)
    article = db.session.scalar(published_article_query().where(Article.short_id == short_id))
    if article is None:
        abort(404)
    parse_article_json(article)
    track_metric(article.id, ArticleMetric.share_link_views)
    share_configs = _get_share_configs()
    return render_template(
        "share_redirect.html",
        article=article,
        share_configs=share_configs,
    )


# Note: This endpoint is CSRF-protected via Flask-WTF but the read-only nature
# (metrics recording only) limits impact. The endpoint is also rate-limited
# globally via Flask-Limiter (configured in extensions.py).


@public_bp.route("/api/v1/track/share-click/<public_id>", methods=["POST"])
@validate_csrf_token
def track_share_click(public_id: str) -> tuple[dict, int]:
    article = db.session.scalar(published_article_query().where(Article.public_id == public_id))
    if article is None:
        abort(404)
    track_metric(article.id, ArticleMetric.share_button_clicks)
    return {"success": True}, 204


@public_bp.route("/track/newsletter-click/<public_id>")
def track_newsletter_click(public_id: str) -> Response:
    article = db.session.scalar(published_article_query().where(Article.public_id == public_id))
    if article is None:
        abort(404)
    track_metric(article.id, ArticleMetric.newsletter_clicks)
    return redirect(f"/article/{article.public_id}", code=302)  # type: ignore[return-value]

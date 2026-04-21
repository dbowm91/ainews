"""Short URL, article detail, and share tracking routes."""

import logging

from flask import request, render_template, redirect, make_response, Response
from sqlalchemy.orm import joinedload

from models import Article, ArticleMetric
from services.article import parse_article_json, track_metric
from routes.public import (
    public_bp,
    _get_share_configs,
)

logger = logging.getLogger(__name__)


@public_bp.route("/article/<int:article_id>")
def article_detail(article_id: int) -> Response:
    from schemas.topic import load_topics
    from services.related import find_related_articles
    from services.article import parse_articles
    from services.cache import get_response_cache

    cache = get_response_cache()
    cache_key = f"article_detail:{article_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        resp = make_response(cached)
        resp.headers["Cache-Control"] = (
            "public, max-age=300, stale-while-revalidate=600"
        )
        return resp

    article = Article.query.options(
        joinedload(Article.tags),
        joinedload(Article.source)
    ).get_or_404(article_id)
    parse_article_json(article)

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

    if not isinstance(response, Response):
        resp = make_response(response)
    else:
        resp = response
    resp.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    if article.updated_at:
        resp.headers["Last-Modified"] = article.updated_at.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
    cache.set(cache_key, resp.get_data(), ttl=300)
    return resp


@public_bp.route("/s/<short_id>")
def short_url_redirect(short_id: str) -> Response:
    article = Article.query.filter_by(short_id=short_id).first_or_404()
    track_metric(article.id, ArticleMetric.share_link_views)
    return redirect(f"/article/{article.id}")


@public_bp.route("/a/<short_id>")
def short_url_tracking_page(short_id: str) -> str:
    article = Article.query.filter_by(short_id=short_id).first_or_404()
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


@public_bp.route("/api/track/share-click/<int:article_id>", methods=["POST"])
def track_share_click(article_id: int) -> tuple[str, int]:
    track_metric(article_id, ArticleMetric.share_button_clicks)
    return "", 204

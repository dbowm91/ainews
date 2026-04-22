"""Feed and content routes: index, topics, tags, RSS, sitemap."""

from flask import request, Response
from datetime import datetime, timezone, timedelta
from collections import namedtuple
from sqlalchemy.orm import joinedload

from models import Article, Tag
from constants import PER_PAGE_PUBLIC, PipelineStatus
from services.article import (
    parse_articles,
    get_articles_paginated,
)
from routes.public import (
    public_bp,
    _render_feed_or_page,
    _get_categories,
    _get_topic_icons,
    _get_tag_cloud,
    _get_share_configs,
)

PER_PAGE = PER_PAGE_PUBLIC


def _get_top_impact(limit: int = 3) -> list[Article]:
    from sqlalchemy import or_
    from services.cache import get_response_cache

    cache = get_response_cache()
    cache_key = f"top_impact:{limit}"

    cached_ids = cache.get(cache_key)
    if cached_ids is not None:
        if not cached_ids:
            return []
        articles = Article.query.filter(Article.id.in_(cached_ids)).all()
        return sorted(articles, key=lambda a: cached_ids.index(a.id)) if articles else []

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    articles = (
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
    if articles:
        cache.set(cache_key, [a.id for a in articles], ttl=300)
    return articles


@public_bp.route("/")
def index() -> str:
    from services.cache import get_response_cache

    page = max(1, request.args.get("page", 1, type=int))
    category = request.args.get("category", "", type=str).strip()
    query = request.args.get("q", "", type=str).strip()

    cache = get_response_cache()
    cache_key = f"index:page:{page}:cat:{category}:q:{query}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

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

    result = _render_feed_or_page(ctx, "index.html")
    if page == 1 and not category and not query:
        cache.set(cache_key, result, ttl=300)
    return result


@public_bp.route("/topic/<category>")
def topic_feed(category: str) -> str:
    from services.cache import get_response_cache

    page = max(1, request.args.get("page", 1, type=int))

    cache = get_response_cache()
    cache_key = f"topic:{category}:page:{page}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

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

    result = _render_feed_or_page(ctx, "topic.html")
    if page == 1:
        cache.set(cache_key, result, ttl=300)
    return result


@public_bp.route("/tag/<slug>")
def tag_feed(slug: str) -> str:
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))

    tag = Tag.query.filter_by(slug=slug).first_or_404()

    q = (
        Article.query.options(joinedload(Article.source), joinedload(Article.tags))
        .filter(
            Article.tags.any(Tag.id == tag.id),
            Article.pipeline_status.in_([PipelineStatus.DONE, PipelineStatus.SKIPPED]),
        )
        .order_by(Article.created_at.desc())
    )

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


@public_bp.route("/feed")
def feed_all() -> Response:
    from services.rss import generate_rss_feed
    from services.cache import get_response_cache

    cache = get_response_cache()
    site_url = request.host_url.rstrip("/")
    cache_key = f"rss_feed:all:{site_url}"

    xml = cache.get(cache_key)
    if xml is None:
        articles = (
            Article.query.options(joinedload(Article.source), joinedload(Article.tags))
            .filter(
                Article.pipeline_status.in_(
                    [PipelineStatus.DONE, PipelineStatus.SKIPPED]
                )
            )
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
        cache.set(cache_key, xml, ttl=600)

    return Response(
        xml,
        mimetype="application/rss+xml",
        headers={"Cache-Control": "public, max-age=600, stale-while-revalidate=1200"},
    )


@public_bp.route("/feed/<category>")
def feed_topic(category: str) -> Response:
    from services.rss import generate_rss_feed
    from schemas.topic import load_topics
    from services.cache import get_response_cache
    from flask import abort

    topics = load_topics().topics
    if category not in topics:
        abort(404)

    cache = get_response_cache()
    site_url = request.host_url.rstrip("/")
    cache_key = f"rss_feed:{category}:{site_url}"

    xml = cache.get(cache_key)
    if xml is None:
        topic_def = topics.get(category)
        topic_name = topic_def.display_name if topic_def else category

        articles = (
            Article.query.options(joinedload(Article.source), joinedload(Article.tags))
            .filter(
                Article.category == category,
                Article.pipeline_status.in_(
                    [PipelineStatus.DONE, PipelineStatus.SKIPPED]
                ),
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
        cache.set(cache_key, xml, ttl=600)

    return Response(
        xml,
        mimetype="application/rss+xml",
        headers={"Cache-Control": "public, max-age=600, stale-while-revalidate=1200"},
    )


@public_bp.route("/sitemap.xml")
def sitemap() -> Response:
    from services.rss import generate_sitemap
    from services.config_utils import get_config_with_default

    limit = get_config_with_default("SITEMAP_LIMIT", 200, int)

    rows = (
        Article.query.filter(
            Article.pipeline_status.in_([PipelineStatus.DONE, PipelineStatus.SKIPPED])
        )
        .with_entities(Article.id, Article.created_at)
        .order_by(Article.created_at.desc())
        .limit(limit)
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

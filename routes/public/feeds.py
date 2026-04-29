"""Feed and content routes: index, topics, tags, RSS, sitemap."""

from collections import namedtuple
from datetime import datetime, timedelta, timezone

from flask import Response, request
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from constants import PER_PAGE_PUBLIC, PipelineStatus
from extensions import db
from models import Article, Tag
from routes.public import (
    _get_categories,
    _get_share_configs,
    _get_tag_cloud,
    _get_topic_icons,
    _render_feed_or_page,
    public_bp,
)
from services.article import (
    get_articles_paginated,
    parse_articles,
)

PER_PAGE = PER_PAGE_PUBLIC


def _get_top_impact(limit: int = 3) -> list[Article]:
    from sqlalchemy import or_

    from services.cache import get_response_cache

    cache = get_response_cache()
    cache_key = f"pub:top_impact:{limit}"

    cached_ids = cache.get(cache_key)
    if cached_ids is not None:
        if not cached_ids:
            return []
        from sqlalchemy.orm import joinedload
        articles = (
            Article.query
            .options(joinedload(Article.source), joinedload(Article.tags))
            .filter(Article.id.in_(cached_ids))
            .all()
        )
        return sorted(articles, key=lambda a: cached_ids.index(a.id)) if articles else []

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    from sqlalchemy.orm import joinedload
    articles = (
        Article.query
        .options(joinedload(Article.source))
        .filter(
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
    sort = request.args.get("sort", "recent", type=str).strip()

    cache = get_response_cache()
    cache_key = f"pub:index:page:{page}:cat:{category}:q:{query}:sort:{sort}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    articles, has_next, next_page = get_articles_paginated(
        page=page,
        per_page=PER_PAGE,
        category=category if category else None,
        query=query if query else None,
        sort=sort,
    )

    share_configs = _get_share_configs()

    ctx = dict(
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        category=category,
        query=query,
        sort=sort,
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
    sort = request.args.get("sort", "recent", type=str).strip()

    cache = get_response_cache()
    cache_key = f"pub:topic:{category}:page:{page}:sort:{sort}"

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
        sort=sort,
    )

    share_configs = _get_share_configs()

    ctx = dict(
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        category=category,
        query="",
        sort=sort,
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
    from services.cache import get_response_cache
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))

    cache = get_response_cache()
    cache_key = f"pub:tag:{slug}:page:{page}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    tag = db.first_or_404(select(Tag).filter_by(slug=slug))

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

    result = _render_feed_or_page(ctx, "tag.html")
    if page == 1:
        cache.set(cache_key, result, ttl=300)
    return result


@public_bp.route("/feed")
def feed_all() -> Response:
    from services.cache import get_response_cache
    from services.rss import generate_rss_feed

    cache = get_response_cache()
    site_url = request.host_url.rstrip("/")
    cache_key = f"pub:rss_feed:all:{site_url}"

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
    from flask import abort

    from schemas.topic import load_topics
    from services.cache import get_response_cache
    from services.rss import generate_rss_feed

    topics = load_topics().topics
    if category not in topics:
        abort(404)

    cache = get_response_cache()
    site_url = request.host_url.rstrip("/")
    cache_key = f"pub:rss_feed:{category}:{site_url}"

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
    from services.cache import get_response_cache
    from services.config_utils import get_config_with_default
    from services.rss import generate_sitemap

    cache = get_response_cache()
    cache_key = "pub:sitemap:xml"

    xml = cache.get(cache_key)
    if xml is None:
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
        cache.set(cache_key, xml, ttl=300)

    return Response(
        xml,
        mimetype="application/xml",
        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=600"},
    )

from __future__ import annotations

import json
import logging

from sqlalchemy.exc import SQLAlchemyError

from services.llm.base import ToolDefinition

logger = logging.getLogger(__name__)

# Layering note: tools.py imports directly from models and extensions for runtime
# use (not just type hints). This is a known layering violation per AGENTS.md.
# The alternative would be creating service-layer helpers for each tool, which
# would add significant complexity. Acceptable given constraints.


def _context_tool_get_topic_note(topic: str, source: str | None = None) -> str:
    from services.cache import get_response_cache

    def _fetch_note() -> str:
        from services.context_service import get_topic_note

        try:
            note = get_topic_note(topic, source)
            return note.note if note else "No note found for this topic."
        except (SQLAlchemyError, KeyError, AttributeError) as e:
            logger.error("Tool get_topic_note failed for topic=%s: %s", topic, e)
            return f"Error retrieving topic note: {type(e).__name__}"
        except (ImportError, ValueError, TypeError, AttributeError) as e:
            logger.error("Unexpected error in get_topic_note for %s: %s", topic, e)
            return f"Error retrieving topic note: {type(e).__name__}"

    cache = get_response_cache()
    cache_key = f"topic_note:{topic}:{source or 'none'}"
    return cache.get_or_set(cache_key, _fetch_note, ttl=120)  # type: ignore[no-any-return]


def _context_tool_get_topic_notes_for_topics(topics: list[str]) -> str:
    from services.context_service import get_topic_notes_for_topics

    try:
        result = get_topic_notes_for_topics(topics)
        if not result:
            return "No topic notes found."
        return "\n".join(
            f"Topic: {k}\nNotes: {'; '.join(v)}" for k, v in result.items()
        )
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_topic_notes_for_topics failed: %s", e)
        return f"Error retrieving topic notes: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_topic_notes_for_topics: %s", e)
        return f"Error retrieving topic notes: {type(e).__name__}"


def _context_tool_get_related_articles(
    topics: list[str], exclude_id: int, limit: int = 5,
) -> str:
    from services.cache import get_response_cache

    def _fetch_articles() -> str:
        from services.context_service import get_related_articles_for_edit

        try:
            articles = get_related_articles_for_edit(topics, exclude_id, limit=limit)
            if not articles:
                return "No related articles found."
            return "\n".join(
                f"- {a['title']}: {a.get('summary_snippet', '')[:100]}" for a in articles
            )
        except (SQLAlchemyError, KeyError, AttributeError) as e:
            logger.error("Tool get_related_articles failed: %s", e)
            return f"Error retrieving related articles: {type(e).__name__}"
        except (ImportError, ValueError, TypeError, AttributeError) as e:
            logger.error("Unexpected error in get_related_articles: %s", e)
            return f"Error retrieving related articles: {type(e).__name__}"

    cache = get_response_cache()
    cache_key = f"related_articles:{','.join(sorted(topics))}:{exclude_id}:{limit}"
    return cache.get_or_set(cache_key, _fetch_articles, ttl=120)  # type: ignore[no-any-return]


def _context_tool_get_trend_memory(
    topics: list[str], min_importance: int = 1, max_age_days: int | None = None,
) -> str:
    from services.trend_memory import get_memory_for_topics

    try:
        entries = get_memory_for_topics(topics, min_importance, max_age_days)
        if not entries:
            return "No trend memory found for these topics."
        return "\n".join(
            f"[importance={e.importance}] [{e.topic}] {e.signal}" for e in entries
        )
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_trend_memory failed: %s", e)
        return f"Error retrieving trend memory: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_trend_memory: %s", e)
        return f"Error retrieving trend memory: {type(e).__name__}"


def _context_tool_get_article_by_id(article_id: int) -> str:
    from extensions import db
    from models import Article

    try:
        article = db.session.get(Article, article_id)
        if not article:
            return f'{{"error": "Article {article_id} not found"}}'
        return json.dumps({
            "id": article.id,
            "title": article.title,
            "pipeline_status": article.pipeline_status,
            "impact_score": article.impact_score,
            "created_at": article.created_at.isoformat() if article.created_at else None,
        })
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_article_by_id failed for %s: %s", article_id, e)
        return f'{{"error": "{type(e).__name__}"}}'
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_article_by_id for %s: %s", article_id, e)
        return f'{{"error": "{type(e).__name__}"}}'


def _context_tool_search_articles(query: str, limit: int = 5) -> str:
    from models import Article

    try:
        articles = Article.query.filter(
            Article.original_title.ilike(f"%{query}%"),
        ).limit(limit).all()
        return json.dumps([
            {"id": a.id, "title": a.original_title} for a in articles
        ])
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool search_articles failed: %s", e)
        return f'{{"error": "{type(e).__name__}"}}'
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in search_articles: %s", e)
        return f'{{"error": "{type(e).__name__}"}}'


def _context_tool_get_source_health() -> str:
    from extensions import db
    from models import Source

    try:
        sources = db.session.query(Source).all()
        return json.dumps([{
            "id": s.id,
            "name": s.name,
            "disabled_at": s.disabled_at.isoformat() if s.disabled_at else None,
            "consecutive_failures": s.consecutive_failures,
        } for s in sources])
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_source_health failed: %s", e)
        return f'{{"error": "{type(e).__name__}"}}'
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_source_health: %s", e)
        return f'{{"error": "{type(e).__name__}"}}'


def _context_tool_get_topic_gap_report(
    topics: list[str] | None = None, days: int = 30,
) -> str:
    from services.topic_gap import get_topic_gap_report

    try:
        reports = get_topic_gap_report(topics=topics, days=days)
        if not reports:
            return "No topic gap data available."
        return "\n".join(
            f"[gap={r.gap_score}] {r.topic}: {r.article_count_7d} articles (7d), "
            f"{r.article_count_30d} articles (30d), {r.trend_memory_count} trend entries, "
            f"{r.active_sources} sources, reason: {r.reason}"
            for r in reports
        )
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_topic_gap_report failed: %s", e)
        return f"Error retrieving topic gap report: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_topic_gap_report: %s", e)
        return f"Error retrieving topic gap report: {type(e).__name__}"


def _search_web(query: str, max_results: int = 5) -> str:
    from services.search import search_web

    try:
        results = search_web(query, max_results)
        if not results:
            return "No search results found."
        return "\n".join(f"- {r.title}: {r.snippet[:150]}..." for r in results)
    except (ConnectionError, TimeoutError, ValueError) as e:
        logger.error("Tool search_web failed for '%s': %s", query, e)
        return f"Error performing web search: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in search_web for '%s': %s", query, e)
        return f"Error performing web search: {type(e).__name__}"


def _get_search_provider(provider_id: str | None = None) -> str:
    from services.search import get_search_provider

    try:
        prov = get_search_provider(provider_id)
        return f"Using search provider: {prov.provider_id}"
    except (ValueError, KeyError, AttributeError) as e:
        logger.error("Tool get_search_provider failed: %s", e)
        return f"Error getting search provider: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_search_provider: %s", e)
        return f"Error getting search provider: {type(e).__name__}"


def _context_tool_get_source_performance(
    source_key: str | None = None, days: int = 7,
) -> str:
    from services.source_intelligence import get_source_performance

    try:
        results = get_source_performance(days=days)
        if not results:
            return "No source performance data available."
        return "\n".join(
            f"[{sp.health}] {sp.name} ({sp.source_key}): {sp.articles_created} created, "
            f"{sp.published} published, selection_rate={sp.selection_rate}, "
            f"avg_impact={sp.avg_impact_score}"
            for sp in results
        )
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_source_performance failed: %s", e)
        return f"Error retrieving source performance: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_source_performance: %s", e)
        return f"Error retrieving source performance: {type(e).__name__}"


def _context_tool_get_quality_report(article_id: int) -> str:
    from services.quality_report_service import get_quality_report

    try:
        report = get_quality_report(article_id)
        if not report:
            return f'No quality report found for article {article_id}.'
        return (
            f"Article {article_id} quality report (stage={report['stage']}): "
            f"overall={report['overall_score']}, citation={report['citation_score']}, "
            f"claim={report['claim_score']}, passed={report['passed']}, "
            f"needs_review={report['needs_review']}, "
            f"findings: {report['findings_total']} total "
            f"({len(report['findings_by_severity']['error'])} errors, "
            f"{len(report['findings_by_severity']['warning'])} warnings)"
        )
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool get_quality_report failed for %s: %s", article_id, e)
        return f"Error retrieving quality report: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in get_quality_report for %s: %s", article_id, e)
        return f"Error retrieving quality report: {type(e).__name__}"


def _context_tool_find_dedupe_candidates(
    title: str, url: str | None = None, limit: int = 5,
) -> str:
    from services.dedup_service import find_dedupe_candidates

    try:
        candidates = find_dedupe_candidates(title=title, url=url, limit=limit)
        if not candidates:
            return "No deduplication candidates found."
        return "\n".join(
            f"- id={c['id']}: {c['title']} ({c['pipeline_status']})"
            for c in candidates
        )
    except (SQLAlchemyError, KeyError, AttributeError) as e:
        logger.error("Tool find_dedupe_candidates failed: %s", e)
        return f"Error finding dedupe candidates: {type(e).__name__}"
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in find_dedupe_candidates: %s", e)
        return f"Error finding dedupe candidates: {type(e).__name__}"


def _context_tool_estimate_stage_cost(
    stage: str, model: str | None = None,
) -> str:
    from services.stage_cost import estimate_stage_cost

    try:
        result = estimate_stage_cost(stage=stage, model=model)
        if "error" in result:
            return f"Error: {result['error']}"
        return (
            f"Stage {result['stage']}"
            + (f" (model={result['model']})" if result['model'] else "")
            + f": estimated_cost=${result['estimated_cost_usd']:.4f}, "
            f"calls={result['call_count']}"
        )
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        logger.error("Unexpected error in estimate_stage_cost: %s", e)
        return f"Error estimating stage cost: {type(e).__name__}"


def _build_context_tools() -> list[ToolDefinition]:
    """Build tool definitions from context_service functions."""
    tools = []

    tools.append(
        ToolDefinition(
            name="get_topic_note",
            description="Get a topic note for a given topic name. Returns the note content.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic name"},
                    "source": {
                        "type": "string",
                        "description": "Optional source filter",
                    },
                },
                "required": ["topic"],
            },
            fn=_context_tool_get_topic_note,
        ),
    )

    tools.append(
        ToolDefinition(
            name="context_notes",
            description="Get topic notes for multiple topics at once.",
            parameters={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topic names",
                    },
                },
                "required": ["topics"],
            },
            fn=_context_tool_get_topic_notes_for_topics,
        ),
    )

    tools.append(
        ToolDefinition(
            name="related_articles",
            description="Get related articles for editing context.",
            parameters={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topics",
                    },
                    "exclude_id": {
                        "type": "integer",
                        "description": "Article ID to exclude",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max articles to return",
                    },
                },
                "required": ["topics", "exclude_id"],
            },
            fn=_context_tool_get_related_articles,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_trend_memory",
            description="Get stored trend memory entries for topics. Use to identify patterns and prior coverage before editing.",
            parameters={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topic names",
                    },
                    "min_importance": {
                        "type": "integer",
                        "description": "Minimum importance tier: 1=low, 2=medium, 3=high. Default 1.",
                    },
                    "max_age_days": {
                        "type": "integer",
                        "description": "Only return entries younger than this many days. Default all.",
                    },
                },
                "required": ["topics"],
            },
            fn=_context_tool_get_trend_memory,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_article_by_id",
            description="Get article details by ID. Returns article metadata.",
            parameters={
                "type": "object",
                "properties": {
                    "article_id": {
                        "type": "integer",
                        "description": "The article ID",
                    },
                },
                "required": ["article_id"],
            },
            fn=_context_tool_get_article_by_id,
        ),
    )

    tools.append(
        ToolDefinition(
            name="search_articles",
            description="Search articles by keyword in title.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return",
                    },
                },
                "required": ["query"],
            },
            fn=_context_tool_search_articles,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_source_health",
            description="Get a summary of all source health status including disabled state and consecutive failures.",
            parameters={
                "type": "object",
                "properties": {},
            },
            fn=_context_tool_get_source_health,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_topic_gap_report",
            description="Get topic gap analysis showing under-covered topics based on search demand, trend memory, and publication volume.",
            parameters={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of topic names to analyze. If not provided, analyzes all configured topics.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back for article counts (default 30, max 365).",
                    },
                },
            },
            fn=_context_tool_get_topic_gap_report,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_source_performance",
            description="Get source performance metrics including articles created, published count, selection rate, and impact scores.",
            parameters={
                "type": "object",
                "properties": {
                    "source_key": {
                        "type": "string",
                        "description": "Optional source key to filter by a specific source.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7, max 365).",
                    },
                },
            },
            fn=_context_tool_get_source_performance,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_quality_report",
            description="Get the latest quality report for an article, including overall score, citation/claim scores, and findings.",
            parameters={
                "type": "object",
                "properties": {
                    "article_id": {
                        "type": "integer",
                        "description": "The article ID",
                    },
                },
                "required": ["article_id"],
            },
            fn=_context_tool_get_quality_report,
        ),
    )

    tools.append(
        ToolDefinition(
            name="find_dedupe_candidates",
            description="Find potential duplicate articles by URL or title to check for coverage overlap.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Article title to check",
                    },
                    "url": {
                        "type": "string",
                        "description": "Optional article URL",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max candidates to return (default 5)",
                    },
                },
                "required": ["title"],
            },
            fn=_context_tool_find_dedupe_candidates,
        ),
    )

    tools.append(
        ToolDefinition(
            name="estimate_stage_cost",
            description="Estimate the cost of running a pipeline stage based on historical metrics.",
            parameters={
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "string",
                        "description": "Stage name: select, research, write, edit, finalize, or publish.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Optional specific model ID to filter cost for that model only.",
                    },
                },
                "required": ["stage"],
            },
            fn=_context_tool_estimate_stage_cost,
        ),
    )

    return tools


def _build_search_tools() -> list[ToolDefinition]:
    """Build tool definitions from search service."""
    tools = []

    tools.append(
        ToolDefinition(
            name="web_search",
            description="Search the web for information on a topic.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
            fn=_search_web,
        ),
    )

    tools.append(
        ToolDefinition(
            name="get_search_provider",
            description="Get the configured search provider.",
            parameters={
                "type": "object",
                "properties": {
                    "provider_id": {
                        "type": "string",
                        "description": "Optional specific provider ID",
                    },
                },
            },
            fn=_get_search_provider,
        ),
    )

    return tools

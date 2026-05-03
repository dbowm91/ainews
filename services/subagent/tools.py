from __future__ import annotations

import json
import logging

from sqlalchemy.exc import SQLAlchemyError

from services.llm.base import ToolDefinition

logger = logging.getLogger(__name__)


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
    return cache.get_or_set(cache_key, _fetch_note, ttl=120)


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
    return cache.get_or_set(cache_key, _fetch_articles, ttl=120)


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

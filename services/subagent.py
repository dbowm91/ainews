from __future__ import annotations

import ast
import functools
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Type

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (  # noqa: F401, E402
    EditContextualizationResponse,
    ResearchSynthesisResponse,
    SubagentResponse,
)
from schemas.pipeline import BASE_DIR, SubagentStageConfig, resolve_subagent_config
from services.llm import get_provider_for_role
from services.llm.base import ToolDefinition
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError
from services.logging_utils import log_pipeline_event, traced_llm_call
from services.metrics import get_metrics, time_histogram
from services.prompts import esc_xml_text
from services.tool_selection import ToolSelector

_TOOL_REGISTRY: dict[str, ToolDefinition] = {}

SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "8"))
_subagent_executor = ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS, thread_name_prefix="subagent")


def register_tool(definition: ToolDefinition) -> None:
    """Register a tool definition in the global tool registry."""
    _TOOL_REGISTRY[definition.name] = definition


def get_registered_tools() -> list[ToolDefinition]:
    """Get all registered tool definitions."""
    return list(_TOOL_REGISTRY.values())


# Context tool helpers
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
        except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error in get_source_health: %s", e)
        return f'{{"error": "{type(e).__name__}"}}'


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
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            logger.error("Unexpected error in get_search_provider: %s", e)
            return f"Error getting search provider: {type(e).__name__}"

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


@functools.lru_cache(maxsize=1)
def _get_all_tools_cached() -> tuple[ToolDefinition, ...]:
    """Build and cache all tool definitions. Returns tuple for hashability."""
    tools = []
    tools.extend(_build_context_tools())
    tools.extend(_build_search_tools())
    return tuple(tools)


def initialize_tool_registry(
    tool_names: list[str] | None = None,
    selector: ToolSelector | None = None,
    context: dict[str, Any] | None = None,
) -> list[ToolDefinition]:
    """Initialize the tool registry with built-in tools, optionally filtered.

    Uses cached tool definitions to avoid rebuilding on every call.

    Args:
        tool_names: Optional list of tool names to include (backward compatible).
        selector: Optional ToolSelector for advanced selection strategies.
        context: Optional context dict passed to selector if provided.

    Returns:
        List of selected ToolDefinition objects.
    """
    global _TOOL_REGISTRY

    all_tools = _get_all_tools_cached()

    if not _TOOL_REGISTRY:
        for tool in all_tools:
            register_tool(tool)

    if selector is not None:
        return selector.select_tools(all_tools, context)

    if tool_names is not None:
        return [t for t in all_tools if t.name in tool_names]
    return list(all_tools)


logger = logging.getLogger(__name__)


_SUBAGENT_TASK_TEMPLATES = {
    "research_synthesis": """<source_article>
  <title>{title}</title>
  <body>{body}</body>
</source_article>

<web_results>
{web_results}
</web_results>

Synthesize the external sources into a coherent summary that supplements the source article.
Focus on facts, context, and perspectives not already covered in the source article.
Return your synthesis as a concise paragraph.""",
    "edit_contextualization": """<draft_article>
{draft}
</draft_article>

<research_brief>
{brief}
</research_brief>

<topic_notes>
{topic_notes}
</topic_notes>

<related_articles>
{related_articles}
</related_articles>

<trend_memory>
{trend_memory}
</trend_memory>

Review the draft in light of the research brief, topic notes, related articles, and trend memory.
Identify gaps in context, missing attribution, or claims that need additional support.
Return a concise contextualization that addresses what the editor should know.""",
}


def _load_prompt_template(path: str) -> str | None:
    p = BASE_DIR / path
    if p.exists():
        return p.read_text()
    return None


def _escape_prompt_data(data: dict[str, Any]) -> dict[str, Any]:
    """Escape all string values in prompt_data for safe XML embedding."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = esc_xml_text(value)
        elif isinstance(value, dict):
            result[key] = _escape_prompt_data(value)
        elif isinstance(value, list):
            result[key] = [
                esc_xml_text(str(v)) if isinstance(v, str) else v for v in value
            ]
        else:
            result[key] = value
    return result


def _get_task_template(task_type: str, stage_config: SubagentStageConfig) -> str:
    if stage_config.task_template:
        loaded = _load_prompt_template(stage_config.task_template)
        if loaded:
            return loaded
    return _SUBAGENT_TASK_TEMPLATES.get(task_type, "")


def _get_subagent_provider_and_config(
    stage_config: SubagentStageConfig,
    default_role: str = "editor",
) -> tuple:
    if stage_config.provider and stage_config.model:
        from services.llm import get_provider_by_id

        provider = get_provider_by_id(stage_config.provider)
        model = stage_config.model
        max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    else:
        provider, model, max_tokens, _ = get_provider_for_role(default_role)
        if stage_config.max_tokens:
            max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    return provider, model, max_tokens, temperature


def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:
    default_role = "researcher" if stage == "research" else "editor"
    stage_config = resolve_subagent_config(stage, default_role=default_role)
    if not stage_config.enabled:
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    log_pipeline_event(
        stage="subagent",
        event="subagent.start",
        article_id=article_id,
        task_type=task_type,
        stage_name=stage,
    )

    template = _get_task_template(task_type, stage_config)
    try:
        prompt_data_escaped = _escape_prompt_data(prompt_data)
        prompt = template.format(**prompt_data_escaped)
    except KeyError as e:
        logger.warning(
            "Subagent %s/%s template missing key: %s",
            stage,
            task_type,
            e,
        )
        get_metrics().counter_inc(
            "subagent.failure",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.failure",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
            error=f"template missing key: {e}",
        )
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    system_prompt = stage_config.system_prompt or ""

    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config, default_role=default_role,
    )

    def _call_with_timeout():
        with traced_llm_call(provider=provider.provider_id, model=model, stage=stage):
            return provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=response_model,
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    result = None
    used_fallback = False
    fallback_stages = []
    last_exc = None

    for attempt in range(stage_config.max_retries + 1):
        try:
            with time_histogram(
                "subagent.duration_seconds",
                labels={"stage": stage, "task_type": task_type},
            ):
                if attempt > 0:
                    import random
                    delay = min(
                        1.0 * (2 ** attempt) + random.uniform(0, 0.5),  # noqa: S311
                        stage_config.retry_delay,
                    )
                    time.sleep(delay)
                future = _subagent_executor.submit(_call_with_timeout)
                try:
                    result = future.result(timeout=stage_config.timeout_seconds)
                except TimeoutError as e:
                    future.cancel()
                    logger.warning(
                        "Subagent %s/%s timed out after %ss",
                        stage,
                        task_type,
                        stage_config.timeout_seconds,
                    )
                    raise ProviderTimeoutError(
                        f"Subagent timed out after {stage_config.timeout_seconds}s",
                    ) from e
            break
        except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
            last_exc = e
            if attempt < stage_config.max_retries:
                logger.info(
                    "Subagent %s/%s attempt %d failed, retrying in %ss: %s",
                    stage,
                    task_type,
                    attempt + 1,
                    stage_config.retry_delay,
                    e,
                )
            continue
        except (AuthError, ProviderServerError) as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed with non-retryable error: %s",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            last_exc = e
            logger.error(
                "Subagent %s/%s unexpected error: %s — using fallback",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break

    if result is None:
        used_fallback = True
        fallback_stages = [stage]
        get_metrics().counter_inc(
            "subagent.failure",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.failure",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
            error=str(last_exc) if last_exc else None,
        )
    else:
        get_metrics().counter_inc(
            "subagent.success",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.complete",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
        )

    get_metrics().counter_inc(
        "subagent.calls",
        labels={
            "stage": stage,
            "task_type": task_type,
            "status": "failure" if used_fallback else "success",
        },
    )

    return SubagentResponse(
        synthesis=result.synthesis if result else "",
        used_fallback=used_fallback,
        fallback_stages=fallback_stages,
    )


def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:
    """Run subagent with tool calling support."""
    default_role = "researcher" if stage == "research" else "editor"
    stage_config = resolve_subagent_config(stage, default_role=default_role)
    if not stage_config.enabled:
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    log_pipeline_event(
        stage="subagent",
        event="subagent.start",
        article_id=article_id,
        task_type=task_type,
        stage_name=stage,
    )

    template = _get_task_template(task_type, stage_config)
    try:
        prompt_data_escaped = _escape_prompt_data(prompt_data)
        prompt = template.format(**prompt_data_escaped)
    except KeyError as e:
        logger.warning(
            "Subagent %s/%s template missing key: %s",
            stage,
            task_type,
            e,
        )
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    system_prompt = stage_config.system_prompt or ""
    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config, default_role=default_role,
    )

    messages = [{"role": "user", "content": prompt}]

    def _call_with_timeout():
        with traced_llm_call(provider=provider.provider_id, model=model, stage=stage):
            return provider.chat_with_tools(
                messages=messages,
                tools=tools,
                tool_choice=None,
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                max_iterations=stage_config.max_iterations,
            )

    result = None
    used_fallback = False
    fallback_stages = []
    last_exc = None
    self_corrected = False

    for attempt in range(stage_config.max_retries + 1):
        try:
            with time_histogram(
                "subagent.duration_seconds",
                labels={"stage": stage, "task_type": task_type},
            ):
                if attempt > 0:
                    import random
                    delay = min(
                        1.0 * (2 ** attempt) + random.uniform(0, 0.5),  # noqa: S311
                        stage_config.retry_delay,
                    )
                    time.sleep(delay)
                future = _subagent_executor.submit(_call_with_timeout)
                try:
                    tc_resp = future.result(timeout=stage_config.timeout_seconds)
                    try:
                        result = response_model.model_validate(
                            {"synthesis": tc_resp.text},
                        )
                    except (json.JSONDecodeError, ValidationError) as validation_err:
                        if self_corrected:
                            raise validation_err
                        error_msg = (
                            f"Your previous response was not valid JSON or did not match "
                            f"the expected schema: {validation_err}. Please correct and "
                            f"return valid JSON in the same format."
                        )
                        logger.info(
                            "Subagent %s/%s self-correcting after validation error: %s",
                            stage,
                            task_type,
                            validation_err,
                        )
                        messages.append({"role": "user", "content": error_msg})
                        self_corrected = True
                        continue
                except TimeoutError as e:
                    future.cancel()
                    logger.warning(
                        "Subagent %s/%s timed out after %ss",
                        stage,
                        task_type,
                        stage_config.timeout_seconds,
                    )
                    raise ProviderTimeoutError(
                        f"Subagent timed out after {stage_config.timeout_seconds}s",
                    ) from e
            break
        except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
            last_exc = e
            if attempt < stage_config.max_retries:
                import random
                delay = min(
                    1.0 * (2 ** attempt) + random.uniform(0, 0.5),
                    stage_config.retry_delay,
                )
                logger.info(
                    "Subagent %s/%s attempt %d failed, retrying in %ss: %s",
                    stage,
                    task_type,
                    attempt + 1,
                    delay,
                    e,
                )
            continue
        except (AuthError, ProviderServerError) as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed with non-retryable error: %s",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            last_exc = e
            logger.error(
                "Subagent %s/%s unexpected error: %s — using fallback",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break

    if result is None:
        used_fallback = True
        fallback_stages = [stage]
        get_metrics().counter_inc(
            "subagent.failure",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.failure",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
            error=str(last_exc) if last_exc else None,
        )
    else:
        get_metrics().counter_inc(
            "subagent.success",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.complete",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
        )

    get_metrics().counter_inc(
        "subagent.calls",
        labels={
            "stage": stage,
            "task_type": task_type,
            "status": "failure" if used_fallback else "success",
        },
    )

    return SubagentResponse(
        synthesis=result.synthesis if result else "",
        used_fallback=used_fallback,
        fallback_stages=fallback_stages,
    )


def run_subagent_chain(
    chain_name: str,
    steps: list[dict],
    initial_prompt_data: dict,
    article_id: int | None = None,
) -> dict[str, Any]:
    """Run a multi-step subagent chain.

    Each step: {task_type, prompt_data_template, response_model, condition}
    Steps can reference outputs of previous steps via template variables.
    Returns dict with step results and any fallback markers.
    """
    from schemas.pipeline import load_pipeline_config

    config = load_pipeline_config()
    chain_config = config.subagent.chains.get(chain_name)
    if not chain_config or not chain_config.enabled:
        return {
            "results": {},
            "used_fallback": True,
            "fallback_stages": ["chain"],
        }

    max_length = chain_config.max_length
    results: dict[str, Any] = {}

    for i, step_config in enumerate(chain_config.steps[:max_length]):
        step_name = f"{chain_name}_step_{i}"
        task_type = step_config.task_type

        if step_config.condition:
            try:
                condition_result = _evaluate_condition(step_config.condition, results)
                if not condition_result:
                    logger.info(
                        "Chain %s step %d (%s) skipped due to condition",
                        chain_name,
                        i,
                        task_type,
                    )
                    results[step_name] = {"synthesis": "", "skipped": True}
                    continue
            except (ValueError, KeyError, AttributeError) as e:
                logger.error(
                    "Chain %s step %d condition evaluation failed: %s",
                    chain_name,
                    i,
                    e,
                )
                results[step_name] = {"synthesis": "", "skipped": True}
                continue

        stage = "research" if "research" in task_type else "edit"
        stage_config = resolve_subagent_config(stage)
        if not stage_config.enabled:
            results[step_name] = {"synthesis": "", "used_fallback": True}
            continue

        try:
            template = step_config.prompt_data_template
            prompt_data = _resolve_template_variables(
                template, initial_prompt_data, results,
            )
            prompt_data_escaped = _escape_prompt_data(prompt_data)
            prompt = template.format(**prompt_data_escaped)
        except (KeyError, ValueError, AttributeError) as e:
            logger.error(
                "Chain %s step %d template error: %s",
                chain_name,
                i,
                e,
            )
            results[step_name] = {"synthesis": "", "used_fallback": True}
            continue

        system_prompt = stage_config.system_prompt or ""
        provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
            stage_config, default_role="editor",
        )

        def _chain_call():
            return provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        step_succeeded = False
        for attempt in range(stage_config.max_retries + 1):
            try:
                future = _subagent_executor.submit(_chain_call)
                try:
                    resp = future.result(timeout=stage_config.timeout_seconds)
                    step_succeeded = True
                    break
                except TimeoutError as e:
                    future.cancel()
                    logger.warning(
                        "Chain %s step %d timed out after %ss (attempt %d)",
                        chain_name,
                        i,
                        stage_config.timeout_seconds,
                        attempt + 1,
                    )
                    raise ProviderTimeoutError(
                        f"Chain step timed out after {stage_config.timeout_seconds}s",
                    ) from e
            except (ProviderTimeoutError, TimeoutError) as e:
                if attempt < stage_config.max_retries:
                    import random
                    delay = min(
                        1.0 * (2 ** attempt) + random.uniform(0, 0.5),  # noqa: S311
                        stage_config.retry_delay,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "Chain %s step %d failed after %d attempts: %s",
                    chain_name,
                    i,
                    attempt + 1,
                    e,
                )
                results[step_name] = {
                    "synthesis": f"[Fallback: {e}]",
                    "used_fallback": True,
                }
                break
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                logger.error(
                    "Chain %s step %d unexpected error: %s",
                    chain_name,
                    i,
                    e,
                )
                results[step_name] = {
                    "synthesis": f"[Fallback: {e}]",
                    "used_fallback": True,
                }
                break

        if step_succeeded:
            results[step_name] = {"synthesis": resp.text, "used_fallback": False}

    all_fallback = all(r.get("used_fallback", False) for r in results.values())

    return {
        "results": results,
        "used_fallback": all_fallback,
        "fallback_stages": list(results.keys()) if all_fallback else [],
    }


# AST evaluation helpers for _evaluate_condition
def _eval_handle_expression(node: ast.Expression, eval_node_fn) -> Any:
    return eval_node_fn(node.body)


def _eval_handle_bool_op(node: ast.BoolOp, eval_node_fn, allowed_ops) -> Any:
    values = [eval_node_fn(v) for v in node.values]
    if isinstance(node.op, ast.And):
        return all(values)
    elif isinstance(node.op, ast.Or):
        return any(values)
    raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")


def _eval_handle_unary_not(node: ast.UnaryOp, eval_node_fn) -> Any:
    return not eval_node_fn(node.operand)


def _eval_handle_compare(node: ast.Compare, eval_node_fn, allowed_ops) -> Any:
    left = eval_node_fn(node.left)
    for op_node, comparator in zip(node.ops, node.comparators):
        op = allowed_ops[type(op_node)]
        right = eval_node_fn(comparator)
        if not op(left, right):
            return False
        left = right
    return True


def _eval_handle_name(node: ast.Name, allowed_names, context) -> Any:
    if node.id not in allowed_names:
        raise ValueError(f"Unknown identifier: {node.id}")
    if node.id in ("results", "previous"):
        return context.get(node.id, context)
    result = context.get(node.id)
    if result is None:
        raise ValueError(f"Context has no key '{node.id}'")
    return result


def _eval_handle_constant(node: ast.Constant) -> Any:
    return node.value


def _eval_handle_attribute(node: ast.Attribute, eval_node_fn, context) -> Any:
    obj = eval_node_fn(node.value)
    if isinstance(obj, dict) and node.attr in obj:
        return obj[node.attr]
    if obj is None:
        return {}
    if node.attr.startswith("__") or node.attr.startswith("_"):
        raise ValueError(f"Access to protected attribute '{node.attr}' is not allowed")
    try:
        return getattr(obj, node.attr)
    except AttributeError:
        if isinstance(obj, dict):
            raise
        if node.attr in context:
            return context[node.attr]
        raise


def _eval_handle_subscript(node: ast.Subscript, eval_node_fn) -> Any:
    obj = eval_node_fn(node.value)
    idx = eval_node_fn(node.slice)
    if isinstance(obj, dict):
        return obj[idx]
    elif isinstance(obj, (list, tuple)):
        if isinstance(idx, int):
            return obj[idx]
        raise ValueError("List index must be an integer")
    raise ValueError("Subscript target must be dict or list")


def _eval_node(
    node: ast.AST,
    allowed_ops: dict,
    allowed_names: set,
    context: dict,
) -> Any:
    """Recursively evaluate an AST node with given allowed ops/names/context."""
    node_type = type(node)
    if node_type is ast.Expression:
        return _eval_handle_expression(node, _eval_node)
    elif node_type is ast.BoolOp:
        return _eval_handle_bool_op(node, _eval_node, allowed_ops)
    elif node_type is ast.UnaryOp:
        if isinstance(node.op, ast.Not):
            return _eval_handle_unary_not(node, _eval_node)
        else:
            raise ValueError("Unary operations not allowed in conditions")
    elif node_type is ast.Compare:
        return _eval_handle_compare(node, _eval_node, allowed_ops)
    elif node_type is ast.Name:
        return _eval_handle_name(node, allowed_names, context)
    elif node_type is ast.Constant:
        return _eval_handle_constant(node)
    elif node_type is ast.Attribute:
        return _eval_handle_attribute(node, _eval_node, context)
    elif node_type is ast.Subscript:
        return _eval_handle_subscript(node, _eval_node)
    elif node_type in (ast.Call, ast.Lambda, ast.BinOp):
        disallowed_msgs = {
            ast.Call: "Function calls not allowed in conditions",
            ast.Lambda: "Lambda expressions not allowed in conditions",
            ast.BinOp: "Binary operations not allowed in conditions",
        }
        raise ValueError(disallowed_msgs[node_type])
    else:
        raise ValueError(f"Unsupported node type: {node_type.__name__}")


def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate a condition expression against the context using AST-based parsing."""
    import ast
    import operator

    _ALLOWED_OPS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Not: operator.not_,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    _ALLOWED_NAMES = {"True", "False", "None", "results", "previous"}

    try:
        tree = ast.parse(condition, mode="eval")
    except (SyntaxError, ValueError):
        return False

    try:
        return bool(_eval_node(tree, _ALLOWED_OPS, _ALLOWED_NAMES, context))
    except ValueError as e:
        if any(seg in str(e) for seg in ("Unsupported node type", "not allowed")):
            raise
        return False
    except Exception as e:  # noqa: BLE001
        logger.debug("Condition evaluation failed for '%s': %s", condition, e)
        return False


def _resolve_template_variables(
    template: str, initial_data: dict, results: dict[str, Any],
) -> dict:
    """Resolve template variables, including references to previous step results."""
    resolved = dict(initial_data)
    for key, value in resolved.items():
        if isinstance(value, str) and "{" in value:
            try:
                resolved[key] = value.format(**results)
            except (KeyError, ValueError, AttributeError) as e:
                logger.warning(
                    "Template resolution failed for key '%s': %s",
                    key, e,
                )
    return resolved

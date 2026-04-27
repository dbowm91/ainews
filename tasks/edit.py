import json
import threading
import time

from celery import shared_task
from celery.utils.log import get_task_logger
from services.llm.errors import ProviderServerError
from constants import PipelineStatus

logger = get_task_logger(__name__)

# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results


_TAG_CACHE: list[str] | None = None
_TAG_CACHE_TIME: float = 0
_TAG_CACHE_TTL = 300
_TAG_CACHE_LOCK = threading.Lock()


def _format_topic_notes(notes_by_topic: dict[str, list[str]]) -> str:
    if not notes_by_topic:
        return "(no topic notes)"
    parts = []
    for topic, notes in notes_by_topic.items():
        parts.append(f"Topic: {topic}")
        for note in notes:
            parts.append(f"  - {note}")
    return "\n".join(parts) if parts else "(no topic notes)"


def _format_related_articles(articles: list[dict]) -> str:
    if not articles:
        return "(no related articles)"
    parts = []
    for a in articles:
        parts.append(f"- {a.get('title', 'Unknown')} ({a.get('category', 'general')})")
        if a.get("snippet"):
            parts.append(f"  {a['snippet'][:200]}")
    return "\n".join(parts) if parts else "(no related articles)"


def _get_cached_tag_names() -> list[str]:
    global _TAG_CACHE, _TAG_CACHE_TIME
    now = time.time()
    if _TAG_CACHE is not None and (now - _TAG_CACHE_TIME) < _TAG_CACHE_TTL:
        return _TAG_CACHE
    from models import Tag

    tags = Tag.query.order_by(Tag.name).limit(100).all()
    fresh_tags = [t.name for t in tags]
    with _TAG_CACHE_LOCK:
        _TAG_CACHE = fresh_tags
        _TAG_CACHE_TIME = now
    return fresh_tags


def clear_tag_cache() -> None:
    """Clear the tag cache (call after tag changes)."""
    global _TAG_CACHE, _TAG_CACHE_TIME
    with _TAG_CACHE_LOCK:
        _TAG_CACHE = None
        _TAG_CACHE_TIME = 0


def _gather_editor_context(article, existing_tags: list[str]) -> str:
    """Gather contextualization for the editor from subagent.

    Returns contextualization string or empty string if not available.
    """
    from services.context_service import (
        get_topic_notes_for_topics,
        get_related_articles_for_edit,
    )
    from services.subagent import (
        run_subagent,
        run_subagent_with_tools,
        EditContextualizationResponse,
    )
    from schemas.pipeline import resolve_subagent_config

    if not article.topics:
        return ""

    topic_notes = get_topic_notes_for_topics(article.topics)
    related_articles = get_related_articles_for_edit(
        article.topics, article.id, limit=5
    )
    from services.trend_memory import (
        get_memory_for_topics,
        _format_memory_for_prompt,
    )

    trend_memory = _format_memory_for_prompt(
        get_memory_for_topics(article.topics, min_importance=1)
    )
    if not topic_notes and not related_articles and not trend_memory:
        return ""

    # Check for tool-calling config
    stage_config = resolve_subagent_config("edit", default_role="editor")
    if stage_config.tools:
        from services.subagent import initialize_tool_registry

        tools = initialize_tool_registry(stage_config.tools)
        context_result = run_subagent_with_tools(
            task_type="edit_contextualization",
            stage="edit",
            prompt_data={
                "draft": article.draft_article or "",
                "brief": article.research_brief or "",
                "topic_notes": _format_topic_notes(topic_notes),
                "related_articles": _format_related_articles(related_articles),
                "trend_memory": trend_memory,
            },
            response_model=EditContextualizationResponse,
            tools=tools,
            article_id=article.id,
        )
    else:
        context_result = run_subagent(
            task_type="edit_contextualization",
            stage="edit",
            prompt_data={
                "draft": article.draft_article or "",
                "brief": article.research_brief or "",
                "topic_notes": _format_topic_notes(topic_notes),
                "related_articles": _format_related_articles(related_articles),
                "trend_memory": trend_memory,
            },
            response_model=EditContextualizationResponse,
            article_id=article.id,
        )
    if context_result.used_fallback:
        logger.warning(
            "Edit contextualization subagent failed, proceeding without context",
            extra={"article_id": article.id},
        )
    return context_result.synthesis


def _handle_validation_and_routing(
    article, db, run_id: int | None = None
) -> dict | None:
    """Validate article quality and determine routing.

    Returns dict with status if routing changed, None if continuing to DONE.
    """
    from services.article_validation import validate_and_raise, ValidationError
    from sqlalchemy.exc import SQLAlchemyError
    from constants import PipelineStatus, truncate_for_log
    from tasks.pipeline import _log_pipeline, _transition_article_status

    try:
        validate_and_raise(article.final_article)
    except ValidationError as e:
        logger.warning(
            "Article validation failed, routing to review: %s",
            e,
            extra={"article_id": article.id},
        )
        _transition_article_status(article, PipelineStatus.REVIEW)
        article.last_error = f"Content validation failed: {e}"
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "info",
                "Validation failed, queued for review: %s",
                truncate_for_log(article.original_title),
                article_id=article.id,
            )
        return {"article_id": article.id, "status": "review"}

    from tasks.pipeline import _should_route_to_review, _transition_article_status

    if _should_route_to_review(article):
        _transition_article_status(article, PipelineStatus.REVIEW)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "info",
                "Queued for review: %s",
                truncate_for_log(article.original_title),
                article_id=article.id,
            )
        return {"article_id": article.id, "status": "review"}

    return None


def _post_finalize_article(article, run_id: int | None = None) -> None:
    """Post-finalize article: trend memory, webhooks, SLA metrics."""
    from datetime import datetime, timezone
    from services.metrics import get_metrics
    from tasks.pipeline import _log_pipeline, _transition_article_status
    from constants import truncate_for_log

    _transition_article_status(article, PipelineStatus.DONE)
    article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if article.crawled_at:
        sla_duration = (article.published_at - article.crawled_at).total_seconds()
        get_metrics().histogram_observe("pipeline_sla_seconds", sla_duration)

    if run_id:
        _log_pipeline(
            run_id,
            "edit",
            "info",
            "Finalized: %s",
            truncate_for_log(article.original_title),
            article_id=article.id,
        )

    try:
        from models import ArticleMetric
        from extensions import db

        metric = db.session.get(ArticleMetric, article.id)
        engagement_data = {}
        if metric:
            engagement_data = {
                "newsletter_clicks": metric.newsletter_clicks or 0,
                "page_loads": metric.page_loads or 0,
            }
        from services.trend_memory import propose_trend_memory
        propose_trend_memory(article, engagement_data=engagement_data)
    except Exception:
        logger.warning(
            "propose_trend_memory failed for article %s, continuing",
            article.id,
        )

    try:
        from services.webhooks import trigger_event
        trigger_event(
            "article.published",
            {
                "article_id": article.id,
                "headline": (
                    json.loads(article.final_article).get("headline", "")
                    if article.final_article
                    else ""
                ),
                "category": article.category,
                "impact_score": article.impact_score,
            },
        )
    except json.JSONDecodeError as e:
        logger.warning("Malformed final_article JSON in webhook for article %s: %s", article.id, e)
    except Exception:
        logger.warning(
            "Webhook trigger failed for article %s, continuing",
            article.id,
        )


def _execute_editor_work(article, provider, model, max_tokens, article_id: int, run_id: int | None = None):
    """Execute the editor LLM work.

    Returns dict with article_id and status.
    """
    from extensions import db
    from sqlalchemy.exc import SQLAlchemyError
    from schemas.pipeline import get_role_config
    from schemas.llm_responses import CondensedArticle
    from services.editor import (
        get_editor_system_prompt,
        build_editor_prompt_with_context,
    )
    from services.metrics import time_histogram
    from services.logging_utils import traced_llm_call
    from tasks.pipeline import _assign_tags

    existing_tags = _get_cached_tag_names()
    contextualization = _gather_editor_context(article, existing_tags)

    # Truncate draft to prevent token overflow
    from services.prompts import sliding_window_truncate
    draft_truncated = sliding_window_truncate(
        article.draft_article or "", max_chars=8000
    )

    rc = get_role_config("editor")
    prompt = build_editor_prompt_with_context(
        draft_json=draft_truncated,
        research_brief=article.research_brief or "",
        existing_tags=existing_tags,
        max_tags=rc.max_tags or 3,
        contextualization=contextualization,
    )

    with traced_llm_call(provider=provider.__class__.__name__, model=model, stage="edit"):
        with time_histogram(
            "pipeline.stage_duration_seconds", labels={"stage": "edit"}
        ):
            result = provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=CondensedArticle,
                model=model,
                system=get_editor_system_prompt(),
                temperature=rc.temperature,
                max_tokens=max_tokens,
            )

    result_json = result.model_dump_json()
    article.final_article = result_json
    article.original_ai_article = result_json

    _assign_tags(article, result.tags or [], db)

    from services.article import create_article_version
    create_article_version(
        article, change_reason="pipeline_edit", changed_by="pipeline:editor"
    )

    routing_result = _handle_validation_and_routing(article, db, run_id)
    if routing_result:
        return routing_result

    _post_finalize_article(article, run_id)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    return {"article_id": article_id, "status": "done"}


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def edit_article(self, article_id: int, run_id=None):
    from tasks.pipeline import run_stage
    return run_stage(
        "editor", article_id, _execute_editor_work, task_self=self, run_id=run_id, skip_next="finalize"
    )

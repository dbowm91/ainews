import threading
from datetime import datetime, timezone

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError
from constants import PipelineStatus, truncate_for_log
from services.llm.errors import ProviderServerError
from services.article_validation import validate_and_raise, ValidationError
import time

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
    # Fast path: check without lock
    if _TAG_CACHE is not None and (now - _TAG_CACHE_TIME) < _TAG_CACHE_TTL:
        return _TAG_CACHE
    with _TAG_CACHE_LOCK:
        # Double-check inside lock
        if _TAG_CACHE is not None and (now - _TAG_CACHE_TIME) < _TAG_CACHE_TTL:
            return _TAG_CACHE
        from models import Tag

        tags = Tag.query.order_by(Tag.name).limit(100).all()
        _TAG_CACHE = [t.name for t in tags]
        _TAG_CACHE_TIME = now
        return _TAG_CACHE


def clear_tag_cache() -> None:
    """Clear the tag cache (call after tag changes)."""
    global _TAG_CACHE, _TAG_CACHE_TIME
    with _TAG_CACHE_LOCK:
        _TAG_CACHE = None
        _TAG_CACHE_TIME = 0


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=30,
    retry_backoff_max=300,
    retry_jitter=True,
)
def edit_article(self, article_id: int, run_id=None):
    from extensions import db
    from schemas.pipeline import get_role_config
    from schemas.llm_responses import CondensedArticle
    from services.editor import (
        get_editor_system_prompt,
        build_editor_prompt_with_context,
    )
    from tasks.pipeline import (
        run_stage,
        _log_pipeline,
        _assign_tags,
        _should_route_to_review,
    )

    def work(article, provider, model, max_tokens):
        from services.context_service import (
            get_topic_notes_for_topics,
            get_related_articles_for_edit,
        )
        from services.subagent import (
            run_subagent,
            EditContextualizationResponse,
        )

        rc = get_role_config("editor")
        existing_tags = _get_cached_tag_names()

        contextualization = ""
        if article.topics:
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
            if topic_notes or related_articles or trend_memory:
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
                contextualization = context_result.synthesis
                if context_result.used_fallback:
                    logger.warning(
                        "Edit contextualization subagent failed, proceeding without context",
                        extra={"article_id": article.id},
                    )

        prompt = build_editor_prompt_with_context(
            draft_json=article.draft_article or "",
            research_brief=article.research_brief or "",
            existing_tags=existing_tags,
            max_tags=rc.max_tags or 3,
            contextualization=contextualization,
        )

        from services.metrics import time_histogram

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

        # Create version snapshot of the AI-generated article
        from services.article import create_article_version

        create_article_version(
            article, change_reason="pipeline_edit", changed_by="pipeline:editor"
        )

        # Validate content quality before transitioning to DONE or REVIEW
        try:
            validate_and_raise(article.final_article)
        except ValidationError as e:
            logger.warning(
                "Article validation failed, routing to review: %s",
                e,
                extra={"article_id": article.id},
            )
            article.pipeline_status = PipelineStatus.REVIEW
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
            return {"article_id": article_id, "status": "review"}

        # Route to review if enabled and article doesn't meet auto-publish threshold
        if _should_route_to_review(article):
            article.pipeline_status = PipelineStatus.REVIEW
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
            return {"article_id": article_id, "status": "review"}

        article.pipeline_status = PipelineStatus.DONE
        article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        if article.crawled_at:
            sla_duration = (article.published_at - article.crawled_at).total_seconds()
            from services.metrics import get_metrics

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
            from services.trend_memory import propose_trend_memory

            propose_trend_memory(article)
        except Exception:
            logger.warning(
                "propose_trend_memory failed for article %s, continuing",
                article.id,
            )

        return {"article_id": article_id, "status": "done"}

    return run_stage(
        "editor", article_id, work, task_self=self, run_id=run_id, skip_next="finalize"
    )

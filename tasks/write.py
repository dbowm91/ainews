from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import PipelineStatus, truncate_for_log
from services.llm.errors import ProviderServerError
from services.writer import CondensedArticle

logger = get_task_logger(__name__)


def _is_degenerate_write(article_obj: CondensedArticle) -> bool:
    """Check if condensed article is degenerate (fails quality gate).

    Returns True if:
    - Body is too short (< 500 chars)
    - No key points (empty list)
    - No citations (empty list)
    """
    body = article_obj.body or ""
    if len(body.strip()) < 500:
        return True
    if not article_obj.key_points:
        return True
    if not article_obj.citations:
        return True
    return False

# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def write_article(self, article_id: int, run_id=None):
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.writer import (
        CondensedArticle,
        build_writer_prompt,
        get_writer_system_prompt,
    )
    from tasks.pipeline import _dispatch_next, _log_pipeline, _transition_article_status, run_stage

    def work(article, provider, model, max_tokens):
        rc = get_role_config("writer")
        _transition_article_status(article, PipelineStatus.EDITING)

        # Fetch trend memory if topics available
        trend_memory = ""
        if article.topics:
            from services.trend_memory import (
                _format_memory_for_prompt,
                get_memory_for_topics,
            )
            trend_memory = _format_memory_for_prompt(
                get_memory_for_topics(article.topics, min_importance=1)
            )

        # Truncate research_brief to prevent token overflow
        from services.prompts import sliding_window_truncate
        research_brief = sliding_window_truncate(
            article.research_brief or "", max_chars=8000
        )

        prompt = build_writer_prompt(
            title=article.original_title or "",
            topics=article.topics or [],
            research_brief=research_brief,
            max_key_points=rc.max_key_points or 5,
            trend_memory=trend_memory,
        )

        from services.logging_utils import traced_llm_call
        from services.metrics import time_histogram

        with traced_llm_call(provider=provider.__class__.__name__, model=model, stage="write"):
            with time_histogram(
                "pipeline.stage_duration_seconds", labels={"stage": "write"}
            ):
                result = provider.chat_structured(
                    messages=[{"role": "user", "content": prompt}],
                    response_model=CondensedArticle,
                    model=model,
                    system=get_writer_system_prompt(article),
                    temperature=rc.temperature,
                    max_tokens=max_tokens,
                    stage="write",
                )

        article.draft_article = result.model_dump_json()
        article.writer_model = model

        # Quality gate: validate condensed article before advancing
        if _is_degenerate_write(result):
            logger.warning(
                "Condensed article failed quality gate, routing to review",
                extra={
                    "article_id": article.id,
                    "body_length": len(result.body or ""),
                    "key_points_count": len(result.key_points or []),
                    "citations_count": len(result.citations or []),
                },
            )
            _transition_article_status(article, PipelineStatus.REVIEW)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                raise
            if run_id:
                _log_pipeline(
                    run_id,
                    "write",
                    "warning",
                    "Write failed quality gate, routed to review: %s",
                    truncate_for_log(article.original_title),
                    article_id=article.id,
                )
            _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)
            return {"article_id": article_id, "quality_gate": "review"}

        _transition_article_status(article, PipelineStatus.EDITING)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        if run_id:
            _log_pipeline(
                run_id,
                "write",
                "info",
                "Drafted: %s",
                truncate_for_log(article.original_title),
                article_id=article.id,
            )

        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.EDITING)
        return {"article_id": article_id}

    return run_stage(
        "writer",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next=PipelineStatus.EDITING,
    )

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import PipelineStatus, truncate_for_log, CELERY_TASK_MAX_RETRIES
from services.llm.errors import ProviderServerError
from schemas.llm_responses import CondensedArticle

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
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=60,
    soft_time_limit=21600,
    time_limit=21660,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def write_article(self, article_id: int, run_id=None, _signature=None, task_name=None):
    from extensions import db
    from schemas.llm_responses import CondensedArticle
    from schemas.pipeline import get_role_config
    from services.writer import (
        build_verified_writer_prompt,
        get_writer_system_prompt,
    )
    from tasks.pipeline import _dispatch_next, _log_pipeline, _transition_article_status, run_stage

    def work(article, provider, model, max_tokens):
        rc = get_role_config("writer")

        from services.editorial_evidence import build_verified_packet

        packet = build_verified_packet(article)
        prompt = build_verified_writer_prompt(
            packet=packet,
            max_key_points=rc.max_key_points or 5,
        )

        from services.logging_utils import traced_llm_call
        from services.metrics import time_histogram

        with traced_llm_call(provider=provider.__class__.__name__, model=model, stage="writer"):
            with time_histogram(
                "pipeline.stage_duration_seconds", labels={"stage": "writer"},
            ):
                result = provider.chat_structured(
                    messages=[{"role": "user", "content": prompt}],
                    response_model=CondensedArticle,
                    model=model,
                    system=get_writer_system_prompt(article),
                    temperature=rc.temperature,
                    max_tokens=max_tokens,
                    stage="writer",
                )

        allowed_urls = {source["url"] for source in packet["sources"]}
        invalid_citations = [
            citation.url for citation in result.citations if citation.url not in allowed_urls
        ]
        if invalid_citations:
            article.last_error = "Editorial hold: writer proposed citations outside the verified dossier"
            from services.auto_review import route_to_review

            route_to_review(article)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                raise
            return {"article_id": article.id, "status": "review", "reason": "unverified_citation"}

        credit = packet["discovery_credit"]
        result.original_attribution.source = credit["source"] or "Original discovery source"
        result.original_attribution.url = credit["url"]
        result.original_attribution.author = credit["author"]
        result.original_attribution.published_at = credit["published_at"]

        article.draft_article = result.model_dump_json()
        article.writer_model = model

        # Shadow mode quality assessment (non-blocking)
        try:
            from services.quality import lightweight_quality_signals

            draft_text = result.body or ""
            if draft_text:
                quality_score = lightweight_quality_signals(draft_text)
                logger.info(
                    "Write quality (shadow): article_id=%s overall=%.2f groundedness=%.2f coherence=%.2f completeness=%.2f safety=%.2f",
                    article.id,
                    quality_score.overall,
                    quality_score.groundedness,
                    quality_score.coherence,
                    quality_score.completeness,
                    quality_score.safety,
                )
        except Exception as e:  # noqa: BLE001 - shadow quality assessment is non-critical
            logger.warning(
                "Quality assessment failed for article %s: %s", article.id, e
            )

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

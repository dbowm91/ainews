"""Pipeline degradation and article finalization logic."""

import json

from celery.utils.log import get_task_logger
from constants import PipelineStatus
from services.article_fallback import build_fallback_article_json

logger = get_task_logger(__name__)

_STAGE_STATUS_MAP = {
    "pending": "select",
    "selecting": "select",
    "selected": "research",
    "researching": "research",
    "writing": "write",
    "written": "edit",
    "editing": "edit",
    "selector": "select",
    "researcher": "research",
    "writer": "write",
    "editor": "edit",
    "select": "select",
    "research": "research",
    "write": "write",
    "edit": "edit",
}


def _degrade_research(article):
    article.research_brief = json.dumps(
        {
            "source_summary": (article.extracted_text or article.original_title or "")[
                :500
            ],
            "key_claims": [],
            "direct_quotes": [],
            "external_sources": [],
            "related_articles": [],
            "context_notes": "Research stage failed; using source text only.",
            "newsworthiness": "Auto-generated after research failure.",
            "impact_score": 30,
        }
    )
    article.impact_score = 30


_STAGE_DEGRADE_MAP = {
    "select": {
        "next_status": PipelineStatus.RESEARCHING,
        "log_message": "Degraded: auto-selected %s",
        "set_fields": lambda article: setattr(
            article,
            "selector_result",
            {"selected": True, "score": 6, "reason": "auto-selected after failure"},
        ),
    },
    "research": {
        "next_status": PipelineStatus.WRITING,
        "log_message": "Degraded: skipped research for %s",
        "set_fields": _degrade_research,
    },
    "write": {
        "next_status": PipelineStatus.EDITING,
        "log_message": "Degraded: minimal draft for %s",
        "set_fields": lambda article: setattr(
            article, "draft_article", _build_fallback_article(article)
        ),
    },
}


def _build_fallback_article(article) -> str:
    return build_fallback_article_json(article)


def _should_route_to_review(article) -> bool:
    from schemas.pipeline import load_pipeline_config

    review_cfg = load_pipeline_config().pipeline.review
    if review_cfg.enabled:
        threshold = review_cfg.auto_publish_threshold
        if threshold is None or (article.impact_score or 0) < threshold:
            return True
    return False


def _apply_fallback(article):
    fallback = article.draft_article or _build_fallback_article(article)
    article.final_article = fallback
    article.original_ai_article = fallback


def _apply_degrade_config(article, config: dict, run_id):
    from extensions import db
    from sqlalchemy.exc import SQLAlchemyError

    config["set_fields"](article)
    article.pipeline_status = config["next_status"]
    article.retry_count = 0
    article.last_error = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    if run_id:
        from tasks.pipeline import _log_pipeline

        _log_pipeline(
            run_id,
            _STAGE_STATUS_MAP.get(config["next_status"], config["next_status"]),
            "warning",
            config["log_message"],
            article_id=article.id,
        )
    from tasks.pipeline import _dispatch_next

    _dispatch_next(article.id, run_id=run_id, next_status=config["next_status"])


def _degrade_edit_stage(article, run_id):
    from extensions import db
    from sqlalchemy.exc import SQLAlchemyError
    from tasks.pipeline import _should_route_to_review

    _apply_fallback(article)
    article.retry_count = 0
    article.last_error = None

    if _should_route_to_review(article):
        article.pipeline_status = PipelineStatus.REVIEW
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            from tasks.pipeline import _log_pipeline

            _log_pipeline(
                run_id,
                "edit",
                "warning",
                "Degraded to review: %s",
                article_id=article.id,
            )
        return

    article.pipeline_status = PipelineStatus.DONE
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    if run_id:
        from tasks.pipeline import _log_pipeline

        _log_pipeline(
            run_id,
            "edit",
            "warning",
            "Degraded: used draft as final for %s",
            article_id=article.id,
        )
    logger.warning("Article %s finalized with degraded content", article.id)


def _degrade_and_advance(article, failed_stage: str, run_id=None):
    failed_stage = _STAGE_STATUS_MAP.get(failed_stage, failed_stage)

    logger.warning(
        "Degrading article %s from stage '%s' (retry_count=%s)",
        article.id,
        failed_stage,
        article.retry_count,
    )

    if failed_stage == "edit":
        _degrade_edit_stage(article, run_id)
        return

    stage_config = _STAGE_DEGRADE_MAP.get(failed_stage)
    if stage_config is None:
        logger.error(
            "Unknown stage '%s' for degradation of article %s",
            failed_stage,
            article.id,
        )
        return

    _apply_degrade_config(article, stage_config, run_id)


def _finalize(article_id: int):
    from models import Article
    from extensions import db
    from services.article import create_article_version

    try:
        article = db.session.get(Article, article_id)
        if article:
            _apply_fallback(article)
            article.retry_count = 0
            article.last_error = None

            if _should_route_to_review(article):
                article.pipeline_status = PipelineStatus.REVIEW
                db.session.commit()
                logger.info("Article %s queued for review (finalize)", article_id)
                return

            article.pipeline_status = PipelineStatus.DONE

            create_article_version(
                article,
                change_reason="pipeline_finalize",
                changed_by="pipeline:finalizer",
            )

            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error("Finalize failed for article %s: %s", article_id, e)


def degrade_stage(article, failed_stage: str, run_id=None):
    """Public API: advance article to next stage with degraded quality."""
    _degrade_and_advance(article, failed_stage, run_id)


def finalize_article(article_id: int):
    """Public API: mark article as done when editor stage is skipped."""
    _finalize(article_id)


def apply_fallback(article):
    """Public API: set final_article from draft or build minimal fallback."""
    _apply_fallback(article)


def should_route_to_review(article) -> bool:
    """Public API: check if article should go to review instead of done."""
    return _should_route_to_review(article)

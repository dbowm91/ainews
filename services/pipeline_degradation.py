"""Pipeline degradation and article finalization logic."""

import json
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import STAGE_STATUS_MAP, PipelineStatus, truncate_for_log
from services.article_fallback import build_fallback_article_json
from services.pipeline_utils import _dispatch_next, _log_pipeline

logger = get_task_logger(__name__)


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
        },
    )
    article.impact_score = 30


def _degrade_write_fields(article) -> None:
    article.draft_article = _build_fallback_article(article)
    article.writer_model = "fallback"


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
        "set_fields": _degrade_write_fields,
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
    from services.article import sanitize_final_article
    fallback = article.draft_article or _build_fallback_article(article)
    article.final_article = sanitize_final_article(fallback)
    article.original_ai_article = fallback


def _apply_degrade_config(article, config: dict, run_id, stage="unknown"):
    from sqlalchemy.exc import SQLAlchemyError

    from extensions import db
    from services.metrics import get_metrics

    config["set_fields"](article)
    article.degradation_count = (article.degradation_count or 0) + 1
    article.pipeline_status = config["next_status"]
    if config["next_status"] != PipelineStatus.DONE:
        article.publicly_visible = False

    get_metrics().counter_inc(
        "pipeline.degradation",
        labels={"stage": stage, "reason": config.get("log_message", "degraded")},
    )
    if article.degradation_count >= 2:
        get_metrics().counter_inc("pipeline.multi_stage_degradation")
    article.retry_count = 0
    article.last_error = None

    from services.publication import apply_publication_state
    apply_publication_state(article)

    if article.degradation_count >= 2:
        from services.auto_review import route_to_review

        route_to_review(article)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        logger.warning(
            "Article %s has degradation_count=%s, routing to review",
            article.id,
            article.degradation_count,
        )
        return

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    if run_id:
        _log_pipeline(
            run_id,
            STAGE_STATUS_MAP.get(config["next_status"], config["next_status"]),
            "warning",
            config["log_message"],
            article_id=article.id,
        )
    _dispatch_next(article.id, run_id=run_id, next_status=config["next_status"])


def _degrade_edit_stage(article, run_id):
    from sqlalchemy.exc import SQLAlchemyError

    from extensions import db
    from services.metrics import get_metrics

    _apply_fallback(article)
    article.degradation_count = (article.degradation_count or 0) + 1
    article.retry_count = 0
    article.last_error = None

    get_metrics().counter_inc(
        "pipeline.degradation",
        labels={"stage": "edit", "reason": "edit_stage_failed"},
    )
    if article.degradation_count >= 2:
        get_metrics().counter_inc("pipeline.multi_stage_degradation")

    if article.degradation_count >= 2 or _should_route_to_review(article):
        from services.auto_review import route_to_review

        route_to_review(article)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "warning",
                "Degraded to review (degradation_count=%s): %s",
                article.degradation_count,
                article_id=article.id,
            )
        return

    article.pipeline_status = PipelineStatus.DONE
    from services.publication import apply_publication_state
    apply_publication_state(article)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    if run_id:
        _log_pipeline(
            run_id,
            "edit",
            "warning",
            "Degraded: used draft as final for %s",
            article_id=article.id,
        )
    logger.warning("Article %s finalized with degraded content", article.id)


def _degrade_and_advance(article, failed_stage: str, run_id=None):
    failed_stage = STAGE_STATUS_MAP.get(failed_stage, failed_stage)

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

    _apply_degrade_config(article, stage_config, run_id, stage=failed_stage)


def post_finalize_article(article, run_id=None):
    """Post-finalize article: published_at, trend memory, webhooks, SLA metrics, embeddings.

    The publication is committed **before** any of the slow work starts.

    The trend memory proposal is an LLM request, and a local model can take
    minutes to answer it. If the write transaction were still open when that
    request went out, the database would be locked for the whole of it: every
    other writer would block, and a task killed by its own time limit would
    leave the lock held behind it. Committing the publication first means
    the lock is released before the model is asked anything, so the request
    can take as long as it needs.

    Everything below the commit is a side effect of the publication. None of
    it can hold the database, and none of it can unpublish the article.
    """
    from extensions import db
    from services.metrics import get_metrics
    from services.webhooks import trigger_event
    from tasks.embeddings import generate_article_embedding

    article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Release the write lock before anything slow happens.
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    if article.crawled_at:
        sla_duration = (article.published_at - article.crawled_at).total_seconds()
        get_metrics().histogram_observe("pipeline.e2e_duration_seconds", sla_duration)

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
        _dispatch_trend_memory(article)
    except Exception:  # noqa: BLE001 - the memory is a side effect, not a condition
        logger.warning(
            "Failed to dispatch the trend memory proposal for article %s, continuing",
            article.id,
        )

    try:
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
    except Exception:  # noqa: BLE001 - webhook failures are non-critical
        logger.warning(
            "Webhook trigger failed for article %s, continuing",
            article.id,
        )

    try:
        generate_article_embedding.delay(article.id)
    except Exception:  # noqa: BLE001 - embedding generation is non-critical
        logger.debug("Failed to enqueue embedding generation for article %s", article.id)


def _dispatch_trend_memory(article) -> None:
    """Ask for trend memory, out of band.

    The proposal runs in its own task so that the publication does not wait
    for the model. The task reads what it needs, ends its transaction, waits
    for the answer with no lock held, and writes the result in one short
    transaction once the answer is complete.
    """
    from extensions import db
    from models import ArticleMetric

    try:
        metric = db.session.get(ArticleMetric, article.id)
        engagement_data = {}
        if metric:
            engagement_data = {
                "newsletter_clicks": metric.newsletter_clicks or 0,
                "page_loads": metric.page_loads or 0,
            }
    except SQLAlchemyError:
        logger.warning(
            "Could not read the engagement metrics for article %s, continuing",
            article.id,
        )
        engagement_data = {}

    try:
        from tasks.trend_memory import propose_trend_memory_for_article

        propose_trend_memory_for_article.delay(article.id, engagement_data)
    except Exception:  # noqa: BLE001 - the proposal is not critical to publication
        logger.warning(
            "Failed to enqueue the trend memory proposal for article %s, continuing",
            article.id,
        )


def _finalize(article_id: int):
    from extensions import db
    from models import Article
    from services.article import create_article_version

    try:
        article = db.session.get(Article, article_id)
        if article:
            _apply_fallback(article)
            article.retry_count = 0
            article.last_error = None

            if _should_route_to_review(article):
                from services.auto_review import route_to_review

                route_to_review(article)
                db.session.commit()
                logger.info("Article %s queued for review (finalize)", article_id)
                return

            article.pipeline_status = PipelineStatus.DONE
            from services.publication import apply_publication_state
            apply_publication_state(article)

            create_article_version(
                article,
                change_reason="pipeline_finalize",
                changed_by="pipeline:finalizer",
            )

            db.session.commit()

            post_finalize_article(article)
    except (SQLAlchemyError, ImportError) as e:
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

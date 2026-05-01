"""Periodic cleanup tasks for maintenance."""

from datetime import datetime, timedelta, timezone

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from celery.utils.log import get_task_logger
from services.task_security import verify_task

logger = get_task_logger(__name__)


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def cleanup_old_pipeline_logs(self):
    """Delete pipeline logs older than 30 days.

    Runs daily via Celery Beat to prevent unbounded growth of the
    pipeline_logs table.
    """
    if not verify_task("cleanup_old_pipeline_logs", (), {}):
        logger.error("Invalid signature for cleanup_old_pipeline_logs")
        raise ValueError("Invalid task signature")

    from extensions import db
    from models import PipelineLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    BATCH_SIZE = 10000
    total_deleted = 0
    try:
        while True:
            ids = [
                r.id
                for r in PipelineLog.query.filter(PipelineLog.created_at < cutoff)
                .with_entities(PipelineLog.id)
                .limit(BATCH_SIZE)
                .all()
            ]
            if not ids:
                break
            deleted = PipelineLog.query.filter(PipelineLog.id.in_(ids)).delete(
                synchronize_session=False,
            )
            total_deleted += deleted
            db.session.commit()
        logger.info("Cleaned up %s pipeline logs older than 30 days", total_deleted)
        return {"deleted": total_deleted}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("cleanup_old_pipeline_logs exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Pipeline log cleanup failed: %s", e)
        raise


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True,
    soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def cleanup_expired_verifications(self):
    """Delete unverified subscribers whose verification has expired.

    Runs every 15 minutes via Celery Beat. A subscriber is removed if
    they never confirmed their email and the verification window has passed.
    """
    if not verify_task("cleanup_expired_verifications", (), {}):
        logger.error("Invalid signature for cleanup_expired_verifications")
        raise ValueError("Invalid task signature")

    from extensions import db
    from models import Subscriber
    from services.config_utils import get_config_with_default

    expiry_seconds = get_config_with_default("VERIFICATION_EXPIRY_SECONDS", 3600, int)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=expiry_seconds)
    try:
        deleted = (
            Subscriber.query.filter(Subscriber.confirmed_at.is_(None))
            .filter(Subscriber.subscribed_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        if deleted:
            logger.info("Cleaned up %s expired unverified subscribers", deleted)
        return {"deleted": deleted}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("cleanup_expired_verifications exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Expired verification cleanup failed: %s", e)
        raise


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, soft_time_limit=60, time_limit=120,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def cleanup_stale_limiter_slots(self):
    """Clean up stale model limiter slots in Redis.

    Runs every 5 minutes via Celery Beat to reclaim slots from tasks
    that exited without releasing their limiter slot (e.g., crashes).
    """
    if not verify_task("cleanup_stale_limiter_slots", (), {}):
        logger.error("Invalid signature for cleanup_stale_limiter_slots")
        raise ValueError("Invalid task signature")

    from services.limiter import get_limiter

    limiter = get_limiter()
    cleaned = limiter.cleanup_stale_slots()
    if cleaned:
        logger.info("Cleaned up %d stale limiter slots", cleaned)
    return {"cleaned": cleaned}


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def consolidate_trend_memory(self):
    """Consolidate low-importance trend memory entries when high-importance entries arrive.

    Runs nightly via Celery Beat (3:30 AM). When a high-importance entry exists
    for a topic, any overlapping low-importance entries are promoted to medium
    importance and TTL'd.
    """
    if not verify_task("consolidate_trend_memory", (), {}):
        logger.error("Invalid signature for consolidate_trend_memory")
        raise ValueError("Invalid task signature")

    from extensions import db
    from services.trend_memory import consolidate_all_topics

    try:
        results = consolidate_all_topics()
        total_merged = sum(results.values())
        logger.info(
            "Trend memory consolidation: merged=%s across topics=%s",
            total_merged,
            results,
        )
        return {"merged": total_merged, "topics": results}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("consolidate_trend_memory exceeded soft time limit")
        raise
    except Exception as e:
        logger.error("Trend memory consolidation failed: %s", e)
        raise


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def recalculate_impact_scores(self):
    """Recalculate impact scores for published articles based on engagement metrics.

    Runs nightly via Celery Beat (4:00 AM). Updates impact scores for articles
    in the DONE status by incorporating newsletter clicks and page loads.
    """
    if not verify_task("recalculate_impact_scores", (), {}):
        logger.error("Invalid signature for recalculate_impact_scores")
        raise ValueError("Invalid task signature")

    from extensions import db
    from models import Article, ArticleMetric

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        articles = (
            Article.query.filter(Article.pipeline_status == "done")
            .filter(Article.published_at >= cutoff)
            .join(ArticleMetric, Article.id == ArticleMetric.article_id)
            .all()
        )

        updated = 0
        for article in articles:
            metric = article.metrics
            if metric:
                clicks = metric.newsletter_clicks or 0
                loads = metric.page_loads or 0
                engagement_score = min((clicks * 10 + loads * 2) / 10, 50)
                if article.impact_score < engagement_score:
                    article.impact_score = int(engagement_score)
                    updated += 1

        if updated > 0:
            db.session.commit()
            logger.info("Recalculated impact scores: updated %d articles", updated)
        else:
            logger.info("Recalculate impact scores: no articles needed updating")

        return {"updated": updated}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("recalculate_impact_scores exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Recalculate impact scores failed: %s", e)
        raise


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def purge_trend_memory(self):
    """Purge expired trend memory entries from the database.

    Runs nightly via Celery Beat (3:45 AM). Removes all entries whose
    expires_at timestamp has passed.
    """
    if not verify_task("purge_trend_memory", (), {}):
        logger.error("Invalid signature for purge_trend_memory")
        raise ValueError("Invalid task signature")

    from extensions import db
    from services.trend_memory import purge_expired

    try:
        purged = purge_expired()
        logger.info("Trend memory purge: removed %d expired entries", purged)
        return {"purged": purged}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("purge_trend_memory exceeded soft time limit")
        raise
    except Exception as e:
        logger.error("Trend memory purge failed: %s", e)
        raise


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
    """Delete article versions older than specified days.

    Runs daily via Celery Beat to prevent unbounded growth of the
    article_versions table.

    Args:
        days_to_keep: Number of days to retain article versions.
        dry_run: If True, return what would be deleted without deleting.
    """
    if not verify_task("cleanup_old_article_versions", (), {"days_to_keep": days_to_keep, "dry_run": dry_run}):
        logger.error("Invalid signature for cleanup_old_article_versions")
        raise ValueError("Invalid task signature")

    from schemas.tasks import CleanupArticleVersionsTask

    try:
        validated = CleanupArticleVersionsTask(days_to_keep=days_to_keep, dry_run=dry_run)
    except Exception as e:
        logger.warning("Invalid cleanup_old_article_versions input: %s", e)
        raise TypeError(f"Invalid cleanup_old_article_versions input: {e}") from e

    from extensions import db
    from models import ArticleVersion

    cutoff = datetime.now(timezone.utc) - timedelta(days=validated.days_to_keep)
    try:
        query = ArticleVersion.query.filter(ArticleVersion.created_at < cutoff)
        if validated.dry_run:
            versions = query.all()
            article_ids = list({v.article_id for v in versions})
            oldest = min((v.created_at for v in versions), default=None)
            return {
                "would_delete": len(versions),
                "oldest_version": oldest.isoformat() if oldest else None,
                "articles_affected": len(article_ids),
                "dry_run": True,
            }
        BATCH_SIZE = 10000
        total_deleted = 0
        while True:
            ids = [
                r.id
                for r in ArticleVersion.query.filter(
                    ArticleVersion.created_at < cutoff,
                )
                .with_entities(ArticleVersion.id)
                .limit(BATCH_SIZE)
                .all()
            ]
            if not ids:
                break
            deleted = ArticleVersion.query.filter(
                ArticleVersion.id.in_(ids),
            ).delete(synchronize_session=False)
            total_deleted += deleted
            db.session.commit()
        logger.info(
            "Cleaned up %s article versions older than %d days",
            total_deleted,
            validated.days_to_keep,
        )
        return {"deleted": total_deleted}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("cleanup_old_article_versions exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Article version cleanup failed: %s", e)
        raise

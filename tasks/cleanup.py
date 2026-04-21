"""Periodic cleanup tasks for maintenance."""

from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from billiard.exceptions import SoftTimeLimitExceeded

logger = get_task_logger(__name__)


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def cleanup_old_pipeline_logs(self):
    """Delete pipeline logs older than 30 days.

    Runs daily via Celery Beat to prevent unbounded growth of the
    pipeline_logs table.
    """
    from models import PipelineLog
    from extensions import db

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
                synchronize_session=False
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


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def cleanup_expired_verifications(self):
    """Delete unverified subscribers whose verification has expired.

    Runs every 15 minutes via Celery Beat. A subscriber is removed if
    they never confirmed their email and the verification window has passed.
    """
    from models import Subscriber
    from extensions import db
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


@shared_task(bind=True, soft_time_limit=60, time_limit=120)
def cleanup_stale_limiter_slots(self):
    """Clean up stale model limiter slots in Redis.

    Runs every 5 minutes via Celery Beat to reclaim slots from tasks
    that exited without releasing their limiter slot (e.g., crashes).
    """
    from services.limiter import get_limiter

    limiter = get_limiter()
    cleaned = limiter.cleanup_stale_slots()
    if cleaned:
        logger.info("Cleaned up %d stale limiter slots", cleaned)
    return {"cleaned": cleaned}


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def consolidate_trend_memory(self):
    """Consolidate low-importance trend memory entries when high-importance entries arrive.

    Runs nightly via Celery Beat. When a high-importance entry exists for a topic,
    any overlapping low-importance entries are promoted to medium importance and TTL'd.
    Also purges all expired entries.
    """
    from services.trend_memory import consolidate_all_topics, purge_expired

    try:
        results = consolidate_all_topics()
        total_merged = sum(results.values())
        purged = purge_expired()
        logger.info(
            "Trend memory consolidation: merged=%s across topics=%s, purged expired=%d",
            total_merged,
            results,
            purged,
        )
        return {"merged": total_merged, "topics": results, "purged": purged}
    except SoftTimeLimitExceeded:
        logger.error("consolidate_trend_memory exceeded soft time limit")
        raise
    except Exception as e:
        logger.error("Trend memory consolidation failed: %s", e)
        raise


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
    """Delete article versions older than specified days.

    Runs daily via Celery Beat to prevent unbounded growth of the
    article_versions table.

    Args:
        days_to_keep: Number of days to retain article versions.
        dry_run: If True, return what would be deleted without deleting.
    """
    from models import ArticleVersion
    from extensions import db

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    try:
        query = ArticleVersion.query.filter(ArticleVersion.created_at < cutoff)
        if dry_run:
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
                    ArticleVersion.created_at < cutoff
                )
                .with_entities(ArticleVersion.id)
                .limit(BATCH_SIZE)
                .all()
            ]
            if not ids:
                break
            deleted = ArticleVersion.query.filter(
                ArticleVersion.id.in_(ids)
            ).delete(synchronize_session=False)
            total_deleted += deleted
            db.session.commit()
        logger.info(
            "Cleaned up %s article versions older than %d days",
            total_deleted,
            days_to_keep,
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

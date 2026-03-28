"""Periodic cleanup tasks for maintenance."""

from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger

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
    try:
        deleted = PipelineLog.query.filter(PipelineLog.created_at < cutoff).delete()
        db.session.commit()
        logger.info(f"Cleaned up {deleted} pipeline logs older than 30 days")
        return {"deleted": deleted}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Pipeline log cleanup failed: {e}")
        raise

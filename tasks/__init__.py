"""Re-export all Celery tasks for backward compatibility.

Every module that defines a Celery task MUST be imported here. The worker
bootstraps with ``import tasks``, so a task whose module is not imported is
never registered on the worker and any beat-scheduled dispatch of it fails
with "Received unregistered task of type ...".
"""

from constants import MAX_STAGE_RETRIES
from tasks.cleanup import (
    cleanup_expired_verifications,
    cleanup_old_article_versions,
    cleanup_old_pipeline_logs,
    cleanup_stale_limiter_slots,
    consolidate_trend_memory,
    maintain_editorial_memory,
    purge_trend_memory,
    recalculate_impact_scores,
)
from tasks.crawl import run_all_sources
from tasks.edit import edit_article
from tasks.extract import process_item
from tasks.newsletter import (
    generate_daily_newsletters,
    retry_failed_newsletter_deliveries,
)
from tasks.pipeline import (
    _assign_tags,
    _finalize,
    _handle_stage_failure,
    _log_pipeline,
)
from services.pipeline_degradation import degrade_stage as _degrade_and_advance
from tasks.research import research_article
from tasks.retry import retry_stuck
from tasks.scheduler import auto_approve_review_articles, publish_scheduled_articles
from tasks.select import select_article
from tasks.subscribers import cleanup_inactive_subscribers
from tasks.trend_memory import propose_trend_memory_for_article
from tasks.webhook import dispatch_webhook_task
from tasks.write import write_article
from tasks.embeddings import backfill_embeddings

__all__ = [
    "run_all_sources",
    "process_item",
    "select_article",
    "research_article",
    "write_article",
    "edit_article",
    "retry_stuck",
    "publish_scheduled_articles",
    "auto_approve_review_articles",
    "propose_trend_memory_for_article",
    "_log_pipeline",
    "_degrade_and_advance",
    "_handle_stage_failure",
    "_finalize",
    "_assign_tags",
    "dispatch_webhook_task",
    "backfill_embeddings",
    "cleanup_old_pipeline_logs",
    "cleanup_expired_verifications",
    "cleanup_stale_limiter_slots",
    "consolidate_trend_memory",
    "maintain_editorial_memory",
    "purge_trend_memory",
    "recalculate_impact_scores",
    "cleanup_old_article_versions",
    "generate_daily_newsletters",
    "retry_failed_newsletter_deliveries",
    "cleanup_inactive_subscribers",
    "MAX_STAGE_RETRIES",
]

"""Re-export all Celery tasks for backward compatibility."""

from constants import MAX_STAGE_RETRIES
from tasks.crawl import run_all_sources
from tasks.edit import edit_article
from tasks.extract import process_item
from tasks.pipeline import (
    _assign_tags,
    _degrade_and_advance,
    _finalize,
    _handle_stage_failure,
    _log_pipeline,
)
from tasks.research import research_article
from tasks.retry import retry_stuck
from tasks.scheduler import publish_scheduled_articles
from tasks.select import select_article
from tasks.webhook import dispatch_webhook_task
from tasks.write import write_article

__all__ = [
    "run_all_sources",
    "process_item",
    "select_article",
    "research_article",
    "write_article",
    "edit_article",
    "retry_stuck",
    "publish_scheduled_articles",
    "_log_pipeline",
    "_degrade_and_advance",
    "_handle_stage_failure",
    "_finalize",
    "_assign_tags",
    "dispatch_webhook_task",
    "MAX_STAGE_RETRIES",
]

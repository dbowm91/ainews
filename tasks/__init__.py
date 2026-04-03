"""Re-export all Celery tasks for backward compatibility."""

from tasks.pipeline import (
    _log_pipeline,
    _degrade_and_advance,
    _handle_stage_failure,
    _finalize,
    _assign_tags,
    MAX_STAGE_RETRIES,
)
from tasks.scheduler import publish_scheduled_articles
from tasks.crawl import run_all_sources
from tasks.extract import process_item
from tasks.select import select_article
from tasks.research import research_article
from tasks.write import write_article
from tasks.edit import edit_article
from tasks.retry import retry_stuck

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
    "MAX_STAGE_RETRIES",
]

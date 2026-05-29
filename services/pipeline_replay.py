"""Pipeline rescue/replay service for manual article stage recovery.

Allows operators to re-run an article from a specific stage, inspect previous
outputs, and avoid manual DB surgery when the pipeline produces bad or stuck states.
"""

import logging
from typing import Any

from extensions import db
from models import Article, ArticleVersion, PipelineLog

logger = logging.getLogger(__name__)

VALID_REPLAY_STAGES = frozenset(["select", "research", "write", "edit"])

# Field clearing map: stage -> fields to clear
# Be conservative - do not delete citations unless task explicitly regenerates them
STAGE_FIELD_CLEAR_MAP = {
    "select": [
        "selector_result",
        "research_brief",
        "draft_article",
        "final_article",
        "selected_at",
        "published_at",
    ],
    "research": [
        "research_brief",
        "draft_article",
        "final_article",
    ],
    "write": [
        "draft_article",
        "final_article",
    ],
    "edit": [
        "final_article",
    ],
}

# Pre-stage status for each replay stage
PRE_STAGE_STATUS = {
    "select": "pending",
    "research": "selected",
    "write": "written",
    "edit": "written",
}


def get_article_pipeline_history(article_id: int) -> list[dict[str, Any]]:
    """Get pipeline history for an article from pipeline logs.

    Args:
        article_id: The article ID

    Returns:
        List of history entries sorted by created_at descending
    """
    logs = (
        PipelineLog.query.filter_by(article_id=article_id)
        .order_by(PipelineLog.created_at.desc())
        .limit(100)
        .all()
    )

    return [
        {
            "id": log.id,
            "stage": log.stage,
            "level": log.level,
            "message": log.message,
            "status": log.status,
            "error": log.error,
            "meta": log.meta,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


def replay_article_stage(
    article_id: int,
    stage: str,
    reason: str,
    provider_id: str | None = None,
    model: str | None = None,
    changed_by: str = "admin",
) -> dict[str, Any]:
    """Replay an article from a specific stage.

    Creates a version snapshot, clears downstream fields, sets the correct
    pre-stage status, and dispatches the relevant task.

    Args:
        article_id: The article ID
        stage: Stage to replay ("select", "research", "write", "edit")
        reason: Reason for replay (e.g., "manual_replay_after_quality_failure")
        provider_id: Optional provider override (ignored if not supported)
        model: Optional model override (ignored if not supported)
        changed_by: User or system initiating the replay

    Returns:
        Dict with result info including task_id and cleared fields

    Raises:
        ValueError: If article doesn't exist or stage is invalid
    """
    if stage not in VALID_REPLAY_STAGES:
        raise ValueError(f"Invalid stage: {stage}. Must be one of: {', '.join(VALID_REPLAY_STAGES)}")

    article = db.session.get(Article, article_id)
    if not article:
        raise ValueError(f"Article {article_id} not found")

    # Create version snapshot before destructive modifications
    _create_replay_version(article, stage, reason, changed_by)

    # Clear downstream fields for the stage
    fields_cleared = _clear_stage_fields(article, stage)

    # Set pre-stage status
    from constants import PipelineStatus
    article.pipeline_status = PipelineStatus(PRE_STAGE_STATUS[stage])

    # Clear last_error since we're re-running
    article.last_error = None

    # Clear retry count for fresh start
    article.retry_count = 0

    db.session.commit()

    # Dispatch the relevant task
    task_id = _dispatch_stage_task(article_id, stage, provider_id, model)

    logger.info(
        "Replay dispatched for article %s stage %s: cleared %s, task %s",
        article_id,
        stage,
        fields_cleared,
        task_id,
    )

    result = {
        "article_id": article_id,
        "stage": stage,
        "task_id": task_id,
        "reason": reason,
        "fields_cleared": fields_cleared,
        "new_status": article.pipeline_status,
    }

    # Warn if provider/model override was requested but not used
    if provider_id is not None or model is not None:
        result["warning"] = "provider/model override not yet implemented in replay"

    return result


def restore_article_version(
    article_id: int,
    version_id: int,
    changed_by: str = "admin",
) -> dict[str, Any]:
    """Restore an article to a previous version.

    Creates a version snapshot of current state before restoring,
    then restores the final_article and original_ai_article from
    the specified version.

    Args:
        article_id: The article ID
        version_id: The ArticleVersion ID to restore
        changed_by: User or system initiating the restore

    Returns:
        Dict with result info including restored version number

    Raises:
        ValueError: If article or version doesn't exist
    """
    article = db.session.get(Article, article_id)
    if not article:
        raise ValueError(f"Article {article_id} not found")

    version = db.session.get(ArticleVersion, version_id)
    if not version:
        raise ValueError(f"Version {version_id} not found")

    if version.article_id != article_id:
        raise ValueError(f"Version {version_id} does not belong to article {article_id}")

    # Create version snapshot before restoring
    _create_replay_version(
        article,
        "restore",
        f"restore_to_version_{version.version_number}",
        changed_by,
    )

    # Restore fields from version
    article.final_article = version.final_article
    article.original_ai_article = version.original_ai_article

    # Reset pipeline status to review for re-editing
    from constants import PipelineStatus
    article.pipeline_status = PipelineStatus.REVIEW

    db.session.commit()

    logger.info(
        "Restored article %s to version %s",
        article_id,
        version.version_number,
    )

    return {
        "article_id": article_id,
        "restored_version_id": version_id,
        "restored_version_number": version.version_number,
        "new_status": article.pipeline_status,
    }


def _create_replay_version(
    article: Article,
    stage: str,
    reason: str,
    changed_by: str,
) -> None:
    """Create a version snapshot before replay or restore."""
    from sqlalchemy.exc import IntegrityError

    max_version = (
        db.session.scalar(
            db.select(db.func.max(ArticleVersion.version_number)).where(
                ArticleVersion.article_id == article.id
            )
        )
        or 0
    )

    source_fields = {
        "pipeline_status": article.pipeline_status,
        "selector_result": article.selector_result,
        "research_brief": article.research_brief,
        "draft_article": article.draft_article,
        "final_article": article.final_article,
        "selected_at": article.selected_at.isoformat() if article.selected_at else None,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "replay_stage": stage,
    }

    version = ArticleVersion(
        article_id=article.id,
        version_number=max_version + 1,
        final_article=article.final_article,
        original_ai_article=article.original_ai_article,
        source_fields=source_fields,
        change_reason=f"replay:{reason}",
        changed_by=changed_by,
    )
    db.session.add(version)

    max_retries = 2
    for attempt in range(max_retries):
        try:
            db.session.flush()
            return
        except IntegrityError:
            db.session.rollback()
            if attempt == max_retries - 1:
                logger.error(
                    "Failed to create version for article %s after %d retries",
                    article.id,
                    max_retries,
                )
                raise
            logger.debug("Version race for article %s, retrying", article.id)


def _clear_stage_fields(article: Article, stage: str) -> list[str]:
    """Clear downstream fields for the given stage."""
    fields_to_clear = STAGE_FIELD_CLEAR_MAP.get(stage, [])
    cleared = []

    for field in fields_to_clear:
        if hasattr(article, field):
            current_val = getattr(article, field)
            if current_val is not None:
                setattr(article, field, None)
                cleared.append(field)

    return cleared


def _dispatch_stage_task(
    article_id: int,
    stage: str,
    provider_id: str | None,
    model: str | None,
) -> str:
    """Dispatch the appropriate Celery task for the stage.

    Returns the task ID.
    """
    from tasks.select import select_article
    from tasks.research import research_article
    from tasks.write import write_article
    from tasks.edit import edit_article

    # Note: provider_id and model overrides are not yet implemented.
    # The current pipeline resolves provider at task execution time.

    task_map = {
        "select": select_article,
        "research": research_article,
        "write": write_article,
        "edit": edit_article,
    }

    task_func = task_map.get(stage)
    if not task_func:
        raise ValueError(f"No task found for stage: {stage}")

    # Dispatch with no run_id for manual replay (creates fresh run context)
    result = task_func.apply_async(args=[article_id], kwargs={"run_id": None})
    return result.id
"""Pipeline rescue/replay API endpoints."""

import logging

from flask import Response, request

from extensions import db
from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response

logger = logging.getLogger(__name__)


@admin_api_bp.route("/articles/<int:article_id>/pipeline/history", methods=["GET"])
@require_auth
def get_pipeline_history(article_id: int) -> Response:
    """Get pipeline history for an article.

    Returns pipeline log entries for the article, sorted by creation time descending.
    """
    article = db.session.get(Article, article_id)
    if not article:
        return api_response(error=f"Article {article_id} not found", status=404)

    from services.pipeline_replay import get_article_pipeline_history

    history = get_article_pipeline_history(article_id)

    return api_response(data={"article_id": article_id, "history": history})


@admin_api_bp.route("/articles/<int:article_id>/pipeline/replay", methods=["POST"])
@require_auth
def replay_article_stage(article_id: int) -> Response:
    """Replay an article from a specific stage.

    Request body:
    {
        "stage": "select|research|write|edit",
        "provider_id": null,  # optional, currently ignored
        "model": null,        # optional, currently ignored
        "reason": "manual_replay_after_quality_failure"
    }
    """
    from models import Article

    article = db.session.get(Article, article_id)
    if not article:
        return api_response(error=f"Article {article_id} not found", status=404)

    data = request.get_json()
    if not data:
        return api_response(error="Request body is required", status=400)

    stage = data.get("stage")
    if not stage:
        return api_response(error="stage is required", status=400)

    reason = data.get("reason", "manual_replay")
    provider_id = data.get("provider_id")
    model = data.get("model")

    from services.pipeline_replay import replay_article_stage, VALID_REPLAY_STAGES

    if stage not in VALID_REPLAY_STAGES:
        return api_response(
            error=f"Invalid stage: {stage}. Must be one of: {', '.join(VALID_REPLAY_STAGES)}",
            status=400,
        )

    from services.audit import log_admin_action

    try:
        result = replay_article_stage(
            article_id=article_id,
            stage=stage,
            reason=reason,
            provider_id=provider_id,
            model=model,
            changed_by="admin",
        )
    except ValueError as e:
        return api_response(error=str(e), status=400)

    try:
        log_admin_action(
            action=f"article_replay_{stage}",
            target_type="article",
            target_id=article_id,
            details={
                "stage": stage,
                "reason": reason,
                "fields_cleared": result.get("fields_cleared", []),
                "task_id": result.get("task_id"),
            },
            category="pipeline",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article replay", exc_info=True)

    meta = {"message": f"Replay of {stage} stage dispatched"}
    if "warning" in result:
        meta["warning"] = result["warning"]

    return api_response(data=result, meta=meta, status=202)


@admin_api_bp.route("/articles/<int:article_id>/pipeline/restore-version", methods=["POST"])
@require_auth
def restore_article_version(article_id: int) -> Response:
    """Restore an article to a previous version.

    Request body:
    {
        "version_id": int
    }
    """
    from models import Article

    article = db.session.get(Article, article_id)
    if not article:
        return api_response(error=f"Article {article_id} not found", status=404)

    data = request.get_json()
    if not data:
        return api_response(error="Request body is required", status=400)

    version_id = data.get("version_id")
    if version_id is None:
        return api_response(error="version_id is required", status=400)

    if not isinstance(version_id, int):
        return api_response(error="version_id must be an integer", status=400)

    from services.pipeline_replay import restore_article_version

    try:
        result = restore_article_version(
            article_id=article_id,
            version_id=version_id,
            changed_by="admin",
        )
    except ValueError as e:
        return api_response(error=str(e), status=400)

    from services.audit import log_admin_action

    try:
        log_admin_action(
            action="article_restore_version",
            target_type="article",
            target_id=article_id,
            details={
                "version_id": version_id,
                "restored_version_number": result.get("restored_version_number"),
            },
            category="pipeline",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article restore", exc_info=True)

    return api_response(
        data=result,
        meta={"message": f"Restored to version {result.get('restored_version_number')}"},
    )
"""Admin pipeline audit surfaces.

Two views over the same audit trail:

``/admin/pipeline-audit``
    The pipeline's activity feed -- every stage event, filterable. This is
    the page that answers "what is the pipeline doing right now, and what
    has it been doing today?"

``/admin/articles/<id>/audit``
    The full trail for a single article -- the stage timeline plus the
    provenance the pipeline recorded on the article itself. This is the page
    that answers "why does this article look the way it does?"

Both are read-only. They read the ``PipelineLog``, ``PipelineRun`` and
``AuditLog`` tables that the pipeline and the admin actions already write.
"""

import logging

from flask import abort, render_template, request

from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)


@admin_bp.route("/pipeline-audit")
@require_auth
def pipeline_audit() -> str:
    """Show the pipeline activity feed."""
    from services.pipeline_audit import (
        list_known_stages,
        list_operator_actions,
        list_stage_events,
    )

    page = max(1, request.args.get("page", 1, type=int))
    stage = request.args.get("stage", "", type=str).strip()
    level = request.args.get("level", "", type=str).strip()
    article_id = request.args.get("article_id", "", type=str).strip()

    parsed_article_id: int | None = None
    if article_id:
        try:
            parsed_article_id = int(article_id)
        except ValueError:
            parsed_article_id = None

    result = list_stage_events(
        stage=stage or None,
        level=level or None,
        article_id=parsed_article_id,
        page=page,
    )

    actions, action_total = list_operator_actions(page=1, per_page=15)

    return render_template(
        "admin/pipeline_audit.html",
        events=result.events,
        total=result.total,
        page=result.page,
        per_page=result.per_page,
        has_next=result.has_next,
        has_prev=result.has_prev,
        summaries=result.summaries,
        stages=list_known_stages(),
        stage_filter=stage,
        level_filter=level,
        article_filter=article_id,
        actions=actions,
        action_total=action_total,
    )


@admin_bp.route("/articles/<int:article_id>/audit")
@require_auth
def article_audit(article_id: int) -> str:
    """Show the full audit trail for a single article."""
    from services.pipeline_audit import get_article_trail

    trail = get_article_trail(article_id)
    if trail is None:
        abort(404)

    return render_template(
        "admin/article_audit.html",
        trail=trail,
        provenance=trail.provenance,
        events=trail.events,
        summaries=trail.stage_summaries,
        versions=trail.versions,
    )

from flask import current_app, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from constants import PER_PAGE_PIPELINE, PER_PAGE_PIPELINE_LOGS
from extensions import db
from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_token, wants_html
from services.audit import log_admin_action
from services.task_security import get_signed_kwargs


@admin_bp.route("/pipelines")
@require_auth
def pipelines():
    from models import PipelineRun
    from services.pagination import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    run_type = request.args.get("type", "", type=str).strip()

    q = PipelineRun.query.order_by(PipelineRun.started_at.desc())
    if run_type:
        q = q.filter_by(run_type=run_type)
    per_page = PER_PAGE_PIPELINE
    runs, has_next, next_page = paginate_query(q, page, per_page)

    running = PipelineRun.query.filter_by(status="running").order_by(PipelineRun.started_at.desc()).limit(100).all()

    return render_template(
        "admin/pipelines.html",
        runs=runs,
        running=running,
        has_next=has_next,
        next_page=next_page,
        page=page,
        run_type=run_type,
    )


@admin_bp.route("/pipelines/<int:run_id>/logs")
@require_auth
def pipeline_logs(run_id):
    from models import PipelineLog, PipelineRun
    from services.pagination import paginate_query

    run = db.get_or_404(PipelineRun, run_id)
    level = request.args.get("level", "", type=str).strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_PIPELINE_LOGS

    q = PipelineLog.query.filter_by(run_id=run_id).order_by(
        PipelineLog.created_at.asc(),
    )
    if level:
        q = q.filter_by(level=level)

    total_count = q.count()
    logs, has_next, next_page = paginate_query(q, page, per_page)
    level_filter = level

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/pipeline_logs.html",
            logs=logs,
            run=run,
            level_filter=level_filter,
            has_next=has_next,
            next_page=next_page,
            page=page,
            total_count=total_count,
        )
    return render_template(
        "admin/pipeline_logs.html",
        logs=logs,
        run=run,
        level_filter=level_filter,
        has_next=has_next,
        next_page=next_page,
        page=page,
        total_count=total_count,
    )


@admin_bp.route("/trigger-crawl", methods=["POST"])
@require_auth
@validate_csrf_token
def trigger_crawl():
    from extensions import db
    from models import PipelineRun
    from tasks import run_all_sources

    try:
        run = PipelineRun(
            run_type="crawl",
            status="running",
            triggered_by="manual",
        )
        db.session.add(run)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        request_id = getattr(g, "request_id", None)
        headers = {"request_id": request_id} if request_id else None
        kwargs = {"run_id": run.id}
        signed_kwargs = get_signed_kwargs("run_all_sources", (), kwargs)
        result = run_all_sources.apply_async(kwargs=signed_kwargs, headers=headers)
        run.task_id = result.id
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        log_admin_action(
            "pipeline_trigger_crawl",
            target_type="pipeline",
            target_id=run.id,
            details={"run_type": "crawl"},
            category="pipeline",
        )
        message = "Crawl started"
        if request.headers.get("HX-Request"):
            return (
                f'<div class="dash-action"><span class="health-dot green blink"></span> {message}</div>',
                202,
            )
        if wants_html():
            flash(f"{message} (run #{run.id}).", "success")
            return redirect(url_for("admin.pipelines"))
        return jsonify(
            {"message": message, "task_id": result.id, "run_id": run.id},
        ), 202
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to trigger crawl")
        message = f"Failed to start crawl: {str(e)[:200]}"
        if request.headers.get("HX-Request"):
            return (
                f'<div class="dash-action"><span class="health-dot red"></span> {message}</div>',
                503,
            )
        if wants_html():
            flash(message, "error")
            return redirect(url_for("admin.pipelines"))
        return jsonify({"error": message}), 503

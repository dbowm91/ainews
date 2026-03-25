from flask import render_template, request, jsonify, current_app
from routes.admin import admin_bp, require_auth
from constants import PER_PAGE_PIPELINE, PER_PAGE_PIPELINE_LOGS


@admin_bp.route("/pipelines")
@require_auth
def pipelines():
    from models import PipelineRun
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    run_type = request.args.get("type", "", type=str).strip()

    q = PipelineRun.query.order_by(PipelineRun.started_at.desc())
    if run_type:
        q = q.filter_by(run_type=run_type)
    per_page = PER_PAGE_PIPELINE
    runs, has_next, next_page = paginate_query(q, page, per_page)

    running = PipelineRun.query.filter_by(status="running").all()

    return render_template(
        "admin/pipelines.html",
        runs=runs,
        running=running,
        has_next=has_next,
        next_page=next_page,
        run_type=run_type,
    )


@admin_bp.route("/pipelines/<int:run_id>/logs")
@require_auth
def pipeline_logs(run_id):
    from models import PipelineRun, PipelineLog
    from services.utils import paginate_query

    run = PipelineRun.query.get_or_404(run_id)
    level = request.args.get("level", "", type=str).strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_PIPELINE_LOGS

    q = PipelineLog.query.filter_by(run_id=run_id).order_by(
        PipelineLog.created_at.asc()
    )
    if level:
        q = q.filter_by(level=level)

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
        )
    return render_template(
        "admin/pipeline_logs.html",
        logs=logs,
        run=run,
        level_filter=level_filter,
        has_next=has_next,
        next_page=next_page,
    )


@admin_bp.route("/trigger-crawl", methods=["POST"])
@require_auth
def trigger_crawl():
    from tasks import run_all_sources
    from models import PipelineRun
    from extensions import db

    try:
        run = PipelineRun(
            run_type="crawl",
            status="running",
            triggered_by="manual",
        )
        db.session.add(run)
        db.session.commit()

        result = run_all_sources.delay(run_id=run.id)
        run.task_id = result.id
        db.session.commit()
        return jsonify(
            {"message": "Crawl started", "task_id": result.id, "run_id": run.id}
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger crawl")
        return jsonify({"message": "Failed to start crawl"}), 503

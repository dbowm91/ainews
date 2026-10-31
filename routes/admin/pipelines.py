from datetime import datetime, timezone

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


def _enqueue_failure_response(run_id: int, exc: Exception):
    """Close a run that was created but could not be published to Celery."""
    from models import PipelineRun

    current_app.logger.error(
        "Failed to enqueue crawl for pipeline run %s",
        run_id,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    db.session.rollback()
    run = db.session.get(PipelineRun, run_id)
    if run is not None and run.status == "running" and not run.task_id:
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.error_message = f"Could not queue crawl task: {str(exc)[:500]}"
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to mark undispatched pipeline run %s failed", run_id)

    if request.headers.get("HX-Request"):
        return '<div class="dash-action"><span class="health-dot red"></span> Failed to queue crawl. Check server logs.</div>', 503
    if wants_html():
        flash(f"Failed to queue crawl for run #{run_id}. Check server logs.", "error")
        return redirect(url_for("admin.pipelines"))
    return jsonify({"error": "Failed to queue crawl", "run_id": run_id}), 503


@admin_bp.route("/trigger-crawl", methods=["POST"])
@require_auth
@validate_csrf_token
def trigger_crawl():
    from extensions import db
    from models import PipelineRun
    from celery_app import celery_app
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
        try:
            result = celery_app.send_task(
                run_all_sources.name,
                kwargs=signed_kwargs,
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001 - publish failures must close the run instead of stranding it
            return _enqueue_failure_response(run.id, exc)
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


@admin_bp.route("/pipelines/<int:run_id>/cancel", methods=["POST"])
@require_auth
@validate_csrf_token
def cancel_pipeline(run_id: int):
    """Stop queued and active Celery work associated with one pipeline run."""
    from models import PipelineRun
    from services.pipeline_cancellation import (
        get_pipeline_task_ids,
        inspect_pipeline_task_ids,
        mark_pipeline_cancelled,
        task_set_key,
    )

    run = db.session.get(PipelineRun, run_id)
    if run is None:
        return jsonify({"error": "Pipeline run not found."}), 404
    if run.status != "running":
        message = f"Run #{run.id} is already {run.status}."
        if wants_html():
            flash(message, "warning")
            return redirect(url_for("admin.pipelines"))
        return jsonify({"message": message, "status": run.status}), 200

    run.status = "cancelled"
    run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    run.error_message = "Cancelled by administrator."
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to mark pipeline run %s cancelled", run_id)
        return jsonify({"error": "Could not cancel pipeline run."}), 503

    try:
        mark_pipeline_cancelled(run_id)
    except Exception:  # noqa: BLE001 - task revocation below remains a second stop mechanism
        current_app.logger.warning("Could not persist cancellation flag for run %s", run_id, exc_info=True)

    task_ids = get_pipeline_task_ids(run_id)
    if run.task_id:
        task_ids.add(run.task_id)
    revoke_error = None
    try:
        from celery_app import celery_app

        task_ids.update(inspect_pipeline_task_ids(celery_app, run_id))
        if task_ids:
            celery_app.control.revoke(sorted(task_ids), terminate=True, signal="SIGTERM")
    except Exception as exc:  # noqa: BLE001 - persisted cancellation still blocks new stages
        revoke_error = str(exc)[:200]
        current_app.logger.warning("Could not revoke every task for run %s: %s", run_id, exc)

    try:
        from extensions import get_redis

        get_redis().delete(task_set_key(run_id))
    except Exception:  # noqa: BLE001 - the task index expires on its own
        current_app.logger.debug("Could not clear task index for run %s", run_id, exc_info=True)

    log_admin_action(
        "pipeline_cancel",
        target_type="pipeline",
        target_id=run.id,
        details={"revoked_task_count": len(task_ids)},
        category="pipeline",
    )
    message = f"Cancellation requested for run #{run.id}."
    if revoke_error:
        message += " The run is marked cancelled; some workers may take up to two minutes to release their active request."
    if wants_html():
        flash(message, "success")
        return redirect(url_for("admin.pipelines"))
    return jsonify({"message": message, "status": "cancelled", "revoked_task_count": len(task_ids)}), 202

"""Cancellation behavior for admin-triggered pipeline shutdown."""

from unittest.mock import patch

from models import PipelineRun
from services.pipeline_cancellation import cancel_key, task_set_key


def test_admin_cancel_marks_run_and_revokes_tracked_and_active_tasks(app, auth_client, mock_redis_client):
    with app.app_context():
        run = PipelineRun(
            task_id="root-task",
            run_type="manual",
            status="running",
            triggered_by="admin",
        )
        from extensions import db

        db.session.add(run)
        db.session.commit()
        run_id = run.id

    redis = mock_redis_client
    redis.set(task_set_key(run_id), "indexed")
    from services.metrics import MetricsCollector

    with (
        patch("services.pipeline_cancellation.inspect_pipeline_task_ids", return_value={"active-task"}),
        patch("services.pipeline_cancellation.mark_pipeline_cancelled") as mark_cancelled,
        patch("extensions.get_redis", return_value=redis),
        patch("services.pipeline_cancellation.get_pipeline_task_ids", return_value={"queued-task"}),
        patch("routes.admin.pipelines.log_admin_action"),
        patch("services.metrics.get_metrics", return_value=MetricsCollector()),
        patch("celery_app.celery_app.control.revoke") as revoke,
    ):
        response = auth_client.post(f"/admin/pipelines/{run_id}/cancel")

    assert response.status_code == 202
    assert response.json["status"] == "cancelled"
    assert response.json["revoked_task_count"] == 3
    mark_cancelled.assert_called_once_with(run_id)
    revoke.assert_called_once_with(
        ["active-task", "queued-task", "root-task"],
        terminate=True,
        signal="SIGTERM",
    )
    assert redis.get(task_set_key(run_id)) is None

    with app.app_context():
        from extensions import db

        saved = db.session.get(PipelineRun, run_id)
        assert saved.status == "cancelled"
        assert saved.error_message == "Cancelled by administrator."


def test_cancel_key_is_stable_for_persisted_run():
    assert cancel_key(42) == "ainews:pipeline_run:cancelled:42"

"""Tests for periodic cleanup tasks."""

from datetime import datetime, timezone, timedelta


class TestCleanupOldPipelineLogs:
    """Test pipeline log cleanup task."""

    def test_deletes_old_logs(self, app):
        """Logs older than 30 days should be deleted."""
        with app.app_context():
            from tasks.cleanup import cleanup_old_pipeline_logs
            from models import PipelineRun, PipelineLog
            from extensions import db

            run = PipelineRun(
                run_type="crawl", status="completed", triggered_by="scheduled"
            )
            db.session.add(run)
            db.session.flush()

            old_time = datetime.now(timezone.utc) - timedelta(days=31)
            old_log = PipelineLog(
                run_id=run.id,
                stage="crawl",
                level="info",
                message="Old log entry",
            )
            old_log.created_at = old_time
            db.session.add(old_log)

            recent_log = PipelineLog(
                run_id=run.id,
                stage="crawl",
                level="info",
                message="Recent log entry",
            )
            db.session.add(recent_log)
            db.session.commit()

            result = cleanup_old_pipeline_logs()

            assert result == {"deleted": 1}
            remaining = PipelineLog.query.all()
            assert len(remaining) == 1
            assert remaining[0].message == "Recent log entry"

    def test_no_logs_deleted_when_all_recent(self, app):
        """When all logs are recent, nothing should be deleted."""
        with app.app_context():
            from tasks.cleanup import cleanup_old_pipeline_logs
            from models import PipelineRun, PipelineLog
            from extensions import db

            run = PipelineRun(
                run_type="crawl", status="completed", triggered_by="scheduled"
            )
            db.session.add(run)
            db.session.flush()

            log = PipelineLog(
                run_id=run.id,
                stage="crawl",
                level="info",
                message="Fresh log",
            )
            db.session.add(log)
            db.session.commit()

            result = cleanup_old_pipeline_logs()

            assert result == {"deleted": 0}
            assert PipelineLog.query.count() == 1

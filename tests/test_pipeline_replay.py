"""Tests for pipeline replay service and API."""

from unittest.mock import patch

import pytest

from extensions import db


class TestPipelineReplayService:
    """Tests for services/pipeline_replay.py."""

    def test_get_article_pipeline_history_returns_logs(self, app, create_article, create_pipeline_run):
        """get_article_pipeline_history returns pipeline log entries."""
        with app.app_context():
            from extensions import db
            from models import PipelineLog

            article = create_article(pipeline_status="done")
            run = create_pipeline_run(run_type="manual")

            log1 = PipelineLog(
                run_id=run.id,
                article_id=article.id,
                stage="select",
                level="info",
                message="Select stage started",
                status="completed",
            )
            log2 = PipelineLog(
                run_id=run.id,
                article_id=article.id,
                stage="select",
                level="info",
                message="Select stage completed",
                status="completed",
            )
            db.session.add_all([log1, log2])
            db.session.commit()

            from services.pipeline_replay import get_article_pipeline_history

            history = get_article_pipeline_history(article.id)

            assert len(history) == 2
            assert history[0]["stage"] == "select"
            assert history[0]["message"] == "Select stage completed"

    def test_get_article_pipeline_history_empty_for_new_article(self, app, create_article):
        """get_article_pipeline_history returns empty list for article with no logs."""
        with app.app_context():
            article = create_article(pipeline_status="pending")

            from services.pipeline_replay import get_article_pipeline_history

            history = get_article_pipeline_history(article.id)

            assert history == []

    def test_replay_select_clears_correct_fields(self, app, create_article, mock_celery_tasks):
        """Replay select clears selector result, research brief, draft, final, timestamps."""
        with app.app_context():
            from extensions import db
            from datetime import datetime, timezone

            article = create_article(
                pipeline_status="done",
                selector_result={"score": 0.9},
                research_brief="research content",
                draft_article="draft content",
                final_article="final content",
            )
            article.selected_at = datetime.now(timezone.utc)
            article.published_at = datetime.now(timezone.utc)
            db.session.commit()

            from services.pipeline_replay import replay_article_stage

            with patch("services.pipeline_replay._dispatch_stage_task") as mock_dispatch:
                mock_dispatch.return_value = "mock-task-id"
                result = replay_article_stage(
                    article_id=article.id,
                    stage="select",
                    reason="test_replay",
                    changed_by="test",
                )

            assert result["fields_cleared"] == [
                "selector_result",
                "research_brief",
                "draft_article",
                "final_article",
                "selected_at",
                "published_at",
            ]
            assert article.pipeline_status == "pending"

    def test_replay_research_preserves_selector_result(self, app, create_article, mock_celery_tasks):
        """Replay research preserves selector result, clears research brief, draft, final."""
        with app.app_context():
            from extensions import db

            article = create_article(
                pipeline_status="done",
                selector_result={"score": 0.9},
                research_brief="research content",
                draft_article="draft content",
                final_article="final content",
            )
            db.session.commit()

            from services.pipeline_replay import replay_article_stage

            with patch("services.pipeline_replay._dispatch_stage_task") as mock_dispatch:
                mock_dispatch.return_value = "mock-task-id"
                result = replay_article_stage(
                    article_id=article.id,
                    stage="research",
                    reason="test_replay",
                    changed_by="test",
                )

            assert "selector_result" not in result["fields_cleared"]
            assert "research_brief" in result["fields_cleared"]
            assert "draft_article" in result["fields_cleared"]
            assert "final_article" in result["fields_cleared"]
            assert article.pipeline_status == "selected"

    def test_replay_write_preserves_selector_and_research(self, app, create_article, mock_celery_tasks):
        """Replay write preserves selector/research, clears draft/final."""
        with app.app_context():
            from extensions import db

            article = create_article(
                pipeline_status="done",
                selector_result={"score": 0.9},
                research_brief="research content",
                draft_article="draft content",
                final_article="final content",
            )
            db.session.commit()

            from services.pipeline_replay import replay_article_stage

            with patch("services.pipeline_replay._dispatch_stage_task") as mock_dispatch:
                mock_dispatch.return_value = "mock-task-id"
                result = replay_article_stage(
                    article_id=article.id,
                    stage="write",
                    reason="test_replay",
                    changed_by="test",
                )

            assert "selector_result" not in result["fields_cleared"]
            assert "research_brief" not in result["fields_cleared"]
            assert "draft_article" in result["fields_cleared"]
            assert "final_article" in result["fields_cleared"]
            assert article.pipeline_status == "written"

    def test_replay_edit_clears_final_only(self, app, create_article, mock_celery_tasks):
        """Replay edit clears final article only."""
        with app.app_context():
            from extensions import db

            article = create_article(
                pipeline_status="done",
                selector_result={"score": 0.9},
                research_brief="research content",
                draft_article="draft content",
                final_article="final content",
            )
            db.session.commit()

            from services.pipeline_replay import replay_article_stage

            with patch("services.pipeline_replay._dispatch_stage_task") as mock_dispatch:
                mock_dispatch.return_value = "mock-task-id"
                result = replay_article_stage(
                    article_id=article.id,
                    stage="edit",
                    reason="test_replay",
                    changed_by="test",
                )

            assert "selector_result" not in result["fields_cleared"]
            assert "research_brief" not in result["fields_cleared"]
            assert "draft_article" not in result["fields_cleared"]
            assert result["fields_cleared"] == ["final_article"]
            assert article.pipeline_status == "written"

    def test_replay_invalid_stage_raises_error(self, app, create_article):
        """replay_article_stage raises ValueError for invalid stage."""
        with app.app_context():
            article = create_article(pipeline_status="done")

            from services.pipeline_replay import replay_article_stage

            with pytest.raises(ValueError, match="Invalid stage"):
                replay_article_stage(
                    article_id=article.id,
                    stage="invalid_stage",
                    reason="test",
                    changed_by="test",
                )

    def test_replay_nonexistent_article_raises_error(self, app):
        """replay_article_stage raises ValueError for nonexistent article."""
        with app.app_context():
            from services.pipeline_replay import replay_article_stage

            with pytest.raises(ValueError, match="not found"):
                replay_article_stage(
                    article_id=99999,
                    stage="select",
                    reason="test",
                    changed_by="test",
                )

    def test_replay_creates_version_snapshot(self, app, create_article, mock_celery_tasks):
        """replay_article_stage creates version snapshot before clearing fields."""
        with app.app_context():
            from extensions import db
            from models import ArticleVersion

            article = create_article(
                pipeline_status="done",
                final_article="final content to version",
            )
            db.session.commit()

            from services.pipeline_replay import replay_article_stage

            with patch("services.pipeline_replay._dispatch_stage_task") as mock_dispatch:
                mock_dispatch.return_value = "mock-task-id"
                replay_article_stage(
                    article_id=article.id,
                    stage="select",
                    reason="test_replay",
                    changed_by="test",
                )

            versions = ArticleVersion.query.filter_by(article_id=article.id).order_by(ArticleVersion.version_number.desc()).all()
            assert len(versions) >= 1
            latest_version = versions[0]
            assert latest_version.final_article == "final content to version"
            assert "test_replay" in latest_version.change_reason

    def test_replay_dispatches_correct_task(self, app, create_article, mock_celery_tasks):
        """replay_article_stage dispatches the correct Celery task for the stage."""
        with app.app_context():
            article = create_article(pipeline_status="done")
            db.session.commit()

            from services.pipeline_replay import replay_article_stage

            with patch("services.pipeline_replay._dispatch_stage_task") as mock_dispatch:
                mock_dispatch.return_value = "mock-task-id"
                result = replay_article_stage(
                    article_id=article.id,
                    stage="write",
                    reason="test",
                    changed_by="test",
                )

                mock_dispatch.assert_called_once_with(article.id, "write", None, None)
                assert result["task_id"] == "mock-task-id"

    def test_restore_article_version(self, app, create_article):
        """restore_article_version restores final_article from version."""
        with app.app_context():
            from extensions import db
            from models import ArticleVersion

            article = create_article(
                pipeline_status="done",
                final_article="current final content",
            )
            db.session.commit()

            version = ArticleVersion(
                article_id=article.id,
                version_number=1,
                final_article="restored final content",
                original_ai_article="restored ai content",
                change_reason="initial",
            )
            db.session.add(version)
            db.session.commit()

            from services.pipeline_replay import restore_article_version

            result = restore_article_version(
                article_id=article.id,
                version_id=version.id,
                changed_by="test",
            )

            assert result["restored_version_number"] == 1
            assert article.final_article == "restored final content"
            assert article.original_ai_article == "restored ai content"
            assert article.pipeline_status == "review"

    def test_restore_article_version_creates_backup_version(self, app, create_article):
        """restore_article_version creates backup version before restoring."""
        with app.app_context():
            from extensions import db
            from models import ArticleVersion

            article = create_article(
                pipeline_status="done",
                final_article="current content",
            )
            db.session.commit()

            version = ArticleVersion(
                article_id=article.id,
                version_number=1,
                final_article="old version content",
                change_reason="initial",
            )
            db.session.add(version)
            db.session.commit()

            initial_version_count = ArticleVersion.query.filter_by(article_id=article.id).count()

            from services.pipeline_replay import restore_article_version

            result = restore_article_version(
                article_id=article.id,
                version_id=version.id,
                changed_by="test",
            )

            new_version_count = ArticleVersion.query.filter_by(article_id=article.id).count()
            assert new_version_count == initial_version_count + 1

    def test_restore_nonexistent_article_raises_error(self, app):
        """restore_article_version raises ValueError for nonexistent article."""
        with app.app_context():
            from services.pipeline_replay import restore_article_version

            with pytest.raises(ValueError, match="not found"):
                restore_article_version(
                    article_id=99999,
                    version_id=1,
                    changed_by="test",
                )

    def test_restore_nonexistent_version_raises_error(self, app, create_article):
        """restore_article_version raises ValueError for nonexistent version."""
        with app.app_context():
            article = create_article(pipeline_status="done")

            from services.pipeline_replay import restore_article_version

            with pytest.raises(ValueError, match="not found"):
                restore_article_version(
                    article_id=article.id,
                    version_id=99999,
                    changed_by="test",
                )

    def test_restore_wrong_article_version_raises_error(self, app, create_article, create_source):
        """restore_article_version raises ValueError when version belongs to different article."""
        with app.app_context():
            from extensions import db
            from models import ArticleVersion

            article1 = create_article(pipeline_status="done")
            article2 = create_article(source=create_source(source_key="test_source_2"), pipeline_status="done")
            db.session.commit()

            version = ArticleVersion(
                article_id=article2.id,
                version_number=1,
                final_article="article2 content",
                change_reason="initial",
            )
            db.session.add(version)
            db.session.commit()

            from services.pipeline_replay import restore_article_version

            with pytest.raises(ValueError, match="does not belong"):
                restore_article_version(
                    article_id=article1.id,
                    version_id=version.id,
                    changed_by="test",
                )


class TestPipelineReplayAPI:
    """Tests for routes/admin/api/replay.py."""

    def test_get_history_endpoint(self, auth_client, app, create_article, create_pipeline_run):
        """GET /api/v1/articles/<id>/pipeline/history returns history."""
        with app.app_context():
            from extensions import db
            from models import PipelineLog

            article = create_article(pipeline_status="done")
            run = create_pipeline_run(run_type="manual")
            log = PipelineLog(
                run_id=run.id,
                article_id=article.id,
                stage="select",
                level="info",
                message="Select completed",
                status="completed",
            )
            db.session.add(log)
            db.session.commit()

            response = auth_client.get(f"/api/v1/articles/{article.id}/pipeline/history")

            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["article_id"] == article.id
            assert len(data["data"]["history"]) == 1
            assert data["data"]["history"][0]["stage"] == "select"

    def test_get_history_nonexistent_article_returns_404(self, auth_client):
        """GET /api/v1/articles/<id>/pipeline/history returns 404 for nonexistent article."""
        response = auth_client.get("/api/v1/articles/99999/pipeline/history")

        assert response.status_code == 404
        data = response.get_json()
        assert "not found" in data["error"]

    def test_replay_endpoint_dispatches_task(self, auth_client, app, create_article, mock_celery_tasks):
        """POST /api/v1/articles/<id>/pipeline/replay dispatches task and returns 202."""
        with app.app_context():
            from extensions import db

            article = create_article(pipeline_status="done")
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/replay",
                json={
                    "stage": "write",
                    "reason": "manual_replay_after_quality_failure",
                },
            )

            assert response.status_code == 202
            data = response.get_json()
            assert data["data"]["article_id"] == article.id
            assert data["data"]["stage"] == "write"
            assert "task_id" in data["data"]

    def test_replay_invalid_stage_returns_400(self, auth_client, app, create_article):
        """POST /api/v1/articles/<id>/pipeline/replay returns 400 for invalid stage."""
        with app.app_context():
            from extensions import db

            article = create_article(pipeline_status="done")
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/replay",
                json={
                    "stage": "invalid_stage",
                    "reason": "test",
                },
            )

            assert response.status_code == 400
            data = response.get_json()
            assert "Invalid stage" in data["error"]

    def test_replay_missing_stage_returns_400(self, auth_client, app, create_article):
        """POST /api/v1/articles/<id>/pipeline/replay returns 400 when stage is missing."""
        with app.app_context():
            from extensions import db

            article = create_article(pipeline_status="done")
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/replay",
                json={
                    "reason": "test",
                },
            )

            assert response.status_code == 400
            data = response.get_json()
            assert "stage is required" in data["error"]

    def test_replay_nonexistent_article_returns_404(self, auth_client):
        """POST /api/v1/articles/<id>/pipeline/replay returns 404 for nonexistent article."""
        response = auth_client.post(
            "/api/v1/articles/99999/pipeline/replay",
            json={
                "stage": "select",
                "reason": "test",
            },
        )

        assert response.status_code == 404

    def test_replay_provider_override_warning(self, auth_client, app, create_article, mock_celery_tasks):
        """POST /api/v1/articles/<id>/pipeline/replay with provider returns warning."""
        with app.app_context():
            from extensions import db

            article = create_article(pipeline_status="done")
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/replay",
                json={
                    "stage": "select",
                    "provider_id": "openai",
                    "model": "gpt-4",
                    "reason": "test",
                },
            )

            assert response.status_code == 202
            data = response.get_json()
            assert "warning" in data["meta"]

    def test_restore_version_endpoint(self, auth_client, app, create_article):
        """POST /api/v1/articles/<id>/pipeline/restore-version restores version."""
        with app.app_context():
            from extensions import db
            from models import ArticleVersion

            article = create_article(
                pipeline_status="done",
                final_article="current content",
            )
            db.session.commit()

            version = ArticleVersion(
                article_id=article.id,
                version_number=1,
                final_article="restored content",
                change_reason="initial",
            )
            db.session.add(version)
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/restore-version",
                json={
                    "version_id": version.id,
                },
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["article_id"] == article.id
            assert data["data"]["restored_version_number"] == 1

    def test_restore_version_missing_version_id_returns_400(self, auth_client, app, create_article):
        """POST /api/v1/articles/<id>/pipeline/restore-version returns 400 when version_id missing."""
        with app.app_context():
            from extensions import db

            article = create_article(pipeline_status="done")
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/restore-version",
                json={},
            )

            assert response.status_code == 400
            data = response.get_json()
            assert "version_id is required" in data["error"]

    def test_restore_version_invalid_version_id_returns_400(self, auth_client, app, create_article):
        """POST /api/v1/articles/<id>/pipeline/restore-version returns 400 when version_id not int."""
        with app.app_context():
            from extensions import db

            article = create_article(pipeline_status="done")
            db.session.commit()

            response = auth_client.post(
                f"/api/v1/articles/{article.id}/pipeline/restore-version",
                json={
                    "version_id": "not-an-int",
                },
            )

            assert response.status_code == 400
            data = response.get_json()
            assert "version_id must be an integer" in data["error"]

    def test_restore_version_nonexistent_article_returns_404(self, auth_client):
        """POST /api/v1/articles/<id>/pipeline/restore-version returns 404 for nonexistent article."""
        response = auth_client.post(
            "/api/v1/articles/99999/pipeline/restore-version",
            json={
                "version_id": 1,
            },
        )

        assert response.status_code == 404
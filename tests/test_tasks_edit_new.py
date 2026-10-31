"""Additional tests for tasks/edit.py - covering uncovered functions."""

import json
from unittest.mock import MagicMock, patch

import pytest


def _passing_quality_report():
    result = MagicMock()
    result.passed = True
    result.needsreview = False
    result.overall_score = 0.9
    result.citation_score = 1.0
    result.claim_score = 1.0
    result.findings = []
    return result


class TestExecuteEditorWork:
    """Tests for _execute_editor_work function."""

    def test_executes_full_editor_pipeline(self, app, create_article, monkeypatch):
        """Full happy path: builds prompt, calls LLM, assigns tags, finalizes."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _execute_editor_work

            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps({"headline": "Draft", "body": "Body"})
            article.research_brief = json.dumps({"summary": "brief"})
            article.topics = ["ai"]

            provider = MagicMock()
            result_model = MagicMock()
            result_model.model_dump_json.return_value = json.dumps({
                "headline": "Edited", "tldr": "TLDR", "body": "Edited body",
                "key_points": ["p1"], "citations": [], "tags": ["ai"],
                "original_attribution": {"source": "test"},
            })
            result_model.tags = ["ai"]
            provider.chat_structured.return_value = result_model

            with (
                patch("tasks.edit._get_cached_tag_names", return_value=["ai", "ml"]),
                patch("tasks.edit._gather_editor_context", return_value="ctx"),
                patch("services.prompts.sliding_window_truncate", side_effect=lambda text, **kw: text),
                patch("schemas.pipeline.get_role_config") as mock_rc,
                patch("services.editor.build_editor_prompt_with_context", return_value="prompt"),
                patch("services.editor.get_editor_system_prompt", return_value="system"),
                patch("services.article.create_article_version"),
                patch("services.article.sanitize_final_article", side_effect=lambda x: x),
                patch("tasks.edit._handle_validation_and_routing", return_value=None),
                patch("services.quality_report.build_quality_report", return_value=_passing_quality_report()),
                patch("services.quality_report.persist_quality_report"),
                patch("tasks.edit._post_finalize_article"),
                patch("tasks.pipeline._assign_tags"),
                patch("extensions.db") as mock_db,
            ):
                mock_rc.return_value = MagicMock(max_tags=3, temperature=0.7)
                mock_db.session.commit = MagicMock()

                result = _execute_editor_work(
                    article, provider, "gpt-4", 4000, article.id, run_id=None,
                )

            assert result["article_id"] == article.id
            assert result["status"] == "done"
            provider.chat_structured.assert_called_once()

    def test_returns_review_when_validation_fails(self, app, create_article, monkeypatch):
        """Returns review status when validation routes to review."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _execute_editor_work

            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps({"headline": "Draft"})
            article.topics = []

            provider = MagicMock()
            result_model = MagicMock()
            result_model.model_dump_json.return_value = "{}"
            result_model.tags = []
            provider.chat_structured.return_value = result_model

            with (
                patch("tasks.edit._get_cached_tag_names", return_value=[]),
                patch("tasks.edit._gather_editor_context", return_value=""),
                patch("services.prompts.sliding_window_truncate", side_effect=lambda text, **kw: text),
                patch("schemas.pipeline.get_role_config") as mock_rc,
                patch("services.editor.build_editor_prompt_with_context", return_value="prompt"),
                patch("services.editor.get_editor_system_prompt", return_value="system"),
                patch("services.article.create_article_version"),
                patch("services.article.sanitize_final_article", side_effect=lambda x: x),
                patch("tasks.edit._handle_validation_and_routing", return_value={"article_id": article.id, "status": "review"}),
                patch("tasks.pipeline._assign_tags"),
                patch("extensions.db") as mock_db,
            ):
                mock_rc.return_value = MagicMock(max_tags=3, temperature=0.7)
                mock_db.session.commit = MagicMock()

                result = _execute_editor_work(
                    article, provider, "gpt-4", 4000, article.id, run_id=42,
                )

            assert result["status"] == "review"

    @pytest.mark.parametrize("passed,needsreview", [(False, True), (True, True)])
    def test_routes_to_review_when_quality_report_requires_it(
        self, app, create_article, monkeypatch, passed, needsreview,
    ):
        """A failed or review-required report cannot finalize the article."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _execute_editor_work

            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps({"headline": "Draft"})
            article.topics = []

            provider = MagicMock()
            result_model = MagicMock()
            result_model.model_dump_json.return_value = json.dumps({
                "headline": "Edited", "body": "Body", "tags": [],
                "original_attribution": {"source": "test"},
                "citations": [], "key_points": [],
            })
            result_model.tags = []
            provider.chat_structured.return_value = result_model

            quality_result = MagicMock()
            quality_result.passed = passed
            quality_result.needsreview = needsreview
            quality_result.overall_score = 0.3
            quality_result.citation_score = 0.2
            quality_result.claim_score = 0.1
            quality_result.findings = [MagicMock(message="low quality")]

            with (
                patch("tasks.edit._get_cached_tag_names", return_value=[]),
                patch("tasks.edit._gather_editor_context", return_value=""),
                patch("services.prompts.sliding_window_truncate", side_effect=lambda text, **kw: text),
                patch("schemas.pipeline.get_role_config") as mock_rc,
                patch("services.editor.build_editor_prompt_with_context", return_value="prompt"),
                patch("services.editor.get_editor_system_prompt", return_value="system"),
                patch("services.article.create_article_version"),
                patch("services.article.sanitize_final_article", side_effect=lambda x: x),
                patch("tasks.edit._handle_validation_and_routing", return_value=None),
                patch("services.quality_report.build_quality_report", return_value=quality_result),
                patch("services.quality_report.persist_quality_report"),
                patch("tasks.pipeline._transition_article_status"),
                patch("tasks.pipeline._dispatch_next"),
                patch("tasks.pipeline._log_pipeline"),
                patch("tasks.pipeline._assign_tags"),
                patch("extensions.db") as mock_db,
            ):
                mock_rc.return_value = MagicMock(max_tags=3, temperature=0.7)
                mock_db.session.commit = MagicMock()

                result = _execute_editor_work(
                    article, provider, "gpt-4", 4000, article.id, run_id=99,
                )

            assert result["status"] == "review"

    def test_routes_to_review_when_quality_report_raises(self, app, create_article, monkeypatch):
        """A report failure cannot finalize an article without a quality result."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _execute_editor_work

            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps({"headline": "Draft"})
            article.topics = []

            provider = MagicMock()
            result_model = MagicMock()
            result_model.model_dump_json.return_value = json.dumps({
                "headline": "Edited", "body": "Body", "tags": [],
                "original_attribution": {"source": "test"},
                "citations": [], "key_points": [],
            })
            result_model.tags = []
            provider.chat_structured.return_value = result_model

            with (
                patch("tasks.edit._get_cached_tag_names", return_value=[]),
                patch("tasks.edit._gather_editor_context", return_value=""),
                patch("services.prompts.sliding_window_truncate", side_effect=lambda text, **kw: text),
                patch("schemas.pipeline.get_role_config") as mock_rc,
                patch("services.editor.build_editor_prompt_with_context", return_value="prompt"),
                patch("services.editor.get_editor_system_prompt", return_value="system"),
                patch("services.article.create_article_version"),
                patch("services.article.sanitize_final_article", side_effect=lambda x: x),
                patch("tasks.edit._handle_validation_and_routing", return_value=None),
                patch("services.quality_report.build_quality_report", side_effect=RuntimeError("boom")),
                patch("tasks.edit._post_finalize_article") as mock_finalize,
                patch("tasks.pipeline._dispatch_next"),
                patch("tasks.pipeline._assign_tags"),
                patch("extensions.db") as mock_db,
            ):
                mock_rc.return_value = MagicMock(max_tags=3, temperature=0.7)
                mock_db.session.commit = MagicMock()

                result = _execute_editor_work(
                    article, provider, "gpt-4", 4000, article.id, run_id=None,
                )

            assert result["status"] == "review"
            assert article.pipeline_status == "review"
            assert article.last_error.startswith("Quality report unavailable:")
            mock_finalize.assert_not_called()

    def test_shadow_quality_assessment_logs_on_success(self, app, create_article, monkeypatch):
        """Shadow quality assessment logs scores when it succeeds."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _execute_editor_work

            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps({"headline": "Draft"})
            article.topics = []

            provider = MagicMock()
            result_model = MagicMock()
            result_model.model_dump_json.return_value = json.dumps({
                "headline": "Edited", "body": "Good body text here", "tags": [],
                "original_attribution": {"source": "test"},
                "citations": [], "key_points": [],
            })
            result_model.tags = []
            provider.chat_structured.return_value = result_model

            quality_score = MagicMock()
            quality_score.overall = 0.8
            quality_score.groundedness = 0.9
            quality_score.coherence = 0.85
            quality_score.completeness = 0.7
            quality_score.safety = 0.95

            with (
                patch("tasks.edit._get_cached_tag_names", return_value=[]),
                patch("tasks.edit._gather_editor_context", return_value=""),
                patch("services.prompts.sliding_window_truncate", side_effect=lambda text, **kw: text),
                patch("schemas.pipeline.get_role_config") as mock_rc,
                patch("services.editor.build_editor_prompt_with_context", return_value="prompt"),
                patch("services.editor.get_editor_system_prompt", return_value="system"),
                patch("services.article.create_article_version"),
                patch("services.article.sanitize_final_article", side_effect=lambda x: x),
                patch("tasks.edit._handle_validation_and_routing", return_value=None),
                patch("services.quality.lightweight_quality_signals", return_value=quality_score),
                patch("services.quality_report.build_quality_report", return_value=_passing_quality_report()),
                patch("services.quality_report.persist_quality_report"),
                patch("tasks.edit._post_finalize_article"),
                patch("tasks.pipeline._assign_tags"),
                patch("extensions.db") as mock_db,
            ):
                mock_rc.return_value = MagicMock(max_tags=3, temperature=0.7)
                mock_db.session.commit = MagicMock()

                result = _execute_editor_work(
                    article, provider, "gpt-4", 4000, article.id, run_id=None,
                )

            assert result["status"] == "done"

    def test_shadow_quality_assessment_tolerates_failure(self, app, create_article, monkeypatch):
        """Shadow quality assessment failure is non-critical."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _execute_editor_work

            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps({"headline": "Draft"})
            article.topics = []

            provider = MagicMock()
            result_model = MagicMock()
            result_model.model_dump_json.return_value = json.dumps({
                "headline": "Edited", "body": "Body", "tags": [],
                "original_attribution": {"source": "test"},
                "citations": [], "key_points": [],
            })
            result_model.tags = []
            provider.chat_structured.return_value = result_model

            with (
                patch("tasks.edit._get_cached_tag_names", return_value=[]),
                patch("tasks.edit._gather_editor_context", return_value=""),
                patch("services.prompts.sliding_window_truncate", side_effect=lambda text, **kw: text),
                patch("schemas.pipeline.get_role_config") as mock_rc,
                patch("services.editor.build_editor_prompt_with_context", return_value="prompt"),
                patch("services.editor.get_editor_system_prompt", return_value="system"),
                patch("services.article.create_article_version"),
                patch("services.article.sanitize_final_article", side_effect=lambda x: x),
                patch("tasks.edit._handle_validation_and_routing", return_value=None),
                patch("services.quality.lightweight_quality_signals", side_effect=RuntimeError("quality boom")),
                patch("services.quality_report.build_quality_report", return_value=_passing_quality_report()),
                patch("services.quality_report.persist_quality_report"),
                patch("tasks.edit._post_finalize_article"),
                patch("tasks.pipeline._assign_tags"),
                patch("extensions.db") as mock_db,
            ):
                mock_rc.return_value = MagicMock(max_tags=3, temperature=0.7)
                mock_db.session.commit = MagicMock()

                result = _execute_editor_work(
                    article, provider, "gpt-4", 4000, article.id, run_id=None,
                )

            assert result["status"] == "done"


class TestHandleValidationAndRoutingAdditional:
    """Additional tests for _handle_validation_and_routing."""

    def test_routes_to_review_when_should_route(self, app, create_article, monkeypatch):
        """Routes to review when _should_route_to_review returns True."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _handle_validation_and_routing

            article = create_article(pipeline_status="editing")
            article.final_article = '{"headline": "Test"}'

            with (
                patch("services.article_validation.validate_and_raise"),
                patch("tasks.pipeline._should_route_to_review", return_value=True),
                patch("tasks.pipeline._transition_article_status"),
                patch("tasks.pipeline._dispatch_next"),
                patch("tasks.pipeline._log_pipeline"),
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit = MagicMock()

                result = _handle_validation_and_routing(article, mock_db, run_id=42)

            assert result == {"article_id": article.id, "status": "review"}

    def test_returns_none_when_no_review_needed(self, app, create_article, monkeypatch):
        """Returns None when validation passes and no review routing needed."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _handle_validation_and_routing

            article = create_article(pipeline_status="editing")
            article.final_article = '{"headline": "Test"}'

            with (
                patch("services.article_validation.validate_and_raise"),
                patch("tasks.pipeline._should_route_to_review", return_value=False),
                patch("extensions.db") as mock_db,
            ):
                result = _handle_validation_and_routing(article, mock_db, run_id=None)

            assert result is None

    def test_no_run_id_skips_logging(self, app, create_article, monkeypatch):
        """When run_id is None, pipeline logging is skipped."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _handle_validation_and_routing
            from services.article_validation import ValidationError

            article = create_article(pipeline_status="editing")
            article.final_article = '{"headline": "Test"}'

            with (
                patch("services.article_validation.validate_and_raise", side_effect=ValidationError("bad")),
                patch("tasks.pipeline._transition_article_status"),
                patch("tasks.pipeline._dispatch_next") as mock_dispatch,
                patch("tasks.pipeline._log_pipeline") as mock_log,
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit = MagicMock()

                result = _handle_validation_and_routing(article, mock_db, run_id=None)

            assert result == {"article_id": article.id, "status": "review"}
            mock_log.assert_not_called()
            mock_dispatch.assert_called_once()

    def test_validation_error_rollback_on_db_failure(self, app, create_article, monkeypatch):
        """DB commit failure during validation error handling triggers rollback."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import _handle_validation_and_routing
            from services.article_validation import ValidationError
            from sqlalchemy.exc import SQLAlchemyError

            article = create_article(pipeline_status="editing")
            article.final_article = '{"headline": "Test"}'

            with (
                patch("services.article_validation.validate_and_raise", side_effect=ValidationError("bad")),
                patch("tasks.pipeline._transition_article_status"),
                patch("tasks.pipeline._dispatch_next"),
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit.side_effect = SQLAlchemyError("db fail")
                mock_db.session.rollback = MagicMock()

                with pytest.raises(SQLAlchemyError):
                    _handle_validation_and_routing(article, mock_db, run_id=None)


class TestGatherEditorContextAdditional:
    """Additional tests for _gather_editor_context."""

    def test_runs_subagent_with_tools_when_configured(self, app, create_article, monkeypatch):
        """When stage_config.tools is set, uses run_subagent_with_tools."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        from schemas.pipeline import load_pipeline_config
        pipeline_config = load_pipeline_config()
        pipeline_config.memory.memory_v2_enabled = False
        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", lambda: pipeline_config)
        with app.app_context():
            from tasks.edit import _gather_editor_context

            article = create_article(pipeline_status="editing")
            article.topics = ["ai"]

            mock_stage_config = MagicMock()
            mock_stage_config.tools = ["tool1"]

            mock_ctx_result = MagicMock()
            mock_ctx_result.used_fallback = False
            mock_ctx_result.synthesis = "context from tools"

            with (
                patch("services.context_service.get_topic_notes_for_topics", return_value={"ai": ["note1"]}),
                patch("services.context_service.get_related_articles_for_edit", return_value=[{"title": "Related"}]),
                patch("services.trend_memory.get_memory_for_topics", return_value=[]),
                patch("services.trend_memory._format_memory_for_prompt", return_value="trend mem"),
                patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
                patch("services.subagent.initialize_tool_registry", return_value=["tools"]),
                patch("services.subagent.run_subagent_with_tools", return_value=mock_ctx_result),
            ):
                result = _gather_editor_context(article, ["existing_tag"])

            assert result == "context from tools"

    def test_runs_plain_subagent_when_no_tools(self, app, create_article, monkeypatch):
        """When stage_config.tools is empty, uses plain run_subagent."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        from schemas.pipeline import load_pipeline_config
        pipeline_config = load_pipeline_config()
        pipeline_config.memory.memory_v2_enabled = False
        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", lambda: pipeline_config)
        with app.app_context():
            from tasks.edit import _gather_editor_context

            article = create_article(pipeline_status="editing")
            article.topics = ["ai"]

            mock_stage_config = MagicMock()
            mock_stage_config.tools = []

            mock_ctx_result = MagicMock()
            mock_ctx_result.used_fallback = False
            mock_ctx_result.synthesis = "context plain"

            with (
                patch("services.context_service.get_topic_notes_for_topics", return_value={"ai": ["note1"]}),
                patch("services.context_service.get_related_articles_for_edit", return_value=[]),
                patch("services.trend_memory.get_memory_for_topics", return_value=[]),
                patch("services.trend_memory._format_memory_for_prompt", return_value="trend mem"),
                patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
                patch("services.subagent.run_subagent", return_value=mock_ctx_result),
            ):
                result = _gather_editor_context(article, [])

            assert result == "context plain"

    def test_returns_empty_when_all_context_empty(self, app, create_article, monkeypatch):
        """Returns empty string when topic_notes, related_articles, and trend_memory are all empty."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        from schemas.pipeline import load_pipeline_config
        pipeline_config = load_pipeline_config()
        pipeline_config.memory.memory_v2_enabled = False
        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", lambda: pipeline_config)
        with app.app_context():
            from tasks.edit import _gather_editor_context

            article = create_article(pipeline_status="editing")
            article.topics = ["ai"]

            with (
                patch("services.context_service.get_topic_notes_for_topics", return_value={}),
                patch("services.context_service.get_related_articles_for_edit", return_value=[]),
                patch("services.trend_memory.get_memory_for_topics", return_value=[]),
                patch("services.trend_memory._format_memory_for_prompt", return_value=""),
            ):
                result = _gather_editor_context(article, [])

            assert result == ""

    def test_warns_on_fallback(self, app, create_article, monkeypatch):
        """Logs warning when subagent used_fallback is True."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        from schemas.pipeline import load_pipeline_config
        pipeline_config = load_pipeline_config()
        pipeline_config.memory.memory_v2_enabled = False
        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", lambda: pipeline_config)
        with app.app_context():
            from tasks.edit import _gather_editor_context

            article = create_article(pipeline_status="editing")
            article.topics = ["ai"]

            mock_stage_config = MagicMock()
            mock_stage_config.tools = []

            mock_ctx_result = MagicMock()
            mock_ctx_result.used_fallback = True
            mock_ctx_result.synthesis = "fallback ctx"

            with (
                patch("services.context_service.get_topic_notes_for_topics", return_value={"ai": ["n"]}),
                patch("services.context_service.get_related_articles_for_edit", return_value=[]),
                patch("services.trend_memory.get_memory_for_topics", return_value=[]),
                patch("services.trend_memory._format_memory_for_prompt", return_value="mem"),
                patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
                patch("services.subagent.run_subagent", return_value=mock_ctx_result),
            ):
                result = _gather_editor_context(article, [])

            assert result == "fallback ctx"


class TestEditArticleTask:
    """Tests for the edit_article Celery task entry point."""

    def test_edit_article_calls_run_stage(self, app, create_article, monkeypatch):
        """edit_article delegates to run_stage with correct args."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import edit_article

            article = create_article(pipeline_status="editing")

            with patch("tasks.pipeline.run_stage", return_value={"article_id": article.id, "status": "done"}) as mock_run:
                result = edit_article.run(article.id, run_id=42)

            call_args = mock_run.call_args
            assert call_args[0][0] == "editor"
            assert call_args[0][1] == article.id
            assert call_args[1]["run_id"] == 42
            assert call_args[1]["skip_next"] == "finalize"
            assert result == {"article_id": article.id, "status": "done"}

    def test_edit_article_work_receives_article_and_run_ids(
        self, app, create_article, monkeypatch
    ):
        """The run_stage work callback supplies the arguments the editor helper needs."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import edit_article

            article = create_article(pipeline_status="editing")
            provider = MagicMock()

            def run_work_inline(_stage, _article_id, work, **_kwargs):
                return work(article, provider, "test-model", 8192)

            with (
                patch("tasks.pipeline.run_stage", side_effect=run_work_inline),
                patch("tasks.edit._execute_editor_work", return_value={"article_id": article.id}) as execute,
            ):
                result = edit_article.run(article.id, run_id=42)

            execute.assert_called_once_with(
                article, provider, "test-model", 8192, article.id, run_id=42
            )
            assert result == {"article_id": article.id}

    def test_edit_article_with_none_run_id(self, app, create_article, monkeypatch):
        """edit_article works with default run_id=None."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.edit import edit_article

            article = create_article(pipeline_status="editing")

            with patch("tasks.pipeline.run_stage", return_value={"article_id": article.id, "status": "done"}) as mock_run:
                result = edit_article.run(article.id)

            mock_run.assert_called_once()
            assert result["status"] == "done"

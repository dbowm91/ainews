"""Tests for tasks/research.py - Research pipeline stage task."""

from unittest.mock import MagicMock, patch

import pytest


def _make_brief(claims=None, impact_score=50):
    """Helper to build a ResearchBrief with mock claims that have .claim attr.

    Note: _is_degenerate_research accesses claim.claim (KeyClaim.claim).
    We use MagicMock to match the actual attribute the code reads.
    """
    if claims is None:
        claims = []
    mock_claims = []
    for c in claims:
        m = MagicMock()
        m.claim = c
        mock_claims.append(m)
    brief = MagicMock()
    brief.key_claims = mock_claims
    brief.impact_score = impact_score
    return brief


class TestIsDegenerateResearch:
    """Tests for _is_degenerate_research function."""

    def test_returns_true_when_no_key_claims(self):
        """Degenerate when key_claims is empty."""
        from tasks.research import _is_degenerate_research

        brief = _make_brief(claims=[], impact_score=50)
        assert _is_degenerate_research(brief) is True

    def test_returns_true_when_all_claims_empty_content(self):
        """Degenerate when all claims have empty content."""
        from tasks.research import _is_degenerate_research

        brief = _make_brief(claims=["", "  "], impact_score=50)
        assert _is_degenerate_research(brief) is True

    def test_returns_true_when_impact_score_low(self):
        """Degenerate when impact_score < 10 even with valid claims."""
        from tasks.research import _is_degenerate_research

        brief = _make_brief(claims=["Valid claim"], impact_score=5)
        assert _is_degenerate_research(brief) is True

    def test_returns_false_when_valid_claims_and_good_score(self):
        """Not degenerate with valid claims and impact >= 10."""
        from tasks.research import _is_degenerate_research

        brief = _make_brief(claims=["Important finding"], impact_score=50)
        assert _is_degenerate_research(brief) is False

    def test_returns_true_when_claims_exist_but_all_whitespace(self):
        """Degenerate when claims are only whitespace."""
        from tasks.research import _is_degenerate_research

        brief = _make_brief(claims=["   ", "\n\t"], impact_score=80)
        assert _is_degenerate_research(brief) is True

    def test_mixed_valid_and_empty_claims_passes_claim_check(self):
        """At least one non-empty claim passes the claim validity check."""
        from tasks.research import _is_degenerate_research

        brief = _make_brief(claims=["", "Real claim"], impact_score=50)
        assert _is_degenerate_research(brief) is False


class TestFormatWebResults:
    """Tests for _format_web_results function."""

    def test_returns_no_web_results_when_empty(self):
        """Returns placeholder for empty list."""
        from tasks.research import _format_web_results
        assert _format_web_results([]) == "(no web results)"

    def test_returns_no_web_results_when_none(self):
        """Returns placeholder for None."""
        from tasks.research import _format_web_results
        assert _format_web_results(None) == "(no web results)"

    def test_formats_single_result(self):
        """Formats a single web result."""
        from tasks.research import _format_web_results

        results = [{"title": "Title", "url": "https://example.com", "snippet": "Snippet text"}]
        output = _format_web_results(results)

        assert "Source: Title" in output
        assert "URL: https://example.com" in output
        assert "Snippet: Snippet text" in output

    def test_formats_multiple_results(self):
        """Formats multiple web results separated by blank lines."""
        from tasks.research import _format_web_results

        results = [
            {"title": "First", "url": "https://a.com", "snippet": "s1"},
            {"title": "Second", "url": "https://b.com", "snippet": "s2"},
        ]
        output = _format_web_results(results)

        assert "Source: First" in output
        assert "Source: Second" in output

    def test_truncates_snippet_to_300_chars(self):
        """Snippet is truncated to 300 characters."""
        from tasks.research import _format_web_results

        results = [{"title": "T", "url": "u", "snippet": "X" * 500}]
        output = _format_web_results(results)

        assert "X" * 300 in output
        assert "X" * 301 not in output

    def test_handles_missing_fields(self):
        """Defaults for missing title, url, snippet."""
        from tasks.research import _format_web_results

        results = [{}]
        output = _format_web_results(results)

        assert "Source: Unknown" in output
        assert "URL: " in output
        assert "Snippet: " in output


class TestPerformWebSearchAndSynthesis:
    """Tests for _perform_web_search_and_synthesis function."""

    def test_returns_empty_when_web_search_disabled(self):
        """Returns empty results when rc.web_search is False."""
        from tasks.research import _perform_web_search_and_synthesis

        article = MagicMock()
        rc = MagicMock()
        rc.web_search = False

        results, synthesis = _perform_web_search_and_synthesis(article, rc)

        assert results == []
        assert synthesis == ""

    def test_uses_configured_search_provider(self):
        """Uses specified search provider when rc.web_search_provider is set."""
        from tasks.research import _perform_web_search_and_synthesis

        article = MagicMock()
        article.original_title = "Test Title"
        article.topics = ["ai"]
        article.id = 1
        article.extracted_text = "text"

        rc = MagicMock()
        rc.web_search = True
        rc.web_search_provider = "duckduckgo"
        rc.web_search_max_results = 3

        mock_search_result = MagicMock()
        mock_search_result.title = "Result"
        mock_search_result.url = "https://example.com"
        mock_search_result.snippet = "Snippet"

        mock_provider = MagicMock()
        mock_provider.search.return_value = [mock_search_result]

        mock_stage_config = MagicMock()
        mock_stage_config.tools = []

        mock_synthesis = MagicMock()
        mock_synthesis.used_fallback = False
        mock_synthesis.synthesis = "synthesized"

        with (
            patch("services.search.get_search_provider", return_value=mock_provider),
            patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
            patch("services.subagent.run_subagent", return_value=mock_synthesis),
        ):
            results, synthesis = _perform_web_search_and_synthesis(article, rc)

        assert len(results) == 1
        assert results[0]["title"] == "Result"
        assert synthesis == "synthesized"
        mock_provider.search.assert_called_once_with(
            "Test Title ai", max_results=3,
        )

    def test_uses_default_search_when_no_provider(self):
        """Falls back to search_web when no provider configured."""
        from tasks.research import _perform_web_search_and_synthesis

        article = MagicMock()
        article.original_title = "Title"
        article.topics = []
        article.id = 1
        article.extracted_text = ""

        rc = MagicMock()
        rc.web_search = True
        rc.web_search_provider = None
        rc.web_search_max_results = 5

        mock_search_result = MagicMock()
        mock_search_result.title = "R"
        mock_search_result.url = "https://x.com"
        mock_search_result.snippet = "s"

        mock_stage_config = MagicMock()
        mock_stage_config.tools = []

        mock_synthesis = MagicMock()
        mock_synthesis.used_fallback = False
        mock_synthesis.synthesis = "syn"

        with (
            patch("services.search.search_web", return_value=[mock_search_result]),
            patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
            patch("services.subagent.run_subagent", return_value=mock_synthesis),
        ):
            results, synthesis = _perform_web_search_and_synthesis(article, rc)

        assert len(results) == 1

    def test_returns_empty_when_no_search_results(self):
        """Returns empty when search returns no results."""
        from tasks.research import _perform_web_search_and_synthesis

        article = MagicMock()
        article.original_title = "Title"
        article.topics = []

        rc = MagicMock()
        rc.web_search = True
        rc.web_search_provider = "duckduckgo"
        rc.web_search_max_results = 5

        mock_provider = MagicMock()
        mock_provider.search.return_value = []

        with patch("services.search.get_search_provider", return_value=mock_provider):
            results, synthesis = _perform_web_search_and_synthesis(article, rc)

        assert results == []
        assert synthesis == ""

    def test_uses_tools_when_configured(self):
        """Uses run_subagent_with_tools when stage_config.tools is set."""
        from tasks.research import _perform_web_search_and_synthesis

        article = MagicMock()
        article.original_title = "Title"
        article.topics = ["ai"]
        article.id = 1
        article.extracted_text = "text"

        rc = MagicMock()
        rc.web_search = True
        rc.web_search_provider = "duckduckgo"
        rc.web_search_max_results = 5

        mock_search_result = MagicMock()
        mock_search_result.title = "R"
        mock_search_result.url = "https://x.com"
        mock_search_result.snippet = "s"

        mock_provider = MagicMock()
        mock_provider.search.return_value = [mock_search_result]

        mock_stage_config = MagicMock()
        mock_stage_config.tools = ["tool1"]

        mock_synthesis = MagicMock()
        mock_synthesis.used_fallback = False
        mock_synthesis.synthesis = "tools synthesis"

        with (
            patch("services.search.get_search_provider", return_value=mock_provider),
            patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
            patch("services.subagent.initialize_tool_registry", return_value=["tools"]),
            patch("services.subagent.run_subagent_with_tools", return_value=mock_synthesis),
        ):
            results, synthesis = _perform_web_search_and_synthesis(article, rc)

        assert synthesis == "tools synthesis"

    def test_warns_on_fallback(self):
        """Logs warning when subagent used_fallback."""
        from tasks.research import _perform_web_search_and_synthesis

        article = MagicMock()
        article.original_title = "Title"
        article.topics = ["ai"]
        article.id = 1
        article.extracted_text = "text"

        rc = MagicMock()
        rc.web_search = True
        rc.web_search_provider = "duckduckgo"
        rc.web_search_max_results = 5

        mock_search_result = MagicMock()
        mock_search_result.title = "R"
        mock_search_result.url = "https://x.com"
        mock_search_result.snippet = "s"

        mock_provider = MagicMock()
        mock_provider.search.return_value = [mock_search_result]

        mock_stage_config = MagicMock()
        mock_stage_config.tools = []

        mock_synthesis = MagicMock()
        mock_synthesis.used_fallback = True
        mock_synthesis.synthesis = "fallback"

        with (
            patch("services.search.get_search_provider", return_value=mock_provider),
            patch("schemas.pipeline.resolve_subagent_config", return_value=mock_stage_config),
            patch("services.subagent.run_subagent", return_value=mock_synthesis),
        ):
            results, synthesis = _perform_web_search_and_synthesis(article, rc)

        assert synthesis == "fallback"


class TestGetRelatedAndContext:
    """Tests for _get_related_and_context function."""

    def test_returns_related_and_empty_context_when_no_topics(self):
        """Returns related articles but empty context when no topics."""
        from tasks.research import _get_related_and_context

        article = MagicMock()
        article.topics = []
        article.id = 1

        rc = MagicMock()
        rc.db_related_max = 5

        mock_related = [{"title": "Related"}]

        with patch("services.related.find_related_articles_dicts", return_value=mock_related):
            related, topic_notes, trend_memory = _get_related_and_context(article, rc)

        assert related == mock_related
        assert topic_notes == ""
        assert trend_memory == ""

    def test_populates_context_when_topics_exist(self, monkeypatch):
        """Fetches topic_notes and trend_memory when topics exist."""
        from tasks.research import _get_related_and_context
        from schemas.pipeline import load_pipeline_config

        pipeline_config = load_pipeline_config()
        pipeline_config.memory.memory_v2_enabled = False
        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", lambda: pipeline_config)

        article = MagicMock()
        article.topics = ["ai", "ml"]
        article.id = 1

        rc = MagicMock()
        rc.db_related_max = 3

        mock_topic_notes = {"ai": ["note1"], "ml": ["note2"]}

        mock_memory_context = MagicMock()
        mock_memory_context.rendered = "trend memory text"

        with (
            patch("services.related.find_related_articles_dicts", return_value=[]),
            patch("services.context_service.get_topic_notes_for_topics", return_value=mock_topic_notes),
            patch("services.trend_memory.get_memory_for_topics", return_value=[]),
            patch("services.trend_memory._format_memory_for_prompt", return_value="trend memory text"),
            patch("services.memory.preflight.ensure_memory_schema"),
            patch("services.memory.memory_context", return_value=mock_memory_context),
        ):
            related, topic_notes, trend_memory = _get_related_and_context(article, rc)

        assert topic_notes == "- note1\n- note2"
        assert trend_memory == "trend memory text"

    def test_handles_empty_topic_notes(self, monkeypatch):
        """Handles empty topic_notes dict gracefully."""
        from tasks.research import _get_related_and_context
        from schemas.pipeline import load_pipeline_config

        pipeline_config = load_pipeline_config()
        pipeline_config.memory.memory_v2_enabled = False
        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", lambda: pipeline_config)

        article = MagicMock()
        article.topics = ["ai"]
        article.id = 1

        rc = MagicMock()
        rc.db_related_max = 5

        mock_memory_context = MagicMock()
        mock_memory_context.rendered = ""

        with (
            patch("services.related.find_related_articles_dicts", return_value=[]),
            patch("services.context_service.get_topic_notes_for_topics", return_value={}),
            patch("services.trend_memory.get_memory_for_topics", return_value=[]),
            patch("services.trend_memory._format_memory_for_prompt", return_value=""),
            patch("services.memory.preflight.ensure_memory_schema"),
            patch("services.memory.memory_context", return_value=mock_memory_context),
        ):
            related, topic_notes, trend_memory = _get_related_and_context(article, rc)

        assert topic_notes == ""


class TestPerformQualityAssessment:
    """Tests for _perform_quality_assessment function."""

    def test_logs_quality_scores_on_success(self):
        """Logs quality scores when assessment succeeds."""
        from tasks.research import _perform_quality_assessment

        article = MagicMock()
        article.id = 1

        brief = MagicMock()
        brief.key_claims = [
            MagicMock(content="Claim 1"),
            MagicMock(content="Claim 2"),
        ]

        quality_score = MagicMock()
        quality_score.overall = 0.8
        quality_score.groundedness = 0.9
        quality_score.coherence = 0.85
        quality_score.completeness = 0.7
        quality_score.safety = 0.95

        with patch("services.quality.lightweight_quality_signals", return_value=quality_score):
            _perform_quality_assessment(article, brief)

    def test_tolerates_quality_assessment_failure(self):
        """Quality assessment exceptions are caught and logged."""
        from tasks.research import _perform_quality_assessment

        article = MagicMock()
        article.id = 1

        brief = MagicMock()
        brief.key_claims = [MagicMock(content="Claim")]

        with patch("services.quality.lightweight_quality_signals", side_effect=RuntimeError("boom")):
            _perform_quality_assessment(article, brief)

    def test_skips_when_no_claims_content(self):
        """Skips assessment when brief has no non-empty claim content."""
        from tasks.research import _perform_quality_assessment

        article = MagicMock()
        article.id = 1

        brief = MagicMock()
        brief.key_claims = [MagicMock(content=""), MagicMock(content="")]

        with patch("services.quality.lightweight_quality_signals") as mock_qs:
            _perform_quality_assessment(article, brief)

        mock_qs.assert_not_called()

    def test_skips_when_key_claims_none(self):
        """Skips assessment when key_claims is None."""
        from tasks.research import _perform_quality_assessment

        article = MagicMock()
        article.id = 1

        brief = MagicMock()
        brief.key_claims = None

        with patch("services.quality.lightweight_quality_signals") as mock_qs:
            _perform_quality_assessment(article, brief)

        mock_qs.assert_not_called()


class TestHandleQualityGateAndTransition:
    """Tests for _handle_quality_gate_and_transition function."""

    def test_routes_to_review_on_degenerate_brief(self, app, create_article, monkeypatch):
        """Routes to REVIEW when research brief is degenerate."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import _handle_quality_gate_and_transition

            article = create_article(pipeline_status="researching")
            brief = _make_brief(claims=[], impact_score=5)

            with (
                patch("tasks.pipeline._transition_article_status") as mock_trans,
                patch("tasks.pipeline._dispatch_next") as mock_dispatch,
                patch("tasks.pipeline._log_pipeline"),
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit = MagicMock()

                result = _handle_quality_gate_and_transition(
                    brief, article, run_id=42, article_id=article.id, db=mock_db,
                )

            assert result == {"article_id": article.id, "quality_gate": "review"}
            mock_trans.assert_called_once()
            mock_dispatch.assert_called_once()

    def test_transitions_to_writing_on_pass(self, app, create_article, monkeypatch):
        """Transitions to WRITING when quality gate passes."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import _handle_quality_gate_and_transition

            article = create_article(pipeline_status="researching")
            brief = _make_brief(claims=["Valid claim"], impact_score=50)

            with (
                patch("tasks.pipeline._transition_article_status") as mock_trans,
                patch("tasks.pipeline._dispatch_next") as mock_dispatch,
                patch("tasks.pipeline._log_pipeline"),
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit = MagicMock()

                result = _handle_quality_gate_and_transition(
                    brief, article, run_id=42, article_id=article.id, db=mock_db,
                )

            assert result == {"article_id": article.id}
            mock_trans.assert_called_once()
            mock_dispatch.assert_called_once()

    def test_no_logging_when_run_id_none(self, app, create_article, monkeypatch):
        """Skips pipeline logging when run_id is None."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import _handle_quality_gate_and_transition

            article = create_article(pipeline_status="researching")
            brief = _make_brief(claims=["Valid"], impact_score=50)

            with (
                patch("tasks.pipeline._transition_article_status"),
                patch("tasks.pipeline._dispatch_next"),
                patch("tasks.pipeline._log_pipeline") as mock_log,
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit = MagicMock()

                result = _handle_quality_gate_and_transition(
                    brief, article, run_id=None, article_id=article.id, db=mock_db,
                )

            assert result == {"article_id": article.id}
            mock_log.assert_not_called()

    def test_db_commit_failure_triggers_rollback(self, app, create_article, monkeypatch):
        """SQLAlchemyError on commit triggers rollback and re-raises."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import _handle_quality_gate_and_transition
            from sqlalchemy.exc import SQLAlchemyError

            article = create_article(pipeline_status="researching")
            brief = _make_brief(claims=[], impact_score=5)

            with (
                patch("tasks.pipeline._transition_article_status"),
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.commit.side_effect = SQLAlchemyError("db fail")
                mock_db.session.rollback = MagicMock()

                with pytest.raises(SQLAlchemyError):
                    _handle_quality_gate_and_transition(
                        brief, article, run_id=42, article_id=article.id, db=mock_db,
                    )

            mock_db.session.rollback.assert_called_once()


class TestGenerateResearchBrief:
    """Tests for _generate_research_brief function."""

    def test_calls_llm_with_correct_params(self, app, create_article, monkeypatch):
        """Builds prompt and calls chat_structured with correct parameters."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import _generate_research_brief
            from schemas.llm_responses import KeyClaim, ResearchBrief

            article = create_article(pipeline_status="researching")
            article.original_title = "Test Title"
            article.extracted_text = "Text content"
            article.original_url = "https://example.com"
            article.original_author = "Author"
            article.topics = ["ai"]

            rc = MagicMock()
            rc.max_article_text_length = 6000
            rc.temperature = 0.7

            provider = MagicMock()
            mock_brief = ResearchBrief(
                source_summary="summary",
                key_claims=[KeyClaim(claim="claim", source="src", confidence="high")],
                newsworthiness="news",
                impact_score=50,
            )
            provider.chat_structured.return_value = mock_brief

            with (
                patch("services.researcher.build_research_prompt", return_value="prompt"),
                patch("services.researcher.get_researcher_system_prompt", return_value="system"),
            ):
                result = _generate_research_brief(
                    article=article,
                    rc=rc,
                    web_results=[],
                    web_synthesis="",
                    related=[],
                    topic_notes="",
                    trend_memory="",
                    provider=provider,
                    model="gpt-4",
                    max_tokens=4000,
                )

            assert result == mock_brief
            provider.chat_structured.assert_called_once()
            call_kwargs = provider.chat_structured.call_args
            assert call_kwargs.kwargs["model"] == "gpt-4"
            assert call_kwargs.kwargs["stage"] == "researcher"


class TestResearchArticleTask:
    """Tests for the research_article Celery task entry point."""

    def test_research_task_budget_exceeds_nested_request_budget(self):
        """Research must not be worker-killed before its bounded LLM calls finish."""
        from tasks.research import research_article

        assert research_article.soft_time_limit == 21600
        assert research_article.time_limit == 21660

    def test_research_synthesis_budget_is_bounded(self):
        """Whole-subagent retries and excessive tool iterations stay disabled."""
        from schemas.pipeline import load_pipeline_config

        research = load_pipeline_config().subagent.research
        assert research.timeout_seconds == 600
        assert research.max_retries == 0
        assert research.max_iterations == 2

    def test_research_article_calls_run_stage(self, app, create_article, monkeypatch):
        """research_article delegates to run_stage with correct args."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import research_article
            from constants import PipelineStatus

            article = create_article(pipeline_status="selected")

            with patch("tasks.pipeline.run_stage", return_value={"article_id": article.id}) as mock_run:
                result = research_article.run(article.id, run_id=42)

            call_args = mock_run.call_args
            assert call_args[0][0] == "researcher"
            assert call_args[0][1] == article.id
            assert call_args[1]["run_id"] == 42
            assert call_args[1]["skip_next"] == PipelineStatus.WRITING

    def test_research_article_work_transitions_before_generating_brief(
        self, app, create_article, monkeypatch
    ):
        """The research work closure resolves its pipeline transition helper."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from constants import PipelineStatus
            from tasks.research import research_article

            article = create_article(pipeline_status="selected")
            role_config = MagicMock(web_search=False, db_related_max=5)
            brief = MagicMock()
            brief.impact_score = 55
            brief.model_dump_json.return_value = '{"impact_score": 55}'

            def run_work_inline(_stage, _article_id, work, task_self, **_kwargs):
                return work(article, MagicMock(), "test-model", 4096)

            with (
                patch("tasks.pipeline.run_stage", side_effect=run_work_inline),
                patch("schemas.pipeline.get_role_config", return_value=role_config),
                patch("tasks.pipeline._transition_article_status") as transition,
                patch("tasks.research._perform_web_search_and_synthesis", return_value=([], "")),
                patch("tasks.research._get_related_and_context", return_value=([], "", "")),
                patch("tasks.research._generate_research_brief", return_value=brief),
                patch("tasks.research._perform_quality_assessment"),
                patch("tasks.research._handle_quality_gate_and_transition", return_value={"article_id": article.id}),
            ):
                result = research_article.run(article.id)

            transition.assert_called_once_with(article, PipelineStatus.RESEARCHING)
            assert result == {"article_id": article.id}

    def test_research_article_with_none_run_id(self, app, create_article, monkeypatch):
        """research_article works with default run_id=None."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        with app.app_context():
            from tasks.research import research_article

            article = create_article(pipeline_status="selected")

            with patch("tasks.pipeline.run_stage", return_value={"article_id": article.id}) as mock_run:
                result = research_article.run(article.id)

            mock_run.assert_called_once()
            assert result["article_id"] == article.id

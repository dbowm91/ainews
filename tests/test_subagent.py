"""Tests for the subagent service."""

from unittest.mock import MagicMock, patch


class TestSubagentResponse:
    """Test SubagentResponse model."""

    def test_subagent_response_defaults(self):
        from services.subagent import SubagentResponse

        resp = SubagentResponse(synthesis="test synthesis")
        assert resp.synthesis == "test synthesis"
        assert resp.used_fallback is False
        assert resp.fallback_stages == []


class TestResearchSynthesisResponse:
    """Test ResearchSynthesisResponse model."""

    def test_research_synthesis_response(self):
        from services.subagent import ResearchSynthesisResponse

        resp = ResearchSynthesisResponse(synthesis="web synthesis content")
        assert resp.synthesis == "web synthesis content"


class TestEditContextualizationResponse:
    """Test EditContextualizationResponse model."""

    def test_edit_contextualization_response(self):
        from services.subagent import EditContextualizationResponse

        resp = EditContextualizationResponse(synthesis="context notes")
        assert resp.synthesis == "context notes"


class TestSubagentTemplates:
    """Test subagent task templates."""

    def test_research_synthesis_template(self):
        from services.subagent import _SUBAGENT_TASK_TEMPLATES

        template = _SUBAGENT_TASK_TEMPLATES["research_synthesis"]
        assert "source_article" in template
        assert "web_results" in template
        assert "Synthesize" in template

    def test_edit_contextualization_template(self):
        from services.subagent import _SUBAGENT_TASK_TEMPLATES

        template = _SUBAGENT_TASK_TEMPLATES["edit_contextualization"]
        assert "draft_article" in template
        assert "research_brief" in template
        assert "topic_notes" in template


class TestRunSubagent:
    """Test run_subagent function."""

    def test_run_subagent_disabled_returns_fallback(self, app):
        """When subagent is disabled, returns fallback response."""
        with app.app_context():
            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                from services.subagent import SubagentResponse
                from schemas.pipeline import SubagentStageConfig

                mock_resolve.return_value = SubagentStageConfig(enabled=False)

                from services.subagent import run_subagent

                result = run_subagent(
                    task_type="research_synthesis",
                    stage="research",
                    prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                    response_model=MagicMock(),
                )

                assert isinstance(result, SubagentResponse)
                assert result.synthesis == ""
                assert result.used_fallback is True

    def test_run_subagent_success(self, app):
        """When subagent succeeds, returns synthesis."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_response = MagicMock()
            mock_response.synthesis = "synthesized content"
            mock_provider.chat_structured.return_value = mock_response

            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    from schemas.pipeline import SubagentStageConfig

                    mock_resolve.return_value = SubagentStageConfig(
                        enabled=True,
                        provider="ollama-local",
                        model="qwen3:8b",
                        max_tokens=2048,
                        temperature=0.0,
                    )
                    mock_get_provider.return_value = mock_provider

                    from services.subagent import (
                        run_subagent,
                        ResearchSynthesisResponse,
                    )

                    result = run_subagent(
                        task_type="research_synthesis",
                        stage="research",
                        prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                        response_model=ResearchSynthesisResponse,
                    )

                    assert result.synthesis == "synthesized content"
                    assert result.used_fallback is False

    def test_run_subagent_failure_returns_fallback(self, app):
        """When subagent call fails, returns fallback response."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_provider.chat_structured.side_effect = Exception("LLM error")

            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                with patch(
                    "services.subagent.get_provider_for_role"
                ) as mock_get_provider:
                    from services.subagent import SubagentResponse
                    from schemas.pipeline import SubagentStageConfig

                    mock_resolve.return_value = SubagentStageConfig(
                        enabled=True,
                        provider="ollama-local",
                        model="qwen3:8b",
                        max_tokens=2048,
                        temperature=0.0,
                    )
                    mock_get_provider.return_value = (mock_provider, "qwen3:8b", 2048)

                    from services.subagent import (
                        run_subagent,
                        ResearchSynthesisResponse,
                    )

                    result = run_subagent(
                        task_type="research_synthesis",
                        stage="research",
                        prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                        response_model=ResearchSynthesisResponse,
                    )

                    assert isinstance(result, SubagentResponse)
                    assert result.synthesis == ""
                    assert result.used_fallback is True
                    assert "research" in result.fallback_stages


class TestResolveSubagentConfig:
    """Test resolve_subagent_config function."""

    def test_resolve_disabled_subagent(self, app):
        """Disabled subagent returns disabled config."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                mock_config = MagicMock()
                mock_config.subagent.research.enabled = False
                mock_config.pipeline.editor.provider = "ollama-local"
                mock_config.pipeline.editor.model = "qwen3:8b"
                mock_load.return_value = mock_config

                from services.subagent import resolve_subagent_config

                result = resolve_subagent_config("research")
                assert result.enabled is False

    def test_resolve_enabled_subagent_with_defaults(self, app):
        """Enabled subagent uses editor defaults when provider/model not set."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                mock_config = MagicMock()
                mock_config.subagent.edit.enabled = True
                mock_config.subagent.edit.provider = None
                mock_config.subagent.edit.model = None
                mock_config.subagent.edit.max_tokens = None
                mock_config.subagent.edit.temperature = None
                mock_config.subagent.edit.timeout_seconds = 120
                mock_config.subagent.edit.system_prompt = None
                mock_config.pipeline.editor.provider = "ollama-local"
                mock_config.pipeline.editor.model = "qwen3:8b"
                mock_load.return_value = mock_config

                from services.subagent import resolve_subagent_config

                result = resolve_subagent_config("edit")
                assert result.enabled is True
                assert result.provider == "ollama-local"
                assert result.model == "qwen3:8b"

    def test_resolve_enabled_subagent_with_custom_settings(self, app):
        """Enabled subagent uses its own provider/model when set."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                mock_config = MagicMock()
                mock_config.subagent.research.enabled = True
                mock_config.subagent.research.provider = "custom-provider"
                mock_config.subagent.research.model = "custom-model"
                mock_config.subagent.research.max_tokens = 4096
                mock_config.subagent.research.temperature = 0.5
                mock_config.subagent.research.timeout_seconds = 180
                mock_config.subagent.research.system_prompt = "custom prompt"
                mock_load.return_value = mock_config

                from services.subagent import resolve_subagent_config

                result = resolve_subagent_config("research")
                assert result.enabled is True
                assert result.provider == "custom-provider"
                assert result.model == "custom-model"
                assert result.max_tokens == 4096
                assert result.temperature == 0.5
                assert result.timeout_seconds == 180
                assert result.system_prompt == "custom prompt"

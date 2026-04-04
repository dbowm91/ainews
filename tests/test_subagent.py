"""Tests for the subagent service."""

from unittest.mock import MagicMock, patch


class TestSubagentResponse:
    """Test SubagentResponse model."""

    def test_subagent_response_defaults(self):
        from schemas.llm_responses import SubagentResponse

        resp = SubagentResponse(synthesis="test synthesis")
        assert resp.synthesis == "test synthesis"
        assert resp.used_fallback is False
        assert resp.fallback_stages == []


class TestResearchSynthesisResponse:
    """Test ResearchSynthesisResponse model."""

    def test_research_synthesis_response(self):
        from schemas.llm_responses import ResearchSynthesisResponse

        resp = ResearchSynthesisResponse(synthesis="web synthesis content")
        assert resp.synthesis == "web synthesis content"


class TestEditContextualizationResponse:
    """Test EditContextualizationResponse model."""

    def test_edit_contextualization_response(self):
        from schemas.llm_responses import EditContextualizationResponse

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

    def test_get_task_template_falls_back_to_hardcoded(self, app):
        """When no task_template is set, falls back to hardcoded templates."""
        with app.app_context():
            from schemas.pipeline import SubagentStageConfig
            from services.subagent import _get_task_template

            config = SubagentStageConfig(enabled=True)
            template = _get_task_template("research_synthesis", config)
            assert "source_article" in template
            assert "web_results" in template

    def test_get_task_template_loads_from_file(self, app, tmp_path):
        """When task_template is set and file exists, loads from file."""
        with app.app_context():
            from schemas.pipeline import SubagentStageConfig, BASE_DIR
            from services.subagent import _get_task_template

            prompt_file = BASE_DIR / "prompts" / "test_template.txt"
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("CUSTOM TEMPLATE CONTENT")

            try:
                config = SubagentStageConfig(
                    enabled=True,
                    task_template="prompts/test_template.txt",
                )
                template = _get_task_template("research_synthesis", config)
                assert template == "CUSTOM TEMPLATE CONTENT"
            finally:
                prompt_file.unlink(missing_ok=True)

    def test_get_task_template_falls_back_when_file_missing(self, app):
        """When task_template is set but file doesn't exist, falls back to hardcoded."""
        with app.app_context():
            from schemas.pipeline import SubagentStageConfig
            from services.subagent import _get_task_template

            config = SubagentStageConfig(
                enabled=True,
                task_template="nonexistent/prompt.txt",
            )
            template = _get_task_template("research_synthesis", config)
            assert "source_article" in template


class TestRunSubagent:
    """Test run_subagent function."""

    def test_run_subagent_disabled_returns_fallback(self, app):
        """When subagent is disabled, returns fallback response."""
        with app.app_context():
            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                from schemas.llm_responses import SubagentResponse
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
                    with patch("services.subagent.get_metrics") as mock_metrics:
                        from schemas.pipeline import SubagentStageConfig

                        mock_resolve.return_value = SubagentStageConfig(
                            enabled=True,
                            provider="ollama-local",
                            model="qwen3:8b",
                            max_tokens=2048,
                            temperature=0.0,
                        )
                        mock_get_provider.return_value = mock_provider
                        mock_metrics_instance = MagicMock()
                        mock_metrics.return_value = mock_metrics_instance

                        from services.subagent import run_subagent
                        from schemas.llm_responses import ResearchSynthesisResponse

                        result = run_subagent(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={
                                "title": "t",
                                "body": "b",
                                "web_results": "wr",
                            },
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
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    with patch("services.subagent.get_metrics") as mock_metrics:
                        from schemas.llm_responses import SubagentResponse
                        from schemas.pipeline import SubagentStageConfig

                        mock_resolve.return_value = SubagentStageConfig(
                            enabled=True,
                            provider="ollama-local",
                            model="qwen3:8b",
                            max_tokens=2048,
                            temperature=0.0,
                        )
                        mock_get_provider.return_value = mock_provider
                        mock_metrics_instance = MagicMock()
                        mock_metrics.return_value = mock_metrics_instance

                        from services.subagent import run_subagent
                        from schemas.llm_responses import ResearchSynthesisResponse

                        result = run_subagent(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={
                                "title": "t",
                                "body": "b",
                                "web_results": "wr",
                            },
                            response_model=ResearchSynthesisResponse,
                        )

                        assert isinstance(result, SubagentResponse)
                        assert result.synthesis == ""
                        assert result.used_fallback is True
                        assert "research" in result.fallback_stages

    def test_run_subagent_with_article_id(self, app):
        """article_id parameter is passed through to logging."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_response = MagicMock()
            mock_response.synthesis = "synthesized content"
            mock_provider.chat_structured.return_value = mock_response

            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    with patch("services.subagent.log_pipeline_event") as mock_log:
                        from schemas.pipeline import SubagentStageConfig

                        mock_resolve.return_value = SubagentStageConfig(
                            enabled=True,
                            provider="ollama-local",
                            model="qwen3:8b",
                            max_tokens=2048,
                            temperature=0.0,
                        )
                        mock_get_provider.return_value = mock_provider

                        from services.subagent import run_subagent
                        from schemas.llm_responses import ResearchSynthesisResponse

                        result = run_subagent(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={
                                "title": "t",
                                "body": "b",
                                "web_results": "wr",
                            },
                            response_model=ResearchSynthesisResponse,
                            article_id=123,
                        )

                        assert result.synthesis == "synthesized content"
                        events = [call[1] for call in mock_log.call_args_list]
                        assert any("subagent.start" in str(e) for e in events)
                        assert any("subagent.complete" in str(e) for e in events)

    def test_run_subagent_emits_metrics(self, app):
        """Subagent calls emit success/failure metrics."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_response = MagicMock()
            mock_response.synthesis = "synthesized content"
            mock_provider.chat_structured.return_value = mock_response

            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    with patch("services.subagent.get_metrics") as mock_metrics:
                        from schemas.pipeline import SubagentStageConfig

                        mock_resolve.return_value = SubagentStageConfig(
                            enabled=True,
                            provider="ollama-local",
                            model="qwen3:8b",
                            max_tokens=2048,
                            temperature=0.0,
                        )
                        mock_get_provider.return_value = mock_provider
                        mock_metrics_instance = MagicMock()
                        mock_metrics.return_value = mock_metrics_instance

                        from services.subagent import run_subagent
                        from schemas.llm_responses import ResearchSynthesisResponse

                        run_subagent(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={
                                "title": "t",
                                "body": "b",
                                "web_results": "wr",
                            },
                            response_model=ResearchSynthesisResponse,
                        )

                        mock_metrics_instance.counter_inc.assert_any_call(
                            "subagent.success",
                            labels={
                                "stage": "research",
                                "task_type": "research_synthesis",
                            },
                        )
                        mock_metrics_instance.counter_inc.assert_any_call(
                            "subagent.calls",
                            labels={
                                "stage": "research",
                                "task_type": "research_synthesis",
                                "status": "success",
                            },
                        )

    def test_run_subagent_retries_on_transient_error(self, app):
        """Subagent retries on ProviderTimeoutError, ConnectionError, TimeoutError."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_response = MagicMock()
            mock_response.synthesis = "synthesized content"
            mock_provider.chat_structured.side_effect = [
                TimeoutError("first attempt"),
                TimeoutError("second attempt"),
                mock_response,
            ]

            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    with patch("services.subagent.get_metrics") as mock_metrics:
                        from schemas.pipeline import SubagentStageConfig

                        mock_resolve.return_value = SubagentStageConfig(
                            enabled=True,
                            provider="ollama-local",
                            model="qwen3:8b",
                            max_tokens=2048,
                            temperature=0.0,
                            max_retries=2,
                            retry_delay=0.01,
                        )
                        mock_get_provider.return_value = mock_provider
                        mock_metrics_instance = MagicMock()
                        mock_metrics.return_value = mock_metrics_instance

                        from services.subagent import run_subagent
                        from schemas.llm_responses import ResearchSynthesisResponse

                        result = run_subagent(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={
                                "title": "t",
                                "body": "b",
                                "web_results": "wr",
                            },
                            response_model=ResearchSynthesisResponse,
                        )

                        assert result.synthesis == "synthesized content"
                        assert result.used_fallback is False
                        assert mock_provider.chat_structured.call_count == 3

    def test_run_subagent_no_retry_on_auth_error(self, app):
        """Subagent does not retry on AuthError."""
        with app.app_context():
            from services.llm.errors import AuthError

            mock_provider = MagicMock()
            mock_provider.chat_structured.side_effect = AuthError("auth failed")

            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    with patch("services.subagent.get_metrics") as mock_metrics:
                        from schemas.pipeline import SubagentStageConfig

                        mock_resolve.return_value = SubagentStageConfig(
                            enabled=True,
                            provider="ollama-local",
                            model="qwen3:8b",
                            max_tokens=2048,
                            temperature=0.0,
                            max_retries=2,
                            retry_delay=0.01,
                        )
                        mock_get_provider.return_value = mock_provider
                        mock_metrics_instance = MagicMock()
                        mock_metrics.return_value = mock_metrics_instance

                        from services.subagent import run_subagent
                        from schemas.llm_responses import ResearchSynthesisResponse

                        result = run_subagent(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={
                                "title": "t",
                                "body": "b",
                                "web_results": "wr",
                            },
                            response_model=ResearchSynthesisResponse,
                        )

                        assert result.synthesis == ""
                        assert result.used_fallback is True
                        assert mock_provider.chat_structured.call_count == 1


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
        """Enabled subagent uses role defaults when provider/model not set."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                with patch("schemas.pipeline.get_role_config") as mock_get_role:
                    mock_config = MagicMock()
                    mock_config.subagent.edit.enabled = True
                    mock_config.subagent.edit.provider = None
                    mock_config.subagent.edit.model = None
                    mock_config.subagent.edit.max_tokens = None
                    mock_config.subagent.edit.temperature = None
                    mock_config.subagent.edit.timeout_seconds = 120
                    mock_config.subagent.edit.system_prompt = None
                    mock_config.subagent.edit.max_retries = 1
                    mock_config.subagent.edit.retry_delay = 5.0
                    mock_config.subagent.edit.task_template = None
                    mock_config.pipeline.editor.provider = "ollama-local"
                    mock_config.pipeline.editor.model = "qwen3:8b"
                    mock_load.return_value = mock_config
                    mock_get_role.return_value = MagicMock(
                        provider="editor-provider", model="editor-model"
                    )

                    from services.subagent import resolve_subagent_config

                    result = resolve_subagent_config("edit", default_role="editor")
                    assert result.enabled is True
                    assert result.provider == "editor-provider"
                    assert result.model == "editor-model"

    def test_resolve_enabled_subagent_uses_researcher_for_research_stage(self, app):
        """Research stage falls back to researcher role, not editor."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                with patch("schemas.pipeline.get_role_config") as mock_get_role:
                    mock_config = MagicMock()
                    mock_config.subagent.research.enabled = True
                    mock_config.subagent.research.provider = None
                    mock_config.subagent.research.model = None
                    mock_config.subagent.research.max_tokens = None
                    mock_config.subagent.research.temperature = None
                    mock_config.subagent.research.timeout_seconds = 120
                    mock_config.subagent.research.system_prompt = None
                    mock_config.subagent.research.max_retries = 1
                    mock_config.subagent.research.retry_delay = 5.0
                    mock_config.subagent.research.task_template = None
                    mock_load.return_value = mock_config
                    mock_get_role.return_value = MagicMock(
                        provider="researcher-provider", model="researcher-model"
                    )

                    from services.subagent import resolve_subagent_config

                    result = resolve_subagent_config(
                        "research", default_role="researcher"
                    )
                    assert result.enabled is True
                    assert result.provider == "researcher-provider"
                    assert result.model == "researcher-model"

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
                mock_config.subagent.research.max_retries = 3
                mock_config.subagent.research.retry_delay = 10.0
                mock_config.subagent.research.task_template = "prompts/custom.txt"
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
                assert result.max_retries == 3
                assert result.retry_delay == 10.0
                assert result.task_template == "prompts/custom.txt"

    def test_resolve_subagent_config_passes_max_retries_and_retry_delay(self, app):
        """resolve_subagent_config passes max_retries and retry_delay to SubagentStageConfig."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                with patch("schemas.pipeline.get_role_config") as mock_get_role:
                    mock_config = MagicMock()
                    mock_config.subagent.edit.enabled = True
                    mock_config.subagent.edit.provider = None
                    mock_config.subagent.edit.model = None
                    mock_config.subagent.edit.max_tokens = None
                    mock_config.subagent.edit.temperature = None
                    mock_config.subagent.edit.timeout_seconds = 120
                    mock_config.subagent.edit.system_prompt = None
                    mock_config.subagent.edit.max_retries = 3
                    mock_config.subagent.edit.retry_delay = 15.0
                    mock_config.subagent.edit.task_template = None
                    mock_load.return_value = mock_config
                    mock_get_role.return_value = MagicMock(provider="p", model="m")

                    from services.subagent import resolve_subagent_config

                    result = resolve_subagent_config("edit")
                    assert result.max_retries == 3
                    assert result.retry_delay == 15.0

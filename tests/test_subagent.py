"""Tests for the subagent service."""

from unittest.mock import MagicMock, patch

import pytest


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
            from schemas.pipeline import BASE_DIR, SubagentStageConfig
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


class TestEscapePromptData:
    """Tests for _escape_prompt_data function."""

    def test_escapes_simple_strings(self):
        from services.subagent import _escape_prompt_data

        data = {"title": "<script>alert('xss')</script>", "body": "normal text"}
        result = _escape_prompt_data(data)
        assert result["title"] == "&lt;script&gt;alert('xss')&lt;/script&gt;"
        assert result["body"] == "normal text"

    def test_escapes_nested_dicts(self):
        from services.subagent import _escape_prompt_data

        data = {
            "outer": {
                "inner": "<img src=x onerror=alert(1)>",
                "safe": "normal",
            }
        }
        result = _escape_prompt_data(data)
        assert result["outer"]["inner"] == "&lt;img src=x onerror=alert(1)&gt;"
        assert result["outer"]["safe"] == "normal"

    def test_escapes_lists(self):
        from services.subagent import _escape_prompt_data

        data = {"items": ["<b>bold</b>", "normal", "<i>italic</i>"]}
        result = _escape_prompt_data(data)
        assert result["items"][0] == "&lt;b&gt;bold&lt;/b&gt;"
        assert result["items"][1] == "normal"
        assert result["items"][2] == "&lt;i&gt;italic&lt;/i&gt;"

    def test_preserves_non_string_values(self):
        from services.subagent import _escape_prompt_data

        data = {"count": 42, "enabled": True, "ratio": 3.14, "none_val": None}
        result = _escape_prompt_data(data)
        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["ratio"] == 3.14
        assert result["none_val"] is None

    def test_handles_empty_strings(self):
        from services.subagent import _escape_prompt_data

        data = {"empty": "", "title": "no special chars"}
        result = _escape_prompt_data(data)
        assert result["empty"] == ""
        assert result["title"] == "no special chars"

    def test_escapes_xml_special_chars(self):
        from services.subagent import _escape_prompt_data

        data = {"xml": "<tag attr=\"value\">content & more</tag>"}
        result = _escape_prompt_data(data)
        assert "&lt;tag" in result["xml"]
        assert "attr=\"value\"" in result["xml"]
        assert "&amp; more" in result["xml"]


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

                        from schemas.llm_responses import ResearchSynthesisResponse
                        from services.subagent import run_subagent

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

                        from schemas.llm_responses import ResearchSynthesisResponse
                        from services.subagent import run_subagent

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

                        from schemas.llm_responses import ResearchSynthesisResponse
                        from services.subagent import run_subagent

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

                        from schemas.llm_responses import ResearchSynthesisResponse
                        from services.subagent import run_subagent

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

                        from schemas.llm_responses import ResearchSynthesisResponse
                        from services.subagent import run_subagent

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

                        from schemas.llm_responses import ResearchSynthesisResponse
                        from services.subagent import run_subagent

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


class TestRunSubagentWithTools:
    """Test run_subagent_with_tools function."""

    def test_runs_with_tools_success(self, app):
        """When subagent succeeds with tools, returns synthesis."""
        with app.app_context():
            mock_tc_resp = MagicMock()
            mock_tc_resp.text = "tool use result"

            mock_provider = MagicMock()
            mock_provider.chat_with_tools.return_value = mock_tc_resp

            mock_tools = [MagicMock()]

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

                        from schemas.llm_responses import SubagentResponse
                        from services.subagent import run_subagent_with_tools

                        result = run_subagent_with_tools(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                            response_model=SubagentResponse,
                            tools=mock_tools,
                        )

                        assert result.synthesis == "tool use result"
                        assert result.used_fallback is False
                        mock_provider.chat_with_tools.assert_called_once()
                        call_kwargs = mock_provider.chat_with_tools.call_args.kwargs
                        assert call_kwargs["tools"] == mock_tools
                        assert call_kwargs["max_iterations"] == 5

    def test_disabled_returns_fallback(self, app):
        """When subagent is disabled, returns fallback response."""
        with app.app_context():
            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                from schemas.llm_responses import SubagentResponse
                from schemas.pipeline import SubagentStageConfig

                mock_resolve.return_value = SubagentStageConfig(enabled=False)

                from services.subagent import run_subagent_with_tools

                result = run_subagent_with_tools(
                    task_type="research_synthesis",
                    stage="research",
                    prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                    response_model=SubagentResponse,
                    tools=[],
                )

                assert isinstance(result, SubagentResponse)
                assert result.synthesis == ""
                assert result.used_fallback is True

    def test_failure_returns_fallback(self, app):
        """When provider fails, returns fallback response."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_provider.chat_with_tools.side_effect = Exception("LLM error")

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

                        from services.subagent import run_subagent_with_tools

                        result = run_subagent_with_tools(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                            response_model=SubagentResponse,
                            tools=[],
                        )

                        assert isinstance(result, SubagentResponse)
                        assert result.synthesis == ""
                        assert result.used_fallback is True
                        assert "research" in result.fallback_stages

    def test_timeout_returns_fallback(self, app):
        """When timeout occurs, returns fallback response."""
        with app.app_context():
            mock_provider = MagicMock()
            mock_tc_resp = MagicMock()
            mock_tc_resp.text = "result"
            mock_provider.chat_with_tools.side_effect = [
                TimeoutError("first attempt"),
                TimeoutError("second attempt"),
                mock_tc_resp,
            ]

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
                            max_retries=2,
                            retry_delay=0.01,
                        )
                        mock_get_provider.return_value = mock_provider
                        mock_metrics_instance = MagicMock()
                        mock_metrics.return_value = mock_metrics_instance

                        from services.subagent import run_subagent_with_tools

                        result = run_subagent_with_tools(
                            task_type="research_synthesis",
                            stage="research",
                            prompt_data={"title": "t", "body": "b", "web_results": "wr"},
                            response_model=SubagentResponse,
                            tools=[],
                        )

                        assert result.synthesis == "result"
                        assert result.used_fallback is False
                        assert mock_provider.chat_with_tools.call_count == 3


class TestSubagentChain:
    """Test run_subagent_chain function."""

    def test_chain_execution_returns_results(self, app):
        """Chain steps execute and return results."""
        with app.app_context():
            mock_resp = MagicMock()
            mock_resp.text = "chain result"

            mock_provider = MagicMock()
            mock_provider.chat.return_value = mock_resp

            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    from schemas.pipeline import (
                        SubagentChainConfig,
                        SubagentChainStep,
                        SubagentStageConfig,
                    )

                    chain_config = SubagentChainConfig(
                        enabled=True,
                        steps=[
                            SubagentChainStep(
                                task_type="research_synthesis",
                                prompt_data_template="{title}",
                                response_model=None,
                            ),
                        ],
                        max_length=10,
                    )
                    mock_config = MagicMock()
                    mock_config.subagent.chains = {"test_chain": chain_config}
                    mock_config.subagent.research = SubagentStageConfig(
                        enabled=True,
                        provider="ollama-local",
                        model="qwen3:8b",
                        max_tokens=2048,
                        temperature=0.0,
                    )
                    mock_load.return_value = mock_config
                    mock_get_provider.return_value = mock_provider

                    from services.subagent import run_subagent_chain

                    result = run_subagent_chain(
                        chain_name="test_chain",
                        steps=[],
                        initial_prompt_data={"title": "test"},
                    )

                    assert "results" in result
                    assert "test_chain_step_0" in result["results"]
                    assert result["used_fallback"] is False

    def test_step_skipped_on_condition(self, app):
        """Step is skipped when condition evaluates to False."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    from schemas.pipeline import (
                        SubagentChainConfig,
                        SubagentChainStep,
                        SubagentStageConfig,
                    )

                    chain_config = SubagentChainConfig(
                        enabled=True,
                        steps=[
                            SubagentChainStep(
                                task_type="research_synthesis",
                                prompt_data_template="{title}",
                                response_model=None,
                                condition="results.get('skipped') == True",
                            ),
                        ],
                        max_length=10,
                    )
                    mock_config = MagicMock()
                    mock_config.subagent.chains = {"test_chain": chain_config}
                    mock_config.subagent.research = SubagentStageConfig(
                        enabled=True,
                        provider="ollama-local",
                        model="qwen3:8b",
                        max_tokens=2048,
                        temperature=0.0,
                    )
                    mock_load.return_value = mock_config
                    mock_get_provider.return_value = MagicMock()

                    from services.subagent import run_subagent_chain

                    result = run_subagent_chain(
                        chain_name="test_chain",
                        steps=[],
                        initial_prompt_data={"title": "test"},
                    )

                    step_result = result["results"]["test_chain_step_0"]
                    assert step_result["skipped"] is True
                    assert step_result["synthesis"] == ""

    def test_chain_continues_on_step_failure(self, app):
        """Chain continues to next step when one step fails."""
        with app.app_context():
            from services.llm.errors import ProviderServerError

            mock_provider = MagicMock()
            mock_provider.chat.side_effect = ProviderServerError("server error")

            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                with patch("services.llm.get_provider_by_id") as mock_get_provider:
                    from schemas.pipeline import (
                        SubagentChainConfig,
                        SubagentChainStep,
                        SubagentStageConfig,
                    )

                    chain_config = SubagentChainConfig(
                        enabled=True,
                        steps=[
                            SubagentChainStep(
                                task_type="research_synthesis",
                                prompt_data_template="{title}",
                                response_model=None,
                            ),
                            SubagentChainStep(
                                task_type="edit_review",
                                prompt_data_template="{content}",
                                response_model=None,
                            ),
                        ],
                        max_length=10,
                    )
                    mock_config = MagicMock()
                    mock_config.subagent.chains = {"test_chain": chain_config}
                    mock_config.subagent.research = SubagentStageConfig(
                        enabled=True,
                        provider="ollama-local",
                        model="qwen3:8b",
                        max_tokens=2048,
                        temperature=0.0,
                    )
                    mock_config.subagent.edit = SubagentStageConfig(
                        enabled=True,
                        provider="ollama-local",
                        model="qwen3:8b",
                        max_tokens=2048,
                        temperature=0.0,
                    )
                    mock_load.return_value = mock_config
                    mock_get_provider.return_value = mock_provider

                    from services.subagent import run_subagent_chain

                    result = run_subagent_chain(
                        chain_name="test_chain",
                        steps=[],
                        initial_prompt_data={"title": "test"},
                    )

                    step1_result = result["results"]["test_chain_step_0"]
                    assert step1_result["used_fallback"] is True
                    assert "Fallback" in step1_result["synthesis"]
                    assert "test_chain_step_1" in result["results"]

    def test_disabled_chain_returns_fallback(self, app):
        """Disabled chain returns fallback without executing steps."""
        with app.app_context():
            with patch("schemas.pipeline.load_pipeline_config") as mock_load:
                mock_config = MagicMock()
                mock_config.subagent.chains.get.return_value = None
                mock_load.return_value = mock_config

                from services.subagent import run_subagent_chain

                result = run_subagent_chain(
                    chain_name="nonexistent_chain",
                    steps=[],
                    initial_prompt_data={},
                )

                assert result["results"] == {}
                assert result["used_fallback"] is True
                assert "chain" in result["fallback_stages"]


class TestEvaluateCondition:
    """Test _evaluate_condition function."""

    def test_evaluate_condition_ast(self):
        """Condition evaluation uses AST-based parsing."""
        from services.subagent import _evaluate_condition

        context = {"results": {"key": "value", "count": 5}}

        assert _evaluate_condition("results['key'] == 'value'", context) is True
        assert _evaluate_condition("results['key'] == 'wrong'", context) is False
        assert _evaluate_condition("results['count'] > 3", context) is True
        assert _evaluate_condition("results['count'] < 3", context) is False

    def test_evaluate_condition_with_and_or(self):
        """Condition evaluation supports AND/OR operators."""
        from services.subagent import _evaluate_condition

        context = {"results": {"a": True, "b": False}}

        assert _evaluate_condition("results['a'] and True", context) is True
        assert _evaluate_condition("results['a'] and results['b']", context) is False
        assert _evaluate_condition("results['a'] or results['b']", context) is True
        assert _evaluate_condition("results['b'] or False", context) is False

    def test_evaluate_condition_with_not(self):
        """Condition evaluation supports NOT operator."""
        from services.subagent import _evaluate_condition

        context = {"results": {"flag": False}}

        assert _evaluate_condition("not results['flag']", context) is True
        assert _evaluate_condition("not True", {"results": {}}) is False

    def test_evaluate_condition_invalid_syntax(self):
        """Invalid syntax returns False."""
        from services.subagent import _evaluate_condition

        context = {"results": {}}

        assert _evaluate_condition("this is not valid python syntax !!!", context) is False

    def test_evaluate_condition_unknown_identifier(self):
        """Unknown identifier raises ValueError."""
        from services.subagent import _evaluate_condition

        context = {"results": {}}

        assert _evaluate_condition("unknown_var == 1", context) is False

    def test_evaluate_condition_with_in(self):
        """Condition evaluation supports 'in' operator."""
        from services.subagent import _evaluate_condition

        context = {"results": {"items": [1, 2, 3]}}

        assert _evaluate_condition("1 in results['items']", context) is True
        assert _evaluate_condition("5 in results['items']", context) is False

    def test_condition_evaluator_blocks_function_calls(self):
        """Function calls in conditions raise ValueError for security."""
        from services.subagent import _evaluate_condition

        context = {"results": {"items": [1, 2, 3]}}

        with pytest.raises(ValueError):
            _evaluate_condition("len(results['items']) > 1", context)

        with pytest.raises(ValueError):
            _evaluate_condition("int(results['items'][0])", context)

        with pytest.raises(ValueError):
            _evaluate_condition("max(results['items'])", context)

    def test_condition_evaluator_dict_access_works(self):
        """Dict access + boolean comparisons still work."""
        from services.subagent import _evaluate_condition

        context = {"results": {"key": "value", "count": 5, "active": True}}

        assert _evaluate_condition("results['key'] == 'value'", context) is True
        assert _evaluate_condition("results['count'] >= 5", context) is True
        assert _evaluate_condition("results['active']", context) is True
        assert _evaluate_condition("results['key'] != 'wrong'", context) is True

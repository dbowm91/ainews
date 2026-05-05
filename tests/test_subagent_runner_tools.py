"""Tests for subagent runner with tools."""

from unittest.mock import MagicMock, patch



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

    def test_run_subagent_with_tools_template_missing_key(self, app):
        """When template has missing key, returns fallback."""
        with app.app_context():
            with patch("services.subagent.resolve_subagent_config") as mock_resolve:
                from schemas.llm_responses import SubagentResponse
                from schemas.pipeline import SubagentStageConfig

                mock_resolve.return_value = SubagentStageConfig(
                    enabled=True,
                    provider="ollama-local",
                    model="qwen3:8b",
                    max_tokens=2048,
                    temperature=0.0,
                )

                from services.subagent import run_subagent_with_tools

                result = run_subagent_with_tools(
                    task_type="research_synthesis",
                    stage="research",
                    prompt_data={"title": "t", "body": "b"},  # missing web_results
                    response_model=SubagentResponse,
                    tools=[],
                )

                assert result.synthesis == ""
                assert result.used_fallback is True
"""Tests for subagent chain execution."""

from unittest.mock import MagicMock, patch

import pytest


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
                        steps=None,
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
                        steps=None,
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
                        steps=None,
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

    def test_chain_step_condition_evaluation_error_skips_step(self, app):
        """Step is skipped when condition evaluation raises ValueError."""
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
                                condition="unknown_var == 1",  # Will raise ValueError
                            ),
                        ],
                        max_length=10,
                    )
                    mock_config = MagicMock()
                    mock_config.subagent.chains = {"test_chain": chain_config}
                    mock_config.subagent.research = SubagentStageConfig(enabled=True)
                    mock_load.return_value = mock_config
                    mock_get_provider.return_value = MagicMock()

                    from services.subagent import run_subagent_chain

                    result = run_subagent_chain(
                        chain_name="test_chain",
                        steps=None,
                        initial_prompt_data={"title": "test"},
                    )

                    step_result = result["results"]["test_chain_step_0"]
                    assert step_result["skipped"] is True
                    assert step_result["synthesis"] == ""


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

    def test_evaluate_condition_protected_attribute(self):
        """Accessing protected attributes raises ValueError."""
        from services.subagent import _evaluate_condition

        class Obj:
            _private = "value"

        context = {"results": {"obj": Obj()}}
        with pytest.raises(ValueError):
            _evaluate_condition("results['obj']._private == 'value'", context)

    def test_evaluate_condition_subscript_non_dict(self):
        """Subscript on non-dict/list returns False."""
        from services.subagent import _evaluate_condition

        context = {"results": {"items": "not a list"}}
        assert _evaluate_condition("results['items'][0] == 'a'", context) is False

    def test_evaluate_condition_attribute_access(self):
        """Attribute access on objects works."""
        from services.subagent import _evaluate_condition

        class Obj:
            attr = "test"

        context = {"results": {"obj": Obj()}}
        assert _evaluate_condition("results['obj'].attr == 'test'", context) is True

    def test_evaluate_condition_lambda_blocked(self):
        """Lambda expressions in conditions raise ValueError."""
        from services.subagent import _evaluate_condition

        context = {"results": {}}
        with pytest.raises(ValueError):
            _evaluate_condition("lambda x: x", context)

    def test_evaluate_condition_not_in_operator(self):
        """'not in' operator works correctly."""
        from services.subagent import _evaluate_condition

        context = {"results": {"items": [1, 2, 3]}}
        assert _evaluate_condition("5 not in results['items']", context) is True
        assert _evaluate_condition("2 not in results['items']", context) is False


class TestResolveTemplateVariables:
    """Test _resolve_template_variables function."""

    def test_resolves_simple_variables(self):
        from services.subagent import _resolve_template_variables

        initial = {"title": "test title"}
        results = {}
        resolved = _resolve_template_variables("{title}", initial, results)
        assert resolved["title"] == "test title"

    def test_resolves_previous_step_results(self):
        from services.subagent import _resolve_template_variables

        initial = {"content": "{step_0}"}
        results = {"step_0": "previous content"}
        resolved = _resolve_template_variables("{content}", initial, results)
        assert resolved["content"] == "previous content"

    def test_handles_missing_keys_in_results(self):
        from services.subagent import _resolve_template_variables

        initial = {"content": "{missing_key}"}
        results = {}
        resolved = _resolve_template_variables("{content}", initial, results)
        assert resolved["content"] == "{missing_key}"

    def test_no_variables_no_change(self):
        from services.subagent import _resolve_template_variables

        initial = {"title": "no variables here"}
        results = {}
        resolved = _resolve_template_variables("{title}", initial, results)
        assert resolved["title"] == "no variables here"
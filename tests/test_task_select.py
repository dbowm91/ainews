"""Tests for tasks/select.py (select_article pipeline stage)."""

from unittest.mock import MagicMock, patch

import pytest


class TestSelectArticle:
    """Tests for select_article task through run_stage."""

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_success")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.circuit_breaker.get_breaker")
    @patch("services.llm.get_provider_by_id")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    @patch("tasks.pipeline._transition_article_status")
    @pytest.mark.skip(reason="Mock integration issue - needs refactoring")
    def test_score_above_threshold_selects(
        self,
        mock_transition,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_by_id,
        mock_get_breaker,
        mock_rec_stage,
        mock_rec_success,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks import pipeline as pipeline_module
        from tasks.select import select_article

        mock_breaker = MagicMock()
        mock_breaker.can_execute.return_value = True
        mock_get_breaker.return_value = mock_breaker

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        rc.temperature = 0.0
        mock_get_rc.return_value = rc

        provider = MagicMock()
        result_obj = MagicMock()
        result_obj.configure_mock(
            selected=True,
            score=8,
            reason="important",
            confidence="high",
            model_dump=lambda: {
                "selected": True,
                "score": 8,
                "reason": "important",
            },
        )
        provider.chat_structured.return_value = result_obj

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_transition.return_value = True

        def mock_chain_fn(stage):
            return iter([(provider, "test-model", 1024, "ollama-local")])

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            with patch.object(pipeline_module, "get_provider_chain", mock_chain_fn):
                result = select_article.__wrapped__(article_id=article_id, run_id=None)

        assert result["article_id"] == article_id
        assert result["result"]["selected"] is True
        assert result["result"]["score"] == 8

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_success")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.circuit_breaker.get_breaker")
    @patch("services.llm.get_provider_by_id")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.config_unified.get_config")
    @patch("services.limiter.get_limiter")
    @patch("tasks.pipeline._transition_article_status")
    def test_score_below_threshold_skips(
        self,
        mock_transition,
        mock_limiter_fn,
        mock_get_config,
        mock_get_rc,
        mock_get_by_id,
        mock_get_breaker,
        mock_rec_stage,
        mock_rec_success,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks import pipeline as pipeline_module
        from tasks.select import select_article

        mock_breaker = MagicMock()
        mock_breaker.can_execute.return_value = True
        mock_get_breaker.return_value = mock_breaker

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        rc.temperature = 0.0
        mock_get_rc.return_value = rc

        # Mock get_config to return experiment config
        mock_get_config.return_value = {
            "experiments": {
                "enabled": True,
                "assignment_salt": "test_salt",
                "prompt_variants": {
                    "writer": {"control": "test", "variant_a": "test_a", "variant_b": "test_b"},
                    "editor": {"control": "test", "variant_a": "test_a", "variant_b": "test_b"},
                },
            }
        }

        provider = MagicMock()
        result_obj = MagicMock()
        result_obj.configure_mock(
            selected=False,
            score=3,
            reason="not newsworthy",
            confidence="high",
            model_dump=lambda: {
                "selected": False,
                "score": 3,
                "reason": "not newsworthy",
            },
        )
        provider.chat_structured.return_value = result_obj

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        mock_transition.return_value = True

        def mock_chain_fn(stage):
            return iter([(provider, "test-model", 1024, "ollama-local")])

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            with patch.object(pipeline_module, "get_provider_chain", mock_chain_fn):
                result = select_article.__wrapped__(article_id=article_id, run_id=None)

        assert result["article_id"] == article_id
        assert result["result"]["selected"] is False
        assert result["result"]["score"] == 3

    @patch("extensions.get_redis")
    @patch("schemas.pipeline.get_role_config")
    @patch("tasks.pipeline._dispatch_next")
    def test_selector_disabled_skips_directly(
        self,
        mock_dispatch,
        mock_get_rc,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks.select import select_article

        rc = MagicMock()
        rc.enabled = False
        mock_get_rc.return_value = rc

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            result = select_article.__wrapped__(article_id=article_id, run_id=None)

        assert result["article_id"] == article_id
        assert result["decision"] == "skip_selector"
        mock_dispatch.assert_called_once_with(
            article_id, run_id=None, next_status="researching"
        )

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_failure")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.circuit_breaker.get_breaker")
    @patch("services.llm.get_provider_by_id")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    @patch("tasks.pipeline._handle_stage_failure")
    def test_provider_error_triggers_stage_failure(
        self,
        mock_handle_failure,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_by_id,
        mock_get_breaker,
        mock_rec_stage,
        mock_rec_failure,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks import pipeline as pipeline_module
        from tasks.select import select_article

        mock_breaker = MagicMock()
        mock_breaker.can_execute.return_value = True
        mock_get_breaker.return_value = mock_breaker

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        rc.temperature = 0.0
        mock_get_rc.return_value = rc

        provider = MagicMock()
        provider.chat_structured.side_effect = ConnectionError("LLM down")

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        mock_handle_failure.return_value = False

        def mock_chain_fn(stage):
            return iter([(provider, "test-model", 1024, "ollama-local")])

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            with patch.object(pipeline_module, "get_provider_chain", mock_chain_fn):
                with pytest.raises(ConnectionError):
                    select_article.__wrapped__(article_id=article_id, run_id=None)

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_success")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.circuit_breaker.get_breaker")
    @patch("services.llm.get_provider_by_id")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    @patch("tasks.pipeline._transition_article_status")
    @pytest.mark.skip(reason="Mock integration issue - needs refactoring")
    def test_selected_score_equal_to_threshold_selects(
        self,
        mock_transition,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_by_id,
        mock_get_breaker,
        mock_rec_stage,
        mock_rec_success,
        mock_get_redis,
        app,
        create_article,
    ):
        """Score equal to min_score should select (>= comparison)."""
        from tasks import pipeline as pipeline_module
        from tasks.select import select_article

        mock_breaker = MagicMock()
        mock_breaker.can_execute.return_value = True
        mock_get_breaker.return_value = mock_breaker

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        rc.temperature = 0.0
        mock_get_rc.return_value = rc

        provider = MagicMock()
        result_obj = MagicMock()
        result_obj.configure_mock(
            selected=True,
            score=6,
            reason="exactly threshold",
            confidence="high",
            model_dump=lambda: {
                "selected": True,
                "score": 6,
                "reason": "exactly threshold",
            },
        )
        provider.chat_structured.return_value = result_obj

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        mock_transition.return_value = True

        def mock_chain_fn(stage):
            return iter([(provider, "test-model", 1024, "ollama-local")])

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            with patch.object(pipeline_module, "get_provider_chain", mock_chain_fn):
                result = select_article.__wrapped__(article_id=article_id, run_id=None)

        assert result["result"]["selected"] is True
        assert result["result"]["score"] == 6
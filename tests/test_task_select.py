"""Tests for tasks/select.py (select_article pipeline stage)."""

from unittest.mock import MagicMock, patch

import pytest


class TestSelectArticle:
    """Tests for select_article task through run_stage."""

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_success")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.llm.get_provider_for_role")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    def test_score_above_threshold_selects(
        self,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_prov,
        mock_rec_stage,
        mock_rec_success,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks.select import select_article

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        mock_get_rc.return_value = rc

        provider = MagicMock()
        result_obj = MagicMock()
        result_obj.selected = True
        result_obj.score = 8
        result_obj.reason = "important"
        result_obj.model_dump.return_value = {
            "selected": True,
            "score": 8,
            "reason": "important",
        }
        provider.chat_structured.return_value = result_obj
        mock_get_prov.return_value = (provider, "test-model", 1024)

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            result = select_article.__wrapped__(article_id=article_id, run_id=None)

        assert result["article_id"] == article_id
        assert result["result"]["selected"] is True
        assert result["result"]["score"] == 8

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_success")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.llm.get_provider_for_role")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    def test_score_below_threshold_skips(
        self,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_prov,
        mock_rec_stage,
        mock_rec_success,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks.select import select_article

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        mock_get_rc.return_value = rc

        provider = MagicMock()
        result_obj = MagicMock()
        result_obj.selected = False
        result_obj.score = 3
        result_obj.reason = "not newsworthy"
        result_obj.model_dump.return_value = {
            "selected": False,
            "score": 3,
            "reason": "not newsworthy",
        }
        provider.chat_structured.return_value = result_obj
        mock_get_prov.return_value = (provider, "test-model", 1024)

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
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
    @patch("services.llm.get_provider_for_role")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    @patch("tasks.pipeline._handle_stage_failure")
    def test_provider_error_triggers_stage_failure(
        self,
        mock_handle_failure,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_prov,
        mock_rec_stage,
        mock_rec_failure,
        mock_get_redis,
        app,
        create_article,
    ):
        from tasks.select import select_article

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        mock_get_rc.return_value = rc

        provider = MagicMock()
        provider.chat_structured.side_effect = ConnectionError("LLM down")
        mock_get_prov.return_value = (provider, "test-model", 1024)

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        mock_handle_failure.return_value = False

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            with pytest.raises(ConnectionError):
                select_article.__wrapped__(article_id=article_id, run_id=None)

    @patch("extensions.get_redis")
    @patch("services.llm.record_provider_success")
    @patch("services.pipeline_monitor.record_stage_result")
    @patch("services.llm.get_provider_for_role")
    @patch("schemas.pipeline.get_role_config")
    @patch("services.limiter.get_limiter")
    def test_selected_score_equal_to_threshold_selects(
        self,
        mock_limiter_fn,
        mock_get_rc,
        mock_get_prov,
        mock_rec_stage,
        mock_rec_success,
        mock_get_redis,
        app,
        create_article,
    ):
        """Score equal to min_score should select (>= comparison)."""
        from tasks.select import select_article

        rc = MagicMock()
        rc.enabled = True
        rc.min_score = 6
        rc.provider = "ollama-local"
        rc.model = "test-model"
        rc.concurrency = 2
        rc.timeout_seconds = 60
        rc.system_prompt = "select articles"
        mock_get_rc.return_value = rc

        provider = MagicMock()
        result_obj = MagicMock()
        result_obj.selected = True
        result_obj.score = 6
        result_obj.reason = "exactly threshold"
        result_obj.model_dump.return_value = {
            "selected": True,
            "score": 6,
            "reason": "exactly threshold",
        }
        provider.chat_structured.return_value = result_obj
        mock_get_prov.return_value = (provider, "test-model", 1024)

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mock_limiter_fn.return_value = limiter

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="pending")
            article_id = article.id
            result = select_article.__wrapped__(article_id=article_id, run_id=None)

        assert result["result"]["selected"] is True
        assert result["result"]["score"] == 6

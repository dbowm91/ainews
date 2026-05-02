"""End-to-end pipeline integration tests.

Tests the full pipeline flow: pending -> researching -> writing -> editing -> done.
Mocks LLM providers at each stage and verifies status transitions.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from models import Article


@pytest.mark.timeout(60)
class TestPipelineEndToEnd:
    """Test full pipeline: pending -> researching -> writing -> editing -> done."""

    def _mock_run_stage_deps(self):
        """Set up common mocks for all run_stage calls."""
        patches = {
            "get_role_config": patch("schemas.pipeline.get_role_config"),
            "get_provider_chain": patch("tasks.pipeline.get_provider_chain"),
            "record_success": patch("services.llm.record_provider_success"),
            "record_failure": patch("services.llm.record_provider_failure"),
            "get_limiter": patch("services.limiter.get_limiter"),
            "get_redis": patch("extensions.get_redis"),
            "get_config_with_default": patch("services.config_utils.get_config_with_default"),
        }
        mocks = {}
        for name, p in patches.items():
            mocks[name] = p.start()

        # Mock get_config_with_default to return appropriate values
        def _config_side_effect(key, default):
            config_values = {
                "MAX_STAGE_RETRIES": 3,
                "MAX_TOTAL_RETRIES": 10,
                "MAX_STAGE_FAILURES": 5,
                "PIPELINE_TIMEOUT_MINUTES": 60,
                "CIRCUIT_BREAKER_FAILURE_THRESHOLD": 5,
                "CIRCUIT_BREAKER_RECOVERY_SECONDS": 300,
            }
            return config_values.get(key, default)

        mocks["get_config_with_default"].side_effect = _config_side_effect

        class PatchesContext:
            def __init__(self, patches, mocks):
                self.patches = patches
                self.mocks = mocks

            def __enter__(self):
                return self.patches, self.mocks

            def __exit__(self, *args):
                for p in self.patches.values():
                    p.stop()

        return PatchesContext(patches, mocks)

    def _configure_rc(self, mocks, enabled=True, provider="ollama"):
        """Configure a standard RoleConfig mock."""
        rc = MagicMock()
        rc.enabled = enabled
        rc.provider = provider
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc
        return rc

    def _configure_limiter(self, mocks):
        """Configure limiter mock to allow execution."""
        limiter = MagicMock()
        limiter.acquire.return_value = True
        mocks["get_limiter"].return_value = limiter
        return limiter

    def _configure_redis(self, mocks):
        """Configure Redis mock for stage locking."""
        redis_mock = MagicMock()
        redis_mock.set.return_value = True
        redis_mock.get.return_value = b"task-e2e"
        redis_mock.hincrby.return_value = 1
        mocks["get_redis"].return_value = redis_mock
        return redis_mock

    def test_full_pipeline_select_through_edit(self, app, create_article):
        """Article progresses through all stages: select -> research -> write -> edit -> done."""
        with self._mock_run_stage_deps() as (patches, mocks):
            self._configure_rc(mocks)
            self._configure_limiter(mocks)
            self._configure_redis(mocks)

            # Mock provider chain to return a mock provider
            mock_provider = MagicMock()
            mocks["get_provider_chain"].return_value = [
                (mock_provider, "qwen3:8b", 2048, "ollama"),
            ]

            with app.app_context():
                article = create_article(
                    pipeline_status="pending",
                    original_title="Test E2E Article",
                    extracted_text="Long text content for the test article.",
                )
                db.session.commit()
                article_id = article.id

            task_self = MagicMock()
            task_self.request.id = "task-e2e"

            def select_work(article, provider, model, max_tokens):
                article.selector_result = {
                    "selected": True,
                    "score": 8,
                    "reason": "Good article",
                }
                article.pipeline_status = "researching"
                db.session.commit()
                return {"article_id": article.id, "result": article.selector_result}

            with app.app_context():
                from tasks.pipeline import run_stage

                result = run_stage("selector", article_id, select_work, task_self)
                assert result["article_id"] == article_id
                article = db.session.get(Article, article_id)
                assert article.pipeline_status == "researching"

            def research_work(article, provider, model, max_tokens):
                article.research_brief = json.dumps(
                    {
                        "source_summary": "Summary",
                        "key_claims": ["claim1"],
                        "direct_quotes": [],
                        "external_sources": [],
                    }
                )
                article.impact_score = 75
                article.pipeline_status = "writing"
                db.session.commit()
                return {"article_id": article.id}

            with app.app_context():
                result = run_stage("researcher", article_id, research_work, task_self)
                article = db.session.get(Article, article_id)
                assert article.pipeline_status == "writing"

            def write_work(article, provider, model, max_tokens):
                article.draft_article = json.dumps(
                    {
                        "headline": "Test E2E Article",
                        "tldr": "Summary",
                        "body": "Full body text",
                    }
                )
                article.pipeline_status = "editing"
                db.session.commit()
                return {"article_id": article.id}

            with app.app_context():
                result = run_stage("writer", article_id, write_work, task_self)
                article = db.session.get(Article, article_id)
                assert article.pipeline_status == "editing"

            def edit_work(article, provider, model, max_tokens):
                final = json.dumps(
                    {
                        "headline": "Test E2E Article",
                        "tldr": "Summary",
                        "body": "Edited body text",
                        "tags": ["test"],
                    }
                )
                article.final_article = final
                article.original_ai_article = final
                article.pipeline_status = "done"
                db.session.commit()
                return {"article_id": article.id}

            with app.app_context():
                with patch("tasks.pipeline._assign_tags"):
                    result = run_stage("editor", article_id, edit_work, task_self)
                    article = db.session.get(Article, article_id)
                    assert article.pipeline_status == "done"
                    assert article.final_article is not None
                    assert article.retry_count == 0

    def test_pipeline_degrades_on_max_retries(self, app, create_article):
        """Article degrades to next stage after MAX_STAGE_RETRIES failures."""
        with self._mock_run_stage_deps() as (patches, mocks):
            self._configure_rc(mocks)
            self._configure_limiter(mocks)
            self._configure_redis(mocks)

            # Mock provider chain
            mock_provider = MagicMock()
            mocks["get_provider_chain"].return_value = [
                (mock_provider, "qwen3:8b", 2048, "ollama"),
            ]

            with app.app_context():
                article = create_article(
                    pipeline_status="researching",
                    extracted_text="Content for testing",
                    original_url="https://example.com",
                )
                db.session.commit()
                article_id = article.id

            from constants import MAX_STAGE_RETRIES
            from tasks.pipeline import _handle_stage_failure

            with app.app_context():
                article = db.session.get(Article, article_id)

                for _i in range(MAX_STAGE_RETRIES - 1):
                    _handle_stage_failure(article, "research", Exception("fail"))
                    article = db.session.get(Article, article_id)
                    assert article.pipeline_status == "researching"

                # After max retries, should degrade to next stage
                _handle_stage_failure(article, "research", Exception("fail"))
                article = db.session.get(Article, article_id)
                # Should now be in writing stage (degraded from researching)
                assert article.pipeline_status == "writing"
                assert article.retry_count == 0

    def test_pipeline_fails_on_global_budget(self, app, create_article):
        """Article marked failed when total_retries exceeds MAX_TOTAL_RETRIES."""
        with self._mock_run_stage_deps() as (patches, mocks):
            self._configure_rc(mocks)
            self._configure_limiter(mocks)
            self._configure_redis(mocks)

            # Mock provider chain
            mock_provider = MagicMock()
            mocks["get_provider_chain"].return_value = [
                (mock_provider, "qwen3:8b", 2048, "ollama"),
            ]

            with app.app_context():
                article = create_article(
                    pipeline_status="writing",
                    extracted_text="Content",
                )
                article.total_retries = 9
                article.retry_count = 0
                db.session.commit()
                article_id = article.id

            from constants import MAX_TOTAL_RETRIES
            from tasks.pipeline import _handle_stage_failure

            with app.app_context():
                article = db.session.get(Article, article_id)
                _handle_stage_failure(article, "write", Exception("fail"))
                article = db.session.get(Article, article_id)
                assert article.total_retries == MAX_TOTAL_RETRIES
                assert article.pipeline_status == "failed"

    def test_stage_lock_prevents_duplicate_processing(self, app, create_article):
        """When stage lock is held by another task, run_stage returns skipped."""
        with self._mock_run_stage_deps() as (patches, mocks):
            self._configure_rc(mocks)
            self._configure_limiter(mocks)

            redis_mock = MagicMock()
            redis_mock.set.return_value = False
            mocks["get_redis"].return_value = redis_mock

            with app.app_context():
                article = create_article(pipeline_status="writing")
                db.session.commit()
                article_id = article.id

            task_self = MagicMock()
            task_self.request.id = "task-other"

            def work(article, provider, model, max_tokens):
                raise AssertionError("Should not be called when locked")

            with app.app_context():
                from tasks.pipeline import run_stage

                result = run_stage("writer", article_id, work, task_self)
                assert result["skipped"] is True
                assert result["reason"] == "stage_locked"

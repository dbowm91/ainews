"""Integration tests for the write pipeline stage."""

import json
from unittest.mock import MagicMock, patch


class TestWriteStage:
    """Test write stage execution with mocked LLM."""

    def _make_article_json(self):
        """Create a valid article JSON string."""
        return json.dumps(
            {
                "headline": "Test Headline",
                "tldr": "Short summary.",
                "why_it_matters": "This matters because...",
                "body": "Full article body text.",
                "key_points": ["Point 1", "Point 2"],
                "what_to_watch": "Watch for X.",
                "citations": [],
                "original_attribution": {
                    "source": "https://example.com",
                    "author": "Test Author",
                },
                "tags": ["ai"],
            }
        )

    def test_write_populates_draft(self, app, create_article):
        """Write stage should populate draft_article."""
        with app.app_context():
            article = create_article(pipeline_status="writing")
            article.research_brief = json.dumps({"source_summary": "Summary"})

            from tasks.pipeline import run_stage

            work_result = {
                "article_id": article.id,
                "draft_article": self._make_article_json(),
            }
            work_fn = MagicMock(return_value=work_result)

            patches, mocks = self._setup_mocks()
            try:
                result = run_stage("writer", article.id, work_fn, MagicMock())

                assert result == work_result
                work_fn.assert_called_once()
            finally:
                for p in patches.values():
                    p.stop()

    def test_write_degrades_to_edit(self, app, create_article):
        """When write fails, article should degrade to editing stage."""
        with app.app_context():
            article = create_article(
                pipeline_status="writing",
                original_title="Test Article",
                original_url="https://example.com",
                extracted_text="Some extracted content.",
            )
            article.original_author = "Author"

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "write")

            assert article.pipeline_status == "editing"
            assert article.draft_article is not None

            draft = json.loads(article.draft_article)
            assert draft["headline"] == "Test Article"
            assert draft["body"] != ""

    def test_write_fallback_uses_extracted_text(self, app, create_article):
        """Fallback article should use extracted text as body."""
        with app.app_context():
            article = create_article(
                pipeline_status="writing",
                original_title="My Title",
                original_url="https://example.com",
                extracted_text="Full extracted text of the article.",
            )
            article.original_author = "Author"

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "write")

            draft = json.loads(article.draft_article)
            assert draft["body"] == "Full extracted text of the article."

    def test_write_fallback_preserves_attribution(self, app, create_article):
        """Fallback article should include original attribution."""
        with app.app_context():
            article = create_article(
                pipeline_status="writing",
                original_title="Title",
                original_url="https://source.com/article",
                extracted_text="Text",
            )
            article.original_author = "Jane Doe"

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "write")

            draft = json.loads(article.draft_article)
            assert (
                draft["original_attribution"]["source"] == "https://source.com/article"
            )
            assert draft["original_attribution"]["author"] == "Jane Doe"

    @staticmethod
    def _setup_mocks():
        patches = {
            "Article": patch("models.Article"),
            "db": patch("extensions.db"),
            "get_role_config": patch("schemas.pipeline.get_role_config"),
            "get_provider_for_role": patch("services.llm.get_provider_for_role"),
            "record_success": patch("services.llm.record_provider_success"),
            "record_failure": patch("services.llm.record_provider_failure"),
            "get_limiter": patch("services.limiter.get_limiter"),
        }
        mocks = {}
        for name, p in patches.items():
            mocks[name] = p.start()

        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        article = MagicMock()
        article.retry_count = 0
        mocks["db"].session.get.return_value = article

        mocks["get_provider_for_role"].return_value = (
            MagicMock(),
            "qwen3:8b",
            2048,
        )

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mocks["get_limiter"].return_value = limiter

        return patches, mocks

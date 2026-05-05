"""Tests for tasks/edit.py - Edit pipeline stage task."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch



class TestFormatTopicNotes:
    """Tests for _format_topic_notes function."""

    def test_returns_no_topic_notes_when_empty(self):
        """Returns '(no topic notes)' for empty dict."""
        from tasks.edit import _format_topic_notes

        result = _format_topic_notes({})
        assert result == "(no topic notes)"

    def test_returns_no_topic_notes_when_none(self):
        """Returns '(no topic notes)' for None."""
        from tasks.edit import _format_topic_notes

        result = _format_topic_notes(None)
        assert result == "(no topic notes)"

    def test_formats_single_topic_with_notes(self):
        """Formats single topic with its notes."""
        from tasks.edit import _format_topic_notes

        result = _format_topic_notes({"AI": ["Note 1", "Note 2"]})
        assert "Topic: AI" in result
        assert "  - Note 1" in result
        assert "  - Note 2" in result

    def test_formats_multiple_topics(self):
        """Formats multiple topics."""
        from tasks.edit import _format_topic_notes

        result = _format_topic_notes({
            "AI": ["AI note"],
            "Security": ["Sec note 1", "Sec note 2"],
        })
        assert "Topic: AI" in result
        assert "Topic: Security" in result
        assert "AI note" in result
        assert "Sec note 1" in result


class TestFormatRelatedArticles:
    """Tests for _format_related_articles function."""

    def test_returns_no_related_articles_when_empty(self):
        """Returns '(no related articles)' for empty list."""
        from tasks.edit import _format_related_articles

        result = _format_related_articles([])
        assert result == "(no related articles)"

    def test_returns_no_related_articles_when_none(self):
        """Returns '(no related articles)' for None."""
        from tasks.edit import _format_related_articles

        result = _format_related_articles(None)
        assert result == "(no related articles)"

    def test_formats_article_with_title_and_category(self):
        """Formats article with title and category."""
        from tasks.edit import _format_related_articles

        articles = [{"title": "Test Article", "category": "AI"}]
        result = _format_related_articles(articles)
        assert "- Test Article (AI)" in result

    def test_formats_article_with_snippet(self):
        """Formats article with snippet truncated to 200 chars."""
        from tasks.edit import _format_related_articles

        articles = [{
            "title": "Test",
            "category": "AI",
            "snippet": "A" * 300,
        }]
        result = _format_related_articles(articles)
        assert "A" * 200 in result
        assert ("A" * 300) not in result

    def test_handles_missing_title(self):
        """Uses 'Unknown' for missing title."""
        from tasks.edit import _format_related_articles

        articles = [{"category": "AI"}]
        result = _format_related_articles(articles)
        assert "- Unknown (AI)" in result

    def test_handles_missing_category(self):
        """Uses 'general' for missing category."""
        from tasks.edit import _format_related_articles

        articles = [{"title": "Test"}]
        result = _format_related_articles(articles)
        assert "- Test (general)" in result


class TestTagCache:
    """Tests for tag cache functions."""

    def test_clear_tag_cache_resets_cache(self, app):
        """clear_tag_cache resets the global cache."""
        with app.app_context():
            import tasks.edit as edit_module
            edit_module._TAG_CACHE = ["cached_tag"]
            edit_module._TAG_CACHE_TIME = 9999999999

            edit_module.clear_tag_cache()

            assert edit_module._TAG_CACHE is None
            assert edit_module._TAG_CACHE_TIME == 0

    def test_get_cached_tag_names_returns_cached(self, app, create_tag, monkeypatch):
        """Returns cached tags if within TTL."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            import tasks.edit as edit_module
            import time

            edit_module._TAG_CACHE = ["cached_tag_1", "cached_tag_2"]
            edit_module._TAG_CACHE_TIME = time.time()

            result = edit_module._get_cached_tag_names()

            assert result == ["cached_tag_1", "cached_tag_2"]

    def test_get_cached_tag_names_fetches_fresh(self, app, create_tag, monkeypatch):
        """Fetches fresh tags when cache is stale."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            import tasks.edit as edit_module

            tag = create_tag(name="fresh_tag")

            edit_module._TAG_CACHE = None
            edit_module._TAG_CACHE_TIME = 0

            result = edit_module._get_cached_tag_names()

            assert "fresh_tag" in result

    def test_get_cached_tag_names_returns_cached_if_expired(self, app, create_tag, monkeypatch):
        """Returns cached tags if cache has expired."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            import tasks.edit as edit_module
            import time

            tag = create_tag(name="fresh_tag")

            edit_module._TAG_CACHE = ["old_cached_tag"]
            edit_module._TAG_CACHE_TIME = time.time() - 400

            result = edit_module._get_cached_tag_names()

            assert "fresh_tag" in result
            assert "old_cached_tag" not in result or len(result) > 1


class TestGatherEditorContext:
    """Tests for _gather_editor_context function."""

    def test_returns_empty_when_no_topics(self, app):
        """Returns empty string when article has no topics."""
        with app.app_context():
            from tasks.edit import _gather_editor_context

            article = MagicMock()
            article.topics = []
            article.draft_article = '{"headline": "Test"}'

            result = _gather_editor_context(article, [])
            assert result == ""


class TestHandleValidationAndRouting:
    """Tests for _handle_validation_and_routing function."""

    def test_routes_to_review_on_validation_failure(self, app, create_article, monkeypatch):
        """Routes to REVIEW when validation fails."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.edit import _handle_validation_and_routing
            from services.article_validation import ValidationError

            article = create_article(pipeline_status="editing")
            article.final_article = '{"headline": "Test"}'

            with patch("services.article_validation.validate_and_raise") as mock_validate:
                mock_validate.side_effect = ValidationError("Invalid content")

                from extensions import db
                with patch.object(db, "session"):
                    result = _handle_validation_and_routing(article, db, run_id=None)

                    assert result == {"article_id": article.id, "status": "review"}


class TestPostFinalizeArticle:
    """Tests for _post_finalize_article function."""

    def test_sets_article_to_done(self, app, create_article, monkeypatch):
        """Sets article pipeline_status to DONE."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.edit import _post_finalize_article
            from constants import PipelineStatus

            article = create_article(pipeline_status="editing")
            article.crawled_at = None
            article.final_article = '{"headline": "Test"}'

            with patch("services.metrics.get_metrics") as mock_metrics:
                mock_metrics.return_value.histogram_observe = MagicMock()

                with patch("services.trend_memory.propose_trend_memory"):
                    with patch("services.webhooks.trigger_event"):
                        _post_finalize_article(article, run_id=None)

                        assert article.pipeline_status == PipelineStatus.DONE

    def test_records_sla_duration_if_crawled(self, app, create_article, monkeypatch):
        """Records E2E duration if article was crawled."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.edit import _post_finalize_article

            article = create_article(pipeline_status="editing")
            article.crawled_at = datetime.now(timezone.utc).replace(tzinfo=None)
            article.final_article = '{"headline": "Test"}'

            with patch("services.metrics.get_metrics") as mock_metrics:
                mock_instance = MagicMock()
                mock_metrics.return_value = mock_instance

                with patch("services.trend_memory.propose_trend_memory"):
                    with patch("services.webhooks.trigger_event"):
                        _post_finalize_article(article, run_id=None)

                        mock_instance.histogram_observe.assert_called()


class TestClearTagCache:
    """Tests for clear_tag_cache function."""

    def test_clears_global_tag_cache(self, app):
        """Clears the global _TAG_CACHE and resets _TAG_CACHE_TIME."""
        with app.app_context():
            import tasks.edit as edit_module

            edit_module._TAG_CACHE = ["some_tag"]
            edit_module._TAG_CACHE_TIME = 12345

            edit_module.clear_tag_cache()

            assert edit_module._TAG_CACHE is None
            assert edit_module._TAG_CACHE_TIME == 0
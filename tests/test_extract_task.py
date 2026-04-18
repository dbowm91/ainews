"""Tests for tasks/extract.py process_item Celery task."""

from unittest.mock import MagicMock, patch


def _call_process_item(**overrides):
    """Call process_item.__wrapped__ with default args."""
    from tasks.extract import process_item

    defaults = {
        "source_key": "src-1",
        "source_name": "Test Source",
        "source_type": "rss",
        "external_id": "ext-1",
        "title": "Test Article",
        "url": "https://example.com/article",
        "author": "Author",
        "published_at": None,
        "text_content": "Short text",
        "raw_score": 0,
        "raw_metadata": {},
        "topics": ["ai"],
        "min_content_length": None,
        "run_id": None,
    }
    defaults.update(overrides)
    return process_item.__wrapped__(**defaults)


class TestProcessItem:
    """Tests for the extract process_item task."""

    @patch("tasks.select.select_article")
    @patch("services.crawling.get_or_create_source")
    @patch("tasks.extract._find_duplicate_article")
    @patch("services.content_extractor.extract_article")
    def test_happy_path(
        self, mock_extract, mock_dedup, mock_get_source, mock_select, app
    ):
        """Happy path: extracts article, creates DB record, dispatches to select."""
        mock_dedup.return_value = None

        extraction = MagicMock()
        extraction.text = "Extracted long article text " * 20
        extraction.status.value = "success"
        mock_extract.return_value = extraction

        with app.app_context():
            from models import Source
            from extensions import db

            source = Source(
                source_key="src-1", name="Test Source", source_type="rss", feed_url=""
            )
            db.session.add(source)
            db.session.commit()
            mock_get_source.return_value = source

            result = _call_process_item(text_content="short", min_content_length=200)

        assert "article_id" in result
        assert result.get("duplicate") is not True
        mock_select.delay.assert_called_once()

    @patch("tasks.select.select_article")
    @patch("services.crawling.get_or_create_source")
    @patch("tasks.extract._find_duplicate_article")
    @patch("services.content_extractor.extract_article")
    def test_extraction_failure_uses_fallback(
        self, mock_extract, mock_dedup, mock_get_source, mock_select, app
    ):
        """When extraction fails, falls back to text_content or title."""
        mock_dedup.return_value = None
        mock_extract.side_effect = Exception("extraction failed")

        with app.app_context():
            from models import Source
            from extensions import db

            source = Source(
                source_key="src-1", name="Test Source", source_type="rss", feed_url=""
            )
            db.session.add(source)
            db.session.commit()
            mock_get_source.return_value = source

            result = _call_process_item(text_content="fallback text content")

        assert "article_id" in result
        mock_select.delay.assert_called_once()

    @patch("tasks.select.select_article")
    @patch("services.crawling.get_or_create_source")
    @patch("tasks.extract._find_duplicate_article")
    @patch("services.content_extractor.extract_article")
    def test_duplicate_returns_existing(
        self, mock_extract, mock_dedup, mock_get_source, mock_select, app
    ):
        """Duplicate article returns existing ID without creating new article."""
        mock_article = MagicMock()
        mock_article.id = 42
        mock_article.original_url = "https://example.com/other"
        mock_dedup.return_value = mock_article

        with app.app_context():
            result = _call_process_item()

        assert result["article_id"] == 42
        assert result["duplicate"] is True
        mock_select.delay.assert_not_called()

    @patch("tasks.select.select_article")
    @patch("services.crawling.get_or_create_source")
    @patch("tasks.extract._find_duplicate_article")
    def test_no_url_skips_extraction(
        self, mock_dedup, mock_get_source, mock_select, app
    ):
        """No URL means no extraction attempt — uses text_content directly."""
        mock_dedup.return_value = None

        with app.app_context():
            from models import Source
            from extensions import db

            source = Source(
                source_key="src-1", name="Test Source", source_type="rss", feed_url=""
            )
            db.session.add(source)
            db.session.commit()
            mock_get_source.return_value = source

            result = _call_process_item(url=None, text_content="text from feed")

        assert "article_id" in result
        mock_select.delay.assert_called_once()

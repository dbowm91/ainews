"""Tests for content extraction service."""

import pytest
from unittest.mock import patch, MagicMock


class TestContentExtractor:
    """Test content extraction functionality."""

    def test_extraction_status_enum(self):
        from services.content_extractor import ExtractionStatus
        assert ExtractionStatus.SUCCESS.value == "success"
        assert ExtractionStatus.PAYWALL.value == "paywall"
        assert ExtractionStatus.EMPTY.value == "empty"
        assert ExtractionStatus.FETCH_ERROR.value == "fetch_error"

    def test_extraction_result_dataclass(self):
        from services.content_extractor import ExtractionResult, ExtractionStatus
        result = ExtractionResult(
            url="https://example.com",
            text="Some text content",
            title="Test Title",
            author="Test Author",
            status=ExtractionStatus.SUCCESS,
            content_length=18,
        )
        assert result.url == "https://example.com"
        assert result.text == "Some text content"
        assert result.title == "Test Title"
        assert result.author == "Test Author"
        assert result.status == ExtractionStatus.SUCCESS
        assert result.content_length == 18

    def test_detect_paywall_positive(self):
        from services.content_extractor import _detect_paywall
        html = "<html><body><p>Subscribe to continue reading</p></body></html>"
        assert _detect_paywall(html) is True

    def test_detect_paywall_case_insensitive(self):
        from services.content_extractor import _detect_paywall
        html = "<html><body><p>SUBSCRIBE TO CONTINUE</p></body></html>"
        assert _detect_paywall(html) is True

    def test_detect_paywall_negative(self):
        from services.content_extractor import _detect_paywall
        html = "<html><body><p>This is free content</p></body></html>"
        assert _detect_paywall(html) is False

    @patch('services.content_extractor.trafilatura.fetch_url')
    def test_extract_article_fetch_error(self, mock_fetch):
        from services.content_extractor import extract_article, ExtractionStatus
        mock_fetch.side_effect = Exception("Network error")
        result = extract_article("https://example.com/article")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None

    @patch('services.content_extractor.trafilatura.fetch_url')
    def test_extract_article_empty_response(self, mock_fetch):
        from services.content_extractor import extract_article, ExtractionStatus
        mock_fetch.return_value = None
        result = extract_article("https://example.com/article")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None

    @patch('services.content_extractor.trafilatura.bare_extraction')
    @patch('services.content_extractor.trafilatura.fetch_url')
    def test_extract_article_success_trafilatura(self, mock_fetch, mock_extract):
        from services.content_extractor import extract_article, ExtractionStatus
        mock_fetch.return_value = "<html><body>Article content</body></html>"
        mock_extract.return_value = {
            "text": "This is a long article text that should be at least 200 characters long. " * 5,
            "title": "Test Article",
            "author": "Test Author",
        }
        result = extract_article("https://example.com/article")
        assert result.status == ExtractionStatus.SUCCESS
        assert result.title == "Test Article"
        assert result.author == "Test Author"
        assert len(result.text) >= 200

    @patch('services.content_extractor.trafilatura.bare_extraction')
    @patch('services.content_extractor.trafilatura.fetch_url')
    def test_extract_article_paywall_detected(self, mock_fetch, mock_extract):
        from services.content_extractor import extract_article, ExtractionStatus
        mock_fetch.return_value = "<html><body>Subscribe to continue reading</body></html>"
        mock_extract.return_value = {
            "text": "This is a long article text that should be at least 200 characters long. " * 5,
            "title": "Test Article",
            "author": "Test Author",
        }
        result = extract_article("https://example.com/article")
        assert result.status == ExtractionStatus.PAYWALL

    @patch('services.content_extractor.trafilatura.bare_extraction')
    @patch('services.content_extractor.trafilatura.fetch_url')
    def test_extract_article_fallback_to_readability(self, mock_fetch, mock_extract):
        from services.content_extractor import extract_article, ExtractionStatus
        mock_fetch.return_value = "<html><body>Short content</body></html>"
        mock_extract.return_value = {"text": "Short"}  # Too short for trafilatura

        # Mock readability to return longer content
        with patch('services.content_extractor.Document') as mock_doc_class:
            mock_doc = MagicMock()
            mock_doc.title.return_value = "Fallback Title"
            mock_doc.summary.return_value = "<p>" + "Fallback content. " * 30 + "</p>"
            mock_doc_class.return_value = mock_doc

            result = extract_article("https://example.com/article")
            assert result.status == ExtractionStatus.SUCCESS
            assert result.title == "Fallback Title"
            assert len(result.text) >= 200

    @patch('services.content_extractor.trafilatura.bare_extraction')
    @patch('services.content_extractor.trafilatura.fetch_url')
    def test_extract_article_empty_when_all_fail(self, mock_fetch, mock_extract):
        from services.content_extractor import extract_article, ExtractionStatus
        mock_fetch.return_value = "<html><body>Short</body></html>"
        mock_extract.return_value = {"text": "Short"}  # Too short

        with patch('services.content_extractor.Document') as mock_doc_class:
            mock_doc = MagicMock()
            mock_doc.title.return_value = "Title"
            mock_doc.summary.return_value = "<p>Short</p>"  # Too short
            mock_doc_class.return_value = mock_doc

            result = extract_article("https://example.com/article")
            assert result.status == ExtractionStatus.EMPTY
            assert result.text is None

"""Tests for the RSS service."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestGenerateRSSFeed:
    """Test RSS feed generation."""

    def _mock_article(
        self,
        title="Test Article",
        tldr="TL;DR text",
        category="ai",
        author="John Doe",
        published_at=None,
    ):
        class MockArticle:
            pass

        article = MockArticle()
        article.id = 1
        article.public_id = "public-story-1"
        article.original_title = title
        article.final_article = json.dumps({"headline": title, "tldr": tldr})
        article.category = category
        article.original_author = author
        article.original_published_at = published_at
        article.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        return article

    def test_valid_xml_structure(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article()]
        feed = generate_rss_feed(
            articles,
            title="Test Feed",
            description="Test description",
            site_url="https://example.com",
        )

        assert '<?xml version="1.0" encoding="UTF-8"?>' in feed
        assert '<rss version="2.0">' in feed
        assert "<channel>" in feed
        assert "</channel>" in feed
        assert "</rss>" in feed

    def test_required_channel_fields(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article()]
        feed = generate_rss_feed(
            articles,
            title="Test Feed",
            description="Test description",
            site_url="https://example.com",
        )

        assert "<title>Test Feed</title>" in feed
        assert "<description>Test description</description>" in feed
        assert "<language>en-us</language>" in feed
        assert "<lastBuildDate>" in feed

    def test_article_item_included(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article(title="Test Title")]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert "<item>" in feed
        assert "</item>" in feed
        assert "<title>Test Title</title>" in feed

    def test_article_link_and_guid(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article()]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert "https://example.com/article/public-story-1" in feed
        assert "<guid>" in feed

    def test_description_from_tldr(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article(tldr="Summary text")]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert "<description>Summary text</description>" in feed

    def test_category_included(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article(category="security")]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert "<category>security</category>" in feed

    def test_author_included(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article(author="Jane Doe")]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert "<author>Jane Doe</author>" in feed

    def test_pubdate_from_published_at(self):
        from services.rss import generate_rss_feed

        articles = [
            self._mock_article(
                published_at=datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
            )
        ]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert "<pubDate>" in feed

    def test_multiple_articles(self):
        from services.rss import generate_rss_feed

        articles = [self._mock_article() for _ in range(3)]
        feed = generate_rss_feed(
            articles,
            title="Feed",
            description="Desc",
            site_url="https://example.com",
        )

        assert feed.count("<item>") == 3


class TestGenerateSitemap:
    """Test sitemap generation."""

    def _mock_article(self, created_at=None):
        class MockArticle:
            pass

        article = MockArticle()
        article.id = 1
        article.public_id = "public-story-1"
        article.created_at = created_at or datetime(2024, 1, 15)
        return article

    def test_valid_xml_structure(self):
        from services.rss import generate_sitemap

        sitemap = generate_sitemap([], site_url="https://example.com")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in sitemap
        assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in sitemap
        assert "</urlset>" in sitemap

    def test_homepage_included(self):
        from services.rss import generate_sitemap

        sitemap = generate_sitemap([], site_url="https://example.com")

        assert "<loc>https://example.com</loc>" in sitemap
        assert "<priority>1.0</priority>" in sitemap

    @patch("schemas.topic.load_topics")
    def test_topic_pages_included(self, mock_load_topics):
        from services.rss import generate_sitemap

        mock_topics = MagicMock()
        mock_topics.topics = {"ai": MagicMock(), "security": MagicMock()}
        mock_load_topics.return_value = mock_topics

        sitemap = generate_sitemap([], site_url="https://example.com")

        assert "https://example.com/topic/ai" in sitemap
        assert "https://example.com/topic/security" in sitemap

    def test_article_urls_included(self):
        from services.rss import generate_sitemap

        articles = [self._mock_article()]
        sitemap = generate_sitemap(articles, site_url="https://example.com")

        assert "https://example.com/article/public-story-1" in sitemap

    def test_article_lastmod(self):
        from services.rss import generate_sitemap

        articles = [self._mock_article(created_at=datetime(2024, 3, 15))]
        sitemap = generate_sitemap(articles, site_url="https://example.com")

        assert "<lastmod>2024-03-15</lastmod>" in sitemap


class TestFormatDate:
    """Test date formatting for RSS."""

    def test_naive_datetime_converted_to_utc(self):
        from services.rss import _format_date

        dt = datetime(2024, 3, 15, 12, 0)
        result = _format_date(dt)

        assert "GMT" in result
        assert "2024" in result

    def test_aware_datetime_uses_utc(self):
        from services.rss import _format_date

        dt = datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
        result = _format_date(dt)

        assert "GMT" in result

    def test_rfc2822_format(self):
        from services.rss import _format_date

        dt = datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
        result = _format_date(dt)

        assert "Fri, 15 Mar 2024" in result
        assert "12:00:00" in result


class TestParseFinalArticle:
    """Test article parsing for RSS."""

    def test_extracts_headline_and_tldr(self):
        from services.rss import _parse_final_article

        class MockArticle:
            final_article = json.dumps(
                {"headline": "Test Headline", "tldr": "Summary text"}
            )
            original_title = "Original"

        headline, tldr = _parse_final_article(MockArticle())

        assert headline == "Test Headline"
        assert tldr == "Summary text"

    def test_fallback_to_original_title(self):
        from services.rss import _parse_final_article

        class MockArticle:
            final_article = None
            original_title = "Original Title"
            summary = None

        headline, tldr = _parse_final_article(MockArticle())

        assert headline == "Original Title"

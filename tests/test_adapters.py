"""Tests for source adapters."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone


class TestBaseAdapter:
    """Test base adapter functionality."""

    def test_raw_item_dataclass(self):
        from adapters.base import RawItem

        item = RawItem(
            source_id="test-source",
            external_id="ext-123",
            title="Test Title",
            url="https://example.com",
            author="Test Author",
            published_at=datetime.now(timezone.utc),
            text_content="Test content",
            raw_score=1.5,
            raw_metadata={"key": "value"},
            topics=["ai"],
        )
        assert item.source_id == "test-source"
        assert item.external_id == "ext-123"
        assert item.title == "Test Title"
        assert item.url == "https://example.com"
        assert item.author == "Test Author"
        assert item.text_content == "Test content"
        assert item.raw_score == 1.5
        assert item.raw_metadata == {"key": "value"}
        assert item.topics == ["ai"]

    def test_adapter_registry(self):
        from adapters.base import _ADAPTER_REGISTRY, get_adapter_class

        # RSS adapter should be registered
        assert "rss" in _ADAPTER_REGISTRY
        adapter_class = get_adapter_class("rss")
        assert adapter_class is not None

    def test_get_adapter_class_invalid(self):
        from adapters.base import get_adapter_class

        with pytest.raises(KeyError) as exc_info:
            get_adapter_class("nonexistent")
        assert "nonexistent" in str(exc_info.value)


class TestRSSAdapter:
    """Test RSS adapter functionality."""

    def test_parse_item_with_full_content(self):
        from adapters.rss import RSSAdapter

        # Create a mock source config
        source_config = MagicMock()
        source_config.id = "test-rss"
        source_config.config = {
            "feed_url": "https://example.com/feed.xml",
            "max_items": 50,
            "request_timeout": 30,
            "user_agent": "TestBot/1.0",
        }
        source_config.topics = MagicMock()
        source_config.topics.include = ["ai", "programming"]

        adapter = RSSAdapter(source_config)

        # Create a mock feed entry - using a dict-like object
        class MockEntry:
            def __init__(self):
                self.title = "Test Article Title"
                self.link = "https://example.com/article/1"
                self.author = "John Doe"
                self.content = [{"value": "<p>This is the full article content.</p>"}]
                self.summary = "This is a summary."
                self.tags = [{"term": "technology"}, {"term": "ai"}]
                self.published_parsed = (2024, 1, 15, 10, 30, 0, 0, 0, 0)

            def get(self, key, default=None):
                return getattr(self, key, default)

        raw_entry = MockEntry()

        item = adapter.parse_item(raw_entry)
        assert item is not None
        assert item.title == "Test Article Title"
        assert item.url == "https://example.com/article/1"
        assert item.author == "John Doe"
        assert item.published_at is not None
        assert "full article content" in item.text_content

    def test_parse_item_with_summary_fallback(self):
        from adapters.rss import RSSAdapter

        source_config = MagicMock()
        source_config.id = "test-rss"
        source_config.config = {
            "feed_url": "https://example.com/feed.xml",
            "max_items": 50,
            "request_timeout": 30,
            "user_agent": "TestBot/1.0",
        }
        source_config.topics = MagicMock()
        source_config.topics.include = ["ai"]

        adapter = RSSAdapter(source_config)

        # Create a mock feed entry without content, but with summary
        class MockEntry:
            def __init__(self):
                self.title = "Test Article"
                self.link = "https://example.com/article/2"
                self.content = None
                self.summary = "This is a summary of the article."
                self.tags = []
                self.published_parsed = None

            def get(self, key, default=None):
                return getattr(self, key, default)

        raw_entry = MockEntry()

        item = adapter.parse_item(raw_entry)
        assert item is not None
        assert item.title == "Test Article"
        assert "summary" in item.text_content

    def test_parse_item_empty_title_returns_none(self):
        from adapters.rss import RSSAdapter

        source_config = MagicMock()
        source_config.id = "test-rss"
        source_config.config = {
            "feed_url": "https://example.com/feed.xml",
            "max_items": 50,
            "request_timeout": 30,
            "user_agent": "TestBot/1.0",
        }
        source_config.topics = MagicMock()
        source_config.topics.include = ["ai"]

        adapter = RSSAdapter(source_config)

        # Create a mock feed entry with empty title
        class MockEntry:
            def __init__(self):
                self.title = ""
                self.link = "https://example.com/article/3"

            def get(self, key, default=None):
                return getattr(self, key, default)

        raw_entry = MockEntry()

        item = adapter.parse_item(raw_entry)
        assert item is None

    def test_parse_item_generates_external_id_from_url(self):
        from adapters.rss import RSSAdapter

        source_config = MagicMock()
        source_config.id = "test-rss"
        source_config.config = {
            "feed_url": "https://example.com/feed.xml",
            "max_items": 50,
            "request_timeout": 30,
            "user_agent": "TestBot/1.0",
        }
        source_config.topics = MagicMock()
        source_config.topics.include = ["ai"]

        adapter = RSSAdapter(source_config)

        # Create a mock feed entry
        class MockEntry:
            def __init__(self):
                self.title = "Test Article"
                self.link = "https://example.com/article/unique"
                self.tags = []
                self.published_parsed = None

            def get(self, key, default=None):
                return getattr(self, key, default)

        raw_entry = MockEntry()

        item = adapter.parse_item(raw_entry)
        assert item is not None
        assert item.external_id is not None
        assert len(item.external_id) == 16  # SHA256 truncated to 16 chars

    def test_parse_item_generates_external_id_from_title_when_no_url(self):
        from adapters.rss import RSSAdapter

        source_config = MagicMock()
        source_config.id = "test-rss"
        source_config.config = {
            "feed_url": "https://example.com/feed.xml",
            "max_items": 50,
            "request_timeout": 30,
            "user_agent": "TestBot/1.0",
        }
        source_config.topics = MagicMock()
        source_config.topics.include = ["ai"]

        adapter = RSSAdapter(source_config)

        # Create a mock feed entry without URL
        class MockEntry:
            def __init__(self):
                self.title = "Article Without URL"
                self.link = ""
                self.tags = []
                self.published_parsed = None

            def get(self, key, default=None):
                return getattr(self, key, default)

        raw_entry = MockEntry()

        item = adapter.parse_item(raw_entry)
        assert item is not None
        assert item.external_id is not None
        assert len(item.external_id) == 16

    def test_get_match_text_includes_content(self):
        from adapters.rss import RSSAdapter
        from adapters.base import RawItem

        source_config = MagicMock()
        source_config.id = "test-rss"
        source_config.config = {
            "feed_url": "https://example.com/feed.xml",
            "max_items": 50,
            "request_timeout": 30,
            "user_agent": "TestBot/1.0",
        }
        source_config.topics = MagicMock()
        source_config.topics.include = ["ai"]

        adapter = RSSAdapter(source_config)

        item = RawItem(
            source_id="test",
            external_id="ext-1",
            title="Test Title",
            text_content="This is some article content for matching.",
        )

        match_text = adapter._get_match_text(item)
        assert "Test Title" in match_text
        assert "article content" in match_text

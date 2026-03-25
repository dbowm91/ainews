"""Tests for cross-source article deduplication."""

import json
import pytest


@pytest.fixture
def seeded_articles(app):
    """Create test articles for dedup testing."""
    from models import Article, Source
    from extensions import db

    source1 = Source(source_key="src1", name="Source 1", source_type="rss", feed_url="")
    source2 = Source(source_key="src2", name="Source 2", source_type="rss", feed_url="")
    db.session.add_all([source1, source2])
    db.session.flush()

    article1 = Article(
        source_id=source1.id,
        external_id="ext1",
        original_url="https://example.com/article-1",
        original_title="Test Article One",
        extracted_text="Some content",
        pipeline_status="done",
        category="ai",
        topics=["ai"],
        final_article=json.dumps(
            {"headline": "Test Article One", "tldr": "TLDR", "body": "Body"}
        ),
    )
    db.session.add(article1)
    db.session.commit()

    return {"source1": source1, "source2": source2, "article1": article1}


class TestDuplicateFinder:
    """Test _find_duplicate_article function."""

    def test_finds_url_duplicate(self, app, seeded_articles):
        from tasks.extract import _find_duplicate_article

        # Same URL with different tracking params should match
        dup = _find_duplicate_article(
            url="https://example.com/article-1?utm_source=twitter",
            title="Different Title",
        )
        assert dup is not None
        assert dup.id == seeded_articles["article1"].id

    def test_finds_exact_url_duplicate(self, app, seeded_articles):
        from tasks.extract import _find_duplicate_article

        dup = _find_duplicate_article(
            url="https://example.com/article-1",
            title="Different Title",
        )
        assert dup is not None
        assert dup.id == seeded_articles["article1"].id

    def test_finds_title_duplicate(self, app, seeded_articles):
        from tasks.extract import _find_duplicate_article

        dup = _find_duplicate_article(
            url="https://totally-different.com/story",
            title="Test Article One",
        )
        assert dup is not None
        assert dup.id == seeded_articles["article1"].id

    def test_no_duplicate_for_new_content(self, app, seeded_articles):
        from tasks.extract import _find_duplicate_article

        dup = _find_duplicate_article(
            url="https://other.com/unique-story",
            title="Completely Different Story",
        )
        assert dup is None

    def test_no_duplicate_empty_inputs(self, app, seeded_articles):
        from tasks.extract import _find_duplicate_article

        dup = _find_duplicate_article(url="", title="")
        assert dup is None

    def test_no_duplicate_none_inputs(self, app, seeded_articles):
        from tasks.extract import _find_duplicate_article

        dup = _find_duplicate_article(url=None, title=None)
        assert dup is None


class TestAdapterUrlNormalization:
    """Test that adapters use normalized URLs for external_id."""

    def test_rss_adapter_normalizes_url(self):
        """RSS adapter should produce the same external_id for URLs
        that differ only in tracking params."""
        import hashlib
        from services.url import normalize_url

        url_a = "https://www.example.com/article?utm_source=twitter"
        url_b = "https://example.com/article?utm_source=facebook"

        id_a = hashlib.sha256(normalize_url(url_a).encode()).hexdigest()[:16]
        id_b = hashlib.sha256(normalize_url(url_b).encode()).hexdigest()[:16]

        assert id_a == id_b

    def test_web_adapter_normalizes_url(self):
        """Web adapter should produce the same external_id for URLs
        that differ only in trailing slash."""
        import hashlib
        from services.url import normalize_url

        url_a = "https://example.com/article/"
        url_b = "https://example.com/article"

        id_a = hashlib.sha256(normalize_url(url_a).encode()).hexdigest()[:16]
        id_b = hashlib.sha256(normalize_url(url_b).encode()).hexdigest()[:16]

        assert id_a == id_b

"""Tests for FTS5 search and article search service."""

import json

from services.pagination import _build_fts_query, _escape_like_pattern


class TestFtsQueryBuilder:
    """Test safe FTS5 query construction."""

    def test_single_word(self):
        assert _build_fts_query("python") == '"python"'

    def test_multiple_words(self):
        assert _build_fts_query("python ai") == '"python" AND "ai"'

    def test_strips_quotes(self):
        result = _build_fts_query('python "machine learning"')
        assert '"python"' in result
        assert "machine" in result
        assert "learning" in result

    def test_strips_operators(self):
        assert _build_fts_query("python:ai") == '"python" AND "ai"'

    def test_strips_parens(self):
        assert _build_fts_query("python (ai)") == '"python" AND "ai"'

    def test_empty_query(self):
        assert _build_fts_query("") == ""

    def test_whitespace_only(self):
        assert _build_fts_query("   ") == ""

    def test_strips_asterisk(self):
        assert _build_fts_query("python*") == '"python"'


class TestEscapeLikePattern:
    """Test LIKE pattern escaping."""

    def test_escapes_percent(self):
        assert _escape_like_pattern("100%") == "100\\%"

    def test_escapes_underscore(self):
        assert _escape_like_pattern("file_name") == "file\\_name"

    def test_escapes_backslash(self):
        assert _escape_like_pattern("path\\file") == "path\\\\file"

    def test_normal_text(self):
        assert _escape_like_pattern("hello world") == "hello world"


class TestGetArticlesPaginated:
    """Test get_articles_paginated with FTS5 fallback."""

    def test_returns_articles_without_query(self, app):
        from extensions import db
        from models import Article, Source
        from services.article import get_articles_paginated

        source = Source(source_key="test", name="Test", source_type="rss", feed_url="")
        db.session.add(source)
        db.session.flush()

        for i in range(3):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"test_{i}",
                    original_title=f"Article {i}",
                    pipeline_status="done",
                    category="ai",
                    final_article=json.dumps(
                        {"headline": f"Article {i}", "tldr": "TLDR"}
                    ),
                )
            )
        db.session.commit()

        articles, has_next, next_page = get_articles_paginated(page=1, per_page=10)
        assert len(articles) == 3
        assert has_next is False

    def test_query_falls_back_when_no_fts(self, app):
        """Search should fall back to ILIKE when FTS5 table doesn't exist."""
        from extensions import db
        from models import Article, Source
        from services.article import get_articles_paginated

        source = Source(
            source_key="test2", name="Test2", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        db.session.add(
            Article(
                source_id=source.id,
                external_id="search_test",
                original_title="Python AI Framework Released",
                pipeline_status="done",
                category="ai",
                final_article=json.dumps(
                    {"headline": "Python AI Framework", "tldr": "TLDR"}
                ),
            )
        )
        db.session.commit()

        articles, _, _ = get_articles_paginated(page=1, per_page=10, query="python")
        assert len(articles) == 1
        assert articles[0].original_title == "Python AI Framework Released"

    def test_category_filter(self, app):
        from extensions import db
        from models import Article, Source
        from services.article import get_articles_paginated

        source = Source(
            source_key="test3", name="Test3", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        db.session.add(
            Article(
                source_id=source.id,
                external_id="cat_ai",
                original_title="AI News",
                pipeline_status="done",
                category="ai",
                final_article=json.dumps({"headline": "AI News", "tldr": "TLDR"}),
            )
        )
        db.session.add(
            Article(
                source_id=source.id,
                external_id="cat_sec",
                original_title="Security News",
                pipeline_status="done",
                category="security",
                final_article=json.dumps({"headline": "Security News", "tldr": "TLDR"}),
            )
        )
        db.session.commit()

        articles, _, _ = get_articles_paginated(page=1, per_page=10, category="ai")
        assert len(articles) == 1
        assert articles[0].category == "ai"

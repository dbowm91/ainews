"""Tests for pagination service."""


class TestPagination:
    def test_paginate_query_basic(self, app):
        from extensions import db
        from models import Article, Source
        from services.pagination import paginate_query

        source = Source(source_key="pg", name="PG", source_type="rss", feed_url="")
        db.session.add(source)
        db.session.flush()

        for i in range(5):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"pg_{i}",
                    original_title=f"Article {i}",
                    pipeline_status="done",
                )
            )
        db.session.commit()

        from models import Article as A

        q = A.query.order_by(A.id)
        items, has_next, next_page = paginate_query(q, page=1, per_page=3)

        assert len(items) == 3
        assert has_next is True
        assert next_page == 2

    def test_paginate_query_last_page(self, app):
        from extensions import db
        from models import Article, Source
        from services.pagination import paginate_query

        source = Source(source_key="pg2", name="PG2", source_type="rss", feed_url="")
        db.session.add(source)
        db.session.flush()

        for i in range(3):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"pg2_{i}",
                    original_title=f"Article {i}",
                    pipeline_status="done",
                )
            )
        db.session.commit()

        from models import Article as A

        q = A.query.order_by(A.id)
        items, has_next, next_page = paginate_query(q, page=1, per_page=10)

        assert len(items) == 3
        assert has_next is False
        assert next_page == 2

    def test_escape_like_pattern(self):
        from services.pagination import _escape_like_pattern

        assert _escape_like_pattern("100%") == "100\\%"
        assert _escape_like_pattern("file_name") == "file\\_name"
        assert _escape_like_pattern("normal text") == "normal text"

    def test_build_fts_query(self):
        from services.search.sqlite_fts import _build_fts_query

        assert _build_fts_query("python") == '"python"'
        assert _build_fts_query("python ai") == '"python" AND "ai"'
        assert _build_fts_query("") == ""
        assert _build_fts_query("   ") == ""
        assert _build_fts_query("python*") == '"python"'

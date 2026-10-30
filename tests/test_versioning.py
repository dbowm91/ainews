"""Tests for article versioning and related article finding."""

import json


class TestArticleVersioning:
    """Test original_ai_article preservation."""

    def test_edit_preserves_original_ai(self, app):
        """When the editor finalizes, original_ai_article should be set."""
        from extensions import db
        from models import Article, Source

        source = Source(
            source_key="ver_test", name="Ver Test", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        draft = json.dumps({"headline": "AI Generated", "tldr": "Original TLDR"})
        article = Article(
            source_id=source.id,
            external_id="ver_1",
            original_title="Test",
            pipeline_status="editing",
            draft_article=draft,
            final_article=draft,
            original_ai_article=draft,
        )
        db.session.add(article)
        db.session.commit()

        # Simulate admin edit: modify final_article but not original_ai_article
        updated = json.loads(article.final_article)
        updated["headline"] = "Human Edited"
        article.final_article = json.dumps(updated)
        db.session.commit()

        # Reload from DB
        fresh = db.session.get(Article, article.id)
        final = json.loads(fresh.final_article)
        original = json.loads(fresh.original_ai_article)

        assert final["headline"] == "Human Edited"
        assert original["headline"] == "AI Generated"

    def test_finalize_sets_original_ai(self, app):
        """_finalize should set original_ai_article from draft."""
        from extensions import db
        from models import Article, Source
        from tasks.pipeline import _finalize

        source = Source(
            source_key="fin_test", name="Fin Test", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        draft = json.dumps({"headline": "Draft", "tldr": "Draft TLDR"})
        article = Article(
            source_id=source.id,
            external_id="fin_1",
            original_title="Test",
            pipeline_status="writing",
            draft_article=draft,
        )
        db.session.add(article)
        db.session.commit()

        _finalize(article.id)

        fresh = db.session.get(Article, article.id)
        assert fresh.final_article == draft
        assert fresh.original_ai_article == draft
        assert fresh.pipeline_status == "done"


class TestFindRelatedArticles:
    """Test the unified find_related_articles_dicts function."""

    def test_returns_empty_for_no_topics(self, app):
        from services.related import find_related_articles_dicts

        result = find_related_articles_dicts(topics=[], exclude_id=1)
        assert result == []

    def test_returns_dicts_with_matching_category(self, app):
        from extensions import db
        from models import Article, Source
        from services.related import find_related_articles_dicts

        source = Source(
            source_key="rel_test", name="Rel Test", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        for i in range(3):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"rel_{i}",
                    original_title=f"AI Article {i}",
                    pipeline_status="done",
                    publicly_visible=True,
                    category="ai",
                    final_article=json.dumps(
                        {"headline": f"AI Article {i}", "tldr": "TLDR"}
                    ),
                )
            )
        db.session.add(
            Article(
                source_id=source.id,
                external_id="rel_sec",
                original_title="Security Article",
                pipeline_status="done",
                publicly_visible=True,
                category="security",
                final_article=json.dumps({"headline": "Security", "tldr": "TLDR"}),
            )
        )
        db.session.commit()

        result = find_related_articles_dicts(topics=["ai"], exclude_id=0, limit=5)

        assert len(result) == 3
        for r in result:
            assert "title" in r
            assert "category" in r
            assert "snippet" in r
            assert "created_at" in r
            assert r["category"] == "ai"

    def test_excludes_specified_article(self, app):
        from extensions import db
        from models import Article, Source
        from services.related import find_related_articles_dicts

        source = Source(
            source_key="ex_test", name="Ex Test", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        articles = []
        for i in range(3):
            a = Article(
                source_id=source.id,
                external_id=f"ex_{i}",
                original_title=f"AI Article {i}",
                pipeline_status="done",
                publicly_visible=True,
                category="ai",
                final_article=json.dumps(
                    {"headline": f"AI Article {i}", "tldr": "TLDR"}
                ),
            )
            db.session.add(a)
            articles.append(a)
        db.session.commit()

        exclude_id = articles[0].id
        result = find_related_articles_dicts(
            topics=["ai"], exclude_id=exclude_id, limit=5
        )

        assert len(result) == 2
        for r in result:
            assert r["title"] != articles[0].original_title

    def test_respects_limit(self, app):
        from extensions import db
        from models import Article, Source
        from services.related import find_related_articles_dicts

        source = Source(
            source_key="lim_test", name="Lim Test", source_type="rss", feed_url=""
        )
        db.session.add(source)
        db.session.flush()

        for i in range(10):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"lim_{i}",
                    original_title=f"AI Article {i}",
                    pipeline_status="done",
                    publicly_visible=True,
                    category="ai",
                    final_article=json.dumps(
                        {"headline": f"AI Article {i}", "tldr": "TLDR"}
                    ),
                )
            )
        db.session.commit()

        result = find_related_articles_dicts(topics=["ai"], exclude_id=0, limit=3)
        assert len(result) == 3

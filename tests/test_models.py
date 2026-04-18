"""Tests for model cascade deletion behavior."""


class TestArticleCascadeDeletions:
    def test_article_delete_cascades_to_citations(
        self, app, create_source, create_article
    ):
        from models import Citation
        from extensions import db

        with app.app_context():
            source = create_source(source_key="cascade-test-1")
            article = create_article(source=source)
            db.session.flush()

            citation = Citation(
                article_id=article.id,
                url="https://example.com/citation",
                title="Citation Title",
            )
            db.session.add(citation)
            db.session.commit()

            db.session.delete(article)
            db.session.commit()

            assert db.session.get(Citation, citation.id) is None

    def test_article_delete_cascades_to_article_metrics(
        self, app, create_source, create_article
    ):
        from models import ArticleMetric
        from extensions import db

        with app.app_context():
            source = create_source(source_key="cascade-test-2")
            article = create_article(source=source)
            db.session.flush()

            metric = ArticleMetric(article_id=article.id, page_loads=42)
            db.session.add(metric)
            db.session.commit()

            metric_id = metric.id
            db.session.delete(article)
            db.session.commit()

            assert db.session.get(ArticleMetric, metric_id) is None

    def test_article_delete_cascades_to_article_versions(
        self, app, create_source, create_article
    ):
        from models import ArticleVersion
        from extensions import db

        with app.app_context():
            source = create_source(source_key="cascade-test-3")
            article = create_article(source=source)
            db.session.flush()

            version = ArticleVersion(
                article_id=article.id,
                version_number=1,
                final_article='{"headline": "Test"}',
            )
            db.session.add(version)
            db.session.commit()

            version_id = version.id
            db.session.delete(article)
            db.session.commit()

            assert db.session.get(ArticleVersion, version_id) is None

    def test_article_delete_cascades_to_article_tags(
        self, app, create_source, create_article, create_tag
    ):
        from extensions import db

        with app.app_context():
            source = create_source(source_key="cascade-test-4")
            article = create_article(source=source)
            tag = create_tag(name="cascade-tag")
            db.session.flush()

            article.tags.append(tag)
            db.session.commit()

            assert len(article.tags) == 1
            db.session.delete(article)
            db.session.commit()

            from models import article_tags

            assoc = db.session.execute(
                article_tags.select().where(article_tags.c.article_id == article.id)
            ).first()
            assert assoc is None


class TestSourceCascadeDeletions:
    def test_source_delete_cascades_to_articles(
        self, app, create_source, create_article
    ):
        from models import Article
        from extensions import db

        with app.app_context():
            source = create_source(source_key="cascade-source-1")
            article = create_article(source=source)
            db.session.commit()

            article_id = article.id
            db.session.delete(source)
            db.session.commit()

            assert db.session.get(Article, article_id) is None

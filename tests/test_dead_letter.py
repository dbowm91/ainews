"""Tests for dead letter service."""


class TestDeadLetter:
    def test_dead_letter_article(self, app, create_source, create_article):
        from services.dead_letter import dead_letter_article

        source = create_source(source_key="dl_test2")
        article = create_article(source=source, pipeline_status="writing")
        result = dead_letter_article(article, reason="test dead letter", stage="write")

        assert result is True
        assert article.pipeline_status == "failed"
        assert "Dead-lettered" in article.last_error

    def test_retry_dead_letter(self, app, create_source, create_article):
        from services.dead_letter import retry_dead_letter

        source = create_source(source_key="dl_test3")
        article = create_article(source=source, pipeline_status="failed")
        result = retry_dead_letter(article)

        assert result is True
        assert article.pipeline_status == "pending"
        assert article.retry_count == 0

    def test_get_dead_lettered_articles(self, app, create_source, create_article):
        from services.dead_letter import get_dead_lettered_articles

        source = create_source(source_key="dl_test")
        create_article(source=source, pipeline_status="failed")
        create_article(source=source, pipeline_status="done", external_id="dl_done")

        articles = get_dead_lettered_articles(limit=10)
        assert len(articles) == 1
        assert articles[0].pipeline_status == "failed"

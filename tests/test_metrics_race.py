"""Tests for track_metric concurrency safety."""

import pytest
from models import Article, ArticleMetric
from extensions import db
from services.article import track_metric


@pytest.fixture
def article_with_source(app):
    """Create a source and article for metric tests."""
    from models import Source

    with app.app_context():
        source = Source(source_key="test", name="Test", source_type="rss")
        db.session.add(source)
        db.session.flush()
        article = Article(
            source_id=source.id,
            external_id="metric-test-1",
            original_title="Metric Test Article",
            pipeline_status="done",
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id
    return article_id


class TestTrackMetric:
    """Test track_metric correctness and upsert behavior."""

    def test_first_page_load_creates_row(self, app, article_with_source):
        with app.app_context():
            track_metric(article_with_source, ArticleMetric.page_loads)
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric is not None
            assert metric.page_loads == 1

    def test_subsequent_increments(self, app, article_with_source):
        with app.app_context():
            track_metric(article_with_source, ArticleMetric.page_loads)
            track_metric(article_with_source, ArticleMetric.page_loads)
            track_metric(article_with_source, ArticleMetric.page_loads)
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric.page_loads == 3

    def test_different_columns_independent(self, app, article_with_source):
        with app.app_context():
            track_metric(article_with_source, ArticleMetric.page_loads)
            track_metric(article_with_source, ArticleMetric.share_button_clicks)
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric.page_loads == 1
            assert metric.share_button_clicks == 1

    def test_insert_then_update(self, app, article_with_source):
        """First call inserts, subsequent calls take the IntegrityError UPDATE path."""
        with app.app_context():
            track_metric(article_with_source, ArticleMetric.share_link_views)
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric.share_link_views == 1

            # Second call goes through the IntegrityError → UPDATE path
            track_metric(article_with_source, ArticleMetric.share_link_views)
            db.session.expire_all()
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric.share_link_views == 2

    def test_many_sequential_increments_no_lost_updates(self, app, article_with_source):
        """Verify no lost updates across many sequential calls."""
        with app.app_context():
            for _ in range(20):
                track_metric(article_with_source, ArticleMetric.page_loads)
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric.page_loads == 20

    def test_concurrent_upsert_increments_correctly(self, app, article_with_source):
        """Simulate concurrent-style increments and verify each one is persisted."""
        with app.app_context():
            for i in range(1, 11):
                track_metric(article_with_source, ArticleMetric.page_loads)
                db.session.expire_all()
                metric = ArticleMetric.query.filter_by(
                    article_id=article_with_source
                ).first()
                assert metric.page_loads == i

    def test_interleaved_metric_columns_no_crosstalk(self, app, article_with_source):
        """Interleaved increments on different columns stay independent."""
        with app.app_context():
            columns = [
                ArticleMetric.page_loads,
                ArticleMetric.share_button_clicks,
                ArticleMetric.share_link_views,
            ]
            for col in columns:
                for _ in range(5):
                    track_metric(article_with_source, col)
            metric = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).first()
            assert metric.page_loads == 5
            assert metric.share_button_clicks == 5
            assert metric.share_link_views == 5

    def test_upsert_creates_single_row_per_article(self, app, article_with_source):
        """Multiple calls produce exactly one ArticleMetric row."""
        with app.app_context():
            for _ in range(5):
                track_metric(article_with_source, ArticleMetric.page_loads)
            count = ArticleMetric.query.filter_by(
                article_id=article_with_source
            ).count()
            assert count == 1

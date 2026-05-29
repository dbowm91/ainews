"""Tests for topic gap service and API."""

from datetime import datetime, timedelta, timezone


class TestTopicGapService:
    """Test topic gap analysis service."""

    def test_empty_topics_returns_empty_list(self, app):
        """No topics returns empty report list."""
        with app.app_context():
            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=[], days=30)
            assert reports == []

    def test_no_data_returns_zero_counts(self, app):
        """No articles/queries returns zero counts with high gap score."""
        with app.app_context():
            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["security"], days=30)
            assert len(reports) == 1
            assert reports[0].topic == "security"
            assert reports[0].article_count_7d == 0
            assert reports[0].article_count_30d == 0
            assert reports[0].gap_score >= 0.0
            assert reports[0].gap_score <= 1.0

    def test_low_volume_high_demand(self, app, create_source, create_article):
        """High zero-result queries but low article volume = high gap score."""
        with app.app_context():
            from models import SearchQuery
            from extensions import db

            source = create_source(source_key="gap-test-source", name="Gap Test", active=True)
            article = create_article(
                source=source,
                original_title="AI Security Article",
                topics=["security"],
                published_at=datetime.now(timezone.utc) - timedelta(days=2),
                impact_score=10,
            )
            db.session.flush()

            for i in range(3):
                query = SearchQuery(
                    query=f"security vulnerability {i}",
                    results_count=0,
                    created_at=datetime.now(timezone.utc) - timedelta(days=i),
                )
                db.session.add(query)
            db.session.commit()

            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["security"], days=30)
            security_report = next(r for r in reports if r.topic == "security")

            assert security_report.article_count_7d >= 1
            assert len(security_report.zero_result_queries) == 3
            assert security_report.gap_score >= 0.3

    def test_high_volume_low_demand(self, app, create_source, create_article):
        """High article volume but no zero-result queries = lower gap score."""
        with app.app_context():
            source = create_source(source_key="high-vol-source", name="High Volume", active=True)
            for i in range(5):
                create_article(
                    source=source,
                    original_title=f"AI Article {i}",
                    topics=["ai"],
                    published_at=datetime.now(timezone.utc) - timedelta(days=i),
                    impact_score=50,
                )

            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["ai"], days=30)
            ai_report = next(r for r in reports if r.topic == "ai")

            assert ai_report.article_count_7d >= 4
            assert ai_report.article_count_30d >= 5
            assert len(ai_report.zero_result_queries) == 0

    def test_trend_memory_increases_gap_score(self, app, create_source, create_article):
        """Trend memory entries indicate demand and increase gap score."""
        with app.app_context():
            from models import TrendMemory
            from extensions import db

            source = create_source(source_key="trend-source", name="Trend Source", active=True)
            create_article(
                source=source,
                original_title="AI Article",
                topics=["ai"],
                published_at=datetime.now(timezone.utc) - timedelta(days=10),
                impact_score=20,
            )
            db.session.flush()

            for i in range(4):
                memory = TrendMemory(
                    topic="ai",
                    signal=f"AI trend signal {i}",
                    importance=2,
                    created_at=datetime.now(timezone.utc) - timedelta(days=i),
                )
                db.session.add(memory)
            db.session.commit()

            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["ai"], days=30)
            ai_report = next(r for r in reports if r.topic == "ai")

            assert ai_report.trend_memory_count == 4

    def test_active_sources_count(self, app, create_source, create_article):
        """Active sources are counted per topic."""
        with app.app_context():
            source1 = create_source(source_key="src1-gap", name="Source 1", active=True)
            source2 = create_source(source_key="src2-gap", name="Source 2", active=True)
            source3 = create_source(source_key="src3-gap", name="Source 3", active=False)

            create_article(source=source1, topics=["privacy"], published_at=datetime.now(timezone.utc) - timedelta(days=1))
            create_article(source=source2, topics=["privacy"], published_at=datetime.now(timezone.utc) - timedelta(days=2))
            create_article(source=source3, topics=["privacy"], published_at=datetime.now(timezone.utc) - timedelta(days=3))

            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["privacy"], days=30)
            privacy_report = next(r for r in reports if r.topic == "privacy")

            assert privacy_report.active_sources == 2

    def test_reports_sorted_by_gap_score(self, app):
        """Reports are sorted by gap score descending."""
        with app.app_context():
            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["ai", "security", "privacy"], days=30)

            assert len(reports) == 3
            gap_scores = [r.gap_score for r in reports]
            assert gap_scores == sorted(gap_scores, reverse=True)

    def test_specific_topics_filter(self, app, create_source, create_article):
        """Requesting specific topics only returns those topics."""
        with app.app_context():
            source = create_source(source_key="filter-source", name="Filter Source", active=True)
            create_article(source=source, topics=["ai"], published_at=datetime.now(timezone.utc) - timedelta(days=1))
            create_article(source=source, topics=["security"], published_at=datetime.now(timezone.utc) - timedelta(days=1))

            from services.topic_gap import get_topic_gap_report

            reports = get_topic_gap_report(topics=["ai"], days=30)
            assert len(reports) == 1
            assert reports[0].topic == "ai"


class TestTopicGapAPI:
    """Test topic gap API endpoint."""

    def test_topic_gap_reports_requires_auth(self, client):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/topic-gap/reports")
        assert response.status_code == 401

    def test_topic_gap_reports_authenticated(self, auth_client, app):
        """Authenticated request returns 200."""
        with app.app_context():
            response = auth_client.get("/api/v1/topic-gap/reports")
            assert response.status_code == 200

    def test_topic_gap_reports_with_topics_param(self, auth_client, app):
        """Topics parameter filters results."""
        with app.app_context():
            response = auth_client.get("/api/v1/topic-gap/reports?topics=ai,security")
            assert response.status_code == 200
            data = response.get_json()
            assert "data" in data
            assert "reports" in data["data"]
            assert data["data"]["meta"]["topics"] == ["ai", "security"]

    def test_topic_gap_reports_with_days_param(self, auth_client, app):
        """Days parameter is accepted."""
        with app.app_context():
            response = auth_client.get("/api/v1/topic-gap/reports?days=7")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 7

    def test_topic_gap_reports_days_clamped_to_max(self, auth_client, app):
        """Days over 365 is clamped to 365."""
        with app.app_context():
            response = auth_client.get("/api/v1/topic-gap/reports?days=500")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 365

    def test_topic_gap_reports_invalid_days_defaults(self, auth_client, app):
        """Invalid days parameter defaults to 30."""
        with app.app_context():
            response = auth_client.get("/api/v1/topic-gap/reports?days=invalid")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 30

    def test_topic_gap_reports_returns_expected_fields(self, auth_client, app):
        """Response contains all expected fields."""
        with app.app_context():
            response = auth_client.get("/api/v1/topic-gap/reports?topics=security")
            assert response.status_code == 200
            data = response.get_json()
            report = data["data"]["reports"][0]

            assert "topic" in report
            assert "article_count_7d" in report
            assert "article_count_30d" in report
            assert "zero_result_queries" in report
            assert "trend_memory_count" in report
            assert "active_sources" in report
            assert "gap_score" in report
            assert "reason" in report
            assert isinstance(report["gap_score"], float)
            assert 0.0 <= report["gap_score"] <= 1.0
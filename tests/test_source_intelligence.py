"""Tests for source intelligence service and API."""

from datetime import datetime, timedelta, timezone


class TestSourceIntelligenceService:
    """Test source intelligence aggregation logic."""

    def test_empty_sources_returns_empty_list(self, app):
        """No sources returns empty performance list."""
        with app.app_context():
            from services.source_intelligence import get_source_performance

            results = get_source_performance(days=7)
            assert results == []

    def test_source_performance_basic(self, app, create_source, create_article):
        """Basic source performance calculation."""
        with app.app_context():
            source = create_source(
                source_key="perf-test",
                name="Performance Test Source",
                active=True,
            )
            db = __import__("extensions").db

            for i in range(5):
                create_article(
                    source=source,
                    pipeline_status="done",
                    impact_score=50 + i * 10,
                    created_at=datetime.now(timezone.utc) - timedelta(days=i),
                )
            db.session.commit()

            from services.source_intelligence import get_source_performance

            results = get_source_performance(days=7)
            assert len(results) == 1
            r = results[0]
            assert r.source_key == "perf-test"
            assert r.name == "Performance Test Source"
            assert r.active is True
            assert r.health == "ok"
            assert r.articles_created == 5
            assert r.published == 5
            assert r.avg_impact_score == 70.0

    def test_source_health_inactive(self, app, create_source):
        """Inactive source returns health=inactive."""
        with app.app_context():
            source = create_source(
                source_key="inactive-test",
                name="Inactive Test",
                active=False,
            )
            from services.source_intelligence import _compute_source_health

            health = _compute_source_health(source)
            assert health == "inactive"

    def test_source_health_failing(self, app, create_source):
        """Source with disabled_at returns health=failing."""
        with app.app_context():
            source = create_source(
                source_key="failing-test",
                name="Failing Test",
                active=True,
            )
            source.disabled_at = datetime.now(timezone.utc)
            from extensions import db
            db.session.commit()

            from services.source_intelligence import _compute_source_health

            health = _compute_source_health(source)
            assert health == "failing"

    def test_source_health_degraded(self, app, create_source):
        """Source with 5+ consecutive_failures returns health=degraded."""
        with app.app_context():
            source = create_source(
                source_key="degraded-test",
                name="Degraded Test",
                active=True,
            )
            source.consecutive_failures = 5
            from extensions import db
            db.session.commit()

            from services.source_intelligence import _compute_source_health

            health = _compute_source_health(source)
            assert health == "degraded"

    def test_source_performance_selection_rate(self, app, create_source, create_article):
        """Selection rate is calculated correctly."""
        with app.app_context():
            source = create_source(
                source_key="sel-rate",
                name="Selection Rate Test",
                active=True,
            )
            from extensions import db

            for i in range(10):
                create_article(
                    source=source,
                    pipeline_status="selected" if i < 3 else "skipped",
                    impact_score=50,
                )
            db.session.commit()

            from services.source_intelligence import get_source_performance

            results = get_source_performance(days=7)
            r = next(x for x in results if x.source_key == "sel-rate")
            assert r.selected == 3
            assert r.skipped == 7
            assert r.selection_rate == 0.3

    def test_source_recommendations_low_selection(self, app, create_source, create_article):
        """Low selection rate triggers recommendation."""
        with app.app_context():
            source = create_source(
                source_key="low-sel",
                name="Low Selection",
                active=True,
            )
            from extensions import db

            for i in range(10):
                create_article(
                    source=source,
                    pipeline_status="skipped",
                    impact_score=30,
                    created_at=datetime.now(timezone.utc) - timedelta(days=i % 7),
                )
            db.session.commit()

            from services.source_intelligence import get_source_recommendations

            recs = get_source_recommendations(days=30)
            low_sel_recs = [r for r in recs if r.source_key == "low-sel"]
            assert any(r.recommendation == "review_selector_criteria" for r in low_sel_recs)

    def test_source_recommendations_high_failures(self, app, create_source):
        """High consecutive failures triggers critical recommendation."""
        with app.app_context():
            source = create_source(
                source_key="hi-fail",
                name="High Failures",
                active=True,
            )
            source.consecutive_failures = 7
            source.last_error = "Connection timeout"
            from extensions import db
            db.session.commit()

            from services.source_intelligence import get_source_recommendations

            recs = get_source_recommendations(days=30)
            hi_fail_recs = [r for r in recs if r.source_key == "hi-fail"]
            assert any(r.severity == "critical" for r in hi_fail_recs)
            assert any(r.recommendation == "disable_source" for r in hi_fail_recs)

    def test_topic_coverage_basic(self, app, create_source, create_article):
        """Topic coverage aggregates correctly."""
        with app.app_context():
            source = create_source(
                source_key="topic-cov",
                name="Topic Coverage Test",
                active=True,
            )
            from extensions import db

            create_article(
                source=source,
                topics=["ai", "security"],
                impact_score=60,
            )
            create_article(
                source=source,
                topics=["ai", "privacy"],
                impact_score=70,
            )
            db.session.commit()

            from services.source_intelligence import get_topic_coverage

            coverage = get_topic_coverage(days=7)
            assert "ai" in coverage
            assert coverage["ai"]["article_count"] == 2
            assert coverage["ai"]["avg_impact_score"] == 65.0


class TestSourceIntelligenceAPI:
    """Test source intelligence API endpoints."""

    def test_sources_performance_requires_auth(self, client):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/sources/performance")
        assert response.status_code == 401

    def test_sources_performance_authenticated(self, auth_client, app):
        """Authenticated request returns 200."""
        with app.app_context():
            response = auth_client.get("/api/v1/sources/performance")
            assert response.status_code == 200

    def test_sources_performance_days_param(self, auth_client, app):
        """Days parameter is accepted and clamped."""
        with app.app_context():
            response = auth_client.get("/api/v1/sources/performance?days=14")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 14

    def test_sources_performance_days_clamped(self, auth_client, app):
        """Days over 90 is clamped to 90."""
        with app.app_context():
            response = auth_client.get("/api/v1/sources/performance?days=200")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 90

    def test_topics_coverage_requires_auth(self, client):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/topics/coverage")
        assert response.status_code == 401

    def test_topics_coverage_authenticated(self, auth_client, app):
        """Authenticated request returns 200."""
        with app.app_context():
            response = auth_client.get("/api/v1/topics/coverage")
            assert response.status_code == 200

    def test_topics_coverage_days_param(self, auth_client, app):
        """Days parameter is accepted."""
        with app.app_context():
            response = auth_client.get("/api/v1/topics/coverage?days=14")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 14

    def test_sources_recommendations_requires_auth(self, client):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/sources/recommendations")
        assert response.status_code == 401

    def test_sources_recommendations_authenticated(self, auth_client, app):
        """Authenticated request returns 200."""
        with app.app_context():
            response = auth_client.get("/api/v1/sources/recommendations")
            assert response.status_code == 200

    def test_sources_recommendations_days_param(self, auth_client, app):
        """Days parameter is accepted."""
        with app.app_context():
            response = auth_client.get("/api/v1/sources/recommendations?days=14")
            assert response.status_code == 200
            data = response.get_json()
            assert data["data"]["meta"]["days"] == 14

    def test_sources_performance_returns_expected_fields(self, auth_client, app):
        """Response contains all expected fields."""
        with app.app_context():
            response = auth_client.get("/api/v1/sources/performance?days=7")
            assert response.status_code == 200
            data = response.get_json()
            assert "data" in data
            assert "sources" in data["data"]
            assert "meta" in data["data"]

    def test_topics_coverage_returns_expected_fields(self, auth_client, app):
        """Response contains all expected fields."""
        with app.app_context():
            response = auth_client.get("/api/v1/topics/coverage?days=7")
            assert response.status_code == 200
            data = response.get_json()
            assert "data" in data
            assert "topics" in data["data"]
            assert "meta" in data["data"]
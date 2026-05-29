"""Tests for services/alerts.py - Alert rule evaluation."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestAlertDataclass:
    def test_alert_to_dict(self):
        """Alert.to_dict() returns correct structure."""
        from services.alerts import Alert
        alert = Alert(
            code="TEST_ALERT",
            severity="warning",
            title="Test Title",
            message="Test message",
            source="test_source",
            metadata={"key": "value"},
        )
        d = alert.to_dict()
        assert d["code"] == "TEST_ALERT"
        assert d["severity"] == "warning"
        assert d["title"] == "Test Title"
        assert d["message"] == "Test message"
        assert d["source"] == "test_source"
        assert d["metadata"] == {"key": "value"}
        assert "created_at" in d


class TestAlertThresholds:
    def test_default_values(self):
        """AlertThresholds has sensible defaults."""
        from services.alerts import AlertThresholds
        t = AlertThresholds()
        assert t.pipeline_backlog == 50
        assert t.stuck_article_count == 10
        assert t.source_consecutive_failures == 5
        assert t.crawl_zero_articles_runs == 3
        assert t.crawl_zero_articles_hours == 24.0

    def test_custom_thresholds(self):
        """AlertThresholds accepts custom values."""
        from services.alerts import AlertThresholds
        t = AlertThresholds(pipeline_backlog=100, stuck_article_count=20)
        assert t.pipeline_backlog == 100
        assert t.stuck_article_count == 20


class TestCheckCeleryWorkers:
    def test_no_workers_returns_alert(self, app):
        """No workers returns a critical alert."""
        with app.app_context():
            with patch("celery_app.celery_app.control.inspect") as mock_inspect:
                mock_inspect.return_value.ping.return_value = None
                from services.alerts import _check_celery_workers
                alert = _check_celery_workers()
                assert alert is not None
                assert alert.code == "CELERY_NO_WORKERS"
                assert alert.severity == "critical"
                assert alert.source == "celery"

    def test_workers_ok_returns_none(self, app):
        """Workers present returns no alert."""
        with app.app_context():
            with patch("celery_app.celery_app.control.inspect") as mock_inspect:
                mock_inspect.return_value.ping.return_value = {"worker1@host": {"ok": True}}
                from services.alerts import _check_celery_workers
                alert = _check_celery_workers()
                assert alert is None


class TestCheckRedis:
    def test_redis_unavailable_returns_alert(self, app):
        """Redis unavailable returns a critical alert."""
        with app.app_context():
            with patch("extensions.get_redis") as mock_get_redis:
                mock_redis = MagicMock()
                mock_redis.ping.side_effect = Exception("Connection refused")
                mock_get_redis.return_value = mock_redis
                from services.alerts import _check_redis_available
                alert = _check_redis_available()
                assert alert is not None
                assert alert.code == "REDIS_UNAVAILABLE"
                assert alert.severity == "critical"

    def test_redis_ok_returns_none(self, app):
        """Redis available returns no alert."""
        with app.app_context():
            with patch("extensions.get_redis") as mock_get_redis:
                mock_redis = MagicMock()
                mock_redis.ping.return_value = True
                mock_get_redis.return_value = mock_redis
                from services.alerts import _check_redis_available
                alert = _check_redis_available()
                assert alert is None


class TestCheckCircuitBreaker:
    def test_circuit_open_returns_alert(self, app):
        """Open circuit breaker returns a critical alert."""
        with app.app_context():
            from services.alerts import _check_circuit_breaker_open
            from services.circuit_breaker import State
            with patch("services.circuit_breaker.get_breaker") as mock_get_breaker:
                mock_breaker = MagicMock()
                mock_breaker.state = State.OPEN
                mock_get_breaker.return_value = mock_breaker
                alert = _check_circuit_breaker_open()
                assert alert is not None
                assert alert.code == "CIRCUIT_BREAKER_OPEN"
                assert alert.severity == "critical"

    def test_circuit_closed_returns_none(self, app):
        """Closed circuit breaker returns no alert."""
        with app.app_context():
            from services.alerts import _check_circuit_breaker_open
            from services.circuit_breaker import State
            with patch("services.circuit_breaker.get_breaker") as mock_get_breaker:
                mock_breaker = MagicMock()
                mock_breaker.state = State.CLOSED
                mock_get_breaker.return_value = mock_breaker
                alert = _check_circuit_breaker_open()
                assert alert is None


class TestCheckPipelineBacklog:
    def test_backlog_above_threshold_returns_warning(self, app):
        """Pipeline backlog above threshold returns warning alert."""
        with app.app_context():
            from extensions import db
            from models import Article, Source
            source = Source(source_key="test", name="Test", source_type="rss", url="http://test.com")
            db.session.add(source)
            db.session.commit()
            for i in range(55):
                article = Article(
                    source_id=source.id,
                    pipeline_status="pending",
                )
                db.session.add(article)
            db.session.commit()
            from services.alerts import _check_pipeline_backlog, AlertThresholds
            thresholds = AlertThresholds(pipeline_backlog=50)
            alert = _check_pipeline_backlog(thresholds)
            assert alert is not None
            assert alert.code == "PIPELINE_BACKLOG"
            assert alert.severity == "warning"

    def test_backlog_below_threshold_returns_none(self, app):
        """Pipeline backlog below threshold returns no alert."""
        with app.app_context():
            from extensions import db
            from models import Article, Source
            source = Source(source_key="test2", name="Test2", source_type="rss", url="http://test2.com")
            db.session.add(source)
            db.session.commit()
            for i in range(5):
                article = Article(
                    source_id=source.id,
                    pipeline_status="pending",
                )
                db.session.add(article)
            db.session.commit()
            from services.alerts import _check_pipeline_backlog, AlertThresholds
            thresholds = AlertThresholds(pipeline_backlog=50)
            alert = _check_pipeline_backlog(thresholds)
            assert alert is None


class TestCheckStuckArticles:
    def test_stuck_articles_above_threshold_returns_warning(self, app):
        """Stuck articles above threshold returns warning alert."""
        with app.app_context():
            from extensions import db
            from models import Article, Source
            source = Source(source_key="test3", name="Test3", source_type="rss", url="http://test3.com")
            db.session.add(source)
            db.session.commit()
            for i in range(15):
                article = Article(
                    source_id=source.id,
                    pipeline_status="pending",
                    retry_count=5,
                )
                db.session.add(article)
            db.session.commit()
            from services.alerts import _check_stuck_articles, AlertThresholds
            thresholds = AlertThresholds(stuck_article_count=10)
            alert = _check_stuck_articles(thresholds)
            assert alert is not None
            assert alert.code == "STUCK_ARTICLES"
            assert alert.severity == "warning"

    def test_stuck_articles_below_threshold_returns_none(self, app):
        """Stuck articles below threshold returns no alert."""
        with app.app_context():
            from services.alerts import _check_stuck_articles, AlertThresholds
            thresholds = AlertThresholds(stuck_article_count=10)
            alert = _check_stuck_articles(thresholds)
            assert alert is None


class TestCheckSourceFailures:
    def test_sources_with_consecutive_failures_returns_warning(self, app):
        """Sources with consecutive failures above threshold returns warning alert."""
        with app.app_context():
            from extensions import db
            from models import Source
            for i in range(6):
                source = Source(
                    source_key=f"fail{i}",
                    name=f"Fail{i}",
                    source_type="rss",
                    url=f"http://fail{i}.com",
                    consecutive_failures=5,
                    active=True,
                )
                db.session.add(source)
            db.session.commit()
            from services.alerts import _check_source_failures, AlertThresholds
            thresholds = AlertThresholds(source_consecutive_failures=5)
            alert = _check_source_failures(thresholds)
            assert alert is not None
            assert alert.code == "SOURCE_CONSECUTIVE_FAILURES"
            assert alert.severity == "warning"

    def test_sources_below_threshold_returns_none(self, app):
        """Sources below threshold returns no alert."""
        with app.app_context():
            from services.alerts import _check_source_failures, AlertThresholds
            thresholds = AlertThresholds(source_consecutive_failures=5)
            alert = _check_source_failures(thresholds)
            assert alert is None


class TestCheckCrawlZeroArticles:
    def test_all_runs_zero_articles_returns_warning(self, app):
        """All recent crawl runs producing zero articles returns warning alert."""
        with app.app_context():
            from extensions import db
            from models import PipelineRun
            now = datetime.now(timezone.utc)
            for i in range(3):
                run = PipelineRun(
                    run_type="crawl",
                    status="completed",
                    articles_fetched=0,
                    started_at=now - timedelta(minutes=i * 10),
                )
                db.session.add(run)
            db.session.commit()
            from services.alerts import _check_crawl_zero_articles, AlertThresholds
            thresholds = AlertThresholds(crawl_zero_articles_runs=3, crawl_zero_articles_hours=24)
            alert = _check_crawl_zero_articles(thresholds=thresholds)
            assert alert is not None
            assert alert.code == "CRAWL_ZERO_ARTICLES"
            assert alert.severity == "warning"

    def test_some_runs_with_articles_returns_none(self, app):
        """Some crawl runs with articles returns no alert."""
        with app.app_context():
            from extensions import db
            from models import PipelineRun
            now = datetime.now(timezone.utc)
            for i in range(3):
                run = PipelineRun(
                    run_type="crawl",
                    status="completed",
                    articles_fetched=5 if i == 0 else 0,
                    started_at=now - timedelta(minutes=i * 10),
                )
                db.session.add(run)
            db.session.commit()
            from services.alerts import _check_crawl_zero_articles, AlertThresholds
            thresholds = AlertThresholds(crawl_zero_articles_runs=3, crawl_zero_articles_hours=24)
            alert = _check_crawl_zero_articles(thresholds=thresholds)
            assert alert is None


class TestCheckQualityGateFailures:
    def test_failure_rate_above_threshold_returns_warning(self, app):
        """Quality gate failure rate above threshold returns warning alert."""
        with app.app_context():
            from extensions import db
            from models import QualityReport, Article, Source
            source = Source(source_key="qgtest", name="QGTest", source_type="rss", url="http://qgtest.com")
            db.session.add(source)
            db.session.commit()
            now = datetime.now(timezone.utc)
            for i in range(6):
                article = Article(source_id=source.id, pipeline_status="published")
                db.session.add(article)
            db.session.commit()
            articles = Article.query.all()
            for article in articles[:4]:
                report = QualityReport(
                    article_id=article.id,
                    stage="edit",
                    overall_score=0.3,
                    passed=False,
                    needs_review=True,
                    findings=[],
                    meta={},
                )
                db.session.add(report)
            for article in articles[4:]:
                report = QualityReport(
                    article_id=article.id,
                    stage="edit",
                    overall_score=0.9,
                    passed=True,
                    needs_review=False,
                    findings=[],
                    meta={},
                )
                db.session.add(report)
            db.session.commit()
            from services.alerts import _check_quality_gate_failures, AlertThresholds
            thresholds = AlertThresholds(quality_gate_failure_rate=0.5)
            alert = _check_quality_gate_failures(window_hours=24, threshold=0.5)
            assert alert is not None
            assert alert.code == "QUALITY_GATE_FAILURE_RATE"
            assert alert.severity == "warning"

    def test_failure_rate_below_threshold_returns_none(self, app):
        """Quality gate failure rate below threshold returns no alert."""
        with app.app_context():
            from services.alerts import _check_quality_gate_failures, AlertThresholds
            thresholds = AlertThresholds(quality_gate_failure_rate=0.5)
            alert = _check_quality_gate_failures(window_hours=24, threshold=0.5)
            assert alert is None


class TestCheckNewsletterDeliveryFailures:
    def test_delivery_failure_rate_above_threshold_returns_warning(self, app):
        """Newsletter delivery failure rate above threshold returns warning alert."""
        with app.app_context():
            from extensions import db
            from models import Newsletter
            now = datetime.now(timezone.utc)
            for i in range(4):
                newsletter = Newsletter(
                    newsletter_type="daily",
                    generated_at=now - timedelta(hours=i),
                    error_message=None if i % 2 == 0 else "SMTP timeout",
                )
                db.session.add(newsletter)
            db.session.commit()
            from services.alerts import _check_newsletter_delivery_failures, AlertThresholds
            thresholds = AlertThresholds(newsletter_delivery_failure_rate=0.25)
            alert = _check_newsletter_delivery_failures(window_hours=24, threshold=0.25)
            assert alert is not None
            assert alert.code == "NEWSLETTER_DELIVERY_FAILURES"
            assert alert.severity == "warning"

    def test_delivery_failure_rate_below_threshold_returns_none(self, app):
        """Newsletter delivery failure rate below threshold returns no alert."""
        with app.app_context():
            from services.alerts import _check_newsletter_delivery_failures, AlertThresholds
            thresholds = AlertThresholds(newsletter_delivery_failure_rate=0.5)
            alert = _check_newsletter_delivery_failures(window_hours=24, threshold=0.5)
            assert alert is None


class TestCheckEstimatedCost:
    def test_cost_above_threshold_returns_info_alert(self, app):
        """Estimated cost above threshold returns info alert."""
        with app.app_context():
            from services.alerts import _check_estimated_cost, AlertThresholds
            thresholds = AlertThresholds(estimated_cost_threshold=50.0)
            with patch("services.metrics.get_metrics") as mock_get_metrics:
                mock_metrics = MagicMock()
                mock_metrics.get_metrics.return_value = {
                    "counters": {"llm.cost.dollars": 150.0},
                    "gauges": {},
                    "histograms": {},
                }
                mock_get_metrics.return_value = mock_metrics
                alert = _check_estimated_cost(window_hours=1, threshold=50.0)
                assert alert is not None
                assert alert.code == "ESTIMATED_COST_ABOVE_THRESHOLD"
                assert alert.severity == "info"

    def test_cost_below_threshold_returns_none(self, app):
        """Estimated cost below threshold returns no alert."""
        with app.app_context():
            from services.alerts import _check_estimated_cost, AlertThresholds
            thresholds = AlertThresholds(estimated_cost_threshold=100.0)
            with patch("services.metrics.get_metrics") as mock_get_metrics:
                mock_metrics = MagicMock()
                mock_metrics.get_metrics.return_value = {
                    "counters": {"llm.cost.dollars": 10.0},
                    "gauges": {},
                    "histograms": {},
                }
                mock_get_metrics.return_value = mock_metrics
                alert = _check_estimated_cost(window_hours=1, threshold=100.0)
                assert alert is None


class TestGetActiveAlerts:
    def test_returns_all_alerts(self, app):
        """get_active_alerts evaluates all checks."""
        with app.app_context():
            from services.alerts import get_active_alerts
            with patch("services.alerts._check_celery_workers", return_value=None):
                with patch("services.alerts._check_redis_available", return_value=None):
                    with patch("services.alerts._check_circuit_breaker_open", return_value=None):
                        with patch("services.alerts._check_pipeline_backlog", return_value=None):
                            with patch("services.alerts._check_stuck_articles", return_value=None):
                                with patch("services.alerts._check_source_failures", return_value=None):
                                    with patch("services.alerts._check_crawl_zero_articles", return_value=None):
                                        with patch("services.alerts._check_quality_gate_failures", return_value=None):
                                            with patch("services.alerts._check_newsletter_delivery_failures", return_value=None):
                                                with patch("services.alerts._check_estimated_cost", return_value=None):
                                                    alerts = get_active_alerts()
            assert alerts == []


class TestDispatchAlerts:
    def test_no_alerts_does_not_dispatch(self, app):
        """dispatch_alerts does nothing when no alerts."""
        with app.app_context():
            from services.alerts import dispatch_alerts
            with patch("services.webhooks.trigger_event") as mock_trigger:
                dispatch_alerts([])
                mock_trigger.assert_not_called()

    def test_non_critical_alerts_do_not_dispatch(self, app):
        """dispatch_alerts does not dispatch non-critical alerts."""
        with app.app_context():
            from services.alerts import dispatch_alerts, Alert
            alerts = [
                Alert(code="WARN", severity="warning", title="Warn", message="Warn", source="test"),
            ]
            with patch("services.webhooks.trigger_event") as mock_trigger:
                dispatch_alerts(alerts)
                mock_trigger.assert_not_called()

    def test_critical_alerts_dispatch(self, app):
        """dispatch_alerts triggers webhook for critical alerts."""
        with app.app_context():
            from services.alerts import dispatch_alerts, Alert
            alerts = [
                Alert(code="CRIT", severity="critical", title="Crit", message="Crit", source="test"),
            ]
            with patch("services.webhooks.trigger_event") as mock_trigger:
                dispatch_alerts(alerts)
                mock_trigger.assert_called_once()
                call_args = mock_trigger.call_args
                assert call_args[0][0] == "alert.critical"
                assert call_args[0][1]["critical_count"] == 1
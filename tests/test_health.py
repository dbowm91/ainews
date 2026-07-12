"""Tests for health service."""


class TestHealth:
    def test_health_result_is_healthy(self):
        from services.health import HealthResult

        r = HealthResult(status="ok", checks={})
        assert r.is_healthy is True
        assert r.to_dict()["status"] == "ok"

    def test_health_result_degraded(self):
        from services.health import HealthResult

        r = HealthResult(status="degraded", checks={"redis": "error"})
        assert r.is_healthy is True

    def test_health_result_unhealthy(self):
        from services.health import HealthResult

        r = HealthResult(status="unhealthy", checks={"database": {"status": "error"}})
        assert r.is_healthy is False

    def test_check_database(self, app):
        from services.health import check_database

        name, status = check_database()
        assert name == "database"
        assert status["status"] == "ok"

    def test_check_celery_connection_failure_is_degraded(self):
        from unittest.mock import patch

        from kombu.exceptions import OperationalError

        from services.health import check_celery

        with patch("celery_app.celery_app.control.inspect") as inspect:
            inspect.return_value.ping.side_effect = OperationalError("Redis unavailable")
            name, status = check_celery()

        assert name == "celery"
        assert status == "error"

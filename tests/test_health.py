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

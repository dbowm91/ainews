"""Tests for metrics service."""

import time


class TestMetricsExpansion:
    def test_time_histogram(self):
        from services.metrics import get_metrics, reset_metrics, time_histogram

        reset_metrics()
        with time_histogram("test.duration"):
            time.sleep(0.01)

        metrics = get_metrics().get_metrics()
        assert "test.duration" in metrics["histograms"]
        assert metrics["histograms"]["test.duration"]["count"] == 1

    def test_record_request(self):
        from services.metrics import get_metrics, record_request, reset_metrics

        reset_metrics()
        record_request("GET", "/api/test", 200, 42.5)

        metrics = get_metrics().get_metrics()
        assert "http_requests_total{method=GET,status=200}" in metrics["counters"]

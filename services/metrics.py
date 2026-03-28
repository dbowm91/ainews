"""Application metrics collection.

Provides in-memory counters, gauges, and histograms for monitoring.
Exposes metrics via a JSON endpoint suitable for scraping or health checks.
"""

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

_metrics_instance: Optional["MetricsCollector"] = None
_metrics_lock = threading.Lock()


class MetricsCollector:
    """Thread-safe in-memory metrics collector.

    Supports counters (increment only), gauges (set to value),
    and simple histograms (record observations).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.monotonic()

    def counter_inc(self, name: str, value: int = 1, labels: dict = None) -> None:
        """Increment a counter."""
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def gauge_set(self, name: str, value: float, labels: dict = None) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def histogram_observe(self, name: str, value: float, labels: dict = None) -> None:
        """Record a histogram observation."""
        key = self._make_key(name, labels)
        with self._lock:
            self._histograms[key].append(value)
            # Keep only last 1000 observations per metric
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]

    def _make_key(self, name: str, labels: dict = None) -> str:
        """Create a metric key with optional labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_metrics(self) -> dict[str, Any]:
        """Return all metrics as a structured dict."""
        with self._lock:
            result = {
                "uptime_seconds": round(time.monotonic() - self._start_time, 1),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {},
            }
            for key, values in self._histograms.items():
                if values:
                    sorted_vals = sorted(values)
                    result["histograms"][key] = {
                        "count": len(values),
                        "min": sorted_vals[0],
                        "max": sorted_vals[-1],
                        "avg": round(sum(values) / len(values), 3),
                        "p50": sorted_vals[len(sorted_vals) // 2],
                        "p95": sorted_vals[int(len(sorted_vals) * 0.95)],
                        "p99": sorted_vals[int(len(sorted_vals) * 0.99)],
                    }
            return result


def get_metrics() -> MetricsCollector:
    """Get or create the singleton MetricsCollector."""
    global _metrics_instance
    if _metrics_instance is not None:
        return _metrics_instance
    with _metrics_lock:
        if _metrics_instance is not None:
            return _metrics_instance
        _metrics_instance = MetricsCollector()
    return _metrics_instance


def reset_metrics() -> None:
    """Reset the singleton (for testing)."""
    global _metrics_instance
    with _metrics_lock:
        _metrics_instance = None

"""Application metrics collection.

Provides Redis-backed counters, gauges, and histograms for monitoring with
in-memory fallback when Redis is unavailable.
Exposes metrics via a JSON endpoint suitable for scraping or health checks.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Any, Optional

import redis.exceptions

logger = logging.getLogger(__name__)

_metrics_instance: Optional["MetricsCollector"] = None
_metrics_lock = threading.Lock()


class MetricsCollector:
    """Thread-safe metrics collector with Redis backend and in-memory fallback.

    Supports counters (increment only), gauges (set to value),
    and simple histograms (record observations).
    """

    _REDIS_PREFIX = "metrics"
    _GAUGE_TTL = 86400  # 24 hours TTL for gauges
    _HISTOGRAM_TTL = 3600  # 1 hour TTL for histogram keys

    def __init__(self, redis_client=None):
        self._lock = threading.Lock()
        self._redis = redis_client
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=1000),
        )
        self._start_time = time.monotonic()

    def counter_inc(
        self, name: str, value: int = 1, labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter."""
        key = self._make_key(name, labels)
        # Try Redis first
        try:
            if self._redis is not None:
                self._redis.incrby(f"{self._REDIS_PREFIX}:counter:{key}", value)
                return
        except redis.exceptions.RedisError:
            pass
        # Fallback to in-memory
        with self._lock:
            self._counters[key] += value

    def gauge_set(
        self, name: str, value: float, labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        # Try Redis first
        try:
            if self._redis is not None:
                redis_key = f"{self._REDIS_PREFIX}:gauge:{key}"
                self._redis.setex(redis_key, self._GAUGE_TTL, value)
                return
        except redis.exceptions.RedisError:
            pass
        # Fallback to in-memory
        with self._lock:
            self._gauges[key] = value

    def histogram_observe(
        self, name: str, value: float, labels: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram observation."""
        key = self._make_key(name, labels)
        # Try Redis first (store as JSON array of observations)
        try:
            if self._redis is not None:
                redis_key = f"{self._REDIS_PREFIX}:histogram:{key}"
                # Use Redis list to store observations, trim to maxlen
                pipe = self._redis.pipeline()
                pipe.rpush(redis_key, value)
                pipe.ltrim(redis_key, -1000, -1)  # Keep last 1000 observations
                pipe.expire(redis_key, self._HISTOGRAM_TTL)
                pipe.execute()
                return
        except redis.exceptions.RedisError:
            pass
        # Fallback to in-memory
        with self._lock:
            self._histograms[key].append(value)

    def _make_key(self, name: str, labels: dict[str, str] | None = None) -> str:
        """Create a metric key with optional labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def clear(self) -> None:
        """Clear all metrics (for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
        # Clear Redis keys if available
        if self._redis is not None:
            try:
                keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:*"))
                if keys:
                    self._redis.delete(*keys)
            except redis.exceptions.RedisError:
                pass

    def get_metrics(self) -> dict[str, Any]:
        """Return all metrics as a structured dict."""
        result = {
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "counters": {},
            "gauges": {},
            "histograms": {},
        }

        # Try to get counters from Redis
        try:
            if self._redis is not None:
                counter_keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:counter:*"))
                if counter_keys:
                    for key in counter_keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        metric_name = key_str.replace(f"{self._REDIS_PREFIX}:counter:", "", 1)
                        result["counters"][metric_name] = int(self._redis.get(key) or 0)
        except redis.exceptions.RedisError:
            pass

        # Fallback to in-memory counters if Redis failed or empty
        if not result["counters"]:
            with self._lock:
                result["counters"] = dict(self._counters)

        # Try to get gauges from Redis
        try:
            if self._redis is not None:
                gauge_keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:gauge:*"))
                if gauge_keys:
                    for key in gauge_keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        metric_name = key_str.replace(f"{self._REDIS_PREFIX}:gauge:", "", 1)
                        val = self._redis.get(key)
                        if val is not None:
                            result["gauges"][metric_name] = float(val)
        except redis.exceptions.RedisError:
            pass

        # Fallback to in-memory gauges if Redis failed or empty
        if not result["gauges"]:
            with self._lock:
                result["gauges"] = dict(self._gauges)

        # Try to get histograms from Redis
        try:
            if self._redis is not None:
                histogram_keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:histogram:*"))
                if histogram_keys:
                    for key in histogram_keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        metric_name = key_str.replace(f"{self._REDIS_PREFIX}:histogram:", "", 1)
                        values = [float(v) for v in self._redis.lrange(key, 0, -1)]
                        if values:
                            sorted_vals = sorted(values)
                            result["histograms"][metric_name] = {
                                "count": len(values),
                                "min": sorted_vals[0],
                                "max": sorted_vals[-1],
                                "avg": round(sum(values) / len(values), 3),
                                "p50": sorted_vals[len(sorted_vals) // 2],
                                "p95": sorted_vals[int(len(sorted_vals) * 0.95)],
                                "p99": sorted_vals[int(len(sorted_vals) * 0.99)],
                            }
        except redis.exceptions.RedisError:
            pass

        # Fallback to in-memory histograms if Redis failed or empty
        if not result["histograms"]:
            with self._lock:
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

    def get_prometheus(self) -> str:
        """Return metrics in Prometheus exposition format."""
        lines = []
        seen_types: set[str] = set()

        def _base_name(key: str) -> str:
            """Extract base metric name before any '{'."""
            brace_idx = key.find("{")
            return key if brace_idx == -1 else key[:brace_idx]

        # Collect all metrics first (from Redis with in-memory fallback)
        counters = {}
        gauges = {}
        histograms = {}

        # Try Redis first for counters
        try:
            if self._redis is not None:
                counter_keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:counter:*"))
                for key in counter_keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    metric_name = key_str.replace(f"{self._REDIS_PREFIX}:counter:", "", 1)
                    counters[metric_name] = int(self._redis.get(key) or 0)
        except redis.exceptions.RedisError:
            pass

        # Fallback to in-memory counters
        if not counters:
            with self._lock:
                counters = dict(self._counters)

        # Try Redis first for gauges
        try:
            if self._redis is not None:
                gauge_keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:gauge:*"))
                for key in gauge_keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    metric_name = key_str.replace(f"{self._REDIS_PREFIX}:gauge:", "", 1)
                    val = self._redis.get(key)
                    if val is not None:
                        gauges[metric_name] = float(val)
        except redis.exceptions.RedisError:
            pass

        # Fallback to in-memory gauges
        if not gauges:
            with self._lock:
                gauges = dict(self._gauges)

        # Try Redis first for histograms
        try:
            if self._redis is not None:
                histogram_keys = list(self._redis.scan_iter(f"{self._REDIS_PREFIX}:histogram:*"))
                for key in histogram_keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    metric_name = key_str.replace(f"{self._REDIS_PREFIX}:histogram:", "", 1)
                    values = [float(v) for v in self._redis.lrange(key, 0, -1)]
                    if values:
                        histograms[metric_name] = values
        except redis.exceptions.RedisError:
            pass

        # Fallback to in-memory histograms
        if not histograms:
            with self._lock:
                histograms = {k: list(v) for k, v in self._histograms.items() if v}

        # Counters
        for key, value in counters.items():
            base = _base_name(key)
            if base not in seen_types:
                seen_types.add(base)
                lines.append(f"# HELP {base} Incrementing counter metric")
                lines.append(f"# TYPE {base} counter")
            lines.append(f"{key} {value}")
        # Gauges
        for key, value in gauges.items():
            base = _base_name(key)
            if base not in seen_types:
                seen_types.add(base)
                lines.append(f"# HELP {base} Current gauge value")
                lines.append(f"# TYPE {base} gauge")
            lines.append(f"{key} {value}")
        # Histograms
        for key, values in histograms.items():
            if values:
                base = _base_name(key)
                if base not in seen_types:
                    seen_types.add(base)
                    lines.append(f"# HELP {base} Histogram metric")
                    lines.append(f"# TYPE {base} histogram")
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")
        return "\n".join(lines)


def get_metrics() -> MetricsCollector:
    """Get or create the singleton MetricsCollector."""
    global _metrics_instance
    if _metrics_instance is not None:
        return _metrics_instance
    with _metrics_lock:
        if _metrics_instance is not None:
            return _metrics_instance
        from extensions import get_redis
        try:
            redis_client = get_redis()
        except Exception:  # noqa: BLE001
            redis_client = None
        _metrics_instance = MetricsCollector(redis_client=redis_client)
    return _metrics_instance


def reset_metrics() -> None:
    """Reset the singleton (for testing). Clears Redis keys if available."""
    global _metrics_instance
    with _metrics_lock:
        if _metrics_instance is not None:
            _metrics_instance.clear()
        _metrics_instance = None


@contextmanager
def time_histogram(name: str, labels: dict[str, str] | None = None):
    """Context manager that records duration as a histogram observation.

    Usage:
        with time_histogram("pipeline.stage.duration", {"stage": "write"}):
            run_write_stage()
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        get_metrics().histogram_observe(name, duration, labels)


def record_request(
    method: str, path: str, status_code: int, duration_ms: float,
) -> None:
    """Record an HTTP request metric.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP status code
        duration_ms: Request duration in milliseconds
    """
    m = get_metrics()
    m.counter_inc(
        "http_requests_total",
        labels={"method": method, "status": str(status_code)},
    )
    m.histogram_observe("http_request_duration_ms", duration_ms)

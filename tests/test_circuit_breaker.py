"""Tests for the circuit breaker module."""

import pytest

_fake_time = 1000.0


def fake_monotonic():
    return _fake_time


def advance_time(seconds):
    global _fake_time
    _fake_time += seconds


@pytest.fixture(autouse=True)
def _reset_fake_clock():
    global _fake_time
    _fake_time = 1000.0
    yield
    _fake_time = 1000.0


@pytest.fixture(autouse=True)
def _patch_monotonic(monkeypatch):
    monkeypatch.setattr("services.circuit_breaker.time.monotonic", fake_monotonic)


class TestCircuitBreaker:
    """Test CircuitBreaker state transitions."""

    def _make_breaker(self, **kwargs):
        from services.circuit_breaker import CircuitBreaker

        defaults = dict(
            name="test",
            failure_threshold=3,
            recovery_timeout=0.5,
            half_open_max_calls=1,
            window_seconds=10.0,
        )
        defaults.update(kwargs)
        return CircuitBreaker(**defaults)

    def test_starts_closed(self):
        breaker = self._make_breaker()
        assert breaker.state.value == "closed"
        assert breaker.can_execute() is True

    def test_opens_after_threshold(self):
        breaker = self._make_breaker(failure_threshold=3)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state.value == "open"
        assert breaker.can_execute() is False

    def test_half_open_after_timeout(self):
        breaker = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state.value == "open"

        advance_time(0.15)
        assert breaker.state.value == "half_open"
        assert breaker.can_execute() is True

    def test_closes_on_success_in_half_open(self):
        breaker = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)

        breaker.can_execute()  # transition to half_open
        breaker.record_success()
        assert breaker.state.value == "closed"
        assert breaker.can_execute() is True

    def test_reopens_on_failure_in_half_open(self):
        breaker = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)

        breaker.can_execute()  # transition to half_open
        breaker.record_failure()
        assert breaker.state.value == "open"

    def test_half_open_limits_concurrent_calls(self):
        breaker = self._make_breaker(
            failure_threshold=2, recovery_timeout=0.1, half_open_max_calls=1
        )
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)

        assert breaker.can_execute() is True
        assert breaker.can_execute() is False  # second call rejected

    def test_old_failures_pruned(self):
        breaker = self._make_breaker(failure_threshold=3, window_seconds=0.1)
        breaker.record_failure()
        advance_time(0.15)
        breaker.record_failure()
        # Old failure should be pruned, only 1 counted
        assert breaker._failure_count == 1

    def test_get_status(self):
        breaker = self._make_breaker()
        status = breaker.get_status()
        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0


class TestGetBreaker:
    """Test the global breaker registry."""

    def test_returns_same_instance(self):
        from services.circuit_breaker import _breakers, get_breaker

        _breakers.clear()
        b1 = get_breaker("test-provider", failure_threshold=5)
        b2 = get_breaker("test-provider")
        assert b1 is b2

    def test_different_names_get_different_instances(self):
        from services.circuit_breaker import _breakers, get_breaker

        _breakers.clear()
        b1 = get_breaker("provider-a")
        b2 = get_breaker("provider-b")
        assert b1 is not b2


class TestCircuitProtected:
    """Test the @circuit_protected decorator."""

    def test_passes_through_when_closed(self):
        from services.circuit_breaker import _breakers, circuit_protected

        _breakers.clear()

        @circuit_protected("decorated-test")
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_raises_when_open(self):
        from services.circuit_breaker import (
            CircuitOpenError,
            _breakers,
            circuit_protected,
            get_breaker,
        )

        _breakers.clear()

        breaker = get_breaker("open-test", failure_threshold=1)
        breaker.record_failure()

        @circuit_protected("open-test")
        def my_func():
            return "ok"

        with pytest.raises(CircuitOpenError):
            my_func()

    def test_calls_fallback_when_open(self):
        from services.circuit_breaker import _breakers, circuit_protected, get_breaker

        _breakers.clear()

        breaker = get_breaker("fallback-test", failure_threshold=1)
        breaker.record_failure()

        def my_fallback():
            return "fallback"

        @circuit_protected("fallback-test", fallback=my_fallback)
        def my_func():
            return "ok"

        assert my_func() == "fallback"

    def test_records_failure_on_exception(self):
        from services.circuit_breaker import _breakers, circuit_protected, get_breaker

        _breakers.clear()

        @circuit_protected("fail-test")
        def my_func():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            my_func()

        breaker = get_breaker("fail-test")
        assert breaker._failure_count == 1

    def test_failure_in_half_open_reopens_circuit(self):
        from services.circuit_breaker import _breakers, circuit_protected, get_breaker

        _breakers.clear()

        breaker = get_breaker(
            "half-open-fail",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=2,
        )
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)
        breaker.can_execute()

        @circuit_protected("half-open-fail")
        def my_func():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            my_func()
        assert breaker.state.value == "open"

    def test_records_success_on_return(self):
        from services.circuit_breaker import _breakers, circuit_protected, get_breaker

        _breakers.clear()

        @circuit_protected("success-test")
        def my_func():
            return "ok"

        my_func()
        breaker = get_breaker("success-test")
        assert breaker.state.value == "closed"


class TestCircuitBreakerMetrics:
    """Test that circuit breaker emits metrics on state transitions."""

    def _make_breaker(self, **kwargs):
        from services.circuit_breaker import CircuitBreaker
        from services.metrics import get_metrics, reset_metrics

        reset_metrics()
        defaults = dict(
            name="test-metric",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=1,
            window_seconds=10.0,
        )
        defaults.update(kwargs)
        return CircuitBreaker(**defaults), get_metrics()

    def test_state_change_metric_on_open(self):
        breaker, metrics = self._make_breaker(failure_threshold=2)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state.value == "open"

        m = metrics.get_metrics()
        key = "circuit_breaker.state_change{from=closed,provider=test-metric,to=open}"
        assert m["counters"].get(key, 0) == 1

    def test_opened_counter_on_open(self):
        breaker, metrics = self._make_breaker(failure_threshold=2)
        breaker.record_failure()
        breaker.record_failure()

        m = metrics.get_metrics()
        assert m["counters"].get("circuit_breaker.opened{provider=test-metric}", 0) == 1

    def test_state_change_metric_on_half_open(self):
        breaker, metrics = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)
        assert breaker.state.value == "half_open"

        m = metrics.get_metrics()
        key = (
            "circuit_breaker.state_change{from=open,provider=test-metric,to=half_open}"
        )
        assert m["counters"].get(key, 0) == 1

    def test_state_change_metric_on_close_from_half_open(self):
        breaker, metrics = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)
        assert breaker.state.value == "half_open"
        breaker.record_success()

        m = metrics.get_metrics()
        key = "circuit_breaker.state_change{from=half_open,provider=test-metric,to=closed}"
        assert m["counters"].get(key, 0) == 1

    def test_reopen_from_half_open(self):
        breaker, metrics = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        breaker.record_failure()
        advance_time(0.15)
        assert breaker.state.value == "half_open"
        breaker.record_failure()

        m = metrics.get_metrics()
        key = (
            "circuit_breaker.state_change{from=half_open,provider=test-metric,to=open}"
        )
        assert m["counters"].get(key, 0) == 1
        # Should have 2 opened total (CLOSED->OPEN and HALF_OPEN->OPEN)
        assert m["counters"].get("circuit_breaker.opened{provider=test-metric}", 0) == 2

    def test_no_metric_without_transition(self):
        breaker, metrics = self._make_breaker(failure_threshold=5)
        breaker.record_failure()
        # Only 1 failure, threshold is 5 — no transition
        m = metrics.get_metrics()
        key = "circuit_breaker.state_change{from=closed,provider=test-metric,to=open}"
        assert m["counters"].get(key, 0) == 0

    def test_metrics_failure_does_not_break_breaker(self, monkeypatch):
        from services.metrics import get_metrics

        breaker, _ = self._make_breaker(failure_threshold=2)

        def boom(*args, **kwargs):
            raise RuntimeError("metrics down")

        monkeypatch.setattr(get_metrics(), "counter_inc", boom)

        # Should not raise — transitions still happen
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state.value == "open"

        advance_time(0.15)
        assert breaker.state.value == "half_open"
        breaker.record_success()
        assert breaker.state.value == "closed"

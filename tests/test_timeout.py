"""Tests for the timeout enforcement utilities."""

import time
import pytest
from services.timeout import timeout, OperationTimeoutError, TimeoutBudget


class TestTimeoutDecorator:
    """Tests for the @timeout decorator."""

    def test_returns_result_before_timeout(self):
        @timeout(5, operation="fast_op")
        def fast_func():
            return 42

        assert fast_func() == 42

    def test_raises_on_timeout(self):
        @timeout(0.1, operation="slow_op")
        def slow_func():
            time.sleep(5)

        with pytest.raises(OperationTimeoutError) as exc_info:
            slow_func()
        assert exc_info.value.operation == "slow_op"
        assert exc_info.value.timeout == 0.1

    def test_timeout_returns_promptly(self):
        """Verify that timeout does not block waiting for the stuck function."""

        @timeout(0.1, operation="prompt_check")
        def stuck_func():
            time.sleep(5)

        start = time.monotonic()
        with pytest.raises(OperationTimeoutError):
            stuck_func()
        elapsed = time.monotonic() - start
        # Should return within 2 seconds (generous for CI), not wait for 999s
        assert elapsed < 2.0

    def test_passes_args_and_kwargs(self):
        @timeout(5)
        def add(a, b, extra=0):
            return a + b + extra

        assert add(1, 2, extra=10) == 13

    def test_propagates_exception(self):
        @timeout(5)
        def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            fail()

    def test_default_operation_name(self):
        @timeout(0.1)
        def my_named_func():
            time.sleep(5)

        with pytest.raises(OperationTimeoutError) as exc_info:
            my_named_func()
        assert exc_info.value.operation == "my_named_func"


class TestTimeoutBudget:
    """Tests for TimeoutBudget."""

    def test_remaining_decreases(self):
        budget = TimeoutBudget(total=10)
        time.sleep(0.05)
        assert budget.remaining < 10

    def test_is_expired_false(self):
        budget = TimeoutBudget(total=10)
        assert not budget.is_expired

    def test_is_expired_true(self):
        budget = TimeoutBudget(total=0)
        time.sleep(0.01)
        assert budget.is_expired

    def test_check_raises_when_expired(self):
        budget = TimeoutBudget(total=0)
        time.sleep(0.01)
        with pytest.raises(OperationTimeoutError):
            budget.check("test_op")

    def test_check_passes_when_not_expired(self):
        budget = TimeoutBudget(total=60)
        budget.check("test_op")  # Should not raise

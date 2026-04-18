"""Tests for degradation/fallback service."""

import pytest


class TestDegradation:
    def test_degrade_on_failure_calls_fallback(self):
        from services.degradation import degrade_on_failure

        def primary():
            raise ValueError("fail")

        def fallback():
            return "fallback_result"

        @degrade_on_failure(fallback=fallback, exceptions=(ValueError,))
        def wrapped():
            return primary()

        assert wrapped() == "fallback_result"

    def test_degrade_on_failure_passes_through(self):
        from services.degradation import degrade_on_failure

        def fallback():
            return "fallback"

        @degrade_on_failure(fallback=fallback)
        def success():
            return "success"

        assert success() == "success"

    def test_fallback_chain_success(self):
        from services.degradation import fallback_chain

        result = fallback_chain(
            lambda: 1 / 0,
            lambda: "second",
            lambda: "third",
        )()
        assert result == "second"

    def test_fallback_chain_all_fail(self):
        from services.degradation import fallback_chain

        with pytest.raises(ZeroDivisionError):
            fallback_chain(
                lambda: 1 / 0,
                lambda: 2 / 0,
            )()

    def test_safe_default(self):
        from services.degradation import safe_default

        @safe_default(default=[], exceptions=(ValueError,))
        def failing():
            raise ValueError("oops")

        assert failing() == []

        @safe_default(default=42)
        def succeeding():
            return 100

        assert succeeding() == 100

"""Tests for subagent middleware."""

import logging




class TestMiddleware:
    """Test middleware classes."""

    def test_tool_middleware_base(self):
        from services.subagent.middleware import ToolMiddleware

        middleware = ToolMiddleware()
        result = []

        def dummy_func(x):
            result.append(x)
            return x * 2

        wrapped = middleware.wrap(dummy_func)
        assert wrapped(5) == 10
        assert result == [5]

    def test_logging_middleware_success(self, caplog):
        from services.subagent.middleware import LoggingMiddleware

        result = []
        middleware = LoggingMiddleware()

        def dummy_func(x):
            result.append(x)
            return x * 2

        wrapped = middleware.wrap(dummy_func)
        with caplog.at_level(logging.INFO):
            assert wrapped(5) == 10

        assert result == [5]
        assert "Tool dummy_func called" in caplog.text
        assert "Tool dummy_func completed" in caplog.text

    def test_logging_middleware_error(self, caplog):
        from services.subagent.middleware import LoggingMiddleware

        middleware = LoggingMiddleware()

        def dummy_func(x):
            raise ValueError("test error")

        wrapped = middleware.wrap(dummy_func)
        with caplog.at_level(logging.ERROR):
            try:
                wrapped(5)
            except ValueError:
                pass

        assert "Tool dummy_func failed" in caplog.text

    def test_timing_middleware_success(self, caplog):
        from services.subagent.middleware import TimingMiddleware

        middleware = TimingMiddleware()

        def dummy_func(x):
            return x * 2

        wrapped = middleware.wrap(dummy_func)
        with caplog.at_level(logging.DEBUG):
            assert wrapped(5) == 10

        assert "executed in" in caplog.text

    def test_timing_middleware_error(self, caplog):
        from services.subagent.middleware import TimingMiddleware

        middleware = TimingMiddleware()

        def dummy_func(x):
            raise ValueError("test error")

        wrapped = middleware.wrap(dummy_func)
        with caplog.at_level(logging.DEBUG):
            try:
                wrapped(5)
            except ValueError:
                pass

        assert "failed after" in caplog.text

    def test_error_handling_middleware_passes_through(self):
        from services.subagent.middleware import ErrorHandlingMiddleware

        middleware = ErrorHandlingMiddleware()

        def dummy_func(x):
            return x * 2

        wrapped = middleware.wrap(dummy_func)
        assert wrapped(5) == 10

    def test_error_handling_middleware_logs_error(self, caplog):
        from services.subagent.middleware import ErrorHandlingMiddleware

        middleware = ErrorHandlingMiddleware()

        def dummy_func(x):
            raise ValueError("test error")

        wrapped = middleware.wrap(dummy_func)
        with caplog.at_level(logging.ERROR):
            try:
                wrapped(5)
            except ValueError:
                pass

        assert "error" in caplog.text.lower()

    def test_apply_middleware_single(self):
        from services.subagent.middleware import (
            LoggingMiddleware,
            apply_middleware,
        )

        result = []
        middleware = LoggingMiddleware()

        def dummy_func(x):
            result.append(x)
            return x * 2

        wrapped = apply_middleware(dummy_func, [middleware])
        assert wrapped(5) == 10
        assert result == [5]

    def test_apply_middleware_chain(self):
        from services.subagent.middleware import (
            LoggingMiddleware,
            TimingMiddleware,
            apply_middleware,
        )

        log_records = []
        middleware1 = LoggingMiddleware()
        middleware2 = TimingMiddleware()

        def dummy_func(x):
            log_records.append("func_called")
            return x * 2

        wrapped = apply_middleware(dummy_func, [middleware1, middleware2])
        result = wrapped(5)
        assert result == 10
        assert len(log_records) == 1
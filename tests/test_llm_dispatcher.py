"""Provider-wide retry and concurrency dispatch contracts."""

from unittest.mock import MagicMock

import pytest

from services.llm.dispatcher import ProviderDispatcher
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError


class _Provider:
    provider_id = "test-provider"
    default_model = "test-model"
    max_concurrent = 2
    dispatcher_wait_timeout_seconds = 10
    dispatcher_slot_ttl_seconds = 180
    retry_attempts = 3
    retry_base_delay_seconds = 5.0
    retry_max_delay_seconds = 60.0

    def __init__(self):
        self._record_failure = MagicMock()


@pytest.fixture
def dispatcher(monkeypatch):
    provider = _Provider()
    limiter = MagicMock()
    limiter.acquire_provider.return_value = True
    monkeypatch.setattr("services.limiter.get_limiter", lambda: limiter)
    return ProviderDispatcher(provider), provider, limiter


def test_retries_transient_failures_and_releases_provider_slot(
    dispatcher, monkeypatch,
):
    runner, provider, limiter = dispatcher
    sleeps = []
    monkeypatch.setattr("services.llm.dispatcher.time.sleep", sleeps.append)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderServerError("temporary upstream failure")
        return "ok"

    assert runner.call(operation, "test-model") == "ok"
    assert calls == 3
    assert limiter.acquire_provider.call_count == 3
    assert limiter.release_provider.call_count == 3
    assert sleeps[0] == 5.0
    assert 5.0 <= sleeps[1] <= 10.0
    provider._record_failure.assert_not_called()


def test_does_not_retry_authentication_failures(dispatcher, monkeypatch):
    runner, _provider, limiter = dispatcher
    sleep = MagicMock()
    monkeypatch.setattr("services.llm.dispatcher.time.sleep", sleep)
    operation = MagicMock(side_effect=AuthError("invalid credentials"))

    with pytest.raises(AuthError):
        runner.call(operation, "test-model")

    operation.assert_called_once()
    limiter.release_provider.assert_called_once()
    sleep.assert_not_called()


def test_stream_retries_until_first_chunk(dispatcher, monkeypatch):
    runner, _provider, limiter = dispatcher
    monkeypatch.setattr("services.llm.dispatcher.time.sleep", lambda _delay: None)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProviderTimeoutError("temporary timeout")
        yield "first"
        yield "second"

    assert list(runner.stream(operation, "test-model")) == ["first", "second"]
    assert calls == 2
    assert limiter.acquire_provider.call_count == 2
    assert limiter.release_provider.call_count == 2


def test_stream_does_not_restart_after_emitting_a_chunk(dispatcher, monkeypatch):
    runner, _provider, limiter = dispatcher
    monkeypatch.setattr("services.llm.dispatcher.time.sleep", lambda _delay: None)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        yield "partial"
        raise ProviderTimeoutError("stream closed")

    iterator = runner.stream(operation, "test-model")
    assert next(iterator) == "partial"
    with pytest.raises(ProviderTimeoutError):
        next(iterator)
    assert calls == 1
    limiter.release_provider.assert_called_once()

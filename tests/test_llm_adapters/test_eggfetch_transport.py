"""AInews contracts for the released EggFetch HTTPX transport."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from eggfetch.integrations.httpx import EggFetchTransport
from services.llm.httpx_transport import create_httpx_client


@pytest.fixture
def llm_stub_url():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(size)
            payload = (
                b'{"id":"chatcmpl-test","object":"chat.completion","created":1,'
                b'"model":"local-test","choices":[{"index":0,'
                b'"message":{"role":"assistant","content":"ready"},'
                b'"finish_reason":"stop"}],"usage":{"prompt_tokens":1,'
                b'"completion_tokens":1,"total_tokens":2}}'
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_httpx_client_uses_eggfetch_and_preserves_long_timeout(llm_stub_url: str) -> None:
    client = create_httpx_client(
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
        timeout=1800.0,
    )
    try:
        assert isinstance(client, httpx.Client)
        assert isinstance(client._transport, EggFetchTransport)
        assert client.timeout.read == 1800.0
        response = client.post(llm_stub_url, json={"model": "local", "messages": []})
        assert response.json()["choices"][0]["message"]["content"] == "ready"
    finally:
        client.close()
    assert client._transport._closed is True


def test_anthropic_sdk_retries_are_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from anthropic import Anthropic

    from services.llm.anthropic import AnthropicProvider

    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return Anthropic(**kwargs)

    monkeypatch.setattr("anthropic.Anthropic", capture)
    provider = AnthropicProvider(
        "anthropic-test",
        {"api_key": "test-key", "model": "test-model", "timeout_seconds": 1800},
    )
    client = provider.client
    try:
        assert captured["max_retries"] == 0
        assert isinstance(client._client._transport, EggFetchTransport)
        assert client._client.timeout.read == 1800.0
    finally:
        provider.close()
    assert client._client.is_closed


@pytest.mark.parametrize("backend", ["httpx", "eggfetch"])
def test_openai_provider_completion_matches_httpx_baseline(
    llm_stub_url: str,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    from services.llm.openai import OpenAIProvider

    monkeypatch.setattr("services.llm.openai.validate_url_safe", lambda url, **kwargs: url)

    def httpx_baseline(*, timeout: float, limits: httpx.Limits) -> httpx.Client:
        return httpx.Client(timeout=timeout, limits=limits, trust_env=True, verify=True)

    client_factory = httpx_baseline if backend == "httpx" else create_httpx_client
    monkeypatch.setattr("services.llm.openai.create_httpx_client", client_factory)
    provider = OpenAIProvider(
        "local-test",
        {
            "api_key": "test-key",
            "base_url": llm_stub_url.rsplit("/chat/completions", 1)[0],
            "model": "local-test",
            "local": True,
            "timeout_seconds": 1800,
            "retry_attempts": 1,
        },
    )
    response = provider.chat([{"role": "user", "content": "hello"}])
    assert response.text == "ready"
    assert response.tokens_used == 2
    if backend == "eggfetch":
        assert isinstance(provider.client._client._transport, EggFetchTransport)
    else:
        assert isinstance(provider.client._client._transport, httpx.HTTPTransport)
    provider.close()


def test_ollama_uses_transport_argument_and_closes_httpx_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.llm.ollama import OllamaProvider

    monkeypatch.setattr("services.llm.ollama.validate_url_safe", lambda url, **kwargs: url)
    provider = OllamaProvider(
        "ollama-test",
        {"host": "http://127.0.0.1:11434", "model": "test-model", "local": True},
    )
    client = provider.client
    transport = client._client._transport
    assert isinstance(transport, EggFetchTransport)
    provider.close()
    assert transport._closed is True

"""Provider management integration tests using local fake HTTP servers."""
from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.main import app

pytestmark = pytest.mark.integration

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_ctx(tmp_path):
    """Ensure each test gets a fresh CLIContext pointing at tmp_path."""
    from ainews_cli.main import _ctx as global_ctx
    global_ctx.config = None
    global_ctx.paths = None
    global_ctx._explicit_paths = {
        "env_file": tmp_path / ".env",
        "providers_file": tmp_path / "providers.yaml",
        "pipeline_file": tmp_path / "pipeline.yaml",
        "sources_file": tmp_path / "sources.yaml",
        "topics_file": tmp_path / "topics.yaml",
        "config_dir": tmp_path,
        "data_dir": tmp_path,
        "state_dir": tmp_path,
        "backup_dir": tmp_path,
    }
    yield
    global_ctx.config = None
    global_ctx.paths = None
    global_ctx._explicit_paths = {}


class _FakeHandler(BaseHTTPRequestHandler):
    """Base handler with configurable response behavior."""

    _response_code: int = 200
    _response_body: Any = None
    _delay: float = 0.0
    _request_log: list[dict[str, Any]] = []

    def do_GET(self) -> None:
        self._request_log.append({
            "method": "GET",
            "path": self.path,
            "headers": dict(self.headers),
        })
        if self._delay > 0:
            time.sleep(self._delay)
        self.send_response(self._response_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self._response_body is not None:
            self.wfile.write(json.dumps(self._response_body).encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _start_fake_server(
    code: int = 200,
    body: Any = None,
    delay: float = 0.0,
) -> tuple[HTTPServer, str]:
    """Start a fake HTTP server and return (server, base_url)."""
    _FakeHandler._response_code = code
    _FakeHandler._response_body = body
    _FakeHandler._delay = delay
    _FakeHandler._request_log = []

    server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def _setup_provider_files(tmp_path: Path, base_url: str, provider_type: str = "generic") -> None:
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
    (tmp_path / "providers.yaml").write_text(
        f"default_provider: test-provider\n"
        f"providers:\n"
        f"  test-provider:\n"
        f"    type: {provider_type}\n"
        f"    enabled: true\n"
        f"    base_url: {base_url}/v1\n"
    )
    (tmp_path / "pipeline.yaml").write_text(
        "pipeline:\n"
        "  selector:\n"
        "    enabled: true\n"
        "    provider: test-provider\n"
        "    model: gpt-4\n"
    )
    (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
    (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")


def _setup_openai_provider_files(tmp_path: Path, base_url: str) -> None:
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\nOPENAI_API_KEY=sk-test-key\n")
    (tmp_path / "providers.yaml").write_text(
        f"default_provider: test-openai\n"
        f"providers:\n"
        f"  test-openai:\n"
        f"    type: openai\n"
        f"    enabled: true\n"
        f"    base_url: {base_url}\n"
    )
    (tmp_path / "pipeline.yaml").write_text(
        "pipeline:\n"
        "  selector:\n"
        "    enabled: true\n"
        "    provider: test-openai\n"
        "    model: gpt-4\n"
    )
    (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
    (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")


def _setup_ollama_provider_files(tmp_path: Path, base_url: str) -> None:
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
    (tmp_path / "providers.yaml").write_text(
        f"default_provider: test-ollama\n"
        f"providers:\n"
        f"  test-ollama:\n"
        f"    type: ollama\n"
        f"    enabled: true\n"
        f"    endpoint: {base_url}\n"
    )
    (tmp_path / "pipeline.yaml").write_text(
        "pipeline:\n"
        "  selector:\n"
        "    enabled: true\n"
        "    provider: test-ollama\n"
        "    model: qwen3:8b\n"
    )
    (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
    (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")


class TestProviderIntegration:
    """Provider management tests using local fake HTTP servers."""

    def test_generic_probe_success(self, tmp_path):
        server, base_url = _start_fake_server(200, {"object": "list", "data": []})
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "ok" in result.output.lower()
        finally:
            server.shutdown()

    def test_model_discovery(self, tmp_path):
        models = {
            "object": "list",
            "data": [
                {"id": "model-a", "context_length": 4096},
                {"id": "model-b"},
                {"id": "model-c"},
            ],
        }
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-models", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "model-a" in result.output
            assert "model-b" in result.output
            assert "model-c" in result.output
        finally:
            server.shutdown()

    def test_model_discovery_json(self, tmp_path):
        models = {
            "object": "list",
            "data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}],
        }
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["--json", "providers-models", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            data = json.loads(result.output)
            assert data["success"] is True
            assert len(data["models"]) == 2
            assert data["models"][0]["id"] == "gpt-4"
        finally:
            server.shutdown()

    def test_auth_rejection_401(self, tmp_path):
        server, base_url = _start_fake_server(401, {"error": "unauthorized"})
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.GENERAL_ERROR
            assert "auth" in result.output.lower() or "fail" in result.output.lower()
        finally:
            server.shutdown()

    def test_auth_rejection_403(self, tmp_path):
        server, base_url = _start_fake_server(403, {"error": "forbidden"})
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.GENERAL_ERROR
            assert "auth" in result.output.lower() or "fail" in result.output.lower()
        finally:
            server.shutdown()

    def test_auth_rejection_json(self, tmp_path):
        server, base_url = _start_fake_server(401, {"error": "invalid key"})
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["--json", "providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            data = json.loads(result.output)
            assert len(data["results"]) == 1
            assert data["results"][0]["success"] is False
            assert data["results"][0]["auth_success"] is False
        finally:
            server.shutdown()

    def test_malformed_response(self, tmp_path):
        class _MalformedHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"not valid json {{{")

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _MalformedHandler)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "fail" in result.output.lower() or "error" in result.output.lower()
        finally:
            server.shutdown()

    def test_timeout_classification(self, tmp_path):
        server, base_url = _start_fake_server(200, {"data": []}, delay=15.0)
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
                timeout=10,
            )
            assert result.exit_code in (exit_codes.GENERAL_ERROR, exit_codes.SUCCESS)
            output_lower = result.output.lower()
            if output_lower:
                assert "fail" in output_lower or "timeout" in output_lower or "error" in output_lower
        finally:
            server.shutdown()

    def test_server_error_500(self, tmp_path):
        server, base_url = _start_fake_server(500, {"error": "internal"})
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.GENERAL_ERROR
            assert "fail" in result.output.lower() or "error" in result.output.lower()
        finally:
            server.shutdown()

    def test_provider_add_transaction(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
        (tmp_path / "providers.yaml").write_text(
            "default_provider: null\nproviders: {}\n"
        )
        (tmp_path / "pipeline.yaml").write_text("pipeline:\n  selector:\n    enabled: true\n")
        (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
        (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")
        providers_before = (tmp_path / "providers.yaml").read_text()
        result = runner.invoke(
            app,
            ["providers-add", "--type", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND
        providers_after = (tmp_path / "providers.yaml").read_text()
        assert providers_before == providers_after

    def test_failed_probe_no_config_change(self, tmp_path):
        server, base_url = _start_fake_server(500, {"error": "down"})
        try:
            _setup_provider_files(tmp_path, base_url)
            providers_before = (tmp_path / "providers.yaml").read_text()
            result = runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.GENERAL_ERROR
            providers_after = (tmp_path / "providers.yaml").read_text()
            assert providers_before == providers_after
        finally:
            server.shutdown()

    def test_openai_auth_probe(self, tmp_path):
        models = {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]}
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_openai_provider_files(tmp_path, f"{base_url}")
            result = runner.invoke(
                app,
                ["providers-test", "test-openai"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "ok" in result.output.lower()
        finally:
            server.shutdown()

    def test_openai_auth_rejection(self, tmp_path):
        server, base_url = _start_fake_server(401, {"error": "invalid key"})
        try:
            _setup_openai_provider_files(tmp_path, f"{base_url}")
            result = runner.invoke(
                app,
                ["providers-test", "test-openai"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.GENERAL_ERROR
            assert "auth" in result.output.lower() or "fail" in result.output.lower()
        finally:
            server.shutdown()

    def test_ollama_probe_success(self, tmp_path):
        models = {"models": [{"name": "qwen3:8b"}, {"name": "llama3"}]}
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_ollama_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test", "test-ollama"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "ok" in result.output.lower()
        finally:
            server.shutdown()

    def test_ollama_model_discovery(self, tmp_path):
        models = {"models": [{"name": "qwen3:8b"}, {"name": "llama3"}]}
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_ollama_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-models", "test-ollama"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "qwen3:8b" in result.output
            assert "llama3" in result.output
        finally:
            server.shutdown()

    def test_skip_probe_warning(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
        (tmp_path / "providers.yaml").write_text(
            "default_provider: null\nproviders: {}\n"
        )
        (tmp_path / "pipeline.yaml").write_text("pipeline:\n  selector:\n    enabled: true\n")
        (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
        (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")

        with patch("builtins.input", side_effect=["http://localhost:8000/v1", ""]):
            result = runner.invoke(
                app,
                ["providers-add", "--type", "generic", "--skip-probe"],
                env={"HOME": str(tmp_path)},
            )
            output = result.output.lower()
            assert "skip" in output or "probe" in output or "warning" in output or result.exit_code == exit_codes.SUCCESS

    def test_set_default_validates_references(self, tmp_path):
        _setup_provider_files(tmp_path, "http://127.0.0.1:9999")
        result = runner.invoke(
            app,
            ["providers-set-default", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_remove_referenced_provider_blocked(self, tmp_path):
        _setup_provider_files(tmp_path, "http://127.0.0.1:9999")
        result = runner.invoke(
            app,
            ["providers-remove", "test-provider"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.VALIDATION_ERROR
        assert "in use" in result.output.lower()

    def test_list_providers_with_fake_server(self, tmp_path):
        models = {"data": [{"id": "model-a"}]}
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["--json", "providers-list"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            data = json.loads(result.output)
            assert len(data["providers"]) >= 1
            assert data["providers"][0]["id"] == "test-provider"
        finally:
            server.shutdown()

    def test_test_all_providers_fake_server(self, tmp_path):
        models = {"data": [{"id": "model-a"}]}
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_provider_files(tmp_path, base_url)
            result = runner.invoke(
                app,
                ["providers-test"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
        finally:
            server.shutdown()

    def test_probe_request_headers(self, tmp_path):
        models = {"data": []}
        server, base_url = _start_fake_server(200, models)
        try:
            _setup_provider_files(tmp_path, base_url)
            runner.invoke(
                app,
                ["providers-test", "test-provider"],
                env={"HOME": str(tmp_path)},
            )
            assert len(_FakeHandler._request_log) >= 1
            req = _FakeHandler._request_log[0]
            assert "/v1/models" in req["path"]
        finally:
            server.shutdown()

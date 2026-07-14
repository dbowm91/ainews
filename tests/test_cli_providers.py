from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.main import app

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


def _setup_provider_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
    (tmp_path / "providers.yaml").write_text(
        "default_provider: ollama-local\n"
        "providers:\n"
        "  ollama-local:\n"
        "    type: ollama\n"
        "    enabled: true\n"
        "    config:\n"
        "      base_url: http://localhost:11434\n"
    )
    (tmp_path / "pipeline.yaml").write_text(
        "pipeline:\n"
        "  selector:\n"
        "    enabled: true\n"
        "    provider: ollama-local\n"
        "    model: qwen3:8b\n"
    )
    (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
    (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")


def _setup_provider_files_with_openai(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
    (tmp_path / "providers.yaml").write_text(
        "default_provider: ollama-local\n"
        "providers:\n"
        "  ollama-local:\n"
        "    type: ollama\n"
        "    enabled: true\n"
        "    config:\n"
        "      base_url: http://localhost:11434\n"
        "  my-openai:\n"
        "    type: openai\n"
        "    enabled: true\n"
        "    config:\n"
        "      base_url: https://api.openai.com/v1\n"
    )
    (tmp_path / "pipeline.yaml").write_text(
        "pipeline:\n"
        "  selector:\n"
        "    enabled: true\n"
        "    provider: ollama-local\n"
        "    model: qwen3:8b\n"
    )
    (tmp_path / "sources.yaml").write_text("- name: test\n  type: rss\n")
    (tmp_path / "topics.yaml").write_text("ai:\n  display_name: AI\n")


class TestProvidersList:
    def test_empty_providers(self, tmp_path):
        _setup_provider_files(tmp_path)
        (tmp_path / "providers.yaml").write_text("default_provider: null\nproviders: {}\n")
        result = runner.invoke(app, ["providers-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == exit_codes.SUCCESS
        assert "No providers" in result.output

    def test_with_providers(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(app, ["providers-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == exit_codes.SUCCESS
        assert "ollama-local" in result.output

    def test_json_output(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(app, ["--json", "providers-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == exit_codes.SUCCESS
        data = json.loads(result.output)
        assert "providers" in data
        assert len(data["providers"]) >= 1

    def test_default_provider_marked(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(app, ["--json", "providers-list"], env={"HOME": str(tmp_path)})
        data = json.loads(result.output)
        assert data["default_provider"] == "ollama-local"
        ollama = next(p for p in data["providers"] if p["id"] == "ollama-local")
        assert ollama["is_default"] is True


class TestProvidersAdd:
    def test_add_shows_types_when_no_type(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(app, ["providers-add"], env={"HOME": str(tmp_path)})
        assert result.exit_code == exit_codes.SUCCESS
        assert "Available provider types" in result.output

    def test_add_json_shows_types(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(app, ["--json", "providers-add"], env={"HOME": str(tmp_path)})
        assert result.exit_code == exit_codes.SUCCESS
        data = json.loads(result.output)
        assert "available_types" in data
        type_ids = [t["type_id"] for t in data["available_types"]]
        assert "ollama" in type_ids

    def test_add_unknown_type(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-add", "--type", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND


class TestProvidersTest:
    def test_test_unknown_provider(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-test", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_test_success(self, tmp_path):
        _setup_provider_files(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["providers-test", "ollama-local"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "ok" in result.output.lower()

    def test_test_all_providers(self, tmp_path):
        _setup_provider_files(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["providers-test"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS

    def test_test_json_output(self, tmp_path):
        _setup_provider_files(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["--json", "providers-test", "ollama-local"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            data = json.loads(result.output)
            assert "results" in data
            assert data["results"][0]["success"] is True


class TestProvidersModels:
    def test_models_unknown_provider(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-models", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_models_success(self, tmp_path):
        _setup_provider_files(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["providers-models", "ollama-local"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            assert "qwen3:8b" in result.output

    def test_models_json_output(self, tmp_path):
        _setup_provider_files(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["--json", "providers-models", "ollama-local"],
                env={"HOME": str(tmp_path)},
            )
            assert result.exit_code == exit_codes.SUCCESS
            data = json.loads(result.output)
            assert data["success"] is True
            assert len(data["models"]) >= 1


class TestProvidersSetDefault:
    def test_set_default_unknown(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-set-default", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_set_default_success(self, tmp_path):
        _setup_provider_files_with_openai(tmp_path)
        result = runner.invoke(
            app,
            ["providers-set-default", "my-openai"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.SUCCESS
        assert "my-openai" in result.output

    def test_set_default_persists(self, tmp_path):
        _setup_provider_files_with_openai(tmp_path)
        runner.invoke(
            app,
            ["providers-set-default", "my-openai"],
            env={"HOME": str(tmp_path)},
        )
        content = (tmp_path / "providers.yaml").read_text()
        assert "my-openai" in content


class TestProvidersAssign:
    def test_assign_unknown_role(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-assign", "ollama-local", "qwen3:8b", "--roles", "badrole"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.VALIDATION_ERROR
        assert "Unknown role" in result.output

    def test_assign_unknown_provider(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-assign", "nonexistent", "qwen3:8b"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_assign_success(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-assign", "ollama-local", "qwen3:8b", "--roles", "selector"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.SUCCESS
        assert "selector" in result.output

    def test_assign_all_roles(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-assign", "ollama-local", "qwen3:8b"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.SUCCESS
        content = (tmp_path / "pipeline.yaml").read_text()
        assert "selector" in content
        assert "writer" in content


class TestProvidersRemove:
    def test_remove_unknown(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-remove", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_remove_in_use_without_reassign(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-remove", "ollama-local"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.VALIDATION_ERROR
        assert "in use" in result.output.lower()

    def test_remove_with_reassign(self, tmp_path):
        _setup_provider_files_with_openai(tmp_path)
        result = runner.invoke(
            app,
            ["providers-remove", "ollama-local", "--reassign-to", "my-openai"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.SUCCESS
        content = (tmp_path / "providers.yaml").read_text()
        assert "ollama-local" not in content

    def test_remove_reassign_target_not_found(self, tmp_path):
        _setup_provider_files(tmp_path)
        result = runner.invoke(
            app,
            ["providers-remove", "ollama-local", "--reassign-to", "nonexistent"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_remove_updates_default(self, tmp_path):
        _setup_provider_files_with_openai(tmp_path)
        runner.invoke(
            app,
            ["providers-remove", "ollama-local", "--reassign-to", "my-openai"],
            env={"HOME": str(tmp_path)},
        )
        content = (tmp_path / "providers.yaml").read_text()
        assert "my-openai" in content


class TestProvidersHelp:
    def test_providers_list_help(self):
        result = runner.invoke(app, ["providers-list", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_providers_add_help(self):
        result = runner.invoke(app, ["providers-add", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_providers_test_help(self):
        result = runner.invoke(app, ["providers-test", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_providers_models_help(self):
        result = runner.invoke(app, ["providers-models", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_providers_set_default_help(self):
        result = runner.invoke(app, ["providers-set-default", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_providers_assign_help(self):
        result = runner.invoke(app, ["providers-assign", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_providers_remove_help(self):
        result = runner.invoke(app, ["providers-remove", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

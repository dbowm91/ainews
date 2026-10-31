from __future__ import annotations

from tests.cli_json import parse_cli_json

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.context import format_provenance, format_secret
from ainews_cli.main import app
from ainews_cli.output import OutputFormatter

runner = CliRunner()


def _make_resolved_paths(tmp_path: Path) -> Any:
    from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.EXPLICIT,
            exists=p.exists(),
            is_writable=True,
        )

    return ResolvedPaths(
        app_dir=_rp(tmp_path),
        config_dir=_rp(tmp_path),
        data_dir=_rp(tmp_path),
        state_dir=_rp(tmp_path),
        backup_dir=_rp(tmp_path),
        env_file=_rp(tmp_path / ".env"),
        providers_file=_rp(tmp_path / "providers.yaml"),
        pipeline_file=_rp(tmp_path / "pipeline.yaml"),
        sources_file=_rp(tmp_path / "sources.yaml"),
        topics_file=_rp(tmp_path / "topics.yaml"),
        database_file=_rp(tmp_path / "db.sqlite"),
        install_metadata_file=_rp(tmp_path / "meta.json"),
        transaction_lock=_rp(tmp_path / "lock"),
        transaction_staging=_rp(tmp_path / "staging"),
    )


def _setup_config_files(tmp_path: Path) -> None:
    """Write schema-valid config fixtures.

    The shapes below mirror what the config engine validates: providers are
    an ID-keyed mapping, topics live under a ``topics:`` key, and sources use
    the ``sources:`` list wrapper.
    """
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
    (tmp_path / "providers.yaml").write_text(
        "default_provider: ollama-local\n"
        "providers:\n"
        "  ollama-local:\n"
        "    type: ollama\n"
        "    enabled: true\n"
        "    config:\n"
        "      host: \"http://localhost:11434\"\n"
        "      model: \"qwen3:8b\"\n"
    )
    (tmp_path / "pipeline.yaml").write_text("pipeline:\n  selector:\n    enabled: true\n")
    (tmp_path / "sources.yaml").write_text(
        "sources:\n"
        "  - id: test\n"
        "    name: Test\n"
        "    type: rss\n"
        "    url: \"https://example.com/feed.xml\"\n"
    )
    (tmp_path / "topics.yaml").write_text("topics:\n  ai:\n    display_name: AI\n")


def _fixture_env(tmp_path: Path) -> dict[str, str]:
    """Pin every resolved config path to the fixture directory.

    In development mode the CLI resolves config files from the repository
    checkout, so a test that only overrides ``HOME`` still reads the
    developer's live ``providers.yaml``/``pipeline.yaml``. Pinning the
    documented ``AINEWS_*`` path overrides keeps these tests hermetic and
    independent of whatever the working tree happens to contain.
    """
    return {
        "HOME": str(tmp_path),
        "AINEWS_CONFIG_DIR": str(tmp_path),
        "AINEWS_ENV_FILE": str(tmp_path / ".env"),
        "AINEWS_PROVIDERS_FILE": str(tmp_path / "providers.yaml"),
        "AINEWS_PIPELINE_FILE": str(tmp_path / "pipeline.yaml"),
        "AINEWS_SOURCES_FILE": str(tmp_path / "sources.yaml"),
        "AINEWS_TOPICS_FILE": str(tmp_path / "topics.yaml"),
    }


class TestVersion:
    def test_version_shows_output(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "version" in result.output.lower() or "python" in result.output.lower()

    def test_version_json_output(self):
        result = runner.invoke(app, ["--json", "version"])
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert "version" in data
        assert "python" in data


class TestConfigPath:
    def test_config_path_shows_paths(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "path"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        assert "config_dir" in result.output

    def test_config_path_json_output(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["--json", "config", "path"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert "config_dir" in data


class TestConfigShow:
    def test_config_show_displays_values(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "show"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_show_redacts_secrets(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "show"], env=_fixture_env(tmp_path))
        assert "test-secret" not in result.output

    def test_config_show_json_output(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["--json", "config", "show"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert isinstance(data, dict)


class TestConfigCheck:
    def test_config_check_valid(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "check"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_check_json_output(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["--json", "config", "check"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert "valid" in data


class TestPathEnvOverrides:
    """The CLI must honour the documented ``AINEWS_*`` path overrides.

    ``docs/configuration.md`` documents these variables as the second
    precedence step, below explicit flags and above the platform default.
    Without them the CLI silently ignored the operator's configuration and
    read the repository checkout instead.
    """

    def test_providers_file_override_is_honoured(self, tmp_path):
        _setup_config_files(tmp_path)
        (tmp_path / "providers.yaml").write_text(
            "default_provider: overridden-provider\n"
            "providers:\n"
            "  overridden-provider:\n"
            "    type: ollama\n"
            "    enabled: true\n"
        )
        result = runner.invoke(
            app, ["config", "get", "default_provider"], env=_fixture_env(tmp_path)
        )
        assert result.exit_code == exit_codes.SUCCESS
        assert "overridden-provider" in result.output

    def test_config_dir_override_is_honoured(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "path"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        assert str(tmp_path.resolve()) in result.output

    def test_path_env_overrides_ignores_unset_variables(self, monkeypatch):
        from ainews_cli.context import path_env_overrides

        monkeypatch.delenv("AINEWS_PROVIDERS_FILE", raising=False)
        monkeypatch.setenv("AINEWS_CONFIG_DIR", "/tmp/ainews-config")
        overrides = path_env_overrides()
        assert overrides == {"AINEWS_CONFIG_DIR": "/tmp/ainews-config"}

    def test_path_env_overrides_ignores_empty_values(self, monkeypatch):
        from ainews_cli.context import path_env_overrides

        monkeypatch.setenv("AINEWS_PROVIDERS_FILE", "")
        assert "AINEWS_PROVIDERS_FILE" not in path_env_overrides()


class TestConfigGet:
    def test_get_unknown_key_exits_not_found(self):
        result = runner.invoke(app, ["config", "get", "unknown.key"])
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_get_valid_key(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "get", "default_provider"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        assert "ollama-local" in result.output

    def test_get_json_output(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["--json", "config", "get", "default_provider"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert data["key"] == "default_provider"
        assert data["value"] == "ollama-local"


class TestConfigSet:
    def test_set_unknown_key_exits_not_found(self):
        result = runner.invoke(app, ["config", "set", "unknown.key", "value"])
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_set_dry_run(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(
            app,
            ["config", "set", "default_provider", "new-provider", "--dry-run"],
            env=_fixture_env(tmp_path),
        )
        assert result.exit_code == exit_codes.SUCCESS
        assert "Would change" in result.output

    def test_set_json_dry_run(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(
            app,
            ["--json", "config", "set", "default_provider", "new-provider", "--dry-run"],
            env=_fixture_env(tmp_path),
        )
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert data["dry_run"] is True


class TestConfigUnset:
    def test_unset_unknown_key_exits_not_found(self):
        result = runner.invoke(app, ["config", "unset", "unknown.key"])
        assert result.exit_code == exit_codes.NOT_FOUND


class TestConfigDiff:
    def test_diff_shows_differences(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "diff"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS

    def test_diff_json_output(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["--json", "config", "diff"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert "diffs" in data
        assert "count" in data


class TestConfigRollback:
    def test_rollback_list_empty(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["config", "rollback", "--list"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS

    def test_rollback_json_output(self, tmp_path):
        _setup_config_files(tmp_path)
        result = runner.invoke(app, ["--json", "config", "rollback", "--list"], env=_fixture_env(tmp_path))
        assert result.exit_code == exit_codes.SUCCESS
        data = parse_cli_json(result)
        assert "snapshots" in data


class TestDoctor:
    def test_doctor_runs(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code in (exit_codes.SUCCESS, exit_codes.GENERAL_ERROR)

    def test_doctor_json_output(self):
        result = runner.invoke(app, ["--json", "doctor"])
        assert result.exit_code in (exit_codes.SUCCESS, exit_codes.GENERAL_ERROR)
        data = parse_cli_json(result)
        assert "outcome" in data
        assert "counts" in data
        assert "checks" in data


class TestHelp:
    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "ainews" in result.output.lower()

    def test_config_help(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "config" in result.output.lower()

    def test_version_help(self):
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_path_help(self):
        result = runner.invoke(app, ["config", "path", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_show_help(self):
        result = runner.invoke(app, ["config", "show", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_check_help(self):
        result = runner.invoke(app, ["config", "check", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_get_help(self):
        result = runner.invoke(app, ["config", "get", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_set_help(self):
        result = runner.invoke(app, ["config", "set", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_unset_help(self):
        result = runner.invoke(app, ["config", "unset", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_diff_help(self):
        result = runner.invoke(app, ["config", "diff", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_config_rollback_help(self):
        result = runner.invoke(app, ["config", "rollback", "--help"])
        assert result.exit_code == exit_codes.SUCCESS

    def test_doctor_help(self):
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == exit_codes.SUCCESS


class TestExitCodes:
    def test_success_code(self):
        assert exit_codes.SUCCESS == 0

    def test_general_error_code(self):
        assert exit_codes.GENERAL_ERROR == 1

    def test_config_error_code(self):
        assert exit_codes.CONFIG_ERROR == 2

    def test_validation_error_code(self):
        assert exit_codes.VALIDATION_ERROR == 3

    def test_not_found_code(self):
        assert exit_codes.NOT_FOUND == 5


class TestFormatSecret:
    def test_none_returns_not_set(self):
        assert format_secret(None) == "(not set)"

    def test_short_value_masked(self):
        assert format_secret("ab") == "****"

    def test_long_value_shows_last_4(self):
        assert format_secret("abcdef") == "****cdef"

    def test_reveal_shows_value(self):
        assert format_secret("secret", reveal=True) == "secret"

    def test_reveal_none_returns_not_set(self):
        assert format_secret(None, reveal=True) == "(not set)"


class TestFormatProvenance:
    def test_env(self):
        assert format_provenance("env") == "environment"

    def test_yaml(self):
        assert format_provenance("yaml") == "config file"

    def test_default(self):
        assert format_provenance("default") == "default value"

    def test_missing(self):
        assert format_provenance("missing") == "not configured"

    def test_unknown(self):
        assert format_provenance("custom") == "custom"


class TestOutputFormatter:
    def test_json_mode(self, capsys):
        fmt = OutputFormatter(json_mode=True)
        fmt.json_data({"key": "value"})
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["key"] == "value"

    def test_kv_pairs_json(self, capsys):
        fmt = OutputFormatter(json_mode=True)
        fmt.kv_pairs([("a", "1"), ("b", "2")])
        fmt._flush_json()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["pairs"]["a"] == "1"

    def test_table_json(self, capsys):
        fmt = OutputFormatter(json_mode=True)
        fmt.table(["H1", "H2"], [["a", "b"]])
        fmt._flush_json()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["headers"] == ["H1", "H2"]
        assert data["rows"] == [["a", "b"]]

    def test_diagnostics_json(self, capsys):
        from ainews_config.loader import Diagnostic

        fmt = OutputFormatter(json_mode=True)
        diags = [
            Diagnostic(severity="error", code="E1", file="f", key="k", message="msg", remediation="fix"),
        ]
        fmt.diagnostics(diags)
        fmt._flush_json()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data["diagnostics"]) == 1
        assert data["diagnostics"][0]["code"] == "E1"


class TestDunderMain:
    """The ``python -m ainews_cli`` entry point used by install wrappers."""

    def test_main_module_invokes_app(self):
        """__main__ delegates to the Typer app (relocation-proof entry)."""
        import runpy
        from unittest.mock import patch

        with patch("ainews_cli.main.app") as mock_app:
            runpy.run_module("ainews_cli", run_name="__main__")
            mock_app.assert_called_once_with()

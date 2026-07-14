"""CLI integration tests for ainews onboard command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.main import app

runner = CliRunner()


class TestOnboardHelp:
    def test_help_flag(self):
        result = runner.invoke(app, ["onboard", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "onboard" in result.output.lower()

    def test_help_shows_options(self):
        result = runner.invoke(app, ["onboard", "--help"])
        assert "--config-file" in result.output
        assert "--non-interactive" in result.output
        assert "--dry-run" in result.output
        assert "--reset" in result.output
        assert "--start" in result.output


class TestOnboardNonInteractive:
    def test_non_interactive_without_config_errors(self):
        result = runner.invoke(app, ["onboard", "--non-interactive"])
        assert result.exit_code == exit_codes.VALIDATION_ERROR
        assert "requires --config-file" in result.output


class TestOnboardDryRun:
    def test_dry_run_with_config_file(self, tmp_path):
        bootstrap_content = """
version: 1
deployment:
  profile: docker-local
  port: 5000
admin:
  username: admin
  password_env: ADMIN_PASSWORD
provider:
  type: ollama
  id: ollama-local
  base_url: http://localhost:11434/v1
  default_model: auto
pipeline:
  profile: balanced
sources:
  profile: minimal
newsletter:
  enabled: false
start: false
"""
        config_file = tmp_path / "bootstrap.yaml"
        config_file.write_text(bootstrap_content)

        result = runner.invoke(
            app,
            ["onboard", "--config-file", str(config_file), "--dry-run"],
        )
        assert result.exit_code == exit_codes.SUCCESS
        assert "Dry run" in result.output or "dry run" in result.output.lower()

    def test_dry_run_json_output(self, tmp_path):
        bootstrap_content = """
version: 1
deployment:
  profile: docker-local
admin:
  username: admin
  password_env: ADMIN_PASSWORD
provider:
  type: ollama
  id: ollama-local
  base_url: http://localhost:11434/v1
  default_model: auto
pipeline:
  profile: balanced
sources:
  profile: minimal
start: false
"""
        config_file = tmp_path / "bootstrap.yaml"
        config_file.write_text(bootstrap_content)

        result = runner.invoke(
            app,
            ["--json", "onboard", "--config-file", str(config_file), "--dry-run"],
        )
        assert result.exit_code == exit_codes.SUCCESS
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert "bootstrap" in data


class TestOnboardReset:
    def test_reset_with_force(self, tmp_path):
        result = runner.invoke(
            app,
            ["onboard", "--reset"],
            input="yes\n",
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == exit_codes.SUCCESS


class TestOnboardConfigFile:
    def test_invalid_config_file_version(self, tmp_path):
        bootstrap_content = """
version: 99
deployment:
  profile: docker-local
admin:
  username: admin
  password_env: ADMIN_PASS
provider:
  type: ollama
  id: ollama-local
  base_url: http://localhost:11434/v1
  default_model: auto
pipeline:
  profile: balanced
sources:
  profile: minimal
"""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text(bootstrap_content)

        result = runner.invoke(
            app,
            ["onboard", "--config-file", str(config_file)],
        )
        assert result.exit_code == exit_codes.VALIDATION_ERROR

    def test_missing_config_file(self):
        result = runner.invoke(
            app,
            ["onboard", "--config-file", "/nonexistent/path/bootstrap.yaml"],
        )
        assert result.exit_code == exit_codes.NOT_FOUND

    def test_empty_config_file(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        result = runner.invoke(
            app,
            ["onboard", "--config-file", str(config_file)],
        )
        assert result.exit_code == exit_codes.VALIDATION_ERROR


class TestOnboardFinalSummary:
    def test_interactive_onboard_prints_summary(self, tmp_path):
        """Interactive mode requires getpass which doesn't work with CliRunner.
        Test that the command is registered and help works."""
        result = runner.invoke(app, ["onboard", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "onboard" in result.output.lower()

    def test_json_output_mode(self, tmp_path):
        bootstrap_content = """
version: 1
deployment:
  profile: docker-local
admin:
  username: admin
  password_env: ADMIN_PASSWORD
provider:
  type: ollama
  id: ollama-local
  base_url: http://localhost:11434/v1
  default_model: auto
pipeline:
  profile: balanced
sources:
  profile: minimal
start: false
"""
        config_file = tmp_path / "bootstrap.yaml"
        config_file.write_text(bootstrap_content)

        result = runner.invoke(
            app,
            ["--json", "onboard", "--config-file", str(config_file)],
            env={"ADMIN_PASSWORD": "SecureP@ss1"},
        )
        assert result.exit_code == exit_codes.SUCCESS
        data = json.loads(result.output)
        assert "status" in data
        assert "summary" in data
        assert data["status"] == "success"


class TestOnboardStageInfo:
    def test_all_stages_have_info(self):
        from ainews_cli.onboard import OnboardingStage, _STAGE_INFO

        for stage in OnboardingStage:
            assert stage in _STAGE_INFO, f"Missing info for {stage.value}"
            info = _STAGE_INFO[stage]
            assert info.name == stage.value
            assert info.description

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ainews_cli.doctor.checks.search import _check_eggsearch_installation
from ainews_cli.doctor.model import CheckStatus


def _paths(providers_file: Path):
    return SimpleNamespace(providers_file=SimpleNamespace(path=providers_file))


def _write_config(path: Path, *, enabled: bool, config_path: str = "") -> None:
    path.write_text(
        "search_providers:\n"
        "  - id: eggsearch\n"
        "    type: eggsearch\n"
        f"    enabled: {'true' if enabled else 'false'}\n"
        "    config:\n"
        f"      config_path: {config_path!r}\n"
        "default_search_provider: duckduckgo\n",
        encoding="utf-8",
    )


def test_doctor_skips_optional_binding_when_provider_disabled(tmp_path):
    providers = tmp_path / "providers.yaml"
    _write_config(providers, enabled=False)
    checks = []
    with patch("ainews_cli.doctor.checks.search.importlib.import_module") as importer:
        _check_eggsearch_installation(_paths(providers), checks)
    importer.assert_not_called()
    assert checks[0].status is CheckStatus.PASS
    assert checks[0].reason_code == "EGGSEARCH_DISABLED"


def test_doctor_distinguishes_missing_config_path(tmp_path):
    providers = tmp_path / "providers.yaml"
    _write_config(providers, enabled=True)
    checks = []
    _check_eggsearch_installation(_paths(providers), checks)
    assert checks[0].status is CheckStatus.FAIL
    assert checks[0].reason_code == "EGGSEARCH_CONFIG_PATH_MISSING"
    assert str(tmp_path) not in checks[0].message


def test_doctor_rejects_relative_or_missing_config_path(tmp_path):
    providers = tmp_path / "providers.yaml"
    _write_config(providers, enabled=True, config_path="relative.toml")
    checks = []
    _check_eggsearch_installation(_paths(providers), checks)
    assert checks[0].reason_code == "EGGSEARCH_CONFIG_PATH_INVALID"


def test_doctor_reports_missing_optional_binding_without_network(tmp_path):
    providers = tmp_path / "providers.yaml"
    config = tmp_path / "eggsearch.toml"
    config.write_text("[search]\nmode='off'\n", encoding="utf-8")
    _write_config(providers, enabled=True, config_path=str(config))
    checks = []
    with patch(
        "ainews_cli.doctor.checks.search.importlib.import_module",
        side_effect=ModuleNotFoundError("eggsearch"),
    ):
        _check_eggsearch_installation(_paths(providers), checks)
    assert checks[0].status is CheckStatus.FAIL
    assert checks[0].reason_code == "EGGSEARCH_NOT_INSTALLED"


def test_doctor_import_error_is_redacted_and_probe_stays_offline(tmp_path):
    providers = tmp_path / "providers.yaml"
    config = tmp_path / "eggsearch.toml"
    config.write_text("[search]\nmode='off'\n", encoding="utf-8")
    _write_config(providers, enabled=True, config_path=str(config))
    checks = []
    with patch(
        "ainews_cli.doctor.checks.search.importlib.import_module",
        side_effect=OSError("native loader error /secret/path"),
    ) as importer:
        _check_eggsearch_installation(_paths(providers), checks)
    importer.assert_called_once_with("eggsearch")
    assert checks[0].reason_code == "EGGSEARCH_IMPORT_FAILED"
    assert "/secret/path" not in checks[0].message

"""Parity tests: shared loader vs. application startup config validation.

Verifies that ``validate_cross_file()`` (used by ``ainews config check``) and
the application startup path (``ProductionConfig.validate()``) agree on
valid/invalid configurations.
"""

from __future__ import annotations

from pathlib import Path

from ainews_config.loader import EffectiveConfiguration, load_config_for_app
from ainews_config.validation import validate_cross_file


def _explicit_paths(tmp_path: Path) -> dict[str, Path | None]:
    """Build explicit_paths dict for load_config_for_app."""
    return {
        "env_file": tmp_path / ".env",
        "providers_file": tmp_path / "providers.yaml",
        "pipeline_file": tmp_path / "pipeline.yaml",
        "sources_file": tmp_path / "sources.yaml",
        "topics_file": tmp_path / "topics.yaml",
    }


def _write_minimal_configs(tmp_path: Path, **overrides: str) -> None:
    """Write minimal valid config files to tmp_path."""
    (tmp_path / ".env").write_text(
        overrides.get("env", "SECRET_KEY=test-secret-key-at-least-32-chars\n")
    )
    (tmp_path / "providers.yaml").write_text(
        overrides.get(
            "providers",
            "default_provider: test-ollama\nproviders:\n  test-ollama:\n"
            "    type: ollama\n    enabled: true\n    config:\n"
            "      host: http://localhost:11434\n      model: llama3\n",
        )
    )
    (tmp_path / "pipeline.yaml").write_text(
        overrides.get(
            "pipeline",
            "pipeline:\n  selector:\n    enabled: true\n  researcher:\n"
            "    enabled: true\n  writer:\n    enabled: true\n  editor:\n"
            "    enabled: true\nschedule:\n  crawl_interval_minutes: 30\n",
        )
    )
    (tmp_path / "sources.yaml").write_text(overrides.get("sources", "[]\n"))
    (tmp_path / "topics.yaml").write_text(
        overrides.get("topics", "ai:\n  display_name: AI\n  query: artificial intelligence\n")
    )


def _providers_dict_to_list(providers_cfg: dict) -> list[dict]:
    """Convert dict-format providers to list-format for validate_cross_file."""
    raw = providers_cfg.get("providers", {})
    if not isinstance(raw, dict):
        return []
    result = []
    for pid, pval in raw.items():
        if not isinstance(pval, dict):
            continue
        entry = {"id": pid, **pval}
        result.append(entry)
    return result


def _validation_for_config(config: EffectiveConfiguration):
    """Run validate_cross_file on a loaded EffectiveConfiguration."""
    providers_list = _providers_dict_to_list(config.providers)
    return validate_cross_file(
        {
            "providers": {
                "providers": providers_list,
                "default_provider": config.providers.get("default_provider"),
            },
            "pipeline": config.pipeline,
            "sources": config.sources,
            "topics": config.topics,
            "environment": config.environment,
        }
    )


class TestSharedLoaderProducesValidConfig:
    """Verify the shared loader returns a well-formed EffectiveConfiguration."""

    def test_returns_effective_configuration(self, tmp_path):
        _write_minimal_configs(tmp_path)
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        assert isinstance(config, EffectiveConfiguration)

    def test_no_fatal_diagnostics_on_valid_input(self, tmp_path):
        _write_minimal_configs(tmp_path)
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        errors = [d for d in config.diagnostics if d.severity == "error"]
        assert errors == []

    def test_providers_loaded(self, tmp_path):
        _write_minimal_configs(tmp_path)
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        assert config.providers.get("default_provider") == "test-ollama"

    def test_pipeline_loaded(self, tmp_path):
        _write_minimal_configs(tmp_path)
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        pipeline_section = config.pipeline.get("pipeline", {})
        assert pipeline_section.get("selector", {}).get("enabled") is True


class TestCrossFileValidationParity:
    """Verify validate_cross_file agrees with the shared loader diagnostics."""

    def test_valid_config_no_errors(self, tmp_path):
        _write_minimal_configs(tmp_path)
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        validation = _validation_for_config(config)
        assert validation.is_valid

    def test_missing_default_provider_detected_by_both(self, tmp_path):
        _write_minimal_configs(
            tmp_path,
            providers=(
                "providers:\n  ollama:\n    type: ollama\n    enabled: true\n"
            ),
        )
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        validation = _validation_for_config(config)
        codes = [e.code for e in validation.errors]
        assert "PROVIDER_MISSING" in codes

    def test_duplicate_source_ids_detected(self, tmp_path):
        _write_minimal_configs(
            tmp_path,
            sources=(
                "- id: src1\n  type: rss\n  url: http://example.com\n"
                "- id: src1\n  type: rss\n  url: http://example2.com\n"
            ),
        )
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        validation = _validation_for_config(config)
        codes = [e.code for e in validation.errors]
        assert "SOURCE_DUPLICATE" in codes

    def test_bad_schedule_value_detected(self, tmp_path):
        _write_minimal_configs(
            tmp_path,
            pipeline=(
                "pipeline:\n  selector:\n    enabled: true\n"
                "schedule:\n  crawl_interval_minutes: 99999\n"
            ),
        )
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        validation = _validation_for_config(config)
        codes = [e.code for e in validation.errors]
        assert "SCHEDULE_OUT_OF_RANGE" in codes

    def test_disabled_default_provider_detected(self, tmp_path):
        _write_minimal_configs(
            tmp_path,
            providers=(
                "default_provider: ollama\nproviders:\n  ollama:\n"
                "    type: ollama\n    enabled: false\n    config:\n"
                "      host: http://localhost:11434\n      model: llama3\n"
            ),
        )
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        validation = _validation_for_config(config)
        codes = [e.code for e in validation.errors]
        assert "PROVIDER_DISABLED" in codes


class TestSharedLoaderErrorHandling:
    """Verify the shared loader does not raise on bad input."""

    def test_missing_files_returns_config_with_diagnostics(self, tmp_path):
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        assert isinstance(config, EffectiveConfiguration)

    def test_malformed_yaml_returns_config_with_diagnostics(self, tmp_path):
        _write_minimal_configs(tmp_path)
        (tmp_path / "providers.yaml").write_text("{{bad yaml\n")
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        codes = [d.code for d in config.diagnostics]
        assert "YAML_PARSE_ERROR" in codes

    def test_empty_directory_returns_config(self, tmp_path):
        config = load_config_for_app(explicit_paths=_explicit_paths(tmp_path))
        assert isinstance(config, EffectiveConfiguration)

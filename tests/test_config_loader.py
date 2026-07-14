from __future__ import annotations

from pathlib import Path

import pytest

from ainews_config.fields import (
    FIELD_REGISTRY,
    ConfigField,
    FieldType,
    SecretClassification,
)
from ainews_config.loader import (
    Diagnostic,
    EffectiveConfiguration,
    ValueProvenance,
    get_effective_value,
    load_all_configs,
    load_dotenv,
    load_yaml,
    redact_value,
    resolve_env_vars,
    set_effective_value,
    unset_effective_value,
)
from ainews_config.paths import (
    ConfigFile,
    PathProvenance,
    ResolvedPath,
    ResolvedPaths,
)


def _make_resolved_paths(tmp_path: Path) -> ResolvedPaths:
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


class TestDiagnostic:
    def test_frozen(self):
        d = Diagnostic(
            severity="error",
            code="TEST",
            file=None,
            key=None,
            message="msg",
        )
        with pytest.raises(AttributeError):
            d.severity = "warning"

    def test_remediation_optional(self):
        d = Diagnostic(
            severity="info",
            code="INFO",
            file=None,
            key=None,
            message="msg",
        )
        assert d.remediation is None


class TestValueProvenance:
    def test_frozen(self):
        p = ValueProvenance(key="k", source="env")
        with pytest.raises(AttributeError):
            p.key = "other"

    def test_optional_fields(self):
        p = ValueProvenance(key="k", source="default")
        assert p.file is None
        assert p.line is None
        assert p.raw_value is None


class TestLoadDotenv:
    def test_simple_key_value(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")
        env, diags = load_dotenv(env_file)
        assert env == {"FOO": "bar", "BAZ": "qux"}
        assert diags == []

    def test_double_quoted_value(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('FOO="hello world"\n')
        env, _ = load_dotenv(env_file)
        assert env["FOO"] == "hello world"

    def test_single_quoted_value(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO='single quoted'\n")
        env, _ = load_dotenv(env_file)
        assert env["FOO"] == "single quoted"

    def test_export_prefix(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("export KEY=value\n")
        env, _ = load_dotenv(env_file)
        assert env["KEY"] == "value"

    def test_comments_ignored(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nFOO=bar\n")
        env, diags = load_dotenv(env_file)
        assert env == {"FOO": "bar"}
        assert diags == []

    def test_blank_lines_ignored(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nFOO=bar\n\n")
        env, _ = load_dotenv(env_file)
        assert env == {"FOO": "bar"}

    def test_malformed_no_equals(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("BAD_LINE_NO_EQUALS\n")
        env, diags = load_dotenv(env_file)
        assert env == {}
        assert len(diags) == 1
        assert diags[0].severity == "error"
        assert diags[0].code == "DOTENV_MALFORMED_LINE"

    def test_empty_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("=value\n")
        env, diags = load_dotenv(env_file)
        assert env == {}
        assert len(diags) == 1
        assert diags[0].code == "DOTENV_EMPTY_KEY"

    def test_unmatched_quote(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('FOO="unmatched\n')
        env, diags = load_dotenv(env_file)
        assert "FOO" not in env
        assert len(diags) == 1
        assert diags[0].code == "DOTENV_UNMATCHED_QUOTE"

    def test_missing_file_returns_empty(self, tmp_path):
        env, diags = load_dotenv(tmp_path / "nonexistent.env")
        assert env == {}
        assert diags == []

    def test_unreadable_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("X=1")
        env_file.chmod(0o000)
        try:
            env, diags = load_dotenv(env_file)
            assert env == {}
            assert len(diags) == 1
            assert diags[0].code == "DOTENV_READ_ERROR"
        finally:
            env_file.chmod(0o644)

    def test_value_with_equals_sign(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("CONN=redis://localhost:6379\n")
        env, _ = load_dotenv(env_file)
        assert env["CONN"] == "redis://localhost:6379"

    def test_multiple_malformed_lines(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GOOD=ok\nBAD1\nBAD2\nALSO_GOOD=yes\n")
        env, diags = load_dotenv(env_file)
        assert env == {"GOOD": "ok", "ALSO_GOOD": "yes"}
        assert len(diags) == 2


class TestResolveEnvVars:
    def test_resolves_known_var(self):
        env = {"MY_VAR": "resolved_value"}
        result, diags = resolve_env_vars("prefix_${MY_VAR}_suffix", env)
        assert result == "prefix_resolved_value_suffix"
        assert diags == []

    def test_reports_unknown_var(self):
        env = {}
        result, diags = resolve_env_vars("${UNKNOWN}", env)
        assert result == "${UNKNOWN}"
        assert len(diags) == 1
        assert diags[0].severity == "warning"
        assert diags[0].code == "ENV_VAR_UNRESOLVED"

    def test_no_vars_unchanged(self):
        env = {}
        result, diags = resolve_env_vars("plain string", env)
        assert result == "plain string"
        assert diags == []

    def test_non_string_passthrough(self):
        env = {}
        result, diags = resolve_env_vars(42, env)
        assert result == 42
        assert diags == []

    def test_resolves_in_dict(self):
        env = {"VAR": "val"}
        result, diags = resolve_env_vars({"a": "${VAR}", "b": "static"}, env)
        assert result == {"a": "val", "b": "static"}
        assert diags == []

    def test_resolves_in_list(self):
        env = {"VAR": "val"}
        result, diags = resolve_env_vars(["${VAR}", "static", 42], env)
        assert result == ["val", "static", 42]
        assert diags == []

    def test_nested_dict_resolution(self):
        env = {"A": "alpha", "B": "beta"}
        data = {"outer": {"inner": "${A}_${B}"}}
        result, diags = resolve_env_vars(data, env)
        assert result == {"outer": {"inner": "alpha_beta"}}
        assert diags == []

    def test_multiple_vars_one_string(self):
        env = {"X": "1", "Y": "2"}
        result, _ = resolve_env_vars("${X}+${Y}", env)
        assert result == "1+2"

    def test_bool_passthrough(self):
        env = {}
        result, _ = resolve_env_vars(True, env)
        assert result is True

    def test_none_passthrough(self):
        env = {}
        result, _ = resolve_env_vars(None, env)
        assert result is None


class TestLoadYaml:
    def test_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value\nnested:\n  a: 1\n")
        data, diags = load_yaml(yaml_file)
        assert data == {"key": "value", "nested": {"a": 1}}
        assert diags == []

    def test_invalid_yaml(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(":\n  - :\n    bad: [unmatched")
        data, diags = load_yaml(yaml_file)
        assert data is None
        assert len(diags) == 1
        assert diags[0].severity == "error"
        assert diags[0].code == "YAML_PARSE_ERROR"

    def test_missing_file(self, tmp_path):
        data, diags = load_yaml(tmp_path / "missing.yaml")
        assert data is None
        assert diags == []

    def test_empty_file(self, tmp_path):
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        data, diags = load_yaml(yaml_file)
        assert data is None
        assert diags == []

    def test_yaml_with_env_var_refs(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("url: ${BASE_URL}/api\n")
        data, _ = load_yaml(yaml_file)
        assert data == {"url": "${BASE_URL}/api"}


class TestLoadAllConfigs:
    def test_loads_from_temp_directory(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc123\n")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text(
            "default_provider: ollama-local\nproviders:\n  ollama-local:\n    model: llama3\n"
        )

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text(
            "pipeline:\n  selector:\n    enabled: true\n"
        )

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("- name: test\n  type: rss\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("ai:\n  keywords:\n    - llama\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)

        assert config.dotenv == {"SECRET_KEY": "abc123"}
        assert config.environment["SECRET_KEY"] == "abc123"
        assert config.providers["default_provider"] == "ollama-local"
        assert config.pipeline["pipeline"]["selector"]["enabled"] is True
        assert config.sources == [{"name": "test", "type": "rss"}]
        assert config.topics["ai"]["keywords"] == ["llama"]

    def test_env_overrides_merged(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=from_env\n")

        for name in ["providers.yaml", "pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(
            paths, env_overrides={"KEY": "override", "EXTRA": "extra"}
        )
        assert config.environment["KEY"] == "override"
        assert config.environment["EXTRA"] == "extra"

    def test_env_vars_resolved_in_yaml(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("API_HOST=example.com\n")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("host: ${API_HOST}\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert config.providers["host"] == "example.com"

    def test_provenance_for_env_vars(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MY_KEY=my_val\n")

        for name in ["providers.yaml", "pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        prov = config.provenance["MY_KEY"]
        assert prov.source == "env"
        assert prov.raw_value == "my_val"

    def test_provenance_for_yaml_values(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("default_provider: test-provider\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        prov = config.provenance["providers.default_provider"]
        assert prov.source == "yaml"
        assert prov.raw_value == "test-provider"

    def test_diagnostics_accumulated(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("BAD_LINE\nGOOD=ok\n")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("key: value\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        error_codes = [d.code for d in config.diagnostics]
        assert "DOTENV_MALFORMED_LINE" in error_codes

    def test_missing_yaml_files_produce_no_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert config.providers == {}
        assert config.pipeline == {}
        assert config.sources == []
        assert config.topics == {}

    def test_idempotent_loading(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("K=V\n")

        for name in ["providers.yaml", "pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        c1 = load_all_configs(paths)
        c2 = load_all_configs(paths)
        assert c1.environment == c2.environment
        assert c1.providers == c2.providers

    def test_yaml_parse_error_added_to_diagnostics(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{{invalid yaml\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        codes = [d.code for d in config.diagnostics]
        assert "YAML_PARSE_ERROR" in codes


class TestRedactValue:
    def test_secret_returns_redacted(self):
        fld = ConfigField(
            key="test",
            destination=ConfigFile.ENV,
            path=("test",),
            field_type=FieldType.STRING,
            secret=SecretClassification.SECRET,
        )
        assert redact_value("test", "my_secret", fld) == "***REDACTED***"

    def test_sensitive_shows_last_4(self):
        fld = ConfigField(
            key="test",
            destination=ConfigFile.ENV,
            path=("test",),
            field_type=FieldType.STRING,
            secret=SecretClassification.SENSITIVE,
        )
        assert redact_value("test", "abcdef", fld) == "***cdef"

    def test_sensitive_short_value(self):
        fld = ConfigField(
            key="test",
            destination=ConfigFile.ENV,
            path=("test",),
            field_type=FieldType.STRING,
            secret=SecretClassification.SENSITIVE,
        )
        assert redact_value("test", "ab", fld) == "***"

    def test_public_returns_as_is(self):
        fld = ConfigField(
            key="test",
            destination=ConfigFile.ENV,
            path=("test",),
            field_type=FieldType.STRING,
            secret=SecretClassification.PUBLIC,
        )
        assert redact_value("test", "visible", fld) == "visible"

    def test_none_field_looks_up_registry(self):
        fld = ConfigField(
            key="secret_key",
            destination=ConfigFile.ENV,
            path=("secret_key",),
            field_type=FieldType.STRING,
            secret=SecretClassification.SECRET,
        )
        old = FIELD_REGISTRY._fields.get("secret_key")
        FIELD_REGISTRY.register(fld)
        try:
            result = redact_value("secret_key", "s3cret")
            assert result == "***REDACTED***"
        finally:
            if old:
                FIELD_REGISTRY._fields["secret_key"] = old
            else:
                FIELD_REGISTRY._fields.pop("secret_key", None)

    def test_unknown_key_returns_as_is(self):
        assert redact_value("nonexistent", "value") == "value"

    def test_generated_returns_as_is(self):
        fld = ConfigField(
            key="test",
            destination=ConfigFile.ENV,
            path=("test",),
            field_type=FieldType.STRING,
            secret=SecretClassification.GENERATED,
        )
        assert redact_value("test", "token123", fld) == "token123"


class TestGetEffectiveValue:
    def _make_config(self, tmp_path) -> EffectiveConfiguration:
        paths = _make_resolved_paths(tmp_path)
        return EffectiveConfiguration(
            paths=paths,
            environment={"MY_VAR": "env_val"},
            providers={"default_provider": "test"},
            pipeline={"pipeline": {"selector": {"enabled": True}}},
            sources=[],
            topics={},
            provenance={},
            diagnostics=[],
            dotenv={},
        )

    def test_get_from_environment(self, tmp_path):
        config = self._make_config(tmp_path)
        assert get_effective_value(config, "MY_VAR") == "env_val"

    def test_get_from_providers(self, tmp_path):
        config = self._make_config(tmp_path)
        assert get_effective_value(config, "default_provider") == "test"

    def test_get_dotted_key(self, tmp_path):
        config = self._make_config(tmp_path)
        assert get_effective_value(config, "pipeline.selector.enabled") is True

    def test_get_missing_key(self, tmp_path):
        config = self._make_config(tmp_path)
        assert get_effective_value(config, "nonexistent") is None

    def test_get_missing_dotted_key(self, tmp_path):
        config = self._make_config(tmp_path)
        assert get_effective_value(config, "pipeline.missing.key") is None


class TestSetEffectiveValue:
    def _make_config(self, tmp_path) -> EffectiveConfiguration:
        paths = _make_resolved_paths(tmp_path)
        return EffectiveConfiguration(
            paths=paths,
            environment={},
            providers={},
            pipeline={},
            sources=[],
            topics={},
            provenance={},
            diagnostics=[],
            dotenv={},
        )

    def test_set_top_level_key(self, tmp_path):
        config = self._make_config(tmp_path)
        set_effective_value(config, "new_key", "new_val")
        assert config.providers["new_key"] == "new_val"

    def test_set_dotted_key_creates_nested(self, tmp_path):
        config = self._make_config(tmp_path)
        set_effective_value(config, "pipeline.selector.enabled", False)
        assert config.pipeline["pipeline"]["selector"]["enabled"] is False

    def test_set_updates_existing_nested(self, tmp_path):
        config = self._make_config(tmp_path)
        config.pipeline["pipeline"] = {"selector": {"enabled": True}}
        set_effective_value(config, "pipeline.selector.enabled", False)
        assert config.pipeline["pipeline"]["selector"]["enabled"] is False

    def test_set_env_key(self, tmp_path):
        config = self._make_config(tmp_path)
        config.environment["EXISTING"] = "old"
        set_effective_value(config, "EXISTING", "new")
        assert config.environment["EXISTING"] == "new"

    def test_set_topics_key(self, tmp_path):
        config = self._make_config(tmp_path)
        set_effective_value(config, "topics.ai", {"keywords": ["llm"]})
        assert config.topics["topics"]["ai"] == {"keywords": ["llm"]}


class TestUnsetEffectiveValue:
    def _make_config(self, tmp_path) -> EffectiveConfiguration:
        paths = _make_resolved_paths(tmp_path)
        return EffectiveConfiguration(
            paths=paths,
            environment={"K": "V"},
            providers={"p_key": "p_val"},
            pipeline={"pipeline": {"selector": {"enabled": True}}},
            sources=[],
            topics={},
            provenance={},
            diagnostics=[],
            dotenv={},
        )

    def test_unset_top_level(self, tmp_path):
        config = self._make_config(tmp_path)
        unset_effective_value(config, "K")
        assert "K" not in config.environment

    def test_unset_nested_key(self, tmp_path):
        config = self._make_config(tmp_path)
        unset_effective_value(config, "pipeline.selector.enabled")
        assert "enabled" not in config.pipeline["pipeline"]["selector"]

    def test_unset_nonexistent_is_noop(self, tmp_path):
        config = self._make_config(tmp_path)
        unset_effective_value(config, "nonexistent")
        unset_effective_value(config, "a.b.c.d")

    def test_unset_in_providers(self, tmp_path):
        config = self._make_config(tmp_path)
        unset_effective_value(config, "p_key")
        assert "p_key" not in config.providers


class TestProvenanceTracking:
    def test_env_provenance_source(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=12345\n")

        for name in ["providers.yaml", "pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        prov = config.provenance["API_KEY"]
        assert prov.source == "env"
        assert prov.key == "API_KEY"

    def test_yaml_provenance_source(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("default_provider: my-provider\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        prov = config.provenance["providers.default_provider"]
        assert prov.source == "yaml"
        assert prov.file == "providers.yaml"

    def test_missing_provenance_for_absent_optional(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        for name in ["providers.yaml", "pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        keys_without_provenance = [
            k for k in FIELD_REGISTRY.all_keys() if k not in config.provenance
        ]
        non_required_no_default = [
            k for k in keys_without_provenance
            if not (fld := FIELD_REGISTRY.lookup(k)) or (fld.required or fld.default is not None)
        ]
        assert len(non_required_no_default) == 0


class TestMultipleErrors:
    def test_all_errors_collected(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("BAD1\nGOOD=ok\nBAD2\n")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{{bad yaml\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("not: [valid\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("key: value\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("key: value\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)

        codes = [d.code for d in config.diagnostics]
        assert codes.count("DOTENV_MALFORMED_LINE") == 2
        assert "YAML_PARSE_ERROR" in codes


class TestProvidersSchemaValidation:
    def test_providers_not_dict_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("providers: not-a-dict\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        codes = [d.code for d in config.diagnostics]
        assert "SCHEMA_VIOLATION" in codes
        assert any(d.key == "providers" for d in config.diagnostics)

    def test_default_provider_not_string_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("default_provider: 12345\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and d.key == "default_provider"
            for d in config.diagnostics
        )

    def test_search_providers_not_list_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("search_providers: not-a-list\n")

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and d.key == "search_providers"
            for d in config.diagnostics
        )

    def test_valid_providers_no_violations(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text(
            "default_provider: ollama\n"
            "providers:\n"
            "  ollama:\n"
            "    model: llama3\n"
            "search_providers:\n"
            "  - duckduckgo\n"
        )

        for name in ["pipeline.yaml", "sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert not any(
            d.code == "SCHEMA_VIOLATION" for d in config.diagnostics
        )


class TestPipelineSchemaValidation:
    def test_pipeline_not_dict_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("pipeline: not-a-dict\n")

        for name in ["sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and d.key == "pipeline"
            for d in config.diagnostics
        )

    def test_role_not_dict_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("pipeline:\n  selector: not-a-dict\n")

        for name in ["sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and d.key == "pipeline.selector"
            for d in config.diagnostics
        )

    def test_valid_pipeline_no_violations(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text(
            "pipeline:\n"
            "  selector:\n"
            "    enabled: true\n"
            "  researcher:\n"
            "    enabled: true\n"
            "  writer:\n"
            "    enabled: true\n"
            "  editor:\n"
            "    enabled: true\n"
        )

        for name in ["sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert not any(
            d.code == "SCHEMA_VIOLATION" and d.key and d.key.startswith("pipeline.")
            for d in config.diagnostics
        )

    def test_optional_sections_not_dict_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text(
            "pipeline:\n  selector:\n    enabled: true\n"
            "schedule: not-a-dict\nmemory: also-not\nsubagent: nope\n"
        )

        for name in ["sources.yaml", "topics.yaml"]:
            (tmp_path / name).write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        violation_keys = [d.key for d in config.diagnostics if d.code == "SCHEMA_VIOLATION"]
        assert "schedule" in violation_keys
        assert "memory" in violation_keys
        assert "subagent" in violation_keys


class TestSourcesSchemaValidation:
    def test_source_not_dict_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("{}\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("- not-a-dict\n- also-not\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and "sources[0]" in (d.key or "")
            for d in config.diagnostics
        )

    def test_source_missing_required_keys(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("{}\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("- name: test\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        violation_keys = [d.key for d in config.diagnostics if d.code == "SCHEMA_VIOLATION"]
        assert "sources[0].id" in violation_keys
        assert "sources[0].url" in violation_keys
        assert "sources[0].type" in violation_keys

    def test_valid_sources_no_violations(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("{}\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text(
            "- id: hackernews\n  url: https://news.ycombinator.com\n  type: web\n"
        )

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("{}\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert not any(
            d.code == "SCHEMA_VIOLATION" and d.key and d.key.startswith("sources[")
            for d in config.diagnostics
        )


class TestTopicsSchemaValidation:
    def test_topic_not_dict_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("{}\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("[]\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("ai: not-a-dict\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and d.key == "topics.ai"
            for d in config.diagnostics
        )

    def test_topic_missing_query_error(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("{}\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("[]\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("ai:\n  display_name: AI\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert any(
            d.code == "SCHEMA_VIOLATION" and d.key == "topics.ai.query"
            for d in config.diagnostics
        )

    def test_valid_topics_no_violations(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text("{}\n")

        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("{}\n")

        sources_file = tmp_path / "sources.yaml"
        sources_file.write_text("[]\n")

        topics_file = tmp_path / "topics.yaml"
        topics_file.write_text("ai:\n  query: artificial intelligence\n  display_name: AI\n")

        paths = _make_resolved_paths(tmp_path)
        config = load_all_configs(paths)
        assert not any(
            d.code == "SCHEMA_VIOLATION" and d.key and d.key.startswith("topics.")
            for d in config.diagnostics
        )


class TestEffectiveConfiguration:
    def test_is_dataclass(self):
        assert hasattr(EffectiveConfiguration, "__dataclass_fields__")

    def test_fields(self):
        fields = {f.name for f in EffectiveConfiguration.__dataclass_fields__.values()}
        expected = {
            "paths",
            "environment",
            "providers",
            "pipeline",
            "sources",
            "topics",
            "provenance",
            "diagnostics",
            "dotenv",
        }
        assert fields == expected

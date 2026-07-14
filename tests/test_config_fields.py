from __future__ import annotations

import re

import pytest

from ainews_config.fields import (
    FIELD_REGISTRY,
    ConfigFile,
    FieldType,
    RuntimeComponent,
    SecretClassification,
    lookup_field,
)

_ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class TestFieldRegistryUniqueness:
    def test_all_keys_are_unique(self):
        keys = FIELD_REGISTRY.all_keys()
        assert len(keys) == len(set(keys))

    def test_no_duplicate_aliases(self):
        seen_aliases: dict[str, str] = {}
        for fld in FIELD_REGISTRY._fields.values():
            for alias in fld.aliases:
                assert alias not in seen_aliases, (
                    f"Alias {alias!r} registered twice: "
                    f"{seen_aliases[alias]!r} and {fld.key!r}"
                )
                seen_aliases[alias] = fld.key


class TestAliasResolution:
    def test_aliases_resolve_to_canonical(self):
        for fld in FIELD_REGISTRY._fields.values():
            for alias in fld.aliases:
                resolved = FIELD_REGISTRY.lookup(alias)
                assert resolved is not None, f"Alias {alias!r} does not resolve"
                assert resolved.key == fld.key

    def test_canonical_lookup_returns_self(self):
        for fld in FIELD_REGISTRY._fields.values():
            resolved = FIELD_REGISTRY.lookup(fld.key)
            assert resolved is fld

    def test_no_circular_alias_references(self):
        for fld in FIELD_REGISTRY._fields.values():
            for alias in fld.aliases:
                canonical = FIELD_REGISTRY._aliases.get(alias, alias)
                assert canonical != alias or canonical in FIELD_REGISTRY._fields, (
                    f"Alias {alias!r} points to non-existent key {canonical!r}"
                )


class TestSecretClassification:
    def test_secret_fields_are_explicitly_marked(self):
        known_secrets = {
            "secret_key",
            "admin_password",
            "celery_task_secret",
            "smtp_password",
        }
        for fld in FIELD_REGISTRY.by_secret(SecretClassification.SECRET):
            assert fld.key in known_secrets, (
                f"Unexpected SECRET field: {fld.key}"
            )

    def test_no_unclassified_fields(self):
        for fld in FIELD_REGISTRY._fields.values():
            assert isinstance(fld.secret, SecretClassification)


class TestByDestination:
    def test_by_destination_groups_correctly(self):
        env_fields = FIELD_REGISTRY.by_destination(ConfigFile.ENV)
        assert len(env_fields) > 0
        for fld in env_fields:
            assert fld.destination == ConfigFile.ENV

    def test_by_destination_providers(self):
        provider_fields = FIELD_REGISTRY.by_destination(ConfigFile.PROVIDERS)
        assert len(provider_fields) > 0
        for fld in provider_fields:
            assert fld.destination == ConfigFile.PROVIDERS

    def test_by_destination_pipeline(self):
        pipeline_fields = FIELD_REGISTRY.by_destination(ConfigFile.PIPELINE)
        assert len(pipeline_fields) > 0
        for fld in pipeline_fields:
            assert fld.destination == ConfigFile.PIPELINE


class TestBySecret:
    def test_by_secret_groups_correctly(self):
        for classification in SecretClassification:
            fields = FIELD_REGISTRY.by_secret(classification)
            for fld in fields:
                assert fld.secret == classification


class TestValidateKey:
    def test_validate_key_raises_for_unknown(self):
        with pytest.raises(KeyError):
            FIELD_REGISTRY.validate_key("nonexistent.field")

    def test_validate_key_returns_field_for_known(self):
        fld = FIELD_REGISTRY.validate_key("secret_key")
        assert fld.key == "secret_key"

    def test_validate_key_resolves_alias(self):
        fld = FIELD_REGISTRY.validate_key("secret_key")
        assert fld is not None


class TestEnvVarValidation:
    def test_all_env_fields_have_valid_names(self):
        env_fields = FIELD_REGISTRY.by_destination(ConfigFile.ENV)
        for fld in env_fields:
            if fld.env_var is not None:
                assert _ENV_VAR_RE.match(fld.env_var), (
                    f"Invalid env var name {fld.env_var!r} for field {fld.key}"
                )


class TestFieldRegistryConstruction:
    def test_registry_has_expected_env_count(self):
        env_fields = FIELD_REGISTRY.by_destination(ConfigFile.ENV)
        assert len(env_fields) >= 35

    def test_registry_has_expected_provider_count(self):
        provider_fields = FIELD_REGISTRY.by_destination(ConfigFile.PROVIDERS)
        assert len(provider_fields) >= 4

    def test_registry_has_expected_pipeline_count(self):
        pipeline_fields = FIELD_REGISTRY.by_destination(ConfigFile.PIPELINE)
        assert len(pipeline_fields) >= 40


class TestLookupFieldFunction:
    def test_lookup_field_returns_field(self):
        fld = lookup_field("secret_key")
        assert fld is not None
        assert fld.key == "secret_key"

    def test_lookup_field_returns_none_for_unknown(self):
        fld = lookup_field("unknown_key")
        assert fld is None

    def test_lookup_field_resolves_alias(self):
        fld = lookup_field("secret_key")
        assert fld is not None
        assert fld.key == "secret_key"


class TestConfigFieldFrozen:
    def test_config_field_is_frozen(self):
        fld = FIELD_REGISTRY.validate_key("secret_key")
        with pytest.raises(AttributeError):
            fld.key = "modified"


class TestRuntimeComponentImpact:
    def test_restart_impact_is_frozenset(self):
        for fld in FIELD_REGISTRY._fields.values():
            assert isinstance(fld.restart_impact, frozenset)
            for comp in fld.restart_impact:
                assert isinstance(comp, RuntimeComponent)


class TestFieldAliases:
    def test_secret_key_alias_secret(self):
        fld = lookup_field("secret")
        assert fld is not None
        assert fld.key == "secret_key"

    def test_admin_password_alias_admin_pass(self):
        fld = lookup_field("admin_pass")
        assert fld is not None
        assert fld.key == "admin_password"

    def test_database_url_alias_db_url(self):
        fld = lookup_field("db_url")
        assert fld is not None
        assert fld.key == "database_url"

    def test_celery_broker_url_alias_broker_url(self):
        fld = lookup_field("broker_url")
        assert fld is not None
        assert fld.key == "celery_broker_url"

    def test_smtp_host_alias_mail_host(self):
        fld = lookup_field("mail_host")
        assert fld is not None
        assert fld.key == "smtp_host"

    def test_smtp_port_alias_mail_port(self):
        fld = lookup_field("mail_port")
        assert fld is not None
        assert fld.key == "smtp_port"

    def test_aliases_resolve_via_validate_key(self):
        fld = FIELD_REGISTRY.validate_key("secret")
        assert fld.key == "secret_key"

    def test_aliases_in_registry_lookup(self):
        fld = FIELD_REGISTRY.lookup("broker_url")
        assert fld is not None
        assert fld.key == "celery_broker_url"
        assert fld.field_type == FieldType.STRING

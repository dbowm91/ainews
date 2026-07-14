from __future__ import annotations

from ainews_config.validation import (
    ValidationResult,
    validate_cross_file,
)


def _base_config(**overrides: object) -> dict:
    cfg: dict = {
        "providers": {
            "providers": [
                {
                    "id": "ollama-local",
                    "type": "ollama",
                    "enabled": True,
                    "config": {"host": "http://localhost:11434"},
                },
            ],
            "default_provider": "ollama-local",
            "default_search_provider": "duckduckgo",
        },
        "pipeline": {
            "pipeline": {
                "selector": {
                    "enabled": True,
                    "provider": "ollama-local",
                    "model": "qwen3:8b",
                    "max_tokens": 1024,
                    "concurrency": 4,
                    "timeout_seconds": 60,
                },
                "researcher": {
                    "enabled": True,
                    "provider": "ollama-local",
                    "model": "qwen3:8b",
                    "max_tokens": 8192,
                    "concurrency": 2,
                    "timeout_seconds": 180,
                },
                "writer": {
                    "enabled": True,
                    "provider": "ollama-local",
                    "model": "qwen3:8b",
                    "max_tokens": 4096,
                    "concurrency": 2,
                    "timeout_seconds": 180,
                },
                "editor": {
                    "enabled": True,
                    "provider": "ollama-local",
                    "model": "qwen3:8b",
                    "max_tokens": 4096,
                    "concurrency": 2,
                    "timeout_seconds": 120,
                },
            },
            "newsletter": {
                "timezone": "America/New_York",
            },
            "schedule": {
                "crawl_interval_minutes": 30,
                "generate_newsletters_hour": 8,
                "cleanup_old_logs_hour": 3,
                "consolidate_trend_memory_hour": 3,
                "cleanup_inactive_subscribers_hour": 1,
            },
        },
        "sources": [
            {
                "id": "hackernews",
                "topics": {"include": ["ai", "security"]},
            },
        ],
        "topics": {
            "ai": {"display_name": "AI & ML"},
            "security": {"display_name": "Security"},
        },
        "environment": {},
    }
    cfg.update(overrides)
    return cfg


class TestValidationResult:
    def test_empty_result_is_valid(self):
        r = ValidationResult()
        assert r.is_valid
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_error_makes_invalid(self):
        r = ValidationResult()
        r.add_error("CODE", None, None, "msg")
        assert not r.is_valid
        assert r.error_count == 1

    def test_warning_keeps_valid(self):
        r = ValidationResult()
        r.add_warning("CODE", None, None, "msg")
        assert r.is_valid
        assert r.warning_count == 1

    def test_add_error(self):
        r = ValidationResult()
        r.add_error("CODE", "file.yaml", "key", "msg", remediation="fix it")
        assert len(r.errors) == 1
        e = r.errors[0]
        assert e.severity == "error"
        assert e.code == "CODE"
        assert e.file == "file.yaml"
        assert e.key == "key"
        assert e.message == "msg"
        assert e.remediation == "fix it"

    def test_add_warning(self):
        r = ValidationResult()
        r.add_warning("CODE", None, None, "msg")
        assert r.errors[0].severity == "warning"


class TestValidConfigPasses:
    def test_valid_config(self):
        result = validate_cross_file(_base_config())
        assert result.is_valid

    def test_empty_config_is_valid(self):
        result = validate_cross_file({})
        assert result.is_valid


class TestDefaultProviderValidation:
    def test_missing_default_provider(self):
        cfg = _base_config()
        cfg["providers"]["default_provider"] = None
        result = validate_cross_file(cfg)
        assert result.is_valid
        assert any(e.code == "PROVIDER_MISSING" for e in result.errors)

    def test_default_provider_not_in_list(self):
        cfg = _base_config()
        cfg["providers"]["default_provider"] = "nonexistent"
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(
            e.code == "PROVIDER_MISSING" and "does not exist" in e.message
            for e in result.errors
        )

    def test_disabled_default_provider(self):
        cfg = _base_config()
        cfg["providers"]["providers"][0]["enabled"] = False
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "PROVIDER_DISABLED" for e in result.errors)


class TestDuplicateProviderIds:
    def test_duplicate_provider_ids(self):
        cfg = _base_config()
        cfg["providers"]["providers"].append(
            {
                "id": "ollama-local",
                "type": "ollama",
                "enabled": True,
                "config": {},
            }
        )
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "PROVIDER_DUPLICATE" for e in result.errors)


class TestPipelineRoles:
    def test_role_missing_provider(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["provider"] = "ghost"
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(
            e.code == "ROLE_PROVIDER_MISSING" and "selector" in e.message
            for e in result.errors
        )

    def test_role_disabled_provider(self):
        cfg = _base_config()
        cfg["providers"]["providers"].append(
            {
                "id": "disabled-one",
                "type": "ollama",
                "enabled": False,
                "config": {},
            }
        )
        cfg["pipeline"]["pipeline"]["writer"]["provider"] = "disabled-one"
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(
            e.code == "ROLE_PROVIDER_DISABLED" and "writer" in e.message
            for e in result.errors
        )

    def test_disabled_role_skipped(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["enabled"] = False
        cfg["pipeline"]["pipeline"]["selector"]["provider"] = "ghost"
        result = validate_cross_file(cfg)
        assert not any(
            e.code == "ROLE_PROVIDER_MISSING" and "selector" in e.message
            for e in result.errors
        )

    def test_null_provider_skipped(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["provider"] = None
        result = validate_cross_file(cfg)
        assert not any(
            e.code == "ROLE_PROVIDER_MISSING" and "selector" in e.message
            for e in result.errors
        )


class TestSourceValidation:
    def test_duplicate_source_ids(self):
        cfg = _base_config()
        cfg["sources"].append({"id": "hackernews", "topics": {"include": []}})
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SOURCE_DUPLICATE" for e in result.errors)

    def test_source_references_nonexistent_topic(self):
        cfg = _base_config()
        cfg["sources"][0]["topics"]["include"] = ["nonexistent"]
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SOURCE_TOPIC_MISSING" for e in result.errors)

    def test_source_valid_topic_references(self):
        cfg = _base_config()
        cfg["sources"][0]["topics"]["include"] = ["ai", "security"]
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestTopicValidation:
    def test_duplicate_topic_ids_not_possible_with_dict(self):
        cfg = _base_config()
        cfg["topics"]["newtopic"] = {"display_name": "New Topic"}
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_missing_display_name_is_warning(self):
        cfg = _base_config()
        cfg["topics"]["newtopic"] = {}
        result = validate_cross_file(cfg)
        assert any(
            e.code == "TOPIC_DUPLICATE" and "display_name" in e.message
            for e in result.errors
        )

    def test_valid_topics_pass(self):
        cfg = _base_config()
        cfg["topics"]["newtopic"] = {"display_name": "New Topic"}
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestScheduleValidation:
    def test_crawl_interval_out_of_range(self):
        cfg = _base_config()
        cfg["pipeline"]["schedule"]["crawl_interval_minutes"] = 0
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SCHEDULE_OUT_OF_RANGE" for e in result.errors)

    def test_hour_out_of_range(self):
        cfg = _base_config()
        cfg["pipeline"]["schedule"]["generate_newsletters_hour"] = 24
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(
            e.code == "SCHEDULE_OUT_OF_RANGE" and "generate_newsletters_hour" in e.key
            for e in result.errors
        )

    def test_valid_schedule(self):
        cfg = _base_config()
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestNewsletterValidation:
    def test_invalid_timezone(self):
        cfg = _base_config()
        cfg["pipeline"]["newsletter"]["timezone"] = "Invalid/Timezone"
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "TIMEZONE_INVALID" for e in result.errors)

    def test_valid_timezone(self):
        cfg = _base_config()
        cfg["pipeline"]["newsletter"]["timezone"] = "UTC"
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestProductionSecrets:
    def test_short_secret_key_in_production(self):
        cfg = _base_config()
        cfg["environment"] = {
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "short",
            "ADMIN_PASSWORD": "scrypt:xxx",
            "CELERY_TASK_SECRET": "a" * 32,
        }
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SECRET_KEY_SHORT" for e in result.errors)

    def test_plaintext_admin_password_in_production(self):
        cfg = _base_config()
        cfg["environment"] = {
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "a" * 32,
            "ADMIN_PASSWORD": "my-password",
            "CELERY_TASK_SECRET": "b" * 32,
        }
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "ADMIN_PASSWORD_PLAINTEXT" for e in result.errors)

    def test_short_celery_secret_in_production(self):
        cfg = _base_config()
        cfg["environment"] = {
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "a" * 32,
            "ADMIN_PASSWORD": "scrypt:xxx",
            "CELERY_TASK_SECRET": "short",
        }
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "CELERY_SECRET_SHORT" for e in result.errors)

    def test_non_production_skips_secret_checks(self):
        cfg = _base_config()
        cfg["environment"] = {
            "FLASK_CONFIG": "development",
            "SECRET_KEY": "x",
            "ADMIN_PASSWORD": "plaintext",
            "CELERY_TASK_SECRET": "y",
        }
        result = validate_cross_file(cfg)
        assert not any(e.code == "SECRET_KEY_SHORT" for e in result.errors)
        assert not any(e.code == "ADMIN_PASSWORD_PLAINTEXT" for e in result.errors)
        assert not any(e.code == "CELERY_SECRET_SHORT" for e in result.errors)

    def test_hashed_password_accepted(self):
        cfg = _base_config()
        cfg["environment"] = {
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "a" * 32,
            "ADMIN_PASSWORD": "scrypt:32768:8:1$salt$hash",
            "CELERY_TASK_SECRET": "c" * 32,
        }
        result = validate_cross_file(cfg)
        assert not any(e.code == "ADMIN_PASSWORD_PLAINTEXT" for e in result.errors)


class TestRedisValidation:
    def test_mixed_redis_nonredis_warning(self):
        cfg = _base_config()
        cfg["environment"] = {
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULT_BACKEND": "rpc://",
        }
        result = validate_cross_file(cfg)
        assert result.is_valid
        assert any(e.code == "REDIS_URL_MISMATCH" for e in result.errors)

    def test_same_db_warning(self):
        cfg = _base_config()
        cfg["environment"] = {
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
        }
        result = validate_cross_file(cfg)
        assert result.is_valid
        assert any(e.code == "REDIS_URL_MISMATCH" for e in result.errors)

    def test_different_dbs_no_warning(self):
        cfg = _base_config()
        cfg["environment"] = {
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
        }
        result = validate_cross_file(cfg)
        assert result.is_valid
        assert not any(e.code == "REDIS_URL_MISMATCH" for e in result.errors)


class TestSafeFetchValidation:
    def test_out_of_range_redirects(self):
        cfg = _base_config()
        cfg["environment"] = {"SAFE_FETCH_MAX_REDIRECTS": "25"}
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SAFE_FETCH_OUT_OF_RANGE" for e in result.errors)

    def test_out_of_range_bytes(self):
        cfg = _base_config()
        cfg["environment"] = {"SAFE_FETCH_MAX_BYTES": "100"}
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SAFE_FETCH_OUT_OF_RANGE" for e in result.errors)

    def test_non_integer_value(self):
        cfg = _base_config()
        cfg["environment"] = {"SAFE_FETCH_MAX_REDIRECTS": "abc"}
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "SAFE_FETCH_OUT_OF_RANGE" for e in result.errors)

    def test_valid_values(self):
        cfg = _base_config()
        cfg["environment"] = {
            "SAFE_FETCH_MAX_REDIRECTS": "5",
            "SAFE_FETCH_MAX_BYTES": "2000000",
            "SAFE_FETCH_CONNECT_TIMEOUT": "5",
            "SAFE_FETCH_READ_TIMEOUT": "10",
            "SAFE_FETCH_TOTAL_TIMEOUT": "20",
        }
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestThemeValidation:
    def test_max_file_bytes_out_of_range(self):
        cfg = _base_config()
        cfg["environment"] = {"THEMES_MAX_FILE_BYTES": "100"}
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "THEME_CONFIG_INVALID" for e in result.errors)

    def test_custom_dir_without_allow_custom(self):
        cfg = _base_config()
        cfg["environment"] = {
            "THEMES_CUSTOM_DIR": "/some/dir",
            "THEMES_ALLOW_CUSTOM": "false",
        }
        result = validate_cross_file(cfg)
        assert result.is_valid
        assert any(
            e.code == "THEME_CONFIG_INVALID" and "custom" in e.message.lower()
            for e in result.errors
        )

    def test_valid_theme_config(self):
        cfg = _base_config()
        cfg["environment"] = {
            "THEMES_MAX_FILE_BYTES": "262144",
            "THEMES_CUSTOM_DIR": "/some/dir",
            "THEMES_ALLOW_CUSTOM": "true",
        }
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestDatabaseUrlValidation:
    def test_missing_database_url_in_production(self):
        cfg = _base_config()
        cfg["environment"] = {"FLASK_CONFIG": "production"}
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "DATABASE_URL_MISSING" for e in result.errors)

    def test_empty_database_url_in_production(self):
        cfg = _base_config()
        cfg["environment"] = {"FLASK_CONFIG": "production", "DATABASE_URL": ""}
        result = validate_cross_file(cfg)
        assert not result.is_valid
        assert any(e.code == "DATABASE_URL_MISSING" for e in result.errors)

    def test_database_url_present_in_production(self):
        cfg = _base_config()
        cfg["environment"] = {
            "FLASK_CONFIG": "production",
            "DATABASE_URL": "sqlite:///instance/prod.db",
        }
        result = validate_cross_file(cfg)
        assert not any(e.code == "DATABASE_URL_MISSING" for e in result.errors)

    def test_non_production_skips_database_url_check(self):
        cfg = _base_config()
        cfg["environment"] = {"FLASK_CONFIG": "development"}
        result = validate_cross_file(cfg)
        assert not any(e.code == "DATABASE_URL_MISSING" for e in result.errors)


class TestRoleModelValidation:
    def test_valid_model_with_colon(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["model"] = "qwen3:8b"
        result = validate_cross_file(cfg)
        assert not any(
            e.code == "ROLE_MODEL_INVALID" and "selector" in (e.key or "")
            for e in result.errors
        )

    def test_valid_model_with_slash(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["model"] = "openai/gpt-4"
        result = validate_cross_file(cfg)
        assert not any(
            e.code == "ROLE_MODEL_INVALID" and "selector" in (e.key or "")
            for e in result.errors
        )

    def test_model_without_colon_or_slash_warns(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["model"] = "gpt4"
        result = validate_cross_file(cfg)
        assert any(
            e.code == "ROLE_MODEL_INVALID" and "selector" in (e.key or "")
            for e in result.errors
        )

    def test_disabled_role_skipped(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["enabled"] = False
        cfg["pipeline"]["pipeline"]["selector"]["model"] = "bad"
        result = validate_cross_file(cfg)
        assert not any(
            e.code == "ROLE_MODEL_INVALID" and "selector" in (e.key or "")
            for e in result.errors
        )

    def test_null_model_skipped(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["model"] = None
        result = validate_cross_file(cfg)
        assert not any(
            e.code == "ROLE_MODEL_INVALID" and "selector" in (e.key or "")
            for e in result.errors
        )

    def test_multiple_invalid_models(self):
        cfg = _base_config()
        cfg["pipeline"]["pipeline"]["selector"]["model"] = "badmodel"
        cfg["pipeline"]["pipeline"]["writer"]["model"] = "alsobad"
        result = validate_cross_file(cfg)
        model_errors = [e for e in result.errors if e.code == "ROLE_MODEL_INVALID"]
        assert len(model_errors) >= 2


class TestMultipleErrors:
    def test_multiple_errors_reported_simultaneously(self):
        cfg = _base_config()
        cfg["providers"]["default_provider"] = "missing"
        cfg["pipeline"]["pipeline"]["selector"]["provider"] = "also-missing"
        cfg["pipeline"]["schedule"]["crawl_interval_minutes"] = 0
        cfg["pipeline"]["newsletter"]["timezone"] = "Bad/Zone"
        result = validate_cross_file(cfg)
        codes = {e.code for e in result.errors}
        assert "PROVIDER_MISSING" in codes
        assert "ROLE_PROVIDER_MISSING" in codes
        assert "SCHEDULE_OUT_OF_RANGE" in codes
        assert "TIMEZONE_INVALID" in codes
        assert result.error_count >= 4


class TestEdgeCases:
    def test_providers_not_dict(self):
        cfg = _base_config()
        cfg["providers"] = "invalid"
        for role in cfg["pipeline"]["pipeline"]:
            cfg["pipeline"]["pipeline"][role]["provider"] = None
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_pipeline_not_dict(self):
        cfg = _base_config()
        cfg["pipeline"] = "invalid"
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_sources_not_list(self):
        cfg = _base_config()
        cfg["sources"] = "invalid"
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_topics_not_dict(self):
        cfg = _base_config()
        cfg["topics"] = "invalid"
        cfg["sources"] = []
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_environment_not_dict(self):
        cfg = _base_config()
        cfg["environment"] = "invalid"
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_provider_missing_id_field(self):
        cfg = _base_config()
        cfg["providers"]["providers"].append({"type": "ollama", "enabled": True, "config": {}})
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_source_without_topics(self):
        cfg = _base_config()
        cfg["sources"].append({"id": "bare-source"})
        result = validate_cross_file(cfg)
        assert result.is_valid

    def test_source_topics_include_not_list(self):
        cfg = _base_config()
        cfg["sources"].append({"id": "bad-topics", "topics": {"include": "not-a-list"}})
        result = validate_cross_file(cfg)
        assert result.is_valid


class TestRedisPresenceProduction:
    def test_missing_broker_in_production(self):
        cfg = _base_config()
        cfg["environment"]["FLASK_CONFIG"] = "production"
        cfg["environment"].pop("CELERY_BROKER_URL", None)
        cfg["environment"].pop("CELERY_RESULT_BACKEND", None)
        result = validate_cross_file(cfg)
        codes = [e.code for e in result.errors]
        assert "REDIS_URL_MISSING" in codes

    def test_missing_backend_in_production(self):
        cfg = _base_config()
        cfg["environment"]["FLASK_CONFIG"] = "production"
        cfg["environment"]["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
        cfg["environment"].pop("CELERY_RESULT_BACKEND", None)
        result = validate_cross_file(cfg)
        codes = [e.code for e in result.errors]
        assert "REDIS_URL_MISSING" in codes

    def test_missing_broker_not_checked_in_development(self):
        cfg = _base_config()
        cfg["environment"].pop("CELERY_BROKER_URL", None)
        cfg["environment"].pop("CELERY_RESULT_BACKEND", None)
        result = validate_cross_file(cfg)
        codes = [e.code for e in result.errors]
        assert "REDIS_URL_MISSING" not in codes

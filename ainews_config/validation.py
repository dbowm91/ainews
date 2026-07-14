from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationError:
    severity: str
    code: str
    file: str | None
    key: str | None
    message: str
    remediation: str | None = None


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(e.severity == "error" for e in self.errors)

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "warning")

    def add_error(
        self,
        code: str,
        file: str | None,
        key: str | None,
        message: str,
        remediation: str | None = None,
    ) -> None:
        self.errors.append(
            ValidationError(
                severity="error",
                code=code,
                file=file,
                key=key,
                message=message,
                remediation=remediation,
            )
        )

    def add_warning(
        self,
        code: str,
        file: str | None,
        key: str | None,
        message: str,
        remediation: str | None = None,
    ) -> None:
        self.errors.append(
            ValidationError(
                severity="warning",
                code=code,
                file=file,
                key=key,
                message=message,
                remediation=remediation,
            )
        )


_ROLES = ("selector", "researcher", "writer", "editor")

_SCHEDULE_BOUNDS: dict[str, tuple[int, int]] = {
    "crawl_interval_minutes": (1, 1440),
    "generate_newsletters_hour": (0, 23),
    "cleanup_old_logs_hour": (0, 23),
    "consolidate_trend_memory_hour": (0, 23),
    "cleanup_inactive_subscribers_hour": (0, 23),
}

_PIPELINE_NUMERIC_BOUNDS: dict[str, tuple[int, int]] = {
    "max_tokens": (1, 1_000_000),
    "concurrency": (1, 64),
    "timeout_seconds": (1, 86400),
    "temperature": (0, 2),
}

_SAFE_FETCH_BOUNDS: dict[str, tuple[int, int]] = {
    "SAFE_FETCH_MAX_REDIRECTS": (0, 20),
    "SAFE_FETCH_MAX_BYTES": (1024, 100_000_000),
    "SAFE_FETCH_CONNECT_TIMEOUT": (1, 60),
    "SAFE_FETCH_READ_TIMEOUT": (1, 300),
    "SAFE_FETCH_TOTAL_TIMEOUT": (1, 600),
}

_MIN_SECRET_LENGTH = 16
_MIN_CELERY_SECRET_LENGTH = 16

_VALID_TIMEZONES = frozenset({
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Paris",
    "Europe/Moscow",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Australia/Sydney",
    "Pacific/Auckland",
})

_THEME_MAX_FILE_BYTES_MIN = 4096
_THEME_MAX_FILE_BYTES_MAX = 10_485_760


def validate_cross_file(config: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()

    _validate_providers(config, result)
    _validate_pipeline_roles(config, result)
    _validate_sources(config, result)
    _validate_topics(config, result)
    _validate_schedule(config, result)
    _validate_newsletter(config, result)
    _validate_production_secrets(config, result)
    _validate_database_url(config, result)
    _validate_role_models(config, result)
    _validate_safe_fetch(config, result)
    _validate_themes(config, result)
    _validate_redis(config, result)

    return result


def _get_providers(config: dict[str, Any]) -> list[dict[str, Any]]:
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        return []
    raw = providers.get("providers", [])
    return raw if isinstance(raw, list) else []


def _get_provider_ids(providers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for p in providers:
        pid = p.get("id")
        if isinstance(pid, str) and pid:
            by_id[pid] = p
    return by_id


def _get_default_provider_id(config: dict[str, Any]) -> str | None:
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        return None
    dp = providers.get("default_provider")
    return dp if isinstance(dp, str) and dp else None


def _get_pipeline(config: dict[str, Any]) -> dict[str, Any]:
    pipeline = config.get("pipeline", {})
    return pipeline if isinstance(pipeline, dict) else {}


def _get_topics(config: dict[str, Any]) -> dict[str, Any]:
    topics = config.get("topics", {})
    if not isinstance(topics, dict):
        return {}
    inner = topics.get("topics", topics)
    return inner if isinstance(inner, dict) else {}


def _get_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = config.get("sources", [])
    return sources if isinstance(sources, list) else []


def _get_environment(config: dict[str, Any]) -> dict[str, str]:
    env = config.get("environment", {})
    return env if isinstance(env, dict) else {}


def _validate_providers(config: dict[str, Any], result: ValidationResult) -> None:
    providers = _get_providers(config)
    provider_map = _get_provider_ids(providers)
    default_id = _get_default_provider_id(config)

    seen_ids: set[str] = set()
    for p in providers:
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            continue
        if pid in seen_ids:
            result.add_error(
                code="PROVIDER_DUPLICATE",
                file="providers.yaml",
                key=f"providers.{pid}",
                message=f"Duplicate provider ID: {pid!r}.",
                remediation="Ensure all provider IDs are unique.",
            )
        seen_ids.add(pid)

    if default_id is None:
        if providers:
            result.add_warning(
                code="PROVIDER_MISSING",
                file="providers.yaml",
                key="default_provider",
                message="No default_provider configured.",
                remediation="Set default_provider in providers.yaml to a valid provider ID.",
            )
        return
    elif default_id not in provider_map:
        result.add_error(
            code="PROVIDER_MISSING",
            file="providers.yaml",
            key="default_provider",
            message=f"Default provider {default_id!r} does not exist.",
            remediation=f"Add a provider with id {default_id!r} or change default_provider.",
        )
    else:
        dp = provider_map[default_id]
        if dp.get("enabled") is False:
            result.add_error(
                code="PROVIDER_DISABLED",
                file="providers.yaml",
                key=f"providers.{default_id}.enabled",
                message=f"Default provider {default_id!r} is disabled.",
                remediation=f"Enable provider {default_id!r} or choose a different default.",
            )

    for p in providers:
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            continue
        ptype = p.get("type")
        config_block = p.get("config", {})
        if not isinstance(config_block, dict):
            config_block = {}
        if ptype in ("openai", "anthropic", "gemini"):
            api_key = config_block.get("api_key", "")
            if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                env = _get_environment(config)
                if env_var not in env:
                    result.add_warning(
                        code="ROLE_PROVIDER_MISSING",
                        file="providers.yaml",
                        key=f"providers.{pid}.config.api_key",
                        message=f"Provider {pid!r} references unresolvable env var ${{{env_var}}}.",
                        remediation=f"Set {env_var} in your environment or .env file.",
                    )


def _validate_role_provider(
    role: str,
    role_config: dict[str, Any],
    provider_map: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> None:
    provider_id = role_config.get("provider")
    if provider_id is None or provider_id == "null":
        return
    if not isinstance(provider_id, str) or not provider_id:
        return

    if provider_id not in provider_map:
        result.add_error(
            code="ROLE_PROVIDER_MISSING",
            file="pipeline.yaml",
            key=f"pipeline.{role}.provider",
            message=f"Role {role!r} references missing provider {provider_id!r}.",
            remediation=f"Add provider {provider_id!r} or assign a different provider.",
        )
    elif provider_map[provider_id].get("enabled") is False:
        result.add_error(
            code="ROLE_PROVIDER_DISABLED",
            file="pipeline.yaml",
            key=f"pipeline.{role}.provider",
            message=f"Role {role!r} references disabled provider {provider_id!r}.",
            remediation=f"Enable provider {provider_id!r} or assign a different provider.",
        )

    model = role_config.get("model")
    if model is not None and model != "null":
        if not isinstance(model, str) or not model:
            result.add_error(
                code="ROLE_PROVIDER_MISSING",
                file="pipeline.yaml",
                key=f"pipeline.{role}.model",
                message=f"Role {role!r} has invalid model value.",
                remediation=f"Set a valid model string for {role!r}.",
            )


def _validate_role_numeric(
    role: str,
    role_config: dict[str, Any],
    result: ValidationResult,
) -> None:
    max_tokens = role_config.get("max_tokens")
    if max_tokens is not None:
        if not isinstance(max_tokens, int) or max_tokens < 1:
            result.add_error(
                code="SCHEDULE_OUT_OF_RANGE",
                file="pipeline.yaml",
                key=f"pipeline.{role}.max_tokens",
                message=f"Role {role!r} max_tokens must be a positive integer.",
                remediation="Set max_tokens to a positive integer.",
            )

    concurrency = role_config.get("concurrency")
    if concurrency is not None:
        if not isinstance(concurrency, int) or not (1 <= concurrency <= 64):
            result.add_error(
                code="SCHEDULE_OUT_OF_RANGE",
                file="pipeline.yaml",
                key=f"pipeline.{role}.concurrency",
                message=f"Role {role!r} concurrency must be between 1 and 64.",
                remediation="Set concurrency to an integer between 1 and 64.",
            )

    timeout = role_config.get("timeout_seconds")
    if timeout is not None:
        if not isinstance(timeout, int) or not (1 <= timeout <= 86400):
            result.add_error(
                code="SCHEDULE_OUT_OF_RANGE",
                file="pipeline.yaml",
                key=f"pipeline.{role}.timeout_seconds",
                message=f"Role {role!r} timeout_seconds must be between 1 and 86400.",
                remediation="Set timeout_seconds to a value between 1 and 86400.",
            )


def _validate_pipeline_roles(config: dict[str, Any], result: ValidationResult) -> None:
    providers = _get_providers(config)
    provider_map = _get_provider_ids(providers)
    pipeline = _get_pipeline(config)
    pipeline_section = pipeline.get("pipeline", {})
    if not isinstance(pipeline_section, dict):
        return

    for role in _ROLES:
        role_config = pipeline_section.get(role, {})
        if not isinstance(role_config, dict):
            continue
        if role_config.get("enabled") is False:
            continue
        _validate_role_provider(role, role_config, provider_map, result)
        _validate_role_numeric(role, role_config, result)


def _validate_sources(config: dict[str, Any], result: ValidationResult) -> None:
    sources = _get_sources(config)
    raw_topics = config.get("topics", {})
    if isinstance(raw_topics, dict):
        inner = raw_topics.get("topics", raw_topics)
        topic_ids = set(inner.keys()) if isinstance(inner, dict) else set()
    else:
        topic_ids = set()

    seen_ids: set[str] = set()
    for s in sources:
        sid = s.get("id")
        if not isinstance(sid, str) or not sid:
            continue
        if sid in seen_ids:
            result.add_error(
                code="SOURCE_DUPLICATE",
                file="sources.yaml",
                key=f"sources.{sid}",
                message=f"Duplicate source ID: {sid!r}.",
                remediation="Ensure all source IDs are unique.",
            )
        seen_ids.add(sid)

        source_topics = s.get("topics", {})
        if isinstance(source_topics, dict):
            include = source_topics.get("include", [])
            if isinstance(include, list):
                for tid in include:
                    if isinstance(tid, str) and tid not in topic_ids:
                        result.add_error(
                            code="SOURCE_TOPIC_MISSING",
                            file="sources.yaml",
                            key=f"sources.{sid}.topics.include",
                            message=f"Source {sid!r} references non-existent topic {tid!r}.",
                            remediation=f"Add topic {tid!r} to topics.yaml or remove the reference.",
                        )


def _validate_topics(config: dict[str, Any], result: ValidationResult) -> None:
    topics = _get_topics(config)
    if not topics:
        return

    seen_ids: set[str] = set()
    for tid, tval in topics.items():
        if not isinstance(tid, str) or not tid:
            continue
        if tid in seen_ids:
            result.add_error(
                code="TOPIC_DUPLICATE",
                file="topics.yaml",
                key=f"topics.{tid}",
                message=f"Duplicate topic ID: {tid!r}.",
                remediation="Ensure all topic IDs are unique.",
            )
        seen_ids.add(tid)

        if not isinstance(tval, dict):
            continue
        display_name = tval.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            result.add_warning(
                code="TOPIC_DUPLICATE",
                file="topics.yaml",
                key=f"topics.{tid}.display_name",
                message=f"Topic {tid!r} is missing display_name.",
                remediation=f"Add display_name to topic {tid!r}.",
            )


def _validate_schedule(config: dict[str, Any], result: ValidationResult) -> None:
    pipeline = _get_pipeline(config)
    schedule = pipeline.get("schedule", {})
    if not isinstance(schedule, dict):
        return

    for key, (lo, hi) in _SCHEDULE_BOUNDS.items():
        val = schedule.get(key)
        if val is None:
            continue
        if not isinstance(val, int):
            result.add_error(
                code="SCHEDULE_OUT_OF_RANGE",
                file="pipeline.yaml",
                key=f"schedule.{key}",
                message=f"Schedule value {key!r} must be an integer.",
                remediation=f"Set {key} to an integer between {lo} and {hi}.",
            )
            continue
        if not (lo <= val <= hi):
            result.add_error(
                code="SCHEDULE_OUT_OF_RANGE",
                file="pipeline.yaml",
                key=f"schedule.{key}",
                message=f"Schedule value {key!r} must be between {lo} and {hi}, got {val}.",
                remediation=f"Set {key} to a value between {lo} and {hi}.",
            )


def _validate_newsletter(config: dict[str, Any], result: ValidationResult) -> None:
    pipeline = _get_pipeline(config)
    newsletter = pipeline.get("newsletter", {})
    if not isinstance(newsletter, dict):
        return

    tz = newsletter.get("timezone")
    if isinstance(tz, str) and tz:
        if tz not in _VALID_TIMEZONES:
            result.add_error(
                code="TIMEZONE_INVALID",
                file="pipeline.yaml",
                key="newsletter.timezone",
                message=f"Invalid timezone: {tz!r}.",
                remediation="Use a valid IANA timezone (e.g. America/New_York, UTC).",
            )


def _validate_production_secrets(
    config: dict[str, Any], result: ValidationResult
) -> None:
    env = _get_environment(config)
    flask_config = env.get("FLASK_CONFIG", "development")
    if flask_config != "production":
        return

    secret_key = env.get("SECRET_KEY", "")
    if isinstance(secret_key, str) and len(secret_key) < _MIN_SECRET_LENGTH:
        result.add_error(
            code="SECRET_KEY_SHORT",
            file=".env",
            key="SECRET_KEY",
            message=f"SECRET_KEY must be at least {_MIN_SECRET_LENGTH} characters in production.",
            remediation="Generate a strong secret with: python -c 'import secrets; print(secrets.token_hex(32))'",
        )

    admin_password = env.get("ADMIN_PASSWORD", "")
    if isinstance(admin_password, str) and admin_password:
        is_hashed = admin_password.startswith(("scrypt:", "pbkdf2:", "argon2:", "$2"))
        if not is_hashed:
            result.add_error(
                code="ADMIN_PASSWORD_PLAINTEXT",
                file=".env",
                key="ADMIN_PASSWORD",
                message="ADMIN_PASSWORD appears to be plaintext in production.",
                remediation="Hash the password: python -c \"from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))\"",
            )

    celery_secret = env.get("CELERY_TASK_SECRET", "")
    if isinstance(celery_secret, str) and len(celery_secret) < _MIN_CELERY_SECRET_LENGTH:
        result.add_error(
            code="CELERY_SECRET_SHORT",
            file=".env",
            key="CELERY_TASK_SECRET",
            message=f"CELERY_TASK_SECRET must be at least {_MIN_CELERY_SECRET_LENGTH} characters in production.",
            remediation="Generate a strong secret with: python -c 'import secrets; print(secrets.token_hex(32))'",
        )


def _validate_database_url(config: dict[str, Any], result: ValidationResult) -> None:
    env = _get_environment(config)
    flask_config = env.get("FLASK_CONFIG", "development")
    if flask_config != "production":
        return

    database_url = env.get("DATABASE_URL", "")
    if not isinstance(database_url, str) or not database_url:
        result.add_error(
            code="DATABASE_URL_MISSING",
            file=".env",
            key="DATABASE_URL",
            message="DATABASE_URL is required in production.",
            remediation="Set DATABASE_URL in your .env file (e.g. sqlite:///instance/prod.db).",
        )


def _validate_role_models(config: dict[str, Any], result: ValidationResult) -> None:
    pipeline = _get_pipeline(config)
    pipeline_section = pipeline.get("pipeline", {})
    if not isinstance(pipeline_section, dict):
        return

    for role in _ROLES:
        role_config = pipeline_section.get(role, {})
        if not isinstance(role_config, dict):
            continue
        if role_config.get("enabled") is False:
            continue

        model = role_config.get("model")
        if model is None or model == "null":
            continue

        if not isinstance(model, str) or not model:
            continue

        if "/" not in model and ":" not in model:
            result.add_warning(
                code="ROLE_MODEL_INVALID",
                file="pipeline.yaml",
                key=f"pipeline.{role}.model",
                message=f"Role {role!r} model {model!r} does not follow expected format (provider/model or model:variant).",
                remediation=f"Use a model string like 'ollama/qwen3:8b' or 'gpt-4' for {role!r}.",
            )


def _validate_safe_fetch(config: dict[str, Any], result: ValidationResult) -> None:
    env = _get_environment(config)

    for key, (lo, hi) in _SAFE_FETCH_BOUNDS.items():
        val = env.get(key)
        if val is None:
            continue
        try:
            int_val = int(val)
        except (ValueError, TypeError):
            result.add_error(
                code="SAFE_FETCH_OUT_OF_RANGE",
                file=".env",
                key=key,
                message=f"{key} must be an integer, got {val!r}.",
                remediation=f"Set {key} to an integer between {lo} and {hi}.",
            )
            continue
        if not (lo <= int_val <= hi):
            result.add_error(
                code="SAFE_FETCH_OUT_OF_RANGE",
                file=".env",
                key=key,
                message=f"{key} must be between {lo} and {hi}, got {int_val}.",
                remediation=f"Set {key} to a value between {lo} and {hi}.",
            )


def _validate_themes(config: dict[str, Any], result: ValidationResult) -> None:
    env = _get_environment(config)

    max_bytes_str = env.get("THEMES_MAX_FILE_BYTES")
    if max_bytes_str is not None:
        try:
            max_bytes = int(max_bytes_str)
        except (ValueError, TypeError):
            result.add_error(
                code="THEME_CONFIG_INVALID",
                file=".env",
                key="THEMES_MAX_FILE_BYTES",
                message=f"THEMES_MAX_FILE_BYTES must be an integer, got {max_bytes_str!r}.",
                remediation=f"Set THEMES_MAX_FILE_BYTES to an integer between {_THEME_MAX_FILE_BYTES_MIN} and {_THEME_MAX_FILE_BYTES_MAX}.",
            )
        else:
            if not (_THEME_MAX_FILE_BYTES_MIN <= max_bytes <= _THEME_MAX_FILE_BYTES_MAX):
                result.add_error(
                    code="THEME_CONFIG_INVALID",
                    file=".env",
                    key="THEMES_MAX_FILE_BYTES",
                    message=f"THEMES_MAX_FILE_BYTES must be between {_THEME_MAX_FILE_BYTES_MIN} and {_THEME_MAX_FILE_BYTES_MAX}, got {max_bytes}.",
                    remediation=f"Set THEMES_MAX_FILE_BYTES to a value between {_THEME_MAX_FILE_BYTES_MIN} and {_THEME_MAX_FILE_BYTES_MAX}.",
                )

    custom_dir = env.get("THEMES_CUSTOM_DIR")
    allow_custom = env.get("THEMES_ALLOW_CUSTOM")
    if custom_dir and isinstance(custom_dir, str) and allow_custom is not None:
        if allow_custom.strip().lower() in ("false", "0", "no"):
            result.add_warning(
                code="THEME_CONFIG_INVALID",
                file=".env",
                key="THEMES_CUSTOM_DIR",
                message="THEMES_CUSTOM_DIR is set but THEMES_ALLOW_CUSTOM is disabled.",
                remediation="Enable THEMES_ALLOW_CUSTOM or remove THEMES_CUSTOM_DIR.",
            )


def _validate_redis(config: dict[str, Any], result: ValidationResult) -> None:
    env = _get_environment(config)
    flask_config = env.get("FLASK_CONFIG", "")

    broker = env.get("CELERY_BROKER_URL", "")
    backend = env.get("CELERY_RESULT_BACKEND", "")

    if flask_config == "production":
        if not broker:
            result.add_error(
                code="REDIS_URL_MISSING",
                file=".env",
                key="CELERY_BROKER_URL",
                message="CELERY_BROKER_URL is required in production mode.",
                remediation="Set CELERY_BROKER_URL to a Redis URL, e.g. redis://localhost:6379/0.",
            )
        if not backend:
            result.add_error(
                code="REDIS_URL_MISSING",
                file=".env",
                key="CELERY_RESULT_BACKEND",
                message="CELERY_RESULT_BACKEND is required in production mode.",
                remediation="Set CELERY_RESULT_BACKEND to a Redis URL, e.g. redis://localhost:6379/1.",
            )

    if not broker or not backend:
        return

    broker_is_redis = isinstance(broker, str) and broker.startswith("redis://")
    backend_is_redis = isinstance(backend, str) and backend.startswith("redis://")

    if broker_is_redis and not backend_is_redis:
        result.add_warning(
            code="REDIS_URL_MISMATCH",
            file=".env",
            key="CELERY_RESULT_BACKEND",
            message="Celery broker is Redis but result backend is not.",
            remediation="Set CELERY_RESULT_BACKEND to a Redis URL for consistent task state tracking.",
        )
    elif not broker_is_redis and backend_is_redis:
        result.add_warning(
            code="REDIS_URL_MISMATCH",
            file=".env",
            key="CELERY_BROKER_URL",
            message="Celery result backend is Redis but broker is not.",
            remediation="Set CELERY_BROKER_URL to a Redis URL for consistent task state tracking.",
        )
    elif broker_is_redis and backend_is_redis:
        from urllib.parse import urlparse

        broker_parsed = urlparse(broker)
        backend_parsed = urlparse(backend)

        if broker_parsed.port == backend_parsed.port and broker_parsed.hostname == backend_parsed.hostname:
            broker_db = broker_parsed.path.lstrip("/") or "0"
            backend_db = backend_parsed.path.lstrip("/") or "0"
            if broker_db == backend_db:
                result.add_warning(
                    code="REDIS_URL_MISMATCH",
                    file=".env",
                    key="CELERY_RESULT_BACKEND",
                    message="Broker and result backend share the same Redis DB. Use different DBs to avoid key collisions.",
                    remediation="Use different Redis DB numbers, e.g. redis://localhost:6379/0 for broker and redis://localhost:6379/1 for backend.",
                )

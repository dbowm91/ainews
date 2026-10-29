from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any

from ainews_config.paths import ConfigFile


class FieldType(enum.Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    PATH = "path"


class SecretClassification(enum.Enum):
    SECRET = "secret"
    SENSITIVE = "sensitive"
    PUBLIC = "public"
    GENERATED = "generated"
    DEPRECATED = "deprecated"


class RuntimeComponent(enum.Enum):
    WEB = "web"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    NONE = "none"


@dataclass(frozen=True)
class ConfigField:
    key: str
    destination: ConfigFile
    path: tuple[str, ...]
    field_type: FieldType
    secret: SecretClassification = SecretClassification.PUBLIC
    restart_impact: frozenset[RuntimeComponent] = frozenset()
    required: bool = False
    nullable: bool = False
    default: Any = None
    default_source: str = "code"
    description: str = ""
    aliases: tuple[str, ...] = ()
    deprecated: bool = False
    validator: str | None = None
    consumers: tuple[str, ...] = ()
    env_var: str | None = None


_ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass
class FieldRegistry:
    _fields: dict[str, ConfigField] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(self, fld: ConfigField) -> None:
        self._fields[fld.key] = fld
        for alias in fld.aliases:
            self._aliases[alias] = fld.key

    def lookup(self, key: str) -> ConfigField | None:
        canonical = self._aliases.get(key, key)
        return self._fields.get(canonical)

    def by_destination(self, dest: ConfigFile) -> list[ConfigField]:
        return [f for f in self._fields.values() if f.destination == dest]

    def by_secret(self, classification: SecretClassification) -> list[ConfigField]:
        return [f for f in self._fields.values() if f.secret == classification]

    def all_keys(self) -> list[str]:
        return sorted(self._fields.keys())

    def validate_key(self, key: str) -> ConfigField:
        fld = self.lookup(key)
        if fld is None:
            raise KeyError(key)
        return fld


FIELD_REGISTRY = FieldRegistry()


def lookup_field(key: str) -> ConfigField | None:
    return FIELD_REGISTRY.lookup(key)


def _env(key: str, **kwargs: Any) -> ConfigField:
    env_var = kwargs.pop("env_var", None)
    if env_var is None:
        env_var = key.upper()
    path: tuple[str, ...] = kwargs.pop("path", ())
    if not path:
        path = (key.lower().replace(".", "_"),)
    return ConfigField(
        key=key,
        destination=ConfigFile.ENV,
        path=path,
        env_var=env_var,
        **kwargs,
    )


def _yaml(
    key: str,
    dest: ConfigFile,
    path: tuple[str, ...],
    **kwargs: Any,
) -> ConfigField:
    return ConfigField(
        key=key,
        destination=dest,
        path=path,
        **kwargs,
    )


_ENV_FIELDS = [
    _env("secret_key", field_type=FieldType.STRING, secret=SecretClassification.SECRET, required=True, description="Session signing and CSRF protection", aliases=("secret",)),
    _env("admin_password", field_type=FieldType.STRING, secret=SecretClassification.SECRET, required=True, description="Admin dashboard password", aliases=("admin_pass",)),
    _env("celery_task_secret", field_type=FieldType.STRING, secret=SecretClassification.SECRET, required=True, description="HMAC signing secret for Celery tasks"),
    _env("flask_config", field_type=FieldType.STRING, description="Flask configuration name (development, production, testing)"),
    _env("smtp_host", field_type=FieldType.STRING, default="localhost", description="SMTP server hostname", aliases=("mail_host",)),
    _env("smtp_port", field_type=FieldType.INT, default=587, description="SMTP server port", aliases=("mail_port",)),
    _env("smtp_user", field_type=FieldType.STRING, description="SMTP authentication username"),
    _env("smtp_password", field_type=FieldType.STRING, secret=SecretClassification.SECRET, description="SMTP authentication password"),
    _env("smtp_from", field_type=FieldType.STRING, default="noreply@ainews.dev", description="Sender email address"),
    _env("smtp_use_tls", field_type=FieldType.BOOL, default=True, description="Enable TLS for SMTP connection"),
    _env("smtp_pool_size", field_type=FieldType.INT, default=5, description="SMTP connection pool size"),
    _env("celery_broker_url", field_type=FieldType.STRING, default="redis://localhost:6379/0", restart_impact=frozenset({RuntimeComponent.WEB, RuntimeComponent.WORKER}), description="Redis URL for Celery task broker", aliases=("broker_url",)),
    _env("celery_result_backend", field_type=FieldType.STRING, default="redis://localhost:6379/1", restart_impact=frozenset({RuntimeComponent.WEB, RuntimeComponent.WORKER}), description="Redis URL for Celery result backend"),
    _env("database_url", field_type=FieldType.STRING, default="sqlite:///instance/prod.db", restart_impact=frozenset({RuntimeComponent.WEB, RuntimeComponent.WORKER}), description="SQLite database URL", aliases=("db_url",)),
    _env("safe_fetch_max_redirects", field_type=FieldType.INT, default=5, description="Maximum redirects for safe fetch client"),
    _env("safe_fetch_max_bytes", field_type=FieldType.INT, default=2000000, description="Maximum response body size in bytes"),
    _env("safe_fetch_connect_timeout", field_type=FieldType.FLOAT, default=5.0, description="Connection timeout in seconds"),
    _env("safe_fetch_read_timeout", field_type=FieldType.FLOAT, default=10.0, description="Read timeout in seconds"),
    _env("safe_fetch_total_timeout", field_type=FieldType.FLOAT, default=20.0, description="Total timeout in seconds"),
    _env("dns_cache_ttl", field_type=FieldType.INT, default=300, description="DNS cache TTL in seconds"),
    _env("dns_cache_max", field_type=FieldType.INT, default=1024, description="DNS cache max entries"),
    _env("l1_cache_maxsize", field_type=FieldType.INT, default=1000, description="L1 in-memory cache max entries"),
    _env("login_max_attempts", field_type=FieldType.INT, default=5, description="Max login attempts before lockout"),
    _env("login_lockout_seconds", field_type=FieldType.INT, default=900, description="Lockout duration in seconds"),
    _env("min_content_length", field_type=FieldType.INT, default=200, description="Minimum content length for article extraction"),
    _env("verification_expiry_seconds", field_type=FieldType.INT, default=3600, description="Email verification token expiry in seconds"),
    _env("max_stage_retries", field_type=FieldType.INT, default=3, description="Max retries per pipeline stage"),
    _env("max_total_retries", field_type=FieldType.INT, default=10, description="Max total retries across all stages"),
    _env("pipeline_timeout_seconds", field_type=FieldType.INT, default=3600, description="Hard timeout for pipeline processing"),
    _env("max_consecutive_failures", field_type=FieldType.INT, default=10, description="Max consecutive crawl failures before source deactivation"),
    _env("stuck_threshold_minutes", field_type=FieldType.INT, default=60, description="Minutes before pipeline considers article stuck"),
    _env("retry_soft_cutoff_minutes", field_type=FieldType.INT, default=15, description="Soft cutoff for retry scheduling"),
    _env("themes_enabled", field_type=FieldType.BOOL, default=True, restart_impact=frozenset({RuntimeComponent.WEB}), description="Enable theme subsystem"),
    _env("themes_custom_dir", field_type=FieldType.PATH, restart_impact=frozenset({RuntimeComponent.WEB}), description="Directory for operator-provided themes"),
    _env("themes_allow_custom", field_type=FieldType.BOOL, default=True, restart_impact=frozenset({RuntimeComponent.WEB}), description="Allow loading custom themes"),
    _env("themes_default", field_type=FieldType.STRING, restart_impact=frozenset({RuntimeComponent.WEB}), description="Default theme identifier"),
    _env("themes_default_dark", field_type=FieldType.STRING, default="catppuccin-mocha", restart_impact=frozenset({RuntimeComponent.WEB}), description="Default dark theme identifier"),
    _env("themes_default_light", field_type=FieldType.STRING, default="catppuccin-latte", restart_impact=frozenset({RuntimeComponent.WEB}), description="Default light theme identifier"),
    _env("themes_max_file_bytes", field_type=FieldType.INT, default=262144, restart_impact=frozenset({RuntimeComponent.WEB}), description="Max bytes per external theme file"),
    _env("themes_strict_contrast", field_type=FieldType.BOOL, default=False, restart_impact=frozenset({RuntimeComponent.WEB}), description="Enable strict contrast validation"),
    _env("db_query_log_level", field_type=FieldType.STRING, default="WARNING", description="Database query log level"),
    _env("running_in_docker", field_type=FieldType.BOOL, description="Indicates Docker container execution"),
]

for _f in _ENV_FIELDS:
    FIELD_REGISTRY.register(_f)

_PROVIDER_FIELDS = [
    _yaml(
        "default_provider",
        dest=ConfigFile.PROVIDERS,
        path=("default_provider",),
        field_type=FieldType.STRING,
        default="ollama-local",
        description="Default LLM provider ID",
    ),
    _yaml(
        "default_search_provider",
        dest=ConfigFile.PROVIDERS,
        path=("default_search_provider",),
        field_type=FieldType.STRING,
        default="duckduckgo",
        description="Default search provider ID",
    ),
    _yaml(
        "providers",
        dest=ConfigFile.PROVIDERS,
        path=("providers",),
        field_type=FieldType.DICT,
        description="List of LLM provider definitions",
    ),
    _yaml(
        "search_providers",
        dest=ConfigFile.PROVIDERS,
        path=("search_providers",),
        field_type=FieldType.DICT,
        description="List of search provider definitions",
    ),
]

for _f in _PROVIDER_FIELDS:
    FIELD_REGISTRY.register(_f)

_ROLES = ("selector", "researcher", "writer", "editor")
_ROLE_FIELDS: list[ConfigField] = []

for _role in _ROLES:
    prefix = f"pipeline.{_role}"
    _ROLE_FIELDS.extend([
        _yaml(f"{prefix}.enabled", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "enabled"), field_type=FieldType.BOOL, default=True, description=f"Enable {_role} role"),
        _yaml(f"{prefix}.provider", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "provider"), field_type=FieldType.STRING, description=f"LLM provider for {_role}"),
        _yaml(f"{prefix}.model", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "model"), field_type=FieldType.STRING, description=f"LLM model for {_role}"),
        _yaml(f"{prefix}.max_tokens", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "max_tokens"), field_type=FieldType.INT, default=4096, description=f"Max tokens for {_role}"),
        _yaml(f"{prefix}.temperature", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "temperature"), field_type=FieldType.FLOAT, default=0.0, description=f"Temperature for {_role}"),
        _yaml(f"{prefix}.concurrency", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "concurrency"), field_type=FieldType.INT, default=2, description=f"Concurrency for {_role}"),
        _yaml(f"{prefix}.timeout_seconds", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "timeout_seconds"), field_type=FieldType.INT, default=120, description=f"Timeout for {_role}"),
        _yaml(f"{prefix}.system_prompt", dest=ConfigFile.PIPELINE, path=("pipeline", _role, "system_prompt"), field_type=FieldType.STRING, secret=SecretClassification.SENSITIVE, nullable=True, description=f"System prompt for {_role}"),
    ])

_ROLE_FIELDS.extend([
    _yaml("pipeline.researcher.web_search", dest=ConfigFile.PIPELINE, path=("pipeline", "researcher", "web_search"), field_type=FieldType.BOOL, nullable=True, description="Enable web search in research"),
    _yaml("pipeline.researcher.web_search_max_results", dest=ConfigFile.PIPELINE, path=("pipeline", "researcher", "web_search_max_results"), field_type=FieldType.INT, nullable=True, description="Max web search results"),
    _yaml("pipeline.researcher.web_search_provider", dest=ConfigFile.PIPELINE, path=("pipeline", "researcher", "web_search_provider"), field_type=FieldType.STRING, nullable=True, description="Search provider for researcher"),
    _yaml("pipeline.researcher.db_related_max", dest=ConfigFile.PIPELINE, path=("pipeline", "researcher", "db_related_max"), field_type=FieldType.INT, nullable=True, description="Max related articles from DB"),
    _yaml("pipeline.researcher.max_article_text_length", dest=ConfigFile.PIPELINE, path=("pipeline", "researcher", "max_article_text_length"), field_type=FieldType.INT, nullable=True, description="Max article text length for research"),
    _yaml("pipeline.writer.max_key_points", dest=ConfigFile.PIPELINE, path=("pipeline", "writer", "max_key_points"), field_type=FieldType.INT, nullable=True, description="Max key points for writer"),
    _yaml("pipeline.editor.max_tags", dest=ConfigFile.PIPELINE, path=("pipeline", "editor", "max_tags"), field_type=FieldType.INT, nullable=True, description="Max tags for editor"),
    _yaml("pipeline.review.enabled", dest=ConfigFile.PIPELINE, path=("pipeline", "review", "enabled"), field_type=FieldType.BOOL, default=False, description="Enable manual review stage"),
    _yaml("pipeline.review.auto_publish_threshold", dest=ConfigFile.PIPELINE, path=("pipeline", "review", "auto_publish_threshold"), field_type=FieldType.FLOAT, default=0.8, description="Auto-publish quality threshold"),
])

_NEWSLETTER_FIELDS = [
    _yaml("newsletter.max_articles", dest=ConfigFile.PIPELINE, path=("newsletter", "max_articles"), field_type=FieldType.INT, default=10, description="Max articles per newsletter"),
    _yaml("newsletter.send_time", dest=ConfigFile.PIPELINE, path=("newsletter", "send_time"), field_type=FieldType.STRING, default="08:00", description="Newsletter send time (HH:MM)"),
    _yaml("newsletter.timezone", dest=ConfigFile.PIPELINE, path=("newsletter", "timezone"), field_type=FieldType.STRING, default="America/New_York", description="Newsletter timezone"),
    _yaml("newsletter.site_url", dest=ConfigFile.PIPELINE, path=("newsletter", "site_url"), field_type=FieldType.STRING, default="https://ainews.dev", description="Site URL for newsletter"),
    _yaml("newsletter.prep_minutes", dest=ConfigFile.PIPELINE, path=("newsletter", "prep_minutes"), field_type=FieldType.INT, default=15, description="Newsletter prep time in minutes"),
]

_SUBAGENT_FIELDS = [
    _yaml("subagent.default.enabled", dest=ConfigFile.PIPELINE, path=("subagent", "default", "enabled"), field_type=FieldType.BOOL, default=False, description="Enable default subagent"),
    _yaml("subagent.research.enabled", dest=ConfigFile.PIPELINE, path=("subagent", "research", "enabled"), field_type=FieldType.BOOL, default=False, description="Enable research subagent"),
    _yaml("subagent.edit.enabled", dest=ConfigFile.PIPELINE, path=("subagent", "edit", "enabled"), field_type=FieldType.BOOL, default=False, description="Enable edit subagent"),
]

_MEMORY_FIELDS = [
    _yaml("memory.ttl_days_low", dest=ConfigFile.PIPELINE, path=("memory", "ttl_days_low"), field_type=FieldType.INT, default=7, description="TTL for low-priority memory entries"),
    _yaml("memory.ttl_days_medium", dest=ConfigFile.PIPELINE, path=("memory", "ttl_days_medium"), field_type=FieldType.INT, default=30, description="TTL for medium-priority memory entries"),
    _yaml("memory.ttl_days_high", dest=ConfigFile.PIPELINE, path=("memory", "ttl_days_high"), field_type=FieldType.INT, default=0, description="TTL for high-priority memory entries (0=infinite)"),
    _yaml("memory.consolidation_cooldown_hours", dest=ConfigFile.PIPELINE, path=("memory", "consolidation_cooldown_hours"), field_type=FieldType.INT, default=24, description="Hours between memory consolidation runs"),
    _yaml("memory.max_entries_per_propose", dest=ConfigFile.PIPELINE, path=("memory", "max_entries_per_propose"), field_type=FieldType.INT, default=10, description="Max memory entries per proposal"),
    _yaml("memory.consolidation_merge_window_hours", dest=ConfigFile.PIPELINE, path=("memory", "consolidation_merge_window_hours"), field_type=FieldType.INT, default=48, description="Hours for consolidation merge window"),
    _yaml("memory.truncation_llm_provider", dest=ConfigFile.PIPELINE, path=("memory", "truncation_llm_provider"), field_type=FieldType.STRING, nullable=True, description="LLM provider for memory truncation"),
    _yaml("memory.truncation_llm_model", dest=ConfigFile.PIPELINE, path=("memory", "truncation_llm_model"), field_type=FieldType.STRING, nullable=True, description="LLM model for memory truncation"),
    _yaml("memory.truncation_llm_max_tokens", dest=ConfigFile.PIPELINE, path=("memory", "truncation_llm_max_tokens"), field_type=FieldType.INT, default=1024, description="Max tokens for memory truncation LLM"),
    _yaml("memory.truncation_llm_temperature", dest=ConfigFile.PIPELINE, path=("memory", "truncation_llm_temperature"), field_type=FieldType.FLOAT, default=0.0, description="Temperature for memory truncation LLM"),
]

_SCHEDULE_FIELDS = [
    _yaml("schedule.crawl_interval_minutes", dest=ConfigFile.PIPELINE, path=("schedule", "crawl_interval_minutes"), field_type=FieldType.INT, default=30, description="Crawl interval in minutes"),
    _yaml("schedule.generate_newsletters_hour", dest=ConfigFile.PIPELINE, path=("schedule", "generate_newsletters_hour"), field_type=FieldType.INT, default=8, description="Hour to generate newsletters (UTC)"),
    _yaml("schedule.cleanup_old_logs_hour", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_old_logs_hour"), field_type=FieldType.INT, default=3, description="Hour to clean up old logs (UTC)"),
    _yaml("schedule.consolidate_trend_memory_hour", dest=ConfigFile.PIPELINE, path=("schedule", "consolidate_trend_memory_hour"), field_type=FieldType.INT, default=3, description="Hour to consolidate trend memory (UTC)"),
    _yaml("schedule.cleanup_inactive_subscribers_hour", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_inactive_subscribers_hour"), field_type=FieldType.INT, default=1, description="Hour to clean up inactive subscribers (UTC)"),
    _yaml("schedule.retry_stuck_interval_minutes", dest=ConfigFile.PIPELINE, path=("schedule", "retry_stuck_interval_minutes"), field_type=FieldType.INT, default=60, description="Minutes between stuck article retries"),
    _yaml("schedule.cleanup_old_versions_hour", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_old_versions_hour"), field_type=FieldType.INT, default=3, description="Hour to clean up old article versions (UTC)"),
    _yaml("schedule.cleanup_old_versions_days_to_keep", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_old_versions_days_to_keep"), field_type=FieldType.INT, default=30, description="Days to keep old article versions"),
    _yaml("schedule.cleanup_expired_verifications_interval_minutes", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_expired_verifications_interval_minutes"), field_type=FieldType.INT, default=15, description="Minutes between expired verification cleanups"),
    _yaml("schedule.publish_scheduled_interval_minutes", dest=ConfigFile.PIPELINE, path=("schedule", "publish_scheduled_interval_minutes"), field_type=FieldType.INT, default=5, description="Minutes between scheduled publish checks"),
    _yaml("schedule.cleanup_stale_limiter_interval_minutes", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_stale_limiter_interval_minutes"), field_type=FieldType.INT, default=5, description="Minutes between stale limiter slot cleanups"),
    _yaml("schedule.cleanup_inactive_subscribers_minute", dest=ConfigFile.PIPELINE, path=("schedule", "cleanup_inactive_subscribers_minute"), field_type=FieldType.INT, default=0, description="Minute of hour for inactive subscriber cleanup"),
    _yaml("schedule.auto_approve_interval_minutes", dest=ConfigFile.PIPELINE, path=("schedule", "auto_approve_interval_minutes"), field_type=FieldType.INT, default=1, description="Minutes between auto-review mode passes over the review queue"),
]

_EXPERIMENTS_FIELDS = [
    _yaml("experiments", dest=ConfigFile.PIPELINE, path=("experiments",), field_type=FieldType.DICT, nullable=True, description="A/B experiment configurations"),
]

_PIPELINE_FIELDS = (
    _ROLE_FIELDS
    + _NEWSLETTER_FIELDS
    + _SUBAGENT_FIELDS
    + _MEMORY_FIELDS
    + _SCHEDULE_FIELDS
    + _EXPERIMENTS_FIELDS
)

for _f in _PIPELINE_FIELDS:
    FIELD_REGISTRY.register(_f)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceAdapterField:
    """Metadata for a source adapter input field."""
    name: str
    label: str
    description: str
    field_type: str  # "text", "password", "url", "select", "bool", "int"
    required: bool = True
    default: str | None = None
    options: list[str] | None = None
    sensitive: bool = False


@dataclass
class SourceAdapterMetadata:
    """Metadata describing a source adapter type's capabilities and requirements."""
    type_id: str
    display_name: str
    description: str
    endpoint_field: str  # primary field name used for connectivity testing (e.g., "feed_url")
    auth_fields: list[str] = field(default_factory=list)  # fields that are authentication-related
    opml_representable: bool = False  # can this source type be exported to OPML?
    default_schedule_minutes: int = 30
    requires_config: list[str] = field(default_factory=list)  # required config sub-keys
    sensitive_fields: list[str] = field(default_factory=list)  # fields to redact in output
    user_facing_fields: list[str] = field(default_factory=list)  # fields to show in list output


@dataclass
class SourceDefinition:
    """A source configuration definition."""
    id: str
    name: str
    type: str
    enabled: bool = True
    schedule_minutes: int = 30
    config: dict[str, Any] = field(default_factory=dict)
    topics: dict[str, Any] = field(default_factory=dict)
    # Display-friendly fields extracted from config
    endpoint_summary: str = ""
    # Computed fields
    requires_restart: bool = False
    requires_schedule_refresh: bool = False


@dataclass
class SourceTestResult:
    """Result of testing a source configuration."""
    source_id: str
    outcome: str  # "config_error", "safety_block", "transport_error", "upstream_error", "parse_error", "success"
    message: str
    latency_ms: float | None = None
    status_code: int | None = None
    reason_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContentMutationResult:
    """Result of a content mutation operation (add/update/remove)."""
    success: bool
    source_id: str | None = None
    operation: str = ""  # "add", "update", "remove", "enable", "disable"
    message: str = ""
    requires_restart: bool = False
    requires_schedule_refresh: bool = False
    diff: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RestartImpact:
    """Reports whether a configuration change requires a worker restart."""
    requires_restart: bool = False
    requires_schedule_refresh: bool = False
    affected_roles: list[str] = field(default_factory=list)
    affected_sources: list[str] = field(default_factory=list)
    message: str = ""

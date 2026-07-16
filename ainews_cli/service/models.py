"""Typed models for service unit specifications."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path


class ServiceScope(enum.Enum):
    USER = "user"
    SYSTEM = "system"


class ServiceProfile(enum.Enum):
    """Deployment profile determines which services are relevant."""
    DOCKER_COMPOSE = "docker_compose"
    BARE_METAL = "bare_metal"


class RestartPolicy(enum.Enum):
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    NO = "no"


@dataclass(frozen=True)
class ServiceUnitSpec:
    """Specification for a single systemd service unit."""
    name: str
    description: str
    scope: ServiceScope
    profile: ServiceProfile
    exec_start: str
    exec_stop: str | None = None
    exec_reload: str | None = None
    working_directory: Path | None = None
    environment_file: Path | None = None
    restart_policy: RestartPolicy = RestartPolicy.ON_FAILURE
    restart_sec: int = 5
    start_limit_burst: int = 5
    start_limit_interval_sec: int = 60
    timeout_start_sec: int = 120
    timeout_stop_sec: int = 30
    user: str | None = None
    group: str | None = None
    wanted_by: str = "multi-user.target"
    after: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    documentation: str | None = None
    # Hardening
    no_new_privileges: bool = True
    private_tmp: bool = True
    protect_system: str | None = "strict"
    protect_home: bool = True
    umask: str = "0027"
    capability_bounding_set: str = ""  # Empty = drop all capabilities
    ambient_capabilities: str = ""
    restrict_namespaces: bool = True
    restrict_realtime: bool = True
    restrict_suidsgid: bool = True
    memory_deny_write_execute: bool = True
    lock_personality: bool = True
    system_call_architectures: str = "native"
    private_network: bool = False  # Only for truly offline services
    private_devices: bool = True
    protect_kernel_tunables: bool = True
    protect_kernel_modules: bool = True
    protect_control_groups: bool = True
    protect_clock: bool = True
    restrict_address_families: str | None = "AF_INET AF_INET6 AF_UNIX"
    system_call_filter: str | None = None  # e.g., "@system-service"
    # Logging
    standard_output: str = "journal"
    standard_error: str = "journal"
    syslog_identifier: str | None = None


@dataclass(frozen=True)
class LogrotateRuleSpec:
    """Specification for a logrotate rule."""
    name: str
    log_paths: list[str]
    frequency: str = "daily"
    rotate_count: int = 10
    compress: bool = True
    delay_compress: bool = True
    missing_ok: bool = True
    notif_empty: bool = True
    create_mode: str = "0640"
    create_user: str = "root"
    create_group: str = "adm"
    postrotate: str | None = None
    prerotate: str | None = None
    size: str | None = None  # e.g., "100M"
    maxsize: str | None = None


@dataclass(frozen=True)
class RenderedUnit:
    """A rendered systemd unit file with metadata."""
    spec: ServiceUnitSpec
    content: str
    filename: str
    install_path: Path  # Where it would be installed


@dataclass(frozen=True)
class RenderedLogrotateRule:
    """A rendered logrotate rule with metadata."""
    spec: LogrotateRuleSpec
    content: str
    filename: str
    install_path: Path


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a unit or logrotate rule."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class InstalledUnitRecord:
    """Record of an installed unit for ownership tracking."""
    unit_name: str
    unit_type: str  # "service", "timer"
    install_path: Path
    content_hash: str  # SHA-256
    installed_at: str  # ISO timestamp
    scope: ServiceScope

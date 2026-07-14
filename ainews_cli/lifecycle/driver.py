from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LifecycleResult:
    success: bool
    message: str
    details: dict | None = None
    degraded: bool = False
    degraded_warnings: list[str] | None = None


@dataclass
class ServiceStatus:
    name: str
    state: str  # "running", "stopped", "failed", "starting", "unknown"
    health: str | None  # "healthy", "unhealthy", "starting", None


@dataclass
class StatusResult:
    success: bool
    services: list[ServiceStatus]
    web_url: str | None = None
    redis_ok: bool = False
    database_ok: bool = False
    celery_ok: bool = False
    pending_migrations: int = 0
    providers_summary: list[dict] | None = None


@dataclass
class LogsResult:
    success: bool
    output: str
    truncated: bool = False


@dataclass
class HealthResult:
    success: bool
    status: str  # "ok", "degraded", "error"
    checks: dict = field(default_factory=dict)
    response_time_ms: float | None = None


@dataclass
class SmokeResult:
    success: bool
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class LifecycleDriver(Protocol):
    def start(self, timeout: int = 120, no_wait: bool = False) -> LifecycleResult: ...
    def stop(self) -> LifecycleResult: ...
    def restart(self, timeout: int = 120) -> LifecycleResult: ...
    def status(self) -> StatusResult: ...
    def logs(
        self,
        service: str | None = None,
        tail: int = 100,
        follow: bool = False,
        timestamps: bool = False,
        raw: bool = False,
    ) -> LogsResult: ...
    def health(self, timeout: int = 10) -> HealthResult: ...
    def smoke(self, timeout: int = 30) -> SmokeResult: ...

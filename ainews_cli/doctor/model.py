from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    remediation: str | None = None
    blocking: bool = False
    details: dict[str, object] | str | None = None
    duration_ms: float | None = None

    @property
    def passed(self) -> bool:
        return self.status in (CheckStatus.PASS, CheckStatus.SKIP)

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "name": self.name,
            "status": self.status.value,
            "passed": self.passed,
            "message": self.message,
        }
        if self.details is not None:
            d["details"] = self.details
        if self.remediation is not None:
            d["remediation"] = self.remediation
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.blocking:
            d["blocking"] = True
        return d


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.status != CheckStatus.FAIL for c in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def skipped_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.SKIP)

    def to_dict(self) -> dict[str, object]:
        return {
            "all_passed": self.all_passed,
            "passed_count": self.passed_count,
            "warn_count": self.warn_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "checks": [c.to_dict() for c in self.checks],
        }


def check_pass(name: str, message: str, **kwargs: Any) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.PASS, message=message, **kwargs)


def check_warn(name: str, message: str, **kwargs: Any) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.WARN, message=message, **kwargs)


def check_fail(name: str, message: str, **kwargs: Any) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.FAIL, message=message, **kwargs)


def check_skip(name: str, message: str, **kwargs: Any) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.SKIP, message=message, **kwargs)

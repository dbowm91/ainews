from __future__ import annotations

from ainews_cli.doctor.model import CheckResult, CheckStatus, DoctorReport

_STATUS_SYMBOLS = {
    CheckStatus.PASS: "\u2705",
    CheckStatus.WARN: "\u26a0\ufe0f",
    CheckStatus.FAIL: "\u274c",
    CheckStatus.SKIP: "\u23ed\ufe0f",
}


def render_check(check: CheckResult) -> str:
    symbol = _STATUS_SYMBOLS.get(check.status, "?")
    suffix = ""
    if check.duration_ms is not None:
        suffix = f" ({check.duration_ms:.0f}ms)"
    if check.reason_code is not None:
        suffix += f" [{check.reason_code}]"
    return f"  {symbol} {check.name}: {check.message}{suffix}"


def render_summary(report: DoctorReport) -> str:
    return (
        f"PASS: {report.passed_count} | "
        f"WARN: {report.warn_count} | "
        f"FAIL: {report.failed_count} | "
        f"SKIP: {report.skipped_count}"
    )


def render_human(report: DoctorReport) -> str:
    lines: list[str] = []
    for check in report.checks:
        lines.append(render_check(check))
        if check.remediation and check.status == CheckStatus.FAIL:
            lines.append(f"    Fix: {check.remediation}")
    lines.append("")
    lines.append(render_summary(report))
    return "\n".join(lines)

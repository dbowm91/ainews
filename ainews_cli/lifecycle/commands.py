from __future__ import annotations

import sys
from typing import Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter

app = typer.Typer(help="Lifecycle management commands")

_ctx = CLIContext()
_out = OutputFormatter()


def _get_driver():
    from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

    config = _ctx.ensure_loaded()
    return DockerComposeDriver(resolved_paths=config.paths)


@app.command()
def start(
    skip_doctor: bool = typer.Option(False, "--skip-doctor", help="Skip doctor prerequisites"),
    skip_migrations: bool = typer.Option(False, "--skip-migrations", help="Skip database migrations"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Don't wait for health check"),
    timeout: int = typer.Option(120, "--timeout", help="Timeout in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Start the ainews services."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    if not skip_doctor:
        from ainews_cli.doctor import run_doctor

        report = run_doctor()
        if not report.all_passed:
            _out.warning("Doctor checks failed. Use --skip-doctor to bypass.")
            if not json_output:
                for check in report.checks:
                    if not check.passed:
                        _out.error(f"  {check.name}: {check.message}")
            sys.exit(exit_codes.GENERAL_ERROR)

    driver = _get_driver()

    if not skip_migrations:
        from ainews_cli.migrations import run_migrations

        migration_result = run_migrations(_ctx.paths)
        if not migration_result["success"]:
            _out.error(f"Migration failed: {migration_result['error']}", exit_codes.GENERAL_ERROR)

    result = driver.start(timeout=timeout, no_wait=no_wait)

    if _ctx.json_output:
        _out.json_data({
            "success": result.success,
            "message": result.message,
            "details": result.details,
            "degraded": result.degraded,
            "degraded_warnings": result.degraded_warnings,
        })
    else:
        if result.success:
            _out.success(result.message)
        else:
            _out.error(result.message, exit_codes.GENERAL_ERROR)

        if result.degraded_warnings:
            for warning in result.degraded_warnings:
                _out.warning(warning)

        _out.info(f"\nDashboard: {result.details.get('web_url', 'http://localhost:5000') if result.details else 'http://localhost:5000'}")

    if not result.success:
        sys.exit(exit_codes.GENERAL_ERROR)


@app.command()
def stop() -> None:
    """Stop the ainews services."""
    driver = _get_driver()
    result = driver.stop()

    if _ctx.json_output:
        _out.json_data({"success": result.success, "message": result.message})
    else:
        if result.success:
            _out.success(result.message)
        else:
            _out.error(result.message, exit_codes.GENERAL_ERROR)

    if not result.success:
        sys.exit(exit_codes.GENERAL_ERROR)


@app.command()
def restart(
    skip_doctor: bool = typer.Option(False, "--skip-doctor", help="Skip doctor prerequisites"),
    timeout: int = typer.Option(120, "--timeout", help="Timeout in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Restart the ainews services."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    if not skip_doctor:
        from ainews_cli.doctor import run_doctor

        report = run_doctor()
        if not report.all_passed:
            _out.warning("Doctor checks failed — refusing to restart.")
            sys.exit(exit_codes.GENERAL_ERROR)

    driver = _get_driver()
    result = driver.restart(timeout=timeout)

    if _ctx.json_output:
        _out.json_data({
            "success": result.success,
            "message": result.message,
            "degraded": result.degraded,
            "degraded_warnings": result.degraded_warnings,
        })
    else:
        if result.success:
            _out.success(result.message)
        else:
            _out.error(result.message, exit_codes.GENERAL_ERROR)
        if result.degraded_warnings:
            for warning in result.degraded_warnings:
                _out.warning(warning)

    if not result.success:
        sys.exit(exit_codes.GENERAL_ERROR)


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Show service status."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    driver = _get_driver()
    result = driver.status()

    if _ctx.json_output:
        data = {
            "success": result.success,
            "services": [
                {"name": s.name, "state": s.state, "health": s.health}
                for s in result.services
            ],
            "web_url": result.web_url,
            "redis_ok": result.redis_ok,
            "database_ok": result.database_ok,
            "celery_ok": result.celery_ok,
            "pending_migrations": result.pending_migrations,
        }
        if result.providers_summary:
            data["providers_summary"] = result.providers_summary
        _out.json_data(data)
    else:
        headers = ["Service", "State", "Health"]
        rows = [[s.name, s.state, s.health or "-"] for s in result.services]
        if rows:
            _out.table(headers, rows)

        _out.info("")
        _out.info(f"Web URL:      {result.web_url or 'unavailable'}")
        _out.info(f"Redis:        {'ok' if result.redis_ok else 'unavailable'}")
        _out.info(f"Database:     {'ok' if result.database_ok else 'unavailable'}")
        _out.info(f"Celery:       {'ok' if result.celery_ok else 'unavailable'}")
        if result.pending_migrations > 0:
            _out.warning(f"Pending migrations: {result.pending_migrations}")


@app.command()
def logs(
    service: Optional[str] = typer.Argument(None, help="Service name"),
    tail: int = typer.Option(100, "--tail", help="Number of lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    timestamps: bool = typer.Option(False, "--timestamps", "-t", help="Show timestamps"),
    raw: bool = typer.Option(False, "--raw", help="Raw passthrough"),
) -> None:
    """View service logs."""
    driver = _get_driver()
    result = driver.logs(
        service=service,
        tail=tail,
        follow=follow,
        timestamps=timestamps,
        raw=raw,
    )

    if _ctx.json_output:
        _out.json_data({
            "success": result.success,
            "output": result.output,
            "truncated": result.truncated,
        })
    else:
        print(result.output, end="")


@app.command()
def health(
    timeout: int = typer.Option(10, "--timeout", help="Timeout in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Check service health."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    driver = _get_driver()
    result = driver.health(timeout=timeout)

    if _ctx.json_output:
        _out.json_data({
            "success": result.success,
            "status": result.status,
            "checks": result.checks,
            "response_time_ms": result.response_time_ms,
        })
    else:
        if result.success:
            _out.success(f"Health: {result.status}")
        else:
            _out.error(f"Health: {result.status}", exit_codes.GENERAL_ERROR)

        if result.response_time_ms is not None:
            _out.info(f"Response time: {result.response_time_ms:.1f}ms")

        for key, value in result.checks.items():
            _out.info(f"  {key}: {value}")


@app.command()
def smoke(
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Run post-deploy smoke checks."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    driver = _get_driver()
    result = driver.smoke(timeout=timeout)

    if _ctx.json_output:
        _out.json_data({
            "success": result.success,
            "passed": result.passed,
            "failed": result.failed,
            "details": result.details,
        })
    else:
        for name in result.passed:
            _out.success(f"  {name}")
        for name in result.failed:
            _out.error(f"  {name}")
        _out.info(f"\n{len(result.passed)}/{len(result.passed) + len(result.failed)} smoke checks passed")

    if not result.success:
        sys.exit(exit_codes.GENERAL_ERROR)


def register_lifecycle_commands(main_app: typer.Typer) -> None:
    """Register lifecycle commands on the main CLI app."""
    for cmd in (start, stop, restart, status, logs, health, smoke):
        main_app.command()(cmd)

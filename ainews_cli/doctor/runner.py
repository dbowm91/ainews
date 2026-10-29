from __future__ import annotations

from typing import TYPE_CHECKING

from ainews_cli.doctor.checks import (
    _check_package_version,
    _check_schema_version,
    _check_python_available,
    _check_resolved_paths,
    _check_directory_writable,
    _check_config_files,
    _check_config_validation,
    _check_placeholder_values,
    _check_secret_permissions,
    _check_secret_permissions_strict,
    _check_port_available,
    _check_redis_connection,
    _check_database_directory,
    _check_database_access,
    _check_database_migrations,
    _check_docker_available,
    _check_compose_available,
    _check_docker_dns_resolution,
    _check_compose_service_health,
    _check_flask_liveness,
    _check_readiness,
    _check_celery_workers,
    _check_provider_auth,
    _check_provider_model_availability,
    _check_eggsearch_installation,
    _check_smtp_connectivity,
    _check_source_connectivity,
    _check_port_conflicts,
)
from ainews_cli.doctor.model import DoctorReport

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


def run_doctor(
    *,
    paths: ResolvedPaths | None = None,
    production: bool = False,
    quick: bool = False,
    network: bool = False,
) -> DoctorReport:
    checks: list[CheckResult] = []

    if paths is None:
        from ainews_config import resolve_paths
        paths = resolve_paths()

    _check_package_version(checks)
    _check_schema_version(checks)
    _check_resolved_paths(paths, checks)
    _check_directory_writable(paths.config_dir.path, "config", checks)
    _check_directory_writable(paths.data_dir.path, "data", checks)
    _check_config_files(paths, checks)
    _check_config_validation(paths, checks, production=production)
    _check_eggsearch_installation(paths, checks)
    _check_secret_permissions(paths, checks)
    _check_database_directory(paths, checks)
    _check_python_available(checks)

    if quick:
        return DoctorReport(
            checks=checks,
            mode={"quick": quick, "production": production, "network": network},
        )

    _check_port_available(checks)
    _check_docker_available(checks)
    _check_compose_available(checks)
    _check_placeholder_values(paths, checks)

    if production:
        _check_secret_permissions_strict(paths, checks)

    _check_redis_connection(paths, checks)
    _check_database_access(paths, checks)
    _check_database_migrations(paths, checks)

    if network:
        _check_flask_liveness(paths, checks)
        _check_readiness(paths, checks)
        _check_celery_workers(paths, checks)
        _check_provider_auth(paths, checks)
        _check_provider_model_availability(paths, checks)
        _check_smtp_connectivity(paths, checks)
        _check_source_connectivity(paths, checks)
        _check_compose_service_health(paths, checks)
        _check_port_conflicts(paths, checks)
        _check_docker_dns_resolution(paths, checks)

    return DoctorReport(
        checks=checks,
        mode={"quick": quick, "production": production, "network": network},
    )

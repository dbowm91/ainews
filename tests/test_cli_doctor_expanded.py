from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from ainews_cli.doctor import (
    CheckResult,
    CheckStatus,
    _check_redis_connection,
    _check_database_access,
    _check_database_migrations,
    _check_flask_liveness,
    _check_readiness,
    _check_celery_workers,
    _check_provider_auth,
    _check_smtp_connectivity,
    _check_compose_service_health,
    _check_port_conflicts,
    run_doctor,
)
from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths


def _make_resolved_paths(tmp_path: Path) -> ResolvedPaths:
    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.EXPLICIT,
            exists=p.exists(),
            is_writable=True,
        )

    return ResolvedPaths(
        app_dir=_rp(tmp_path),
        config_dir=_rp(tmp_path),
        data_dir=_rp(tmp_path),
        state_dir=_rp(tmp_path),
        backup_dir=_rp(tmp_path),
        env_file=_rp(tmp_path / ".env"),
        providers_file=_rp(tmp_path / "providers.yaml"),
        pipeline_file=_rp(tmp_path / "pipeline.yaml"),
        sources_file=_rp(tmp_path / "sources.yaml"),
        topics_file=_rp(tmp_path / "topics.yaml"),
        database_file=_rp(tmp_path / "db.sqlite"),
        install_metadata_file=_rp(tmp_path / "meta.json"),
        transaction_lock=_rp(tmp_path / "lock"),
        transaction_staging=_rp(tmp_path / "staging"),
    )


def _make_paths_with_db(tmp_path: Path, db_path: Path) -> ResolvedPaths:
    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.EXPLICIT,
            exists=p.exists(),
            is_writable=True,
        )

    return ResolvedPaths(
        app_dir=_rp(tmp_path),
        config_dir=_rp(tmp_path),
        data_dir=_rp(tmp_path),
        state_dir=_rp(tmp_path),
        backup_dir=_rp(tmp_path),
        env_file=_rp(tmp_path / ".env"),
        providers_file=_rp(tmp_path / "providers.yaml"),
        pipeline_file=_rp(tmp_path / "pipeline.yaml"),
        sources_file=_rp(tmp_path / "sources.yaml"),
        topics_file=_rp(tmp_path / "topics.yaml"),
        database_file=_rp(db_path),
        install_metadata_file=_rp(tmp_path / "meta.json"),
        transaction_lock=_rp(tmp_path / "lock"),
        transaction_staging=_rp(tmp_path / "staging"),
    )


class TestCheckRedisConnection:
    def test_redis_ok(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_redis = MagicMock()
        mock_redis.from_url.return_value.ping.return_value = True
        with patch.dict("sys.modules", {"redis": mock_redis}):
            _check_redis_connection(paths, checks)
        assert len(checks) == 1
        assert checks[0].name == "redis_connection"
        assert checks[0].passed is True
        assert checks[0].status == CheckStatus.PASS

    def test_redis_not_installed(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        with patch.dict("sys.modules", {"redis": None}):
            _check_redis_connection(paths, checks)
        assert checks[0].passed is True
        assert checks[0].status == CheckStatus.SKIP
        assert "not installed" in checks[0].message

    def test_redis_connection_error(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_redis_mod = MagicMock()
        mock_redis_mod.from_url.return_value.ping.side_effect = OSError("refused")
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            _check_redis_connection(paths, checks)
        assert checks[0].passed is False
        assert checks[0].status == CheckStatus.FAIL
        assert "failed" in checks[0].message.lower()


class TestCheckDatabaseAccess:
    def test_no_database(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_database_access(paths, checks)
        assert checks[0].passed is True
        assert "not found" in checks[0].message

    def test_database_accessible(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
        paths = _make_paths_with_db(tmp_path, db_path)
        checks: list[CheckResult] = []
        _check_database_access(paths, checks)
        assert checks[0].passed is True
        assert "1 tables" in checks[0].message


class TestCheckDatabaseMigrations:
    def test_migrations_ok(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_status = {"needs_migration": False, "error": None}
        with patch("ainews_cli.migrations.get_migration_status", return_value=mock_status):
            _check_database_migrations(paths, checks)
        assert checks[0].passed is True

    def test_migrations_pending(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_status = {"needs_migration": True, "pending_count": 3, "error": None}
        with patch("ainews_cli.migrations.get_migration_status", return_value=mock_status):
            _check_database_migrations(paths, checks)
        assert checks[0].passed is False
        assert "3 pending" in checks[0].message


class TestCheckFlaskLiveness:
    def test_liveness_ok(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        with patch.dict("sys.modules", {"requests": mock_requests}):
            _check_flask_liveness(paths, checks)
        assert checks[0].passed is True

    def test_liveness_not_installed(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        with patch.dict("sys.modules", {"requests": None}):
            _check_flask_liveness(paths, checks)
        assert checks[0].passed is True
        assert checks[0].status == CheckStatus.SKIP
        assert "not installed" in checks[0].message


class TestCheckReadiness:
    def test_ready(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "ok"}
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        with patch.dict("sys.modules", {"requests": mock_requests}):
            _check_readiness(paths, checks)
        assert checks[0].passed is True

    def test_not_ready(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "error"}
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        with patch.dict("sys.modules", {"requests": mock_requests}):
            _check_readiness(paths, checks)
        assert checks[0].passed is False


class TestCheckCeleryWorkers:
    def test_workers_ok(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_sub = MagicMock()
        mock_sub.run.return_value = MagicMock(returncode=0, stdout="pong\n")
        with patch.dict("sys.modules", {"subprocess": mock_sub}):
            _check_celery_workers(paths, checks)
        assert checks[0].passed is True

    def test_workers_not_responding(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_sub = MagicMock()
        mock_sub.run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        with patch.dict("sys.modules", {"subprocess": mock_sub}):
            _check_celery_workers(paths, checks)
        assert checks[0].passed is False


class TestCheckProviderAuth:
    def test_no_providers(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_config = MagicMock()
        mock_config.providers = {"providers": {}}
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_provider_auth(paths, checks)
        assert checks[0].passed is True
        assert "no providers" in checks[0].message.lower()

    def test_providers_configured(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_config = MagicMock()
        mock_config.providers = {
            "default_provider": "ollama",
            "providers": {"ollama": {"type": "ollama", "enabled": True}},
        }
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_provider_auth(paths, checks)
        assert checks[0].passed is True
        assert "1 provider" in checks[0].message


class TestCheckSmtpConnectivity:
    def test_not_configured(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        with patch.dict("os.environ", {}, clear=True):
            _check_smtp_connectivity(paths, checks)
        assert checks[0].passed is True
        assert checks[0].status == CheckStatus.SKIP
        assert "not configured" in checks[0].message

    def test_smtp_reachable(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        mock_smtplib = MagicMock()
        with patch.dict("os.environ", {"SMTP_HOST": "localhost"}):
            with patch.dict("sys.modules", {"smtplib": mock_smtplib}):
                _check_smtp_connectivity(paths, checks)
        assert checks[0].passed is True


class TestCheckComposeServiceHealth:
    def test_all_healthy(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        ps_data = json.dumps({"Name": "web", "State": "running", "Health": "healthy"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=ps_data)
            _check_compose_service_health(paths, checks)
        assert checks[0].passed is True

    def test_unhealthy_service(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        ps_data = json.dumps({"Name": "web", "State": "running", "Health": "unhealthy"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=ps_data)
            _check_compose_service_health(paths, checks)
        assert checks[0].passed is False
        assert "unhealthy" in checks[0].message.lower()


class TestCheckPortConflicts:
    def test_no_conflicts(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        with patch("socket.socket") as mock_sock:
            mock_sock.return_value.__enter__.return_value.connect_ex.return_value = 1
            _check_port_conflicts(paths, checks)
        assert checks[0].passed is True

    def test_conflicts_detected(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        with patch("socket.socket") as mock_sock:
            mock_sock.return_value.__enter__.return_value.connect_ex.return_value = 0
            _check_port_conflicts(paths, checks)
        assert checks[0].passed is False
        assert "in use" in checks[0].message.lower()


class TestDoctorQuickFlag:
    def test_quick_skips_network_checks(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        report = run_doctor(paths=paths, quick=True)
        check_names = {c.name for c in report.checks}
        assert "port_available" not in check_names
        assert "docker_available" not in check_names
        assert "redis_connection" not in check_names
        assert "flask_liveness" not in check_names
        assert "package_version" in check_names
        assert "schema_version" in check_names


class TestDoctorNetworkFlag:
    def test_network_adds_connectivity_checks(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.doctor.runner._check_flask_liveness") as mock_liveness, \
             patch("ainews_cli.doctor.runner._check_readiness") as mock_ready, \
             patch("ainews_cli.doctor.runner._check_celery_workers") as mock_celery, \
             patch("ainews_cli.doctor.runner._check_provider_auth") as mock_provider, \
             patch("ainews_cli.doctor.runner._check_smtp_connectivity") as mock_smtp, \
             patch("ainews_cli.doctor.runner._check_compose_service_health") as mock_compose, \
             patch("ainews_cli.doctor.runner._check_port_conflicts") as mock_ports:
            report = run_doctor(paths=paths, network=True)
            mock_liveness.assert_called_once()
            mock_ready.assert_called_once()
            mock_celery.assert_called_once()
            mock_provider.assert_called_once()
            mock_smtp.assert_called_once()
            mock_compose.assert_called_once()
            mock_ports.assert_called_once()


class TestDoctorProductionFlag:
    def test_production_adds_strict_checks(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        env_path = paths.env_file.path
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("SECRET_KEY=test\n")
        env_path.chmod(0o600)
        try:
            report = run_doctor(paths=paths, production=True)
            check_names = {c.name for c in report.checks}
            assert "secret_permissions_strict" in check_names
        finally:
            env_path.chmod(0o644)


class TestDoctorJsonOutput:
    def test_json_serializable(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        report = run_doctor(paths=paths)
        d = report.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        deserialized = json.loads(serialized)
        assert deserialized["all_passed"] == report.all_passed
        # Verify status field is present
        assert "warn_count" in deserialized
        assert "skipped_count" in deserialized


class TestSourceConnectivitySchema:
    """Test source connectivity with different adapter type schemas."""

    def test_extract_primary_url_rss(self):
        from ainews_cli.doctor import _extract_primary_url
        source = {"type": "rss", "config": {"feed_url": "https://example.com/feed.xml"}}
        assert _extract_primary_url(source) == "https://example.com/feed.xml"

    def test_extract_primary_url_api(self):
        from ainews_cli.doctor import _extract_primary_url
        source = {"type": "api", "config": {"list_url": "https://example.com/api/items"}}
        assert _extract_primary_url(source) == "https://example.com/api/items"

    def test_extract_primary_url_web(self):
        from ainews_cli.doctor import _extract_primary_url
        source = {"type": "web", "config": {"listing_url": "https://example.com/news"}}
        assert _extract_primary_url(source) == "https://example.com/news"

    def test_extract_primary_url_unknown_type(self):
        from ainews_cli.doctor import _extract_primary_url
        source = {"type": "unknown", "config": {"some_key": "https://example.com"}}
        assert _extract_primary_url(source) is None

    def test_extract_primary_url_missing_config(self):
        from ainews_cli.doctor import _extract_primary_url
        source = {"type": "rss"}
        assert _extract_primary_url(source) is None


class TestDockerDnsNonInvasive:
    """Test that Docker DNS check doesn't create containers."""

    def test_docker_not_found_returns_skip(self):
        from ainews_cli.doctor import _check_docker_dns_resolution
        from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths
        from pathlib import Path as _Path

        tmp = _Path("/tmp/test_doctor_docker")
        paths = ResolvedPaths(
            app_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            config_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            data_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            state_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            backup_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            env_file=ResolvedPath(path=tmp / ".env", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            providers_file=ResolvedPath(path=tmp / "providers.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            pipeline_file=ResolvedPath(path=tmp / "pipeline.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            sources_file=ResolvedPath(path=tmp / "sources.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            topics_file=ResolvedPath(path=tmp / "topics.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            database_file=ResolvedPath(path=tmp / "db.sqlite", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            install_metadata_file=ResolvedPath(path=tmp / "meta.json", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            transaction_lock=ResolvedPath(path=tmp / "lock", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            transaction_staging=ResolvedPath(path=tmp / "staging", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
        )
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value=None):
            _check_docker_dns_resolution(paths, checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.SKIP
        assert "Docker not found" in checks[0].message

    def test_no_running_containers_returns_skip(self):
        from ainews_cli.doctor import _check_docker_dns_resolution
        from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths
        from pathlib import Path as _Path

        tmp = _Path("/tmp/test_doctor_docker2")
        paths = ResolvedPaths(
            app_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            config_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            data_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            state_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            backup_dir=ResolvedPath(path=tmp, provenance=PathProvenance.EXPLICIT, exists=True, is_writable=True),
            env_file=ResolvedPath(path=tmp / ".env", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            providers_file=ResolvedPath(path=tmp / "providers.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            pipeline_file=ResolvedPath(path=tmp / "pipeline.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            sources_file=ResolvedPath(path=tmp / "sources.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            topics_file=ResolvedPath(path=tmp / "topics.yaml", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            database_file=ResolvedPath(path=tmp / "db.sqlite", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            install_metadata_file=ResolvedPath(path=tmp / "meta.json", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            transaction_lock=ResolvedPath(path=tmp / "lock", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
            transaction_staging=ResolvedPath(path=tmp / "staging", provenance=PathProvenance.EXPLICIT, exists=False, is_writable=False),
        )
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("ainews_cli.doctor.checks.docker._docker_daemon_running", return_value=True), \
             patch("ainews_cli.doctor.checks.docker._get_running_containers", return_value=[]):
            _check_docker_dns_resolution(paths, checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.SKIP
        assert "No running containers" in checks[0].message


class TestDoctorReportStatusCounts:
    """Test DoctorReport status counting with all four statuses."""

    def test_mixed_statuses(self):
        from ainews_cli.doctor import DoctorReport, check_pass, check_warn, check_fail, check_skip

        report = DoctorReport(checks=[
            check_pass("a", "ok"),
            check_warn("b", "warned"),
            check_fail("c", "failed"),
            check_skip("d", "skipped"),
        ])
        assert report.all_passed is False  # FAIL present
        assert report.passed_count == 1
        assert report.warn_count == 1
        assert report.failed_count == 1
        assert report.skipped_count == 1

    def test_mixed_no_fail(self):
        from ainews_cli.doctor import DoctorReport, check_pass, check_warn, check_skip

        report = DoctorReport(checks=[
            check_pass("a", "ok"),
            check_warn("b", "warned"),
            check_skip("d", "skipped"),
        ])
        assert report.all_passed is True  # no FAIL

    def test_all_skip(self):
        from ainews_cli.doctor import DoctorReport, check_skip

        report = DoctorReport(checks=[
            check_skip("a", "skipped"),
            check_skip("b", "skipped"),
        ])
        assert report.all_passed is True
        assert report.skipped_count == 2
        assert report.passed_count == 0

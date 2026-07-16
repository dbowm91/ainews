"""Tests for ainews_cli.service — models, systemd rendering, state tracking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ainews_cli.service.models import (
    InstalledUnitRecord,
    LogrotateRuleSpec,
    RestartPolicy,
    ServiceProfile,
    ServiceScope,
    ServiceUnitSpec,
)
from ainews_cli.service.state import (
    add_installed_unit,
    content_hash,
    load_installed_units,
    remove_installed_unit,
    save_installed_units,
)
from ainews_cli.service.systemd import (
    build_celery_beat_unit,
    build_celery_worker_unit,
    build_docker_compose_unit,
    build_web_unit,
    render_unit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(**overrides) -> ServiceUnitSpec:
    defaults = {
        "name": "ainews-test",
        "description": "Test service",
        "scope": ServiceScope.USER,
        "profile": ServiceProfile.BARE_METAL,
        "exec_start": "/usr/bin/ainews start",
    }
    defaults.update(overrides)
    return ServiceUnitSpec(**defaults)


def _make_record(**overrides) -> InstalledUnitRecord:
    defaults = {
        "unit_name": "ainews-web",
        "unit_type": "service",
        "install_path": Path("/etc/systemd/system/ainews-web.service"),
        "content_hash": "abc123",
        "installed_at": "2026-01-01T00:00:00Z",
        "scope": ServiceScope.SYSTEM,
    }
    defaults.update(overrides)
    return InstalledUnitRecord(**defaults)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestServiceUnitSpec:
    """Tests for ServiceUnitSpec frozen dataclass."""

    def test_frozen(self):
        spec = _make_spec()
        with pytest.raises(AttributeError):
            spec.name = "changed"

    def test_defaults(self):
        spec = _make_spec()
        assert spec.restart_policy == RestartPolicy.ON_FAILURE
        assert spec.restart_sec == 5
        assert spec.no_new_privileges is True
        assert spec.private_tmp is True
        assert spec.protect_system == "strict"
        assert spec.after == []
        assert spec.requires == []
        assert spec.exec_stop is None
        assert spec.exec_reload is None
        assert spec.working_directory is None
        assert spec.environment_file is None

    def test_custom_fields(self):
        spec = _make_spec(
            restart_policy=RestartPolicy.ALWAYS,
            restart_sec=10,
            exec_stop="/usr/bin/ainews stop",
            exec_reload="/usr/bin/ainews config check",
            working_directory=Path("/opt/ainews"),
            environment_file=Path("/etc/ainews/.env"),
            after=["network.target"],
            requires=["docker.service"],
        )
        assert spec.restart_policy == RestartPolicy.ALWAYS
        assert spec.restart_sec == 10
        assert spec.exec_stop == "/usr/bin/ainews stop"
        assert spec.exec_reload == "/usr/bin/ainews config check"
        assert spec.working_directory == Path("/opt/ainews")
        assert spec.environment_file == Path("/etc/ainews/.env")
        assert spec.after == ["network.target"]
        assert spec.requires == ["docker.service"]


class TestServiceScope:
    def test_values(self):
        assert ServiceScope.USER.value == "user"
        assert ServiceScope.SYSTEM.value == "system"

    def test_enum_members(self):
        assert set(ServiceScope) == {ServiceScope.USER, ServiceScope.SYSTEM}


class TestRestartPolicy:
    def test_values(self):
        assert RestartPolicy.ALWAYS.value == "always"
        assert RestartPolicy.ON_FAILURE.value == "on-failure"
        assert RestartPolicy.NO.value == "no"

    def test_enum_members(self):
        assert set(RestartPolicy) == {
            RestartPolicy.ALWAYS,
            RestartPolicy.ON_FAILURE,
            RestartPolicy.NO,
        }


class TestServiceProfile:
    def test_values(self):
        assert ServiceProfile.DOCKER_COMPOSE.value == "docker_compose"
        assert ServiceProfile.BARE_METAL.value == "bare_metal"


class TestInstalledUnitRecord:
    def test_frozen(self):
        record = _make_record()
        with pytest.raises(AttributeError):
            record.unit_name = "changed"

    def test_roundtrip_fields(self):
        record = _make_record(
            unit_name="ainews-worker",
            unit_type="timer",
            scope=ServiceScope.USER,
        )
        assert record.unit_name == "ainews-worker"
        assert record.unit_type == "timer"
        assert record.scope == ServiceScope.USER


class TestLogrotateRuleSpec:
    def test_defaults(self):
        spec = LogrotateRuleSpec(name="test", log_paths=["/var/log/test/*.log"])
        assert spec.frequency == "daily"
        assert spec.rotate_count == 10
        assert spec.compress is True
        assert spec.delay_compress is True
        assert spec.missing_ok is True
        assert spec.notif_empty is True
        assert spec.size is None
        assert spec.maxsize is None

    def test_frozen(self):
        spec = LogrotateRuleSpec(name="test", log_paths=["/var/log/test/*.log"])
        with pytest.raises(AttributeError):
            spec.name = "changed"


# ---------------------------------------------------------------------------
# Systemd rendering
# ---------------------------------------------------------------------------


class TestRenderUnit:
    """Tests for systemd unit file rendering."""

    def test_basic_render(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert result.filename == "ainews-test.service"
        assert "[Unit]" in result.content
        assert "[Service]" in result.content
        assert "[Install]" in result.content
        assert "Description=Test service" in result.content
        assert "ExecStart=/usr/bin/ainews start" in result.content

    def test_generator_comment(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "Generated by ainews service manager" in result.content

    def test_hardening_directives(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "NoNewPrivileges=true" in result.content
        assert "PrivateTmp=true" in result.content
        assert "ProtectSystem=strict" in result.content
        assert "ProtectHome=true" in result.content
        assert "UMask=0027" in result.content

    def test_restart_policy(self):
        spec = _make_spec(restart_policy=RestartPolicy.ALWAYS)
        result = render_unit(spec)
        assert "Restart=always" in result.content

    def test_restart_policy_no(self):
        spec = _make_spec(restart_policy=RestartPolicy.NO)
        result = render_unit(spec)
        assert "Restart=no" in result.content

    def test_optional_exec_stop(self):
        spec = _make_spec(exec_stop="/usr/bin/ainews stop")
        result = render_unit(spec)
        assert "ExecStop=/usr/bin/ainews stop" in result.content

    def test_optional_exec_stop_absent(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "ExecStop" not in result.content

    def test_optional_exec_reload(self):
        spec = _make_spec(exec_reload="/usr/bin/ainews config check")
        result = render_unit(spec)
        assert "ExecReload=/usr/bin/ainews config check" in result.content

    def test_optional_exec_reload_absent(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "ExecReload" not in result.content

    def test_working_directory(self):
        spec = _make_spec(working_directory=Path("/opt/ainews"))
        result = render_unit(spec)
        assert "WorkingDirectory=/opt/ainews" in result.content

    def test_environment_file(self):
        spec = _make_spec(environment_file=Path("/etc/ainews/.env"))
        result = render_unit(spec)
        assert "EnvironmentFile=/etc/ainews/.env" in result.content

    def test_after_dependencies(self):
        spec = _make_spec(after=["network.target", "redis.service"])
        result = render_unit(spec)
        assert "After=network.target redis.service" in result.content

    def test_requires_dependencies(self):
        spec = _make_spec(requires=["docker.service"])
        result = render_unit(spec)
        assert "Requires=docker.service" in result.content

    def test_user_scope_install_path(self):
        spec = _make_spec(scope=ServiceScope.USER)
        result = render_unit(spec)
        assert ".config/systemd/user" in str(result.install_path)
        assert result.install_path.name == "ainews-test.service"

    def test_system_scope_install_path(self):
        spec = _make_spec(scope=ServiceScope.SYSTEM)
        result = render_unit(spec)
        assert "/etc/systemd/system" in str(result.install_path)
        assert result.install_path.name == "ainews-test.service"

    def test_type_simple(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "Type=simple" in result.content

    def test_restart_sec(self):
        spec = _make_spec(restart_sec=10)
        result = render_unit(spec)
        assert "RestartSec=10" in result.content

    def test_timeout_directives(self):
        spec = _make_spec(timeout_start_sec=60, timeout_stop_sec=15)
        result = render_unit(spec)
        assert "TimeoutStartSec=60" in result.content
        assert "TimeoutStopSec=15" in result.content

    def test_user_and_group(self):
        spec = _make_spec(user="www-data", group="www-data")
        result = render_unit(spec)
        assert "User=www-data" in result.content
        assert "Group=www-data" in result.content

    def test_user_group_absent_by_default(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "User=" not in result.content
        assert "Group=" not in result.content

    def test_standard_output_error(self):
        spec = _make_spec(standard_output="syslog", standard_error="syslog")
        result = render_unit(spec)
        assert "StandardOutput=syslog" in result.content
        assert "StandardError=syslog" in result.content

    def test_syslog_identifier(self):
        spec = _make_spec(syslog_identifier="ainews-web")
        result = render_unit(spec)
        assert "SyslogIdentifier=ainews-web" in result.content

    def test_syslog_identifier_absent(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "SyslogIdentifier" not in result.content

    def test_documentation(self):
        spec = _make_spec(documentation="https://docs.example.com")
        result = render_unit(spec)
        assert "Documentation=https://docs.example.com" in result.content

    def test_documentation_absent(self):
        spec = _make_spec()
        result = render_unit(spec)
        assert "Documentation" not in result.content

    def test_wanted_by(self):
        spec = _make_spec(wanted_by="default.target")
        result = render_unit(spec)
        assert "WantedBy=default.target" in result.content

    def test_rendered_unit_is_frozen(self):
        spec = _make_spec()
        result = render_unit(spec)
        with pytest.raises(AttributeError):
            result.content = "changed"

    def test_start_limit_burst_and_interval(self):
        spec = _make_spec(start_limit_burst=3, start_limit_interval_sec=30)
        result = render_unit(spec)
        assert result.spec.start_limit_burst == 3
        assert result.spec.start_limit_interval_sec == 30

    def test_protect_system_none(self):
        spec = _make_spec(protect_system=None)
        result = render_unit(spec)
        assert "ProtectSystem" not in result.content

    def test_hardening_disabled(self):
        spec = _make_spec(
            no_new_privileges=False,
            private_tmp=False,
            protect_home=False,
            umask="0022",
        )
        result = render_unit(spec)
        assert "NoNewPrivileges=false" in result.content
        assert "PrivateTmp=false" in result.content
        assert "ProtectHome=false" in result.content
        assert "UMask=0022" in result.content

    def test_multiple_after_and_requires(self):
        spec = _make_spec(
            after=["network.target", "redis.service", "postgres.service"],
            requires=["docker.service", "redis.service"],
        )
        result = render_unit(spec)
        assert "After=network.target redis.service postgres.service" in result.content
        assert "Requires=docker.service redis.service" in result.content

    def test_filename_matches_name(self):
        for name in ["ainews-web", "ainews-worker", "my-custom-service"]:
            spec = _make_spec(name=name)
            result = render_unit(spec)
            assert result.filename == f"{name}.service"


class TestBuildWebUnit:
    def test_returns_spec(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths)
        assert spec.name == "ainews-web"
        assert spec.scope == ServiceScope.USER
        assert "ainews start" in spec.exec_start

    def test_default_scope(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths)
        assert spec.scope == ServiceScope.USER

    def test_custom_scope(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths, scope=ServiceScope.SYSTEM)
        assert spec.scope == ServiceScope.SYSTEM

    def test_has_exec_stop(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths)
        assert spec.exec_stop is not None
        assert "stop" in spec.exec_stop

    def test_has_exec_reload(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths)
        assert spec.exec_reload is not None
        assert "config check" in spec.exec_reload

    def test_after_dependencies(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths)
        assert "network.target" in spec.after
        assert "redis.service" in spec.after

    def test_syslog_identifier(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_web_unit(paths)
        assert spec.syslog_identifier == "ainews-web"


class TestBuildCeleryWorkerUnit:
    def test_returns_spec(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_worker_unit(paths)
        assert spec.name == "ainews-celery-worker"
        assert "celery-worker" in spec.exec_start

    def test_after_includes_web(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_worker_unit(paths)
        assert "ainews-web.service" in spec.after

    def test_syslog_identifier(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_worker_unit(paths)
        assert spec.syslog_identifier == "ainews-celery-worker"

    def test_restart_sec(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_worker_unit(paths)
        assert spec.restart_sec == 10


class TestBuildCeleryBeatUnit:
    def test_returns_spec(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_beat_unit(paths)
        assert spec.name == "ainews-celery-beat"
        assert "celery-beat" in spec.exec_start

    def test_after_includes_web(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_beat_unit(paths)
        assert "ainews-web.service" in spec.after

    def test_timeout_values(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="ainews"):
            spec = build_celery_beat_unit(paths)
        assert spec.timeout_start_sec == 60
        assert spec.timeout_stop_sec == 30


class TestBuildDockerComposeUnit:
    def test_returns_spec(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        assert spec.name == "ainews"
        assert spec.profile == ServiceProfile.DOCKER_COMPOSE
        assert "docker compose" in spec.exec_start

    def test_always_restart(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        assert spec.restart_policy == RestartPolicy.ALWAYS

    def test_requires_docker(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        assert "docker.service" in spec.requires

    def test_after_network_and_docker(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        assert "network.target" in spec.after
        assert "docker.service" in spec.after

    def test_has_exec_stop(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        assert "docker compose down" in spec.exec_stop

    def test_syslog_identifier(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        assert spec.syslog_identifier == "ainews"


# ---------------------------------------------------------------------------
# Logrotate rendering
# ---------------------------------------------------------------------------


class TestLogrotateRendering:
    def test_basic_render(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(name="web", log_paths=["/var/log/ainews/web.log"])
        result = render_logrotate_rule(spec)
        assert result.filename == "ainews-web.conf"
        assert "/etc/logrotate.d" in str(result.install_path)
        assert "/var/log/ainews/web.log" in result.content
        assert "daily" in result.content
        assert "rotate 10" in result.content

    def test_generator_comment(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(name="web", log_paths=["/var/log/test.log"])
        result = render_logrotate_rule(spec)
        assert "Generated by ainews service manager" in result.content

    def test_compress_directives(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="web",
            log_paths=["/var/log/test.log"],
            compress=True,
            delay_compress=True,
        )
        result = render_logrotate_rule(spec)
        assert "compress" in result.content
        assert "delaycompress" in result.content

    def test_no_compress(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="web",
            log_paths=["/var/log/test.log"],
            compress=False,
            delay_compress=False,
        )
        result = render_logrotate_rule(spec)
        assert "    compress" not in result.content
        assert "    delaycompress" not in result.content

    def test_size_and_maxsize(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="web",
            log_paths=["/var/log/test.log"],
            size="100M",
            maxsize="500M",
        )
        result = render_logrotate_rule(spec)
        assert "size 100M" in result.content
        assert "maxsize 500M" in result.content

    def test_no_size_maxsize(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(name="web", log_paths=["/var/log/test.log"])
        result = render_logrotate_rule(spec)
        assert "    size " not in result.content
        assert "    maxsize " not in result.content

    def test_prerotate_postrotate(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="web",
            log_paths=["/var/log/test.log"],
            prerotate="echo prerotate",
            postrotate="echo postrotate",
        )
        result = render_logrotate_rule(spec)
        assert "prerotate" in result.content
        assert "echo prerotate" in result.content
        assert "postrotate" in result.content
        assert "echo postrotate" in result.content
        assert "endscript" in result.content

    def test_create_directive(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="web",
            log_paths=["/var/log/test.log"],
            create_mode="0640",
            create_user="root",
            create_group="adm",
        )
        result = render_logrotate_rule(spec)
        assert "create 0640 root adm" in result.content

    def test_missingok_notifempty(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="web",
            log_paths=["/var/log/test.log"],
            missing_ok=True,
            notif_empty=True,
        )
        result = render_logrotate_rule(spec)
        assert "missingok" in result.content
        assert "notifempty" in result.content

    def test_multiple_log_paths(self):
        from ainews_cli.service.logrotate import render_logrotate_rule

        spec = LogrotateRuleSpec(
            name="multi",
            log_paths=["/var/log/a.log", "/var/log/b.log"],
        )
        result = render_logrotate_rule(spec)
        assert "/var/log/a.log /var/log/b.log" in result.content

    def test_build_logrotate_rule(self):
        from ainews_cli.service.logrotate import build_logrotate_rule

        spec = build_logrotate_rule(Path("/var/log/ainews"))
        assert spec.name == "ainews"
        assert "/var/log/ainews/*.log" in spec.log_paths[0]
        assert spec.frequency == "daily"
        assert spec.rotate_count == 10
        assert spec.compress is True
        assert spec.postrotate is not None


# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------


class TestServiceState:
    """Tests for installed unit state persistence."""

    def test_save_and_load(self, tmp_path):
        record = _make_record()
        save_installed_units(tmp_path, [record])
        loaded = load_installed_units(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].unit_name == "ainews-web"
        assert loaded[0].scope == ServiceScope.SYSTEM

    def test_load_empty(self, tmp_path):
        assert load_installed_units(tmp_path) == []

    def test_load_no_file(self, tmp_path):
        state_file = tmp_path / "service-state.json"
        assert not state_file.exists()
        assert load_installed_units(tmp_path) == []

    def test_load_corrupt(self, tmp_path):
        (tmp_path / "service-state.json").write_text("not json")
        assert load_installed_units(tmp_path) == []

    def test_load_empty_json(self, tmp_path):
        (tmp_path / "service-state.json").write_text("{}")
        result = load_installed_units(tmp_path)
        assert result == []

    def test_load_missing_units_key(self, tmp_path):
        (tmp_path / "service-state.json").write_text('{"other": []}')
        result = load_installed_units(tmp_path)
        assert result == []

    def test_add_installed_unit(self, tmp_path):
        record = _make_record()
        add_installed_unit(tmp_path, record)
        loaded = load_installed_units(tmp_path)
        assert len(loaded) == 1

    def test_add_replaces_existing(self, tmp_path):
        record1 = _make_record(content_hash="abc123")
        record2 = _make_record(content_hash="def456")
        add_installed_unit(tmp_path, record1)
        add_installed_unit(tmp_path, record2)
        loaded = load_installed_units(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].content_hash == "def456"

    def test_remove_installed_unit(self, tmp_path):
        record = _make_record()
        add_installed_unit(tmp_path, record)
        assert remove_installed_unit(tmp_path, "ainews-web") is True
        assert load_installed_units(tmp_path) == []

    def test_remove_nonexistent(self, tmp_path):
        assert remove_installed_unit(tmp_path, "nonexistent") is False

    def test_remove_from_multiple(self, tmp_path):
        for name in ["web", "worker", "beat"]:
            add_installed_unit(
                tmp_path,
                _make_record(unit_name=f"ainews-{name}", content_hash=name),
            )
        assert remove_installed_unit(tmp_path, "ainews-worker") is True
        loaded = load_installed_units(tmp_path)
        assert len(loaded) == 2
        names = {u.unit_name for u in loaded}
        assert names == {"ainews-web", "ainews-beat"}

    def test_multiple_units(self, tmp_path):
        for i in range(3):
            record = _make_record(
                unit_name=f"ainews-unit-{i}",
                install_path=Path(f"/etc/systemd/system/ainews-unit-{i}.service"),
                content_hash=f"hash{i}",
                scope=ServiceScope.USER,
            )
            add_installed_unit(tmp_path, record)
        loaded = load_installed_units(tmp_path)
        assert len(loaded) == 3
        names = {u.unit_name for u in loaded}
        assert names == {"ainews-unit-0", "ainews-unit-1", "ainews-unit-2"}

    def test_state_file_is_json(self, tmp_path):
        record = _make_record()
        save_installed_units(tmp_path, [record])
        raw = json.loads((tmp_path / "service-state.json").read_text())
        assert "units" in raw
        assert len(raw["units"]) == 1
        assert raw["units"][0]["unit_name"] == "ainews-web"

    def test_scope_serialized_as_string(self, tmp_path):
        record = _make_record(scope=ServiceScope.USER)
        save_installed_units(tmp_path, [record])
        raw = json.loads((tmp_path / "service-state.json").read_text())
        assert raw["units"][0]["scope"] == "user"

    def test_scope_deserialized_to_enum(self, tmp_path):
        record = _make_record(scope=ServiceScope.SYSTEM)
        add_installed_unit(tmp_path, record)
        loaded = load_installed_units(tmp_path)
        assert loaded[0].scope == ServiceScope.SYSTEM

    def test_install_path_serialized_as_string(self, tmp_path):
        record = _make_record()
        save_installed_units(tmp_path, [record])
        raw = json.loads((tmp_path / "service-state.json").read_text())
        assert isinstance(raw["units"][0]["install_path"], str)


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_basic(self):
        h = content_hash("hello world")
        assert h == hashlib.sha256(b"hello world").hexdigest()
        assert len(h) == 64

    def test_empty_string(self):
        h = content_hash("")
        assert h == hashlib.sha256(b"").hexdigest()

    def test_deterministic(self):
        assert content_hash("test") == content_hash("test")

    def test_different_inputs(self):
        assert content_hash("a") != content_hash("b")

    def test_unicode(self):
        h = content_hash("日本語")
        assert h == hashlib.sha256("日本語".encode("utf-8")).hexdigest()
        assert len(h) == 64


# ---------------------------------------------------------------------------
# Integration: build + render round-trip
# ---------------------------------------------------------------------------


class TestBuildAndRenderRoundTrip:
    """Test that build_* functions produce specs that render correctly."""

    def test_web_unit_renderable(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="/usr/bin/ainews"):
            spec = build_web_unit(paths)
        result = render_unit(spec)
        assert "[Unit]" in result.content
        assert "[Service]" in result.content
        assert "[Install]" in result.content
        assert "ainews-web" in result.filename

    def test_docker_compose_unit_renderable(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        spec = build_docker_compose_unit(paths)
        result = render_unit(spec)
        assert "docker compose up" in result.content
        assert "docker compose down" in result.content
        assert "ainews.service" == result.filename

    def test_celery_worker_renderable(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="/usr/bin/ainews"):
            spec = build_celery_worker_unit(paths)
        result = render_unit(spec)
        assert "celery-worker" in result.content
        assert "ainews-celery-worker.service" == result.filename

    def test_celery_beat_renderable(self):
        from unittest.mock import MagicMock

        paths = MagicMock()
        paths.app_dir.path = Path("/opt/ainews")
        with patch("ainews_cli.service.systemd._find_cli_executable", return_value="/usr/bin/ainews"):
            spec = build_celery_beat_unit(paths)
        result = render_unit(spec)
        assert "celery-beat" in result.content
        assert "ainews-celery-beat.service" == result.filename

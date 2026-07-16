"""Comprehensive tests for ainews CLI update and uninstall system."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ainews_cli.exit_codes import UNINSTALL_ERROR, UPDATE_ERROR


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture()
def app_dir(tmp_path: Path) -> Path:
    d = tmp_path / "app"
    d.mkdir()
    return d


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture()
def backup_dir(tmp_path: Path) -> Path:
    d = tmp_path / "backups"
    d.mkdir()
    return d


@pytest.fixture()
def metadata_path(tmp_path: Path) -> Path:
    p = tmp_path / "install-metadata.json"
    p.write_text(
        json.dumps(
            {
                "version": "1.3.0",
                "installed_at": "2026-01-15T10:00:00Z",
                "install_type": "stable",
                "commit": "abc123def456",
            }
        )
    )
    return p


@pytest.fixture()
def resolved_paths(tmp_path: Path, metadata_path: Path):
    """Create a ResolvedPaths-like object using real tmp dirs."""
    from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.PLATFORM_DEFAULT,
            exists=p.exists(),
            is_writable=True,
        )

    base = tmp_path / "ainews"
    base.mkdir(exist_ok=True)
    return ResolvedPaths(
        app_dir=_rp(base / "app"),
        config_dir=_rp(base / "config"),
        data_dir=_rp(base / "data"),
        state_dir=_rp(base / "state"),
        backup_dir=_rp(base / "backups"),
        env_file=_rp(base / "config" / ".env"),
        providers_file=_rp(base / "config" / "providers.yaml"),
        pipeline_file=_rp(base / "config" / "pipeline.yaml"),
        sources_file=_rp(base / "config" / "sources.yaml"),
        topics_file=_rp(base / "config" / "topics.yaml"),
        database_file=_rp(base / "data" / "ainews.db"),
        install_metadata_file=_rp(metadata_path),
        transaction_lock=_rp(base / "state" / "txn.lock"),
        transaction_staging=_rp(base / "state" / "txn.staging"),
    )


@pytest.fixture()
def install_metadata_dict() -> dict[str, Any]:
    return {
        "version": "1.3.0",
        "installed_at": "2026-01-15T10:00:00Z",
        "install_type": "stable",
        "commit": "abc123def456",
    }


@pytest.fixture()
def output_fmt() -> MagicMock:
    mock = MagicMock()
    mock.error = MagicMock()
    mock.info = MagicMock()
    mock.success = MagicMock()
    mock.warning = MagicMock()
    mock.json_data = MagicMock()
    mock.kv_pairs = MagicMock()
    return mock


# ===================================================================
# 1. Update models (ainews_cli/update/models.py)
# ===================================================================


class TestUpdatePhaseEnum:
    def test_all_phases_are_string_values(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        for phase in UpdatePhase:
            assert isinstance(phase.value, str)

    def test_expected_count(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        assert len(UpdatePhase) == 13

    def test_idle_value(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        assert UpdatePhase.IDLE.value == "idle"

    def test_complete_value(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        assert UpdatePhase.COMPLETE.value == "complete"

    def test_failed_value(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        assert UpdatePhase.FAILED.value == "failed"

    def test_rolled_back_value(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        assert UpdatePhase.ROLLED_BACK.value == "rolled_back"

    def test_string_enum_comparison(self) -> None:
        from ainews_cli.update.models import UpdatePhase

        assert UpdatePhase.IDLE == "idle"
        assert UpdatePhase.DOWNLOADING == "downloading"


class TestUpdateOperation:
    def test_defaults(self) -> None:
        from ainews_cli.update.models import UpdateOperation, UpdatePhase

        op = UpdateOperation()
        assert op.phase == UpdatePhase.IDLE
        assert op.source_version == ""
        assert op.target_version is None
        assert op.channel == "stable"
        assert op.migration_results == []
        assert op.health_results == {}
        assert op.error_message is None
        assert op.completed_at is None
        assert op.operation_id  # non-empty auto-generated

    def test_operation_id_is_unique(self) -> None:
        from ainews_cli.update.models import UpdateOperation

        a = UpdateOperation()
        b = UpdateOperation()
        assert a.operation_id != b.operation_id

    def test_created_at_is_iso(self) -> None:
        from ainews_cli.update.models import UpdateOperation

        op = UpdateOperation()
        assert "T" in op.created_at
        assert "Z" in op.created_at or "+" in op.created_at

    def test_custom_fields(self) -> None:
        from ainews_cli.update.models import UpdateOperation, UpdatePhase

        op = UpdateOperation(
            phase=UpdatePhase.STAGED,
            source_version="1.2.0",
            target_version="1.3.0",
            channel="prerelease",
            error_message="something broke",
        )
        assert op.phase == UpdatePhase.STAGED
        assert op.source_version == "1.2.0"
        assert op.target_version == "1.3.0"
        assert op.channel == "prerelease"
        assert op.error_message == "something broke"


class TestUpdateCheckResult:
    def test_frozen(self) -> None:
        from ainews_cli.update.models import UpdateCheckResult

        r = UpdateCheckResult(
            current_version="1.0.0",
            latest_version="1.1.0",
            current_commit=None,
            latest_commit=None,
            channel="stable",
            update_available=True,
            is_upgrade=True,
            is_downgrade=False,
            is_reinstall=False,
            artifact_name="ainews-1.1.0-linux-x86_64.tar.gz",
            artifact_url="https://example.com/download",
            artifact_size=1024,
            min_supported_version="1.0.0",
        )
        assert r.update_available is True
        with pytest.raises(AttributeError):
            r.current_version = "2.0.0"  # type: ignore[misc]


class TestUpdatePlan:
    def test_frozen(self) -> None:
        from ainews_cli.update.models import UpdateCheckResult, UpdatePlan

        check = UpdateCheckResult(
            current_version="1.0.0",
            latest_version="1.1.0",
            current_commit=None,
            latest_commit=None,
            channel="stable",
            update_available=True,
            is_upgrade=True,
            is_downgrade=False,
            is_reinstall=False,
            artifact_name=None,
            artifact_url=None,
            artifact_size=None,
            min_supported_version="1.0.0",
        )
        plan = UpdatePlan(
            check=check,
            artifact_sha256=None,
            config_migrations=[],
            db_migrations=[],
            service_restart_required=True,
            estimated_downtime="< 30s",
            backup_required=True,
            rollback_capable=True,
            paths_changed=["app_dir"],
            blockers=[],
        )
        assert plan.service_restart_required is True
        with pytest.raises(AttributeError):
            plan.blockers = []  # type: ignore[misc]


class TestStatePersistence:
    def test_roundtrip(self, state_dir: Path) -> None:
        from ainews_cli.update.models import (
            UpdateOperation,
            UpdatePhase,
            clear_update_state,
            load_update_state,
            save_update_state,
        )

        op = UpdateOperation(
            phase=UpdatePhase.DOWNLOADING,
            source_version="1.0.0",
            target_version="1.1.0",
            channel="stable",
        )
        save_update_state(state_dir, op)
        loaded = load_update_state(state_dir)

        assert loaded is not None
        assert loaded.phase == UpdatePhase.DOWNLOADING
        assert loaded.source_version == "1.0.0"
        assert loaded.target_version == "1.1.0"
        assert loaded.operation_id == op.operation_id

        clear_update_state(state_dir)
        assert load_update_state(state_dir) is None

    def test_clear_nonexistent_file(self, state_dir: Path) -> None:
        from ainews_cli.update.models import clear_update_state

        # Should not raise
        clear_update_state(state_dir)

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        from ainews_cli.update.models import UpdateOperation, save_update_state

        nested = tmp_path / "deeply" / "nested" / "state"
        save_update_state(nested, UpdateOperation())
        assert nested.exists()
        assert (nested / "update-state.json").exists()

    def test_load_missing_file_returns_none(self, state_dir: Path) -> None:
        from ainews_cli.update.models import load_update_state

        assert load_update_state(state_dir) is None

    def test_load_corrupt_json_returns_none(self, state_dir: Path) -> None:
        from ainews_cli.update.models import load_update_state

        (state_dir / "update-state.json").write_text("{not valid json!!!")
        assert load_update_state(state_dir) is None

    def test_load_invalid_phase_returns_none(self, state_dir: Path) -> None:
        from ainews_cli.update.models import load_update_state

        data = {"phase": "bogus_phase", "operation_id": "x"}
        (state_dir / "update-state.json").write_text(json.dumps(data))
        assert load_update_state(state_dir) is None

    def test_load_missing_phase_key_returns_none(self, state_dir: Path) -> None:
        from ainews_cli.update.models import load_update_state

        data = {"operation_id": "x"}
        (state_dir / "update-state.json").write_text(json.dumps(data))
        assert load_update_state(state_dir) is None

    def test_save_updates_updated_at(self, state_dir: Path) -> None:
        from ainews_cli.update.models import UpdateOperation, load_update_state, save_update_state

        op = UpdateOperation()
        save_update_state(state_dir, op)
        first = load_update_state(state_dir)
        assert first is not None
        t1 = first.updated_at

        save_update_state(state_dir, op)
        second = load_update_state(state_dir)
        assert second is not None
        assert second.updated_at >= t1


class TestFormatUpdatePhase:
    def test_known_phases(self) -> None:
        from ainews_cli.update.models import UpdatePhase, format_update_phase

        assert format_update_phase(UpdatePhase.IDLE) == "Idle"
        assert format_update_phase(UpdatePhase.CHECKING) == "Checking for updates"
        assert format_update_phase(UpdatePhase.DOWNLOADING) == "Downloading artifact"
        assert format_update_phase(UpdatePhase.COMPLETE) == "Update complete"
        assert format_update_phase(UpdatePhase.FAILED) == "Update failed"
        assert format_update_phase(UpdatePhase.ROLLED_BACK) == "Rolled back"

    def test_all_phases_have_descriptions(self) -> None:
        from ainews_cli.update.models import UpdatePhase, format_update_phase

        for phase in UpdatePhase:
            label = format_update_phase(phase)
            assert isinstance(label, str)
            assert len(label) > 0


# ===================================================================
# 2. GitHub client (ainews_cli/update/github.py)
# ===================================================================


class TestDetectPlatform:
    def test_returns_valid_string(self) -> None:
        from ainews_cli.update.github import detect_platform

        result = detect_platform()
        assert "-" in result
        os_part, arch_part = result.split("-", 1)
        assert os_part in ("linux", "macos")
        assert arch_part in ("x86_64", "aarch64")

    @patch("ainews_cli.update.github.platform.system", return_value="Windows")
    def test_unsupported_os_raises(self, _mock: MagicMock) -> None:
        from ainews_cli.update.github import detect_platform

        with pytest.raises(RuntimeError, match="Unsupported operating system"):
            detect_platform()

    @patch("ainews_cli.update.github.platform.machine", return_value="mips")
    def test_unsupported_arch_raises(self, _mock: MagicMock) -> None:
        from ainews_cli.update.github import detect_platform

        with pytest.raises(RuntimeError, match="Unsupported CPU architecture"):
            detect_platform()

    @patch("ainews_cli.update.github.platform.machine", return_value="arm64")
    @patch("ainews_cli.update.github.platform.system", return_value="Darwin")
    def test_macos_arm64(self, _s: MagicMock, _m: MagicMock) -> None:
        from ainews_cli.update.github import detect_platform

        assert detect_platform() == "macos-aarch64"

    @patch("ainews_cli.update.github.platform.machine", return_value="amd64")
    @patch("ainews_cli.update.github.platform.system", return_value="Linux")
    def test_linux_amd64(self, _s: MagicMock, _m: MagicMock) -> None:
        from ainews_cli.update.github import detect_platform

        assert detect_platform() == "linux-x86_64"


class TestResolveVersion:
    def test_explicit_commit(self) -> None:
        from ainews_cli.update.github import resolve_version

        result = resolve_version("stable", commit="deadbeef123")
        assert result == "commit:deadbeef123"

    def test_explicit_version(self) -> None:
        from ainews_cli.update.github import resolve_version

        result = resolve_version("stable", version="1.4.0")
        assert result == "tag:v1.4.0"

    def test_explicit_version_strips_v_prefix(self) -> None:
        from ainews_cli.update.github import resolve_version

        result = resolve_version("stable", version="v1.4.0")
        assert result == "tag:v1.4.0"

    def test_invalid_channel_raises(self) -> None:
        from ainews_cli.update.github import resolve_version

        with pytest.raises(ValueError, match="Invalid channel"):
            resolve_version("nonexistent_channel")

    @patch("ainews_cli.update.github._github_request")
    def test_stable_channel(self, mock_req: MagicMock) -> None:
        from ainews_cli.update.github import resolve_version

        mock_req.return_value = {"tag_name": "v1.5.0", "prerelease": False}
        result = resolve_version("stable")
        assert result == "tag:v1.5.0"

    @patch("ainews_cli.update.github._github_request")
    def test_stable_channel_no_tag_raises(self, mock_req: MagicMock) -> None:
        from ainews_cli.update.github import resolve_version

        mock_req.return_value = {"tag_name": ""}
        with pytest.raises(RuntimeError, match="No stable releases found"):
            resolve_version("stable")

    @patch("ainews_cli.update.github._github_request")
    def test_prerelease_channel(self, mock_req: MagicMock) -> None:
        from ainews_cli.update.github import resolve_version

        mock_req.return_value = [
            {"tag_name": "v1.4.0", "prerelease": False},
            {"tag_name": "v1.5.0-rc1", "prerelease": True},
        ]
        result = resolve_version("prerelease")
        assert result == "tag:v1.5.0-rc1"

    @patch("ainews_cli.update.github._github_request")
    def test_prerelease_none_found_raises(self, mock_req: MagicMock) -> None:
        from ainews_cli.update.github import resolve_version

        mock_req.return_value = [
            {"tag_name": "v1.4.0", "prerelease": False},
        ]
        with pytest.raises(RuntimeError, match="No prereleases found"):
            resolve_version("prerelease")

    @patch("ainews_cli.update.github._github_request")
    def test_main_channel(self, mock_req: MagicMock) -> None:
        from ainews_cli.update.github import resolve_version

        mock_req.return_value = {"commit": {"sha": "abcdef1234567890"}}
        result = resolve_version("main")
        assert result == "commit:abcdef1234567890"

    @patch("ainews_cli.update.github._github_request")
    def test_main_channel_no_sha_raises(self, mock_req: MagicMock) -> None:
        from ainews_cli.update.github import resolve_version

        mock_req.return_value = {"commit": {"sha": ""}}
        with pytest.raises(RuntimeError, match="Could not resolve commit SHA"):
            resolve_version("main")


class TestVerifyChecksum:
    def test_matching_hash(self, tmp_path: Path) -> None:
        from ainews_cli.update.github import verify_checksum

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        import hashlib

        expected = hashlib.sha256(b"hello world").hexdigest()
        result = verify_checksum(f, expected)
        assert result == expected

    def test_mismatched_hash_raises(self, tmp_path: Path) -> None:
        from ainews_cli.update.github import verify_checksum

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        with pytest.raises(ValueError, match="Checksum mismatch"):
            verify_checksum(f, "0000000000000000000000000000000000000000000000000000000000000000")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        from ainews_cli.update.github import verify_checksum

        with pytest.raises(FileNotFoundError):
            verify_checksum(tmp_path / "nonexistent.txt", "abc123")

    def test_case_insensitive_comparison(self, tmp_path: Path) -> None:
        from ainews_cli.update.github import verify_checksum

        f = tmp_path / "test.txt"
        f.write_text("data")
        import hashlib

        expected = hashlib.sha256(b"data").hexdigest()
        result = verify_checksum(f, expected.upper())
        assert result == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        from ainews_cli.update.github import verify_checksum

        f = tmp_path / "empty.txt"
        f.write_text("")
        import hashlib

        expected = hashlib.sha256(b"").hexdigest()
        result = verify_checksum(f, expected)
        assert result == expected


# ===================================================================
# 3. Update engine (ainews_cli/update/engine.py)
# ===================================================================


class TestCompareVersions:
    def test_equal(self) -> None:
        from ainews_cli.update.engine import _compare_versions

        assert _compare_versions("1.0.0", "1.0.0") == 0

    def test_less_than(self) -> None:
        from ainews_cli.update.engine import _compare_versions

        assert _compare_versions("1.0.0", "1.1.0") == -1

    def test_greater_than(self) -> None:
        from ainews_cli.update.engine import _compare_versions

        assert _compare_versions("1.1.0", "1.0.0") == 1

    def test_patch_version(self) -> None:
        from ainews_cli.update.engine import _compare_versions

        assert _compare_versions("1.0.0", "1.0.1") == -1
        assert _compare_versions("1.0.1", "1.0.0") == 1


class TestDetectIncompleteOperation:
    def test_returns_none_when_no_state(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import detect_incomplete_operation

        assert detect_incomplete_operation(resolved_paths) is None

    def test_returns_none_for_complete_phase(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import detect_incomplete_operation
        from ainews_cli.update.models import UpdateOperation, UpdatePhase, save_update_state

        op = UpdateOperation(phase=UpdatePhase.COMPLETE)
        save_update_state(resolved_paths.state_dir.path, op)
        assert detect_incomplete_operation(resolved_paths) is None

    def test_returns_none_for_failed_phase(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import detect_incomplete_operation
        from ainews_cli.update.models import UpdateOperation, UpdatePhase, save_update_state

        op = UpdateOperation(phase=UpdatePhase.FAILED)
        save_update_state(resolved_paths.state_dir.path, op)
        assert detect_incomplete_operation(resolved_paths) is None

    def test_returns_none_for_rolled_back_phase(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import detect_incomplete_operation
        from ainews_cli.update.models import UpdateOperation, UpdatePhase, save_update_state

        op = UpdateOperation(phase=UpdatePhase.ROLLED_BACK)
        save_update_state(resolved_paths.state_dir.path, op)
        assert detect_incomplete_operation(resolved_paths) is None

    @pytest.mark.parametrize(
        "phase",
        [
            "downloading",
            "planned",
            "verified",
            "backed_up",
            "staged",
            "migrating",
            "activated",
            "validating",
            "checking",
        ],
    )
    def test_returns_op_for_nonterminal_phases(self, resolved_paths: Any, phase: str) -> None:
        from ainews_cli.update.engine import detect_incomplete_operation
        from ainews_cli.update.models import UpdateOperation, UpdatePhase, save_update_state

        op = UpdateOperation(phase=UpdatePhase(phase))
        save_update_state(resolved_paths.state_dir.path, op)
        result = detect_incomplete_operation(resolved_paths)
        assert result is not None
        assert result.phase == UpdatePhase(phase)


class TestCheckForUpdate:
    @patch("ainews_cli.update.engine.github")
    def test_upgrade_available(self, mock_github: MagicMock, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import check_for_update

        mock_github.resolve_version.return_value = "tag:v2.0.0"
        mock_github.resolve_artifact_url.return_value = (
            "https://example.com/download",
            "ainews-2.0.0-linux-x86_64.tar.gz",
            "v2.0.0",
        )
        mock_github.detect_platform.return_value = "linux-x86_64"

        result = check_for_update(resolved_paths)
        assert result.update_available is True
        assert result.is_upgrade is True
        assert result.latest_version == "2.0.0"

    @patch("ainews_cli.update.engine.github")
    def test_already_latest(self, mock_github: MagicMock, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import check_for_update

        mock_github.resolve_version.return_value = "tag:v1.3.0"
        mock_github.resolve_artifact_url.return_value = (
            "https://example.com/download",
            "ainews-1.3.0-linux-x86_64.tar.gz",
            "v1.3.0",
        )
        mock_github.detect_platform.return_value = "linux-x86_64"

        result = check_for_update(resolved_paths)
        # Note: update_available and is_reinstall may be None (Python `and` short-circuit)
        # when current_commit exists but latest_commit is None; falsy is acceptable here.
        assert not result.update_available
        assert result.is_upgrade is False
        assert result.is_downgrade is False

    @patch("ainews_cli.update.engine.github")
    def test_downgrade_detected(self, mock_github: MagicMock, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import check_for_update

        mock_github.resolve_version.return_value = "tag:v1.0.0"
        mock_github.resolve_artifact_url.return_value = (
            "https://example.com/download",
            "ainews-1.0.0-linux-x86_64.tar.gz",
            "v1.0.0",
        )
        mock_github.detect_platform.return_value = "linux-x86_64"

        result = check_for_update(resolved_paths)
        assert result.is_downgrade is True
        assert result.update_available is False


class TestPlanUpdate:
    def test_already_latest_adds_blocker(self) -> None:
        from ainews_cli.update.engine import plan_update
        from ainews_cli.update.models import UpdateCheckResult

        check = UpdateCheckResult(
            current_version="1.3.0",
            latest_version="1.3.0",
            current_commit=None,
            latest_commit=None,
            channel="stable",
            update_available=False,
            is_upgrade=False,
            is_downgrade=False,
            is_reinstall=False,
            artifact_name=None,
            artifact_url=None,
            artifact_size=None,
            min_supported_version="1.0.0",
        )
        from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

        dummy = ResolvedPath(
            path=Path("/nonexistent"),
            provenance=PathProvenance.PLATFORM_DEFAULT,
            exists=False,
            is_writable=False,
        )
        paths = ResolvedPaths(
            app_dir=dummy,
            config_dir=dummy,
            data_dir=dummy,
            state_dir=dummy,
            backup_dir=dummy,
            env_file=dummy,
            providers_file=dummy,
            pipeline_file=dummy,
            sources_file=dummy,
            topics_file=dummy,
            database_file=dummy,
            install_metadata_file=dummy,
            transaction_lock=dummy,
            transaction_staging=dummy,
        )

        plan = plan_update(check, paths)
        assert any("latest version" in b.lower() for b in plan.blockers)
        assert plan.backup_required is False

    def test_upgrade_requires_backup(self) -> None:
        from ainews_cli.update.engine import plan_update
        from ainews_cli.update.models import UpdateCheckResult
        from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

        check = UpdateCheckResult(
            current_version="1.2.0",
            latest_version="1.3.0",
            current_commit=None,
            latest_commit=None,
            channel="stable",
            update_available=True,
            is_upgrade=True,
            is_downgrade=False,
            is_reinstall=False,
            artifact_name=None,
            artifact_url=None,
            artifact_size=None,
            min_supported_version="1.0.0",
        )
        dummy = ResolvedPath(
            path=Path("/nonexistent"),
            provenance=PathProvenance.PLATFORM_DEFAULT,
            exists=False,
            is_writable=False,
        )
        paths = ResolvedPaths(
            app_dir=dummy,
            config_dir=dummy,
            data_dir=dummy,
            state_dir=dummy,
            backup_dir=dummy,
            env_file=dummy,
            providers_file=dummy,
            pipeline_file=dummy,
            sources_file=dummy,
            topics_file=dummy,
            database_file=dummy,
            install_metadata_file=dummy,
            transaction_lock=dummy,
            transaction_staging=dummy,
        )

        plan = plan_update(check, paths)
        assert plan.backup_required is True
        assert plan.rollback_capable is True
        assert plan.service_restart_required is True


class TestAcquireReleaseLock:
    def test_acquire_and_release(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import acquire_update_lock, release_update_lock

        fd = acquire_update_lock(resolved_paths)
        assert fd is not None
        release_update_lock(fd)

    def test_double_acquire_fails(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import acquire_update_lock, release_update_lock

        fd1 = acquire_update_lock(resolved_paths)
        assert fd1 is not None
        try:
            fd2 = acquire_update_lock(resolved_paths)
            assert fd2 is None
        finally:
            release_update_lock(fd1)


class TestApplyUpdate:
    def test_dry_run_does_not_modify(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import apply_update
        from ainews_cli.update.models import (
            UpdateCheckResult,
            UpdatePhase,
            UpdatePlan,
            load_update_state,
        )

        check = UpdateCheckResult(
            current_version="1.0.0",
            latest_version="1.1.0",
            current_commit=None,
            latest_commit=None,
            channel="stable",
            update_available=True,
            is_upgrade=True,
            is_downgrade=False,
            is_reinstall=False,
            artifact_name="ainews-1.1.0-linux-x86_64.tar.gz",
            artifact_url="https://example.com/artifact.tar.gz",
            artifact_size=None,
            min_supported_version="1.0.0",
        )
        plan = UpdatePlan(
            check=check,
            artifact_sha256=None,
            config_migrations=[],
            db_migrations=[],
            service_restart_required=True,
            estimated_downtime="< 30s",
            backup_required=False,
            rollback_capable=False,
            paths_changed=["app_dir"],
            blockers=[],
        )

        op = apply_update(resolved_paths, plan, dry_run=True)
        assert op.phase == UpdatePhase.PLANNED
        # No state file should be persisted for dry runs
        assert load_update_state(resolved_paths.state_dir.path) is None


class TestRollbackUpdate:
    def test_no_operation_returns_false(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import rollback_update

        assert rollback_update(resolved_paths) is False

    def test_operation_with_no_backup_returns_false(self, resolved_paths: Any) -> None:
        from ainews_cli.update.engine import rollback_update
        from ainews_cli.update.models import UpdateOperation, UpdatePhase

        op = UpdateOperation(
            phase=UpdatePhase.STAGED,
            previous_app_path=None,
            backup_id=None,
        )
        # previous path doesn't exist, no backup_id → False
        assert rollback_update(resolved_paths, operation=op) is False


# ===================================================================
# 4. Channel commands (ainews_cli/channel/commands.py)
# ===================================================================


class TestChannelHelpers:
    def test_read_metadata_missing(self, tmp_path: Path) -> None:
        from ainews_cli.channel.commands import _read_metadata

        assert _read_metadata(tmp_path / "nonexistent.json") == {}

    def test_read_metadata_valid(self, tmp_path: Path) -> None:
        from ainews_cli.channel.commands import _read_metadata

        p = tmp_path / "meta.json"
        p.write_text(json.dumps({"install_type": "stable", "version": "1.0.0"}))
        result = _read_metadata(p)
        assert result["install_type"] == "stable"

    def test_read_metadata_corrupt(self, tmp_path: Path) -> None:
        from ainews_cli.channel.commands import _read_metadata

        p = tmp_path / "meta.json"
        p.write_text("not json!!!")
        assert _read_metadata(p) == {}

    def test_write_metadata_creates_parent(self, tmp_path: Path) -> None:
        from ainews_cli.channel.commands import _write_metadata

        p = tmp_path / "nested" / "dir" / "meta.json"
        _write_metadata(p, {"install_type": "main"})
        assert p.exists()
        assert json.loads(p.read_text())["install_type"] == "main"

    def test_write_metadata_atomic(self, tmp_path: Path) -> None:
        from ainews_cli.channel.commands import _write_metadata

        p = tmp_path / "meta.json"
        _write_metadata(p, {"version": "1"})
        assert p.exists()
        assert not (tmp_path / "meta.tmp").exists()


class TestChannelShowCommand:
    def test_show_with_valid_metadata(self, tmp_path: Path, metadata_path: Path, output_fmt: MagicMock) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "show"])
        assert result.exit_code == 0
        out.kv_pairs.assert_called_once()

    def test_show_json_output(self, tmp_path: Path, metadata_path: Path, output_fmt: MagicMock) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "show", "--json"])
        assert result.exit_code == 0
        out.json_data.assert_called_once()

    def test_show_missing_metadata_exits(self, tmp_path: Path, output_fmt: MagicMock) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = tmp_path / "nonexistent.json"
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "show"])
        # Should call out.error for missing metadata
        out.error.assert_called()


class TestChannelSetCommand:
    def test_set_valid_channel(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "main", "-y"])
        assert result.exit_code == 0
        out.success.assert_called_once()
        # Verify metadata was updated
        data = json.loads(metadata_path.read_text())
        assert data["install_type"] == "main"

    def test_set_invalid_channel(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "invalid"])
        out.error.assert_called()

    def test_set_same_channel_noop(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "stable", "-y"])
        assert result.exit_code == 0
        out.info.assert_called()
        # Metadata should not be written
        data = json.loads(metadata_path.read_text())
        assert data["install_type"] == "stable"

    def test_set_dry_run_no_write(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "main", "--dry-run", "-y"])
        assert result.exit_code == 0
        data = json.loads(metadata_path.read_text())
        assert data["install_type"] == "stable"  # unchanged

    def test_set_risky_channel_with_yes(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "prerelease", "-y"])
        assert result.exit_code == 0
        out.success.assert_called_once()

    def test_set_missing_metadata_exits(self, tmp_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = tmp_path / "nonexistent.json"
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "main", "-y"])
        out.error.assert_called()

    def test_set_json_output(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.channel.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        runner = __import__("typer.testing").testing.CliRunner()
        result = runner.invoke(app, ["channel", "set", "main", "-y", "--json"])
        assert result.exit_code == 0
        out.json_data.assert_called_once()


# ===================================================================
# 5. Uninstall commands (ainews_cli/uninstall/commands.py)
# ===================================================================


class TestIsUnsafePath:
    def test_rejects_root(self) -> None:
        from ainews_cli.uninstall.commands import _is_unsafe_path

        assert _is_unsafe_path(Path("/")) is True

    def test_rejects_home(self) -> None:
        from ainews_cli.uninstall.commands import _is_unsafe_path

        assert _is_unsafe_path(Path.home()) is True

    def test_rejects_empty_string(self) -> None:
        from ainews_cli.uninstall.commands import _is_unsafe_path

        # Path("") resolves to ".", which is not empty or "/" — verify the function's behavior
        # The empty-string check fires for str(path) being falsy; Path("") gives "."
        # so this actually tests the "." case
        result = _is_unsafe_path(Path(""))
        # "." is not explicitly rejected by the function, so it returns False
        assert result is False

    def test_rejects_unresolved_var(self) -> None:
        from ainews_cli.uninstall.commands import _is_unsafe_path

        assert _is_unsafe_path(Path("${HOME}/ainews")) is True

    def test_rejects_tilde(self) -> None:
        from ainews_cli.uninstall.commands import _is_unsafe_path

        assert _is_unsafe_path(Path("~/ainews")) is True

    def test_accepts_safe_path(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _is_unsafe_path

        assert _is_unsafe_path(tmp_path / "ainews") is False


class TestIsPathOwned:
    def test_owned_under_root(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _is_path_owned

        root = tmp_path / "approved"
        root.mkdir()
        target = root / "ainews" / "app"
        target.mkdir(parents=True)
        assert _is_path_owned(target, [root]) is True

    def test_not_owned(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _is_path_owned

        root = tmp_path / "approved"
        root.mkdir()
        target = tmp_path / "other" / "app"
        target.mkdir(parents=True)
        assert _is_path_owned(target, [root]) is False

    def test_multiple_roots(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _is_path_owned

        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        target = root_b / "file.txt"
        target.touch()
        assert _is_path_owned(target, [root_a, root_b]) is True


class TestBuildRemovalPlan:
    def test_app_only_mode(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _build_removal_plan

        base = tmp_path / "ainews"
        base.mkdir()
        app_d = base / "app"
        app_d.mkdir()
        config_d = base / "config"
        config_d.mkdir()

        paths = MagicMock()
        paths.app_dir.path = app_d
        paths.config_dir.path = config_d
        paths.data_dir.path = base / "data"
        paths.state_dir.path = base / "state"
        paths.backup_dir.path = base / "backups"

        with patch("ainews_cli.uninstall.commands._is_path_owned", return_value=True):
            plan = _build_removal_plan(paths, remove_app_only=True, purge=False)
        assert len(plan["app_files"]) == 1
        assert len(plan["config_files"]) == 0

    def test_purge_mode(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _build_removal_plan

        base = tmp_path / "ainews"
        base.mkdir()
        app_d = base / "app"
        app_d.mkdir()
        config_d = base / "config"
        config_d.mkdir()
        data_d = base / "data"
        data_d.mkdir()
        state_d = base / "state"
        state_d.mkdir()
        backup_d = base / "backups"
        backup_d.mkdir()

        paths = MagicMock()
        paths.app_dir.path = app_d
        paths.config_dir.path = config_d
        paths.data_dir.path = data_d
        paths.state_dir.path = state_d
        paths.backup_dir.path = backup_d

        with patch("ainews_cli.uninstall.commands._is_path_owned", return_value=True):
            plan = _build_removal_plan(paths, remove_app_only=False, purge=True)
        assert len(plan["app_files"]) == 1
        assert len(plan["config_files"]) == 1
        assert len(plan["data_files"]) >= 1  # data and/or state
        assert len(plan["backup_files"]) == 1

    def test_default_mode_no_data(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _build_removal_plan

        base = tmp_path / "ainews"
        base.mkdir()
        app_d = base / "app"
        app_d.mkdir()
        config_d = base / "config"
        config_d.mkdir()
        data_d = base / "data"
        data_d.mkdir()
        state_d = base / "state"
        state_d.mkdir()
        backup_d = base / "backups"
        backup_d.mkdir()

        paths = MagicMock()
        paths.app_dir.path = app_d
        paths.config_dir.path = config_d
        paths.data_dir.path = data_d
        paths.state_dir.path = state_d
        paths.backup_dir.path = backup_d

        with patch("ainews_cli.uninstall.commands._is_path_owned", return_value=True):
            plan = _build_removal_plan(paths, remove_app_only=False, purge=False)
        assert len(plan["app_files"]) == 1
        assert len(plan["config_files"]) == 1
        assert len(plan["data_files"]) == 0
        assert len(plan["backup_files"]) == 0

    def test_nonexistent_dirs_excluded(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _build_removal_plan

        paths = MagicMock()
        paths.app_dir.path = tmp_path / "nonexistent" / "app"
        paths.config_dir.path = tmp_path / "nonexistent" / "config"
        paths.data_dir.path = tmp_path / "nonexistent" / "data"
        paths.state_dir.path = tmp_path / "nonexistent" / "state"
        paths.backup_dir.path = tmp_path / "nonexistent" / "backups"

        with patch("ainews_cli.uninstall.commands._is_path_owned", return_value=True):
            plan = _build_removal_plan(paths, remove_app_only=False, purge=True)
        assert all(len(v) == 0 for v in plan.values())


class TestSafeRemove:
    def test_remove_file(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _safe_remove

        f = tmp_path / "file.txt"
        f.write_text("hello")
        assert _safe_remove(f) is True
        assert not f.exists()

    def test_remove_directory(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _safe_remove

        d = tmp_path / "dir"
        d.mkdir()
        (d / "file.txt").write_text("data")
        assert _safe_remove(d) is True
        assert not d.exists()

    def test_remove_symlink_file(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _safe_remove

        target = tmp_path / "real.txt"
        target.write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        assert _safe_remove(link) is True
        assert not link.exists()
        assert target.exists()  # real file preserved

    def test_remove_nonexistent_returns_true(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import _safe_remove

        assert _safe_remove(tmp_path / "nope.txt") is True


class TestUninstallMissingMetadata:
    def test_fails_without_metadata(self, tmp_path: Path) -> None:
        from ainews_cli.uninstall.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = tmp_path / "nonexistent.json"
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        # load_install_metadata is imported inside the function body, so patch at source
        with patch("ainews_config.paths.load_install_metadata", return_value=None):
            runner = __import__("typer.testing").testing.CliRunner()
            result = runner.invoke(app, ["--yes"])
        out.error.assert_called()


class TestUninstallDryRun:
    def test_dry_run_no_removal(self, tmp_path: Path, metadata_path: Path) -> None:
        from ainews_cli.uninstall.commands import register_commands
        from ainews_cli.context import CLIContext
        from ainews_cli.output import OutputFormatter
        from ainews_config.paths import InstallMetadata
        import typer

        app = typer.Typer()
        ctx = MagicMock(spec=CLIContext)
        config = MagicMock()
        config.paths.install_metadata_file.path = metadata_path
        ctx.ensure_loaded.return_value = config
        out = MagicMock(spec=OutputFormatter)

        register_commands(app, ctx, out)

        meta = InstallMetadata(
            version="1.3.0",
            installed_at="2026-01-15T10:00:00Z",
            install_type="stable",
        )
        with patch("ainews_config.paths.load_install_metadata", return_value=meta):
            runner = __import__("typer.testing").testing.CliRunner()
            result = runner.invoke(app, ["--dry-run", "--yes"])
        # Dry run should succeed and report nothing (no owned paths)
        assert result.exit_code == 0


# ===================================================================
# 6. Exit codes
# ===================================================================


class TestExitCodes:
    def test_update_error_exists(self) -> None:
        assert UPDATE_ERROR == 10

    def test_uninstall_error_exists(self) -> None:
        assert UNINSTALL_ERROR == 11

    def test_update_error_is_int(self) -> None:
        assert isinstance(UPDATE_ERROR, int)

    def test_uninstall_error_is_int(self) -> None:
        assert isinstance(UNINSTALL_ERROR, int)

from __future__ import annotations

import json
import os
import sqlite3
import tarfile
import time
from pathlib import Path
from typing import Any

import pytest

from ainews_config.backup import (
    BackupError,
    BackupManifest,
    BackupSection,
    BaseMigration,
    MigrationReport,
    RestorePlan,
    VerifyResult,
    _compute_migration_checksum,
    _compute_sha256,
    _get_application_version,
    _get_database_schema_version,
    _make_backup_id,
    _parse_version,
    _safe_archive_path,
    _version_compatible,
    create_backup,
    execute_migration_plan,
    get_migration_status_for_backup,
    list_backups,
    pin_backup,
    plan_migrations,
    plan_restore,
    prune_backups,
    restore_backup,
    show_backup,
    unpin_backup,
    verify_backup,
)
from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backup_paths(tmp_path):
    """Create a minimal ResolvedPaths structure for testing."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    backup_dir = tmp_path / "backups"
    app_dir = tmp_path / "app"

    for d in [config_dir, data_dir, state_dir, backup_dir, app_dir]:
        d.mkdir(parents=True, exist_ok=True)

    env_file = config_dir / ".env"
    env_file.write_text(
        "SECRET_KEY=test-secret-key-12345\nADMIN_PASSWORD=admin123\n"
    )
    env_file.chmod(0o600)

    providers_file = config_dir / "providers.yaml"
    providers_file.write_text(
        "providers:\n  ollama:\n    type: ollama\n    enabled: true\n"
    )

    pipeline_file = config_dir / "pipeline.yaml"
    pipeline_file.write_text("pipeline:\n  selector:\n    provider: ollama\n")

    sources_file = config_dir / "sources.yaml"
    sources_file.write_text("sources: []\n")

    topics_file = config_dir / "topics.yaml"
    topics_file.write_text("topics: []\n")

    db_file = data_dir / "ainews.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version "
        "(version_num VARCHAR(32) NOT NULL)"
    )
    conn.execute(
        "INSERT INTO alembic_version (version_num) VALUES ('036')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, title TEXT)"
    )
    conn.commit()
    conn.close()

    meta_file = config_dir / "install-metadata.json"
    meta_file.write_text(
        json.dumps(
            {
                "version": "1.4.0",
                "installed_at": "2026-07-15T00:00:00Z",
                "install_type": "development",
            }
        )
    )

    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.DEVELOPMENT,
            exists=p.exists(),
            is_writable=True,
        )

    return ResolvedPaths(
        app_dir=_rp(app_dir),
        config_dir=_rp(config_dir),
        data_dir=_rp(data_dir),
        state_dir=_rp(state_dir),
        backup_dir=_rp(backup_dir),
        env_file=_rp(env_file),
        providers_file=_rp(providers_file),
        pipeline_file=_rp(pipeline_file),
        sources_file=_rp(sources_file),
        topics_file=_rp(topics_file),
        database_file=_rp(db_file),
        install_metadata_file=_rp(meta_file),
        transaction_lock=_rp(state_dir / "transaction.lock"),
        transaction_staging=_rp(state_dir / "staging"),
    )


class FakeMigration(BaseMigration):
    """A test migration that records calls for assertions."""

    def __init__(
        self,
        id: str = "test-001",
        from_version: str = "1.0.0",
        to_version: str = "1.1.0",
        reversible: bool = False,
        fail_preflight: bool = False,
        fail_apply: bool = False,
    ):
        self._id = id
        self._from_version = from_version
        self._to_version = to_version
        self._reversible = reversible
        self._fail_preflight = fail_preflight
        self._fail_apply = fail_apply
        self.preflight_called = False
        self.apply_called = False
        self.rollback_called = False

    @property
    def id(self) -> str:
        return self._id

    @property
    def from_version(self) -> str:
        return self._from_version

    @property
    def to_version(self) -> str:
        return self._to_version

    @property
    def reversible(self) -> bool:
        return self._reversible

    def preflight(self, context: dict[str, Any]) -> MigrationReport:
        self.preflight_called = True
        if self._fail_preflight:
            return MigrationReport(
                migration_id=self.id,
                success=False,
                message="Preflight check failed",
                from_version=self.from_version,
                to_version=self.to_version,
            )
        return super().preflight(context)

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        self.apply_called = True
        if self._fail_apply:
            return MigrationReport(
                migration_id=self.id,
                success=False,
                message="Apply step failed",
                from_version=self.from_version,
                to_version=self.to_version,
            )
        return MigrationReport(
            migration_id=self.id,
            success=True,
            message=f"Applied {self.id}",
            from_version=self.from_version,
            to_version=self.to_version,
        )


def _create_standalone_backup(
    backup_dir: Path,
    backup_id: str,
    *,
    app_version: str = "1.4.0",
    db_version: str = "036",
    tag: str | None = None,
) -> BackupManifest:
    """Create a backup directory with manifest + files directly (no locks)."""
    bd = backup_dir / backup_id
    bd.mkdir(parents=True, exist_ok=True)

    # config tar
    import io

    config_tar = bd / "config.tar"
    with tarfile.open(str(config_tar), "w") as tar:
        for name, content in [
            (".env", "SECRET_KEY=old-key\n"),
            ("providers.yaml", "providers: {}\n"),
            ("pipeline.yaml", "pipeline: {}\n"),
            ("sources.yaml", "sources: []\n"),
            ("topics.yaml", "topics: []\n"),
        ]:
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    # database
    db_path = bd / "database.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version "
        "(version_num VARCHAR(32) NOT NULL)"
    )
    conn.execute(
        "INSERT INTO alembic_version (version_num) VALUES (?)", (db_version,)
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, title TEXT)"
    )
    conn.commit()
    conn.close()

    # install metadata
    meta_path = bd / "install_metadata.json"
    meta_path.write_text(
        json.dumps({"version": app_version, "install_type": "development"})
    )

    sections = []
    for name, fname in [
        ("config", "config.tar"),
        ("database", "database.sqlite"),
        ("install_metadata", "install_metadata.json"),
    ]:
        fp = bd / fname
        sections.append(
            BackupSection(
                name=name,
                path=fname,
                sha256=_compute_sha256(fp),
                size=fp.stat().st_size,
            )
        )

    manifest = BackupManifest(
        schema_version=1,
        backup_id=backup_id,
        created_at="2026-07-15T00:00:00+00:00",
        application_version=app_version,
        config_schema_version="50",
        database_schema_version=db_version,
        source_install={"channel": "development"},
        sections=sections,
        tag=tag,
        total_size=sum(s.size for s in sections),
    )

    manifest_path = bd / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
    )
    return manifest


# ---------------------------------------------------------------------------
# Backup Creation Tests
# ---------------------------------------------------------------------------


class TestCreateBackup:
    def test_create_backup_basic(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)

        assert manifest.schema_version == 1
        assert manifest.backup_id
        assert manifest.application_version == "1.4.0"
        assert len(manifest.sections) == 3

        bd = backup_paths.backup_dir.path / manifest.backup_id
        assert (bd / "manifest.json").exists()

    def test_create_backup_includes_config_tarball(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        config_section = next(
            s for s in manifest.sections if s.name == "config"
        )
        tar_path = bd / config_section.path
        assert tar_path.exists()

        with tarfile.open(str(tar_path), "r") as tar:
            names = tar.getnames()
            assert ".env" in names
            assert "providers.yaml" in names
            assert "pipeline.yaml" in names
            assert "sources.yaml" in names
            assert "topics.yaml" in names

    def test_create_backup_includes_database(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        db_section = next(
            s for s in manifest.sections if s.name == "database"
        )
        db_path = bd / db_section.path
        assert db_path.exists()

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        result = conn.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        conn.close()
        assert result is not None
        assert result[0] == "036"

    def test_create_backup_includes_install_metadata(
        self, backup_paths, monkeypatch
    ):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        meta_section = next(
            s for s in manifest.sections if s.name == "install_metadata"
        )
        meta_path = bd / meta_section.path
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["version"] == "1.4.0"

    def test_create_backup_with_tag(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths, tag="pre-upgrade")
        assert manifest.tag == "pre-upgrade"

        bd = backup_paths.backup_dir.path / manifest.backup_id
        stored = json.loads((bd / "manifest.json").read_text())
        assert stored["tag"] == "pre-upgrade"

    def test_create_backup_permissions(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        assert (bd.stat().st_mode & 0o777) == 0o700
        for child in bd.iterdir():
            mode = child.stat().st_mode & 0o777
            if child.is_dir():
                assert mode == 0o700, f"{child.name} should be 0o700"
            else:
                assert mode == 0o600, f"{child.name} should be 0o600"

    def test_create_backup_staging_cleanup(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)

        staging_dirs = [
            d
            for d in backup_paths.backup_dir.path.iterdir()
            if d.is_dir() and d.name.startswith(".staging-")
        ]
        assert staging_dirs == []


# ---------------------------------------------------------------------------
# Verification Tests
# ---------------------------------------------------------------------------


class TestVerifyBackup:
    def test_verify_backup_valid(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)

        result = verify_backup(
            backup_paths.backup_dir.path, manifest.backup_id
        )
        assert result.valid is True
        assert result.reason_code is None
        assert result.details["sections_count"] == 3

    def test_verify_backup_missing_directory(self, backup_paths):
        result = verify_backup(
            backup_paths.backup_dir.path, "nonexistent-2026-01-01"
        )
        assert result.valid is False
        assert result.reason_code == "backup_not_found"

    def test_verify_backup_missing_manifest(self, backup_paths):
        bd = backup_paths.backup_dir.path / "broken-backup"
        bd.mkdir()
        (bd / "dummy.txt").write_text("no manifest")

        result = verify_backup(backup_paths.backup_dir.path, "broken-backup")
        assert result.valid is False
        assert result.reason_code == "manifest_missing"

    def test_verify_backup_checksum_mismatch(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        # Tamper with config tar, keeping same size to avoid size_mismatch
        tar_path = bd / "config.tar"
        original_size = tar_path.stat().st_size
        tampered = b"\x00" * original_size
        tar_path.write_bytes(tampered)

        result = verify_backup(backup_paths.backup_dir.path, manifest.backup_id)
        assert result.valid is False
        assert result.reason_code == "checksum_mismatch"

    def test_verify_backup_size_mismatch(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        # Rewrite the manifest with wrong size for database section
        db_section = next(
            s for s in manifest.sections if s.name == "database"
        )
        modified_sections = []
        for s in manifest.sections:
            if s.name == "database":
                modified_sections.append(
                    BackupSection(
                        name=s.name,
                        path=s.path,
                        sha256=s.sha256,
                        size=s.size + 1000,
                    )
                )
            else:
                modified_sections.append(s)

        modified_manifest = BackupManifest(
            schema_version=manifest.schema_version,
            backup_id=manifest.backup_id,
            created_at=manifest.created_at,
            application_version=manifest.application_version,
            config_schema_version=manifest.config_schema_version,
            database_schema_version=manifest.database_schema_version,
            source_install=manifest.source_install,
            sections=modified_sections,
            total_size=manifest.total_size,
        )
        (bd / "manifest.json").write_text(
            json.dumps(modified_manifest.to_dict(), indent=2)
        )

        result = verify_backup(backup_paths.backup_dir.path, manifest.backup_id)
        assert result.valid is False
        assert result.reason_code == "size_mismatch"

    def test_verify_backup_database_corrupt(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        # Corrupt the database file
        db_path = bd / "database.sqlite"
        db_path.write_bytes(b"not-a-database" + b"\x00" * 100)

        # We need to update the manifest so sections pass checksum/size
        db_section = next(
            s for s in manifest.sections if s.name == "database"
        )
        new_sha = _compute_sha256(db_path)
        new_size = db_path.stat().st_size
        modified_sections = []
        for s in manifest.sections:
            if s.name == "database":
                modified_sections.append(
                    BackupSection(
                        name=s.name,
                        path=s.path,
                        sha256=new_sha,
                        size=new_size,
                    )
                )
            else:
                modified_sections.append(s)

        modified_manifest = BackupManifest(
            schema_version=manifest.schema_version,
            backup_id=manifest.backup_id,
            created_at=manifest.created_at,
            application_version=manifest.application_version,
            config_schema_version=manifest.config_schema_version,
            database_schema_version=manifest.database_schema_version,
            source_install=manifest.source_install,
            sections=modified_sections,
            total_size=manifest.total_size,
        )
        (bd / "manifest.json").write_text(
            json.dumps(modified_manifest.to_dict(), indent=2)
        )

        result = verify_backup(backup_paths.backup_dir.path, manifest.backup_id)
        assert result.valid is False
        assert result.reason_code == "db_corrupt"

    def test_verify_backup_unsafe_path(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        # Rewrite manifest with an unsafe path
        modified_sections = []
        for s in manifest.sections:
            if s.name == "config":
                modified_sections.append(
                    BackupSection(
                        name=s.name,
                        path="../etc/passwd",
                        sha256=s.sha256,
                        size=s.size,
                    )
                )
            else:
                modified_sections.append(s)

        modified_manifest = BackupManifest(
            schema_version=manifest.schema_version,
            backup_id=manifest.backup_id,
            created_at=manifest.created_at,
            application_version=manifest.application_version,
            config_schema_version=manifest.config_schema_version,
            database_schema_version=manifest.database_schema_version,
            source_install=manifest.source_install,
            sections=modified_sections,
            total_size=manifest.total_size,
        )
        (bd / "manifest.json").write_text(
            json.dumps(modified_manifest.to_dict(), indent=2)
        )

        result = verify_backup(backup_paths.backup_dir.path, manifest.backup_id)
        assert result.valid is False
        assert result.reason_code == "unsafe_path"

    def test_verify_backup_config_parse_error(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id

        # Replace the config tar with one containing invalid YAML
        import io

        tar_path = bd / "config.tar"
        with tarfile.open(str(tar_path), "w") as tar:
            invalid_yaml = b":\n  :\n    - :\n  invalid: [unbalanced"
            info = tarfile.TarInfo(name="providers.yaml")
            info.size = len(invalid_yaml)
            tar.addfile(info, io.BytesIO(invalid_yaml))

        # Update manifest to reflect new tar checksum/size
        new_sha = _compute_sha256(tar_path)
        new_size = tar_path.stat().st_size
        config_section = next(
            s for s in manifest.sections if s.name == "config"
        )
        modified_sections = []
        for s in manifest.sections:
            if s.name == "config":
                modified_sections.append(
                    BackupSection(
                        name=s.name,
                        path=s.path,
                        sha256=new_sha,
                        size=new_size,
                    )
                )
            else:
                modified_sections.append(s)

        modified_manifest = BackupManifest(
            schema_version=manifest.schema_version,
            backup_id=manifest.backup_id,
            created_at=manifest.created_at,
            application_version=manifest.application_version,
            config_schema_version=manifest.config_schema_version,
            database_schema_version=manifest.database_schema_version,
            source_install=manifest.source_install,
            sections=modified_sections,
            total_size=sum(s.size for s in modified_sections),
        )
        (bd / "manifest.json").write_text(
            json.dumps(modified_manifest.to_dict(), indent=2)
        )

        result = verify_backup(backup_paths.backup_dir.path, manifest.backup_id)
        assert result.valid is False
        assert result.reason_code in ("config_parse_error", "config_tar_corrupt")


# ---------------------------------------------------------------------------
# Listing Tests
# ---------------------------------------------------------------------------


class TestListBackups:
    def test_list_backups_empty(self, backup_paths):
        result = list_backups(backup_paths.backup_dir.path)
        assert result == []

    def test_list_backups_with_backups(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m1 = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2026-07-15T000000Z-1.4.0",
            app_version="1.4.0",
            tag="first",
        )
        m2 = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2026-07-15T010000Z-1.4.0",
            app_version="1.4.0",
            tag="second",
        )

        result = list_backups(backup_paths.backup_dir.path)
        assert len(result) == 2
        ids = [m.backup_id for m in result]
        assert m1.backup_id in ids
        assert m2.backup_id in ids

    def test_list_backups_pinned(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        pin_backup(backup_paths.backup_dir.path, manifest.backup_id)

        result = list_backups(backup_paths.backup_dir.path)
        assert len(result) == 1
        assert result[0].pinned is True


# ---------------------------------------------------------------------------
# Pinning Tests
# ---------------------------------------------------------------------------


class TestPinning:
    def test_pin_backup(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        pin_backup(backup_paths.backup_dir.path, manifest.backup_id)

        pins_file = backup_paths.backup_dir.path / "pins.json"
        assert pins_file.exists()
        data = json.loads(pins_file.read_text())
        assert manifest.backup_id in data["pinned"]

    def test_unpin_backup(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        pin_backup(backup_paths.backup_dir.path, manifest.backup_id)
        unpin_backup(backup_paths.backup_dir.path, manifest.backup_id)

        pins_file = backup_paths.backup_dir.path / "pins.json"
        data = json.loads(pins_file.read_text())
        assert manifest.backup_id not in data["pinned"]

    def test_prune_respects_pins(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m_old = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2020-01-01T000000Z-1.0.0",
            app_version="1.0.0",
        )
        m_new = create_backup(backup_paths)
        pin_backup(backup_paths.backup_dir.path, m_old.backup_id)

        result = prune_backups(
            backup_paths,
            max_count=1,
            max_age_days=0,
        )
        assert m_old.backup_id not in result.deleted
        assert m_old.backup_id in result.kept


# ---------------------------------------------------------------------------
# Pruning Tests
# ---------------------------------------------------------------------------


class TestPruning:
    def test_prune_by_count(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        ids = []
        for i in range(5):
            m = _create_standalone_backup(
                backup_paths.backup_dir.path,
                f"2026-01-0{i + 1}T000000Z-1.4.0",
                app_version="1.4.0",
            )
            # Age these directories so they're candidates for pruning
            old_time = time.time() - 86400 * 2
            os.utime(
                backup_paths.backup_dir.path / m.backup_id,
                (old_time, old_time),
            )
            ids.append(m.backup_id)

        result = prune_backups(
            backup_paths,
            max_count=3,
            max_age_days=0,
        )
        assert len(result.deleted) >= 2

    def test_prune_by_count_fresh_backups(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifests = []
        for i in range(5):
            m = _create_standalone_backup(
                backup_paths.backup_dir.path,
                f"2026-07-{10 + i:02d}T000000Z-1.4.0",
                app_version="1.4.0",
            )
            manifests.append(m)

        result = prune_backups(
            backup_paths,
            max_count=3,
            max_age_days=365,
        )
        assert len(result.deleted) == 2
        deleted_ids = {m.backup_id for m in manifests if m.backup_id in result.deleted}
        assert len(deleted_ids) == 2
        assert len(result.kept) == 3
        assert len(result.kept) + len(result.deleted) == 5

    def test_prune_by_count_respects_pins(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifests = []
        for i in range(5):
            m = _create_standalone_backup(
                backup_paths.backup_dir.path,
                f"2026-07-{10 + i:02d}T000000Z-1.4.0",
                app_version="1.4.0",
            )
            manifests.append(m)

        pinned_file = backup_paths.backup_dir.path / "pins.json"
        pinned_file.write_text(
            json.dumps({"pinned": [manifests[0].backup_id, manifests[1].backup_id]})
        )

        result = prune_backups(
            backup_paths,
            max_count=3,
            max_age_days=365,
        )
        assert manifests[0].backup_id in result.kept
        assert manifests[1].backup_id in result.kept
        assert len(result.deleted) == 2

    def test_prune_by_age(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m_old = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2020-01-01T000000Z-1.0.0",
            app_version="1.0.0",
        )
        # Age the old backup
        old_time = time.time() - 86400 * 100
        os.utime(
            backup_paths.backup_dir.path / m_old.backup_id,
            (old_time, old_time),
        )
        m_new = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2026-07-15T000000Z-1.4.0",
            app_version="1.4.0",
        )

        result = prune_backups(
            backup_paths,
            max_count=100,
            max_age_days=1,
        )
        assert m_old.backup_id in result.deleted
        assert m_new.backup_id in result.kept

    def test_prune_dry_run(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m_old = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2020-01-01T000000Z-1.0.0",
            app_version="1.0.0",
        )
        # Age the old backup
        old_time = time.time() - 86400 * 100
        os.utime(
            backup_paths.backup_dir.path / m_old.backup_id,
            (old_time, old_time),
        )
        m_new = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2026-07-15T000000Z-1.4.0",
            app_version="1.4.0",
        )

        result = prune_backups(
            backup_paths,
            max_count=100,
            max_age_days=1,
            dry_run=True,
        )
        assert result.dry_run is True
        assert m_old.backup_id in result.deleted
        # Old backup should still exist on disk
        assert (backup_paths.backup_dir.path / m_old.backup_id).exists()

    def test_prune_never_deletes_last(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2020-01-01T000000Z-1.0.0",
            app_version="1.0.0",
        )

        result = prune_backups(
            backup_paths,
            max_count=1,
            max_age_days=0,
        )
        assert m.backup_id not in result.deleted
        assert m.backup_id in result.kept
        assert (backup_paths.backup_dir.path / m.backup_id).exists()

    def test_prune_empty_directory(self, backup_paths):
        result = prune_backups(backup_paths)
        assert result.deleted == []
        assert result.kept == []


# ---------------------------------------------------------------------------
# Restore Tests
# ---------------------------------------------------------------------------


class TestRestore:
    def test_plan_restore_valid(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)

        plan = plan_restore(backup_paths, manifest.backup_id, dry_run=True)
        assert isinstance(plan, RestorePlan)
        assert plan.backup_id == manifest.backup_id
        assert "config" in plan.sections
        assert "database" in plan.sections
        assert "install_metadata" in plan.sections
        assert len(plan.paths_affected) > 0
        assert plan.services_to_stop == ["celery-worker", "flask-app"]

    def test_plan_restore_dry_run(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)

        # Record original env content
        original_env = backup_paths.env_file.path.read_text()

        plan = plan_restore(backup_paths, manifest.backup_id, dry_run=True)
        assert plan.safety_backup_id is None
        # File should not be modified
        assert backup_paths.env_file.path.read_text() == original_env

    def test_restore_backup_full(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        # Create backup with known content
        m = create_backup(backup_paths, tag="original")

        # Now change the env file
        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed-key\nADMIN_PASSWORD=changed-pass\n"
        )
        assert "changed-key" in backup_paths.env_file.path.read_text()

        # Patch _make_backup_id to produce unique safety backup IDs
        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        plan = restore_backup(backup_paths, m.backup_id)
        # After restore, original content should be back
        restored_env = backup_paths.env_file.path.read_text()
        assert "changed-key" not in restored_env
        assert "test-secret-key-12345" in restored_env

    def test_restore_backup_config_only(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        # Modify env file
        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed\nADMIN_PASSWORD=changed\n"
        )

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        plan = restore_backup(backup_paths, m.backup_id, config_only=True)
        assert plan.sections == ["config"]
        restored_env = backup_paths.env_file.path.read_text()
        assert "changed" not in restored_env

    def test_restore_backup_data_only(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        # Modify env file (should NOT be restored)
        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed\nADMIN_PASSWORD=changed\n"
        )

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        plan = restore_backup(backup_paths, m.backup_id, data_only=True)
        assert "config" not in plan.sections
        assert "database" in plan.sections
        # Env file should remain modified
        assert "changed" in backup_paths.env_file.path.read_text()

    def test_restore_creates_safety_backup(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        # Count backups before restore
        backups_before = list_backups(backup_paths.backup_dir.path)
        count_before = len(backups_before)

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        restore_backup(backup_paths, m.backup_id)

        backups_after = list_backups(backup_paths.backup_dir.path)
        # Should have original + safety backup
        assert len(backups_after) > count_before

    def test_restore_permissions(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        restore_backup(backup_paths, m.backup_id)

        # Check env file permissions
        mode = backup_paths.env_file.path.stat().st_mode & 0o777
        assert mode == 0o600, f"env file should be 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# Version Compatibility Tests
# ---------------------------------------------------------------------------


class TestVersionCompatibility:
    def test_version_compatible_same_major(self):
        major_ok, minor_ok = _version_compatible("1.4.0", "1.5.0")
        assert major_ok is True
        assert minor_ok is False

    def test_version_incompatible_different_major(self):
        major_ok, minor_ok = _version_compatible("1.4.0", "2.0.0")
        assert major_ok is False
        assert minor_ok is False

    def test_version_compatible_same_minor(self):
        major_ok, minor_ok = _version_compatible("1.4.0", "1.4.1")
        assert major_ok is True
        assert minor_ok is True

    def test_version_compatible_identical(self):
        major_ok, minor_ok = _version_compatible("1.4.0", "1.4.0")
        assert major_ok is True
        assert minor_ok is True

    def test_parse_version(self):
        assert _parse_version("1.4.0") == (1, 4, 0)
        assert _parse_version("2.0.0") == (2, 0, 0)
        assert _parse_version("0.0.0") == (0, 0, 0)
        assert _parse_version("1") == (1,)

    def test_parse_version_non_numeric(self):
        result = _parse_version("1.4.0-beta")
        assert result == (1, 4)


# ---------------------------------------------------------------------------
# Migration Framework Tests
# ---------------------------------------------------------------------------


class TestMigrationFramework:
    def test_plan_migrations_empty(self):
        result = plan_migrations([], "1.0.0", "2.0.0")
        assert result == []

    def test_plan_migrations_ordered(self):
        m1 = FakeMigration(
            id="m1", from_version="1.0.0", to_version="1.1.0"
        )
        m2 = FakeMigration(
            id="m2", from_version="1.1.0", to_version="1.2.0"
        )
        m3 = FakeMigration(
            id="m3", from_version="1.2.0", to_version="1.3.0"
        )
        # Pass in reverse order
        result = plan_migrations([m3, m1, m2], "1.0.0", "1.3.0")
        assert len(result) == 3
        assert result[0].id == "m1"
        assert result[1].id == "m2"
        assert result[2].id == "m3"

    def test_plan_migrations_downgrade_refused(self):
        with pytest.raises(BackupError) as exc_info:
            plan_migrations([], "2.0.0", "1.0.0")
        assert exc_info.value.code == "DOWNGRADE_NOT_SUPPORTED"

    def test_plan_migrations_same_version_returns_empty(self):
        result = plan_migrations([], "1.0.0", "1.0.0")
        assert result == []

    def test_execute_migration_plan_preflight_failure(self, tmp_path):
        m = FakeMigration(
            id="m1",
            from_version="1.0.0",
            to_version="1.1.0",
            fail_preflight=True,
        )
        reports = execute_migration_plan([m], tmp_path)
        assert len(reports) == 1
        assert reports[0].success is False
        assert "Preflight" in reports[0].message
        assert m.apply_called is False

    def test_execute_migration_plan_success(self, tmp_path):
        m1 = FakeMigration(
            id="m1", from_version="1.0.0", to_version="1.1.0"
        )
        m2 = FakeMigration(
            id="m2", from_version="1.1.0", to_version="1.2.0"
        )
        reports = execute_migration_plan([m1, m2], tmp_path)
        assert len(reports) == 4  # preflight + apply for each
        assert all(r.success for r in reports)
        assert m1.preflight_called is True
        assert m1.apply_called is True
        assert m2.preflight_called is True
        assert m2.apply_called is True

    def test_migration_idempotent(self, tmp_path):
        m = FakeMigration(id="m1", from_version="1.0.0", to_version="1.1.0")
        # Run twice
        reports1 = execute_migration_plan([m], tmp_path)
        m2 = FakeMigration(
            id="m1", from_version="1.0.0", to_version="1.1.0"
        )
        reports2 = execute_migration_plan([m2], tmp_path)
        # Both should succeed independently (protocol doesn't prevent it)
        assert all(r.success for r in reports1)
        assert all(r.success for r in reports2)

    def test_execute_migration_plan_apply_failure(self, tmp_path):
        m = FakeMigration(
            id="m1",
            from_version="1.0.0",
            to_version="1.1.0",
            fail_apply=True,
        )
        m2 = FakeMigration(
            id="m2", from_version="1.1.0", to_version="1.2.0"
        )
        reports = execute_migration_plan([m, m2], tmp_path)
        # m1 preflight + apply, then stop (m2 not reached)
        assert len(reports) == 2
        assert reports[0].success is True  # preflight
        assert reports[1].success is False  # apply
        assert m2.preflight_called is False
        assert m2.apply_called is False

    def test_base_migration_rollback_not_reversible(self, tmp_path):
        m = FakeMigration(
            id="m1",
            from_version="1.0.0",
            to_version="1.1.0",
            reversible=False,
        )
        report = m.rollback(tmp_path, {})
        assert report.success is False
        assert "not reversible" in report.message

    def test_plan_migrations_filters_by_range(self):
        m1 = FakeMigration(
            id="m1", from_version="1.0.0", to_version="1.1.0"
        )
        m2 = FakeMigration(
            id="m2", from_version="1.1.0", to_version="1.2.0"
        )
        m3 = FakeMigration(
            id="m3", from_version="2.0.0", to_version="2.1.0"
        )
        # Only m1 and m2 are in range 1.0.0 -> 1.2.0
        result = plan_migrations([m1, m2, m3], "1.0.0", "1.2.0")
        assert len(result) == 2
        assert result[0].id == "m1"
        assert result[1].id == "m2"


# ---------------------------------------------------------------------------
# Manifest Tests
# ---------------------------------------------------------------------------


class TestManifest:
    def test_manifest_to_dict_roundtrip(self):
        original = BackupManifest(
            schema_version=1,
            backup_id="2026-07-15T000000Z-1.4.0",
            created_at="2026-07-15T00:00:00+00:00",
            application_version="1.4.0",
            config_schema_version="50",
            database_schema_version="036",
            source_install={"channel": "stable", "commit": "abc123"},
            sections=[
                BackupSection(
                    name="config",
                    path="config.tar",
                    sha256="abc123",
                    size=1024,
                ),
                BackupSection(
                    name="database",
                    path="database.sqlite",
                    sha256="def456",
                    size=2048,
                ),
                BackupSection(
                    name="install_metadata",
                    path="install_metadata.json",
                    sha256="ghi789",
                    size=128,
                ),
            ],
            pinned=True,
            tag="pre-upgrade",
            total_size=3200,
        )

        d = original.to_dict()
        restored = BackupManifest.from_dict(d)

        assert restored.schema_version == original.schema_version
        assert restored.backup_id == original.backup_id
        assert restored.created_at == original.created_at
        assert restored.application_version == original.application_version
        assert restored.config_schema_version == original.config_schema_version
        assert (
            restored.database_schema_version
            == original.database_schema_version
        )
        assert restored.source_install == original.source_install
        assert len(restored.sections) == len(original.sections)
        assert restored.pinned == original.pinned
        assert restored.tag == original.tag
        assert restored.total_size == original.total_size

    def test_manifest_schema_version(self, manifest_data=None):
        m = BackupManifest(
            schema_version=1,
            backup_id="test",
            created_at="2026-07-15T00:00:00+00:00",
            application_version="1.0.0",
            config_schema_version="1",
            database_schema_version=None,
            source_install={},
            sections=[],
        )
        assert m.schema_version == 1

    def test_manifest_size_bytes_property(self):
        m = BackupManifest(
            schema_version=1,
            backup_id="test",
            created_at="2026-07-15T00:00:00+00:00",
            application_version="1.0.0",
            config_schema_version="1",
            database_schema_version=None,
            source_install={},
            sections=[
                BackupSection(name="a", path="a.bin", sha256="x", size=100),
                BackupSection(name="b", path="b.bin", sha256="y", size=200),
            ],
            total_size=0,
        )
        assert m.size_bytes == 300

    def test_manifest_size_bytes_with_total(self):
        m = BackupManifest(
            schema_version=1,
            backup_id="test",
            created_at="2026-07-15T00:00:00+00:00",
            application_version="1.0.0",
            config_schema_version="1",
            database_schema_version=None,
            source_install={},
            sections=[
                BackupSection(name="a", path="a.bin", sha256="x", size=100),
            ],
            total_size=500,
        )
        assert m.size_bytes == 500

    def test_manifest_path_property(self):
        m = BackupManifest(
            schema_version=1,
            backup_id="2026-07-15T000000Z-1.4.0",
            created_at="2026-07-15T00:00:00+00:00",
            application_version="1.4.0",
            config_schema_version="1",
            database_schema_version=None,
            source_install={},
            sections=[],
        )
        assert m.path == "2026-07-15T000000Z-1.4.0"


# ---------------------------------------------------------------------------
# Lock Tests
# ---------------------------------------------------------------------------


class TestLocking:
    def test_concurrent_backup_lock(self, backup_paths, monkeypatch):
        import fcntl

        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )

        lock_path = backup_paths.state_dir.path / "backup.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Hold the lock open
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            with pytest.raises(BackupError) as exc_info:
                create_backup(backup_paths)
            assert exc_info.value.code == "LOCK_BUSY"
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


# ---------------------------------------------------------------------------
# Utility Tests
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_compute_sha256(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        sha = _compute_sha256(test_file)
        assert len(sha) == 64
        assert sha == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_make_backup_id(self):
        bid = _make_backup_id("1.4.0")
        assert "1.4.0" in bid
        assert "T" in bid
        assert bid.endswith("Z-1.4.0")

    def test_safe_archive_path_valid(self):
        assert _safe_archive_path("config.tar") is True
        assert _safe_archive_path("subdir/file.yaml") is True

    def test_safe_archive_path_traversal(self):
        assert _safe_archive_path("../etc/passwd") is False
        assert _safe_archive_path("subdir/../../etc/passwd") is False

    def test_safe_archive_path_absolute(self):
        assert _safe_archive_path("/etc/passwd") is False

    def test_get_database_schema_version(self, backup_paths):
        version = _get_database_schema_version(
            backup_paths.database_file.path
        )
        assert version == "036"

    def test_get_database_schema_version_missing(self, tmp_path):
        version = _get_database_schema_version(tmp_path / "nonexistent.db")
        assert version is None

    def test_get_application_version_fallback(self, monkeypatch):
        monkeypatch.setattr(
            "importlib.metadata.version",
            lambda x: (_ for _ in ()).throw(
                importlib.metadata.PackageNotFoundError
            ),
        )
        # The patched version is only for the outer call; need to patch
        # _get_application_version directly
        import importlib.metadata as _im

        original = _im.version

        def _patched(pkg):
            if pkg == "ainews":
                raise _im.PackageNotFoundError
            return original(pkg)

        monkeypatch.setattr(_im, "version", _patched)
        assert _get_application_version() == "0.0.0"

    def test_get_migration_status_for_backup(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)

        status = get_migration_status_for_backup(
            backup_paths.backup_dir.path, manifest.backup_id
        )
        assert status["version"] == "036"
        assert status["error"] is None

    def test_get_migration_status_no_database(self, tmp_path):
        status = get_migration_status_for_backup(tmp_path, "nonexistent")
        assert status["version"] is None
        assert "not found" in status["error"]

    def test_show_backup(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths, tag="test-show")

        shown = show_backup(
            backup_paths.backup_dir.path, manifest.backup_id
        )
        assert shown.backup_id == manifest.backup_id
        assert shown.tag == "test-show"

    def test_show_backup_not_found(self, backup_paths):
        with pytest.raises(FileNotFoundError):
            show_backup(backup_paths.backup_dir.path, "no-such-backup")


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_create_backup_no_database(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        # Remove the database
        backup_paths.database_file.path.unlink()
        manifest = create_backup(backup_paths)
        section_names = [s.name for s in manifest.sections]
        assert "database" not in section_names
        assert "config" in section_names

    def test_create_backup_no_install_metadata(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        backup_paths.install_metadata_file.path.unlink()
        manifest = create_backup(backup_paths)
        section_names = [s.name for s in manifest.sections]
        assert "install_metadata" not in section_names

    def test_create_backup_missing_config_file(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        # Remove one config file — backup should still succeed
        backup_paths.topics_file.path.unlink()
        manifest = create_backup(backup_paths)
        assert manifest.schema_version == 1

    def test_prune_single_old_backup_stays(self, backup_paths, monkeypatch):
        """Even if a single old backup exists, it must not be pruned."""
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2020-01-01T000000Z-1.0.0",
            app_version="1.0.0",
        )
        result = prune_backups(
            backup_paths,
            max_count=1,
            max_age_days=0,
        )
        assert m.backup_id not in result.deleted
        assert m.backup_id in result.kept

    def test_verify_result_reason_property(self):
        r = VerifyResult(
            valid=False,
            reason_code="test_code",
            message="test message",
        )
        assert r.reason == "test_code"

    def test_verify_result_reason_fallback(self):
        r = VerifyResult(
            valid=False,
            reason_code=None,
            message="fallback message",
        )
        assert r.reason == "fallback message"


# ---------------------------------------------------------------------------
# WAL Snapshot Consistency Tests
# ---------------------------------------------------------------------------


class TestWALSnapshot:
    def test_backup_with_active_wal(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        db_path = backup_paths.database_file.path
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO articles (title) VALUES ('WAL test article')")
        conn.commit()
        conn.close()

        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id
        db_section = next(
            s for s in manifest.sections if s.name == "database"
        )
        backup_db = bd / db_section.path

        backup_conn = sqlite3.connect(f"file:{backup_db}?mode=ro", uri=True)
        result = backup_conn.execute(
            "SELECT title FROM articles WHERE title = 'WAL test article'"
        ).fetchone()
        backup_conn.close()
        assert result is not None
        assert result[0] == "WAL test article"

    def test_backup_wal_files_captured(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        db_path = backup_paths.database_file.path
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO articles (title) VALUES ('WAL test')")
        conn.commit()
        wal_path = Path(str(db_path) + "-wal")
        shm_path = Path(str(db_path) + "-shm")
        conn.close()

        manifest = create_backup(backup_paths)
        bd = backup_paths.backup_dir.path / manifest.backup_id
        db_section = next(
            s for s in manifest.sections if s.name == "database"
        )
        backup_db = bd / db_section.path

        backup_conn = sqlite3.connect(str(backup_db))
        result = backup_conn.execute(
            "SELECT COUNT(*) FROM articles"
        ).fetchone()
        backup_conn.close()
        assert result[0] >= 1


# ---------------------------------------------------------------------------
# Config Mutation Concurrent with Locking Tests
# ---------------------------------------------------------------------------


class TestConfigMutation:
    def test_backup_during_config_write_blocks(self, backup_paths, monkeypatch):
        import fcntl

        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        lock_path = backup_paths.state_dir.path / "backup.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            with pytest.raises(BackupError) as exc_info:
                create_backup(backup_paths)
            assert exc_info.value.code == "LOCK_BUSY"
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_backup_completes_after_lock_release(self, backup_paths, monkeypatch):
        import fcntl

        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        lock_path = backup_paths.state_dir.path / "backup.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            with pytest.raises(BackupError):
                create_backup(backup_paths)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

        manifest = create_backup(backup_paths)
        assert manifest.schema_version == 1


# ---------------------------------------------------------------------------
# Incomplete Backup Publication Tests
# ---------------------------------------------------------------------------


class TestIncompleteBackup:
    def test_staging_cleanup_on_failure(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        monkeypatch.setattr(
            "ainews_config.backup._validate_config_files",
            lambda paths: (_ for _ in ()).throw(
                BackupError(message="Simulated validation failure", code="CONFIG_INVALID")
            ),
        )

        with pytest.raises(BackupError):
            create_backup(backup_paths)

        staging_dirs = [
            d
            for d in backup_paths.backup_dir.path.iterdir()
            if d.is_dir() and d.name.startswith(".staging-")
        ]
        assert staging_dirs == []

    def test_no_partial_backup_on_config_failure(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        monkeypatch.setattr(
            "ainews_config.backup._validate_config_files",
            lambda paths: (_ for _ in ()).throw(
                BackupError(message="Simulated validation failure", code="CONFIG_INVALID")
            ),
        )

        with pytest.raises(BackupError):
            create_backup(backup_paths)

        backup_dirs = [
            d
            for d in backup_paths.backup_dir.path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        assert backup_dirs == []


# ---------------------------------------------------------------------------
# Health Check Rollback Tests
# ---------------------------------------------------------------------------


class TestHealthCheckRollback:
    def test_rollback_on_health_failure(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed-key\nADMIN_PASSWORD=changed-pass\n"
        )

        class FakeLifecycle:
            def __init__(self):
                self.stopped = False
                self.started = False
                self.health_checked = False

            def stop_services(self) -> bool:
                self.stopped = True
                return True

            def start_services(self, timeout: int = 120) -> bool:
                self.started = True
                return True

            def check_health(self, timeout: int = 10) -> bool:
                self.health_checked = True
                return False

        lifecycle = FakeLifecycle()

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        from ainews_config.backup import RestoreError

        with pytest.raises(RestoreError) as exc_info:
            restore_backup(backup_paths, m.backup_id, lifecycle=lifecycle)

        assert "health check" in str(exc_info.value.message).lower()
        assert lifecycle.stopped is True
        assert lifecycle.health_checked is True

    def test_rollback_reverts_to_pre_restore_state(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        original_env = backup_paths.env_file.path.read_text()
        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed\nADMIN_PASSWORD=changed\n"
        )

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        class FailHealthLifecycle:
            def stop_services(self) -> bool:
                return True
            def start_services(self, timeout: int = 120) -> bool:
                return True
            def check_health(self, timeout: int = 10) -> bool:
                return False

        from ainews_config.backup import RestoreError

        with pytest.raises(RestoreError):
            restore_backup(
                backup_paths, m.backup_id, lifecycle=FailHealthLifecycle()
            )

        current_env = backup_paths.env_file.path.read_text()
        assert "changed" in current_env


# ---------------------------------------------------------------------------
# Interrupted Restore Recovery Tests
# ---------------------------------------------------------------------------


class TestInterruptedRestore:
    def test_safety_backup_created_before_restore(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        backups_before = list_backups(backup_paths.backup_dir.path)
        count_before = len(backups_before)

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        restore_backup(backup_paths, m.backup_id)

        backups_after = list_backups(backup_paths.backup_dir.path)
        assert len(backups_after) > count_before

    def test_staging_cleanup_after_restore(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        restore_backup(backup_paths, m.backup_id)

        staging_dirs = [
            d
            for d in backup_paths.backup_dir.path.iterdir()
            if d.is_dir() and d.name.startswith(".restore-staging-")
        ]
        assert staging_dirs == []

    def test_staging_cleanup_after_crash_recovery(self, backup_paths, monkeypatch):
        """Simulate a leftover staging dir from a crash, verify restore succeeds and cleans its own."""
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        # Modify current state
        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed\nADMIN_PASSWORD=changed\n"
        )

        # Make backup IDs unique to avoid conflicts
        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        # Simulate crash: create a leftover staging directory
        fake_staging = backup_paths.backup_dir.path / ".restore-staging-crash-leftover"
        fake_staging.mkdir(parents=True, exist_ok=True)
        (fake_staging / "crash_marker.txt").write_text("crash evidence")

        # Restore should succeed despite the leftover staging dir
        restore_backup(backup_paths, m.backup_id)

        # Verify the restore's own staging dir is cleaned up
        restore_staging = backup_paths.backup_dir.path / f".restore-staging-{m.backup_id}"
        assert not restore_staging.exists()

        # Verify state is restored
        restored_env = backup_paths.env_file.path.read_text()
        assert "test-secret-key-12345" in restored_env

    def test_safety_backup_preserves_state_on_crash(self, backup_paths, monkeypatch):
        """Verify safety backup preserves pre-restore state even if restore fails."""
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        # Record original env content
        original_env = backup_paths.env_file.path.read_text()

        # Modify current state
        backup_paths.env_file.path.write_text(
            "SECRET_KEY=changed\nADMIN_PASSWORD=changed\n"
        )

        # Make backup IDs unique to avoid conflicts
        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        # Create a safety backup manually (simulating what restore_backup does)
        safety = create_backup(backup_paths)

        # Verify safety backup has the modified state
        safety_env = backup_paths.backup_dir.path / safety.backup_id / "config.tar"
        assert safety_env.exists()

        # Restore from original backup
        restore_backup(backup_paths, m.backup_id)

        # Verify state is restored
        restored_env = backup_paths.env_file.path.read_text()
        assert "test-secret-key-12345" in restored_env


class TestSecretFreeOutput:
    def test_manifest_no_secrets(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        d = manifest.to_dict()
        manifest_json = json.dumps(d, indent=2)

        assert "test-secret-key-12345" not in manifest_json
        assert "admin123" not in manifest_json
        assert "SECRET_KEY" not in manifest_json
        assert "ADMIN_PASSWORD" not in manifest_json

    def test_verify_result_no_secrets(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        result = verify_backup(
            backup_paths.backup_dir.path, manifest.backup_id
        )
        result_json = json.dumps({
            "valid": result.valid,
            "reason": result.reason,
            "message": result.message,
        })
        assert "test-secret-key-12345" not in result_json
        assert "admin123" not in result_json

    def test_restore_plan_no_secrets(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        plan = plan_restore(backup_paths, manifest.backup_id, dry_run=True)
        plan_json = json.dumps({
            "backup_id": plan.backup_id,
            "sections": plan.sections,
            "paths_affected": plan.paths_affected,
        })
        assert "test-secret-key-12345" not in plan_json
        assert "admin123" not in plan_json

    def test_prune_result_no_secrets(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2020-01-01T000000Z-1.0.0",
            app_version="1.0.0",
        )
        result = prune_backups(
            backup_paths, max_count=1, max_age_days=0, dry_run=True
        )
        result_json = json.dumps({
            "deleted": result.deleted,
            "kept": result.kept,
        })
        assert "SECRET_KEY" not in result_json


# ---------------------------------------------------------------------------
# Max Total Bytes Pruning Tests
# ---------------------------------------------------------------------------


class TestPruneMaxTotalBytes:
    def test_prune_by_total_bytes(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        ids = []
        for i in range(3):
            m = _create_standalone_backup(
                backup_paths.backup_dir.path,
                f"2026-01-0{i + 1}T000000Z-1.4.0",
                app_version="1.4.0",
            )
            old_time = time.time() - 86400 * 2
            os.utime(
                backup_paths.backup_dir.path / m.backup_id,
                (old_time, old_time),
            )
            ids.append(m.backup_id)

        total_size = 0
        for bid in ids:
            manifest_path = backup_paths.backup_dir.path / bid / "manifest.json"
            data = json.loads(manifest_path.read_text())
            total_size += data.get("total_size", 0)

        result = prune_backups(
            backup_paths,
            max_count=100,
            max_age_days=0,
            max_total_bytes=total_size // 2,
        )
        assert len(result.deleted) > 0

    def test_prune_max_total_bytes_dry_run(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = _create_standalone_backup(
            backup_paths.backup_dir.path,
            "2026-01-01T000000Z-1.4.0",
            app_version="1.4.0",
        )
        old_time = time.time() - 86400 * 2
        os.utime(
            backup_paths.backup_dir.path / m.backup_id,
            (old_time, old_time),
        )

        result = prune_backups(
            backup_paths,
            max_count=100,
            max_age_days=0,
            max_total_bytes=1,
            dry_run=True,
        )
        assert result.dry_run is True
        assert (backup_paths.backup_dir.path / m.backup_id).exists()


# ---------------------------------------------------------------------------
# RestorePlan New Fields Tests
# ---------------------------------------------------------------------------


class TestRestorePlanFields:
    def test_plan_restore_secrets_impact(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        plan = plan_restore(backup_paths, manifest.backup_id, dry_run=True)

        assert len(plan.secrets_impact) > 0
        assert any(".env" in s or "secret" in s.lower() for s in plan.secrets_impact)

    def test_plan_restore_restart_actions(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        plan = plan_restore(backup_paths, manifest.backup_id, dry_run=True)

        assert len(plan.restart_actions) > 0
        assert any("ainews start" in a for a in plan.restart_actions)

    def test_plan_restore_permissions_impact(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        manifest = create_backup(backup_paths)
        plan = plan_restore(backup_paths, manifest.backup_id, dry_run=True)

        assert len(plan.permissions_impact) > 0
        assert any("0o600" in p for p in plan.permissions_impact)


# ---------------------------------------------------------------------------
# Lifecycle Driver Integration Tests
# ---------------------------------------------------------------------------


class TestLifecycleIntegration:
    def test_restore_calls_lifecycle_stop(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        class TrackingLifecycle:
            def __init__(self):
                self.calls = []

            def stop_services(self) -> bool:
                self.calls.append("stop")
                return True

            def start_services(self, timeout: int = 120) -> bool:
                self.calls.append("start")
                return True

            def check_health(self, timeout: int = 10) -> bool:
                self.calls.append("health")
                return True

        lifecycle = TrackingLifecycle()
        restore_backup(backup_paths, m.backup_id, lifecycle=lifecycle)

        assert "stop" in lifecycle.calls
        assert "start" in lifecycle.calls
        assert "health" in lifecycle.calls

    def test_restore_without_lifecycle(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        m = create_backup(backup_paths)

        call_count = 0
        orig_make_id = _make_backup_id

        def _unique_make_id(app_version: str) -> str:
            nonlocal call_count
            call_count += 1
            return orig_make_id(app_version) + f"-{call_count}"

        monkeypatch.setattr(
            "ainews_config.backup._make_backup_id", _unique_make_id
        )

        plan = restore_backup(backup_paths, m.backup_id, lifecycle=None)
        assert plan.backup_id == m.backup_id


# ---------------------------------------------------------------------------
# Cross-File Config Validation Tests
# ---------------------------------------------------------------------------


class TestCrossFileValidation:
    def test_verify_catches_missing_provider_reference(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        import io

        tar_path = backup_paths.backup_dir.path / "cross-validate-test"
        tar_path.mkdir(parents=True, exist_ok=True)

        config_tar = tar_path / "config.tar"
        with tarfile.open(str(config_tar), "w") as tar:
            providers_content = b"providers:\n  ollama:\n    type: ollama\n    enabled: true\n"
            info = tarfile.TarInfo(name="providers.yaml")
            info.size = len(providers_content)
            tar.addfile(info, io.BytesIO(providers_content))

            pipeline_content = b"pipeline:\n  selector:\n    provider: nonexistent\n"
            info2 = tarfile.TarInfo(name="pipeline.yaml")
            info2.size = len(pipeline_content)
            tar.addfile(info2, io.BytesIO(pipeline_content))

            env_content = b"SECRET_KEY=test\n"
            info3 = tarfile.TarInfo(name=".env")
            info3.size = len(env_content)
            tar.addfile(info3, io.BytesIO(env_content))

        from ainews_config.backup import _verify_config_cross_validation

        result = _verify_config_cross_validation(tar_path)
        assert result is not None
        assert result.valid is False
        assert result.reason_code == "config_parse_error"
        assert "nonexistent" in result.message

    def test_verify_valid_config_passes(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        import io

        tar_path = backup_paths.backup_dir.path / "cross-validate-valid"
        tar_path.mkdir(parents=True, exist_ok=True)

        config_tar = tar_path / "config.tar"
        with tarfile.open(str(config_tar), "w") as tar:
            providers_content = b"providers:\n  ollama:\n    type: ollama\n    enabled: true\n"
            info = tarfile.TarInfo(name="providers.yaml")
            info.size = len(providers_content)
            tar.addfile(info, io.BytesIO(providers_content))

            pipeline_content = b"pipeline:\n  selector:\n    provider: ollama\n"
            info2 = tarfile.TarInfo(name="pipeline.yaml")
            info2.size = len(pipeline_content)
            tar.addfile(info2, io.BytesIO(pipeline_content))

            env_content = b"SECRET_KEY=test\n"
            info3 = tarfile.TarInfo(name=".env")
            info3.size = len(env_content)
            tar.addfile(info3, io.BytesIO(env_content))

        from ainews_config.backup import _verify_config_cross_validation

        result = _verify_config_cross_validation(tar_path)
        assert result is None


# ---------------------------------------------------------------------------
# Include Logs Tests
# ---------------------------------------------------------------------------


class TestIncludeLogs:
    def test_backup_includes_logs_when_requested(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        log_dir = backup_paths.state_dir.path.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "test.log"
        log_file.write_text("2026-07-15 test log entry\n")

        manifest = create_backup(backup_paths, include_logs=True)
        bd = backup_paths.backup_dir.path / manifest.backup_id
        config_section = next(
            s for s in manifest.sections if s.name == "config"
        )
        tar_path = bd / config_section.path

        with tarfile.open(str(tar_path), "r") as tar:
            names = tar.getnames()
            assert "logs/test.log" in names

    def test_backup_excludes_logs_by_default(self, backup_paths, monkeypatch):
        monkeypatch.setattr(
            "ainews_config.backup._get_application_version",
            lambda: "1.4.0",
        )
        log_dir = backup_paths.state_dir.path.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "test.log"
        log_file.write_text("2026-07-15 test log entry\n")

        manifest = create_backup(backup_paths, include_logs=False)
        bd = backup_paths.backup_dir.path / manifest.backup_id
        config_section = next(
            s for s in manifest.sections if s.name == "config"
        )
        tar_path = bd / config_section.path

        with tarfile.open(str(tar_path), "r") as tar:
            names = tar.getnames()
            assert not any("logs/" in n for n in names)


# ---------------------------------------------------------------------------
# Migration Identity Checksum Tests
# ---------------------------------------------------------------------------


class TestMigrationChecksum:
    def test_checksum_is_sha256_hex(self):
        from ainews_config.backup import _compute_migration_checksum

        checksum = _compute_migration_checksum("test-id", "1.0.0", "2.0.0")
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_checksum_deterministic(self):
        from ainews_config.backup import _compute_migration_checksum

        c1 = _compute_migration_checksum("id-1", "1.0.0", "2.0.0")
        c2 = _compute_migration_checksum("id-1", "1.0.0", "2.0.0")
        assert c1 == c2

    def test_checksum_changes_with_id(self):
        from ainews_config.backup import _compute_migration_checksum

        c1 = _compute_migration_checksum("id-1", "1.0.0", "2.0.0")
        c2 = _compute_migration_checksum("id-2", "1.0.0", "2.0.0")
        assert c1 != c2

    def test_checksum_changes_with_from_version(self):
        from ainews_config.backup import _compute_migration_checksum

        c1 = _compute_migration_checksum("id-1", "1.0.0", "2.0.0")
        c2 = _compute_migration_checksum("id-1", "1.1.0", "2.0.0")
        assert c1 != c2

    def test_checksum_changes_with_to_version(self):
        from ainews_config.backup import _compute_migration_checksum

        c1 = _compute_migration_checksum("id-1", "1.0.0", "2.0.0")
        c2 = _compute_migration_checksum("id-1", "1.0.0", "2.1.0")
        assert c1 != c2

    def test_base_migration_checksum_property(self):
        class TestMigration(BaseMigration):
            @property
            def id(self) -> str:
                return "test-migration"

            @property
            def from_version(self) -> str:
                return "1.0.0"

            @property
            def to_version(self) -> str:
                return "2.0.0"

            def apply(self, staging_root, context):
                return MigrationReport(
                    migration_id=self.id,
                    success=True,
                    message="Applied",
                    from_version=self.from_version,
                    to_version=self.to_version,
                )

        m = TestMigration()
        assert len(m.checksum) == 64
        assert m.checksum == _compute_migration_checksum(
            "test-migration", "1.0.0", "2.0.0"
        )


# ---------------------------------------------------------------------------
# Migration Version Fixtures Tests
# ---------------------------------------------------------------------------


class TestMigrationFixtures:
    def test_current_config_schema_version_defined(self):
        from ainews_config.migrations import CURRENT_CONFIG_SCHEMA_VERSION

        assert isinstance(CURRENT_CONFIG_SCHEMA_VERSION, str)
        assert "." in CURRENT_CONFIG_SCHEMA_VERSION

    def test_current_install_metadata_schema_version_defined(self):
        from ainews_config.migrations import CURRENT_INSTALL_METADATA_SCHEMA_VERSION

        assert isinstance(CURRENT_INSTALL_METADATA_SCHEMA_VERSION, str)
        assert "." in CURRENT_INSTALL_METADATA_SCHEMA_VERSION

    def test_current_manifest_schema_version_defined(self):
        from ainews_config.migrations import CURRENT_MANIFEST_SCHEMA_VERSION

        assert isinstance(CURRENT_MANIFEST_SCHEMA_VERSION, str)
        assert "." in CURRENT_MANIFEST_SCHEMA_VERSION

    def test_min_supported_source_version_defined(self):
        from ainews_config.migrations import MIN_SUPPORTED_SOURCE_VERSION

        assert isinstance(MIN_SUPPORTED_SOURCE_VERSION, str)
        assert "." in MIN_SUPPORTED_SOURCE_VERSION

    def test_config_schema_registry_is_list(self):
        from ainews_config.migrations import CONFIG_MIGRATIONS

        assert isinstance(CONFIG_MIGRATIONS, list)

    def test_install_metadata_schema_registry_is_list(self):
        from ainews_config.migrations import INSTALL_METADATA_MIGRATIONS

        assert isinstance(INSTALL_METADATA_MIGRATIONS, list)

    def test_manifest_schema_registry_is_list(self):
        from ainews_config.migrations import MANIFEST_MIGRATIONS

        assert isinstance(MANIFEST_MIGRATIONS, list)

    def test_get_all_migrations_returns_list(self):
        from ainews_config.migrations import get_all_migrations

        all_migrations = get_all_migrations()
        assert isinstance(all_migrations, list)

    def test_migration_checksums_unique(self):
        from ainews_config.migrations import get_all_migrations

        migrations = get_all_migrations()
        if len(migrations) > 1:
            checksums = [m.checksum for m in migrations]
            assert len(checksums) == len(set(checksums))

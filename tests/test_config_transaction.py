from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from pathlib import Path

import pytest

from ainews_config.paths import (
    PathProvenance,
    ResolvedPath,
    ResolvedPaths,
)
from ainews_config.transaction import (
    ConfigTransaction,
    TransactionError,
    list_rollbacks,
    restore_rollback,
    transaction,
)


def _make_paths(tmp_path: Path) -> ResolvedPaths:
    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.EXPLICIT,
            exists=p.exists(),
            is_writable=True,
        )

    return ResolvedPaths(
        app_dir=_rp(tmp_path),
        config_dir=_rp(tmp_path / "config"),
        data_dir=_rp(tmp_path / "data"),
        state_dir=_rp(tmp_path / "state"),
        backup_dir=_rp(tmp_path / "backups"),
        env_file=_rp(tmp_path / ".env"),
        providers_file=_rp(tmp_path / "providers.yaml"),
        pipeline_file=_rp(tmp_path / "pipeline.yaml"),
        sources_file=_rp(tmp_path / "sources.yaml"),
        topics_file=_rp(tmp_path / "topics.yaml"),
        database_file=_rp(tmp_path / "ainews.db"),
        install_metadata_file=_rp(tmp_path / "install-metadata.json"),
        transaction_lock=_rp(tmp_path / "state" / "transaction.lock"),
        transaction_staging=_rp(tmp_path / "state" / "staging"),
    )


class TestSuccessfulTransaction:
    def test_modifies_files_atomically(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("original: true\n")

        with transaction(paths) as txn:
            txn.modify_file(target, b"modified: true\n")

        assert target.read_text() == "modified: true\n"

    def test_multiple_files_in_one_transaction(self, tmp_path):
        paths = _make_paths(tmp_path)
        f1 = tmp_path / "providers.yaml"
        f2 = tmp_path / "pipeline.yaml"
        f1.write_text("a: 1\n")
        f2.write_text("b: 2\n")

        with transaction(paths) as txn:
            txn.modify_file(f1, b"a: 10\n")
            txn.modify_file(f2, b"b: 20\n")

        assert f1.read_text() == "a: 10\n"
        assert f2.read_text() == "b: 20\n"


class TestFailedTransaction:
    def test_leaves_original_files_unchanged(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("original: true\n")

        with pytest.raises(ValueError, match="simulated error"):
            with transaction(paths) as txn:
                txn.modify_file(target, b"modified: true\n")
                raise ValueError("simulated error")

        assert target.read_text() == "original: true\n"


class TestLockRelease:
    def test_lock_is_released_on_exception(self, tmp_path):
        paths = _make_paths(tmp_path)
        lock_path = paths.transaction_lock.path
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ValueError):
            with transaction(paths) as txn:
                raise ValueError("test")

        fd = os.open(str(lock_path), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pytest.fail("Lock was not released")
        finally:
            os.close(fd)

    def test_lock_is_released_on_success(self, tmp_path):
        paths = _make_paths(tmp_path)

        with transaction(paths) as txn:
            pass

        fd = os.open(str(paths.transaction_lock.path), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pytest.fail("Lock was not released")
        finally:
            os.close(fd)


class TestStagingCleanup:
    def test_staging_files_cleaned_on_success(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("a: 1\n")

        with transaction(paths) as txn:
            txn.modify_file(target, b"a: 2\n")

        staging_dir = paths.transaction_staging.path
        if staging_dir.exists():
            assert list(staging_dir.iterdir()) == []

    def test_staging_files_cleaned_on_failure(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("a: 1\n")

        with pytest.raises(RuntimeError, match="boom"):
            with transaction(paths) as txn:
                txn.modify_file(target, b"a: 2\n")
                raise RuntimeError("boom")

        staging_dir = paths.transaction_staging.path
        if staging_dir.exists():
            assert list(staging_dir.iterdir()) == []


class TestRollbackCreation:
    def test_rollback_snapshot_created(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("original: content\n")

        with transaction(paths) as txn:
            txn.modify_file(target, b"new: content\n")

        manifests = list_rollbacks(paths.backup_dir.path)
        assert len(manifests) == 1
        assert manifests[0].transaction_id.startswith("txn-")


class TestListRollbacks:
    def test_returns_manifests_sorted_by_date(self, tmp_path):
        paths = _make_paths(tmp_path)
        backup_dir = paths.backup_dir.path
        backup_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            d = backup_dir / f"txn-{i:03d}"
            d.mkdir()
            (d / "manifest.json").write_text(json.dumps({
                "transaction_id": f"txn-{i:03d}",
                "files_changed": [],
                "rollback_path": str(d),
                "created_at": f"2025-01-01T00:00:{i:02d}+00:00",
            }))

        manifests = list_rollbacks(backup_dir)
        assert len(manifests) == 3
        assert manifests[0].transaction_id == "txn-000"
        assert manifests[1].transaction_id == "txn-001"
        assert manifests[2].transaction_id == "txn-002"

    def test_returns_empty_for_missing_dir(self, tmp_path):
        assert list_rollbacks(tmp_path / "nonexistent") == []


class TestRestoreRollback:
    def test_restores_files_correctly(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("original: true\n")

        with transaction(paths) as txn:
            txn.modify_file(target, b"modified: true\n")

        assert target.read_text() == "modified: true\n"

        manifests = list_rollbacks(paths.backup_dir.path)
        assert len(manifests) == 1

        restore_rollback(paths.backup_dir.path, manifests[0].transaction_id, paths)
        assert target.read_text() == "original: true\n"

    def test_raises_on_missing_transaction(self, tmp_path):
        paths = _make_paths(tmp_path)
        with pytest.raises(TransactionError, match="Rollback not found"):
            restore_rollback(paths.backup_dir.path, "txn-nonexistent", paths)


class TestExternalModification:
    def test_aborts_on_external_modification(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("original: true\n")

        with pytest.raises(TransactionError, match="modified externally"):
            with transaction(paths) as txn:
                txn.modify_file(target, b"new: content\n")
                target.write_text("external: change\n")


class TestFileCreation:
    def test_creates_new_file(self, tmp_path):
        paths = _make_paths(tmp_path)
        new_file = tmp_path / "new_file.yaml"

        with transaction(paths) as txn:
            txn.create_file(new_file, b"key: value\n")

        assert new_file.read_text() == "key: value\n"


class TestFileDeletion:
    def test_deletes_existing_file(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("to_delete: true\n")

        with transaction(paths) as txn:
            txn.delete_file(target)

        assert not target.exists()


class TestTransactionId:
    def test_transaction_id_is_unique(self, tmp_path):
        paths = _make_paths(tmp_path)
        ids: list[str] = []

        for _ in range(5):
            txn = ConfigTransaction(paths)
            txn._transaction_id = txn._generate_transaction_id()
            ids.append(txn._transaction_id)

        assert len(set(ids)) == 5

    def test_transaction_id_format(self, tmp_path):
        paths = _make_paths(tmp_path)
        txn = ConfigTransaction(paths)
        tid = txn._generate_transaction_id()
        assert tid.startswith("txn-")


class TestLockExclusivity:
    def test_second_transaction_blocks(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("a: 1\n")

        barrier = threading.Event()
        first_done = threading.Event()
        second_blocked = threading.Event()

        def first_txn():
            with transaction(paths) as txn:
                txn.modify_file(target, b"a: 2\n")
                barrier.set()
                first_done.wait(timeout=5)

        def second_txn():
            barrier.wait(timeout=5)
            time.sleep(0.05)
            try:
                with transaction(paths) as txn:
                    pass
                second_blocked.set()
            except TransactionError:
                pass

        t1 = threading.Thread(target=first_txn)
        t2 = threading.Thread(target=second_txn)
        t1.start()
        t2.start()
        first_done.set()
        t1.join(timeout=5)
        t2.join(timeout=5)


class TestStagingDirectoryCreation:
    def test_staging_dir_created_if_missing(self, tmp_path):
        paths = _make_paths(tmp_path)
        staging_dir = paths.transaction_staging.path
        assert not staging_dir.exists()

        with transaction(paths) as txn:
            pass

        assert staging_dir.exists()


class TestTransactionContextManager:
    def test_context_manager_yields_txn(self, tmp_path):
        paths = _make_paths(tmp_path)
        with transaction(paths) as txn:
            assert isinstance(txn, ConfigTransaction)

    def test_context_manager_releases_lock_on_normal_exit(self, tmp_path):
        paths = _make_paths(tmp_path)
        with transaction(paths) as txn:
            pass

        fd = os.open(str(paths.transaction_lock.path), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pytest.fail("Lock not released")
        finally:
            os.close(fd)


class TestEdgeCases:
    def test_empty_transaction(self, tmp_path):
        paths = _make_paths(tmp_path)
        with transaction(paths) as txn:
            pass

        assert not list_rollbacks(paths.backup_dir.path)

    def test_modify_nonexistent_file(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "does_not_exist.yaml"

        with transaction(paths) as txn:
            txn.modify_file(target, b"new: content\n")

        assert target.read_text() == "new: content\n"

    def test_create_then_modify_in_same_transaction(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "new.yaml"

        with transaction(paths) as txn:
            txn.create_file(target, b"v1: 1\n")
            txn.modify_file(target, b"v2: 2\n")

        assert target.read_text() == "v2: 2\n"

    def test_yaml_validation_rejects_invalid_syntax(self, tmp_path):
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("valid: true\n")

        with pytest.raises(TransactionError, match="YAML validation"):
            with transaction(paths) as txn:
                txn.modify_file(target, b"{{invalid yaml::\n")

    def test_atomic_replace_creates_parent_dirs(self, tmp_path):
        paths = _make_paths(tmp_path)
        deep = tmp_path / "a" / "b" / "c" / "file.txt"

        with transaction(paths) as txn:
            txn.create_file(deep, b"deep: true\n")

        assert deep.read_text() == "deep: true\n"

    def test_transaction_error_has_code(self, tmp_path):
        paths = _make_paths(tmp_path)
        err = TransactionError(message="test", code="TEST_CODE")
        assert err.code == "TEST_CODE"
        assert err.message == "test"
        assert err.partial_files == []

    def test_snapshot_records_existence(self, tmp_path):
        paths = _make_paths(tmp_path)
        txn = ConfigTransaction(paths)

        existing = tmp_path / "exists.txt"
        existing.write_text("data")
        txn._snapshot_file(existing)
        assert txn._snapshots[-1].exists is True

        missing = tmp_path / "missing.txt"
        txn._snapshot_file(missing)
        assert txn._snapshots[-1].exists is False

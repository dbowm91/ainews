from __future__ import annotations

import fcntl
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

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

pytestmark = pytest.mark.integration


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


class TestTransactionMultiFileUpdate:
    def test_valid_multi_file_update(self, tmp_path):
        """Load config, change values, commit atomically, verify all files updated."""
        paths = _make_paths(tmp_path)

        env_file = tmp_path / ".env"
        providers_file = tmp_path / "providers.yaml"
        pipeline_file = tmp_path / "pipeline.yaml"

        env_file.write_text(
            "SECRET_KEY=old_secret\n"
            "ADMIN_PASSWORD=old_password\n"
            "AINEWS_LOG_LEVEL=INFO\n"
        )
        providers_file.write_text(
            "# Provider configuration\n"
            "providers:\n"
            "  ollama:\n"
            "    enabled: true\n"
            "    base_url: http://localhost:11434\n"
        )
        pipeline_file.write_text(
            "# Pipeline settings\n"
            "pipeline:\n"
            "  max_retries: 3\n"
            "  timeout: 120\n"
        )

        with transaction(paths) as txn:
            txn.modify_file(env_file, b"AINEWS_LOG_LEVEL=DEBUG\n")
            txn.modify_file(
                providers_file,
                b"# Provider configuration\n"
                b"providers:\n"
                b"  ollama:\n"
                b"    enabled: false\n"
                b"    base_url: http://localhost:11434\n",
            )
            txn.modify_file(
                pipeline_file,
                b"# Pipeline settings\n"
                b"pipeline:\n"
                b"  max_retries: 5\n"
                b"  timeout: 240\n",
            )

        # Verify all files updated
        assert env_file.read_text() == "AINEWS_LOG_LEVEL=DEBUG\n"
        assert "enabled: false" in providers_file.read_text()
        assert "max_retries: 5" in pipeline_file.read_text()

        # Verify unrelated fields in .env are removed (env file is replaced wholesale)
        env_content = env_file.read_text()
        assert "SECRET_KEY=" not in env_content

        # Verify YAML comments preserved where supported
        providers_content = providers_file.read_text()
        assert providers_content.startswith("# Provider configuration")

        pipeline_content = pipeline_file.read_text()
        assert pipeline_content.startswith("# Pipeline settings")

    def test_multi_file_update_preserves_unrelated_files(self, tmp_path):
        """Modifying some files does not touch unrelated files."""
        paths = _make_paths(tmp_path)

        providers_file = tmp_path / "providers.yaml"
        sources_file = tmp_path / "sources.yaml"
        topics_file = tmp_path / "topics.yaml"

        providers_file.write_text("providers:\n  ollama:\n    enabled: true\n")
        sources_file.write_text("sources:\n  - name: test\n    type: rss\n")
        topics_file.write_text("topics:\n  - ai_safety\n  - llms\n")

        original_sources = sources_file.read_text()
        original_topics = topics_file.read_text()

        with transaction(paths) as txn:
            txn.modify_file(providers_file, b"providers:\n  ollama:\n    enabled: false\n")

        assert "enabled: false" in providers_file.read_text()
        assert sources_file.read_text() == original_sources
        assert topics_file.read_text() == original_topics

    def test_create_new_file_in_transaction(self, tmp_path):
        """Creating a new file in a multi-file transaction."""
        paths = _make_paths(tmp_path)

        env_file = tmp_path / ".env"
        new_file = tmp_path / "custom.yaml"

        env_file.write_text("KEY=value\n")

        with transaction(paths) as txn:
            txn.modify_file(env_file, b"KEY=new_value\n")
            txn.create_file(new_file, b"custom:\n  enabled: true\n")

        assert env_file.read_text() == "KEY=new_value\n"
        assert new_file.read_text() == "custom:\n  enabled: true\n"


class TestTransactionInvalidUpdate:
    def test_invalid_cross_file_no_changes(self, tmp_path):
        """Validation failure prevents any file changes."""
        paths = _make_paths(tmp_path)

        providers_file = tmp_path / "providers.yaml"
        env_file = tmp_path / ".env"

        providers_file.write_text(
            "providers:\n"
            "  ollama:\n"
            "    enabled: true\n"
        )
        env_file.write_text("SECRET_KEY=original_secret\n")

        original_providers = providers_file.read_bytes()
        original_env = env_file.read_bytes()

        with pytest.raises(TransactionError, match="validation|YAML|Cross-file"):
            with transaction(paths) as txn:
                txn.modify_file(providers_file, b"{{{{invalid yaml::\n")
                txn.modify_file(env_file, b"KEY=value\n")

        # Byte-for-byte preservation of original files
        assert providers_file.read_bytes() == original_providers
        assert env_file.read_bytes() == original_env

    def test_invalid_yaml_prevents_all_changes(self, tmp_path):
        """Even valid files are not written when one file has invalid YAML."""
        paths = _make_paths(tmp_path)

        good_file = tmp_path / "sources.yaml"
        bad_file = tmp_path / "pipeline.yaml"

        good_file.write_text("sources:\n  - name: test\n")
        bad_file.write_text("pipeline:\n  max_retries: 3\n")

        original_good = good_file.read_bytes()
        original_bad = bad_file.read_bytes()

        with pytest.raises(TransactionError):
            with transaction(paths) as txn:
                txn.modify_file(good_file, b"sources:\n  - name: updated\n")
                txn.modify_file(bad_file, b":invalid: yaml: {{{::\n")

        assert good_file.read_bytes() == original_good
        assert bad_file.read_bytes() == original_bad

    def test_empty_yaml_rejected(self, tmp_path):
        """Empty YAML file content is rejected (YAML parse error on bare colon etc)."""
        paths = _make_paths(tmp_path)

        target = tmp_path / "providers.yaml"
        target.write_text("providers:\n  ollama:\n    enabled: true\n")

        original = target.read_bytes()

        # Invalid YAML: a bare colon with no key
        with pytest.raises(TransactionError):
            with transaction(paths) as txn:
                txn.modify_file(target, b":\n")

        assert target.read_bytes() == original


class TestTransactionMidCommitFailure:
    def test_mid_commit_failure_restores_original(self, tmp_path):
        """Failure during replacement restores original state."""
        paths = _make_paths(tmp_path)

        file_a = tmp_path / "providers.yaml"
        file_b = tmp_path / "pipeline.yaml"

        file_a.write_text("a: original_a\n")
        file_b.write_text("b: original_b\n")

        original_a = file_a.read_bytes()
        original_b = file_b.read_bytes()

        call_count = 0
        original_atomic = ConfigTransaction._atomic_replace

        def failing_atomic(target_path: Path, content: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Simulated disk failure mid-commit")
            return original_atomic(target_path, content)

        with patch.object(ConfigTransaction, "_atomic_replace", side_effect=failing_atomic):
            with pytest.raises(TransactionError, match="Failed to apply changes"):
                with transaction(paths) as txn:
                    txn.modify_file(file_a, b"a: new_a\n")
                    txn.modify_file(file_b, b"b: new_b\n")

        # Original state restored for all files
        assert file_a.read_bytes() == original_a
        assert file_b.read_bytes() == original_b

    def test_no_temporary_files_remain_after_failure(self, tmp_path):
        """No staging or temp files remain after a mid-commit failure."""
        paths = _make_paths(tmp_path)

        target = tmp_path / "providers.yaml"
        target.write_text("key: original\n")

        original = target.read_bytes()

        with patch.object(
            ConfigTransaction,
            "_atomic_replace",
            side_effect=OSError("Disk full"),
        ):
            with pytest.raises(TransactionError):
                with transaction(paths) as txn:
                    txn.modify_file(target, b"key: new_value\n")

        assert target.read_bytes() == original

        staging_dir = paths.transaction_staging.path
        if staging_dir.exists():
            staging_files = [f for f in staging_dir.iterdir() if f.is_file()]
            assert staging_files == []

    def test_subsequent_transaction_succeeds_after_failure(self, tmp_path):
        """A new transaction can succeed after a previous one failed."""
        paths = _make_paths(tmp_path)

        target = tmp_path / "providers.yaml"
        target.write_text("key: v1\n")

        # First transaction fails
        with patch.object(
            ConfigTransaction,
            "_atomic_replace",
            side_effect=OSError("Temporary failure"),
        ):
            with pytest.raises(TransactionError):
                with transaction(paths) as txn:
                    txn.modify_file(target, b"key: v2\n")

        assert target.read_text() == "key: v1\n"

        # Second transaction succeeds
        with transaction(paths) as txn:
            txn.modify_file(target, b"key: v3\n")

        assert target.read_text() == "key: v3\n"

    def test_failure_restores_already_replaced_files(self, tmp_path):
        """When the second file fails, the first replaced file is rolled back."""
        paths = _make_paths(tmp_path)

        file_a = tmp_path / "a.yaml"
        file_b = tmp_path / "b.yaml"

        file_a.write_text("a: 1\n")
        file_b.write_text("b: 1\n")

        original_a = file_a.read_bytes()
        original_b = file_b.read_bytes()

        call_count = 0
        original_atomic = ConfigTransaction._atomic_replace

        def fail_on_second(target_path: Path, content: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("Fail on second file")
            return original_atomic(target_path, content)

        with patch.object(ConfigTransaction, "_atomic_replace", side_effect=fail_on_second):
            with pytest.raises(TransactionError, match="Failed to apply changes"):
                with transaction(paths) as txn:
                    txn.modify_file(file_a, b"a: 2\n")
                    txn.modify_file(file_b, b"b: 2\n")

        assert file_a.read_bytes() == original_a
        assert file_b.read_bytes() == original_b


class TestTransactionStaleLock:
    def test_stale_lock_detected(self, tmp_path):
        """Stale lock is detected and recovered."""
        paths = _make_paths(tmp_path)
        lock_path = paths.transaction_lock.path
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Create a stale lock file with old timestamp (>10 minutes)
        lock_path.write_text("stale lock content")
        old_time = time.time() - 700  # ~12 minutes ago
        os.utime(lock_path, (old_time, old_time))

        # Transaction should succeed despite stale lock
        target = tmp_path / "providers.yaml"
        target.write_text("key: original\n")

        with transaction(paths) as txn:
            txn.modify_file(target, b"key: updated\n")

        assert target.read_text() == "key: updated\n"

    def test_active_lock_respected(self, tmp_path):
        """Active lock prevents concurrent writes."""
        paths = _make_paths(tmp_path)
        lock_path = paths.transaction_lock.path
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        barrier = threading.Event()
        first_done = threading.Event()
        second_failed = threading.Event()

        def first_txn():
            # Hold the lock open
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                barrier.set()
                # Wait for second transaction to attempt
                time.sleep(2)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                first_done.set()

        def second_txn():
            barrier.wait(timeout=5)
            time.sleep(0.1)  # Let first txn hold the lock
            try:
                with transaction(paths) as txn:
                    pass
                # Should not reach here
            except TransactionError as e:
                assert e.code == "LOCK_BUSY"
                second_failed.set()

        t1 = threading.Thread(target=first_txn)
        t2 = threading.Thread(target=second_txn)
        t1.start()
        t2.start()

        first_done.wait(timeout=5)
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert second_failed.is_set(), "Second transaction should have failed with LOCK_BUSY"

    def test_lock_released_on_exception(self, tmp_path):
        """Lock is properly released when transaction raises an exception."""
        paths = _make_paths(tmp_path)
        lock_path = paths.transaction_lock.path

        with pytest.raises(RuntimeError):
            with transaction(paths) as txn:
                raise RuntimeError("boom")

        # Verify lock is released
        fd = os.open(str(lock_path), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pytest.fail("Lock was not released after exception")
        finally:
            os.close(fd)


class TestTransactionRollbackRetention:
    def test_retention_limit_enforced(self, tmp_path):
        """Creating more than retention limit prunes old snapshots."""
        from ainews_config.transaction import MAX_ROLLBACKS

        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("key: initial\n")

        # Create more transactions than the retention limit
        for i in range(MAX_ROLLBACKS + 5):
            with transaction(paths) as txn:
                txn.modify_file(target, f"key: value_{i}\n".encode())

        manifests = list_rollbacks(paths.backup_dir.path)
        assert len(manifests) == MAX_ROLLBACKS

    def test_newest_snapshot_preserved_after_pruning(self, tmp_path):
        """After pruning, the newest rollback is still available."""
        from ainews_config.transaction import MAX_ROLLBACKS

        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("key: initial\n")

        for i in range(MAX_ROLLBACKS + 3):
            with transaction(paths) as txn:
                txn.modify_file(target, f"key: value_{i}\n".encode())

        manifests = list_rollbacks(paths.backup_dir.path)
        assert len(manifests) == MAX_ROLLBACKS

        # Restore the most recent rollback — it restores the state before that transaction
        latest = manifests[-1]
        assert latest.transaction_id.startswith("txn-")
        restore_rollback(paths.backup_dir.path, latest.transaction_id, paths)

        # The restored content should be a valid previous state (not the current state)
        restored = target.read_text()
        assert restored.startswith("key: value_")
        assert restored != "key: initial\n"  # Should not be the very first state

    def test_rollback_created_per_transaction(self, tmp_path):
        """Each committed transaction creates exactly one rollback."""
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("key: v0\n")

        for i in range(3):
            with transaction(paths) as txn:
                txn.modify_file(target, f"key: v{i + 1}\n".encode())

        manifests = list_rollbacks(paths.backup_dir.path)
        assert len(manifests) == 3

        # Each rollback has unique transaction ID
        ids = [m.transaction_id for m in manifests]
        assert len(set(ids)) == 3

    def test_prune_preserves_rollback_content(self, tmp_path):
        """Pruning old rollbacks does not corrupt the remaining ones."""
        from ainews_config.transaction import MAX_ROLLBACKS

        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("key: v0\n")

        for i in range(MAX_ROLLBACKS + 2):
            with transaction(paths) as txn:
                txn.modify_file(target, f"key: v{i + 1}\n".encode())

        manifests = list_rollbacks(paths.backup_dir.path)

        # Each remaining rollback directory should contain a valid manifest
        for manifest in manifests:
            rollback_dir = Path(manifest.rollback_path)
            assert rollback_dir.exists()
            assert (rollback_dir / "manifest.json").exists()

    def test_rollback_manifest_content(self, tmp_path):
        """Rollback manifest contains correct metadata."""
        paths = _make_paths(tmp_path)
        target = tmp_path / "providers.yaml"
        target.write_text("key: original\n")

        with transaction(paths) as txn:
            txn.modify_file(target, b"key: modified\n")

        manifests = list_rollbacks(paths.backup_dir.path)
        assert len(manifests) == 1

        manifest = manifests[0]
        assert manifest.transaction_id.startswith("txn-")
        assert len(manifest.files_changed) == 1
        assert manifest.rollback_path != ""
        assert manifest.created_at != ""

        # Verify rollback directory contains the original content
        rollback_dir = Path(manifest.rollback_path)
        assert rollback_dir.exists()

        # Find the rollback file (named by hash of original path)
        rollback_files = [f for f in rollback_dir.iterdir() if f.name != "manifest.json"]
        assert len(rollback_files) == 1

        original_content = rollback_files[0].read_bytes()
        assert original_content == b"key: original\n"

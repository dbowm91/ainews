import gzip
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

VERIFY_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_backup.sh"

REQUIRED_TABLES = ["articles", "sources", "tags", "subscribers", "newsletters"]

requires_sqlite3_cli = pytest.mark.skipif(
    shutil.which("sqlite3") is None,
    reason="sqlite3 CLI not installed",
)


def _create_db(path: Path, tables: list[str] | None = None):
    if tables is None:
        tables = REQUIRED_TABLES
    conn = sqlite3.connect(str(path))
    for table in tables:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def run_verify(path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(VERIFY_SCRIPT), path],
        capture_output=True,
        text=True,
    )


@requires_sqlite3_cli
class TestVerifyBackupValid:
    def test_valid_database(self, tmp_path):
        db_path = tmp_path / "backup.db"
        _create_db(db_path)
        result = run_verify(str(db_path))
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_valid_gzipped_database(self, tmp_path):
        db_path = tmp_path / "backup.db"
        _create_db(db_path)
        gz_path = tmp_path / "backup.db.gz"
        with open(db_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            f_out.write(f_in.read())
        result = run_verify(str(gz_path))
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestVerifyBackupInvalid:
    def test_no_arguments(self, tmp_path):
        result = subprocess.run(
            ["bash", str(VERIFY_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Usage" in result.stdout

    def test_nonexistent_file(self, tmp_path):
        result = run_verify(str(tmp_path / "nonexistent.db"))
        assert result.returncode != 0

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.db"
        empty.touch()
        result = run_verify(str(empty))
        assert result.returncode != 0
        assert "FAIL" in result.stdout

    @requires_sqlite3_cli
    def test_corrupt_database(self, tmp_path):
        bad = tmp_path / "corrupt.db"
        bad.write_bytes(b"not a sqlite database at all")
        result = run_verify(str(bad))
        assert result.returncode != 0
        assert "FAIL" in result.stdout

    @requires_sqlite3_cli
    def test_missing_required_table(self, tmp_path):
        db_path = tmp_path / "partial.db"
        _create_db(db_path, tables=["articles", "sources"])
        result = run_verify(str(db_path))
        assert result.returncode != 0
        assert "FAIL" in result.stdout

    @requires_sqlite3_cli
    def test_corrupt_gzipped_database(self, tmp_path):
        gz_path = tmp_path / "corrupt.db.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(b"not a sqlite database")
        result = run_verify(str(gz_path))
        assert result.returncode != 0
        assert "FAIL" in result.stdout

from __future__ import annotations

import fcntl
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MIGRATION_LOCK_FILE = "migration.lock"


def _run_flask_command(
    args: list[str],
    paths: Any,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": str(Path(sys.executable).parent) + ":" + (subprocess.os.environ.get("PATH", "")),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    flask_app = str(paths.app_dir.path / "run.py")
    env["FLASK_APP"] = flask_app

    db_url = paths.database_file.path
    if db_url.exists():
        env["DATABASE_URL"] = f"sqlite:///{db_url}"

    cmd = [sys.executable, "-m", "flask"] + args
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(paths.app_dir.path),
            env={**subprocess.os.environ, **env},
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
        )
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"Flask not found: {e}",
        )


def detect_pending_migrations(paths: Any) -> dict[str, Any]:
    current = _run_flask_command(["db", "current"], paths, timeout=30)
    heads = _run_flask_command(["db", "heads"], paths, timeout=30)

    current_rev = current.stdout.strip().splitlines()[-1].strip() if current.returncode == 0 else None
    head_revs = [
        line.strip()
        for line in heads.stdout.strip().splitlines()
        if line.strip() and not line.startswith("=")
    ] if heads.returncode == 0 else []

    pending = max(0, len(head_revs) - (1 if current_rev else 0))
    if current_rev and current_rev in head_revs:
        pending = 0

    return {
        "current_revision": current_rev,
        "head_revisions": head_revs,
        "pending_count": pending,
        "error": None if current.returncode == 0 else current.stderr.strip(),
    }


def run_migrations(paths: Any, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        result = _run_flask_command(["db", "history", "--sql"], paths, timeout=30)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    lock_path = paths.state_dir.path / _MIGRATION_LOCK_FILE
    lock_fd = None
    try:
        lock_fd = open(lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as e:
        if lock_fd:
            lock_fd.close()
        return {
            "success": False,
            "output": "",
            "error": f"Another migration is in progress: {e}",
        }

    try:
        result = _run_flask_command(["db", "upgrade"], paths, timeout=120)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except OSError:
            pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def get_migration_status(paths: Any) -> dict[str, Any]:
    status = detect_pending_migrations(paths)
    return {
        "current_revision": status["current_revision"],
        "head_revisions": status["head_revisions"],
        "pending_count": status["pending_count"],
        "needs_migration": status["pending_count"] > 0,
        "error": status["error"],
    }


def check_migration_lock(paths: Any) -> dict[str, Any]:
    lock_path = paths.state_dir.path / _MIGRATION_LOCK_FILE
    if not lock_path.exists():
        return {"locked": False, "pid": None}

    try:
        lock_fd = open(lock_path, "r")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            return {"locked": False, "pid": None}
        except BlockingIOError:
            lock_fd.close()
            return {"locked": True, "pid": None}
    except OSError:
        return {"locked": False, "pid": None}

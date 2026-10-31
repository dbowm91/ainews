"""Development services must share the web process lifetime."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from scripts import dev_supervisor


def test_supervisor_pid_dir_can_be_isolated_in_environment(tmp_path):
    env = os.environ.copy()
    env["AINEWS_DEV_PID_DIR"] = str(tmp_path / "isolated-pids")
    result = subprocess.run(
        [sys.executable, "-c", "from scripts.dev_supervisor import PID_DIR; print(PID_DIR)"],
        cwd=dev_supervisor.ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == str(tmp_path / "isolated-pids")


def test_web_exit_stops_worker_and_beat_process_groups(tmp_path, monkeypatch):
    children: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def capture_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(dev_supervisor.subprocess, "Popen", capture_popen)
    commands = {
        "web": [sys.executable, "-c", "import time; time.sleep(0.6)"],
        "celery-worker": [sys.executable, "-c", "import time; time.sleep(30)"],
        "celery-beat": [sys.executable, "-c", "import time; time.sleep(30)"],
    }

    result = dev_supervisor.supervise(
        commands, pid_dir=tmp_path, poll_interval=0.05, stop_timeout=1,
    )

    assert result == 1
    assert len(children) == 3
    assert all(child.poll() is not None for child in children)
    assert not list(tmp_path.glob("*.pid"))


def test_supervisor_shutdown_stops_all_process_groups(tmp_path):
    code = """
from pathlib import Path
import sys
from scripts.dev_supervisor import supervise
py = sys.executable
commands = {name: [py, '-c', 'import time; time.sleep(30)']
            for name in ('web', 'celery-worker', 'celery-beat')}
supervise(commands, pid_dir=Path(sys.argv[1]), poll_interval=0.05, stop_timeout=1)
"""
    supervisor = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], cwd=dev_supervisor.ROOT)
    child_pids: list[int] = []
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        pid_files = list(tmp_path.glob("*.pid"))
        if len(pid_files) == 3:
            child_pids = [int(path.read_text()) for path in pid_files]
            break
        if supervisor.poll() is not None:
            raise AssertionError(f"supervisor exited early with {supervisor.returncode}")
        time.sleep(0.05)
    assert len(child_pids) == 3

    supervisor.send_signal(signal.SIGTERM)
    assert supervisor.wait(timeout=10) == 0
    assert all(not dev_supervisor._pid_is_running(pid) for pid in child_pids)
    assert not list(tmp_path.glob("*.pid"))


def test_worker_and_beat_units_are_bound_to_web_lifetime():
    from unittest.mock import MagicMock, patch

    from ainews_cli.service.systemd import (
        build_celery_beat_unit,
        build_celery_worker_unit,
        build_web_unit,
        render_unit,
    )

    paths = MagicMock()
    paths.app_dir.path = "/opt/ainews"
    paths.state_dir.path = "/var/lib/ainews"
    with patch("ainews_cli.service.systemd._find_cli_executable", return_value="/opt/ainews/.venv/bin/ainews"):
        web = build_web_unit(paths)
        worker = build_celery_worker_unit(paths)
        beat = build_celery_beat_unit(paths)

    assert set(web.wants) == {"ainews-celery-worker.service", "ainews-celery-beat.service"}
    assert worker.binds_to == ["ainews-web.service"]
    assert beat.binds_to == ["ainews-web.service"]
    assert "-m celery" in worker.exec_start and "--component" not in worker.exec_start
    assert "-m celery" in beat.exec_start and "--component" not in beat.exec_start
    assert "BindsTo=ainews-web.service" in render_unit(worker).content
    assert "BindsTo=ainews-web.service" in render_unit(beat).content

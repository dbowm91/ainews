#!/usr/bin/env python3
"""Keep the local web server, Celery worker and Beat in one managed lifecycle."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PID_DIR = ROOT / ".pids"
SUPERVISOR_PID = PID_DIR / "dev-supervisor.pid"
LOCK_FILE = PID_DIR / "dev-supervisor.lock"
SERVICE_NAMES = ("web", "celery-worker", "celery-beat")
STOP_REQUESTED = False


def _commands(python: str | None = None) -> dict[str, list[str]]:
    python = python or sys.executable
    return {
        "web": [python, "-m", "flask", "run", "--no-reload", "--port", "5000"],
        "celery-worker": [python, "-m", "celery", "-A", "celery_app:celery_app", "worker", "-l", "info", "--concurrency=2"],
        "celery-beat": [python, "-m", "celery", "-A", "celery_app:celery_app", "beat", "-l", "info", f"--schedule={PID_DIR / 'celerybeat-schedule'}"],
    }


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def _stop_process_group(process: subprocess.Popen, timeout: float) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def supervise(
    commands: dict[str, list[str]] | None = None,
    *,
    pid_dir: Path = PID_DIR,
    poll_interval: float = 0.25,
    stop_timeout: float = 5,
) -> int:
    """Run all local services and tear down every sibling if one exits."""
    global STOP_REQUESTED
    STOP_REQUESTED = False
    pid_dir.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    children: dict[str, subprocess.Popen] = {}
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    command_map = commands or _commands()
    result = 0
    try:
        for name in SERVICE_NAMES:
            log = (pid_dir / f"{name}.log").open("a", encoding="utf-8")
            try:
                children[name] = subprocess.Popen(
                    command_map[name], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                )
            finally:
                log.close()
            (pid_dir / f"{name}.pid").write_text(str(children[name].pid), encoding="ascii")

        while not STOP_REQUESTED:
            for name, child in children.items():
                code = child.poll()
                if code is not None:
                    print(f"{name} exited with status {code}; stopping remaining services", flush=True)
                    result = 1
                    return result
            time.sleep(poll_interval)
    except (OSError, KeyError) as exc:
        print(f"Could not start local services: {exc}", file=sys.stderr, flush=True)
        result = 1
    finally:
        for name in reversed(SERVICE_NAMES):
            process = children.get(name)
            if process is not None:
                _stop_process_group(process, stop_timeout)
            try:
                (pid_dir / f"{name}.pid").unlink()
            except FileNotFoundError:
                pass
        try:
            (pid_dir / "dev-supervisor.pid").unlink()
        except FileNotFoundError:
            pass
    return result


def start() -> int:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    lock = LOCK_FILE.open("a+")
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Development services are already managed by a supervisor.")
            return 0
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "supervise", str(lock.fileno())],
            cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=(PID_DIR / "dev-supervisor.log").open("ab"),
            stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(lock.fileno(),),
        )
        (PID_DIR / "dev-supervisor.pid").write_text(str(proc.pid), encoding="ascii")
        print(f"Development services supervisor started (PID {proc.pid}).")
        return 0
    finally:
        lock.close()


def stop() -> int:
    pid = _read_pid(SUPERVISOR_PID)
    if pid is None or not _pid_is_running(pid):
        try:
            SUPERVISOR_PID.unlink()
        except FileNotFoundError:
            pass
        print("Development services are stopped.")
        return 0
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and _pid_is_running(pid):
        time.sleep(0.2)
    if _pid_is_running(pid):
        print("Supervisor did not stop within 20 seconds; refusing to kill it and orphan its children.", file=sys.stderr)
        return 1
    print("Development services stopped.")
    return 0


def status() -> int:
    pid = _read_pid(SUPERVISOR_PID)
    if pid is None or not _pid_is_running(pid):
        print("Development services supervisor is stopped.")
        return 1
    print(f"Development services supervisor is running (PID {pid}).")
    for name in SERVICE_NAMES:
        child_pid = _read_pid(PID_DIR / f"{name}.pid")
        state = "running" if child_pid is not None and _pid_is_running(child_pid) else "stopped"
        print(f"  {state}: {name}" + (f" (PID {child_pid})" if child_pid else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "status"
    if command == "start":
        return start()
    if command == "stop":
        return stop()
    if command == "status":
        return status()
    if command == "supervise" and len(args) == 2:
        # The inherited lock descriptor prevents two concurrent start requests
        # from creating competing worker/Beat trees.
        int(args[1])
        return supervise()
    print("Usage: dev_supervisor.py [start|stop|status]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Keep the local web server, Celery worker and Beat in one managed lifecycle."""
from __future__ import annotations

import fcntl
import http.client
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
from urllib.parse import quote, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
PID_DIR = Path(os.environ.get("AINEWS_DEV_PID_DIR", ROOT / ".pids")).expanduser().resolve()
SUPERVISOR_PID = PID_DIR / "dev-supervisor.pid"
LOCK_FILE = PID_DIR / "dev-supervisor.lock"
SERVICE_NAMES = ("web", "celery-worker", "celery-beat")
STOP_REQUESTED = False


def _commands(python: str | None = None, port: str = "5000") -> dict[str, list[str]]:
    python = python or sys.executable
    return {
        "web": [python, "-m", "flask", "run", "--no-reload", "--port", port],
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


def _load_environment() -> dict[str, str]:
    """Load .env values for the supervisor, leaving shell values authoritative."""
    env = os.environ.copy()
    try:
        from dotenv import dotenv_values

        for key, value in dotenv_values(ROOT / ".env").items():
            if value is not None:
                env.setdefault(key, value)
    except ImportError:
        pass
    env["PYTHONUNBUFFERED"] = "1"
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _redis_urls(env: dict[str, str]) -> list[str]:
    broker_url = env.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    urls = [
        broker_url,
        env.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    ]
    redis_url = env.get("REDIS_URL")
    if redis_url:
        urls.append(redis_url)
    config_cache_url = env.get("CONFIG_CACHE_REDIS_URL") or broker_url.replace("/0", "/1").replace("/2", "/1")
    urls.append(config_cache_url)
    redis_password = env.get("REDIS_PASSWORD")
    config_password = redis_password or env.get("CONFIG_CACHE_REDIS_PASSWORD")
    authenticated: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        password = config_password if url == config_cache_url else redis_password
        if password and not parsed.password and parsed.hostname:
            username = f"{quote(parsed.username, safe='')}:" if parsed.username else ":"
            netloc = f"{username}{quote(password, safe='')}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            url = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        authenticated.append(url)
    return list(dict.fromkeys(authenticated))


def _redis_reachable(url: str) -> bool:
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("The Python Redis client is not installed; install the project dependencies before starting development services.") from exc

    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except (redis.RedisError, OSError, ValueError):
        return False


def _start_local_redis(env: dict[str, str], pid_dir: Path) -> subprocess.Popen:
    urls = _redis_urls(env)
    parsed = [urlparse(url) for url in urls]
    endpoints = {(item.scheme, item.hostname, item.port or 6379) for item in parsed}
    if len(endpoints) != 1:
        raise RuntimeError("Configured Redis URLs are not all the same endpoint; start each configured Redis service manually.")
    scheme, host, port = next(iter(endpoints))
    has_password = any(item.password or item.username for item in parsed) or bool(
        env.get("REDIS_PASSWORD") or env.get("CONFIG_CACHE_REDIS_PASSWORD")
    )
    if scheme != "redis" or host not in {"localhost", "127.0.0.1", "::1"} or has_password:
        raise RuntimeError("Configured Redis is unreachable and is not an unauthenticated local redis:// endpoint; start it manually or correct the Redis URL.")

    server = env.get("REDIS_SERVER_BIN") or shutil.which("redis-server")
    if not server:
        raise RuntimeError("Redis is unreachable and redis-server is not installed or on PATH. Install Redis or configure a reachable Redis endpoint.")

    bind_host = "::1" if host == "::1" else "127.0.0.1"
    command = [server, "--bind", bind_host, "--port", str(port), "--save", "", "--appendonly", "no"]
    log = (pid_dir / "redis.log").open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()
    (pid_dir / "redis.pid").write_text(str(process.pid), encoding="ascii")

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"redis-server exited with status {process.returncode}; see {pid_dir / 'redis.log'}.")
        if all(_redis_reachable(url) for url in urls):
            return process
        time.sleep(0.2)
    _stop_process_group(process, 2)
    try:
        (pid_dir / "redis.pid").unlink()
    except FileNotFoundError:
        pass
    raise RuntimeError(f"redis-server did not become ready; see {pid_dir / 'redis.log'}.")


def _prepare_redis(env: dict[str, str], pid_dir: Path) -> subprocess.Popen | None:
    urls = _redis_urls(env)
    if all(_redis_reachable(url) for url in urls):
        (pid_dir / "redis.mode").write_text("reused", encoding="ascii")
        try:
            (pid_dir / "redis.pid").unlink()
        except FileNotFoundError:
            pass
        print("Redis is already reachable; reusing the configured service.", flush=True)
        return None
    process = _start_local_redis(env, pid_dir)
    (pid_dir / "redis.mode").write_text("managed", encoding="ascii")
    print(f"Started local Redis (PID {process.pid}); it will stop with the development services.", flush=True)
    return process


def _wait_for_web_ready(process: subprocess.Popen, port: str, timeout: float = 60) -> None:
    """Wait for Flask initialization to finish before Celery opens the DB."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"web exited with status {process.returncode} before becoming ready.")
        connection = http.client.HTTPConnection("127.0.0.1", int(port), timeout=5)
        try:
            connection.request("GET", "/health")
            if connection.getresponse().status < 500:
                return
        except (OSError, http.client.HTTPException, ValueError):
            pass
        finally:
            connection.close()
        time.sleep(0.25)
    raise RuntimeError(f"web did not become healthy within {timeout:g} seconds; see {PID_DIR / 'web.log'}.")


def _launch_service(name: str, command: list[str], env: dict[str, str], pid_dir: Path) -> subprocess.Popen:
    log = (pid_dir / f"{name}.log").open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()
    (pid_dir / f"{name}.pid").write_text(str(process.pid), encoding="ascii")
    return process


def _start_children(
    children: dict[str, subprocess.Popen],
    command_map: dict[str, list[str]],
    env: dict[str, str],
    pid_dir: Path,
    *,
    manage_redis: bool,
) -> None:
    if manage_redis:
        redis_child = _prepare_redis(env, pid_dir)
        if redis_child is not None:
            children["redis"] = redis_child
    for name in SERVICE_NAMES:
        children[name] = _launch_service(name, command_map[name], env, pid_dir)
        if manage_redis and name == "web":
            _wait_for_web_ready(children[name], env.get("DEV_WEB_PORT", "5000"))


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
    env = _load_environment()
    command_map = commands or _commands(port=env.get("DEV_WEB_PORT", "5000"))
    result = 0
    try:
        _start_children(children, command_map, env, pid_dir, manage_redis=commands is None)

        while not STOP_REQUESTED:
            for name, child in children.items():
                code = child.poll()
                if code is not None:
                    print(f"{name} exited with status {code}; stopping remaining services", flush=True)
                    result = 1
                    return result
            time.sleep(poll_interval)
    except (OSError, KeyError, ValueError) as exc:
        print(f"Could not start local services: {exc}", file=sys.stderr, flush=True)
        result = 1
    except RuntimeError as exc:
        print(f"Could not start managed services: {exc}", file=sys.stderr, flush=True)
        result = 1
    finally:
        for name in (*reversed(SERVICE_NAMES), "redis"):
            process = children.get(name)
            if process is not None:
                _stop_process_group(process, stop_timeout)
            try:
                (pid_dir / f"{name}.pid").unlink()
            except FileNotFoundError:
                pass
        try:
            (pid_dir / "redis.mode").unlink()
        except FileNotFoundError:
            pass
        try:
            (pid_dir / "redis.pid").unlink()
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
    mode_path = PID_DIR / "redis.mode"
    mode = mode_path.read_text(encoding="ascii").strip() if mode_path.exists() else "unknown"
    if mode == "managed":
        redis_pid = _read_pid(PID_DIR / "redis.pid")
        print("  running: redis (managed by supervisor)" + (f" (PID {redis_pid})" if redis_pid else ""))
    elif mode == "reused":
        print("  running: redis (reusing configured service)")
    else:
        print("  unknown: redis")
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

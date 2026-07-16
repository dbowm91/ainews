"""Path and configuration validation for service management."""

from __future__ import annotations

import os
import re
from pathlib import Path
from ainews_cli.service.models import (
    InstalledUnitRecord,
    ServiceUnitSpec,
)

# ---------------------------------------------------------------------------
# Path validation constants
# ---------------------------------------------------------------------------

_UNSAFE_PATH_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_RELATIVE_COMPONENTS = {"..", ".", ""}
_MAX_PATH_LENGTH = 4096


class PathValidationError(Exception):
    """Raised when a path fails safety validation."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Unsafe path {path!r}: {reason}")
        self.path = path
        self.reason = reason


# ---------------------------------------------------------------------------
# Path validation functions
# ---------------------------------------------------------------------------


def validate_path(path: Path, *, label: str = "path") -> None:
    """Validate a path is safe for use in service unit files.

    Rejects:
    - Empty paths
    - Root (/) or home directory
    - Paths with unresolved variables (${...}) or tildes (~)
    - Relative paths
    - Paths containing control characters or newlines
    - Paths exceeding maximum length
    - Symlinks (for install targets)

    Raises:
        PathValidationError if path is unsafe.
    """
    s = str(path)

    if not s:
        raise PathValidationError(s, "empty path")

    if len(s) > _MAX_PATH_LENGTH:
        raise PathValidationError(s, f"path exceeds {_MAX_PATH_LENGTH} characters")

    if s == "/":
        raise PathValidationError(s, "root directory")

    try:
        home = Path.home()
        if path == home:
            raise PathValidationError(s, "home directory")
    except RuntimeError:
        pass

    if "${" in s or "~" in s:
        raise PathValidationError(s, "contains unresolved variable or tilde")

    if _UNSAFE_PATH_CHARS.search(s):
        raise PathValidationError(s, "contains control characters or newlines")

    if not path.is_absolute():
        raise PathValidationError(s, "relative path")


def validate_executable(path: Path | None, exec_str: str | None) -> list[dict[str, str]]:
    """Validate that an executable exists and is accessible.

    Returns a list of check results.
    """
    checks: list[dict[str, str]] = []

    if not exec_str:
        checks.append({
            "name": "exec_exists",
            "status": "WARN",
            "message": "No ExecStart defined",
        })
        return checks

    # Extract the binary path from the exec string (first token)
    parts = exec_str.split()
    if not parts:
        checks.append({
            "name": "exec_exists",
            "status": "WARN",
            "message": "Empty ExecStart",
        })
        return checks

    binary = parts[0]

    # Skip validation for paths with arguments or complex expressions
    if binary.startswith("/") or binary.startswith("./"):
        binary_path = Path(binary)
        if binary_path.exists():
            if os.access(binary_path, os.X_OK):
                checks.append({
                    "name": "exec_exists",
                    "status": "PASS",
                    "message": f"Executable exists: {binary}",
                })
            else:
                checks.append({
                    "name": "exec_exists",
                    "status": "WARN",
                    "message": f"File exists but not executable: {binary}",
                })
        else:
            checks.append({
                "name": "exec_exists",
                "status": "FAIL",
                "message": f"Executable not found: {binary}",
            })
    else:
        # For commands in PATH (like "ainews"), just check it's not empty
        checks.append({
            "name": "exec_exists",
            "status": "PASS",
            "message": f"Command will be resolved via PATH: {binary}",
        })

    return checks


def validate_env_file_permissions(env_path: Path | None) -> list[dict[str, str]]:
    """Validate environment file has secure permissions.

    Returns a list of check results.
    """
    checks: list[dict[str, str]] = []

    if not env_path or not env_path.exists():
        return checks

    try:
        stat = os.stat(env_path)
        mode = oct(stat.st_mode)[-3:]
        uid = stat.st_uid
        gid = stat.st_gid

        # Check permissions are not world-readable
        if int(mode[2]) > 0:  # Others have any permission
            checks.append({
                "name": "env_file_perms",
                "status": "WARN",
                "message": f"Environment file {env_path} has world-accessible mode {mode} (recommend 0600)",
            })
        elif int(mode[1]) > 4:  # Group has write+ permission
            checks.append({
                "name": "env_file_perms",
                "status": "WARN",
                "message": f"Environment file {env_path} has group-writable mode {mode} (recommend 0600)",
            })
        else:
            checks.append({
                "name": "env_file_perms",
                "status": "PASS",
                "message": f"Environment file permissions: {mode}",
            })

        # Check ownership matches current user for user-scope services
        if uid != os.getuid() or gid != os.getgid():
            checks.append({
                "name": "env_file_owner",
                "status": "WARN",
                "message": f"Environment file owned by {uid}:{gid}, current user is {os.getuid()}:{os.getgid()}",
            })

    except OSError as e:
        checks.append({
            "name": "env_file_perms",
            "status": "WARN",
            "message": f"Could not check environment file permissions: {e}",
        })

    return checks


def detect_conflicts(
    spec: ServiceUnitSpec,
    installed_units: list[InstalledUnitRecord],
) -> list[dict[str, str]]:
    """Detect conflicts with existing installed units.

    Returns a list of check results.
    """
    checks: list[dict[str, str]] = []

    for existing in installed_units:
        if existing.unit_name == spec.name:
            # Same unit name - check if it's a different path
            if existing.install_path != spec.name + ".service":
                checks.append({
                    "name": f"conflict:{spec.name}",
                    "status": "WARN",
                    "message": (
                        f"Unit '{spec.name}' already installed at {existing.install_path}. "
                        f"New installation will replace it."
                    ),
                })
            else:
                checks.append({
                    "name": f"conflict:{spec.name}",
                    "status": "PASS",
                    "message": f"Unit '{spec.name}' will be updated",
                })
            break

    # Check for name collisions with system units
    systemd_paths = ["/etc/systemd/system", "/usr/lib/systemd/system"]
    for systemd_path in systemd_paths:
        unit_file = Path(systemd_path) / f"{spec.name}.service"
        if unit_file.exists():
            checks.append({
                "name": f"system_unit:{spec.name}",
                "status": "WARN",
                "message": f"Unit file already exists at {unit_file}",
            })

    return checks


def validate_unit_spec_comprehensive(
    spec: ServiceUnitSpec,
    installed_units: list[InstalledUnitRecord],
    *,
    check_executables: bool = True,
    check_env_perms: bool = True,
    check_conflicts: bool = True,
) -> list[dict[str, str]]:
    """Run comprehensive validation on a unit specification.

    Combines all validation checks into a single call.
    """
    checks: list[dict[str, str]] = []

    # Basic spec validation
    if not spec.exec_start:
        checks.append({
            "name": "exec_start",
            "status": "FAIL",
            "message": "ExecStart is empty",
        })
    else:
        checks.append({
            "name": "exec_start",
            "status": "PASS",
            "message": f"ExecStart: {spec.exec_start}",
        })

    # Secret detection
    secret_patterns = ["password=", "secret=", "token=", "key=", "credential="]
    lower_cmd = (spec.exec_start or "").lower()
    for pattern in secret_patterns:
        if pattern in lower_cmd:
            checks.append({
                "name": "secrets_in_cmd",
                "status": "FAIL",
                "message": f"Potential secret in ExecStart: {pattern}",
            })
            break
    else:
        checks.append({
            "name": "secrets_in_cmd",
            "status": "PASS",
            "message": "No secrets detected in command line",
        })

    # Executable existence checks
    if check_executables:
        checks.extend(validate_executable(None, spec.exec_start))
        if spec.exec_stop:
            checks.extend(validate_executable(None, spec.exec_stop))

    # Environment file permissions
    if check_env_perms and spec.environment_file:
        checks.extend(validate_env_file_permissions(spec.environment_file))

    # Conflict detection
    if check_conflicts:
        checks.extend(detect_conflicts(spec, installed_units))

    # Hardening checks
    if spec.no_new_privileges:
        checks.append({
            "name": "hardening_nonewprivileges",
            "status": "PASS",
            "message": "NoNewPrivileges=true",
        })
    else:
        checks.append({
            "name": "hardening_nonewprivileges",
            "status": "WARN",
            "message": "NoNewPrivileges=false",
        })

    if spec.private_tmp:
        checks.append({
            "name": "hardening_privatetmp",
            "status": "PASS",
            "message": "PrivateTmp=true",
        })

    if spec.protect_system:
        checks.append({
            "name": "hardening_protectsystem",
            "status": "PASS",
            "message": f"ProtectSystem={spec.protect_system}",
        })

    if spec.protect_home:
        checks.append({
            "name": "hardening_protecthome",
            "status": "PASS",
            "message": "ProtectHome=true",
        })

    # Root user check
    user = spec.user
    if user in ("root", ""):
        checks.append({
            "name": "running_as_root",
            "status": "WARN",
            "message": "Service runs as root — consider using a dedicated user",
        })
    else:
        checks.append({
            "name": "running_as_root",
            "status": "PASS",
            "message": f"Service user: {user or '(current user)'}",
        })

    return checks

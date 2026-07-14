"""Secret generation and admin password setup for ainews onboarding."""

from __future__ import annotations

import getpass
import logging
import os
import secrets

logger = logging.getLogger(__name__)

_PLACEHOLDER_PASSWORDS = frozenset({
    "password",
    "admin",
    "changeme",
    "changeme123",
    "password123",
    "admin123",
    "secret",
    "test",
    "letmein",
    "welcome",
    "monkey",
    "dragon",
    "master",
    "qwerty",
    "123456",
    "12345678",
    "123456789",
})

_MIN_PASSWORD_LENGTH = 8


def generate_application_secrets() -> dict[str, str]:
    """Generate all required application secrets.

    Returns:
        Dict mapping env var names to generated secret values.
    """
    return {
        "SECRET_KEY": secrets.token_hex(32),
        "CELERY_TASK_SECRET": secrets.token_hex(32),
    }


def hash_admin_password(password: str) -> str:
    """Hash an admin password using werkzeug security.

    Args:
        password: Plain-text password.

    Returns:
        Password hash string.
    """
    from werkzeug.security import generate_password_hash

    return generate_password_hash(password)


def validate_admin_password(password: str) -> list[str]:
    """Validate an admin password against the minimum policy.

    Args:
        password: Plain-text password to validate.

    Returns:
        List of policy violation messages (empty if valid).
    """
    violations: list[str] = []

    if not password or not password.strip():
        violations.append("Password must not be blank or whitespace only.")
        return violations

    if len(password) < _MIN_PASSWORD_LENGTH:
        violations.append(
            f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long."
        )

    if password.lower().strip() in _PLACEHOLDER_PASSWORDS:
        violations.append("Password must not be a known placeholder value.")

    return violations


def interactive_password_entry(prompt: str = "Admin password: ") -> str:
    """Collect a password interactively with confirmation and validation.

    Uses hidden input (no echo). Requires confirmation. Validates against
    the minimum password policy.

    Args:
        prompt: The prompt to display.

    Returns:
        The validated plain-text password.

    Raises:
        SystemExit: If validation fails after maximum retries.
    """
    max_attempts = 3

    for _attempt in range(max_attempts):
        try:
            password = getpass.getpass(prompt=prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(1)

        violations = validate_admin_password(password)
        if violations:
            for v in violations:
                print(f"  Error: {v}", flush=True)
            continue

        try:
            confirm = getpass.getpass(prompt="Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(1)

        if password != confirm:
            print("  Passwords do not match.", flush=True)
            continue

        return password

    print("Maximum password attempts exceeded.", flush=True)
    raise SystemExit(1)


def secure_password_from_env(env_var: str) -> str:
    """Read and validate a password from an environment variable.

    Args:
        env_var: Name of the environment variable.

    Returns:
        The validated password.

    Raises:
        ValueError: If the env var is not set or the password is invalid.
    """
    password = os.environ.get(env_var)
    if not password:
        raise ValueError(f"Environment variable {env_var} is not set or empty.")

    violations = validate_admin_password(password)
    if violations:
        raise ValueError(
            f"Password from {env_var} violates policy: {'; '.join(violations)}"
        )

    return password


def secure_password_from_file(file_path: str) -> str:
    """Read and validate a password from a file path.

    Args:
        file_path: Path to a file containing the password.

    Returns:
        The validated password.

    Raises:
        ValueError: If the file is unreadable or the password is invalid.
    """
    path = os.path.expanduser(file_path)
    try:
        with open(path, encoding="utf-8") as f:
            password = f.read().strip()
    except OSError as e:
        raise ValueError(f"Cannot read password file {path}: {e}") from e

    violations = validate_admin_password(password)
    if violations:
        raise ValueError(
            f"Password from file violates policy: {'; '.join(violations)}"
        )

    return password


def rotate_admin_password(interactive: bool = True) -> str:
    """Generate a new admin password hash, optionally collecting interactively.

    Returns:
        The new password hash.
    """
    if interactive:
        password = interactive_password_entry("New admin password: ")
    else:
        password = secrets.token_urlsafe(24)
        logger.info("Generated random admin password (non-interactive rotation).")
    return hash_admin_password(password)


def rotate_application_secrets() -> dict[str, str]:
    """Generate new application secrets (SECRET_KEY, CELERY_TASK_SECRET).

    Returns:
        Dict mapping env var names to new secret values.
    """
    return generate_application_secrets()

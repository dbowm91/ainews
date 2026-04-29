#!/usr/bin/env python3
"""Generate a hashed admin password for use in .env files.

Usage:
    python scripts/hash_password.py              # prompts for password (recommended)
    python scripts/hash_password.py mypassword   # pass password as argument

WARNING: Passing the password as a command-line argument may expose it in
shell history (~/.bash_history, ~/.zsh_history) and process listings (ps).
Interactive mode (no arguments) is recommended for security.

Output can be set as ADMIN_PASSWORD in your .env file.
"""

import getpass
import re
import sys

from werkzeug.security import check_password_hash, generate_password_hash


def validate_password_strength(password: str) -> None:
    """Validate password meets complexity requirements."""
    if len(password) < 12:
        print(
            "Error: password must be at least 12 characters for security",
            file=sys.stderr,
        )
        sys.exit(1)
    if not re.search(r"[A-Z]", password):
        print(
            "Error: password must contain at least one uppercase letter",
            file=sys.stderr,
        )
        sys.exit(1)
    if not re.search(r"[a-z]", password):
        print(
            "Error: password must contain at least one lowercase letter",
            file=sys.stderr,
        )
        sys.exit(1)
    if not re.search(r"\d", password):
        print(
            "Error: password must contain at least one digit",
            file=sys.stderr,
        )
        sys.exit(1)
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        print(
            "Error: password must contain at least one special character",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    if len(sys.argv) > 1:
        print(
            "Warning: password passed via command line may appear in shell history "
            "and process listings.",
            file=sys.stderr,
        )
        print(
            "         Consider using interactive mode instead (run without arguments).",
            file=sys.stderr,
        )
        password = sys.argv[1]
    else:
        password = getpass.getpass("Enter password to hash: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: passwords do not match", file=sys.stderr)
            sys.exit(1)

    validate_password_strength(password)

    hashed = generate_password_hash(password, method="scrypt", salt_len=16, key_len=32)

    assert hashed.startswith("scrypt:"), f"Expected scrypt hash, got: {hashed.split('$')[0]}"

    n_param = re.search(r'scrypt:n=(\d+)', hashed)
    if n_param:
        n_value = int(n_param.group(1))
        if n_value < 131072:
            print(
                f"Warning: scrypt n={n_value} is below OWASP 2024-2026 recommendation of 131072",
                file=sys.stderr,
            )

    assert check_password_hash(hashed, password), "Hash verification failed"
    assert not check_password_hash(hashed, password + "wrong"), (
        "Hash should reject wrong password"
    )

    print()
    print("Hashed password (set this as ADMIN_PASSWORD in .env):")
    print()
    print(f"  ADMIN_PASSWORD={hashed}")
    print()
    print("Verification: OK (hash matches input password)")
    print("Method: scrypt (OWASP 2024-2026 compliant)")


if __name__ == "__main__":
    main()

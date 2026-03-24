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

import sys
import getpass
from werkzeug.security import generate_password_hash, check_password_hash


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

    if len(password) < 8:
        print("Error: password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    hashed = generate_password_hash(password)

    # Verify the hash works
    assert check_password_hash(hashed, password), "Hash verification failed"
    assert not check_password_hash(hashed, password + "wrong"), "Hash should reject wrong password"

    print()
    print("Hashed password (set this as ADMIN_PASSWORD in .env):")
    print()
    print(f"  ADMIN_PASSWORD={hashed}")
    print()
    print("Verification: OK (hash matches input password)")


if __name__ == "__main__":
    main()

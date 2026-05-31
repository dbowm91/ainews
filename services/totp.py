import os
import secrets

import pyotp
from pyotp import TOTP

# Encryption key for TOTP secrets
_TOTP_ENCRYPTION_KEY: bytes | None = None


def _get_totp_encryption_key() -> bytes:
    """Get or validate the TOTP encryption key from environment."""
    global _TOTP_ENCRYPTION_KEY
    if _TOTP_ENCRYPTION_KEY is not None:
        return _TOTP_ENCRYPTION_KEY
    key = os.environ.get("TOTP_ENCRYPTION_KEY", "")
    if not key:
        # If no key is set, use a derived key from WEBHOOK_SECRET_KEY for backward compatibility
        webhook_key = os.environ.get("WEBHOOK_SECRET_KEY", "")
        if webhook_key:
            # Derive a key from webhook key using SHA-256
            import hashlib
            _TOTP_ENCRYPTION_KEY = hashlib.sha256(webhook_key.encode("utf-8")).digest()
            return _TOTP_ENCRYPTION_KEY
        raise RuntimeError("TOTP_ENCRYPTION_KEY or WEBHOOK_SECRET_KEY environment variable must be set")
    from cryptography.fernet import Fernet
    try:
        Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"TOTP_ENCRYPTION_KEY must be a valid Fernet key (44 base64 chars), got length {len(key)}",
        ) from e
    _TOTP_ENCRYPTION_KEY = key.encode("utf-8")
    return _TOTP_ENCRYPTION_KEY


def encrypt_totp_secret(secret: str) -> str:
    """Encrypt a TOTP secret for storage. Returns versioned base64-encoded ciphertext."""
    from cryptography.fernet import Fernet

    key = _get_totp_encryption_key()
    f = Fernet(key)
    ciphertext = f.encrypt(secret.encode("utf-8")).decode("utf-8")
    return f"v1:enc:{ciphertext}"


def decrypt_totp_secret(ciphertext: str) -> str:
    """Decrypt a stored TOTP secret. Handles versioned and legacy formats."""
    from cryptography.fernet import Fernet

    key = _get_totp_encryption_key()
    f = Fernet(key)

    if ciphertext.startswith("v1:enc:"):
        actual_cipher = ciphertext[7:]
        return f.decrypt(actual_cipher.encode("utf-8")).decode("utf-8")

    # Legacy plaintext - encrypt and re-save
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def generate_secret() -> str:
    return pyotp.random_base32()


def verify_token(secret: str, token: str) -> bool:
    if not secret or not token:
        return False
    # Decrypt if encrypted
    try:
        if secret.startswith("v1:enc:"):
            secret = decrypt_totp_secret(secret)
    except (ValueError, TypeError):
        pass
    totp = TOTP(secret)
    return totp.verify(token)


def get_provisioning_uri(secret: str, username: str, issuer: str = "ainews") -> str:
    # Decrypt if encrypted
    try:
        if secret.startswith("v1:enc:"):
            secret = decrypt_totp_secret(secret)
    except (ValueError, TypeError):
        pass
    totp = TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def generate_backup_codes(count: int = 8, length: int = 8) -> list[str]:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    codes = []
    for _ in range(count):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        codes.append(code)
    return codes


def verify_backup_code(stored_codes: list[str], provided_code: str) -> bool:
    if not stored_codes or not provided_code:
        return False
    provided_normalized = provided_code.strip().lower()
    for stored_code in stored_codes:
        if stored_code.strip().lower() == provided_normalized:
            return True
    return False


def consume_backup_code(stored_codes: list[str], provided_code: str) -> list[str] | None:
    provided_normalized = provided_code.strip().lower()
    for i, stored_code in enumerate(stored_codes):
        if stored_code.strip().lower() == provided_normalized:
            new_codes = stored_codes.copy()
            new_codes.pop(i)
            return new_codes
    return None

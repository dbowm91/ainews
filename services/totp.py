import secrets

import pyotp
from pyotp import TOTP


def generate_secret() -> str:
    return pyotp.random_base32()


def verify_token(secret: str, token: str) -> bool:
    if not secret or not token:
        return False
    totp = TOTP(secret)
    return totp.verify(token)


def get_provisioning_uri(secret: str, username: str, issuer: str = "ainews") -> str:
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

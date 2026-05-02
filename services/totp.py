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

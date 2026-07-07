from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class ApiToken(db.Model):  # type: ignore[name-defined]
    __tablename__ = "api_tokens"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(255), unique=True, nullable=False)
    token_prefix = db.Column(db.String(16), nullable=False, index=True)
    name = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime, nullable=True, default=None)

    def __init__(self, **kwargs):
        token_hash = kwargs.get("token_hash")
        if token_hash:
            raw_hash = kwargs.pop("raw_token_hash", None)
            if raw_hash:
                kwargs["token_prefix"] = raw_hash[:16]
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<ApiToken {self.name or self.id}>"


class AdminUser(db.Model):  # type: ignore[name-defined]
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    totp_secret = db.Column(db.String(256))
    totp_enabled = db.Column(db.Boolean, default=False)
    backup_codes = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<AdminUser {self.username}>"
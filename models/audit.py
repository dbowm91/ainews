from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    category = db.Column(db.String(32), nullable=True, index=True)
    target_type = db.Column(db.String(32))
    target_id = db.Column(db.Integer)
    user = db.Column(db.String(64), default="admin")
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.Index("ix_audit_logs_target", "target_type", "target_id"),)

    def __repr__(self):
        return f"<AuditLog {self.action} {self.target_type}:{self.target_id}>"
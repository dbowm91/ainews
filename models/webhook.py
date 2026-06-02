from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class Webhook(db.Model):  # type: ignore[name-defined]
    __tablename__ = "webhooks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(128), nullable=False)
    events = db.Column(db.JSON, nullable=False, default=list)
    active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_failure_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    failure_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Webhook {self.name}>"


class WebhookEvent(db.Model):  # type: ignore[name-defined]
    __tablename__ = "webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    webhook_id = db.Column(
        db.Integer, db.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type = db.Column(db.String(64), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    idempotency_key = db.Column(db.String(64), nullable=True, index=True)
    delivered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    payload = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<WebhookEvent webhook_id={self.webhook_id} type={self.event_type}>"
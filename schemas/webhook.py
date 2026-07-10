"""Pydantic schemas for webhook validation and serialization."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WebhookCreate(BaseModel):
    url: str = Field(description="Webhook endpoint URL")
    event_type: str = Field(description="Event type to subscribe to (e.g., article.published, newsletter.sent)")
    secret: Optional[str] = Field(default=None, description="HMAC secret for signature verification")
    active: bool = Field(default=True, description="Whether the webhook is active")
    name: Optional[str] = Field(default=None, description="Human-readable name for this webhook")


class WebhookResponse(BaseModel):
    id: int
    url: str
    event_type: str
    active: bool
    name: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}
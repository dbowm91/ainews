"""Pydantic schemas for Celery task input validation.

These schemas validate external arguments passed to Celery tasks, catching
type errors and invalid ranges early before task logic runs. Tasks that
accept external arguments (not just internal IDs) benefit most from
validation here.

Usage pattern (inside task body):
    from schemas.tasks import SelectArticleTask

    def select_article(self, article_id: int, run_id=None):
        try:
            validated = SelectArticleTask(article_id=article_id, run_id=run_id)
        except Exception as e:
            logger.warning("Invalid task input: %s", e)
            raise TypeError(f"Invalid select_article input: {e}")

        article_id = validated.article_id
        run_id = validated.run_id
        # ... rest of task logic
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SelectArticleTask(BaseModel):
    article_id: int = Field(..., gt=0, description="Article database ID")
    run_id: Optional[int] = Field(default=None, ge=0, description="Pipeline run ID")

    @field_validator("article_id")
    @classmethod
    def article_id_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"article_id must be positive, got {v}")
        return v


class GenerateNewsletterTask(BaseModel):
    dry_run_email: Optional[str] = Field(default=None, description="Email for dry run output")
    run_id: Optional[int] = Field(default=None, ge=0, description="Pipeline run ID")

    @field_validator("dry_run_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError(f"Invalid email format: {v}")
        return v


class SendEmailTask(BaseModel):
    email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html: str = Field(..., min_length=1, description="Email HTML body")
    unsub_url: str = Field(..., min_length=1, description="Unsubscribe URL")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError(f"Invalid email format: {v}")
        return v


class CleanupArticleVersionsTask(BaseModel):
    days_to_keep: int = Field(default=90, ge=1, le=365, description="Days of versions to retain")
    dry_run: bool = Field(default=False, description="Preview without deleting")

    @field_validator("days_to_keep")
    @classmethod
    def validate_days_to_keep(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"days_to_keep must be at least 1, got {v}")
        if v > 365:
            raise ValueError(f"days_to_keep exceeds 1 year (365 days), got {v}")
        return v


class ProcessItemTask(BaseModel):
    source_key: str = Field(..., min_length=1, description="Source identifier key")
    source_name: str = Field(..., min_length=1, max_length=255, description="Source display name")
    source_type: str = Field(..., description="Source type: rss, api, or web")
    external_id: Optional[str] = Field(default=None, max_length=500, description="External article ID")
    title: str = Field(..., min_length=1, max_length=1000, description="Article title")
    url: Optional[str] = Field(default=None, max_length=2000, description="Article URL")
    author: Optional[str] = Field(default=None, max_length=255, description="Article author")
    published_at: Optional[str] = Field(default=None, description="Publication date ISO string")
    text_content: Optional[str] = Field(default=None, description="Article text content")
    raw_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Relevance score 0-1")
    raw_metadata: Optional[dict] = Field(default=None, description="Raw metadata dict")
    topics: Optional[list[str]] = Field(default_factory=list, description="Article topics")
    min_content_length: Optional[int] = Field(default=None, ge=0, le=10000, description="Min content length")
    run_id: Optional[int] = Field(default=None, ge=0, description="Pipeline run ID")

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in ("rss", "api", "web"):
            raise ValueError(f"source_type must be rss, api, or web, got {v}")
        return v

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: Optional[list[str]]) -> list[str]:
        if v is None:
            return []
        if len(v) > 20:
            raise ValueError(f"topics list exceeds maximum of 20 items, got {len(v)}")
        return v
"""Pydantic schemas for admin API request validation.

These schemas validate request parameters and JSON bodies for admin API routes,
catching type errors and invalid values early before route logic runs.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_VALID_SOURCE_TYPES = frozenset({"rss", "atom", "web", "twitter", "reddit"})
_SOURCE_KEY_RE = re.compile(r"^[a-z0-9_]+$")


class ArticleIdsParams(BaseModel):
    """Query parameters for GET /api/articles/ids."""

    q: Optional[str] = Field(default="", max_length=200)
    status: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[int] = Field(default=None, ge=1)
    date_from: Optional[str] = Field(default=None, max_length=32)
    date_to: Optional[str] = Field(default=None, max_length=32)
    impact_min: Optional[int] = Field(default=None, ge=0, le=100)
    impact_max: Optional[int] = Field(default=None, ge=0, le=100)
    tag: Optional[str] = Field(default=None, max_length=64)

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_iso_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid ISO date format: {v}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from constants import VALID_PIPELINE_STATUSES

        if v not in VALID_PIPELINE_STATUSES:
            raise ValueError(
                f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}"
            )
        return v


class CreateSourceRequest(BaseModel):
    """Request body for POST /api/sources."""

    source_key: str = Field(..., pattern=r"^[a-z0-9_]+$", max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    url: Optional[str] = Field(default=None, max_length=2048)
    feed_url: Optional[str] = Field(default=None, max_length=2048)
    source_type: str = Field(..., max_length=32)
    active: bool = Field(default=True)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in _VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of: {sorted(_VALID_SOURCE_TYPES)}")
        return v


class UpdateSourceRequest(BaseModel):
    """Request body for PUT /api/sources/<id>."""

    source_key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$", max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    url: Optional[str] = Field(default=None, max_length=2048)
    feed_url: Optional[str] = Field(default=None, max_length=2048)
    source_type: Optional[str] = Field(default=None, max_length=32)
    active: Optional[bool] = None

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in _VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of: {sorted(_VALID_SOURCE_TYPES)}")
        return v


class BulkArticleRequest(BaseModel):
    """Request body for POST /api/articles/bulk."""

    article_ids: list[int] = Field(..., min_length=1, max_length=500)
    action: str = Field(..., min_length=1, max_length=32)
    status: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = Field(default=None, max_length=64)
    tags: Optional[list[str]] = Field(default=None, max_length=10)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid_actions = {"delete", "set_status", "set_category", "reprocess", "add_tags"}
        if v not in valid_actions:
            raise ValueError(
                f"Invalid action. Must be one of: {', '.join(sorted(valid_actions))}"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from constants import VALID_PIPELINE_STATUSES

        if v not in VALID_PIPELINE_STATUSES:
            raise ValueError(
                f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}"
            )
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) > 10:
            raise ValueError(f"Maximum 10 tags allowed, got {len(v)}")
        return v


class TaskStatusParams(BaseModel):
    """Path parameter for GET /api/task/<task_id>."""

    task_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not re.match(r"^[\w\-]+$", v):
            raise ValueError(f"Invalid task_id format: {v}")
        return v

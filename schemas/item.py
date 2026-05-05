from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawItem(BaseModel):
    source_id: str
    external_id: str
    title: str
    url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    text_content: str | None = None
    raw_score: float = 0.0
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
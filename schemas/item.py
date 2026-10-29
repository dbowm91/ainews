from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _unescape_entities(value: Any) -> Any:
    """Decode HTML entities in text that arrives HTML-escaped.

    RSS titles arrive already decoded, but JSON API sources sometimes return
    escaped text such as ``Everything announced at Amazon&#8217;s ...``.
    Storing that verbatim makes the entity visible in the rendered headline,
    because the template escapes the stored value again.
    """
    if isinstance(value, str) and "&" in value:
        unescaped = html.unescape(value)
        if unescaped != value:
            return unescaped
    return value


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

    @field_validator("title", "author", mode="before")
    @classmethod
    def _decode_entities(cls, value: Any) -> Any:
        return _unescape_entities(value)
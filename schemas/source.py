from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from schemas.common import BASE_DIR, cached_config_with_mtime, load_yaml_file


class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    WEB = "web"


class MatchMode(str, Enum):
    KEYWORD = "keyword"
    CONTEXTUAL = "contextual"


class TopicMatchConfig(BaseModel):
    match_mode: MatchMode = MatchMode.KEYWORD
    include: list[str] = Field(default_factory=lambda: ["other"])
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RSSConfig(BaseModel):
    feed_url: str = Field(..., min_length=1)
    max_items: int = Field(default=50, ge=1, le=200)
    request_timeout: int = Field(default=15, ge=5, le=60)
    user_agent: str = "AINewsBot/1.0"
    min_content_length: int = Field(
        default=200,
        ge=0,
        le=5000,
        description="If feed content is shorter than this, scrape the article page",
    )


class APIConfig(BaseModel):
    list_url: str = Field(..., min_length=1)
    list_method: str = "json_array"
    list_items_path: Optional[str] = None
    max_items: int = Field(default=30, ge=1, le=200)
    item_url: Optional[str] = None
    item_method: str = "json_object"
    fields: dict[str, str] = Field(default_factory=dict)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    request_timeout: int = 15
    user_agent: str = "AINewsBot/1.0"
    api_key: Optional[str] = None
    auth_header: Optional[str] = None


class PaginationConfig(BaseModel):
    enabled: bool = False
    type: str = "next_link"
    next_link_selector: Optional[str] = None
    max_pages: int = 3

    @field_validator("type")
    @classmethod
    def validate_pagination_type(cls, v):
        if v not in ("next_link", "query_param", "none"):
            raise ValueError(f"Unknown pagination type '{v}'")
        return v


class ListingConfig(BaseModel):
    card_selector: str
    link_selector: str
    link_attribute: str = "href"
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)


class ArticleSelectors(BaseModel):
    title_selector: Optional[str] = None
    author_selector: Optional[str] = None
    date_selector: Optional[str] = None
    date_attribute: Optional[str] = None
    body_selector: Optional[str] = None


class WebConfig(BaseModel):
    base_url: str = Field(..., min_length=1)
    listing_url: str = Field(..., min_length=1)
    listing: ListingConfig
    article: ArticleSelectors
    request_delay_min: float = 1.5
    request_delay_max: float = 4.0
    max_retries: int = 3
    user_agent: str = "AINewsBot/1.0"


ADAPTER_CONFIGS: dict[str, type[BaseModel]] = {
    "rss": RSSConfig,
    "api": APIConfig,
    "web": WebConfig,
}


class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)
    type: str
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any] = Field(default_factory=dict)
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v not in ADAPTER_CONFIGS:
            raise ValueError(
                f"Unknown source type '{v}'. Known: {list(ADAPTER_CONFIGS.keys())}"
            )
        return v

    @field_validator("config")
    @classmethod
    def validate_adapter_config(cls, v, info):
        source_type = info.data.get("type")
        if source_type in ADAPTER_CONFIGS:
            adapter_config = ADAPTER_CONFIGS[source_type]
            return adapter_config.model_validate(v).model_dump()
        return v


def _load_sources_from_file(path: Path) -> list[SourceConfig]:
    if not path.exists():
        return []
    raw = load_yaml_file(path)
    return [
        SourceConfig(**entry)
        for entry in raw.get("sources", [])
        if entry.get("enabled", True)
    ]


def load_sources(path: str | Path = BASE_DIR / "sources.yaml") -> list[SourceConfig]:
    return cached_config_with_mtime(
        key="sources",
        loader_fn=lambda: _load_sources_from_file(Path(path)),
        config_path=Path(path),
    )

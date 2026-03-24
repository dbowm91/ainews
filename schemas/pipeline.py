from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

BASE_DIR = Path(__file__).parent.parent


class RoleConfig(BaseModel):
    enabled: bool = True
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = Field(default=4096, ge=256, le=128000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    concurrency: int = Field(default=2, ge=1, le=32)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    system_prompt: Optional[str] = None  # configurable system prompt for all roles
    min_score: Optional[int] = None  # selector only
    web_search: Optional[bool] = None  # researcher only
    web_search_max_results: Optional[int] = None  # researcher only
    web_search_provider: Optional[str] = None  # researcher only
    db_related_max: Optional[int] = None  # researcher only
    max_article_text_length: Optional[int] = None  # researcher only
    max_key_points: Optional[int] = None  # writer only
    max_tags: Optional[int] = None  # editor only


class ReviewConfig(BaseModel):
    enabled: bool = False
    auto_publish_threshold: Optional[int] = Field(
        default=None,
        description="Auto-publish articles with impact_score >= this value, bypassing review",
    )


class PipelineConfig(BaseModel):
    selector: RoleConfig
    researcher: RoleConfig
    writer: RoleConfig
    editor: RoleConfig
    review: ReviewConfig = Field(default_factory=ReviewConfig)


class NewsletterConfig(BaseModel):
    max_articles: int = Field(default=10, ge=1, le=50)
    send_time: str = "08:00"
    timezone: str = "America/New_York"
    site_url: str = "https://ainews.dev"
    prep_minutes: int = Field(default=15, ge=5, le=60)


class NewsletterPipelineConfig(BaseModel):
    reader: RoleConfig = Field(
        default_factory=lambda: RoleConfig(
            provider="ollama-local",
            model="qwen3:8b",
            max_tokens=4096,
            temperature=0.0,
            concurrency=2,
            timeout_seconds=120,
        )
    )
    writer: RoleConfig = Field(
        default_factory=lambda: RoleConfig(
            provider="ollama-local",
            model="qwen3:8b",
            max_tokens=2048,
            temperature=0.4,
            concurrency=1,
            timeout_seconds=120,
        )
    )
    editor: RoleConfig = Field(
        default_factory=lambda: RoleConfig(
            provider="ollama-local",
            model="qwen3:8b",
            max_tokens=2048,
            temperature=0.0,
            concurrency=1,
            timeout_seconds=90,
        )
    )


class PipelineRootConfig(BaseModel):
    pipeline: PipelineConfig
    newsletter: NewsletterConfig = Field(default_factory=NewsletterConfig)
    newsletter_pipeline: NewsletterPipelineConfig = Field(
        default_factory=NewsletterPipelineConfig
    )


def _load_pipeline_config_from_file(path: str | Path) -> PipelineRootConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Pipeline config not found: {p}")
    raw = yaml.safe_load(p.read_text()) or {}
    return PipelineRootConfig(**raw)


def load_pipeline_config(
    path: str | Path = BASE_DIR / "pipeline.yaml",
) -> PipelineRootConfig:
    try:
        from services.config_cache import get_config_cache

        return get_config_cache().get(
            key="pipeline",
            loader_fn=lambda: _load_pipeline_config_from_file(path),
            ttl=300,
        )
    except Exception:
        return _load_pipeline_config_from_file(path)


def get_role_config(role: str) -> RoleConfig:
    config = load_pipeline_config()
    parts = role.split(".", 1)
    if len(parts) == 2:
        section = getattr(config, parts[0], None)
        if section is not None:
            return getattr(section, parts[1])
    return getattr(config.pipeline, role)

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import (
    BASE_DIR,
    MAX_TOKENS_FIELD,
    cached_config_with_mtime,
    load_yaml_file,
)


class RoleConfig(BaseModel):
    enabled: bool = True
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD
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


class SubagentStageConfig(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = MAX_TOKENS_FIELD
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    system_prompt: Optional[str] = None
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_delay: float = Field(default=5.0, ge=0.0, le=60.0)
    task_template: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=5, ge=1, le=20)


class SubagentChainStep(BaseModel):
    task_type: str
    prompt_data_template: str
    response_model: Optional[str] = None
    condition: Optional[str] = None


class SubagentChainConfig(BaseModel):
    enabled: bool = False
    max_length: int = Field(default=5, ge=1, le=10)
    steps: list[SubagentChainStep] = Field(default_factory=list)


class SubagentConfig(BaseModel):
    default: SubagentStageConfig = Field(default_factory=SubagentStageConfig)
    research: SubagentStageConfig = Field(default_factory=SubagentStageConfig)
    edit: SubagentStageConfig = Field(default_factory=SubagentStageConfig)
    chains: dict[str, SubagentChainConfig] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    ttl_days_low: int = 7
    ttl_days_medium: int = 30
    ttl_days_high: int = 0
    consolidation_cooldown_hours: int = 24
    max_entries_per_propose: int = 3
    consolidation_merge_window_hours: int = 72
    truncation_llm_enabled: bool = True
    truncation_llm_threshold: int = 2000
    truncation_llm_max_tokens: int = 512
    truncation_llm_temperature: float = 0.0


class StageConfig(BaseModel):
    """Pipeline stage configuration stub.

    Currently only defines tools list. The actual stage configuration is handled
    by SubagentStageConfig and RoleConfig. This stub exists for future extensibility.
    """
    tools: list[str] = Field(default_factory=list)


class PipelineRootConfig(BaseModel):
    pipeline: PipelineConfig
    newsletter: NewsletterConfig = Field(default_factory=NewsletterConfig)
    newsletter_pipeline: NewsletterPipelineConfig = Field(
        default_factory=NewsletterPipelineConfig
    )
    subagent: SubagentConfig = Field(default_factory=SubagentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    stages: dict[str, StageConfig] = Field(default_factory=dict)
    schedule: dict = Field(default_factory=dict)


def _load_pipeline_config_from_file(path: str | Path) -> PipelineRootConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Pipeline config not found: {p}")
    raw = load_yaml_file(p)
    from schemas.common import resolve_env_vars

    raw = resolve_env_vars(raw)
    return PipelineRootConfig(**raw)


def load_pipeline_config(
    path: str | Path = BASE_DIR / "pipeline.yaml",
) -> PipelineRootConfig:
    return cached_config_with_mtime(
        key="pipeline",
        loader_fn=lambda: _load_pipeline_config_from_file(path),
        config_path=Path(path),
    )


def get_role_config(role: str) -> RoleConfig:
    config = load_pipeline_config()
    parts = role.split(".", 1)
    if len(parts) == 2:
        section = getattr(config, parts[0], None)
        if section is not None:
            return getattr(section, parts[1])
    return getattr(config.pipeline, role)


def resolve_subagent_config(
    stage: str, default_role: Optional[str] = None
) -> SubagentStageConfig:
    config = load_pipeline_config()
    stage_config = getattr(config.subagent, stage, None)
    if default_role is None:
        default_role = "editor"
    if stage_config and stage_config.enabled:
        role_config = get_role_config(default_role)
        kwargs = {
            "enabled": True,
            "provider": stage_config.provider or role_config.provider,
            "model": stage_config.model or role_config.model,
        }
        if stage_config.max_tokens is not None:
            kwargs["max_tokens"] = stage_config.max_tokens
        if stage_config.temperature is not None:
            kwargs["temperature"] = stage_config.temperature
        if stage_config.timeout_seconds is not None:
            kwargs["timeout_seconds"] = stage_config.timeout_seconds
        if stage_config.system_prompt is not None:
            kwargs["system_prompt"] = stage_config.system_prompt
        if stage_config.max_retries is not None:
            kwargs["max_retries"] = stage_config.max_retries
        if stage_config.retry_delay is not None:
            kwargs["retry_delay"] = stage_config.retry_delay
        if stage_config.task_template is not None:
            kwargs["task_template"] = stage_config.task_template
        if stage_config.tools:
            kwargs["tools"] = stage_config.tools
        return SubagentStageConfig(**kwargs)
    return SubagentStageConfig(enabled=False)

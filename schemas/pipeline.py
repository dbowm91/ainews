from __future__ import annotations

from pathlib import Path
from string import Formatter
from typing import Literal, Optional, cast

from pydantic import BaseModel, Field

from schemas.common import (
    BASE_DIR,
    MAX_TOKENS_FIELD,
    cached_config_with_mtime,
    config_cache_key,
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
    """Configuration for the review stage and auto-publish behavior."""

    enabled: bool = False
    auto_approve: bool = Field(
        default=False,
        description=(
            "Approve and publish every article that reaches the review queue "
            "without waiting for a human. Default: False (a human decides)."
        ),
    )
    auto_publish_threshold: Optional[int] = Field(
        default=None,
        description="Auto-publish articles with impact_score >= this value, bypassing review. Default: None (disabled).",
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
    """Configuration for subagent pipeline stages.

    All fields are optional with sensible defaults:
    - default: Fallback config for any stage not explicitly configured.
    - research: Config for the research stage.
    - edit: Config for the edit stage.
    - chains: Named subagent chains for multi-step workflows.
    """

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
    research_token_budget: int = Field(default=900, ge=0, le=1600)
    editor_token_budget: int = Field(default=640, ge=0, le=1600)
    deep_token_budget: int = Field(default=1600, ge=0, le=2400)
    max_records_per_context: int = Field(default=8, ge=0, le=50)
    max_shared_records_per_context: int = Field(default=3, ge=0, le=20)
    max_query_topics: int = Field(default=20, ge=1, le=100)
    # These gates have independent rollback semantics: writes may be dual-written
    # before V2 reads/tools, maintenance, or synthesis are activated.
    memory_v2_writes_enabled: bool = False
    memory_v2_enabled: bool = False
    memory_tools_enabled: bool = False
    memory_tool_max_tokens_per_stage: int = Field(default=800, ge=0, le=2400)
    memory_tool_max_records_per_stage: int = Field(default=16, ge=0, le=100)
    memory_tool_max_chars_per_stage: int = Field(default=6000, ge=0, le=20000)
    memory_maintenance_enabled: bool = False
    memory_maintenance_max_items: int = Field(default=500, ge=1, le=5000)
    memory_maintenance_max_categories: int = Field(default=20, ge=1, le=200)
    memory_max_syntheses_per_day: int = Field(default=0, ge=0, le=1000)
    memory_synthesis_enabled: bool = False
    memory_synthesis_provider: Optional[str] = None
    memory_synthesis_model: Optional[str] = None
    memory_synthesis_reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    memory_synthesis_max_tokens: int = Field(default=768, ge=128, le=2048)
    memory_synthesis_retry_max_tokens: int = Field(default=2048, ge=128, le=4096)
    max_high_age_days: int = Field(default=90, ge=1, le=3650)
    high_review_grace_days: int = Field(default=30, ge=0, le=365)


class PipelineOptimizationConfig(BaseModel):
    """Independent rollback switches for optional pipeline inference work."""

    selector_prefilter_enabled: bool = False
    conditional_research_synthesis_enabled: bool = False
    conditional_edit_contextualization_enabled: bool = False
    memory_candidate_reuse_enabled: bool = False
    optional_llm_call_caps_enabled: bool = False
    max_optional_llm_calls_per_article_per_day: int = Field(default=3, ge=0, le=100)
    max_optional_llm_calls_per_day: int = Field(default=200, ge=0, le=10000)


class RuntimeConfig(BaseModel):
    """Process-wide limits for LLM work."""

    max_concurrent_llm_requests: int = Field(default=2, ge=1, le=32)


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
    optimizations: PipelineOptimizationConfig = Field(default_factory=PipelineOptimizationConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    experiments: dict = Field(default_factory=dict)
    stages: dict[str, StageConfig] = Field(default_factory=dict)
    schedule: dict = Field(default_factory=dict)


_KNOWN_SUBAGENT_TOOLS = frozenset({
    "get_topic_note", "context_notes", "related_articles", "get_trend_memory",
    "get_article_by_id", "search_articles", "get_source_health", "get_topic_gap_report",
    "get_source_performance", "get_quality_report", "find_dedupe_candidates",
    "estimate_stage_cost", "web_search", "get_search_provider", "memory_search", "memory_get",
})


def _validate_subagent_templates(config: PipelineRootConfig) -> None:
    expected = {
        "research": {"research_synthesis": {"title", "body", "web_results"}},
        "edit": {"edit_contextualization": {"draft", "brief", "topic_notes", "related_articles", "trend_memory"}},
    }
    for stage_name in ("research", "edit"):
        stage = getattr(config.subagent, stage_name)
        unknown = sorted(set(stage.tools) - _KNOWN_SUBAGENT_TOOLS)
        if unknown:
            raise ValueError(f"Unknown configured subagent tools for {stage_name}: {', '.join(unknown)}")
        task_template = stage.task_template
        required = expected[stage_name]
        if not task_template:
            continue
        path = Path(task_template)
        if not path.is_absolute():
            path = BASE_DIR / path
        if not path.is_file():
            raise ValueError(f"Configured {stage_name} subagent template does not exist: {task_template}")
        template = path.read_text()
        fields = {field for _, field, _, _ in Formatter().parse(template) if field}
        expected_fields = next(iter(required.values()))
        missing = sorted(expected_fields - fields)
        if missing:
            raise ValueError(
                f"Configured {stage_name} subagent template is missing placeholders: {', '.join(missing)}"
            )


def _load_pipeline_config_from_file(path: str | Path) -> PipelineRootConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Pipeline config not found: {p}")
    raw = load_yaml_file(p)
    from schemas.common import resolve_env_vars

    raw = resolve_env_vars(raw)
    config = PipelineRootConfig(**raw)
    _validate_subagent_templates(config)
    return config


def load_pipeline_config(
    path: str | Path = BASE_DIR / "pipeline.yaml",
) -> PipelineRootConfig:
    return cached_config_with_mtime(
        key=config_cache_key("pipeline", path),
        loader_fn=lambda: _load_pipeline_config_from_file(path),
        config_path=Path(path),
    )


def get_role_config(role: str) -> RoleConfig:
    config = load_pipeline_config()
    parts = role.split(".", 1)
    if len(parts) == 2:
        section = getattr(config, parts[0], None)
        if section is not None:
            return cast(RoleConfig, getattr(section, parts[1]))
    return cast(RoleConfig, getattr(config.pipeline, role))


def resolve_subagent_config(
    stage: str, default_role: Optional[str] = None
) -> SubagentStageConfig:
    config = load_pipeline_config()
    # Pipeline roles (researcher/editor) are intentionally distinct from the
    # subagent configuration keys (research/edit). Accept both at this public
    # boundary, but resolve through one canonical mapping.
    stage = {"researcher": "research", "editor": "edit"}.get(stage, stage)
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
        return SubagentStageConfig(**kwargs)  # type: ignore[arg-type]
    return SubagentStageConfig(enabled=False)

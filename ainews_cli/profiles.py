"""Deployment, pipeline, and source profiles for ainews onboarding."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Deployment profiles
# ---------------------------------------------------------------------------


class DeploymentProfile(str, enum.Enum):
    DOCKER_LOCAL = "docker-local"
    DOCKER_LAN = "docker-lan"
    REVERSE_PROXY = "reverse-proxy"
    BARE_METAL = "bare-metal"
    CUSTOM = "custom"


@dataclass
class DeploymentProfileConfig:
    name: str
    description: str
    env_overrides: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    requires_docker: bool = False
    requires_network: bool = False
    interactive_fields: list[str] = field(default_factory=list)


_DEPLOYMENT_PROFILES: dict[str, DeploymentProfileConfig] = {}


def _register_deployment(
    name: str,
    desc: str,
    *,
    env: dict[str, str] | None = None,
    warnings: list[str] | None = None,
    requires_docker: bool = False,
    requires_network: bool = False,
    interactive_fields: list[str] | None = None,
) -> None:
    _DEPLOYMENT_PROFILES[name] = DeploymentProfileConfig(
        name=name,
        description=desc,
        env_overrides=env or {},
        warnings=warnings or [],
        requires_docker=requires_docker,
        requires_network=requires_network,
        interactive_fields=interactive_fields or [],
    )


_register_deployment(
    DeploymentProfile.DOCKER_LOCAL,
    "Docker Compose on localhost — development and single-machine demo",
    env={
        "FLASK_CONFIG": "development",
        "AINEWS_RUNNING_IN_DOCKER": "1",
        "CELERY_BROKER_URL": "redis://redis:6379/0",
        "CELERY_RESULT_BACKEND": "redis://redis:6379/1",
        "DATABASE_URL": "sqlite:///instance/prod.db",
        "PORT": "5000",
    },
    warnings=[
        "Default credentials are for local development only.",
        "Do not use in production without reviewing security settings.",
    ],
    requires_docker=True,
)

_register_deployment(
    DeploymentProfile.DOCKER_LAN,
    "Docker Compose exposed on LAN — internal network access",
    env={
        "FLASK_CONFIG": "production",
        "AINEWS_RUNNING_IN_DOCKER": "1",
        "CELERY_BROKER_URL": "redis://redis:6379/0",
        "CELERY_RESULT_BACKEND": "redis://redis:6379/1",
        "DATABASE_URL": "sqlite:///instance/prod.db",
        "PORT": "5000",
    },
    warnings=[
        "No TLS configured — traffic is unencrypted.",
        "Ensure strong admin credentials and generated secrets.",
        "Restrict network access with firewall rules.",
    ],
    requires_docker=True,
    requires_network=True,
    interactive_fields=["site_url"],
)

_register_deployment(
    DeploymentProfile.REVERSE_PROXY,
    "Behind a reverse proxy (nginx, Caddy, etc.) — production deployments",
    env={
        "FLASK_CONFIG": "production",
        "AINEWS_RUNNING_IN_DOCKER": "1",
        "CELERY_BROKER_URL": "redis://redis:6379/0",
        "CELERY_RESULT_BACKEND": "redis://redis:6379/1",
        "DATABASE_URL": "sqlite:///instance/prod.db",
        "PORT": "5000",
    },
    warnings=[
        "The application must be deployed behind a TLS-terminating reverse proxy.",
        "Configure proxy headers: X-Forwarded-For, X-Forwarded-Proto, Host.",
    ],
    requires_docker=True,
    requires_network=True,
    interactive_fields=["site_url", "trusted_proxies"],
)

_register_deployment(
    DeploymentProfile.BARE_METAL,
    "Bare metal or VM — no Docker, foreground commands",
    env={
        "FLASK_CONFIG": "production",
        "CELERY_BROKER_URL": "redis://localhost:6379/0",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
        "DATABASE_URL": "sqlite:///instance/prod.db",
        "PORT": "5000",
    },
    warnings=[
        "Requires Python 3.11+, Redis, and uv available on PATH.",
        "Services run in foreground — use a process manager for production.",
    ],
    requires_docker=False,
    requires_network=False,
)

_register_deployment(
    DeploymentProfile.CUSTOM,
    "Custom — full control over all values",
    env={},
    warnings=[],
    requires_docker=False,
    requires_network=False,
    interactive_fields=["flask_config", "port", "site_url", "broker_url", "result_backend", "database_url"],
)


def get_deployment_profile(name: str) -> DeploymentProfileConfig:
    """Get a deployment profile by name.

    Raises:
        KeyError: If the profile name is not found.
    """
    if name not in _DEPLOYMENT_PROFILES:
        valid = ", ".join(sorted(_DEPLOYMENT_PROFILES.keys()))
        raise KeyError(f"Unknown deployment profile: {name!r}. Valid profiles: {valid}")
    return _DEPLOYMENT_PROFILES[name]


def list_deployment_profiles() -> list[DeploymentProfileConfig]:
    """List all available deployment profiles."""
    return [_DEPLOYMENT_PROFILES[k] for k in sorted(_DEPLOYMENT_PROFILES.keys())]


# ---------------------------------------------------------------------------
# Pipeline profiles
# ---------------------------------------------------------------------------


class PipelineProfile(str, enum.Enum):
    LIGHTWEIGHT = "lightweight-local"
    BALANCED = "balanced"
    QUALITY = "quality"
    LOW_COST = "low-cost"
    CUSTOM = "custom"


@dataclass
class PipelineProfileConfig:
    name: str
    description: str
    role_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    schedule_overrides: dict[str, Any] = field(default_factory=dict)
    subagent_overrides: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _role(
    *,
    enabled: bool = True,
    provider: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    concurrency: int = 2,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "enabled": enabled,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "concurrency": concurrency,
        "timeout_seconds": timeout_seconds,
    }
    if provider is not None:
        d["provider"] = provider
    if model is not None:
        d["model"] = model
    return d


_PIPELINE_PROFILES: dict[str, PipelineProfileConfig] = {}

_PIPELINE_PROFILES["lightweight-local"] = PipelineProfileConfig(
    name="lightweight-local",
    description="Conservative concurrency, smaller token limits, bounded timeouts",
    role_overrides={
        "selector": _role(max_tokens=2048, concurrency=1, timeout_seconds=60),
        "researcher": _role(max_tokens=4096, concurrency=1, timeout_seconds=90),
        "writer": _role(max_tokens=4096, concurrency=1, timeout_seconds=90),
        "editor": _role(max_tokens=4096, concurrency=1, timeout_seconds=60),
    },
    schedule_overrides={
        "crawl_interval_minutes": 60,
    },
    subagent_overrides={
        "default": {"enabled": False},
        "research": {"enabled": False},
        "edit": {"enabled": False},
    },
    warnings=[
        "Reduced concurrency may limit throughput.",
        "Subagents are disabled — quality may vary for complex articles.",
    ],
)

_PIPELINE_PROFILES["balanced"] = PipelineProfileConfig(
    name="balanced",
    description="Production-like defaults, moderate concurrency and token limits",
    role_overrides={
        "selector": _role(max_tokens=2048, concurrency=2, timeout_seconds=90),
        "researcher": _role(max_tokens=8192, concurrency=2, timeout_seconds=120),
        "writer": _role(max_tokens=8192, concurrency=2, timeout_seconds=120),
        "editor": _role(max_tokens=4096, concurrency=2, timeout_seconds=90),
    },
    schedule_overrides={
        "crawl_interval_minutes": 30,
    },
    subagent_overrides={},
    warnings=[],
)

_PIPELINE_PROFILES["quality"] = PipelineProfileConfig(
    name="quality",
    description="Larger budgets, quality-oriented — increased latency and cost",
    role_overrides={
        "selector": _role(max_tokens=4096, concurrency=2, timeout_seconds=120),
        "researcher": _role(max_tokens=16384, concurrency=2, timeout_seconds=180),
        "writer": _role(max_tokens=16384, concurrency=1, timeout_seconds=180),
        "editor": _role(max_tokens=8192, concurrency=2, timeout_seconds=120),
    },
    schedule_overrides={
        "crawl_interval_minutes": 30,
    },
    subagent_overrides={
        "default": {"enabled": True},
        "research": {"enabled": True},
        "edit": {"enabled": True},
    },
    warnings=[
        "Higher token usage increases latency and API costs.",
        "Subagents are enabled for deeper research and editing.",
    ],
)

_PIPELINE_PROFILES["low-cost"] = PipelineProfileConfig(
    name="low-cost",
    description="Smaller models, lower concurrency, reduced token ceilings",
    role_overrides={
        "selector": _role(max_tokens=1024, concurrency=1, timeout_seconds=60),
        "researcher": _role(max_tokens=2048, concurrency=1, timeout_seconds=90),
        "writer": _role(max_tokens=2048, concurrency=1, timeout_seconds=90),
        "editor": _role(max_tokens=2048, concurrency=1, timeout_seconds=60),
    },
    schedule_overrides={
        "crawl_interval_minutes": 60,
    },
    subagent_overrides={
        "default": {"enabled": False},
        "research": {"enabled": False},
        "edit": {"enabled": False},
    },
    warnings=[
        "Lower token budgets may truncate research and writing quality.",
        "Subagents are disabled.",
    ],
)

_PIPELINE_PROFILES["custom"] = PipelineProfileConfig(
    name="custom",
    description="Preserve current values and prompt for individual stage assignments",
    role_overrides={},
    schedule_overrides={},
    subagent_overrides={},
    warnings=[],
)


def get_pipeline_profile(name: str) -> PipelineProfileConfig:
    """Get a pipeline profile by name.

    Raises:
        KeyError: If the profile name is not found.
    """
    if name not in _PIPELINE_PROFILES:
        valid = ", ".join(sorted(_PIPELINE_PROFILES.keys()))
        raise KeyError(f"Unknown pipeline profile: {name!r}. Valid profiles: {valid}")
    return _PIPELINE_PROFILES[name]


def list_pipeline_profiles() -> list[PipelineProfileConfig]:
    """List all available pipeline profiles."""
    return [_PIPELINE_PROFILES[k] for k in sorted(_PIPELINE_PROFILES.keys())]


def pipeline_profile_to_env(profile: PipelineProfileConfig) -> dict[str, Any]:
    """Convert a pipeline profile to a pipeline config dict."""
    pipeline_section: dict[str, Any] = {}
    if profile.role_overrides:
        pipeline_section["pipeline"] = {}
        for role, overrides in profile.role_overrides.items():
            pipeline_section["pipeline"][role] = overrides
    if profile.schedule_overrides:
        pipeline_section["schedule"] = dict(profile.schedule_overrides)
    if profile.subagent_overrides:
        pipeline_section["subagent"] = dict(profile.subagent_overrides)
    return pipeline_section


# ---------------------------------------------------------------------------
# Source profiles
# ---------------------------------------------------------------------------


class SourceProfile(str, enum.Enum):
    MINIMAL = "minimal"
    AI_GENERAL = "ai-general"
    AI_SECURITY = "ai-security"
    COMPREHENSIVE = "comprehensive"
    EXISTING = "existing-defaults"
    CUSTOM = "custom"


@dataclass
class SourceProfileConfig:
    name: str
    description: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    topics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _rss_source(
    source_id: str,
    url: str,
    name: str,
    *,
    crawl_interval: int | None = None,
    topics_include: list[str] | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": source_id,
        "url": url,
        "type": "rss",
        "name": name,
        "enabled": True,
    }
    if crawl_interval is not None:
        d["crawl_interval"] = crawl_interval
    if topics_include:
        d["topics"] = {"include": topics_include}
    return d


_SOURCE_PROFILES: dict[str, SourceProfileConfig] = {}

_SOURCE_PROFILES["minimal"] = SourceProfileConfig(
    name="minimal",
    description="Single AI news RSS feed for quick setup",
    sources=[
        _rss_source(
            "ai-news-blog",
            "https://blog.example.com/feed",
            "AI News Blog",
        ),
    ],
    topics={
        "ai-general": {
            "display_name": "AI General",
            "query": "artificial intelligence",
        },
    },
)

_SOURCE_PROFILES["ai-general"] = SourceProfileConfig(
    name="ai-general",
    description="General AI news sources — broad coverage of AI research and industry",
    sources=[
        _rss_source(
            "openai-blog",
            "https://openai.com/blog/rss.xml",
            "OpenAI Blog",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "google-ai-blog",
            "https://blog.research.google/feeds/posts/default?alt=rss",
            "Google AI Blog",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "huggingface-blog",
            "https://huggingface.co/blog/feed.xml",
            "Hugging Face Blog",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "arxiv-ai",
            "https://rss.arxiv.org/rss/cs.AI",
            "arXiv cs.AI",
            topics_include=["ai-general"],
        ),
    ],
    topics={
        "ai-general": {
            "display_name": "AI General",
            "query": "artificial intelligence machine learning",
        },
        "llm": {
            "display_name": "Large Language Models",
            "query": "large language model LLM GPT Claude Gemini",
        },
    },
)

_SOURCE_PROFILES["ai-security"] = SourceProfileConfig(
    name="ai-security",
    description="AI safety and security focused sources",
    sources=[
        _rss_source(
            "alignment-forum",
            "https://www.alignmentforum.org/feed.xml",
            "Alignment Forum",
            topics_include=["ai-safety"],
        ),
        _rss_source(
            "anthropic-news",
            "https://www.anthropic.com/rss.xml",
            "Anthropic News",
            topics_include=["ai-safety", "ai-general"],
        ),
    ],
    topics={
        "ai-safety": {
            "display_name": "AI Safety",
            "query": "AI safety alignment risk",
        },
        "ai-general": {
            "display_name": "AI General",
            "query": "artificial intelligence",
        },
    },
)

_SOURCE_PROFILES["comprehensive"] = SourceProfileConfig(
    name="comprehensive",
    description="Full coverage — AI, security, industry, and research",
    sources=[
        _rss_source(
            "openai-blog",
            "https://openai.com/blog/rss.xml",
            "OpenAI Blog",
            topics_include=["ai-general", "llm"],
        ),
        _rss_source(
            "google-ai-blog",
            "https://blog.research.google/feeds/posts/default?alt=rss",
            "Google AI Blog",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "huggingface-blog",
            "https://huggingface.co/blog/feed.xml",
            "Hugging Face Blog",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "arxiv-ai",
            "https://rss.arxiv.org/rss/cs.AI",
            "arXiv cs.AI",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "anthropic-news",
            "https://www.anthropic.com/rss.xml",
            "Anthropic News",
            topics_include=["ai-general"],
        ),
        _rss_source(
            "alignment-forum",
            "https://www.alignmentforum.org/feed.xml",
            "Alignment Forum",
            topics_include=["ai-safety"],
        ),
    ],
    topics={
        "ai-general": {
            "display_name": "AI General",
            "query": "artificial intelligence machine learning",
        },
        "llm": {
            "display_name": "Large Language Models",
            "query": "large language model LLM GPT Claude Gemini",
        },
        "ai-safety": {
            "display_name": "AI Safety",
            "query": "AI safety alignment risk",
        },
    },
)

_SOURCE_PROFILES["existing-defaults"] = SourceProfileConfig(
    name="existing-defaults",
    description="Keep existing sources.yaml — do not modify",
    sources=[],
    topics={},
    warnings=[
        "Existing sources.yaml will not be modified.",
        "Review your current sources with: ainews config show",
    ],
)

_SOURCE_PROFILES["custom"] = SourceProfileConfig(
    name="custom",
    description="Start with an empty sources configuration",
    sources=[],
    topics={},
    warnings=[],
)


def get_source_profile(name: str) -> SourceProfileConfig:
    """Get a source profile by name.

    Raises:
        KeyError: If the profile name is not found.
    """
    if name not in _SOURCE_PROFILES:
        valid = ", ".join(sorted(_SOURCE_PROFILES.keys()))
        raise KeyError(f"Unknown source profile: {name!r}. Valid profiles: {valid}")
    return _SOURCE_PROFILES[name]


def list_source_profiles() -> list[SourceProfileConfig]:
    """List all available source profiles."""
    return [_SOURCE_PROFILES[k] for k in sorted(_SOURCE_PROFILES.keys())]


def source_profile_to_yaml(profile: SourceProfileConfig) -> dict[str, Any]:
    """Convert a source profile to a sources.yaml dict.

    Returns:
        Dict with ``sources`` list and ``topics`` dict keys.
    """
    return {
        "sources": list(profile.sources),
        "topics": dict(profile.topics),
    }

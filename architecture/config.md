# Configuration System

ainews uses YAML-based configuration files validated by Pydantic schemas, with Redis-backed caching and environment variable support.

## Configuration Files

| File | Purpose | Schema |
|------|---------|--------|
| `pipeline.yaml` | Pipeline stages, newsletter, subagent, memory, experiments, schedules | `PipelineRootConfig` |
| `providers.yaml` | LLM provider definitions + search provider config | Provider schemas |
| `sources.yaml` | News source definitions with adapter configs | `SourceConfig` |
| `topics.yaml` | Topic definitions for article classification | `TopicsConfig` |
| `config.py` | Flask configuration classes (Development, Production, Testing) | Flask Config |

## Pipeline Configuration (`pipeline.yaml`)

Top-level structure:

```yaml
pipeline:
  selector:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 1024
    temperature: 0.2
    concurrency: 4
    timeout_seconds: 60
    min_score: 6
    system_prompt: |
      You are a news editor deciding which stories to cover...

  researcher:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 8192
    temperature: 0.0
    concurrency: 2
    timeout_seconds: 180
    web_search: true
    web_search_max_results: 5
    web_search_provider: null
    db_related_max: 5
    max_article_text_length: 6000
    system_prompt: |
      You are a tech research analyst...

  writer:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 4096
    temperature: 0.3
    concurrency: 2
    timeout_seconds: 180
    max_key_points: 5
    system_prompt: |
      You are a professional tech news writer...

  editor:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 4096
    temperature: 0.0
    concurrency: 2
    timeout_seconds: 120
    max_tags: 3
    system_prompt: |
      You are a meticulous editor...

newsletter:
  max_articles: 10
  send_time: "08:00"
  timezone: "America/New_York"
  site_url: "${SITE_URL}"
  prep_minutes: 15

newsletter_pipeline:
  reader:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 4096
    temperature: 0.0
    concurrency: 2
    timeout_seconds: 120
    system_prompt: |
      You are a news analyst...

  writer:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 2048
    temperature: 0.4
    concurrency: 1
    timeout_seconds: 120
    system_prompt: |
      You are a newsletter writer...

  editor:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 2048
    temperature: 0.0
    concurrency: 1
    timeout_seconds: 90
    system_prompt: |
      You are an editor reviewing a newsletter executive summary...

subagent:
  default:
    enabled: false
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 2048
    temperature: 0.0
    timeout_seconds: 120
    max_retries: 1
    retry_delay: 5.0
  research:
    enabled: true
    provider: null
    model: null
    max_tokens: 2048
    temperature: 0.0
    timeout_seconds: 120
    max_retries: 1
    retry_delay: 5.0
    max_iterations: 5
    tools:
      - web_search
      - context_notes
      - related_articles
      - get_source_health
    system_prompt: |
      You are a research synthesizer...
    task_template: prompts/subagent_research_synthesis.txt
  edit:
    enabled: true
    provider: null
    model: null
    max_tokens: 2048
    temperature: 0.0
    timeout_seconds: 120
    max_retries: 1
    retry_delay: 5.0
    max_iterations: 5
    tools:
      - context_notes
      - related_articles
      - trend_memory
    system_prompt: |
      You are an editorial contextualizer...
    task_template: prompts/subagent_edit_contextualization.txt
  chains:
    research_deep:
      max_length: 3
      steps:
        - task_type: research
          prompt_data_template: ""
          condition: "article.impact_score >= 50"
        - task_type: research
          prompt_data_template: ""
          condition: "previous.steps[0].success"
    edit_review:
      max_length: 2
      steps:
        - task_type: edit
          prompt_data_template: ""
          condition: "article.pipeline_status == 'editing'"
        - task_type: edit
          prompt_data_template: ""
          condition: "previous.steps[0].success and article.degradation_count == 0"

memory:
  ttl_days_low: 7
  ttl_days_medium: 30
  ttl_days_high: 0
  consolidation_cooldown_hours: 24
  max_entries_per_propose: 3
  consolidation_merge_window_hours: 72

stages:
  research:
    tools: ["search_web", "get_topic_note"]
  write:
    tools: ["search_web"]
  edit:
    tools: ["get_topic_note", "get_related_articles", "get_trend_memory"]

experiments:
  enabled: true
  assignment_salt: "${EXPERIMENT_SALT}"
  prompt_variants:
    writer:
      control: |
        You are a professional tech news writer...
      variant_a: |
        You are a tech news writer specializing in concise, data-driven reporting...
      variant_b: |
        You are a narrative tech journalist...
    editor:
      control: |
        You are a meticulous editor...
      variant_a: |
        You are a copy editor focused on clarity and conciseness...
      variant_b: |
        You are a content strategist editor...

schedule:
  crawl_interval_minutes: 30
  retry_stuck_interval_minutes: 60
  cleanup_interval_minutes: 180
  cleanup_old_logs_hour: 3
  cleanup_old_versions_hour: 3
  cleanup_expired_verifications_interval_minutes: 15
  publish_scheduled_interval_minutes: 5
  cleanup_stale_limiter_interval_minutes: 5
  generate_newsletters_hour: 8
  consolidate_trend_memory_hour: 3
  cleanup_inactive_subscribers_hour: 1
  cleanup_inactive_subscribers_minute: 0
  cleanup_old_versions_days_to_keep: 90
```

> **Note:** System prompts are truncated above for readability. See the actual `pipeline.yaml` for full prompts. The `site_url` field supports environment variable expansion via `${SITE_URL}` syntax.

### RoleConfig

```python
class RoleConfig(BaseModel):
    enabled: bool = True
    provider: str = Field(..., min_length=1)  # Required
    model: str = Field(..., min_length=1)  # Required
    max_tokens: int = 4096
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    concurrency: int = Field(default=2, ge=1, le=32)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    system_prompt: Optional[str] = None  # Override prompts/*.txt
    min_score: Optional[int] = None      # Selector-specific
    # Role-specific fields:
    web_search: Optional[bool] = None    # researcher only
    web_search_max_results: Optional[int] = None  # researcher only
    db_related_max: Optional[int] = None  # researcher only
    max_article_text_length: Optional[int] = None  # researcher only
    max_key_points: Optional[int] = None  # writer only
    max_tags: Optional[int] = None       # editor only
```

### SubagentStageConfig

```python
class SubagentStageConfig(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None  # Falls back to default role config
    model: Optional[str] = None    # Falls back to default role config
    max_tokens: int = Field(default=4096, ge=256, le=128000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_delay: float = Field(default=5.0, ge=0.0, le=60.0)
    system_prompt: Optional[str] = None
    task_template: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=5, ge=1, le=20)
```

### ReviewConfig

```python
class ReviewConfig(BaseModel):
    """Configuration for the review stage and auto-publish behavior."""
    enabled: bool = False
    auto_publish_threshold: Optional[int] = Field(
        default=None,
        description="Auto-publish articles with impact_score >= this value, bypassing review. Default: None (disabled).",
    )
```

### MemoryConfig

```python
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
```

## Provider Configuration (`providers.yaml`)

```yaml
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      host: "http://localhost:11434"
      model: "qwen3:8b"
      max_tokens: 4096

  - id: openai
    type: openai
    enabled: false
    config:
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"
      model: "gpt-4o-mini"
      max_tokens: 4096

  - id: anthropic
    type: anthropic
    enabled: false
    config:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-sonnet-4-5-20250929"
      max_tokens: 4096

  - id: gemini
    type: gemini
    enabled: false
    config:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.0-flash"
      max_tokens: 4096

default_provider: ollama-local

search_providers:
  - id: duckduckgo
    type: duckduckgo
    enabled: true
    config: {}

  - id: google
    type: google
    enabled: false
    config:
      api_key: "${GOOGLE_API_KEY}"
      cse_id: "${GOOGLE_CSE_ID}"

  - id: searxng
    type: searxng
    enabled: false
    config:
      host: "http://localhost:8888"

  - id: hybrid
    type: hybrid
    enabled: true
    config: {}  # FTS5 + vector similarity search

default_search_provider: duckduckgo
```

## Source Configuration (`sources.yaml`)

```yaml
sources:
  - name: "Hacker News"
    id: "hacker-news"
    type: "api"
    enabled: true
    schedule_minutes: 30
    config:
      list_url: "https://hacker-news.firebaseio.com/v0/topstories.json"
      list_method: "json_array"
      item_url: "https://hacker-news.firebaseio.com/v0/item/{id}.json"
      max_items: 30
      fields:
        title: "title"
        url: "url"
        author: "by"
        published_at: "time"

  - name: "TechCrunch"
    id: "techcrunch"
    type: "rss"
    enabled: true
    config:
      feed_url: "https://techcrunch.com/feed/"
      max_items: 20

  - name: "Ars Technica"
    id: "ars-technica"
    type: "rss"
    enabled: true
    config:
      feed_url: "https://feeds.arstechnica.com/arstechnica/index"
      max_items: 20
```

### SourceConfig Schema

```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)
    type: str  # "rss", "api", or "web" (validated by field_validator)
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any]  # Adapter-specific (RSSConfig, APIConfig, or WebConfig)
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)

    @field_validator("config")
    def validate_adapter_config(cls, v, info):
        # Validates config against RSSConfig/APIConfig/WebConfig based on type
```

## Topic Configuration (`topics.yaml`)

```yaml
topics:
  ai:
    name: "AI & Machine Learning"
    description: "Artificial intelligence, machine learning, and neural networks"
    color: "#3B82F6"
    icon: "brain"
  privacy:
    name: "Privacy & Security"
    description: "Digital privacy, cybersecurity, and data protection"
    color: "#EF4444"
    icon: "shield"
  programming:
    name: "Programming"
    description: "Software development, languages, and tools"
    color: "#10B981"
    icon: "code"
  hardware:
    name: "Hardware"
    description: "Computer hardware, chips, and devices"
    color: "#F59E0B"
    icon: "cpu"
```

## Config Loading & Caching

### Loading Pattern

```python
# schemas/pipeline.py
def load_pipeline_config(path: str = None) -> PipelineRootConfig:
    """Load and validate pipeline.yaml with mtime-based cache."""
    config_path = Path(path or BASE_DIR / "pipeline.yaml")
    return cached_config_with_mtime(config_path, PipelineRootConfig)

# schemas/source.py
def load_sources(path: str = None) -> list[SourceConfig]:
    """Load and validate sources.yaml."""
    # ...

# schemas/llm.py
def load_providers_config(path: str = None) -> dict:
    """Load and validate providers.yaml."""
    # ...
```

### Caching Strategy

```python
# schemas/common.py
def cached_config_with_mtime(key: str, loader_fn: Callable[[], T], config_path: Path, ttl: int = 300) -> T:
    """Load a config with automatic invalidation when the source file changes.
    Uses ConfigCache (Redis-backed) with mtime-based staleness detection."""
```

### Celery-Safe Config Access

```python
# services/config_utils.py
def get_config_with_default(key: str, default=None):
    """Access Flask config from Celery tasks safely.
    Celery tasks run outside Flask app context."""
    try:
        from flask import current_app
        value = current_app.config.get(key)
        if value is not None:
            return value
    except RuntimeError:
        pass  # Outside Flask app context
    return default
```

## Environment Variables

Key environment variables used across the codebase:

| Variable | Purpose |
|----------|---------|
| `FLASK_CONFIG` | Flask config class (development/production/testing) |
| `SECRET_KEY` | Flask session signing key |
| `DATABASE_URL` | Database connection string |
| `REDIS_URL` | Redis connection string |
| `REDIS_SSL` | Enable Redis SSL |
| `REDIS_MAX_CONNECTIONS` | Redis pool size (default: 100) |
| `CONFIG_CACHE_REDIS_URL` | Dedicated Redis for config cache (default: derived from `REDIS_URL`) |
| `CONFIG_CACHE_REDIS_PASSWORD` | Redis password for config cache auth (default: none) |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_API_KEY` | Google Custom Search API key |
| `GOOGLE_CSE_ID` | Google Custom Search engine ID |
| `SEARXNG_BASE_URL` | SearxNG instance URL |
| `WEBHOOK_SECRET_KEY` | Fernet key for webhook secret encryption |
| `CELERY_TASK_SECRET` | HMAC secret for task signing |
| `EXPERIMENT_SALT` | Salt for A/B experiment group assignment |
| `CONTENT_EXTRACTOR_WORKERS` | Thread pool size for content extraction (default: 8) |
| `RELATED_CANDIDATE_LIMIT` | Candidate limit for related articles (default: 50) |

## Config Validation

`services/config_unified.py:validate_config()` validates all configs:

```python
def validate_config() -> tuple[bool, list[str]]:
    """Validate pipeline, topic, source, and LLM provider configs.
    Returns (is_valid, errors) tuple."""
```

Reload via `POST /api/v1/config/reload` admin endpoint.

## Celery Beat Schedule

Beat schedule is loaded from `pipeline.yaml` `schedule:` section via `config.py:get_beat_schedule()`:

```python
class Config:
    @classmethod
    def get_beat_schedule(cls, pipeline_cfg: dict | None = None) -> dict:
        """Build beat schedule from pipeline.yaml config."""
        if pipeline_cfg is None:
            from schemas.pipeline import load_pipeline_config
            pipeline_cfg = load_pipeline_config()

        sched = pipeline_cfg.schedule
        crawl_interval = int(sched.get("crawl_interval_minutes", 30))
        retry_interval = int(sched.get("retry_stuck_interval_minutes", 60))
        cleanup_logs_hour = int(sched.get("cleanup_old_logs_hour", 3))
        cleanup_versions_hour = int(sched.get("cleanup_old_versions_hour", 3))
        cleanup_expired_interval = int(sched.get("cleanup_expired_verifications_interval_minutes", 15))
        publish_interval = int(sched.get("publish_scheduled_interval_minutes", 5))
        cleanup_limiter_interval = int(sched.get("cleanup_stale_limiter_interval_minutes", 5))
        newsletters_hour = int(sched.get("generate_newsletters_hour", 8))
        trend_memory_hour = int(sched.get("consolidate_trend_memory_hour", 3))
        cleanup_subscribers_hour = int(sched.get("cleanup_inactive_subscribers_hour", 1))
        cleanup_subscribers_minute = int(sched.get("cleanup_inactive_subscribers_minute", 0))

        return {
            "run-all-sources": {
                "task": "tasks.crawl.run_all_sources",
                "schedule": timedelta(minutes=crawl_interval),
            },
            "retry-stuck-articles": {
                "task": "tasks.retry.retry_stuck",
                "schedule": timedelta(minutes=retry_interval),
            },
            "generate-newsletters": {
                "task": "tasks.newsletter.generate_daily_newsletters",
                "schedule": crontab(hour=newsletters_hour, minute=0),
            },
            "cleanup-old-logs": {
                "task": "tasks.cleanup.cleanup_old_pipeline_logs",
                "schedule": crontab(hour=cleanup_logs_hour, minute=0),
            },
            "consolidate-trend-memory": {
                "task": "tasks.cleanup.consolidate_trend_memory",
                "schedule": crontab(hour=trend_memory_hour, minute=30),
            },
            "purge-trend-memory": {
                "task": "tasks.cleanup.purge_trend_memory",
                "schedule": crontab(hour=trend_memory_hour, minute=45),
            },
            "cleanup-old-versions": {
                "task": "tasks.cleanup.cleanup_old_article_versions",
                "schedule": crontab(hour=cleanup_versions_hour, minute=45),
            },
            "cleanup-expired-verifications": {
                "task": "tasks.cleanup.cleanup_expired_verifications",
                "schedule": timedelta(minutes=cleanup_expired_interval),
            },
            "publish-scheduled-articles": {
                "task": "tasks.scheduler.publish_scheduled_articles",
                "schedule": timedelta(minutes=publish_interval),
            },
            "cleanup-stale-limiter-slots": {
                "task": "tasks.cleanup.cleanup_stale_limiter_slots",
                "schedule": timedelta(minutes=cleanup_limiter_interval),
            },
            "retry-failed-newsletter-deliveries": {
                "task": "tasks.newsletter.retry_failed_newsletter_deliveries",
                "schedule": timedelta(hours=2),
            },
            "recalculate-impact-scores": {
                "task": "tasks.cleanup.recalculate_impact_scores",
                "schedule": crontab(hour=4, minute=0),
            },
            "cleanup-inactive-subscribers": {
                "task": "tasks.subscribers.cleanup_inactive_subscribers",
                "schedule": crontab(hour=cleanup_subscribers_hour, minute=cleanup_subscribers_minute),
            },
            "backfill-embeddings": {
                "task": "tasks.embeddings.backfill_embeddings",
                "schedule": crontab(hour=2, minute=0),
            },
        }
```

All 14 tasks are shown above. Configurable values come from `pipeline.yaml` `schedule:` section with defaults in parentheses:

| Config Key | Default | Used By |
|------------|---------|---------|
| `crawl_interval_minutes` | 30 | `run-all-sources` (`timedelta`) |
| `retry_stuck_interval_minutes` | 60 | `retry-stuck-articles` (`timedelta`) |
| `cleanup_old_logs_hour` | 3 | `cleanup-old-logs` (`crontab`) |
| `cleanup_old_versions_hour` | 3 | `cleanup-old-versions` (`crontab`) |
| `cleanup_expired_verifications_interval_minutes` | 15 | `cleanup-expired-verifications` (`timedelta`) |
| `publish_scheduled_interval_minutes` | 5 | `publish-scheduled-articles` (`timedelta`) |
| `cleanup_stale_limiter_interval_minutes` | 5 | `cleanup-stale-limiter-slots` (`timedelta`) |
| `generate_newsletters_hour` | 8 | `generate-newsletters` (`crontab`) |
| `consolidate_trend_memory_hour` | 3 | `consolidate-trend-memory`, `purge-trend-memory` (`crontab`) |
| `cleanup_inactive_subscribers_hour` | 1 | `cleanup-inactive-subscribers` (`crontab`) |
| `cleanup_inactive_subscribers_minute` | 0 | `cleanup-inactive-subscribers` (`crontab`) |

After changing `pipeline.yaml`, call `Config.reload_beat_schedule()` then `POST /api/v1/config/reload` to apply.

## Key Files

| File | Purpose |
|------|---------|
| `pipeline.yaml` | Pipeline stage, newsletter, subagent, memory, experiment config |
| `providers.yaml` | LLM + search provider definitions |
| `sources.yaml` | News source definitions |
| `topics.yaml` | Topic definitions |
| `config.py` | Flask config classes + `get_beat_schedule()` |
| `schemas/pipeline.py` | `PipelineRootConfig`, `RoleConfig`, `SubagentConfig`, `MemoryConfig` |
| `schemas/source.py` | `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig` |
| `schemas/llm.py` | Provider config schemas |
| `schemas/topic.py` | `TopicDef`, `TopicsConfig` |
| `schemas/common.py` | `cached_config_with_mtime()` |
| `services/config_utils.py` | `get_config_with_default()` for Celery |
| `services/config_cache.py` | Redis-backed config cache |
| `services/config_unified.py` | `validate_config()` |

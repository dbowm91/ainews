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
  selector:     # RoleConfig: provider, model, temperature, max_tokens, concurrency, timeout
  researcher:   # RoleConfig
  writer:       # RoleConfig
  editor:       # RoleConfig

newsletter:
  send_time: "08:00"
  max_articles: 10
  timezone: "America/New_York"
  site_url: "https://ainews.dev"
  prep_minutes: 15

newsletter_pipeline:
  reader:     # RoleConfig for newsletter reader stage
  writer:     # RoleConfig for newsletter writer stage
  editor:     # RoleConfig for newsletter editor stage

subagent:
  max_iterations: 5
  tool_timeout: 30.0
  default:      # SubagentStageConfig: enabled, tools, max_retries
  research:     # SubagentStageConfig
  edit:         # SubagentStageConfig
  chains:       # SubagentChainConfig with conditional steps

memory:
  ttl_days_low: 7
  ttl_days_medium: 30
  ttl_days_high: 0
  consolidation_cooldown_hours: 24
  max_entries_per_propose: 3
  consolidation_merge_window_hours: 72

stages:
  selector:     # StageConfig (stub - only tools field)
  researcher:
  writer:
  editor:

experiments:
  enabled: false
  assignment_salt: "${EXPERIMENT_SALT}"
  prompt_variants:
    writer:
      control: "..."
      variant_a: "..."
    editor:
      control: "..."
      variant_a: "..."

schedule:
  run-all-sources: "every-30-min"
  generate-newsletters: "08:00-et"
  # ... other schedule overrides
```

### RoleConfig

```python
class RoleConfig(BaseModel):
    provider: str = Field(...)  # Required
    model: str = Field(...)  # Required
    max_tokens: int = 4096
    temperature: float = 0.0
    concurrency: int = 2
    timeout_seconds: int = 120
    enabled: bool = True
    system_prompt: Optional[str] = None  # Override prompts/*.txt
    min_score: Optional[int] = None      # Selector-specific
```

### SubagentStageConfig

```python
class SubagentStageConfig(BaseModel):
    enabled: bool = False
    tools: list[str] = Field(default_factory=list)
    max_retries: int = 1
    timeout_seconds: int = 120
    provider: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    system_prompt: Optional[str] = None
    retry_delay: float = 5.0
    task_template: Optional[str] = None
    max_iterations: int = 5
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
  ollama-local:
    type: openai
    enabled: true
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"
    default_model: "qwen3:8b"

  openai:
    type: openai
    enabled: false
    api_key: "${OPENAI_API_KEY}"
    default_model: "gpt-4o"

  anthropic:
    type: anthropic
    enabled: false
    api_key: "${ANTHROPIC_API_KEY}"
    default_model: "claude-sonnet-4-20250514"

  gemini:
    type: gemini
    enabled: false
    api_key: "${GEMINI_API_KEY}"
    default_model: "gemini-2.0-flash"

search:
  default: duckduckgo
  providers:
    duckduckgo:
      enabled: true
    hybrid:
      enabled: true
    google:
      enabled: false
    searxng:
      enabled: false
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
    from celery_support import get_current_app
    app = get_current_app()
    return app.config.get(key, default)
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
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_SEARCH_API_KEY` | Google Custom Search API key |
| `GOOGLE_SEARCH_CX` | Google Custom Search engine ID |
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
    @staticmethod
    def get_beat_schedule() -> dict:
        """Build Celery beat schedule from pipeline.yaml."""
        pipeline_config = load_pipeline_config()
        return {
            "run-all-sources": {
                "task": "tasks.crawl.run_all_sources",
                "schedule": crontab(minute="*/30"),
            },
            "generate-newsletters": {
                "task": "tasks.newsletter.generate_daily_newsletters",
                "schedule": crontab(hour=8, minute=0),  # 8:00 AM ET
            },
            # ... 14 scheduled tasks total
        }
```

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

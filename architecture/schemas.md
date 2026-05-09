# Schemas Module

The `schemas/` package contains Pydantic models for validation and serialization of configuration and responses.

## File Inventory

| File | Models | Purpose |
|------|--------|---------|
| `pipeline.py` | `PipelineRootConfig`, stage configs | Pipeline stage configuration |
| `source.py` | `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig` | Source adapter configuration |
| `llm.py` | Provider definitions | LLM/search provider settings |
| `llm_responses.py` | `SelectionResult`, `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief` | LLM response schemas |
| `tasks.py` | Task input validation | Celery task input validation |
| `topic.py` | Topic definitions | Topic configuration |
| `webhook.py` | `WebhookCreate`, `WebhookResponse` | Webhook configuration |

## Pipeline Configuration (`pipeline.py`)

**Note:** `StageConfig` is a stub with only `tools: list[str]`. Actual stage configuration is handled by `RoleConfig` within `PipelineConfig`.

```python
class PipelineRootConfig(BaseModel):
    pipeline: PipelineConfig           # Stage role configurations (selector, researcher, writer, editor)
    newsletter: NewsletterConfig
    newsletter_pipeline: NewsletterPipelineConfig  # 3-stage LLM pipeline for newsletter generation
    subagent: SubagentConfig            # Subagent tool and chain configuration
    memory: MemoryConfig
    stages: dict[str, StageConfig]     # Stub - only has tools field
    schedule: dict                      # Beat schedule overrides

class StageConfig(BaseModel):
    tools: list[str] = Field(default_factory=list)  # Stub - actual config in RoleConfig

class NewsletterConfig(BaseModel):
    max_articles: int = Field(default=10, ge=1, le=50)
    send_time: str = "08:00"
    timezone: str = "America/New_York"
    site_url: str = "https://ainews.dev"
    prep_minutes: int = Field(default=15, ge=5, le=60)

class NewsletterPipelineConfig(BaseModel):
    reader: RoleConfig
    writer: RoleConfig
    editor: RoleConfig

class SubagentConfig(BaseModel):
    enabled: bool = True
    default: SubagentStageConfig
    research: SubagentStageConfig
    edit: SubagentStageConfig
    chains: dict[str, SubagentChainConfig]  # Chain configurations

class SubagentChainConfig(BaseModel):
    enabled: bool = False
    max_length: int = Field(default=5, ge=1, le=10)
    steps: list[SubagentChainStep]

class SubagentChainStep(BaseModel):
    task_type: str
    prompt_data_template: str
    response_model: Optional[str] = None
    condition: Optional[str] = None

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

## Source Configuration (`source.py`)

```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str
    type: str                          # "rss", "api", or "web"
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any]             # Adapter-specific configuration
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)

class RSSConfig(BaseModel):
    item_path: str = "entries"
    field_mappings: dict[str, str]

class APIConfig(BaseModel):
    item_path: str
    auth_header: str | None = None
    pagination: PaginationConfig | None = None

class WebConfig(BaseModel):
    item_css: str
    field_selectors: dict[str, str]
    pagination: PaginationConfig | None = None
    follow_links: bool = False

class PaginationConfig(BaseModel):
    type: Literal["cursor", "offset", "page"]
    next_button_css: str | None = None
    cursor_path: str | None = None
    offset_param: str | None = None
    limit_param: str | None = None
```

## LLM Responses (`llm_responses.py`)

### Selection Result

```python
class SelectionResult(BaseModel):
    selected: bool
    score: int = Field(ge=1, le=10)
    reason: str
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    key_topics: list[str] = Field(default_factory=list)
    impact_summary: Optional[str] = None
```

### Research Brief

```python
class ResearchBrief(BaseModel):
    source_summary: str
    key_claims: list[KeyClaim]               # Note: list[KeyClaim] not list[str]
    direct_quotes: list[DirectQuote]
    external_sources: list[ExternalSource]
    related_articles: list[RelatedArticle]
    context_notes: str                       # Note: 'context_notes' not 'context'
    newsworthiness: str
    impact_score: int

class KeyClaim(BaseModel):
    claim: str
    source: str
    confidence: str

class DirectQuote(BaseModel):
    quote: str                              # Verbatim quote text
    attribution: str                        # Who said it
    source_url: Optional[str] = None        # Source URL of the quote

class ExternalSource(BaseModel):
    title: str
    url: str
    snippet: str

class RelatedArticle(BaseModel):
    title: str
    category: str
    summary_snippet: str
    created_at: str
```

### Condensed Article

```python
class CondensedArticle(BaseModel):
    headline: str
    tldr: str
    body: str
    why_it_matters: str                      # Additional fields not in doc
    key_points: list[str]
    what_to_watch: str
    citations: list[CitationItem]
    original_attribution: OriginalAttribution
    tags: list[str]
```

### Executive Summary

```python
class ExecutiveSummary(BaseModel):
    summary: str                             # Note: single 'summary' field (not 6 fields)
```

### Newsletter Brief

```python
class NewsletterBrief(BaseModel):
    themes: list[str]                        # Note: list[str] not str
    highlights: list[str]
    connections: list[str]                    # Note: list[str] not str
    preamble: str
    articles: list[NewsletterArticle]
    footer: str | None = None

class NewsletterArticle(BaseModel):
    headline: str = Field(description="Article headline within the newsletter")
    summary: str = Field(description="Brief summary of the article")
    url: Optional[str] = Field(default=None, description="URL to the article")
    tags: list[str] = Field(default_factory=list, description="Topics/tags for this article")
```

## Task Validation (`tasks.py`)

```python
class SelectArticleTask(BaseModel):
    article_id: int = Field(..., ge=1)

class ProcessItemTask(BaseModel):
    source_id: int
    item_data: dict
    topics: list[str] = Field(default_factory=list)

class GenerateNewsletterTask(BaseModel):
    date: Optional[date] = None
    email: Optional[str] = None

class SendEmailTask(BaseModel):
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    subject: str
    body: str

class CleanupArticleVersionsTask(BaseModel):
    days: int = Field(1, ge=1, le=365)
```

## Usage Patterns

### Configuration Loading

```python
# Load pipeline.yaml
with open("pipeline.yaml") as f:
    config_data = yaml.safe_load(f)
config = PipelineRootConfig(**config_data)
```

### Response Validation

```python
# Validate LLM response
response = llm_provider.chat(messages)
result = SelectionResult.model_validate_json(response.content)
```

### Task Input Validation

```python
@celery_app.task
def select_article(article_id: int):
    # Automatic validation via Pydantic
    input_data = SelectArticleInput(article_id=article_id)
    ...
```

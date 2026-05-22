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
| `item.py` | `RawItem` | Crawled item data from adapters |
| `admin.py` | Admin response schemas | Admin API response schemas |

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
    name: str = Field(..., min_length=1, max_length=128)
    type: str                          # "rss", "api", or "web" (validated by field_validator)
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any] = Field(default_factory=dict)  # Adapter-specific configuration
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)
    # Note: validate_adapter_config field_validator validates config against RSSConfig/APIConfig/WebConfig
    # Returns dict to match config field type (dict[str, Any]), but validation ensures type safety

class RSSConfig(BaseModel):
    feed_url: str = Field(..., min_length=1)
    max_items: int = Field(default=50, ge=1, le=200)
    request_timeout: int = Field(default=15, ge=5, le=60)
    user_agent: str = "AINewsBot/1.0"
    min_content_length: int = Field(default=200, ge=0, le=5000)

class APIConfig(BaseModel):
    list_url: str = Field(..., min_length=1)
    list_method: str = "json_array"    # or "json_object_items" for nested items
    list_items_path: Optional[str] = None  # JSONPath to items array
    max_items: int = Field(default=30, ge=1, le=200)
    item_url: Optional[str] = None       # Template for individual item URLs
    item_method: str = "json_object"
    fields: dict[str, str] = Field(default_factory=dict)
    filters: list[dict[str, Any]] = Field(default_factory=list)  # equals, min, exists
    metadata: dict[str, str] = Field(default_factory=dict)  # Additional fields to extract
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)  # next_link, query_param, none
    api_key: Optional[str] = None
    auth_header: Optional[str] = None    # e.g., "Authorization"
    request_timeout: int = 15
    user_agent: str = "AINewsBot/1.0"

class WebConfig(BaseModel):
    base_url: str = Field(..., min_length=1)
    listing_url: str = Field(..., min_length=1)
    listing: ListingConfig
    article: ArticleSelectors
    request_delay_min: float = 1.5
    request_delay_max: float = 4.0
    max_retries: int = 3
    user_agent: str = "AINewsBot/1.0"

class ListingConfig(BaseModel):
    card_selector: str
    link_selector: str
    link_attribute: str = "href"
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)

class ArticleSelectors(BaseModel):
    title_selector: str
    author_selector: Optional[str] = None
    date_selector: Optional[str] = None
    date_attribute: str = "datetime"
    body_selector: Optional[str] = None

class PaginationConfig(BaseModel):
    enabled: bool = False
    type: str = "next_link"             # "next_link", "query_param", or "none"
    next_link_selector: Optional[str] = None
    max_pages: int = 3
    @field_validator("type")
    def validate_pagination_type(cls, v):
        if v not in ("next_link", "query_param", "none"):
            raise ValueError(f"Unknown pagination type '{v}'")
        return v
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
    themes: list[str]                        # Major themes across selected articles
    highlights: list[str]                    # Most notable individual stories
    connections: list[str]                    # Patterns connecting multiple articles
    # Note: actual model does NOT have preamble, footer, or articles fields
    # These were in older documentation but are not implemented

class NewsletterArticle(BaseModel):
    headline: str = Field(description="Article headline within the newsletter")
    summary: str = Field(description="Brief summary of the article")
    url: Optional[str] = Field(default=None, description="URL to the article")
    tags: list[str] = Field(default_factory=list, description="Topics/tags for this article")
```

## Task Validation (`tasks.py`)

```python
class SelectArticleTask(BaseModel):
    article_id: int = Field(..., gt=0, description="Article database ID")
    run_id: Optional[int] = Field(default=None, ge=0, description="Pipeline run ID")

class ProcessItemTask(BaseModel):
    # Fields: source_key, source_name, source_type, external_id, title, url,
    # author, published_at, text_content, raw_score, raw_metadata, topics,
    # min_content_length, run_id
    # Note: actual implementation differs from older documentation

class GenerateNewsletterTask(BaseModel):
    dry_run_email: Optional[str] = None
    run_id: Optional[int] = None

class SendEmailTask(BaseModel):
    email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html: str = Field(..., min_length=1, description="Email HTML body")
    unsub_url: str = Field(..., min_length=1, description="Unsubscribe URL")

class CleanupArticleVersionsTask(BaseModel):
    days_to_keep: int = Field(default=90, ge=1, le=365, description="Days of versions to retain")
    dry_run: bool = Field(default=False, description="Preview without deleting")
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

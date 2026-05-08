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
    version: str = "1.0"
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
    max_articles: int = 20
    send_time: str = "08:00"
    timezone: str = "America/New_York"
    site_url: str
    prep_minutes: int = 15
    enable_topic_newsletters: bool = True
    batch_size: int = 500

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
    enabled: bool = True
    consolidate_interval_hours: int = 24
    max_entries_per_topic: int = 100
    embedding_model: str = "text-embedding-ada-002"
    ttl_days: int = 365
```

## Source Configuration (`source.py`)

```python
class SourceConfig(BaseModel):
    name: str
    type: Literal["rss", "api", "web"]
    url: str
    adapter_config: RSSConfig | APIConfig | WebConfig
    enabled: bool = True
    crawl_interval_minutes: int = 30

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
    score: int = Field(ge=1, le=10)
    confidence: Literal["low", "medium", "high"]
    reason: str                              # Note: field is 'reason' not 'reasoning'
    key_topics: list[str]
    impact_summary: str | None = None
    selected: bool | None = None             # Undocumented field
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
    text: str
    source: str

class ExternalSource(BaseModel):
    url: str
    title: str
    reliability: str

class RelatedArticle(BaseModel):
    article_id: int
    title: str
    relevance: str
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
    article_id: int
    title: str
    summary: str
    key_points: list[str]
    source_name: str
    url: str
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

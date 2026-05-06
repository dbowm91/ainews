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

```python
class PipelineRootConfig(BaseModel):
    version: str = "1.0"
    stages: dict[str, StageConfig]
    newsletter: NewsletterConfig
    subagent: SubagentConfig
    memory: MemoryConfig

class StageConfig(BaseModel):
    enabled: bool = True
    model: str | None = None
    prompt_variant: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout: float = 120.0

class NewsletterConfig(BaseModel):
    daily_send_time: str = "08:00"
    enable_topic_newsletters: bool = True
    batch_size: int = 500
    retry_attempts: int = 3

class SubagentConfig(BaseModel):
    enabled: bool = True
    max_iterations: int = 5
    tool_timeout: float = 30.0
    tools: list[str]

class MemoryConfig(BaseModel):
    enabled: bool = True
    consolidate_interval_hours: int = 24
    max_entries_per_topic: int = 100
    embedding_model: str = "text-embedding-ada-002"
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
    reasoning: str
    key_topics: list[str]
    impact_summary: str | None = None
```

### Research Brief

```python
class ResearchBrief(BaseModel):
    article_id: int
    key_findings: list[str]
    context: str
    citations: list[Citation]
    related_trends: list[str]
    background: str | None = None

class Citation(BaseModel):
    url: str
    title: str
    source: str
    relevance: str
```

### Condensed Article

```python
class CondensedArticle(BaseModel):
    article_id: int
    title: str
    summary: str  # 2-3 sentences
    key_points: list[str]  # 3-5 bullet points
    implications: str | None = None
    hook: str | None = None
    word_count: int = Field(ge=100, le=600)
```

### Executive Summary

```python
class ExecutiveSummary(BaseModel):
    date: date
    theme: str
    overview: str  # 2-4 sentences
    highlights: list[str]  # 3-5 key developments
    outlook: str | None = None
    article_count: int
```

### Newsletter Brief

```python
class NewsletterBrief(BaseModel):
    newsletter_id: int
    subject: str
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
class ProcessItemInput(BaseModel):
    source_id: int
    item_data: dict

class SelectArticleInput(BaseModel):
    article_id: int

class ResearchArticleInput(BaseModel):
    article_id: int

class WriteArticleInput(BaseModel):
    article_id: int
    research_brief_id: int | None = None

class EditArticleInput(BaseModel):
    article_id: int
    context: dict | None = None
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

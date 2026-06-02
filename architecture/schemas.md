# Schemas Module

The `schemas/` package contains Pydantic models for validation and serialization of configuration and responses.

## File Inventory

| File | Models | Purpose |
|------|--------|---------|
| `pipeline.py` | `PipelineRootConfig`, `PipelineConfig`, `RoleConfig`, `ReviewConfig`, `StageConfig`, `NewsletterConfig`, `NewsletterPipelineConfig`, `SubagentConfig`, `SubagentStageConfig`, `SubagentChainConfig`, `SubagentChainStep`, `MemoryConfig` | Pipeline stage configuration |
| `source.py` | `SourceConfig`, `SourceType`, `MatchMode`, `RSSConfig`, `APIConfig`, `WebConfig`, `TopicMatchConfig`, `PaginationConfig`, `ListingConfig`, `ArticleSelectors` | Source adapter configuration |
| `common.py` | `ProviderDef` | Shared provider definitions for LLM and search providers |
| `llm.py` | `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig` | LLM provider settings |
| `llm_responses.py` | `SelectionResult`, `ResearchBrief`, `KeyClaim`, `DirectQuote`, `ExternalSource`, `RelatedArticle`, `CitationItem`, `OriginalAttribution`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief`, `NewsletterArticle`, `SubagentResponse`, `ResearchSynthesisResponse`, `EditContextualizationResponse`, `ToolCall`, `ToolResult`, `ToolCallingResponse` | LLM response schemas |
| `tasks.py` | `SelectArticleTask`, `ProcessItemTask`, `GenerateNewsletterTask`, `SendEmailTask`, `CleanupArticleVersionsTask` | Celery task input validation |
| `topic.py` | `TopicDef`, `TopicsConfig` | Topic configuration |
| `webhook.py` | `WebhookCreate`, `WebhookResponse` | Webhook configuration |
| `item.py` | `RawItem` | Crawled item data from adapters |
| `admin.py` | `ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams` | Admin API request validation |
| `search.py` | `SearchConfig` | Search provider configuration (loaded from providers.yaml) |

## Pipeline Configuration (`pipeline.py`)

**Note:** `StageConfig` is a stub with only `tools: list[str]`. Actual stage configuration is handled by `RoleConfig` within `PipelineConfig`.

```python
class PipelineConfig(BaseModel):
    selector: RoleConfig
    researcher: RoleConfig
    writer: RoleConfig
    editor: RoleConfig
    review: ReviewConfig = Field(default_factory=ReviewConfig)

class RoleConfig(BaseModel):
    """Per-stage LLM role configuration."""
    enabled: bool = True
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    concurrency: int = Field(default=2, ge=1, le=32)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    system_prompt: Optional[str] = None  # configurable system prompt for all roles
    # Role-specific optional fields:
    min_score: Optional[int] = None          # selector role only
    web_search: Optional[bool] = None       # researcher role only
    web_search_max_results: Optional[int] = None   # researcher role only
    web_search_provider: Optional[str] = None      # researcher role only
    db_related_max: Optional[int] = None           # researcher role only
    max_article_text_length: Optional[int] = None # researcher role only
    max_key_points: Optional[int] = None          # writer role only
    max_tags: Optional[int] = None               # editor role only

class ReviewConfig(BaseModel):
    """Configuration for the review stage and auto-publish behavior."""
    enabled: bool = False
    auto_publish_threshold: Optional[int] = Field(
        default=None,
        description="Auto-publish articles with impact_score >= this value, bypassing review.",
    )

class SubagentStageConfig(BaseModel):
    """Per-stage subagent configuration."""
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

class PipelineRootConfig(BaseModel):
    pipeline: PipelineConfig           # Stage role configurations (selector, researcher, writer, editor)
    newsletter: NewsletterConfig
    newsletter_pipeline: NewsletterPipelineConfig  # 3-stage LLM pipeline for newsletter generation
    subagent: SubagentConfig            # Subagent tool and chain configuration
    memory: MemoryConfig
    experiments: dict                   # A/B experiment configuration (prompt_variants, assignment_salt)
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

class SubagentConfig(BaseModel):
    default: SubagentStageConfig
    research: SubagentStageConfig
    edit: SubagentStageConfig
    chains: dict[str, SubagentChainConfig]  # Chain configurations

    # Note: There is NO 'enabled' field on SubagentConfig.
    # The enabled flag exists on individual SubagentStageConfig instances.

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

### Enums

```python
class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    WEB = "web"

class MatchMode(str, Enum):
    KEYWORD = "keyword"
    CONTEXTUAL = "contextual"
```

`SourceType` defines valid source adapter types. `MatchMode` selects between keyword-based or LLM-based contextual topic matching in the selector stage.

### Source Config Models

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
    min_content_length: int = Field(default=200, ge=0, le=5000,
        description="If feed content is shorter than this, scrape the article page")

class APIConfig(BaseModel):
    list_url: str = Field(..., min_length=1)
    list_method: str = "json_array"    # or "json_object_items" for nested items
    list_items_path: Optional[str] = None  # JSONPath to items array
    max_items: int = Field(default=30, ge=1, le=200)
    item_url: Optional[str] = None     # Template URL using {id} placeholder for item ID
    item_method: str = "json_object"
    fields: dict[str, str] = Field(default_factory=dict)
    filters: list[dict[str, Any]] = Field(default_factory=list)  # equals, min, exists, contains
    metadata: dict[str, str] = Field(default_factory=dict)  # Additional fields to extract
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)  # next_link, query_param, none
    request_timeout: int = 15
    user_agent: str = "AINewsBot/1.0"
    api_key: Optional[str] = None
    auth_header: Optional[str] = None  # Header name; only Bearer auth supported (value always 'Bearer {api_key}')

class TopicMatchConfig(BaseModel):
    """Configuration for article topic matching in the selector stage."""
    match_mode: MatchMode = MatchMode.KEYWORD  # keyword or contextual
    include: list[str] = Field(default_factory=lambda: ["other"])  # Topics to include
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)  # Minimum confidence threshold

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
    title_selector: Optional[str] = None  # Optional - not all sources have separate title selectors
    author_selector: Optional[str] = None
    date_selector: Optional[str] = None
    date_attribute: Optional[str] = None
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

## Raw Item (`item.py`)

`RawItem` is the standard schema produced by all adapters (RSS, API, Web) and consumed by the ingestion pipeline. Adapters return `RawItem` instances from their `fetch()` method.

```python
class RawItem(BaseModel):
    source_id: str                                  # Source identifier (matches Source.id)
    external_id: str                                # Unique ID from the external source
    title: str                                      # Article title
    url: str | None = None                          # Article URL
    author: str | None = None                       # Article author
    published_at: datetime | None = None            # Publication timestamp
    text_content: str | None = None                 # Extracted article text
    raw_score: float = 0.0                          # Adapter-provided relevance score (0.0-1.0)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)  # Adapter-specific metadata
    topics: list[str] = Field(default_factory=list) # Adapter-detected topic tags
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

### Citation and Attribution Models

```python
class CitationItem(BaseModel):
    title: str
    url: str
    author: Optional[str] = None
    type: str = "article"  # "article", "web", or "db"

class OriginalAttribution(BaseModel):
    source: str
    author: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
```

`CitationItem` represents a source referenced within a condensed article. `OriginalAttribution` identifies the original article's source, author, URL, and publication date for proper credit.

### Condensed Article

```python
class CondensedArticle(BaseModel):
    headline: str                          # Catchy but accurate headline
    tldr: str                              # One-sentence summary for busy readers
    body: str                              # Full condensed article in markdown
    why_it_matters: str                    # 1-2 sentences connecting to a bigger trend
    key_points: list[str]                  # 3-5 bullet points of key takeaways
    what_to_watch: str                     # Forward-looking indicator
    citations: list[CitationItem]          # All sources referenced in the article
    original_attribution: OriginalAttribution  # Original source credit
    tags: list[str]                        # 1-3 concise topic tags (lowercase, hyphenated)
```

### Executive Summary

```python
class ExecutiveSummary(BaseModel):
    summary: str                             # Note: single 'summary' field (not 6 fields)
```

### Newsletter Brief

```python
class NewsletterArticle(BaseModel):
    """Individual article entry within a newsletter."""
    headline: str = Field(description="Article headline within the newsletter")
    summary: str = Field(description="Brief summary of the article")
    url: Optional[str] = Field(default=None, description="URL to the article")
    tags: list[str] = Field(default_factory=list, description="Topics/tags for this article")

class NewsletterBrief(BaseModel):
    themes: list[str]                        # Major themes across selected articles
    highlights: list[str]                    # Most notable individual stories
    connections: list[str]                    # Patterns connecting multiple articles
    # Note: actual model does NOT have preamble, footer, or articles fields
    # These were in older documentation but are not implemented
```

### Subagent Responses

```python
class SubagentResponse(BaseModel):
    """Response from subagent calls with optional fallback tracking."""
    synthesis: str = Field(description="Synthesized output from the subagent")
    used_fallback: bool = Field(default=False, description="Whether a fallback response was used")
    fallback_stages: list[str] = Field(default=[], description="Which stages used fallback responses")

class ResearchSynthesisResponse(BaseModel):
    """Research synthesis output for contextualization."""
    synthesis: str = Field(description="Synthesized summary of web research results")

class EditContextualizationResponse(BaseModel):
    """Edit contextualization output for gap/attribution/claims analysis."""
    synthesis: str = Field(description="Contextualization notes for the editor")

class ToolCall(BaseModel):
    """Tool call representation from LLM with tools."""
    id: str
    name: str
    arguments: dict

class ToolResult(BaseModel):
    """Tool result representation from tool execution."""
    id: str
    name: str
    content: str

class ToolCallingResponse(BaseModel):
    """Combined tool calling response from LLM provider."""
    text: str
    model: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_used: int = 0
```

### Task Validation (`tasks.py`)

```python
class SelectArticleTask(BaseModel):
    article_id: int = Field(..., gt=0, description="Article database ID")
    run_id: Optional[int] = Field(default=None, ge=0, description="Pipeline run ID")

class ProcessItemTask(BaseModel):
    source_key: str = Field(..., min_length=1, description="Source identifier key")
    source_name: str = Field(..., min_length=1, max_length=255, description="Source display name")
    source_type: str = Field(..., description="Source type: rss, api, or web")
    external_id: Optional[str] = Field(default=None, max_length=500, description="External article ID")
    title: str = Field(..., min_length=1, max_length=1000, description="Article title")
    url: Optional[str] = Field(default=None, max_length=2000, description="Article URL")
    author: Optional[str] = Field(default=None, max_length=255, description="Article author")
    published_at: Optional[str] = Field(default=None, description="Publication date ISO string")
    text_content: Optional[str] = Field(default=None, description="Article text content")
    raw_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Relevance score 0-1")
    raw_metadata: Optional[dict] = Field(default=None, description="Raw metadata dict")
    topics: Optional[list[str]] = Field(default_factory=list, description="Article topics (max 20)")
    min_content_length: Optional[int] = Field(default=None, ge=0, le=10000, description="Min content length")
    run_id: Optional[int] = Field(default=None, ge=0, description="Pipeline run ID")

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in ("rss", "api", "web"):
            raise ValueError(f"source_type must be rss, api, or web, got {v}")
        return v

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: Optional[list[str]]) -> list[str]:
        if v is None:
            return []
        if len(v) > 20:
            raise ValueError(f"topics list exceeds maximum of 20 items, got {len(v)}")
        return v

class GenerateNewsletterTask(BaseModel):
    dry_run_email: Optional[str] = None
    run_id: Optional[int] = None

class SendEmailTask(BaseModel):
    email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html: str = Field(..., min_length=1, description="Email HTML body")
    unsub_url: str = Field(..., min_length=1, description="Unsubscribe URL")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email format: {v}")
        return v

class CleanupArticleVersionsTask(BaseModel):
    days_to_keep: int = Field(default=90, ge=1, le=365, description="Days of versions to retain")
    dry_run: bool = Field(default=False, description="Preview without deleting")
```

## Common Schemas (`common.py`)

### Provider Definition

```python
class ProviderDef(BaseModel):
    """Shared provider definition for LLM and search providers."""
    id: str = Field(..., pattern=r"^[a-z0-9_\-]+$")
    type: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)
```

`ProviderDef` is the base schema for provider entries in `providers.yaml`. Both LLM providers and search providers use this shape.

## LLM Provider Configurations (`llm.py`)

```python
class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    host: str = "http://localhost:11434"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD   # 4096 default, 256-128000 range

class OpenAIConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    api_key: str = Field(..., min_length=1)        # Resolved from ${ENV_VAR} at validation time
    base_url: str = "https://api.openai.com/v1"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD

class AnthropicConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    api_key: str = Field(..., min_length=1)        # Resolved from ${ENV_VAR} at validation time
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD

class GeminiConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    api_key: str = Field(..., min_length=1)        # Resolved from ${ENV_VAR} at validation time
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD

class LLMProvidersConfig(BaseModel):
    providers: list[ProviderDef] = Field(default_factory=list)
    default_provider: str = "ollama-local"
```

All provider configs use `ConfigDict(extra="allow")` to permit additional provider-specific fields. API keys support `${ENV_VAR}` syntax and are resolved at validation time via `resolve_env_var()` with `required=True`.

The `ADAPTER_CONFIGS` dict maps provider type strings to their config classes: `{"ollama": OllamaConfig, "openai": OpenAIConfig, "anthropic": AnthropicConfig, "gemini": GeminiConfig}`.

`LLMProvidersConfig` is loaded from `providers.yaml` via `load_providers_config()` with Redis-backed caching.

## Search Provider Configuration (`search.py`)

```python
class SearchConfig(BaseModel):
    providers: list[ProviderDef] = Field(default_factory=list)
    default_provider: str = "duckduckgo"
```

`SearchConfig` is loaded from the `search_providers:` key in `providers.yaml` via `load_search_config()`. Defaults to DuckDuckGo if no config file exists.

**Note:** The schema field `default_provider` maps to the `default_search_provider` key in YAML configuration.

## Topic Configuration (`topic.py`)

```python
class TopicDef(BaseModel):
    display_name: str                      # Human-readable topic name
    description: str                       # Topic description for matching context
    color: str = "blue"                    # Display color for UI
    icon: Optional[str] = None             # Optional icon identifier

class TopicsConfig(BaseModel):
    topics: dict[str, TopicDef] = Field(default_factory=dict)  # Keyed by topic slug
```

`TopicsConfig` is loaded from `topics.yaml` via `load_topics()`. Topic keys are lowercase slugs used throughout the pipeline for article tagging and matching.

## Admin Schemas (`admin.py`)

```python
class ArticleIdsParams(BaseModel):
    """Query parameters for GET /api/articles/ids."""
    q: Optional[str] = Field(default="", max_length=200)
    status: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[int] = Field(default=None, ge=1)
    date_from: Optional[str] = Field(default=None, max_length=32)  # ISO date format
    date_to: Optional[str] = Field(default=None, max_length=32)    # ISO date format
    impact_min: Optional[int] = Field(default=None, ge=0, le=100)
    impact_max: Optional[int] = Field(default=None, ge=0, le=100)
    tag: Optional[str] = Field(default=None, max_length=64)
    # Validators: validate_iso_date (date_from/date_to), validate_status (must be valid PipelineStatus)

class CreateSourceRequest(BaseModel):
    """Request body for POST /api/sources."""
    source_key: str = Field(..., pattern=r"^[a-z0-9_]+$", max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    url: Optional[str] = Field(default=None, max_length=2048)
    feed_url: Optional[str] = Field(default=None, max_length=2048)
    source_type: str = Field(..., max_length=32)  # rss, atom, web, twitter, reddit
    active: bool = Field(default=True)

class UpdateSourceRequest(BaseModel):
    """Request body for PUT /api/sources/<id>."""
    source_key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$", max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    url: Optional[str] = Field(default=None, max_length=2048)
    feed_url: Optional[str] = Field(default=None, max_length=2048)
    source_type: Optional[str] = Field(default=None, max_length=32)
    active: Optional[bool] = None

class BulkArticleRequest(BaseModel):
    """Request body for POST /api/articles/bulk."""
    article_ids: list[int] = Field(..., min_length=1, max_length=500)
    action: str = Field(..., min_length=1, max_length=32)
    status: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = Field(default=None, max_length=64)
    tags: Optional[list[str]] = Field(default=None, max_length=10)
    # Valid actions: "delete", "set_status", "set_category", "reprocess", "add_tags"

class TaskStatusParams(BaseModel):
    """Path parameter for GET /api/task/<task_id>."""
    task_id: str = Field(..., min_length=1, max_length=128)  # alphanumeric + hyphens
```

## Intentional Layer Violations

The following layer violations are intentional and documented:

### `schemas/common.py` imports from `services`

`schemas/common.py` imports `services.config_cache` via `cached_config()` and `cached_config_with_mtime()`. This is intentional because config caching requires services layer knowledge. Documented with inline comments:
```python
# Layer violation: schemas should not import from services.
# This is intentional - config caching requires services layer knowledge.
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
    input_data = SelectArticleTask(article_id=article_id)
    ...
```

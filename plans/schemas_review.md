# Schemas Module Review

## Verified Claims

### StageConfig is a stub
**Status:** VERIFIED

`StageConfig` in `schemas/pipeline.py` (lines 140-141) contains only `tools: list[str]`. The documentation accurately notes this is a stub and actual stage configuration is handled by `RoleConfig`.

```python
class StageConfig(BaseModel):
    tools: list[str] = Field(default_factory=list)
```

### RoleConfig structure
**Status:** VERIFIED

`RoleConfig` has all documented fields: `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `concurrency`, `timeout_seconds`, `system_prompt`, and role-specific fields (`min_score`, `web_search`, `max_article_text_length`, etc.).

### PipelineConfig roles
**Status:** VERIFIED

`PipelineConfig` contains `selector`, `researcher`, `writer`, `editor`, and `review` roles.

### NewsletterConfig fields
**Status:** VERIFIED

All fields match: `max_articles`, `send_time`, `timezone`, `site_url`, `prep_minutes`.

### NewsletterPipelineConfig with defaults
**Status:** VERIFIED

Has `reader`, `writer`, `editor` with default factory `RoleConfig` objects using `ollama-local` provider and `qwen3:8b` model.

### SubagentConfig structure
**Status:** VERIFIED

`SubagentConfig` has `default`, `research`, `edit` (all `SubagentStageConfig`), and `chains: dict[str, SubagentChainConfig]`.

### MemoryConfig fields
**Status:** VERIFIED

All documented fields present: `ttl_days_low`, `ttl_days_medium`, `ttl_days_high`, `consolidation_cooldown_hours`, `max_entries_per_propose`, `consolidation_merge_window_hours`, `truncation_llm_*` fields.

### SelectionResult fields
**Status:** VERIFIED

Matches documentation: `selected`, `score` (ge=1, le=10), `reason`, `confidence` (pattern), `key_topics`, `impact_summary`.

### ResearchBrief structure
**Status:** VERIFIED

Uses `list[KeyClaim]` not `list[str]`, has `context_notes` (not `context`), includes all nested types.

### CondensedArticle fields
**Status:** VERIFIED

Has all documented fields including `why_it_matters`, `key_points`, `what_to_watch`, `citations`, `original_attribution`, `tags`.

### ExecutiveSummary
**Status:** VERIFIED

Has single `summary: str` field as documented.

### NewsletterArticle
**Status:** VERIFIED

Has `headline`, `summary`, `url`, `tags` fields.

---

## Discrepancies

### 1. NewsletterBrief missing `preamble` and `footer` fields

**Documentation says:**
```python
class NewsletterBrief(BaseModel):
    themes: list[str]
    highlights: list[str]
    connections: list[str]
    preamble: str           # <-- documented but missing
    articles: list[NewsletterArticle]
    footer: str | None = None  # <-- documented but missing
```

**Actual code (`schemas/llm_responses.py` lines 142-148):**
```python
class NewsletterBrief(BaseModel):
    themes: list[str]
    highlights: list[str]
    connections: list[str]
    # No preamble field
    # No footer field
```

The model only has `themes`, `highlights`, `connections`. The `preamble` and `footer` fields documented in `architecture/schemas.md` do not exist in the actual code.

---

### 2. Source adapter configs have completely different structures

**Documentation says:**
```python
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
```

**Actual code (`schemas/source.py`):**

`RSSConfig` (lines 29-39):
```python
class RSSConfig(BaseModel):
    feed_url: str = Field(..., min_length=1)
    max_items: int = Field(default=50, ge=1, le=200)
    request_timeout: int = Field(default=15, ge=5, le=60)
    user_agent: str = "AINewsBot/1.0"
    min_content_length: int = Field(default=200, ge=0, le=5000)
    # No item_path, no field_mappings
```

`APIConfig` (lines 42-55):
```python
class APIConfig(BaseModel):
    list_url: str = Field(..., min_length=1)
    list_method: str = "json_array"
    list_items_path: Optional[str] = None
    max_items: int = Field(default=30, ge=1, le=200)
    item_url: Optional[str] = None
    item_method: str = "json_object"
    fields: dict[str, str] = Field(default_factory=dict)
    # No item_path as documented
```

`WebConfig` (lines 87-95):
```python
class WebConfig(BaseModel):
    base_url: str = Field(..., min_length=1)
    listing_url: str = Field(..., min_length=1)
    listing: ListingConfig
    article: ArticleSelectors
    request_delay_min: float = 1.5
    request_delay_max: float = 4.0
    max_retries: int = 3
    user_agent: str = "AINewsBot/1.0"
    # Completely different structure - no item_css, no field_selectors
```

The adapter config documentation is completely out of sync with implementation.

---

### 3. Tasks schema differs significantly from documentation

**Documentation says:**
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

**Actual code (`schemas/tasks.py`):**

`SelectArticleTask` (lines 33-42) - ADDITIONAL `run_id` field not documented:
```python
class SelectArticleTask(BaseModel):
    article_id: int = Field(..., gt=0)
    run_id: Optional[int] = Field(default=None, ge=0)
```

`ProcessItemTask` (lines 87-117) - COMPLETELY DIFFERENT:
```python
class ProcessItemTask(BaseModel):
    source_key: str  # was source_id
    source_name: str  # new field
    source_type: str  # new field
    external_id: Optional[str] = None  # new field
    title: str  # new field
    url: Optional[str] = None  # new field
    author: Optional[str] = None  # new field
    published_at: Optional[str] = None  # new field
    text_content: Optional[str] = None  # new field
    raw_score: Optional[float] = None  # new field
    raw_metadata: Optional[dict] = None  # new field
    topics: Optional[list[str]] = None  # was required list, now optional
    # item_data dict was removed entirely
```

`GenerateNewsletterTask` (lines 45-56) - DIFFERENT field names:
```python
class GenerateNewsletterTask(BaseModel):
    dry_run_email: Optional[str] = None  # was "email"
    run_id: Optional[int] = None  # new field
    # "date" field was removed
```

`SendEmailTask` (lines 59-70) - Different validator:
```python
class SendEmailTask(BaseModel):
    email: str = Field(...)
    subject: str = Field(...)
    html: str = Field(...)  # was "body"
    unsub_url: str = Field(...)  # new field
    # Uses _EMAIL_RE regex instead of pattern attribute
```

`CleanupArticleVersionsTask` (lines 73-84) - Different field name:
```python
class CleanupArticleVersionsTask(BaseModel):
    days_to_keep: int = Field(default=90, ge=1, le=365)  # was "days"
    dry_run: bool = Field(default=False)  # new field
```

---

### 4. PaginationConfig structure differs

**Documentation says:**
```python
class PaginationConfig(BaseModel):
    type: Literal["cursor", "offset", "page"]
    next_button_css: str | None = None
    cursor_path: str | None = None
    offset_param: str | None = None
    limit_param: str | None = None
```

**Actual code (lines 58-69):**
```python
class PaginationConfig(BaseModel):
    enabled: bool = False
    type: str = "next_link"  # NOT Literal, uses string
    next_link_selector: Optional[str] = None  # was next_button_css
    max_pages: int = 3  # new field
    # No cursor_path, offset_param, limit_param
```

---

### 5. Document references non-existent `schemas/article.py`

The architecture document references `schemas/article.py` for Article API schemas, but this file does not exist. There is no article.py in the schemas directory.

---

## Bugs Found

### Bug 1: No adapter-specific config validation

**File:** `schemas/source.py`

`SourceConfig.config` is typed as `dict[str, Any]` with no validation against the actual adapter type. This means:
- An RSS source with API-config fields will pass validation silently
- A user will only discover the misconfiguration at runtime when the adapter tries to use it

```python
class SourceConfig(BaseModel):
    ...
    config: dict[str, Any] = Field(default_factory=dict)  # No adapter validation
```

### Bug 2: StageConfig serves no purpose

**File:** `schemas/pipeline.py`

`StageConfig` is defined and used in `PipelineRootConfig.stages: dict[str, StageConfig]`, but:
1. It only has `tools: list[str]` - no actual stage configuration
2. The comment admits it's a stub
3. No code appears to actually use `PipelineRootConfig.stages`
4. The actual stage configuration is via `RoleConfig` in `PipelineConfig`

This creates confusion and unused code.

---

## Improvement Recommendations

### 1. Update architecture/schemas.md to match actual implementation

The documentation is significantly out of sync with the code:
- Source adapter configs are completely different
- Task schemas have major structural differences
- NewsletterBrief is missing fields
- PaginationConfig differs

Recommendation: Update `architecture/schemas.md` to accurately reflect the actual code structure.

### 2. Consider adding adapter config validation

Add a validator to `SourceConfig` that validates `config` against the appropriate adapter schema based on `type`:

```python
@field_validator("config")
@classmethod
def validate_adapter_config(cls, v, info):
    source_type = info.data.get("type")
    if source_type in ADAPTER_CONFIGS:
        adapter_config = ADAPTER_CONFIGS[source_type]
        # Validate and strip unknown fields
        return adapter_config.model_validate(v).model_dump()
    return v
```

### 3. Remove or properly implement StageConfig

Either:
- Remove `StageConfig` and `stages` field from `PipelineRootConfig` if unused
- Or expand `StageConfig` to actually contain meaningful configuration

### 4. Add missing fields to NewsletterBrief

If `preamble` and `footer` are needed, add them to `NewsletterBrief`:
```python
class NewsletterBrief(BaseModel):
    themes: list[str]
    highlights: list[str]
    connections: list[str]
    preamble: str  # Add if needed
    articles: list[NewsletterArticle]
    footer: str | None = None  # Add if needed
```

### 5. Document the actual task schemas

The tasks.py module has significantly different schemas than documented. Either:
- Update the architecture document to match
- Or refactor the actual schemas to match the documentation

---

## Layer Violations

### Layer Violation 1: Utils importing from Services

**Files:** `schemas/common.py`

The `cached_config` and `cached_config_with_mtime` utility functions in `schemas/common.py` import from `services.config_cache`:

```python
# schemas/common.py lines 70-77
def cached_config(key: str, loader_fn: Callable[[], T], ttl: int = 300) -> T:
    try:
        from services.config_cache import get_config_cache  # VIOLATION
        return cast(T, get_config_cache().get(key=key, loader_fn=loader_fn, ttl=ttl))
    except Exception:
        return cast(T, loader_fn())
```

Per AGENTS.md guidelines, utils should contain "pure helper functions with minimal dependencies." These functions reach into the services layer, which violates clean layering. The `schemas/` module is meant to be a low-level module that other layers can import, but importing services creates a circular dependency risk and breaks the layer isolation.

**Note:** This is a pre-existing architectural issue, not a new bug.

### Layer Violation 2: RoleConfig field naming is not generic

**File:** `schemas/pipeline.py`

`RoleConfig` has hardcoded role-specific fields:
```python
class RoleConfig(BaseModel):
    ...
    min_score: Optional[int] = None      # selector only
    web_search: Optional[bool] = None    # researcher only
    web_search_max_results: Optional[int] = None  # researcher only
    web_search_provider: Optional[str] = None    # researcher only
    db_related_max: Optional[int] = None           # researcher only
    max_article_text_length: Optional[int] = None   # researcher only
    max_key_points: Optional[int] = None           # writer only
    max_tags: Optional[int] = None                 # editor only
```

While not a layer violation per se, this design forces `RoleConfig` to know about all pipeline roles. A more extensible design would use role-specific config classes that inherit from a base or use a plugin system.

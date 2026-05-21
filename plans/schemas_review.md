# Schemas Module Architecture Review

**Review Date:** 2026-05-21  
**Reviewer:** Architecture Review Agent  
**Document Reviewed:** `architecture/schemas.md`

---

## Executive Summary

The architecture document `architecture/schemas.md` is **largely accurate** but has several discrepancies with the actual implementation. Most critically, there is a **duplicate `ADAPTER_CONFIGS` bug** in `schemas/source.py` that causes the `SourceConfig.config` field_validator to fail at runtime.

---

## Verified Correct

### 1. StageConfig Stub Status
**Status:** VERIFIED CORRECT

The document correctly states that `StageConfig` is a stub with only `tools: list[str]`.

**Actual Implementation (`schemas/pipeline.py` lines 140-146):**
```python
class StageConfig(BaseModel):
    """Pipeline stage configuration stub.

    Currently only defines tools list. The actual stage configuration is handled
    by SubagentStageConfig and RoleConfig. This stub exists for future extensibility.
    """
    tools: list[str] = Field(default_factory=list)
```

### 2. PipelineRootConfig Structure
**Status:** VERIFIED CORRECT

The documented structure matches the implementation:
- `pipeline: PipelineConfig` - present (line 150)
- `newsletter: NewsletterConfig` - present with defaults (line 151)
- `newsletter_pipeline: NewsletterPipelineConfig` - present with defaults (lines 152-154)
- `subagent: SubagentConfig` - present with defaults (line 155)
- `memory: MemoryConfig` - present with defaults (line 156)
- `stages: dict[str, StageConfig]` - present as stub dict (line 157)
- `schedule: dict` - present with defaults (line 158)

### 3. ExecutiveSummary Schema
**Status:** VERIFIED CORRECT

**Documented (line 179-181):**
```python
class ExecutiveSummary(BaseModel):
    summary: str                             # Note: single 'summary' field (not 6 fields)
```

**Actual Implementation (`schemas/llm_responses.py` lines 151-158):**
```python
class ExecutiveSummary(BaseModel):
    summary: str = Field(
        description=(
            "3-4 paragraph executive summary. Sharp, slightly informal tone. "
            "Lead with the most important takeaway. "
            "Reference specific articles where relevant."
        )
    )
```

### 4. NewsletterBrief Does NOT Have preamble/footer
**Status:** VERIFIED CORRECT

The document correctly notes that `NewsletterBrief` does NOT have `preamble`, `footer`, or `articles` fields.

**Actual Implementation (`schemas/llm_responses.py` lines 142-148):**
```python
class NewsletterBrief(BaseModel):
    themes: list[str] = Field(description="Major themes across the selected articles")
    highlights: list[str] = Field(description="Most notable individual stories")
    connections: list[str] = Field(
        default_factory=list,
        description="Patterns or threads connecting multiple articles",
    )
```

### 5. NewsletterArticle Schema
**Status:** VERIFIED CORRECT

**Documented (lines 193-198):**
```python
class NewsletterArticle(BaseModel):
    headline: str = Field(description="Article headline within the newsletter")
    summary: str = Field(description="Brief summary of the article")
    url: Optional[str] = Field(default=None, description="URL to the article")
    tags: list[str] = Field(default_factory=list, description="Topics/tags for this article")
```

**Actual Implementation (`schemas/llm_responses.py` lines 135-139):** Matches exactly.

### 6. SelectionResult Schema
**Status:** VERIFIED CORRECT

**Actual Implementation (`schemas/llm_responses.py` lines 16-22):**
```python
class SelectionResult(BaseModel):
    selected: bool
    score: int = Field(ge=1, le=10)
    reason: str
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    key_topics: list[str] = Field(default_factory=list, description="Identified topics from the article")
    impact_summary: Optional[str] = Field(default=None, description="Brief summary of why this article matters")
```

### 7. Task Validation Schemas
**Status:** VERIFIED CORRECT

- `SelectArticleTask` matches documentation (lines 33-42 in tasks.py)
- `GenerateNewsletterTask` matches documentation (lines 45-56)
- `SendEmailTask` matches documentation (lines 59-70)
- `CleanupArticleVersionsTask` matches documentation (lines 73-84)
- `ProcessItemTask` documented fields match implementation (lines 87-117)

### 8. MemoryConfig
**Status:** VERIFIED CORRECT

All fields and defaults match the implementation (`schemas/pipeline.py` lines 127-137).

### 9. SubagentConfig Structure
**Status:** VERIFIED CORRECT

- `enabled: bool = True`
- `default: SubagentStageConfig`
- `research: SubagentStageConfig`
- `edit: SubagentStageConfig`
- `chains: dict[str, SubagentChainConfig]`

All match the implementation (`schemas/pipeline.py` lines 120-124).

### 10. Topic Schemas
**Status:** VERIFIED CORRECT

`TopicDef` and `TopicsConfig` match the implementation (`schemas/topic.py`).

### 11. Webhook Schemas
**Status:** VERIFIED CORRECT

`WebhookCreate` and `WebhookResponse` match the implementation (`schemas/webhook.py`).

---

## Discrepancies Found

### 1. SourceConfig Type Field Missing pattern validator
**Status:** DISCREPANCY (Low Impact)

**Documented (`architecture/schemas.md` line 108):**
```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)
    type: str                          # "rss", "api", or "web"
```

**Actual Implementation (`schemas/source.py` lines 105-112):**
```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)
    type: str
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any] = Field(default_factory=dict)
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)
```

The documentation shows `type: str` without the pattern or description, but the implementation has a `validate_type` field_validator (lines 114-121) that validates against known source types. This is an improvement over what was documented.

### 2. RSSConfig Schema Different from Documented
**Status:** DISCREPANCY (Medium Impact)

**Documented (`architecture/schemas.md` lines 89-91):**
```python
class RSSConfig(BaseModel):
    item_path: str = "entries"
    field_mappings: dict[str, str]
```

**Actual Implementation (`schemas/source.py` lines 29-39):**
```python
class RSSConfig(BaseModel):
    feed_url: str = Field(..., min_length=1)
    max_items: int = Field(default=50, ge=1, le=200)
    request_timeout: int = Field(default=15, ge=5, le=60)
    user_agent: str = "AINewsBot/1.0"
    min_content_length: int = Field(
        default=200,
        ge=0,
        le=5000,
        description="If feed content is shorter than this, scrape the article page",
    )
```

The documented schema appears to be an older version. The actual implementation has completely different fields focused on RSS feed handling.

### 3. APIConfig Schema Different from Documented
**Status:** DISCREPANCY (Medium Impact)

**Documented (`architecture/schemas.md` lines 93-96):**
```python
class APIConfig(BaseModel):
    item_path: str
    auth_header: str | None = None
    pagination: PaginationConfig | None = None
```

**Actual Implementation (`schemas/source.py` lines 42-55):**
```python
class APIConfig(BaseModel):
    list_url: str = Field(..., min_length=1)
    list_method: str = "json_array"
    list_items_path: Optional[str] = None
    max_items: int = Field(default=30, ge=1, le=200)
    item_url: Optional[str] = None
    item_method: str = "json_object"
    fields: dict[str, str] = Field(default_factory=dict)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    request_timeout: int = 15
    user_agent: str = "AINewsBot/1.0"
    api_key: Optional[str] = None
    auth_header: Optional[str] = None
```

The documented schema appears outdated. The actual implementation has many more fields.

### 4. WebConfig Schema Different from Documented
**Status:** DISCREPANCY (Medium Impact)

**Documented (`architecture/schemas.md` lines 98-102):**
```python
class WebConfig(BaseModel):
    item_css: str
    field_selectors: dict[str, str]
    pagination: PaginationConfig | None = None
    follow_links: bool = False
```

**Actual Implementation (`schemas/source.py` lines 87-95):**
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
```

The documented schema appears outdated. The actual implementation uses `ListingConfig` and `ArticleSelectors` composite objects.

### 5. PaginationConfig Type Literal
**Status:** DISCREPANCY (Low Impact)

**Documented (`architecture/schemas.md` line 105):**
```python
class PaginationConfig(BaseModel):
    type: Literal["cursor", "offset", "page"]
```

**Actual Implementation (`schemas/source.py` lines 58-69):**
```python
class PaginationConfig(BaseModel):
    enabled: bool = False
    type: str = "next_link"
    next_link_selector: Optional[str] = None
    max_pages: int = 3

    @field_validator("type")
    @classmethod
    def validate_pagination_type(cls, v):
        if v not in ("next_link", "query_param", "none"):
            raise ValueError(f"Unknown pagination type '{v}'")
        return v
```

The actual implementation uses string validation with different values: `"next_link"`, `"query_param"`, `"none"` instead of `"cursor"`, `"offset"`, `"page"`.

---

## Bugs Identified

### CRITICAL BUG: Duplicate ADAPTER_CONFIGS Definition in schemas/source.py

**File:** `schemas/source.py`

**Issue:** There are TWO definitions of `ADAPTER_CONFIGS` in the same file:

**First definition (lines 98-102):**
```python
ADAPTER_CONFIGS: dict[str, type[BaseModel]] = {
    "rss": RSSConfig,
    "api": APIConfig,
    "web": WebConfig,
}
```

This is used by the `SourceConfig.validate_adapter_config` field_validator (lines 123-130).

**However, this same dictionary is REDEFINED later in `schemas/llm.py` (lines 74-79):**
```python
ADAPTER_CONFIGS: dict[str, type[BaseModel]] = {
    "ollama": OllamaConfig,
    "openai": OpenAIConfig,
    "anthropic": AnthropicConfig,
    "gemini": GeminiConfig,
}
```

**Bug:** The `SourceConfig.validate_adapter_config` validator at line 127 calls:
```python
if source_type in ADAPTER_CONFIGS:
```

This check will FAIL for source types "rss", "api", "web" because by the time this runs, `ADAPTER_CONFIGS` has been reassigned to the LLM provider configs in `schemas/llm.py`.

**Root Cause:** Both files define `ADAPTER_CONFIGS` as a module-level variable. Since Python imports are singleton, when `schemas/source.py` imports from `schemas/llm.py`, the later definition overwrites the earlier one.

**Impact:** Any attempt to validate a `SourceConfig` with adapter-specific config will fail silently or raise a confusing error.

**Fix Required:** Rename one of the `ADAPTER_CONFIGS` dictionaries to avoid collision. Suggested rename for `schemas/llm.py`:
```python
LLM_ADAPTER_CONFIGS: dict[str, type[BaseModel]] = {
    "ollama": OllamaConfig,
    "openai": OpenAIConfig,
    "anthropic": AnthropicConfig,
    "gemini": GeminiConfig,
}
```

---

## Improvement Suggestions

### 1. Document the actual adapter config schemas in architecture/schemas.md

The adapter configs (`RSSConfig`, `APIConfig`, `WebConfig`) documented in the architecture file are significantly different from the actual implementation. The documentation should be updated to reflect:

- Actual field names and types
- The composite object pattern used for `WebConfig` (`ListingConfig`, `ArticleSelectors`)
- The pagination configuration approach

### 2. Add PaginationConfig to architecture/schemas.md

The `PaginationConfig` class with its `enabled`, `type`, `next_link_selector`, and `max_pages` fields is missing from the documentation entirely.

### 3. Document ListingConfig and ArticleSelectors

The `ListingConfig` and `ArticleSelectors` classes in `schemas/source.py` are not documented in `architecture/schemas.md`.

### 4. Update SourceType documentation

The `SourceType` enum in `schemas/source.py` (lines 12-15) should be documented:
```python
class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    WEB = "web"
```

### 5. Consider documenting the field_validator chain

The `SourceConfig` class has two field validators:
- `validate_type` (lines 114-121) - validates source type
- `validate_adapter_config` (lines 123-130) - validates config against adapter schema

This validation chain is an important architectural pattern that should be documented.

### 6. Document the common.py layer violation

As noted in the code comments (lines 72-73 and 86-87 in `schemas/common.py`), there is an intentional layer violation where `schemas/` imports from `services/`. This should be documented in the architecture.

---

## Questions for Architecture

### Q1: What is the intended PaginationConfig type values?

The implementation uses `"next_link"`, `"query_param"`, `"none"` but the old documentation shows `"cursor"`, `"offset"`, `"page"`. Which is correct for the current design?

### Q2: Should we keep the duplicate ADAPTER_CONFIGS names?

Given that `source.py` and `llm.py` both define `ADAPTER_CONFIGS` for different purposes, should we:
- Rename both to be more specific (e.g., `SOURCE_ADAPTER_CONFIGS`, `LLM_ADAPTER_CONFIGS`)?
- Keep as-is since they're in different modules (though the import issue remains)?

### Q3: Are the old RSS/API/WebConfig schemas in the documentation remnants of a previous design?

The significant differences between documented and actual adapter configs suggests either:
- The documentation was never updated after a refactor
- The actual implementation diverged from the documented design

Which should be considered the source of truth?

---

## Summary Table

| Claim | Status | Notes |
|-------|--------|-------|
| StageConfig is stub with only `tools` field | VERIFIED | |
| PipelineRootConfig structure complete | VERIFIED | |
| SourceConfig has adapter_config validator | VERIFIED | But has bug with duplicate ADAPTER_CONFIGS |
| RSSConfig schema accuracy | DISCREPANCY | Documented fields don't match actual |
| APIConfig schema accuracy | DISCREPANCY | Documented fields don't match actual |
| WebConfig schema accuracy | DISCREPANCY | Documented fields don't match actual |
| PaginationConfig type values | DISCREPANCY | Different type values in doc vs code |
| SelectionResult schema | VERIFIED | |
| ResearchBrief schema | VERIFIED | |
| CondensedArticle schema | VERIFIED | |
| ExecutiveSummary schema | VERIFIED | |
| NewsletterBrief no preamble/footer | VERIFIED | |
| NewsletterArticle schema | VERIFIED | |
| SelectArticleTask schema | VERIFIED | |
| ProcessItemTask schema | VERIFIED | |
| GenerateNewsletterTask schema | VERIFIED | |
| SendEmailTask schema | VERIFIED | |
| CleanupArticleVersionsTask schema | VERIFIED | |

---

## Recommendations

1. **Immediate:** Fix the duplicate `ADAPTER_CONFIGS` bug by renaming the LLM provider configs dictionary
2. **High Priority:** Update `architecture/schemas.md` to match actual adapter config implementations
3. **Medium Priority:** Add missing schemas to documentation (PaginationConfig, ListingConfig, ArticleSelectors, SourceType enum)
4. **Low Priority:** Document the intentional layer violation in common.py

# Schemas Module Architecture Review

## Summary

The architecture document `architecture/schemas.md` is **largely accurate** but has several discrepancies with the actual implementation. Most discrepancies are already noted in the document via "Note:" corrections, but a few claims need correction.

---

## Verified Claims

### File Inventory — VERIFIED
| File | Models | Purpose | Status |
|------|--------|---------|--------|
| `pipeline.py` | `PipelineRootConfig`, stage configs | Pipeline stage configuration | ✓ |
| `source.py` | `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig` | Source adapter configuration | ✓ |
| `llm.py` | Provider definitions | LLM/search provider settings | ✓ |
| `llm_responses.py` | `SelectionResult`, `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief` | LLM response schemas | ✓ |
| `tasks.py` | Task input validation | Celery task input validation | ✓ |
| `topic.py` | Topic definitions | Topic configuration | ✓ |
| `webhook.py` | `WebhookCreate`, `WebhookResponse` | Webhook configuration | ✓ |

Additional files not in inventory: `schemas/common.py`, `schemas/item.py`, `schemas/admin.py`, `schemas/search.py`, `schemas/__init__.py`.

---

## Discrepancies and Issues

### 1. `source.py` — SourceConfig Field Names DO NOT MATCH Document

**Document claims (architecture/schemas.md:79-86):**
```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str
    type: str                          # "rss", "api", or "web"
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any]             # Adapter-specific configuration
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)
```

**Actual implementation (schemas/source.py:105-112):**
```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)  # + min/max_length constraint
    type: str
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any] = Field(default_factory=dict)  # + default_factory
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)
```

**Issue:** Document omits `min_length=1, max_length=128` on `name` and `default_factory=dict` on `config`. Document does not mention the `validate_type` field validator on `type`.

---

### 2. `source.py` — RSSConfig, APIConfig, WebConfig DO NOT MATCH Document

**Document claims (architecture/schemas.md:89-101):**
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

**Actual implementation (schemas/source.py:29-96):**

The actual adapters use **completely different schemas**:

```python
class RSSConfig(BaseModel):
    feed_url: str = Field(..., min_length=1)
    max_items: int = Field(default=50, ge=1, le=200)
    request_timeout: int = Field(default=15, ge=5, le=60)
    user_agent: str = "AINewsBot/1.0"
    min_content_length: int = Field(default=200, ge=0, le=5000, ...)

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

**Additionally, there are classes the document never mentions:**
- `PaginationConfig` — actual implementation has `enabled`, `type`, `next_link_selector`, `max_pages` (NOT the three variants in the doc)
- `ListingConfig` — contains `card_selector`, `link_selector`, `link_attribute`, `pagination`
- `ArticleSelectors` — contains `title_selector`, `author_selector`, `date_selector`, `date_attribute`, `body_selector`
- `SourceType(str, Enum)` — enum with RSS, API, WEB values
- `MatchMode(str, Enum)` — enum with KEYWORD, CONTEXTUAL values

**Issue:** MAJOR — Document's adapter configs are completely fictional. The document shows generic/stub-like field names (`item_path`, `field_mappings`, `item_css`, `field_selectors`) that don't exist in the actual code. The actual implementation has detailed, real fields appropriate for real RSS/API/Web crawling.

---

### 3. `source.py` — PaginationConfig DOES NOT MATCH Document

**Document claims (architecture/schemas.md:104-109):**
```python
class PaginationConfig(BaseModel):
    type: Literal["cursor", "offset", "page"]
    next_button_css: str | None = None
    cursor_path: str | None = None
    offset_param: str | None = None
    limit_param: str | None = None
```

**Actual implementation (schemas/source.py:58-69):**
```python
class PaginationConfig(BaseModel):
    enabled: bool = False
    type: str = "next_link"  # NOT Literal - just a str with validator
    next_link_selector: Optional[str] = None
    max_pages: int = 3

    @field_validator("type")
    @classmethod
    def validate_pagination_type(cls, v):
        if v not in ("next_link", "query_param", "none"):
            raise ValueError(f"Unknown pagination type '{v}'")
        return v
```

**Issue:** Document claims `Literal["cursor", "offset", "page"]` but actual has `str` with values `next_link`, `query_param`, `none`. Also missing `enabled` and `max_pages` fields.

---

### 4. `llm_responses.py` — CondensedArticle WHY_IT_MATTERS Has Default

**Document claim (architecture/schemas.md:168):**
```python
class CondensedArticle(BaseModel):
    # ...
    why_it_matters: str                      # Additional fields not in doc
```

**Actual implementation (schemas/llm_responses.py:104-107):**
```python
class CondensedArticle(BaseModel):
    # ...
    why_it_matters: str = Field(
        default="",
        description="1-2 sentences on why this matters to the reader...",
    )
```

**Issue:** `why_it_matters` has a `default=""` in code, but document shows no default. Minor.

---

### 5. `source.py` — CRIT-3 Fix: Field Validator for Adapter Config IS Implemented

**Document note (architecture/schemas.md:86):**
> `config: dict[str, Any]` — Adapter-specific configuration

**Actual implementation (schemas/source.py:123-130):**
```python
@field_validator("config")
@classmethod
def validate_adapter_config(cls, v, info):
    source_type = info.data.get("type")
    if source_type in ADAPTER_CONFIGS:
        adapter_config = ADAPTER_CONFIGS[source_type]
        return adapter_config.model_validate(v).model_dump()
    return v
```

**Status:** CRIT-3 fix is VERIFIED — the field validator IS implemented and validates adapter config against the appropriate schema based on source type.

---

### 6. `source.py` — Additional `validate_type` Field Validator

**Actual implementation (schemas/source.py:114-121):**
```python
@field_validator("type")
@classmethod
def validate_type(cls, v):
    if v not in ADAPTER_CONFIGS:
        raise ValueError(
            f"Unknown source type '{v}'. Known: {list(ADAPTER_CONFIGS.keys())}"
        )
    return v
```

**Issue:** Document does not mention this validator. This is an additional validation layer beyond what the document describes.

---

### 7. `llm_responses.py` — Additional Models Not in Document

**Models not mentioned in document but present in code:**

- `SubagentResponse` (llm_responses.py:164-173)
- `ResearchSynthesisResponse` (llm_responses.py:176-178)
- `EditContextualizationResponse` (llm_responses.py:180-183)
- `ToolCall` (llm_responses.py:186-189)
- `ToolResult` (llm_responses.py:192-195)
- `ToolCallingResponse` (llm_responses.py:198-202)

---

### 8. `tasks.py` — ProcessItemTask Has Validators

**Document note (architecture/schemas.md:211):**
> Note: actual implementation differs from older documentation

**Actual implementation (schemas/tasks.py:103-117):**
```python
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
```

**Issue:** Document correctly notes the discrepancy but doesn't detail these validators.

---

## Verified Correct Claims

### StageConfig is a Stub — VERIFIED
**Document claim (architecture/schemas.md:19, 28-32):**
> **Note:** `StageConfig` is a stub with only `tools: list[str]`.

**Actual implementation (schemas/pipeline.py:140-146):**
```python
class StageConfig(BaseModel):
    """Pipeline stage configuration stub.

    Currently only defines tools list. The actual stage configuration is handled
    by SubagentStageConfig and RoleConfig. This stub exists for future extensibility.
    """
    tools: list[str] = Field(default_factory=list)
```

Confirmed — StageConfig is indeed just a stub.

### NewsletterBrief Missing Fields — VERIFIED
**Document claim (architecture/schemas.md:190-191):**
> Note: actual model does NOT have preamble, footer, or articles fields
> These were in older documentation but are not implemented

**Actual implementation (schemas/llm_responses.py:142-148):**
```python
class NewsletterBrief(BaseModel):
    themes: list[str]
    highlights: list[str]
    connections: list[str] = Field(default_factory=list)
```

Confirmed — NewsletterBrief only has `themes`, `highlights`, `connections`.

### ExecutiveSummary Single Field — VERIFIED
**Document claim (architecture/schemas.md:180):**
> Note: single 'summary' field (not 6 fields)

**Actual implementation (schemas/llm_responses.py:151-158):**
```python
class ExecutiveSummary(BaseModel):
    summary: str = Field(description="3-4 paragraph executive summary...")
```

Confirmed — only `summary` field.

### ResearchBrief Key Claims Type — VERIFIED
**Document claim (architecture/schemas.md:131):**
> Note: list[KeyClaim] not list[str]

**Actual implementation (schemas/llm_responses.py:53-57):**
```python
class ResearchBrief(BaseModel):
    key_claims: list[KeyClaim] = Field(description="Factual claims with source attribution")
```

Confirmed.

### ResearchBrief Context Notes — VERIFIED
**Document claim (architecture/schemas.md:135):**
> Note: 'context_notes' not 'context'

**Actual implementation (schemas/llm_responses.py:67-70):**
```python
class ResearchBrief(BaseModel):
    context_notes: str = Field(default="", description="Additional context...")
```

Confirmed.

---

## Bug Reports

### BUG-1: Document's Source Adapter Schemas Are Inaccurate
- **Severity:** High
- **File:** `architecture/schemas.md` lines 89-101
- **Description:** The document shows `RSSConfig`, `APIConfig`, and `WebConfig` with generic field names (`item_path`, `field_mappings`, `item_css`, `field_selectors`, `pagination: PaginationConfig | None`) that **do not exist in the actual code**. The actual implementation has completely different, detailed fields appropriate for real RSS feed reading, API calling, and web scraping.
- **Fix:** Update the document to match the actual schemas in `schemas/source.py`.

### BUG-2: Document's PaginationConfig Is Inaccurate
- **Severity:** High
- **File:** `architecture/schemas.md` lines 104-109
- **Description:** Document shows `Literal["cursor", "offset", "page"]` but actual is `str` with values `"next_link"`, `"query_param"`, `"none"`. Document also omits `enabled` and `max_pages` fields.
- **Fix:** Update the document to match actual `PaginationConfig` in `schemas/source.py:58-69`.

### BUG-3: Document Omits SourceConfig Field Validators
- **Severity:** Medium
- **File:** `architecture/schemas.md` lines 79-86
- **Description:** Document shows `SourceConfig` without field validators, but the actual code has `validate_type` and `validate_adapter_config` validators.
- **Fix:** Add documentation of the validators or at least note their existence.

### BUG-4: Document's LLM Provider Schemas Section Is Empty
- **Severity:** Medium
- **File:** `architecture/schemas.md` line 11 (llm.py row) and lines not present
- **Description:** The document lists `llm.py` with "Provider definitions" but provides no schema details. The file contains `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig` — none of which are documented.
- **Fix:** Add schema details for LLM provider configurations.

### BUG-5: Document's File Inventory Missing Several Files
- **Severity:** Low
- **File:** `architecture/schemas.md` line 5-16 (File Inventory table)
- **Description:** Inventory misses `common.py`, `item.py`, `admin.py`, `search.py`, `__init__.py`
- **Fix:** Add these to the inventory or note they contain supporting code.

---

## Improvement Recommendations

1. **High Priority — Update adapter config schemas in the document** to match the actual `RSSConfig`, `APIConfig`, `WebConfig`, `PaginationConfig`, `ListingConfig`, `ArticleSelectors` implementations.

2. **High Priority — Document field validators** for `SourceConfig` (`validate_type`, `validate_adapter_config`), as these are critical for understanding the validation behavior.

3. **Medium Priority — Add LLM provider schemas** to document the provider configuration models in `llm.py`.

4. **Low Priority — Add missing files to inventory** (`common.py`, `item.py`, `admin.py`, `search.py`).

5. **Low Priority — Add subagent response schemas** to document `SubagentResponse`, `ResearchSynthesisResponse`, `EditContextualizationResponse`, `ToolCall`, `ToolResult`, `ToolCallingResponse`.
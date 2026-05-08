# Architecture Review: schemas.md

**Date:** 2026-05-08  
**Reviewer:** Architecture Review Agent  
**Document:** `/Users/davidbowman/projects/ainews/architecture/schemas.md`

---

## Summary

| Category | Status |
|----------|--------|
| File Inventory | Partially accurate (missing files exist, wrong files listed) |
| Pipeline Configuration | Largely incorrect (different class structure) |
| Source Configuration | Completely different structure |
| LLM Responses | Partially accurate (field name and type differences) |
| Task Validation | Completely different (wrong model names, different fields) |

---

## 1. Verified Items (Correct)

### File Inventory (Partially Correct)

**Document says:** `pipeline.py`, `source.py`, `llm.py`, `llm_responses.py`, `tasks.py`, `topic.py`, `webhook.py`

**Actual files in `schemas/`:**
- `__init__.py` (empty - documented but correctly noted)
- `pipeline.py` - EXISTS (correct)
- `source.py` - EXISTS (correct)
- `llm.py` - EXISTS (correct)
- `llm_responses.py` - EXISTS (correct)
- `tasks.py` - EXISTS (correct)
- `topic.py` - EXISTS (correct)
- `webhook.py` - EXISTS (correct)
- `common.py` - EXISTS (NOT documented - missing from inventory)
- `item.py` - EXISTS (NOT documented - missing from inventory)
- `search.py` - EXISTS (NOT documented - missing from inventory)
- `admin.py` - EXISTS (NOT documented - missing from inventory)

**Finding:** Document correctly lists 7 files but misses 4 additional files that exist. The undocumented files serve important purposes:
- `common.py` - Shared utilities (env var resolution, config loading, caching)
- `item.py` - `RawItem` for raw item representation
- `search.py` - Search provider configuration
- `admin.py` - Admin API request validation

### StageConfig Only Has `tools` Field (Correct)

**Document says:** `StageConfig` has 7 fields (`enabled`, `model`, `prompt_variant`, `temperature`, `max_tokens`, `timeout`, `tools`)

**Actual (`schemas/pipeline.py:140-141`):**
```python
class StageConfig(BaseModel):
    tools: list[str] = Field(default_factory=list)
```

**Verification:** CONFIRMED - `StageConfig` only has `tools` field. The documented 7-field version does not exist.

**Note:** The actual stage configuration is handled by `SubagentStageConfig` which has many fields (`enabled`, `provider`, `model`, `max_tokens`, `temperature`, `timeout_seconds`, `system_prompt`, `max_retries`, `retry_delay`, `task_template`, `tools`, `max_iterations`).

### CondensedArticle Uses `headline/tldr/body` (Correct)

**Document says:** `CondensedArticle` has `headline`, `tldr`, `body`

**Actual (`schemas/llm_responses.py:101-129`):**
```python
class CondensedArticle(BaseModel):
    headline: str  # EXISTS
    tldr: str      # EXISTS
    body: str      # EXISTS
    # Additional undocumented fields:
    why_it_matters: str
    key_points: list[str]
    what_to_watch: str
    citations: list[CitationItem]
    original_attribution: OriginalAttribution
    tags: list[str]
```

**Verification:** CONFIRMED that `headline`, `tldr`, `body` exist. Document correctly identifies these fields but fails to mention the additional fields present.

### NewsletterBrief Uses `themes/highlights/connections` (Correct - Type Difference)

**Document says:** `NewsletterBrief` has `themes: str`, `highlights: list[str]`, `connections: str`

**Actual (`schemas/llm_responses.py:142-148`):**
```python
class NewsletterBrief(BaseModel):
    themes: list[str]           # Document says str, actual is list[str]
    highlights: list[str]        # CORRECT
    connections: list[str]      # Document says str, actual is list[str]
    # Missing: newsletter_id, subject (documented but don't exist)
```

**Verification:** CONFIRMED - Field names match but `themes` and `connections` are `list[str]` not `str` as documented.

---

## 2. Discrepancies

### 2.1 Pipeline Configuration (`pipeline.py`) - COMPLETELY DIFFERENT

**Document says:**
```python
class PipelineRootConfig(BaseModel):
    version: str = "1.0"
    stages: dict[str, StageConfig]
    newsletter: NewsletterConfig
    subagent: SubagentConfig
    memory: MemoryConfig
```

**Actual (`schemas/pipeline.py:144-153`):**
```python
class PipelineRootConfig(BaseModel):
    pipeline: PipelineConfig           # Different - wrapped in pipeline key
    newsletter: NewsletterConfig        # EXISTS but different fields
    newsletter_pipeline: NewsletterPipelineConfig  # NOT DOCUMENTED
    subagent: SubagentConfig            # EXISTS but different structure
    memory: MemoryConfig                # EXISTS but different fields
    stages: dict[str, StageConfig]     # EXISTS but StageConfig is stub
    schedule: dict                      # NOT DOCUMENTED
```

**Major Issues:**
1. `PipelineRootConfig.pipeline` wraps stage roles in a `PipelineConfig` object
2. `NewsletterConfig` has different fields (`max_articles`, `send_time`, `timezone`, `site_url`, `prep_minutes` vs documented `daily_send_time`, `enable_topic_newsletters`, `batch_size`, `retry_attempts`)
3. `newsletter_pipeline` section is NOT documented
4. `SubagentConfig` has different structure (nested `default`, `research`, `edit`, `chains`)
5. `MemoryConfig` has different fields

### 2.2 ResearchBrief - Different Structure

**Document says:**
```python
class ResearchBrief(BaseModel):
    article_id: int
    key_claims: list[str]
    context: str
    citations: list[Citation]
    related_trends: list[str]
    background: str | None = None
```

**Actual (`schemas/llm_responses.py:53-81`):**
```python
class ResearchBrief(BaseModel):
    # No article_id field
    source_summary: str           # NOT DOCUMENTED
    key_claims: list[KeyClaim]    # list[KeyClaim] not list[str]
    direct_quotes: list[DirectQuote]  # NOT DOCUMENTED
    external_sources: list[ExternalSource]  # NOT DOCUMENTED
    related_articles: list[RelatedArticle]  # NOT DOCUMENTED
    context_notes: str            # DOCUMENTED as "context"
    newsworthiness: str           # NOT DOCUMENTED
    impact_score: int             # NOT DOCUMENTED
    # Missing: citations, related_trends, background
```

**Field Mapping:**
| Documented | Actual | Type Change |
|------------|--------|-------------|
| `key_claims: list[str]` | `key_claims: list[KeyClaim]` | String to nested model |
| `context: str` | `context_notes: str` | Field renamed |
| `citations: list[Citation]` | REMOVED | Not present |
| `related_trends: list[str]` | REMOVED | Not present |
| `background: str | None` | REMOVED | Not present |
| `article_id: int` | REMOVED | Not present |

**Additional Undocumented Fields:**
- `source_summary: str`
- `direct_quotes: list[DirectQuote]`
- `external_sources: list[ExternalSource]`
- `related_articles: list[RelatedArticle]`
- `newsworthiness: str`
- `impact_score: int`

### 2.3 SelectionResult - Field Name Difference

**Document says:**
```python
class SelectionResult(BaseModel):
    score: int = Field(ge=1, le=10)
    confidence: Literal["low", "medium", "high"]
    reasoning: str
    key_topics: list[str]
    impact_summary: str | None = None
```

**Actual (`schemas/llm_responses.py:16-22`):**
```python
class SelectionResult(BaseModel):
    selected: bool            # NOT DOCUMENTED - new field
    score: int = Field(ge=1, le=10)   # EXISTS
    reason: str               # DOCUMENTED as "reasoning"
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")  # Same
    key_topics: list[str]      # EXISTS
    impact_summary: Optional[str]  # EXISTS
```

**Discrepancy:** `reasoning` in document is `reason` in actual implementation.

### 2.4 ExecutiveSummary - Completely Different

**Document says:**
```python
class ExecutiveSummary(BaseModel):
    date: date
    theme: str
    overview: str  # 2-4 sentences
    highlights: list[str]  # 3-5 key developments
    outlook: str | None = None
    article_count: int
```

**Actual (`schemas/llm_responses.py:151-158`):**
```python
class ExecutiveSummary(BaseModel):
    summary: str  # DOCUMENTED as "overview"
    # Missing ALL documented fields: date, theme, highlights, outlook, article_count
```

**Missing Fields:** `date`, `theme`, `highlights`, `outlook`, `article_count`

### 2.5 Source Configuration (`source.py`) - COMPLETELY DIFFERENT

**Document says:**
```python
class SourceConfig(BaseModel):
    name: str
    type: Literal["rss", "api", "web"]
    url: str
    adapter_config: RSSConfig | APIConfig | WebConfig
    enabled: bool = True
    crawl_interval_minutes: int = 30
```

**Actual (`schemas/source.py:105-122`):**
```python
class SourceConfig(BaseModel):
    id: str                      # DOCUMENTED as "name"
    name: str                    # EXISTS
    type: str                    # DOCUMENTED correctly but type is string not Literal
    enabled: bool = True         # EXISTS
    schedule_minutes: int        # DOCUMENTED as "crawl_interval_minutes"
    config: dict[str, Any]        # DOCUMENTED as "adapter_config" but different type
    topics: TopicMatchConfig     # NOT DOCUMENTED
```

**Config Classes:**
| Documented | Actual | Status |
|------------|--------|--------|
| `RSSConfig` with `item_path`, `field_mappings` | `RSSConfig` with `feed_url`, `max_items`, `request_timeout`, `user_agent`, `min_content_length` | COMPLETELY DIFFERENT |
| `APIConfig` with `item_path`, `auth_header`, `pagination` | `APIConfig` with `list_url`, `list_method`, `list_items_path`, `item_url`, `item_method`, `fields`, `filters`, `metadata`, `api_key`, `auth_header` | COMPLETELY DIFFERENT |
| `WebConfig` with `item_css`, `field_selectors`, `pagination`, `follow_links` | `WebConfig` with `base_url`, `listing_url`, `listing: ListingConfig`, `article: ArticleSelectors`, `request_delay_min`, `request_delay_max`, `max_retries`, `user_agent` | COMPLETELY DIFFERENT |

### 2.6 LLM Provider Configuration (`llm.py`) - DIFFERENT Structure

**Document:** Mentions "Provider definitions" but provides no actual schema.

**Actual (`schemas/llm.py`):**
```python
class OllamaConfig(BaseModel)
class OpenAIConfig(BaseModel)
class AnthropicConfig(BaseModel)
class GeminiConfig(BaseModel)
class LLMProvidersConfig(BaseModel)
```

**Finding:** Document does not show the actual provider config schemas. The `ProviderDef` class in `common.py` is also undocumented.

### 2.7 Task Validation (`tasks.py`) - DIFFERENT Model Names and Fields

**Document says:**
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

**Actual (`schemas/tasks.py`):**
```python
class SelectArticleTask(BaseModel):
    article_id: int
    run_id: Optional[int] = None

class GenerateNewsletterTask(BaseModel):
    dry_run_email: Optional[str] = None
    run_id: Optional[int] = None

class SendEmailTask(BaseModel):
    email: str
    subject: str
    html: str
    unsub_url: str

class CleanupArticleVersionsTask(BaseModel):
    days_to_keep: int = 90
    dry_run: bool = False

class ProcessItemTask(BaseModel):
    source_key: str
    source_name: str
    source_type: str
    external_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    text_content: Optional[str] = None
    raw_score: Optional[float] = None
    raw_metadata: Optional[dict] = None
    topics: Optional[list[str]] = None
    min_content_length: Optional[int] = None
    run_id: Optional[int] = None
```

**Discrepancies:**
| Documented | Actual | Notes |
|------------|--------|-------|
| `ProcessItemInput` | `ProcessItemTask` | Renamed |
| `SelectArticleInput` | `SelectArticleTask` | Renamed |
| `ResearchArticleInput` | NOT FOUND | Does not exist |
| `WriteArticleInput` | NOT FOUND | Does not exist |
| `EditArticleInput` | NOT FOUND | Does not exist |
| `ProcessItemTask` fields completely different | Different fields |

---

## 3. Issues Found

### Issue 1: Documentation is Inaccurate for StageConfig

**Problem:** The document describes `StageConfig` with 7 fields but the actual implementation only has `tools`. This creates confusion about the stage configuration system.

**Root Cause:** The document seems to describe `SubagentStageConfig` but labels it as `StageConfig`.

**Impact:** High - Developers referencing the documentation will have wrong expectations.

### Issue 2: ResearchBrief Completely Different

**Problem:** The documented `ResearchBrief` schema bears little resemblance to the actual implementation. The documented version has `article_id`, simple `list[str]` for `key_claims`, and fields like `citations`, `related_trends`, `background`. The actual implementation has complex nested types and completely different fields.

**Root Cause:** Likely a schema evolution without documentation update.

**Impact:** High - Any code generated based on documentation will be incompatible with actual API.

### Issue 3: ExecutiveSummary Missing Most Fields

**Problem:** The document shows 6 fields (`date`, `theme`, `overview`, `highlights`, `outlook`, `article_count`) but the actual implementation only has `summary: str`.

**Impact:** Medium - Newsletter generation code likely works but documentation is misleading.

### Issue 4: Task Schemas Are Wrong

**Problem:** Documented task input models (`ProcessItemInput`, `SelectArticleInput`, `ResearchArticleInput`, `WriteArticleInput`, `EditArticleInput`) do not exist in the codebase. The actual models have different names and structures.

**Impact:** High - Celery task validation based on documentation would fail.

### Issue 5: NewsletterArticle Has Different Fields

**Document says:**
```python
class NewsletterArticle(BaseModel):
    article_id: int
    title: str
    summary: str
    key_points: list[str]
    source_name: str
    url: str
```

**Actual (`schemas/llm_responses.py:135-140`):**
```python
class NewsletterArticle(BaseModel):
    headline: str         # DOCUMENTED as "title"
    summary: str          # EXISTS
    url: Optional[str]     # DOCUMENTED as required, actual is optional
    tags: list[str]       # NOT DOCUMENTED (replaces key_points, source_name)
    # Missing: article_id, key_points, source_name
```

**Impact:** Medium - Newsletter rendering based on documentation would use wrong field names.

---

## 4. Recommendations

### High Priority

1. **Update StageConfig Documentation**
   - Either document `SubagentStageConfig` as the actual stage configuration class
   - Or clarify that `StageConfig` is a minimal stub and actual configuration comes from `SubagentStageConfig`

2. **Rewrite ResearchBrief Section**
   - Document actual field names and types
   - Include nested models (`KeyClaim`, `DirectQuote`, `ExternalSource`, `RelatedArticle`)
   - Add new fields (`source_summary`, `newsworthiness`, `impact_score`)

3. **Fix Task Schemas Section**
   - Update task model names to match actual (`SelectArticleTask`, `GenerateNewsletterTask`, `SendEmailTask`, `CleanupArticleVersionsTask`, `ProcessItemTask`)
   - Document actual field structures

### Medium Priority

4. **Update ExecutiveSummary Documentation**
   - Either add missing fields to implementation
   - Or update documentation to reflect `summary: str` only

5. **Fix NewsletterArticle Documentation**
   - Change `title` to `headline`
   - Add `tags` field
   - Note that `article_id`, `key_points`, `source_name` are not present

6. **Document NewsletterBrief Types**
   - Note that `themes` and `connections` are `list[str]` not `str`

### Low Priority

7. **Add Missing Files to Inventory**
   - `common.py` - Shared utilities (important for understanding config loading)
   - `item.py` - `RawItem` model
   - `search.py` - Search provider config
   - `admin.py` - Admin API validation

8. **Add LLM Provider Schemas**
   - Document actual provider config classes (`OllamaConfig`, `OpenAIConfig`, etc.)

---

## 5. Summary of Required Documentation Updates

| Section | Required Action |
|---------|----------------|
| File Inventory | Add `common.py`, `item.py`, `search.py`, `admin.py` |
| StageConfig | Document `SubagentStageConfig` instead, or clarify StageConfig is a stub |
| ResearchBrief | Complete rewrite with actual fields and nested types |
| CondensedArticle | Add undocumented fields (`why_it_matters`, `what_to_watch`, `citations`, `original_attribution`, `tags`) |
| ExecutiveSummary | Either implement missing fields or update docs |
| NewsletterBrief | Fix types for `themes` and `connections` (list[str] not str) |
| NewsletterArticle | Change `title` to `headline`, add `tags`, note missing fields |
| SelectionResult | Change `reasoning` to `reason` |
| Source Configuration | Complete rewrite with actual field names and types |
| Task Validation | Complete rewrite with actual model names and fields |

---

## 6. Conclusion

The `schemas.md` documentation is significantly outdated and inaccurate. The file inventory is mostly correct but the actual schema definitions are largely wrong. This includes:

1. **Completely incorrect schemas:** Pipeline configuration, source configuration, task validation schemas
2. **Significantly different schemas:** ResearchBrief, ExecutiveSummary, SelectionResult
3. **Missing fields documented as present:** Most fields in ResearchBrief, ExecutiveSummary, NewsletterArticle
4. **Wrong field types:** NewsletterBrief themes/connections are lists not strings

The documentation requires a comprehensive update to reflect the current implementation. Any developer relying on this documentation for integration work would encounter significant errors.

---

*End of Review*

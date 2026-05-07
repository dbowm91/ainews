# Review 08: Schemas Architecture Review

## Context

Reviewed `architecture/schemas.md` documenting the expected Pydantic schemas architecture and compared against actual implementation in `schemas/` directory. This is a comprehensive fresh review building on prior work in `plans/08_schemas.md`.

---

## Executive Summary

The architecture documentation in `architecture/schemas.md` is significantly outdated. The documented schemas do not reflect the actual implementation - they appear to describe an older or planned design that was never fully synchronized with the code. Major structural differences exist across Pipeline, Source, LLM responses, and Task schemas.

---

## File Inventory

| File | Documented | Actual | Status |
|------|------------|--------|--------|
| `pipeline.py` | Yes | Yes | DISCREPANCY |
| `source.py` | Yes | Yes | DISCREPANCY |
| `llm.py` | Yes | Yes | VERIFIED |
| `llm_responses.py` | Yes | Yes | DISCREPANCY |
| `tasks.py` | Yes | Yes | DISCREPANCY |
| `topic.py` | Yes | Yes | VERIFIED |
| `webhook.py` | Yes | Yes | VERIFIED (created post prior review) |
| `common.py` | No | Yes | INFO |
| `admin.py` | No | Yes | INFO |
| `item.py` | No | Yes | INFO |
| `search.py` | No | Yes | INFO |

---

## Verification Details

### 1. Pipeline Configuration (`schemas/pipeline.py`)

| Documented Class | Actual Class | Status | Issue |
|------------------|--------------|--------|-------|
| `PipelineRootConfig` | `PipelineRootConfig` | DISCREPANCY | Structure differs significantly |
| `StageConfig` | `StageConfig` | DISCREPANCY | Documented has 7 fields, actual is empty stub |
| `NewsletterConfig` | `NewsletterConfig` | DISCREPANCY | Different fields |
| `SubagentConfig` | `SubagentConfig` | DISCREPANCY | Different nested structure |
| `MemoryConfig` | `MemoryConfig` | DISCREPANCY | Completely different structure |

**Documented `PipelineRootConfig` structure (from doc):**
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

**Actual `PipelineRootConfig` structure (from code):**
```python
class PipelineRootConfig(BaseModel):
    pipeline: PipelineConfig  # Contains selector, researcher, writer, editor, review
    newsletter: NewsletterConfig  # max_articles, send_time, timezone, site_url, prep_minutes
    newsletter_pipeline: NewsletterPipelineConfig
    subagent: SubagentConfig  # default, research, edit, chains
    memory: MemoryConfig  # ttl_days_*, consolidation_*, truncation_llm_*
    stages: dict[str, StageConfig]  # Stub - only has tools: list[str]
    schedule: dict

class StageConfig(BaseModel):
    tools: list[str] = Field(default_factory=list)  # EMPTY STUB - only field
```

**Discrepancy Analysis:**
- `StageConfig` is documented to have 7 fields (`enabled`, `model`, `prompt_variant`, `temperature`, `max_tokens`, `timeout`) but actual is an empty stub with only `tools: list[str]`
- `NewsletterConfig` documented fields (`daily_send_time`, `enable_topic_newsletters`, `batch_size`, `retry_attempts`) vs actual (`max_articles`, `send_time`, `timezone`, `site_url`, `prep_minutes`)
- `SubagentConfig` documented as simple flat structure, actual has nested `default`, `research`, `edit`, `chains`
- `MemoryConfig` documented with `embedding_model`, actual uses `truncation_llm_*` settings with no embedding model

---

### 2. Source Configuration (`schemas/source.py`)

| Documented Class | Actual Class | Status | Issue |
|------------------|--------------|--------|-------|
| `SourceConfig` | `SourceConfig` | DISCREPANCY | `type` is `str`, not `Literal["rss", "api", "web"]` |
| `RSSConfig` | `RSSConfig` | DISCREPANCY | Has `feed_url`, not documented `item_path` and `field_mappings` |
| `APIConfig` | `APIConfig` | DISCREPANCY | Different fields |
| `WebConfig` | `WebConfig` | DISCREPANCY | Different structure using `ListingConfig` and `ArticleSelectors` |
| `PaginationConfig` | `PaginationConfig` | DISCREPANCY | `type` is `str`, not `Literal["cursor", "offset", "page"]` |

**Documented `SourceConfig`:**
```python
class SourceConfig(BaseModel):
    name: str
    type: Literal["rss", "api", "web"]  # Actual: str
    url: str
    adapter_config: RSSConfig | APIConfig | WebConfig  # Actual: config: dict[str, Any]
    enabled: bool = True
    crawl_interval_minutes: int = 30  # Actual: schedule_minutes
```

**Actual `SourceConfig`:**
```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)
    type: str  # No Literal constraint
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any] = Field(default_factory=dict)  # Generic dict, not typed union
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)
```

---

### 3. LLM Responses (`schemas/llm_responses.py`)

| Documented Class | Actual Class | Status | Issue |
|------------------|--------------|--------|-------|
| `SelectionResult` | `SelectionResult` | VERIFIED | Has `selected: bool`, `key_topics`, `impact_summary` (post-fix) |
| `ResearchBrief` | `ResearchBrief` | DISCREPANCY | No `article_id`, no `Citation`, uses `key_claims` |
| `Citation` | N/A | DISCREPANCY | Class is named `CitationItem` or embedded as `CitationItem` |
| `CondensedArticle` | `CondensedArticle` | DISCREPANCY | Documented has `title`, `summary`, `word_count`. Actual has `headline`, `tldr`, `body` |
| `ExecutiveSummary` | `ExecutiveSummary` | DISCREPANCY | Documented has `date`, `theme`, `overview`, `highlights`, `outlook`, `article_count`. Actual has `summary: str` |
| `NewsletterBrief` | `NewsletterBrief` | DISCREPANCY | Documented has `newsletter_id`, `subject`, `preamble`, `articles`. Actual has `themes`, `highlights`, `connections` |
| `NewsletterArticle` | `NewsletterArticle` | VERIFIED | Now exists in code |

**Actual `SelectionResult` (verified):**
```python
class SelectionResult(BaseModel):
    selected: bool
    score: int = Field(ge=1, le=10)
    reason: str
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    key_topics: list[str] = Field(default_factory=list)
    impact_summary: Optional[str] = Field(default=None)
```

**Actual `ResearchBrief` vs Documented:**
```
Documented: article_id: int, key_findings: list[str], context: str, citations: list[Citation], related_trends: list[str], background: str | None
Actual:     source_summary: str, key_claims: list[KeyClaim], direct_quotes: list[DirectQuote], 
            external_sources: list[ExternalSource], related_articles: list[RelatedArticle], 
            context_notes: str, newsworthiness: str, impact_score: int
```

**Actual `CondensedArticle` vs Documented:**
```
Documented: article_id: int, title: str, summary: str, key_points: list[str], 
            implications: str | None, hook: str | None, word_count: int = Field(ge=100, le=600)
Actual:     headline: str, tldr: str, why_it_matters: str, body: str, key_points: list[str],
            what_to_watch: str, citations: list[CitationItem], original_attribution: OriginalAttribution, tags: list[str]
```

**Actual `ExecutiveSummary` vs Documented:**
```
Documented: date: date, theme: str, overview: str, highlights: list[str], 
            outlook: str | None, article_count: int
Actual:     summary: str (3-4 paragraph executive summary)
```

---

### 4. Task Validation (`schemas/tasks.py`)

| Documented Class | Actual Class | Status | Issue |
|------------------|--------------|--------|-------|
| `ProcessItemInput` | `ProcessItemTask` | DISCREPANCY | Naming convention mismatch |
| `SelectArticleInput` | `SelectArticleTask` | DISCREPANCY | Naming convention mismatch |
| `ResearchArticleInput` | N/A | DISCREPANCY | Class not found |
| `WriteArticleInput` | N/A | DISCREPANCY | Class not found |
| `EditArticleInput` | N/A | DISCREPANCY | Class not found |

**Issue:** All documented task input schemas use `*Input` suffix but actual classes use `*Task` suffix.

---

### 5. Webhook Schemas (`schemas/webhook.py`)

| Documented Class | Actual Class | Status |
|------------------|--------------|--------|
| `WebhookCreate` | `WebhookCreate` | VERIFIED |
| `WebhookResponse` | `WebhookResponse` | VERIFIED |

**Status:** Webhook schemas were created (after prior review) and now match documentation.

---

## Bug Findings

### Critical

1. **`StageConfig` is an empty stub** - Documented with 7 fields (`enabled`, `model`, `prompt_variant`, `temperature`, `max_tokens`, `timeout`) but actual is just `tools: list[str] = Field(default_factory=list)`. This class appears unused or incomplete.

2. **LLM response structures differ drastically** - `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, and `NewsletterBrief` all have completely different structures than documented. The documented schemas appear to describe an older or different design.

### High

3. **Task schema naming inconsistency** - Documented as `*Input` suffix, actual is `*Task` suffix. Classes `ProcessItemTask`, `SelectArticleTask`, `GenerateNewsletterTask`, `SendEmailTask`, `CleanupArticleVersionsTask` do not match documented names.

4. **`SourceConfig.type` lacks type constraint** - Documented as `Literal["rss", "api", "web"]` but actual is `str`. A validator exists but it's not a type-level constraint.

5. **`PaginationConfig.type` lacks type constraint** - Documented as `Literal["cursor", "offset", "page"]` but actual is `str` with a runtime validator.

### Medium

6. **`ResearchBrief` missing `article_id`** - Documented has `article_id: int` but actual does not.

7. **`CondensedArticle` lacks `word_count`** - Documented has `word_count: int = Field(ge=100, le=600)` but actual does not.

8. **`ExecutiveSummary` missing multiple fields** - Documented has `date`, `theme`, `overview`, `highlights`, `outlook`, `article_count` but actual only has `summary: str`.

9. **`NewsletterBrief` structure differs** - Documented has `newsletter_id`, `subject`, `preamble`, `articles: list[NewsletterArticle]`, `footer`. Actual has `themes`, `highlights`, `connections`.

10. **Missing `ResearchArticleInput`, `WriteArticleInput`, `EditArticleInput`** - Documented but not found in `tasks.py`.

---

## Improvement Opportunities

### 1. StageConfig Enhancement

**Reference:** `schemas/pipeline.py` line 140-142

The `StageConfig` class is documented as having substantial configuration options but is currently an empty stub:
```python
class StageConfig(BaseModel):
    tools: list[str] = Field(default_factory=list)
```

**Recommendation:** Either implement the documented StageConfig fields or remove from documentation. If the pipeline stages don't use this configuration, the documentation should reflect actual usage.

### 2. Task Schema Naming Convention

**Reference:** `schemas/tasks.py`

All task input schemas use `*Task` suffix (e.g., `SelectArticleTask`) but documentation shows `*Input` suffix (e.g., `SelectArticleInput`).

**Recommendation:** Standardize naming. If `*Task` is the intended convention, update documentation. If `*Input` is preferred, rename classes.

### 3. Source Type Literal

**Reference:** `schemas/source.py` line 106

```python
type: str  # Should be Literal["rss", "api", "web"]
```

**Recommendation:** Consider changing `SourceConfig.type` from `str` to `Literal["rss", "api", "web"]` for type-level safety. The validator at line 112-119 provides runtime checking but Pydantic's Literal type would be cleaner.

### 4. Pagination Type Literal

**Reference:** `schemas/source.py` line 58

```python
type: str = "next_link"  # Could be Literal["next_link", "query_param", "none"]
```

**Recommendation:** Consider using Literal type for PaginationConfig.type.

### 5. LLM Response Documentation Sync

**Reference:** `schemas/llm_responses.py`

The LLM response schemas (`ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief`) have evolved significantly from the documented structure.

**Recommendation:** Update `architecture/schemas.md` to reflect actual implementation, or refactor implementation to match documented design. Given the actual implementation is well-structured and used throughout the codebase, updating documentation is recommended.

### 6. Missing Task Input Schemas

**Reference:** `schemas/tasks.py`

Documented `ResearchArticleInput`, `WriteArticleInput`, `EditArticleInput` are not implemented. The tasks likely receive simple IDs directly without complex input validation.

**Recommendation:** Either implement these schemas for consistency, or remove from documentation if not needed.

---

## Specific Code References

| File | Line | Issue |
|------|------|-------|
| `schemas/pipeline.py` | 140-142 | `StageConfig` empty stub |
| `schemas/pipeline.py` | 51-57 | `NewsletterConfig` fields differ |
| `schemas/pipeline.py` | 120-125 | `SubagentConfig` structure differs |
| `schemas/pipeline.py` | 127-138 | `MemoryConfig` structure differs |
| `schemas/source.py` | 106 | `type: str` should be `Literal` |
| `schemas/source.py` | 58 | `PaginationConfig.type` should be `Literal` |
| `schemas/llm_responses.py` | 53-82 | `ResearchBrief` different structure |
| `schemas/llm_responses.py` | 101-130 | `CondensedArticle` different structure |
| `schemas/llm_responses.py` | 151-158 | `ExecutiveSummary` different structure |
| `schemas/llm_responses.py` | 142-149 | `NewsletterBrief` different structure |
| `schemas/tasks.py` | 33-42 | `SelectArticleTask` naming mismatch |
| `schemas/tasks.py` | 87-117 | `ProcessItemTask` naming mismatch |

---

## Action Items

### High Priority

1. **[HIGH]** Update `architecture/schemas.md` to reflect actual `StageConfig` structure (or implement missing fields)
2. **[HIGH]** Standardize task schema naming convention (`*Input` vs `*Task`)
3. **[HIGH]** Update LLM response documentation to match actual `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief` structures

### Medium Priority

4. **[MEDIUM]** Change `SourceConfig.type` from `str` to `Literal["rss", "api", "web"]`
5. **[MEDIUM]** Change `PaginationConfig.type` to `Literal["next_link", "query_param", "none"]`
6. **[MEDIUM]** Add `article_id: int` to `ResearchBrief` if needed by pipeline
7. **[MEDIUM]** Add `word_count: int` to `CondensedArticle` if needed for quality checks

### Low Priority

8. **[LOW]** Document the extra files (`common.py`, `admin.py`, `item.py`, `search.py`) in architecture or remove if unnecessary
9. **[LOW]** Implement missing task input schemas (`ResearchArticleInput`, `WriteArticleInput`, `EditArticleInput`) or remove from documentation

---

## Conclusion

The `architecture/schemas.md` documentation is significantly out of sync with the actual implementation. The most impactful issues are:

1. **StageConfig** being an empty stub when documented with 7 fields
2. **LLM response schemas** having completely different structures than documented
3. **Task schema naming** using `*Task` suffix instead of documented `*Input`

The implementation appears more mature and well-structured than the documentation suggests. The recommended path forward is to update `architecture/schemas.md` to accurately reflect the current implementation rather than refactoring working code to match outdated documentation.

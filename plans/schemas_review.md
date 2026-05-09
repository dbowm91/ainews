# Schemas Architecture Review Plan

## Verified Claims
- **StageConfig is a stub** (pipeline.py:140-141): `tools: list[str] = Field(default_factory=list)` - CONFIRMED. Doc note is accurate.
- **SelectionResult uses `reason` not `reasoning`** (llm_responses.py:19): Field is `reason: str` - CONFIRMED.
- **ResearchBrief uses `context_notes` not `context`** (llm_responses.py:67): Field is `context_notes: str` - CONFIRMED.
- **NewsletterBrief `themes: list[str]`** (llm_responses.py:143): `themes: list[str]` - CONFIRMED.
- **NewsletterBrief `connections: list[str]`** (llm_responses.py:145): `connections: list[str]` - CONFIRMED.
- **ExecutiveSummary has single `summary` field** (llm_responses.py:151-158): `summary: str` - CONFIRMED.
- **PipelineRootConfig has `pipeline`, `newsletter`, `newsletter_pipeline`, `subagent`, `memory`, `stages`, `schedule`** (pipeline.py:144-153): CONFIRMED.

## Discrepancies

### 1. PipelineRootConfig missing `version` field
- **Doc says**: `version: str = "1.0"` should exist
- **Actual**: No `version` field in PipelineRootConfig (pipeline.py:144-153)
- **Impact**: Config loading may fail if pipeline.yaml contains a `version` key that isn't expected

### 2. MemoryConfig is COMPLETELY DIFFERENT from documented
- **Doc describes** (architecture/schemas.md:67-72):
  ```python
  enabled: bool = True
  consolidate_interval_hours: int = 24
  max_entries_per_topic: int = 100
  embedding_model: str = "text-embedding-ada-002"
  ttl_days: int = 365
  ```
- **Actual** (pipeline.py:127-137):
  ```python
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
- **Impact**: Documentation is completely wrong - no `enabled`, `max_entries_per_topic`, `embedding_model`, or `ttl_days` fields exist

### 3. NewsletterConfig missing `enable_topic_newsletters` and `batch_size`
- **Doc says** (architecture/schemas.md:35-43): Should have `enable_topic_newsletters: bool = True` and `batch_size: int = 500`
- **Actual** (pipeline.py:51-56): Neither field exists
- **Doc incorrectly states `max_articles: int = 20`**: Actual default is `10` (line 52: `Field(default=10, ge=1, le=50)`)
- **Doc incorrectly states `site_url: str` with no default**: Actual has `Field(default="https://ainews.dev")` (line 55)

### 4. SelectionResult `confidence` is wrong type
- **Doc says**: `confidence: Literal["low", "medium", "high"]`
- **Actual** (llm_responses.py:20): `confidence: str = Field(default="medium", pattern="^(low|medium|high)$")`
- Both validate the same values, but type annotation differs. Literal is more precise.

### 5. SelectionResult `impact_summary` is documented but MISSING from actual schema
- **Doc says**: `impact_summary: str | None = None`
- **Actual**: Field does not exist in SelectionResult (llm_responses.py:16-22)
- **Also**: Doc marks `selected: bool | None = None` as "Undocumented field" but actual `selected: bool` is REQUIRED (no Optional), so doc's characterization is off

### 6. CondensedArticle `direct_quotes` field type mismatch
- **Doc says**: `direct_quotes: list[DirectQuote]` but describes `text: str` and `source: str`
- **Actual** (llm_responses.py:40-43): DirectQuote has `quote: str`, `attribution: str`, `source_url: Optional[str] = None`
- Field names don't match doc description (text/quote mismatch, source/attribution mismatch)

### 7. RelatedArticle completely different structure
- **Doc says** (architecture/schemas.md:150-153):
  ```python
  article_id: int
  title: str
  relevance: str
  ```
- **Actual** (llm_responses.py:46-50):
  ```python
  title: str
  category: str
  summary_snippet: str
  created_at: str
  ```
- No `article_id` or `relevance` fields; has `category`, `summary_snippet`, `created_at` instead

### 8. ExternalSource structure mismatch
- **Doc says**: `url: str`, `title: str`, `reliability: str`
- **Actual** (llm_responses.py:28-31): `title: str`, `url: str`, `snippet: str`
- `reliability` replaced by `snippet`

### 9. SourceConfig `adapter_config` doesn't exist
- **Doc says** (architecture/schemas.md:82): `adapter_config: RSSConfig | APIConfig | WebConfig`
- **Actual** (source.py:105-112): Has `config: dict[str, Any]` instead
- This is a MAJOR architectural difference - the discriminated union approach documented doesn't exist

### 10. SourceConfig field names differ
- Doc: `crawl_interval_minutes` | Actual: `schedule_minutes`
- Doc: `type: Literal["rss", "api", "web"]` | Actual: `type: str` (validated via validator)
- Doc shows `url: str` | Actual has no `url` field (uses `feed_url` in RSSConfig, `list_url` in APIConfig, `base_url`/`listing_url` in WebConfig)

### 11. ProcessItemTask structure completely different
- **Doc says** (tasks.py lines 204-207): `source_id: int`, `item_data: dict`, `topics: list[str]`
- **Actual** (tasks.py:87-101): Has `source_key`, `source_name`, `source_type`, `external_id`, `title`, `url`, `author`, `published_at`, `text_content`, `raw_score`, `raw_metadata`, `topics`, `min_content_length`, `run_id`
- This is a complete rewrite - doc and code share only `topics`

### 12. SendEmailTask differs
- **Doc says**: `body: str`
- **Actual** (tasks.py:62): `html: str`
- Doc says `body` but code has `html`

### 13. CleanupArticleVersionsTask field name differs
- **Doc says**: `days: int`
- **Actual** (tasks.py:74): `days_to_keep: int`

### 14. Multiple undocumented schemas exist
- `item.py` exists but is not documented (RawItem)
- `admin.py` exists but is not documented (ArticleIdsParams, CreateSourceRequest, etc.)
- `search.py` exists but is not documented (SearchConfig)
- `llm_responses.py` contains undocumented models: SubagentResponse, ResearchSynthesisResponse, EditContextualizationResponse, ToolCall, ToolResult, ToolCallingResponse (lines 164-201)

### 15. NewsletterArticle has undocumented fields
- **Actual** (llm_responses.py:135-139): Has `url: Optional[str]`, `tags: list[str]` that are not documented
- Doc only shows `article_id`, `title`, `summary`, `key_points`, `source_name`, `url` but actual has `headline`, `tags` instead of `key_points`, and no `source_name`

### 16. NewsletterArticle structure differs from doc
- **Doc says**: `article_id: int`, `title`, `summary`, `key_points`, `source_name`, `url`
- **Actual**: `headline`, `summary`, `url`, `tags`
- Missing `article_id`, `key_points`, `source_name`; has `headline` (not `title`), `tags` (not `key_points`)

## Improvement Recommendations

1. **[HIGH] Update MemoryConfig documentation or fix code**: The MemoryConfig in code is vastly different from documented. Either the docs need updating or the code was refactored without updating docs.

2. **[HIGH] Update NewsletterConfig documentation**: `enable_topic_newsletters` and `batch_size` are missing; `max_articles` default is 10 not 20; `site_url` has default.

3. **[HIGH] Fix SourceConfig documentation**: `adapter_config` doesn't exist, use `config: dict[str, Any]` pattern instead.

4. **[HIGH] Add `version` to PipelineRootConfig or remove from docs**: Either add the version field to match docs or remove from docs.

5. **[HIGH] Add `impact_summary` to SelectionResult or remove from docs**: Field documented but doesn't exist.

6. **[MEDIUM] Document missing schemas**: `item.py`, `admin.py`, `search.py`, and additional LLM response models are not documented.

7. **[MEDIUM] Fix SelectionResult `confidence` type**: Use `Literal["low", "medium", "high"]` instead of `str` with pattern for stricter type safety.

8. **[MEDIUM] Update RelatedArticle documentation**: Structure differs completely - update or clarify.

9. **[MEDIUM] Update ExternalSource documentation**: `reliability` vs `snippet` mismatch.

10. **[MEDIUM] Update ProcessItemTask documentation**: Completely different structure.

11. **[LOW] Align DirectQuote field names**: `quote` vs `text`, `attribution` vs `source`.

12. **[LOW] Update NewsletterArticle documentation**: Structure differs (headline vs title, tags vs key_points).

13. **[LOW] SendEmailTask `body` vs `html`**: Update doc or field name.

14. **[LOW] CleanupArticleVersionsTask field name**: `days` vs `days_to_keep`.

## Bugs Found

1. **Documentation claims `adapter_config: RSSConfig | APIConfig | WebConfig` in SourceConfig** (architecture/schemas.md:82)
   - **Actual**: `config: dict[str, Any]` in source.py:111
   - **Bug**: The discriminated union type hint in docs doesn't exist in code

2. **Documentation shows `max_articles: int = 20` for NewsletterConfig** (architecture/schemas.md:36)
   - **Actual**: `max_articles: int = Field(default=10, ge=1, le=50)` in pipeline.py:52
   - **Bug**: Default value is incorrect in documentation

3. **Documentation shows `enable_topic_newsletters: bool = True` and `batch_size: int = 500` for NewsletterConfig** (architecture/schemas.md:41-42)
   - **Actual**: Neither field exists in pipeline.py:51-56
   - **Bug**: Fields documented but not implemented

4. **Documentation shows `site_url: str` with no default** (architecture/schemas.md:39)
   - **Actual**: `site_url: str = "https://ainews.dev"` in pipeline.py:55
   - **Bug**: Documentation shows required field but code has default value

5. **Documentation shows `version: str = "1.0"` in PipelineRootConfig** (architecture/schemas.md:23)
   - **Actual**: No `version` field exists in pipeline.py:144-153
   - **Bug**: Field documented but not present in code

6. **Documentation shows `impact_summary: str | None = None` in SelectionResult** (architecture/schemas.md:119)
   - **Actual**: No `impact_summary` field in llm_responses.py:16-22
   - **Bug**: Field documented but not implemented

7. **Documentation shows `related_articles: list[RelatedArticle]` with `article_id: int, title: str, relevance: str`** (architecture/schemas.md:150-153)
   - **Actual** (llm_responses.py:46-50): `title: str, category: str, summary_snippet: str, created_at: str` - no `article_id` or `relevance`
   - **Bug**: Field names completely different

8. **Documentation shows `external_sources: list[ExternalSource]` with `url: str, title: str, reliability: str`** (architecture/schemas.md:145-148)
   - **Actual** (llm_responses.py:28-31): `title: str, url: str, snippet: str`
   - **Bug**: `reliability` field documented but `snippet` is actual field name

## Layer Violations

1. **No clean layer violations detected**: The schemas module is relatively clean. Schemas import from `schemas.common` for shared utilities, which is appropriate. No adapters importing from services, no services importing from adapters detected within this module.

2. **Minor concern**: `cached_config` and `cached_config_with_mtime` in `schemas/common.py` import from `services.config_cache` (line 73, 85). This creates a runtime dependency from schemas to services. However, it uses try/except with fallback, so it won't fail if services isn't available. This is a soft dependency acceptable for caching infrastructure.

## Summary

The architecture document is significantly out of sync with the actual implementations. The most critical issues are:

1. **MemoryConfig**: Completely different fields (0% match with documentation)
2. **SourceConfig**: Uses `config: dict` instead of discriminated union `adapter_config`
3. **NewsletterConfig**: Missing fields (`enable_topic_newsletters`, `batch_size`), wrong defaults
4. **ProcessItemTask**: Completely different structure
5. **PipelineRootConfig**: Missing `version` field
6. **SelectionResult**: Missing `impact_summary` field
7. **RelatedArticle/ExternalSource**: Wrong field names

The schemas module itself appears well-structured with proper Pydantic validation, but the documentation has not been kept up to date with code changes.

# Architecture Schemas Review

**Review date:** 2026-05-29
**Reviewed files:** `schemas/*.py`, `pipeline.yaml`

---

## Verified Claims

### File Inventory (schemas.md lines 5-20)
All schema files exist and models match:
| File | Models | Verified |
|------|--------|----------|
| `pipeline.py` | `PipelineRootConfig`, stage configs | ✓ |
| `source.py` | `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig`, `TopicMatchConfig` | ✓ |
| `common.py` | `ProviderDef` | ✓ |
| `llm.py` | Provider definitions | ✓ |
| `llm_responses.py` | All LLM response schemas | ✓ |
| `tasks.py` | Task validation schemas | ✓ |
| `topic.py` | Topic definitions | ✓ |
| `webhook.py` | `WebhookCreate`, `WebhookResponse` | ✓ |
| `item.py` | `RawItem` | ✓ |
| `admin.py` | Admin request schemas | ✓ |
| `search.py` | `SearchConfig`, `load_search_config` | ✓ |

### PipelineRootConfig Structure (schemas.md lines 26-33)
- `pipeline: PipelineConfig` ✓
- `newsletter: NewsletterConfig` ✓
- `newsletter_pipeline: NewsletterPipelineConfig` ✓
- `subagent: SubagentConfig` ✓
- `memory: MemoryConfig` ✓
- `stages: dict[str, StageConfig]` ✓
- `schedule: dict` ✓

### RoleConfig (schemas.md lines 16-27)
Documented fields exist and match:
- `provider: str` ✓
- `model: str` ✓
- `max_tokens: int` ✓
- `temperature: float` ✓
- `concurrency: int` ✓
- `timeout_seconds: int` ✓

Note: `RoleConfig` also has undocumented fields `enabled: bool = True`, `system_prompt`, `min_score`, `web_search`, `web_search_max_results`, `web_search_provider`, `db_related_max`, `max_article_text_length`, `max_key_points`, `max_tags` (schemas/pipeline.py:16-33). Documented subset is correct but incomplete.

### StageConfig Stub (schemas.md lines 35-36)
- "StageConfig is a stub with only `tools: list[str]`" ✓ (schemas/pipeline.py:141-147)

### SubagentConfig (schemas.md lines 77-84)
- `default`, `research`, `edit` stages ✓
- `chains: dict[str, SubagentChainConfig]` ✓
- "There is NO 'enabled' field on SubagentConfig" ✓ (confirmed at schemas/pipeline.py:121-125)
- "The enabled flag exists on individual SubagentStageConfig instances" ✓ (SubagentStageConfig.enabled at schemas/pipeline.py:94)

### SubagentStageConfig (schemas/pipeline.py:93-106)
All fields documented in AGENTS.md but NOT in schemas.md:
- `enabled: bool = False` ✓
- `provider: Optional[str]` ✓
- `model: Optional[str]` ✓
- `max_tokens: int` ✓
- `temperature: float` ✓
- `timeout_seconds: int` ✓
- `system_prompt: Optional[str]` ✓
- `max_retries: int` ✓
- `retry_delay: float` ✓
- `task_template: Optional[str]` ✓
- `tools: list[str]` ✓
- `max_iterations: int` ✓

### SubagentChainConfig (schemas.md lines 86-89)
- `enabled: bool = False` ✓
- `max_length: int = 5` ✓
- `steps: list[SubagentChainStep]` ✓

### SubagentChainStep (schemas.md lines 91-95)
- `task_type: str` ✓
- `prompt_data_template: str` ✓
- `response_model: Optional[str]` ✓
- `condition: Optional[str]` ✓

### NewsletterConfig (schemas.md lines 38-43)
- `max_articles: int = 10` ✓
- `send_time: str = "08:00"` ✓
- `timezone: str = "America/New_York"` ✓
- `site_url: str = "https://ainews.dev"` ✓
- `prep_minutes: int = 15` ✓

### NewsletterPipelineConfig (schemas.md lines 45-75)
- `reader`, `writer`, `editor` RoleConfigs with `qwen3:8b` defaults ✓

### MemoryConfig (schemas.md lines 97-108)
All fields match `schemas/pipeline.py:128-138`:
- `ttl_days_low: int = 7` ✓
- `ttl_days_medium: int = 30` ✓
- `ttl_days_high: int = 0` ✓
- `consolidation_cooldown_hours: int = 24` ✓
- `max_entries_per_propose: int = 3` ✓
- `consolidation_merge_window_hours: int = 72` ✓
- `truncation_llm_enabled: bool = True` ✓
- `truncation_llm_threshold: int = 2000` ✓
- `truncation_llm_max_tokens: int = 512` ✓
- `truncation_llm_temperature: float = 0.0` ✓

### Source Configuration (schemas.md lines 110-186)
- `SourceConfig.id` pattern `r"^[a-z0-9_]+$"` ✓
- `SourceConfig.name` min/max length ✓
- `SourceConfig.type` field_validator validates against RSS/API/Web ✓
- `SourceConfig.enabled: bool = True` ✓
- `SourceConfig.schedule_minutes: int = 30` ✓
- `SourceConfig.config: dict[str, Any]` ✓
- `SourceConfig.topics: TopicMatchConfig` ✓
- `RSSConfig`: `feed_url`, `max_items=50`, `request_timeout=15`, `user_agent`, `min_content_length=200` ✓
- `APIConfig`: `list_url`, `list_method="json_array"`, `list_items_path=None`, `max_items=30`, `item_url`, `fields`, `filters`, `metadata`, `pagination`, `api_key`, `auth_header` (Bearer auth), `request_timeout=15`, `user_agent` ✓
- `WebConfig`: `base_url`, `listing_url`, `listing: ListingConfig`, `article: ArticleSelectors`, `request_delay_min=1.5`, `request_delay_max=4.0`, `max_retries=3`, `user_agent` ✓
- `ListingConfig`: `card_selector`, `link_selector`, `link_attribute="href"`, `pagination` ✓
- `ArticleSelectors`: all optional selectors ✓
- `PaginationConfig`: `enabled=False`, `type="next_link"`, `next_link_selector=None`, `max_pages=3` ✓

### LLM Responses (schemas.md lines 188-311)

**SelectionResult** (schemas/llm_responses.py:16-22):
- `selected: bool` ✓
- `score: int` ge=1 le=10 ✓
- `reason: str` ✓
- `confidence: str` pattern `^(low|medium|high)$` ✓
- `key_topics: list[str]` ✓
- `impact_summary: Optional[str]` ✓

**ResearchBrief** (schemas/llm_responses.py:53-81):
- `source_summary: str` ✓
- `key_claims: list[KeyClaim]` ✓
- `direct_quotes: list[DirectQuote]` ✓
- `external_sources: list[ExternalSource]` ✓
- `related_articles: list[RelatedArticle]` ✓
- `context_notes: str` (not 'context') ✓
- `newsworthiness: str` ✓
- `impact_score: int` ge=0 le=100 ✓

**KeyClaim, DirectQuote, ExternalSource, RelatedArticle** all verified ✓

**CondensedArticle** (schemas/llm_responses.py:101-129):
- `headline: str` ✓
- `tldr: str` ✓
- `why_it_matters: str` ✓
- `body: str` ✓
- `key_points: list[str]` ✓
- `what_to_watch: str` ✓
- `citations: list[CitationItem]` ✓
- `original_attribution: OriginalAttribution` ✓
- `tags: list[str]` ✓

**ExecutiveSummary** (schemas/llm_responses.py:151-158):
- `summary: str` with detailed description ✓

**NewsletterBrief** (schemas/llm_responses.py:142-148):
- "actual model does NOT have preamble, footer, or articles fields" ✓
- `themes: list[str]` ✓
- `highlights: list[str]` ✓
- `connections: list[str]` ✓

**NewsletterArticle** (schemas/llm_responses.py:135-139):
- `headline`, `summary`, `url`, `tags` ✓

**SubagentResponse, ResearchSynthesisResponse, EditContextualizationResponse** ✓

**ToolCall, ToolResult, ToolCallingResponse** ✓

### Task Validation (schemas.md lines 313-372)

**SelectArticleTask** (schemas/tasks.py:33-42):
- `article_id: int` gt=0 ✓
- `run_id: Optional[int]` ge=0 ✓

**ProcessItemTask** (schemas/tasks.py:87-117):
- All 13 fields match ✓
- `source_type` validator checks rss/api/web ✓
- `topics` validator checks max 20 items ✓

**GenerateNewsletterTask** (schemas/tasks.py:45-56):
- `dry_run_email: Optional[str]` ✓
- `run_id: Optional[int]` ✓
- `dry_run_email` validator via `_EMAIL_RE` ✓

**SendEmailTask** (schemas/tasks.py:59-70):
- `email`, `subject`, `html`, `unsub_url` ✓
- `email` validator via `_EMAIL_RE` ✓

**CleanupArticleVersionsTask** (schemas/tasks.py:73-84):
- `days_to_keep: int` default=90 ge=1 le=365 ✓
- `dry_run: bool` default=False ✓

### ProviderDef (schemas.md lines 378-387)
- `id: str` pattern `r"^[a-z0-9_\-]+$"` ✓
- `type: str` ✓
- `enabled: bool = True` ✓
- `config: dict = {}` ✓

### Intentional Layer Violations (schemas.md lines 389-399)
- `schemas/common.py` imports from `services.config_cache` ✓
- Comment explaining layer violation present ✓

---

## Incorrect Claims

**None identified.** All documented field names, types, defaults, and validators match actual code.

---

## Bugs Found

**None.** No bugs in documentation.

---

## Improvement Opportunities

### 1. Missing: RoleConfig.enabled field not documented (MEDIUM)
**Location:** schemas.md - Pipeline Configuration / RoleConfig (lines 16-27)

`RoleConfig` in `schemas/pipeline.py:17` has `enabled: bool = True` which is not documented. This field controls whether a pipeline role is active. While the documented subset of fields is accurate, this is a significant omission given the field controls pipeline behavior.

**Recommendation:** Add `enabled: bool = True` to RoleConfig documentation.

### 2. Missing: ReviewConfig not documented (MEDIUM)
**Location:** schemas.md - Pipeline Configuration (around lines 44-49)

`ReviewConfig` (`schemas/pipeline.py:35-41`) is not documented at all. This config controls review stage and auto-publish behavior:
```python
class ReviewConfig(BaseModel):
    enabled: bool = False
    auto_publish_threshold: Optional[int] = None
```

`PipelineConfig` at line 49 has `review: ReviewConfig = Field(default_factory=ReviewConfig)` which is also not documented.

**Recommendation:** Add ReviewConfig section with `enabled` and `auto_publish_threshold` fields.

### 3. Minor: RoleConfig additional fields not documented (LOW)
**Location:** schemas.md - Pipeline Configuration / RoleConfig

`RoleConfig` has additional optional fields beyond the documented core 6:
- `system_prompt: Optional[str]`
- `min_score: Optional[int]` (selector only)
- `web_search: Optional[bool]` (researcher only)
- `web_search_max_results: Optional[int]` (researcher only)
- `web_search_provider: Optional[str]` (researcher only)
- `db_related_max: Optional[int]` (researcher only)
- `max_article_text_length: Optional[int]` (researcher only)
- `max_key_points: Optional[int]` (writer only)
- `max_tags: Optional[int]` (editor only)

These are role-specific options that may be intentional omissions, but they should at minimum be listed as "plus role-specific options" to avoid confusion.

**Recommendation:** Add note about role-specific optional fields or list them explicitly.

### 4. Minor: SubagentStageConfig not documented in schemas.md (LOW)
**Location:** schemas.md - Pipeline Configuration

The full `SubagentStageConfig` schema (14 fields) is not documented in schemas.md. Only `SubagentConfig` and `SubagentChainConfig` are documented. The 14 fields of `SubagentStageConfig` are documented in AGENTS.md but not in this architecture doc.

**Recommendation:** Add SubagentStageConfig fields to schema documentation or reference AGENTS.md.

---

## Stale Content

**None identified.** All content is current with codebase.

---

## Priority Summary

| Finding | Severity | Type | Effort |
|---------|----------|------|--------|
| Document RoleConfig.enabled | MEDIUM | Improvement | Low |
| Document ReviewConfig | MEDIUM | Improvement | Low |
| Document RoleConfig role-specific fields | LOW | Improvement | Low |
| Document SubagentStageConfig | LOW | Improvement | Low |

All verified claims correct; no bugs or stale content found.
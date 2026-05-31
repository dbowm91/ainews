# Review: architecture/schemas.md

**Reviewed:** 2026-05-31
**Source:** `architecture/schemas.md`
**Reviewer:** Subagent 1 (Data Layer)
**Status:** COMPLETE

---

## Verified Claims

### File Inventory (Lines 7-19)
- All 12 schema files exist: `pipeline.py`, `source.py`, `common.py`, `llm.py`, `llm_responses.py`, `tasks.py`, `topic.py`, `webhook.py`, `item.py`, `admin.py`, `search.py`
- All listed model classes exist with correct names

### Pipeline Configuration (Lines 21-158)
- `StageConfig` is a stub with only `tools: list[str]` — VERIFIED (`schemas/pipeline.py:150-156`)
- `RoleConfig` fields match: enabled, provider, model, max_tokens, temperature, concurrency, timeout_seconds, system_prompt, min_score, web_search, web_search_max_results, web_search_provider, db_related_max, max_article_text_length, max_key_points, max_tags — VERIFIED
- `RoleConfig` provider and model are required (`...`) — VERIFIED (`schemas/pipeline.py:18-19`)
- `SubagentStageConfig` fields match: enabled, provider, model, max_tokens, temperature, timeout_seconds, system_prompt, max_retries, retry_delay, task_template, tools, max_iterations — VERIFIED (`schemas/pipeline.py:93-105`)
- `SubagentStageConfig` `max_iterations` ge=1 le=20 — VERIFIED (`schemas/pipeline.py:105`)
- `ReviewConfig` fields: enabled=False, auto_publish_threshold=None — VERIFIED (`schemas/pipeline.py:35-41`)
- `SubagentConfig` has NO top-level `enabled` field — VERIFIED (`schemas/pipeline.py:121-134`)
- `NewsletterConfig` fields match — VERIFIED (`schemas/pipeline.py:52-57`)
- `NewsletterPipelineConfig` fields and defaults match — VERIFIED (`schemas/pipeline.py:60-90`)
- `MemoryConfig` fields match — VERIFIED (`schemas/pipeline.py:137-147`)

### Source Configuration (Lines 160-254)
- `SourceType` enum: RSS="rss", API="api", WEB="web" — VERIFIED (`schemas/source.py:12-15`)
- `MatchMode` enum: KEYWORD="keyword", CONTEXTUAL="contextual" — VERIFIED (`schemas/source.py:18-20`)
- `RSSConfig` fields match — VERIFIED (`schemas/source.py:29-39`)
- `APIConfig` fields match — VERIFIED (`schemas/source.py:57-71`)
- `WebConfig` fields match — VERIFIED (`schemas/source.py:89-97`)
- `TopicMatchConfig` fields match — VERIFIED (`schemas/source.py:23-26`)
- `ListingConfig` fields match — VERIFIED (`schemas/source.py:74-78`)
- `ArticleSelectors` fields match — VERIFIED (`schemas/source.py:81-86`)
- `PaginationConfig` with validator — VERIFIED (`schemas/source.py:43-54`)
- `SourceConfig` validator logic (`validate_adapter_config`) — VERIFIED (`schemas/source.py:125-132`)
- `ADAPTER_CONFIGS` dict mapping — VERIFIED (`schemas/source.py:100-104`)

### LLM Responses (Lines 256-398)
- `SelectionResult` fields match — VERIFIED (`schemas/llm_responses.py:16-22`)
- `ResearchBrief` fields match (source_summary, key_claims, direct_quotes, external_sources, related_articles, context_notes, newsworthiness, impact_score) — VERIFIED (`schemas/llm_responses.py:53-81`)
- `KeyClaim`, `DirectQuote`, `ExternalSource`, `RelatedArticle` — VERIFIED
- `CitationItem` and `OriginalAttribution` — VERIFIED (`schemas/llm_responses.py:87-98`)
- `CondensedArticle` fields match — VERIFIED (`schemas/llm_responses.py:101-129`)
- `ExecutiveSummary` has single `summary` field — VERIFIED (`schemas/llm_responses.py:151-158`)
- `NewsletterBrief` does NOT have `preamble`, `footer`, or `articles` fields — VERIFIED (`schemas/llm_responses.py:142-148`)
- `SubagentResponse` fields match — VERIFIED (`schemas/llm_responses.py:164-173`)
- `ToolCall`, `ToolResult`, `ToolCallingResponse` — VERIFIED (`schemas/llm_responses.py:186-202`)

### Task Validation (Lines 400-459)
- `SelectArticleTask` fields match — VERIFIED (`schemas/tasks.py:33-42`)
- `ProcessItemTask` fields match — VERIFIED (`schemas/tasks.py:87-117`)
- `ProcessItemTask.validate_source_type` validator — VERIFIED (`schemas/tasks.py:103-108`)
- `ProcessItemTask.validate_topics` validator — VERIFIED (`schemas/tasks.py:110-117`)
- `GenerateNewsletterTask` fields match — VERIFIED (`schemas/tasks.py:45-56`)
- `SendEmailTask` fields match — VERIFIED (`schemas/tasks.py:59-70`)
- `CleanupArticleVersionsTask` fields match — VERIFIED (`schemas/tasks.py:73-84`)

### Common Schemas (Lines 461-474)
- `ProviderDef` fields: id, type, enabled, config — VERIFIED (`schemas/common.py:23-29`)
- `ProviderDef` id pattern `^[a-z0-9_\-]+$` — VERIFIED (`schemas/common.py:26`)

### LLM Provider Configurations (Lines 476-513)
- `OllamaConfig` fields match — VERIFIED (`schemas/llm.py:17-22`)
- `OpenAIConfig` fields match — VERIFIED (`schemas/llm.py:25-31`)
- `AnthropicConfig` fields match — VERIFIED (`schemas/llm.py:42-47`)
- `GeminiConfig` fields match — VERIFIED (`schemas/llm.py:58-63`)
- `LLMProvidersConfig` fields match — VERIFIED (`schemas/llm.py:82-84`)
- `ADAPTER_CONFIGS` dict — VERIFIED (`schemas/llm.py:74-79`)

### Search Provider Configuration (Lines 515-523)
- `SearchConfig` fields: providers, default_provider="duckduckgo" — VERIFIED (`schemas/search.py:10-12`)

### Topic Configuration (Lines 525-538)
- `TopicDef` fields match — VERIFIED (`schemas/topic.py:11-15`)
- `TopicsConfig` fields match — VERIFIED (`schemas/topic.py:18-19`)

### Admin Schemas (Lines 540-586)
- `ArticleIdsParams` fields match — VERIFIED (`schemas/admin.py:19-30`)
- `CreateSourceRequest` fields match — VERIFIED (`schemas/admin.py:57-65`)
- `UpdateSourceRequest` fields match — VERIFIED (`schemas/admin.py:75-83`)
- `BulkArticleRequest` fields match — VERIFIED (`schemas/admin.py:95-102`)
- `TaskStatusParams` fields match — VERIFIED (`schemas/admin.py:137-140`)

### Intentional Layer Violations (Lines 588-598)
- `schemas/common.py` imports `services.config_cache` — VERIFIED (`schemas/common.py:72-96`)
- Inline comment documenting the violation — VERIFIED (`schemas/common.py:72-73`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 76-84 | `PipelineRootConfig` fields shown without default values (implying required) | `schemas/pipeline.py:159-169` — `newsletter`, `newsletter_pipeline`, `subagent`, `memory`, `experiments`, `stages`, `schedule` all have `default_factory` | MEDIUM |
| 76-84 | `PipelineRootConfig` missing `experiments: dict = Field(default_factory=dict)` field | `schemas/pipeline.py:167` — `experiments: dict = Field(default_factory=dict)` exists | HIGH |
| 118 | `SubagentChainConfig.steps: list[SubagentChainStep]` shown as required | `schemas/pipeline.py:118` — `steps: list[SubagentChainStep] = Field(default_factory=list)` has default | LOW |
| 131 | `SubagentConfig.chains: dict[str, SubagentChainConfig]` shown as required | `schemas/pipeline.py:134` — `chains: dict[str, SubagentChainConfig] = Field(default_factory=dict)` has default | LOW |
| 439-441 | `GenerateNewsletterTask.dry_run_email: Optional[str] = None` shown without Field wrapper | `schemas/tasks.py:46` — `dry_run_email: Optional[str] = Field(default=None, description="...")` | LOW |
| 443-447 | `SendEmailTask` fields shown without Field descriptions | `schemas/tasks.py:60-63` — fields have `Field(..., description="...")` | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | **`PipelineRootConfig.experiments` field undocumented.** The `experiments: dict = Field(default_factory=dict)` field exists at `schemas/pipeline.py:167` and is used by the A/B experiment system (documented in `pipeline.yaml:265-292`). This is a functional field, not a stub. | `architecture/schemas.md:76-84` | HIGH | `schemas/pipeline.py:167`, `pipeline.yaml:265-292` |
| 2 | **`RawItem` schema undocumented.** `schemas/item.py` defines `RawItem` with 10 fields (source_id, external_id, title, url, author, published_at, text_content, raw_score, raw_metadata, topics). This schema is used by all adapters to return crawled items. | `architecture/schemas.md` | MEDIUM | `schemas/item.py:9-19` |
| 3 | **`WebhookCreate` and `WebhookResponse` schemas undocumented.** `schemas/webhook.py` defines these two schemas used by webhook API routes. | `architecture/schemas.md` | LOW | `schemas/webhook.py:10-27` |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Add `experiments: dict` field to `PipelineRootConfig` documentation with note about A/B experiment configuration. | maintainability | P1 |
| 2 | Add `RawItem` schema documentation (used by all adapters). | maintainability | P1 |
| 3 | Add `WebhookCreate` and `WebhookResponse` schema documentation. | maintainability | P2 |
| 4 | Show `default_factory` for all optional fields in `PipelineRootConfig` to clarify which are truly required vs. defaulted. | maintainability | P2 |
| 5 | The `SourceConfig` doc (line 188) says `validate_adapter_config field_validator` but the actual validator names are `validate_type` and `validate_adapter_config`. Update to reflect both validators. | maintainability | P2 |
| 6 | Add the `@field_validator("config")` logic description showing it validates against adapter-specific schemas (RSSConfig, APIConfig, WebConfig). | maintainability | P3 |
| 7 | The `PipelineConfig` doc shows fields without `default_factory`, but all role fields (selector, researcher, writer, editor) are required. Only `review` has a default. Clarify this distinction. | maintainability | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| N/A | No stale content detected | All referenced files, classes, and functions exist | None |

---

## Summary

- Verified: 58 claims
- Incorrect: 6 claims (1 HIGH, 1 MEDIUM, 4 LOW)
- Bugs: 3 (HIGH: 1, MEDIUM: 1, LOW: 1)
- Improvements: 7
- Stale items: 0

**Overall Assessment:** The schemas.md document is comprehensive and accurate for the models it covers. The critical gap is the missing `experiments` field on `PipelineRootConfig` (used by the A/B experiment system). Secondary gaps are the undocumented `RawItem`, `WebhookCreate`, and `WebhookResponse` schemas. The document correctly identifies the `StageConfig` stub, the `SubagentConfig` no-enabled-field pattern, and the intentional layer violation in `common.py`. All validator logic, enum values, and field constraints match the actual code.

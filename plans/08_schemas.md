# Plan 08: Schemas Architecture Verification

## Context

Reviewed `architecture/schemas.md` documenting the expected Pydantic schemas architecture and compared against actual implementation in `schemas/` directory.

---

## Verification Results

### File Inventory

| File | Documented | Actual | Status |
|------|------------|--------|--------|
| `pipeline.py` | Yes | Yes | DISCREPANCY |
| `source.py` | Yes | Yes | DISCREPANCY |
| `llm.py` | Yes | Yes | VERIFIED |
| `llm_responses.py` | Yes | Yes | DISCREPANCY |
| `tasks.py` | Yes | Yes | DISCREPANCY |
| `topic.py` | Yes | Yes | VERIFIED |
| `webhook.py` | Documented | NOT FOUND | DISCREPANCY |
| `common.py` | Not documented | EXISTS | INFO |
| `admin.py` | Not documented | EXISTS | INFO |
| `item.py` | Not documented | EXISTS | INFO |
| `search.py` | Not documented | EXISTS | INFO |

### Pipeline Configuration (`pipeline.py`)

| Claim | Status | Details |
|-------|--------|---------|
| `PipelineRootConfig` exists | VERIFIED | Class exists but structure differs |
| `StageConfig` exists | VERIFIED | Class exists but is a stub with only `tools: list[str]` |
| `NewsletterConfig` exists | VERIFIED | Class exists but fields differ (uses `send_time` vs `daily_send_time`) |
| `SubagentConfig` exists | VERIFIED | Class exists but different nested structure |
| `MemoryConfig` exists | VERIFIED | Class exists but fields differ significantly |
| `stages: dict[str, StageConfig]` | DISCREPANCY | Field exists but `StageConfig` is empty stub |

**Actual `PipelineRootConfig` structure:**
- Uses nested `PipelineConfig` containing `selector`, `researcher`, `writer`, `editor`, `review` roles
- `NewsletterConfig` has `max_articles`, `send_time`, `timezone`, `site_url`, `prep_minutes`
- `SubagentConfig` has `default`, `research`, `edit`, `chains` (not the documented structure)
- `MemoryConfig` has TTL and consolidation settings (completely different from doc)

### Source Configuration (`source.py`)

| Claim | Status | Details |
|-------|--------|---------|
| `SourceConfig` exists | VERIFIED | Exists but `type` is `str`, not `Literal["rss", "api", "web"]` |
| `RSSConfig` exists | VERIFIED | Has `feed_url`, not documented `item_path` and `field_mappings` |
| `APIConfig` exists | VERIFIED | Different fields (`list_url`, `list_items_path`, etc.) |
| `WebConfig` exists | VERIFIED | Different fields (uses `ListingConfig` and `ArticleSelectors`) |
| `PaginationConfig` exists | VERIFIED | Exists but `type` is `str`, not `Literal["cursor", "offset", "page"]` |

### LLM Responses (`llm_responses.py`)

| Claim | Status | Details |
|-------|--------|---------|
| `SelectionResult` exists | VERIFIED | Has `selected: bool` (not in doc), missing `key_topics` and `impact_summary` |
| `ResearchBrief` exists | VERIFIED | Different structure - no `article_id`, no `Citation`, uses `key_claims` |
| `Citation` exists | DISCREPANCY | Class is named `CitationItem` (or nested differently) |
| `CondensedArticle` exists | VERIFIED | Different structure (has `headline`, `tldr`, `body` vs `title`, `summary`) |
| `ExecutiveSummary` exists | VERIFIED | Field is `summary` (str) not `date`, `theme`, `overview`, `outlook`, `article_count` |
| `NewsletterBrief` exists | VERIFIED | Has `themes`, `highlights`, `connections` (not `newsletter_id`, `subject`, `preamble`) |
| `NewsletterArticle` exists | DISCREPANCY | Not found in `llm_responses.py` |

### Task Validation (`tasks.py`)

| Claim | Status | Details |
|-------|--------|---------|
| `ProcessItemInput` exists | DISCREPANCY | Class named `ProcessItemTask` |
| `SelectArticleInput` exists | DISCREPANCY | Class named `SelectArticleTask` |
| `ResearchArticleInput` exists | DISCREPANCY | Not found |
| `WriteArticleInput` exists | DISCREPANCY | Not found |
| `EditArticleInput` exists | DISCREPANCY | Not found |

---

## Bug Findings

### Critical

1. **`webhook.py` missing** - Documented but file does not exist. No `WebhookCreate` or `WebhookResponse` schemas.

2. **`StageConfig` is empty stub** - The class only has `tools: list[str] = Field(default_factory=list)` but documented to have `enabled`, `model`, `prompt_variant`, `temperature`, `max_tokens`, `timeout`.

3. **`SelectionResult` missing documented fields** - Should have `key_topics: list[str]` and `impact_summary: str | None` per doc.

### High

4. **Task input schema names mismatch** - All documented as `*Input` suffix (e.g., `SelectArticleInput`) but actual classes use `*Task` suffix (e.g., `SelectArticleTask`).

5. **`NewsletterBrief` structure mismatch** - Documented has `newsletter_id`, `subject`, `preamble`, `articles: list[NewsletterArticle]`, `footer`. Actual has `themes`, `highlights`, `connections`.

6. **`NewsletterArticle` missing** - Documented as part of `NewsletterBrief` but class does not exist.

7. **`ResearchBrief` missing `article_id`** - Documented has `article_id: int` field.

8. **`Citation` missing** - Documented as part of `ResearchBrief` but actual uses `KeyClaim` with different structure.

### Medium

9. **`SourceConfig.type` type mismatch** - Documented as `Literal["rss", "api", "web"]` but actual is `str`.

10. **`PaginationConfig.type` type mismatch** - Documented as `Literal["cursor", "offset", "page"]` but actual is `str`.

11. **`ExecutiveSummary` fields differ** - Documented has `date`, `theme`, `overview`, `highlights`, `outlook`, `article_count`. Actual has single `summary: str`.

12. **`CondensedArticle` structure differs significantly** - Documented has `title`, `summary`, `key_points`, `implications`, `hook`, `word_count`. Actual has `headline`, `tldr`, `why_it_matters`, `body`, `key_points`, `what_to_watch`, `citations`, `original_attribution`, `tags`.

### Low

13. **`MemoryConfig` completely different** - Documented has `enabled`, `consolidate_interval_hours`, `max_entries_per_topic`, `embedding_model`. Actual has TTL settings, consolidation settings, truncation settings.

14. **`NewsletterConfig` fields differ** - Documented has `daily_send_time`, `enable_topic_newsletters`, `batch_size`, `retry_attempts`. Actual has `max_articles`, `send_time`, `timezone`, `site_url`, `prep_minutes`.

15. **`SubagentConfig` structure differs** - Documented as simple with `enabled`, `max_iterations`, `tool_timeout`, `tools`. Actual has nested `default`, `research`, `edit`, `chains` with different fields.

---

## Improvement Opportunities

### 1. Documentation Sync
The documented schemas do not reflect the actual implementation. Either:
- Update `architecture/schemas.md` to match implementation, OR
- Refactor implementation to match documented schema structure

### 2. Schema Naming Convention
Current uses `*Task` suffix for task schemas but docs show `*Input`. Establish consistent naming.

### 3. Missing Webhook Schemas
Create `schemas/webhook.py` with `WebhookCreate` and `WebhookResponse` if webhooks are used.

### 4. StageConfig Enhancement
`StageConfig` is documented with substantial configuration but actual is empty stub. Either implement or remove from docs.

### 5. NewsletterArticle Schema
If newsletter articles are a distinct entity, create the schema. Currently `NewsletterBrief.articles` has no type definition.

### 6. SelectionResult Enhancement
Add `key_topics: list[str]` and `impact_summary: str | None` fields if selector stage returns these.

---

## Action Items

1. **[HIGH]** Create `schemas/webhook.py` with `WebhookCreate` and `WebhookResponse` classes
2. **[HIGH]** Rename task schemas from `*Task` to `*Input` suffix OR update documentation
3. **[HIGH]** Add `key_topics` and `impact_summary` to `SelectionResult`
4. **[HIGH]** Create `NewsletterArticle` schema and update `NewsletterBrief`
5. **[MEDIUM]** Update `architecture/schemas.md` to reflect actual `StageConfig`, `MemoryConfig`, `SubagentConfig` structures
6. **[MEDIUM]** Change `SourceConfig.type` from `str` to `Literal["rss", "api", "web"]`
7. **[MEDIUM]** Change `PaginationConfig.type` to a Literal union type
8. **[MEDIUM]** Add `article_id: int` to `ResearchBrief` if needed
9. **[LOW]** Document the extra files (`common.py`, `admin.py`, `item.py`, `search.py`) or remove if unnecessary

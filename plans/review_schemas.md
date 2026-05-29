# Review: architecture/schemas.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

### File Inventory (partial)
- `pipeline.py` → PipelineRootConfig, stage configs — CORRECT (`schemas/pipeline.py:150`)
- `source.py` → SourceConfig, RSSConfig, APIConfig, WebConfig, TopicMatchConfig — CORRECT (`schemas/source.py:106,29,42,88,23`)
- `common.py` → ProviderDef — CORRECT (`schemas/common.py:23`)
- `llm_responses.py` → SelectionResult, ResearchBrief, CondensedArticle, ExecutiveSummary, NewsletterBrief, SubagentResponse, ResearchSynthesisResponse, EditContextualizationResponse, ToolCall, ToolResult, ToolCallingResponse — CORRECT (`schemas/llm_responses.py`)
- `tasks.py` → SelectArticleTask, ProcessItemTask, GenerateNewsletterTask, SendEmailTask, CleanupArticleVersionsTask — CORRECT (`schemas/tasks.py`)
- `topic.py` → Topic definitions — CORRECT (`schemas/topic.py`)
- `webhook.py` → WebhookCreate, WebhookResponse — CORRECT (`schemas/webhook.py`)
- `item.py` → RawItem — CORRECT (`schemas/item.py`)
- `search.py` → SearchConfig, load_search_config — CORRECT (`schemas/search.py`)

### Pipeline Configuration
- `PipelineRootConfig` structure — CORRECT (`schemas/pipeline.py:150-159`)
- `StageConfig` is stub with only `tools` field — CORRECT (`schemas/pipeline.py:141-147`)
- `PipelineConfig` has selector, researcher, writer, editor roles — CORRECT (`schemas/pipeline.py:44-49`)
- `NewsletterConfig` fields — CORRECT (`schemas/pipeline.py:52-57`)
- `NewsletterPipelineConfig` defaults — CORRECT (`schemas/pipeline.py:60-90`)

### RoleConfig
- `enabled` default=True — CORRECT (`schemas/pipeline.py:17`)
- `provider`, `model` required — CORRECT (`schemas/pipeline.py:18-19`)
- `max_tokens` with MAX_TOKENS_FIELD (4096, ge=256, le=128000) — CORRECT (`schemas/pipeline.py:20`)
- `temperature` default=0.0, ge=0.0, le=2.0 — CORRECT (`schemas/pipeline.py:21`)
- `concurrency` default=2, ge=1, le=32 — CORRECT (`schemas/pipeline.py:22`)
- `timeout_seconds` default=120, ge=10, le=600 — CORRECT (`schemas/pipeline.py:23`)

### SubagentConfig
- Has `default`, `research`, `edit` fields — CORRECT (`schemas/pipeline.py:122-124`)
- NO `enabled` field at top level — CORRECT (`schemas/pipeline.py:121-125`)
- `chains` field present — CORRECT (`schemas/pipeline.py:125`)

### SubagentStageConfig
- `enabled` default=False — CORRECT (`schemas/pipeline.py:94`)
- Has provider, model, max_tokens, temperature, timeout_seconds, system_prompt — CORRECT (`schemas/pipeline.py:95-100`)
- Has max_retries, retry_delay — CORRECT (`schemas/pipeline.py:101-102`)
- Has task_template, tools, max_iterations — CORRECT (`schemas/pipeline.py:103-105`)

### SubagentChainConfig
- `enabled` default=False — CORRECT (`schemas/pipeline.py:116`)
- `max_length` default=5, ge=1, le=10 — CORRECT (`schemas/pipeline.py:117`)
- `steps` list of SubagentChainStep — CORRECT (`schemas/pipeline.py:118`)

### SubagentChainStep
- `task_type` str — CORRECT (`schemas/pipeline.py:109`)
- `prompt_data_template` str — CORRECT (`schemas/pipeline.py:110`)
- `response_model` Optional[str] — CORRECT (`schemas/pipeline.py:111`)
- `condition` Optional[str] — CORRECT (`schemas/pipeline.py:112`)

### MemoryConfig
- All fields match — CORRECT (`schemas/pipeline.py:128-138`)
- `ttl_days_low=7`, `ttl_days_medium=30`, `ttl_days_high=0` — CORRECT
- `consolidation_cooldown_hours=24` — CORRECT
- `max_entries_per_propose=3` — CORRECT
- `consolidation_merge_window_hours=72` — CORRECT
- `truncation_llm_*` fields — CORRECT

### SourceConfig
- `id` pattern `^[a-z0-9_]+$` — CORRECT (`schemas/source.py:107`)
- `name` min_length=1, max_length=128 — CORRECT (`schemas/source.py:108`)
- `type` validated by field_validator — CORRECT (`schemas/source.py:115-122`)
- `enabled` default=True — CORRECT (`schemas/source.py:110`)
- `schedule_minutes` default=30, ge=5, le=1440 — CORRECT (`schemas/source.py:111`)
- `config` dict — CORRECT (`schemas/source.py:112`)
- `topics` TopicMatchConfig — CORRECT (`schemas/source.py:113`)
- `validate_adapter_config` validates against RSSConfig/APIConfig/WebConfig — CORRECT (`schemas/source.py:124-131`)

### RSSConfig
- All fields match — CORRECT (`schemas/source.py:29-39`)
- `feed_url` required — CORRECT (`schemas/source.py:30`)
- `max_items` default=50, ge=1, le=200 — CORRECT (`schemas/source.py:31`)
- `request_timeout` default=15, ge=5, le=60 — CORRECT (`schemas/source.py:32`)
- `min_content_length` default=200, ge=0, le=5000 — CORRECT (`schemas/source.py:34-39`)

### APIConfig
- All fields match — CORRECT (`schemas/source.py:42-56`)
- `list_url` required — CORRECT (`schemas/source.py:43`)
- `list_method` default="json_array" — CORRECT (`schemas/source.py:44`)
- `filters` list — CORRECT (`schemas/source.py:50`)
- `pagination` PaginationConfig — CORRECT (`schemas/source.py:52`)
- `auth_header` — CORRECT (`schemas/source.py:56`)

### TopicMatchConfig
- All fields match — CORRECT (`schemas/source.py:23-26`)
- `match_mode` MatchMode default=KEYWORD — CORRECT
- `include` default=["other"] — CORRECT
- `min_confidence` default=0.5, ge=0.0, le=1.0 — CORRECT

### WebConfig
- All fields match — CORRECT (`schemas/source.py:88-96`)
- `base_url`, `listing_url` required — CORRECT
- `listing` ListingConfig, `article` ArticleSelectors — CORRECT
- `request_delay_min=1.5`, `request_delay_max=4.0` — CORRECT
- `max_retries=3` — CORRECT

### ListingConfig
- All fields match — CORRECT (`schemas/source.py:73-77`)
- `card_selector`, `link_selector` required — CORRECT
- `link_attribute` default="href" — CORRECT
- `pagination` PaginationConfig — CORRECT

### ArticleSelectors
- All fields Optional — CORRECT (`schemas/source.py:80-85`)

### PaginationConfig
- All fields match — CORRECT (`schemas/source.py:59-70`)
- `enabled` default=False — CORRECT
- `type` default="next_link" with validator — CORRECT
- `max_pages` default=3 — CORRECT

### LLM Response Schemas
- `SelectionResult` — CORRECT (`schemas/llm_responses.py:16-22`)
- `ResearchBrief` — CORRECT (`schemas/llm_responses.py:53-81`)
- `KeyClaim`, `DirectQuote`, `ExternalSource`, `RelatedArticle` — CORRECT
- `CondensedArticle` — CORRECT (`schemas/llm_responses.py:101-129`)
- `ExecutiveSummary` — CORRECT (`schemas/llm_responses.py:151-158`)
- `NewsletterBrief` — CORRECT (`schemas/llm_responses.py:142-148`)
- `NewsletterArticle` — CORRECT (`schemas/llm_responses.py:135-139`)
- `SubagentResponse` — CORRECT (`schemas/llm_responses.py:164-173`)
- `ResearchSynthesisResponse` — CORRECT (`schemas/llm_responses.py:176-177`)
- `EditContextualizationResponse` — CORRECT (`schemas/llm_responses.py:180-183`)
- `ToolCall` — CORRECT (`schemas/llm_responses.py:186-189`)
- `ToolResult` — CORRECT (`schemas/llm_responses.py:192-195`)
- `ToolCallingResponse` — CORRECT (`schemas/llm_responses.py:198-202`)

### Task Validation Schemas
- `SelectArticleTask` — CORRECT (`schemas/tasks.py:33-42`)
- `ProcessItemTask` source_key, source_name, source_type, title required — CORRECT (`schemas/tasks.py:87-101`)
- `ProcessItemTask` validate_source_type — CORRECT (`schemas/tasks.py:103-108`)
- `GenerateNewsletterTask` validate_email — CORRECT (`schemas/tasks.py:45-56`)
- `SendEmailTask` fields — CORRECT (`schemas/tasks.py:59-63`)
- `CleanupArticleVersionsTask` — CORRECT (`schemas/tasks.py:73-84`)

### Common Schemas
- `ProviderDef` — CORRECT (`schemas/common.py:23-29`)
- `MAX_TOKENS_FIELD` = 4096, ge=256, le=128000 — CORRECT (`schemas/common.py:20`)

### Intentional Layer Violations
- `schemas/common.py` imports from `services.config_cache` — CORRECT (`schemas/common.py:75,89`)

---

## Incorrect Claims

### SendEmailTask: No email validator
- **Claim:** `# Note: No email format validator exists on this field (unlike GenerateNewsletterTask)` (schemas.md:358)
- **Actual:** `SendEmailTask` DOES have an email validator at `schemas/tasks.py:65-70`:
  ```python
  @field_validator("email")
  @classmethod
  def validate_email(cls, v: str) -> str:
      if not _EMAIL_RE.match(v):
          raise ValueError(f"Invalid email format: {v}")
      return v
  ```
- **Priority:** HIGH

### ProcessItemTask: Missing topics validation
- **Claim (by omission):** The doc lists ProcessItemTask fields but does not mention topics length validation
- **Actual:** ProcessItemTask `topics` field at `schemas/tasks.py:99` has NO max_length constraint and NO `validate_topics` validator. The topics list can grow unbounded. The `validate_topics` validator that limits to 20 items exists on a different class (not on ProcessItemTask).
- **Impact:** External callers can pass arbitrarily large topics lists without validation.
- **Priority:** MEDIUM

### PipelineConfig missing ReviewConfig in doc
- **Claim:** PipelineRootConfig has `pipeline: PipelineConfig` but ReviewConfig is not documented
- **Actual:** `PipelineConfig` has a `review: ReviewConfig` field (`schemas/pipeline.py:49`). `ReviewConfig` has `enabled: bool = False` and `auto_publish_threshold: Optional[int]` (`schemas/pipeline.py:35-41`). Not documented anywhere in schemas.md.
- **Priority:** LOW

---

## Bugs Found

### ProcessItemTask topics validation gap
- **Location:** `schemas/tasks.py:99` — `topics: Optional[list[str]] = Field(default_factory=list, description="Article topics")`
- **Issue:** No `max_length` or validator on the topics field. External API callers can submit arbitrarily large topic lists. Compare with the `validate_topics` validator that exists on a different schema but not on ProcessItemTask.
- **Priority:** MEDIUM

---

## Improvement Opportunities

### Missing Schema File: admin.py
- **Location:** `schemas/admin.py`
- **Issue:** `schemas/admin.py` contains 6 schemas not documented in the file inventory table: `ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams`. These are used for admin API request validation.
- **Priority:** HIGH

### Missing Schema File: llm.py
- **Location:** `schemas/llm.py`
- **Issue:** `schemas/llm.py` contains 5 schemas not documented: `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig`. These define LLM provider configuration shapes loaded from `providers.yaml`.
- **Priority:** HIGH

### Missing Schema: ReviewConfig
- **Location:** `schemas/pipeline.py:35-41`
- **Issue:** `ReviewConfig` is a field of `PipelineConfig` but is not documented. It has `enabled: bool = False` and `auto_publish_threshold: Optional[int]`.
- **Priority:** MEDIUM

### Missing Schemas in llm_responses.py inventory
- **Location:** `schemas/llm_responses.py`
- **Issue:** The file inventory lists 11 schemas but the file actually contains 15. Missing from inventory: `CitationItem` (line 87), `OriginalAttribution` (line 94), `KeyClaim` (line 34), `DirectQuote` (line 40), `ExternalSource` (line 28), `RelatedArticle` (line 46), `NewsletterArticle` (line 135). All of these ARE documented in the body of the file, just not in the summary table.
- **Priority:** LOW

### Missing schemas/__init__.py in inventory
- **Location:** `schemas/__init__.py`
- **Issue:** File not listed in inventory table (minor — it's an empty __init__).
- **Priority:** LOW

### SubagentConfig.chains default not documented
- **Location:** `schemas/pipeline.py:125` — `chains: dict[str, SubagentChainConfig] = Field(default_factory=dict)`
- **Issue:** The doc shows `chains: dict[str, SubagentChainConfig]` without the default_factory, implying it's required. In code it defaults to an empty dict.
- **Priority:** LOW

### SubagentChainStep.response_model/condition Optionality
- **Location:** `schemas/pipeline.py:111-112`
- **Issue:** The doc shows `response_model: Optional[str] = None` and `condition: Optional[str] = None` which is correct, but doesn't call out that both are optional (the Optional annotation implies this but explicit mention helps).
- **Priority:** LOW

---

## Stale Content

### None identified
All documented schemas exist in the current codebase. No references to removed or renamed schemas were found.

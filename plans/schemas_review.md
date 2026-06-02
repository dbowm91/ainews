# Schemas Architecture Review

## Summary
Overall health assessment: **Good** with minor documentation inaccuracies.

The schemas module is well-structured and the documentation is largely accurate. Most discrepancies are cosmetic/presentation issues where the doc shows simplified type annotations but the actual code uses explicit `Field()` constructs with validators and defaults. No actual bugs or layer violations beyond the documented intentional ones.

## Verified Claims

### File Inventory - ALL VERIFIED ✅
All 12 schema files exist with correct model names:

| File | Models Listed | Status |
|------|--------------|--------|
| `pipeline.py` | PipelineRootConfig, PipelineConfig, RoleConfig, ReviewConfig, StageConfig, NewsletterConfig, NewsletterPipelineConfig, SubagentConfig, SubagentStageConfig, SubagentChainConfig, SubagentChainStep, MemoryConfig | ✅ All present |
| `source.py` | SourceConfig, SourceType, MatchMode, RSSConfig, APIConfig, WebConfig, TopicMatchConfig, PaginationConfig, ListingConfig, ArticleSelectors | ✅ All present |
| `common.py` | ProviderDef | ✅ Present |
| `llm.py` | OllamaConfig, OpenAIConfig, AnthropicConfig, GeminiConfig, LLMProvidersConfig | ✅ All present |
| `llm_responses.py` | SelectionResult, ResearchBrief, KeyClaim, DirectQuote, ExternalSource, RelatedArticle, CitationItem, OriginalAttribution, CondensedArticle, ExecutiveSummary, NewsletterBrief, NewsletterArticle, SubagentResponse, ResearchSynthesisResponse, EditContextualizationResponse, ToolCall, ToolResult, ToolCallingResponse | ✅ All present |
| `tasks.py` | SelectArticleTask, ProcessItemTask, GenerateNewsletterTask, SendEmailTask, CleanupArticleVersionsTask | ✅ All present |
| `topic.py` | TopicDef, TopicsConfig | ✅ Present |
| `webhook.py` | WebhookCreate, WebhookResponse | ✅ Present |
| `item.py` | RawItem | ✅ Present |
| `admin.py` | ArticleIdsParams, CreateSourceRequest, UpdateSourceRequest, BulkArticleRequest, TaskStatusParams | ✅ All present |
| `search.py` | SearchConfig | ✅ Present |

### Pipeline Configuration - MOSTLY VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| StageConfig is a stub with only `tools` field | ✅ | `schemas/pipeline.py:150-156` |
| PipelineConfig has selector, researcher, writer, editor, review fields | ✅ | `schemas/pipeline.py:44-49` |
| RoleConfig field names and types | ✅ | `schemas/pipeline.py:16-32` |
| RoleConfig `max_tokens` uses MAX_TOKENS_FIELD | ✅ | `schemas/pipeline.py:20` |
| ReviewConfig auto_publish_threshold | ✅ | `schemas/pipeline.py:35-41` |
| SubagentStageConfig field names and types | ✅ | `schemas/pipeline.py:93-105` |
| SubagentConfig has no `enabled` at top level | ✅ | `schemas/pipeline.py:121-134` |
| SubagentChainConfig/steps | ✅ | `schemas/pipeline.py:108-118` |
| MemoryConfig field names and values | ✅ | `schemas/pipeline.py:137-147` |
| NewsletterConfig field defaults | ✅ | `schemas/pipeline.py:52-57` |
| NewsletterPipelineConfig defaults | ✅ | `schemas/pipeline.py:60-90` |

### Source Configuration - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| SourceType enum values (RSS, API, WEB) | ✅ | `schemas/source.py:12-15` |
| MatchMode enum values (KEYWORD, CONTEXTUAL) | ✅ | `schemas/source.py:18-20` |
| RSSConfig field names and defaults | ✅ | `schemas/source.py:29-39` |
| APIConfig field names, defaults, pagination | ✅ | `schemas/source.py:57-71` |
| WebConfig field names and defaults | ✅ | `schemas/source.py:89-98` |
| TopicMatchConfig defaults | ✅ | `schemas/source.py:23-26` |
| PaginationConfig type validator | ✅ | `schemas/source.py:43-54` |
| SourceConfig field validators | ✅ | `schemas/source.py:117-133` |
| ADAPTER_CONFIGS mapping | ✅ | `schemas/source.py:101-105` |

### LLM Response Schemas - MOSTLY VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| SelectionResult fields | ✅ | `schemas/llm_responses.py:16-22` |
| ResearchBrief fields including `context_notes` | ✅ | `schemas/llm_responses.py:53-81` |
| KeyClaim, DirectQuote, ExternalSource, RelatedArticle | ✅ | `schemas/llm_responses.py:28-50` |
| CitationItem, OriginalAttribution | ✅ | `schemas/llm_responses.py:87-98` |
| ExecutiveSummary single `summary` field | ✅ | `schemas/llm_responses.py:151-158` |
| NewsletterBrief themes/highlights/connections | ✅ | `schemas/llm_responses.py:142-148` |
| NewsletterArticle fields | ✅ | `schemas/llm_responses.py:135-139` |
| SubagentResponse, ResearchSynthesisResponse, EditContextualizationResponse | ✅ | `schemas/llm_responses.py:164-183` |
| ToolCall, ToolResult, ToolCallingResponse | ✅ | `schemas/llm_responses.py:186-201` |

### Tasks Schemas - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| SelectArticleTask fields and validator | ✅ | `schemas/tasks.py:33-42` |
| ProcessItemTask source_type validator | ✅ | `schemas/tasks.py:103-108` |
| ProcessItemTask topics validator (max 20) | ✅ | `schemas/tasks.py:110-116` |
| SendEmailTask email validator | ✅ | `schemas/tasks.py:65-70` |
| CleanupArticleVersionsTask | ✅ | `schemas/tasks.py:73-84` |

### Admin Schemas - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| ArticleIdsParams fields and validators | ✅ | `schemas/admin.py:19-54` |
| CreateSourceRequest / UpdateSourceRequest | ✅ | `schemas/admin.py:57-92` |
| BulkArticleRequest action/status validators | ✅ | `schemas/admin.py:95-134` |
| TaskStatusParams validator | ✅ | `schemas/admin.py:137-147` |

### Common Schemas - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| ProviderDef field names and pattern | ✅ | `schemas/common.py:23-29` |
| MAX_TOKENS_FIELD definition | ✅ | `schemas/common.py:20` |
| cached_config layer violation documented | ✅ | `schemas/common.py:72-79` |

### LLM Config - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| OllamaConfig, OpenAIConfig, AnthropicConfig, GeminiConfig | ✅ | `schemas/llm.py:17-71` |
| OpenAIConfig.api_key validator resolves ${ENV_VAR} | ✅ | `schemas/llm.py:33-39` |
| AnthropicConfig.api_key validator | ✅ | `schemas/llm.py:49-55` |
| GeminiConfig.api_key validator | ✅ | `schemas/llm.py:65-71` |
| ADAPTER_CONFIGS mapping for LLM providers | ✅ | `schemas/llm.py:74-79` |
| LLMProvidersConfig default_provider="ollama-local" | ✅ | `schemas/llm.py:82-84` |

### Search Config - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| SearchConfig providers/default_provider | ✅ | `schemas/search.py:10-12` |
| Load from `search_providers` key | ✅ | `schemas/search.py:22` |
| Default search provider key `default_search_provider` | ✅ | `schemas/search.py:23` |

### Topic Config - VERIFIED ✅

| Claim | Status | Location |
|-------|--------|----------|
| TopicDef fields | ✅ | `schemas/topic.py:11-15` |
| TopicsConfig topics dict | ✅ | `schemas/topic.py:18-19` |

## Discrepancies Found

### 1. **Minor**: CondensedArticle `why_it_matters` and `what_to_watch` defaults
- **Claim** (line 349): `why_it_matters: str | None = None`
- **Claim** (line 351): `what_to_watch: str | None = None`
- **Reality**: Both are `str = Field(default="", ...)` (empty string default, not None)
- **Severity**: Minor
- **Location**: `schemas/llm_responses.py:104-107, 118-120`
- **Suggested fix**: Update doc to show:
  ```python
  why_it_matters: str = Field(default="", description="1-2 sentences connecting to bigger trend")
  # ...
  what_to_watch: str = Field(default="", description="Forward-looking indicator")
  ```

### 2. **Minor**: NewsletterConfig has implicit default in PipelineRootConfig
- **Claim** (line 77): `newsletter: NewsletterConfig` (no default shown)
- **Reality**: Code has `newsletter: NewsletterConfig = Field(default_factory=NewsletterConfig)` making it optional with a default
- **Severity**: Minor
- **Location**: `schemas/pipeline.py:161`
- **Suggested fix**: Update doc line 77 to show the Field() wrapper, or note that NewsletterConfig has a default_factory

### 3. **Minor**: GenerateNewsletterTask validators not shown in doc
- **Claim** (line 458-460): Shows task without validators
- **Reality**: Code has `validate_email` field validator on `dry_run_email`
- **Severity**: Minor
- **Location**: `schemas/tasks.py:49-56`
- **Suggested fix**: Add validator note to doc or show the full model with validator

### 4. **Minor**: SearchConfig default_provider YAML key mismatch
- **Claim** (line 537-540): Shows `default_provider: str = "duckduckgo"` without explaining YAML key
- **Reality**: Schema field is `default_provider` but YAML key is `default_search_provider`
- **Severity**: Minor
- **Location**: `schemas/search.py:12,23`
- **Suggested fix**: Add note: "Note: reads from `default_search_provider` key in YAML, not `default_provider`"

### 5. **Minor**: ProcessItemTask field descriptions differ slightly
- **Claim** (line 438): "Article topics (max 20)"
- **Reality**: Code description just says "Article topics" (max 20 enforced by validator, not in description)
- **Severity**: Minor
- **Location**: `schemas/tasks.py:99`
- **Suggested fix**: Update code description to include "(max 20)" for consistency

## Bugs Identified

None. All code is functioning correctly. Discrepancies are documentation-only.

## Improvement Opportunities

### 1. Add missing max_items to WebConfig
- **Improvement**: WebConfig has `max_items` field but it was added to doc as part of the WebAdapter pagination fix (Wave 8). The doc doesn't show it in the WebConfig class definition.
- **Location**: `schemas/source.py:94`
- **Benefit**: Documentation accuracy for WebConfig completeness

### 2. Clarify SearchConfig YAML key naming
- **Improvement**: Add clarifying comment that `SearchConfig.default_provider` maps to `default_search_provider` in YAML
- **Location**: `schemas/search.py:12`
- **Benefit**: Prevents confusion about schema field naming vs YAML key naming

### 3. Document GenerateNewsletterTask dry_run_email validator
- **Improvement**: Show the email validation in the task schema documentation
- **Location**: `schemas/tasks.py:49-56`
- **Benefit**: Complete documentation of input validation behavior

## Stale Items Found

None. No outdated documentation or obsolete references detected.

## Recommendations

1. **Low Priority**: Update `CondensedArticle.why_it_matters` and `what_to_watch` documentation to show `Field(default="", ...)` instead of `= None`
2. **Low Priority**: Add `Field(default_factory=NewsletterConfig)` to PipelineRootConfig.newsletter in doc
3. **Low Priority**: Add note about `GenerateNewsletterTask` email validator
4. **Low Priority**: Clarify `SearchConfig.default_provider` vs `default_search_provider` YAML key mapping
5. **Low Priority**: Add `max_items` to WebConfig documentation section

All recommendations are documentation-only fixes. The actual schema code is correct and well-implemented.
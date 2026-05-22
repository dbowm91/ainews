# Schemas Module Review

This document compares `architecture/schemas.md` against actual implementation code in `schemas/`.

---

## Verified Claims

### File Inventory
All documented files exist and contain the documented models:
- `schemas/pipeline.py` - `PipelineRootConfig`, stage configs
- `schemas/source.py` - `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig`, `TopicMatchConfig`
- `schemas/llm.py` - Provider definitions
- `schemas/llm_responses.py` - `SelectionResult`, `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief`
- `schemas/tasks.py` - Task input validation
- `schemas/topic.py` - Topic definitions
- `schemas/webhook.py` - `WebhookCreate`, `WebhookResponse`
- `schemas/item.py` - `RawItem`
- `schemas/admin.py` - Admin request schemas
- `schemas/search.py` - `SearchConfig`, `load_search_config`

### StageConfig is a Stub
The documentation correctly notes that `StageConfig` is a stub containing only `tools: list[str]`. The implementation (lines 141-147 of `pipeline.py`) confirms this with an explicit docstring.

### NewsletterBrief Does NOT Have preamble/footer/articles Fields
The documentation correctly notes these fields are not implemented. The actual `NewsletterBrief` (lines 142-148 of `llm_responses.py`) has only `themes`, `highlights`, and `connections`.

### RoleConfig Has All Documented Fields
The `RoleConfig` class in `pipeline.py` (lines 16-33) matches the documentation with all role-specific optional fields.

### MemoryConfig Matches Documentation
`MemoryConfig` in `pipeline.py` (lines 128-138) exactly matches the documented structure.

### SubagentChainStep and SubagentChainConfig Match
Both classes match their documentation.

### Source Configuration Classes Match
- `RSSConfig`, `APIConfig`, `TopicMatchConfig`, `WebConfig`, `ListingConfig`, `ArticleSelectors`, `PaginationConfig` all match their documentation.

### Intentional Layer Violation Documented
The layer violation in `schemas/common.py` importing from `services.config_cache` is properly documented with inline comments.

### LLM Response Schemas Match
- `SelectionResult` matches
- `ResearchBrief` and all nested types (`KeyClaim`, `DirectQuote`, `ExternalSource`, `RelatedArticle`) match
- `CondensedArticle` matches (with unmentioned `why_it_matters`, `what_to_watch`, etc.)
- `ExecutiveSummary` matches (single `summary` field)

---

## Discrepancies

### 1. SubagentConfig Has No `enabled` Field
**Documentation says:**
```python
class SubagentConfig(BaseModel):
    enabled: bool = True   # <-- Documented as existing
    default: SubagentStageConfig
    ...
```

**Actual implementation (pipeline.py lines 121-125):**
```python
class SubagentConfig(BaseModel):
    default: SubagentStageConfig = Field(default_factory=SubagentStageConfig)
    research: SubagentStageConfig = Field(default_factory=SubagentStageConfig)
    edit: SubagentStageConfig = Field(default_factory=SubagentStageConfig)
    chains: dict[str, SubagentChainConfig] = Field(default_factory=dict)
```

There is NO `enabled` field on `SubagentConfig`. The `enabled` flag exists on individual `SubagentStageConfig` instances.

### 2. ArticleSelectors.title_selector is Optional
**Documentation says:**
```python
class ArticleSelectors(BaseModel):
    title_selector: str   # <-- Required in docs
```

**Actual implementation (source.py lines 80-85):**
```python
class ArticleSelectors(BaseModel):
    title_selector: Optional[str] = None   # <-- Optional in code
```

### 3. GenerateNewsletterTask Has No Email Validator
**Documentation shows validators for `dry_run_email`**, but **actual implementation (tasks.py lines 49-56) does NOT have this validator.** The field exists but without email format validation.

### 4. ProcessItemTask Validator Description Mismatch
The documentation only mentions validators for `source_type` and `topics`, but the implementation also has an `article_id_positive` validator (tasks.py lines 37-42).

### 5. CleanupArticleVersionsTask Has No Validator in Docs
**Documentation does not mention the field validator on `days_to_keep`.** The actual implementation (tasks.py lines 77-84) has validation logic.

### 6. Admin Schemas Are Request, Not Response Schemas
**Documentation says:** "Admin response schemas"

**Actual implementation (`admin.py` line 1):** "Pydantic schemas for admin API request validation."

The schemas in `admin.py` validate **request** parameters, not response schemas.

### 7. Missing Subagent Response Schemas in Documentation
**Documentation only mentions:** `SelectionResult`, `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief`

**Actual implementation includes additional models in `llm_responses.py`:**
- `SubagentResponse` (lines 164-173)
- `ResearchSynthesisResponse` (lines 176-178)
- `EditContextualizationResponse` (lines 180-183)
- `ToolCall` (lines 186-189)
- `ToolResult` (lines 192-195)
- `ToolCallingResponse` (lines 198-202)

---

## Bugs

### 1. SearchConfig Uses Wrong Caching Function
The `load_search_config` function (search.py lines 28-31) uses `cached_config` without passing `config_path`, unlike other config loaders that use `cached_config_with_mtime`. This means search config won't be automatically invalidated when `providers.yaml` changes.

### 2. APIAdapter AuthHeader Comment Misleading
In `source.py` line 56, the comment says "only Bearer auth supported (value always 'Bearer {api_key}')" but this logic is not enforced in the schema - the `auth_header` field is just stored as a string. The Bearer token construction happens elsewhere in the adapter.

---

## Improvements

1. **Update SubagentConfig Documentation** - Remove the `enabled: bool = True` field from `SubagentConfig` in the documentation, as it doesn't exist in the implementation.

2. **Fix ArticleSelectors.title_selector Documentation** - Either mark `title_selector` as optional in the docs or change the implementation to be required.

3. **Add GenerateNewsletterTask Email Validator to Docs** - The implementation has email validation for `dry_run_email`, but documentation doesn't reflect this.

4. **Add CleanupArticleVersionsTask Validator to Docs** - The implementation has a validator for `days_to_keep`, but documentation doesn't mention it.

5. **Correct Admin Schemas Description** - Change "Admin response schemas" to "Admin request schemas" in the file inventory table.

6. **Document Subagent Response Schemas** - Add documentation for `SubagentResponse`, `ResearchSynthesisResponse`, `EditContextualizationResponse`, `ToolCall`, `ToolResult`, and `ToolCallingResponse`.

7. **Fix SearchConfig Caching** - Consider changing `load_search_config` to use `cached_config_with_mtime` for consistency with other loaders.

8. **Document ProcessItemTask article_id Validator** - The implementation has an `article_id_positive` validator that isn't mentioned in the documentation.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 15 |
| Discrepancies | 7 |
| Bugs | 2 |
| Improvements | 8 |

The documentation is largely accurate but has several discrepancies regarding:
- Missing `enabled` field on `SubagentConfig`
- Optional vs required `title_selector`
- Missing field validators in docs
- Incorrect description of admin.py (request vs response)
- Missing subagent response schemas

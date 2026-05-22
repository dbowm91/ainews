# Schemas Module Architecture Review

## Summary

Verified claims in `architecture/schemas.md` against actual codebase. Found **1 CRIT**, **2 HIGH**, **3 MED**, and **2 LOW** issues.

---

## File Inventory Verification

| Documented File | Actual File | Status |
|----------------|-------------|--------|
| `pipeline.py` | ✓ Exists | VERIFIED |
| `source.py` | ✓ Exists | VERIFIED |
| `llm.py` | ✓ Exists | VERIFIED |
| `llm_responses.py` | ✓ Exists | VERIFIED |
| `tasks.py` | ✓ Exists | VERIFIED |
| `topic.py` | ✓ Exists | VERIFIED |
| `webhook.py` | ✓ Exists | VERIFIED |
| `item.py` | ✓ Exists | VERIFIED |
| `admin.py` | ✓ Exists | VERIFIED |
| `search.py` | ✓ Exists | **MISSING FROM DOC** |

---

## Verified Claims

### pipeline.py
- `StageConfig` is correctly documented as a stub with only `tools: list[str]`
- `PipelineRootConfig` structure matches
- `NewsletterConfig`, `NewsletterPipelineConfig`, `SubagentConfig`, `MemoryConfig` all match
- `SubagentChainStep` and `SubagentChainConfig` match
- `RoleConfig` has extra fields not in doc (`system_prompt`, `db_related_max`, `max_article_text_length`, `max_key_points`, `max_tags`) but doc doesn't claim completeness

### source.py
- `SourceConfig` structure matches (id pattern, name, type, enabled, schedule_minutes, config, topics)
- `RSSConfig` matches
- `APIConfig` mostly matches (see HIGH issues)
- `WebConfig` matches
- `PaginationConfig` matches with validator
- `TopicMatchConfig` properly defined but not documented in file inventory

### llm_responses.py
- `SelectionResult` matches
- `ResearchBrief` matches (KeyClaim not list[str], context_notes not context)
- `CondensedArticle` matches (why_it_matters, key_points, what_to_watch documented correctly)
- `ExecutiveSummary` correctly documented as single `summary` field
- `NewsletterBrief` correctly notes missing preamble/footer/articles fields
- `NewsletterArticle` matches

### tasks.py
- `SelectArticleTask` matches
- `GenerateNewsletterTask` matches
- `SendEmailTask` matches
- `CleanupArticleVersionsTask` matches
- `ProcessItemTask` exists with different structure than old doc (see MED)

### Other Files
- `topic.py` / `TopicDef` / `TopicsConfig` - VERIFIED
- `webhook.py` / `WebhookCreate` / `WebhookResponse` - VERIFIED
- `item.py` / `RawItem` - VERIFIED
- `admin.py` - VERIFIED
- `llm.py` / provider configs - VERIFIED

---

## Discrepancies and Issues

### CRIT

#### 1. Missing `search.py` from documentation
- **File:** `schemas/search.py` (entire file)
- **Issue:** The file `schemas/search.py` with `SearchConfig`, `_load_search_config_from_file`, and `load_search_config` is entirely missing from the document's file inventory
- **Impact:** Documentation does not reflect actual codebase
- **Recommendation:** Add `search.py` to the file inventory table and document `SearchConfig`

---

### HIGH

#### 2. APIConfig `request_timeout` missing from documentation
- **File:** `schemas/source.py:53`
- **Code:**
  ```python
  class APIConfig(BaseModel):
      # ... documented fields ...
      request_timeout: int = 15  # Line 53 - NOT in doc
      user_agent: str = "AINewsBot/1.0"
      api_key: Optional[str] = None
      auth_header: Optional[str] = None
  ```
- **Issue:** Document shows `auth_header` as the last field but `request_timeout` exists before `user_agent`. Doc doesn't mention `request_timeout` at all.
- **Recommendation:** Update doc to include `request_timeout: int = 15`

#### 3. APIConfig `auth_header` description misleading
- **File:** `schemas/source.py:56` / Doc line 112
- **Code:** `auth_header: Optional[str] = None`
- **Doc says:** `# e.g., "Authorization"` implying it holds the header name
- **Issue:** The comment suggests `auth_header` is a header name template, but the field actually stores the **header name** (e.g., "Authorization") for Bearer token auth. The API adapter uses it as `headers={auth_header: f"Bearer {api_key}"}`
- **Recommendation:** Clarify comment: `# Header name for Bearer auth (e.g., "Authorization")`

---

### MED

#### 4. Documented `ReviewConfig` default inconsistent
- **File:** `schemas/pipeline.py:38-40`
- **Doc says:** "auto_publish_threshold: Default: 80"
- **Code:**
  ```python
  auto_publish_threshold: Optional[int] = Field(
      default=None,
      description="Auto-publish articles with impact_score >= this value, bypassing review. Default: 80.",
  )
  ```
- **Issue:** The field defaults to `None` but the description says "Default: 80". If `None`, no auto-publish happens (all go to review unless explicitly configured). Actual default behavior is NO auto-publish.
- **Recommendation:** Either change default to `80` or fix description to say "Default: None (disabled)"

#### 5. `ProcessItemTask` documented differently than actual
- **File:** `schemas/tasks.py:87-117`
- **Doc notes:** "actual implementation differs from older documentation"
- **Actual fields (verified):**
  - `source_key`, `source_name`, `source_type`, `external_id`, `title`, `url`, `author`, `published_at`, `text_content`, `raw_score`, `raw_metadata`, `topics`, `min_content_length`, `run_id`
- **Issue:** The doc shows these fields in a comment but doesn't clarify the actual implementation structure vs old documentation
- **Recommendation:** Update doc with accurate field list from actual code

#### 6. Layer violation: `schemas/common.py` imports from `services.config_cache`
- **File:** `schemas/common.py:75,89`
- **Issue:** The document states schemas contain Pydantic models for validation/serialization. The `cached_config` and `cached_config_with_mtime` functions import from `services.config_cache`, violating clean layering. This is **documented as intentional** with comments ("Layer violation: schemas should not import from services. This is intentional..."), but it's still a layering violation.
- **Recommendation:** This is a known architectural issue. Document it explicitly in the architecture documentation rather than hiding it in code comments.

---

### LOW

#### 7. `TopicMatchConfig` not documented as separate model
- **File:** `schemas/source.py:23-27`
- **Issue:** `TopicMatchConfig` (with `match_mode`, `include`, `min_confidence`) exists but is not listed in the file inventory. It is referenced in `SourceConfig.topics` but never defined in the doc.
- **Recommendation:** Add `TopicMatchConfig` to source.py documentation section

#### 8. `admin.py` imports `VALID_PIPELINE_STATUSES` from `constants.py`
- **File:** `schemas/admin.py:48-49, 119`
- **Code:**
  ```python
  from constants import VALID_PIPELINE_STATUSES
  # ...
  if v not in VALID_PIPELINE_STATUSES:
  ```
- **Issue:** Schema validation depends on a central constants file. If VALID_PIPELINE_STATUSES changes, schema validation changes. This is a soft coupling.
- **Recommendation:** Document that `admin.py` schema validators depend on `constants.VALID_PIPELINE_STATUSES`

---

## Security Considerations

1. **No security issues found** - Pydantic validation is properly used with `Field(...), min_length, max_length, pattern` constraints
2. Email validation in `tasks.py` uses regex but it's for basic format checking which is appropriate
3. `auth_header` in APIConfig is just a header name (no secrets stored there)

---

## Performance Considerations

1. **No performance issues found** - schemas are pure Pydantic models with no heavy computation
2. Config caching in `common.py` uses Redis with fallback to direct file load

---

## Recommendations Summary

| Priority | Issue | Location |
|----------|-------|----------|
| CRIT | Missing `search.py` from documentation | `schemas/search.py` (entire file) |
| HIGH | APIConfig `request_timeout` missing from doc | `schemas/source.py:53` |
| HIGH | APIConfig `auth_header` description misleading | `schemas/source.py:56` / doc line 112 |
| MED | ReviewConfig default inconsistent with description | `schemas/pipeline.py:38-40` |
| MED | ProcessItemTask structure not accurately documented | `schemas/tasks.py:87-117` |
| MED | Layer violation in `common.py` not documented | `schemas/common.py:75,89` |
| LOW | TopicMatchConfig not documented | `schemas/source.py:23-27` |
| LOW | admin.py depends on constants.py | `schemas/admin.py:48-49` |
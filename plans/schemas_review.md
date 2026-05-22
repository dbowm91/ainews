# Schemas Module Review

## Summary

Document: `architecture/schemas.md` (339 lines)
Reviewed: All schema files in `schemas/` package

---

## Verified Claims

### File Inventory
All 12 files listed in the document exist and match purpose:

| File | Verified |
|------|----------|
| `pipeline.py` | ✅ `PipelineRootConfig`, stage configs, `RoleConfig`, `SubagentConfig` |
| `source.py` | ✅ `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig`, `TopicMatchConfig` |
| `llm.py` | ✅ Provider definitions (`OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`) |
| `llm_responses.py` | ✅ All response schemas |
| `tasks.py` | ✅ All task input validation schemas |
| `topic.py` | ✅ `TopicDef`, `TopicsConfig` |
| `webhook.py` | ✅ `WebhookCreate`, `WebhookResponse` |
| `item.py` | ✅ `RawItem` |
| `admin.py` | ✅ Admin API request schemas |
| `search.py` | ✅ `SearchConfig`, `load_search_config` |

### Key Verified Implementation Details

1. **StageConfig is a stub** ✅ - Confirmed at `schemas/pipeline.py:141-147`
   - Only has `tools: list[str]`
   - Docstring explicitly states actual config is in `RoleConfig` and `SubagentStageConfig`

2. **SourceConfig validation** ✅ - `schemas/source.py:115-131`
   - `validate_type` checks against `ADAPTER_CONFIGS` dict
   - `validate_adapter_config` uses Pydantic `model_validate` to validate config dict

3. **PaginationConfig** ✅ - `schemas/source.py:59-70`
   - Has `type` field validator
   - Validates against `("next_link", "query_param", "none")`
   - Document correctly notes this

4. **Layer violation in common.py** ✅ - Documented at `schemas/common.py:72-73,86-87`
   - `cached_config` and `cached_config_with_mtime` import from `services.config_cache`
   - Comment documents intentional violation

5. **MemoryConfig** ✅ - `schemas/pipeline.py:128-138`
   - All fields match document

6. **ExecutiveSummary** ✅ - Single `summary` field at `schemas/llm_responses.py:151-158`

7. **NewsletterBrief** ✅ - `schemas/llm_responses.py:142-148`
   - No `preamble`, `footer`, or `articles` fields (document correctly notes these are not implemented)

8. **Task schemas** ✅ - All match document
   - `SelectArticleTask`, `ProcessItemTask`, `GenerateNewsletterTask`, `SendEmailTask`, `CleanupArticleVersionsTask`

---

## Discrepancies and Issues

### MEDIUM: `contains` Filter Not Implemented

**Document says:** `filters: list[dict[str, Any]]  # equals, min, exists`
- Listed filter operations: `equals`, `min`, `exists`

**Actual implementation:** `adapters/api.py:196-210`
```python
def _passes_filters(self, data: Any, filters: list[dict]) -> bool:
    if not filters:
        return True
    for f in filters:
        current = self._resolve_path(data, f.get("field", ""))
        if "equals" in f and current != f["equals"]:
            return False
        if "min" in f:
            try:
                if float(current) < f["min"]:
                    return False
            except (ValueError, TypeError):
                return False
        if "exists" in f and f["exists"] and current is None:
            return False
    return True
```

The `contains` filter operation is NOT implemented. If a config uses `{"contains": "value"}`, it is silently ignored.

**Fix:** Add to `_passes_filters`:
```python
if "contains" in f:
    if f["contains"] not in str(current):
        return False
```

---

### MEDIUM: ArticleSelectors date_attribute Default Mismatch

**Document says:** `date_attribute: str = "datetime"`
**Actual:** `schemas/source.py:84`
```python
date_attribute: Optional[str] = None
```

Document says default is `"datetime"` but code defaults to `None`. This is a documentation inaccuracy.

---

### LOW: APIConfig Missing `auth_type` Field

**Document says:** `auth_header: Optional[str] = None    # Header name for Bearer auth token (e.g., "Authorization")`
**Actual:** `schemas/source.py:56`
```python
auth_header: Optional[str] = None
```

The `auth_type` field mentioned in APIAdapter notes is not in the schema (but APIAdapter only supports Bearer token anyway, so this is just a naming issue).

---

### LOW: SearchConfig ProviderDef Pattern

**Document says:** `ProviderDef` has `pattern=r"^[a-z0-9_\-]+$"` (line 26 in common.py)
**Actual:** `schemas/common.py:26`
```python
id: str = Field(..., pattern=r"^[a-z0-9_\-]+$")
```

Pattern includes underscore (`_`) and hyphen (`-`). This is correctly implemented.

---

### LOW: APIAdapter Authentication Notes

**AGENTS.md says:** "APIAdapter only supports Bearer token authentication. No API key header support (e.g., `X-Api-Key`) is implemented."

The schema has `auth_header` to customize header name, but implementation at `adapters/api.py:165-170` always uses `Bearer` prefix:
```python
if cfg.api_key:
    if cfg.auth_header:
        headers[cfg.auth_header] = f"Bearer {cfg.api_key}"
    else:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
```

This is correctly implemented per Bearer token spec.

---

## Documentation Issues

### OUTDATED: `item_url` Template Description

**Document says:** `item_url: Optional[str] = None       # Template for individual item URLs`
**Actual:** Works with `cfg.item_url.format(id=item_id)` at `adapters/api.py:163`

The `item_url` is a Python format string using `{id}` placeholder. Documentation doesn't specify this.

---

## Recommendations

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| MED | Missing `contains` filter | `adapters/api.py:196-210` | Implement `contains` filter operation |
| MED | Documentation inaccuracy | `schemas/source.py:84` | Update `date_attribute` default to `None` in docs |
| LOW | Missing `auth_type` field | Not applicable | Consider documenting `auth_type` limitation |
| LOW | `item_url` template format | `adapters/api.py:163` | Document `{id}` placeholder in schema docstring |

---

## Conclusion

The schemas module is well-documented overall. The main issue is the missing `contains` filter operation in `APIAdapter._passes_filters()`. This is a functional gap between documented capability and implementation. All other discrepancies are minor documentation inaccuracies or naming differences that don't affect functionality.
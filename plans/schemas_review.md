# Schemas Module Architecture Review

## Summary

The `schemas/` package contains Pydantic models for validation and serialization. The document at `architecture/schemas.md` is largely accurate but has several discrepancies, missing implementations, and one duplicate `except` block bug.

---

## Verified Claims

| Claim | Status |
|-------|--------|
| File Inventory: `pipeline.py` with `PipelineRootConfig`, stage configs | ✓ Correct |
| File Inventory: `source.py` with `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig` | ✓ Correct |
| File Inventory: `llm.py` with Provider definitions | ✓ Correct |
| File Inventory: `llm_responses.py` with response schemas | ✓ Correct |
| File Inventory: `tasks.py` with task input validation | ✓ Correct |
| File Inventory: `topic.py` with topic definitions | ✓ Correct |
| File Inventory: `webhook.py` with `WebhookCreate`, `WebhookResponse` | ✓ Correct |
| `StageConfig` is a stub with only `tools: list[str]` | ✓ Correct |
| `NewsletterConfig`, `NewsletterPipelineConfig`, `SubagentConfig`, `MemoryConfig` fields | ✓ Correct |
| `SourceConfig.validate_adapter_config` validates config against RSS/API/Web configs | ✓ Correct |
| `PaginationConfig` pagination type validator | ✓ Correct |
| `SelectionResult`, `ResearchBrief` (with `KeyClaim`, `DirectQuote`, etc.) | ✓ Correct |
| `CondensedArticle` has `why_it_matters` and other additional fields beyond doc | ✓ Noted (doc acknowledged) |
| `ExecutiveSummary` has single `summary` field (not 6 fields) | ✓ Correct |
| `NewsletterBrief` does NOT have preamble/footer/articles fields | ✓ Correct (doc acknowledged) |
| Layer violation in `schemas/common.py` importing from `services.config_cache` | ✓ Documented and intentional |

---

## Discrepancies and Issues

### CRIT-1: Duplicate `except Exception` Blocks in `cached_config_with_mtime`

**File:** `schemas/common.py:96-99`

```python
    except Exception:  # noqa: BLE001
        return cast(T, loader_fn())
    except Exception:  # noqa: BLE001
        return cast(T, loader_fn())
```

The second `except` block on line 98 is **completely unreachable** — if the first `except` catches any exception, it returns, so the second block never executes. This is a copy-paste bug.

**Fix:** Remove line 98 (`except Exception: return cast(T, loader_fn())`).

**Priority:** CRIT — dead code that indicates a bug, however the fallback behavior still works by accident.

---

### CRIT-2: `ArticleSelectors` Field Name Mismatch in WebConfig

**File:** `schemas/source.py:80-85`

The document at line 133 says `date_attribute: str = "datetime"` but the actual implementation at line 84 is:

```python
date_attribute: Optional[str] = None
```

The field is `Optional` with `None` default, not a required `str` with `"datetime"` default. This affects the web adapter configuration expectations.

**Priority:** CRIT — web scraper config may not work correctly with default `None` when date attribute is expected to be `"datetime"`.

---

### CRIT-3: `title_selector` Required in ArticleSelectors But Document Says Optional

**File:** `schemas/source.py:81`

The document does not specify whether fields in `ArticleSelectors` are required/optional. The actual code:

```python
title_selector: Optional[str] = None
```

The `WebConfig` requires both `listing` and `article` fields (both required, not Optional). If `title_selector` is `None`, the web scraper may fail at runtime. This should be validated at config load time, not silently passed through.

**Priority:** CRIT — web adapter may fail silently at runtime if `title_selector` is not provided.

---

### HIGH-1: `SourceConfig.validate_adapter_config` Always Returns `model_dump()`

**File:** `schemas/source.py:124-131`

```python
@field_validator("config")
@classmethod
def validate_adapter_config(cls, v, info):
    source_type = info.data.get("type")
    if source_type in ADAPTER_CONFIGS:
        adapter_config = ADAPTER_CONFIGS[source_type]
        return adapter_config.model_validate(v).model_dump()
    return v
```

When validation succeeds, it returns a **dict** (`model_dump()`), not the original dict structure. The original field is `dict[str, Any]`, so this is technically compatible, but it converts Pydantic models back to dicts and loses type information. This is intentional per pattern but worth noting.

**Priority:** MED — no runtime issue but a layer concern.

---

### HIGH-2: `ReviewConfig.auto_publish_threshold` Not Documented

**File:** `schemas/pipeline.py:35-40`

The document does not list `ReviewConfig` at all. It exists and has an `auto_publish_threshold` field:

```python
class ReviewConfig(BaseModel):
    enabled: bool = False
    auto_publish_threshold: Optional[int] = Field(
        default=None,
        description="Auto-publish articles with impact_score >= this value, bypassing review",
    )
```

This is used in `PipelineConfig` (line 48) but not documented.

**Priority:** MED — undocumented configuration that pipeline editors won't know about.

---

### HIGH-3: `SearchConfig` Not in Document

**File:** `schemas/search.py`

The document does not list `search.py` in the File Inventory. This file exists and provides search provider configuration.

**Priority:** MED — missing from documentation.

---

### MED-1: `RawItem` in `schemas/item.py` Not Documented

**File:** `schemas/item.py`

The document does not list `item.py` in the File Inventory. The `RawItem` model is used by adapters to represent scraped items before database insertion.

**Priority:** MED — undocumented but used in adapter layer.

---

### MED-2: `admin.py` Not Documented

**File:** `schemas/admin.py`

The document does not list `admin.py` in the File Inventory. This file contains admin API request validation schemas that are critical for the admin API layer.

**Priority:** MED — undocumented but critical for admin API validation.

---

### MED-3: `api_key` Resolution in `llm.py` Can Result in Empty String

**File:** `schemas/llm.py:33-39`

```python
@field_validator("api_key")
@classmethod
def validate_api_key(cls, v: str) -> str:
    resolved = resolve_env_var(v, required=True)
    if not resolved:
        raise ValueError("api_key must not be empty")
    return resolved
```

The `required=True` in `resolve_env_var` raises `ValueError` if the env var is not set. However, `resolve_env_var` with `required=True` raises `ValueError` which is correct, but the `if not resolved` check after is redundant (the exception would already be raised). This is not a bug but dead code.

**Priority:** LOW — dead check, not a functional issue.

---

### MED-4: `ListConfig.card_selector` is Required but Unvalidated

**File:** `schemas/source.py:73-77`

```python
class ListingConfig(BaseModel):
    card_selector: str
    link_selector: str
    link_attribute: str = "href"
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
```

`card_selector` and `link_selector` are required fields with no `min_length` validation, so empty strings would be accepted. If a scraper config has `card_selector: ""`, it would pass validation but fail at runtime.

**Priority:** MED — validation gap that could cause runtime failures.

---

### LOW-1: File Inventory Missing `__init__.py`

**File:** `schemas/__init__.py`

The file is empty. The document doesn't mention that `__init__.py` exists but is empty. This is fine but worth noting the package has no public API defined.

---

## Layering Violations

### Documented & Intentional

| Location | Violation | Acknowledged |
|----------|-----------|--------------|
| `schemas/common.py:72-73` | imports from `services.config_cache` | ✓ Yes (commented) |
| `schemas/common.py:86-87` | imports from `services.config_cache` | ✓ Yes (commented) |

No other significant layering violations found. The `ProviderDef` in `common.py` is used by both `schemas/llm.py` and `schemas/search.py`, which is appropriate.

---

## Performance Concerns

1. **Config caching with mtime tracking** in `cached_config_with_mtime` relies on Redis. If Redis is down, it falls back to direct file load. This is acceptable behavior.

2. **No caching TTL issues** detected — TTL is 300 seconds by default which is reasonable.

---

## Recommendations Summary

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| CRIT | Duplicate `except Exception` block | `common.py:98` | Remove unreachable second except block |
| CRIT | `date_attribute` is Optional[None] vs str "datetime" | `source.py:84` | Change default to `"datetime"` or update doc |
| CRIT | `title_selector` Optional but used as required by WebConfig | `source.py:81` | Add Pydantic validator or make required |
| HIGH | `ReviewConfig` not documented | `pipeline.py:35-40` | Add to `architecture/schemas.md` |
| HIGH | `SearchConfig` not in file inventory | `search.py` | Add to file inventory in doc |
| MED | `admin.py` not in file inventory | `admin.py` | Add to file inventory in doc |
| MED | `item.py` not in file inventory | `item.py` | Add to file inventory in doc |
| MED | `card_selector`/`link_selector` no min_length validation | `source.py:74-75` | Add `min_length=1` validation |
| MED | Dead code: redundant `if not resolved` check | `llm.py:37` | Remove dead check |
| LOW | Empty `__init__.py` | `__init__.py` | Consider adding exports |

---

## Verification Commands

To verify the duplicate except bug:
```bash
ruff check schemas/common.py
```

To verify model fields:
```bash
python -c "from schemas.source import SourceConfig, ArticleSelectors; print(ArticleSelectors.model_fields)"
```

To run tests:
```bash
pytest tests/schemas/ -v
```
# Services Module Architecture Review

Review of `architecture/services.md` against actual implementation in `services/` directory.

---

## Verified Correct Claims

### 1. LLM Provider Base Interface (`services/llm/base.py`)
The `BaseLLMProvider` abstract class contains ALL documented abstract methods:
- `_create_client()` - line 195-198
- `chat()` - lines 200-211
- `chat_streaming()` - lines 213-224
- `_chat_with_schema()` - lines 389-401
- `_call_api_with_tools()` - lines 403-419
- `_extract_text_and_tool_calls()` - lines 421-433
- `_format_tool_result()` - lines 435-448

The documentation shows `chat_with_tools` as abstract (lines 91-101), but implementation at lines 450-565 is concrete (not abstract). This is correct - the method has a default implementation using the abstract `_call_api_with_tools`, `_extract_text_and_tool_calls`, and `_format_tool_result` hooks.

### 2. Circuit Breaker Pattern (`services/circuit_breaker.py`)
- `CircuitBreaker` base class (lines 31-180) with CLOSED→OPEN→HALF_OPEN state machine
- `RedisCircuitBreaker` extends it for distributed coordination (lines 183-380)
- `get_breaker()` factory function (lines 388-406)
- `circuit_protected()` decorator (lines 415-448)
- State transitions properly implemented with metrics tracking

### 3. Newsletter Pipeline 3-Stage Orchestration (`services/newsletter_pipeline.py`)
- `generate_executive_summary()` function (lines 166-301) correctly orchestrates:
  - Reader stage (lines 191-212) → produces `NewsletterBrief`
  - Writer stage (lines 214-245) → produces `ExecutiveSummary`
  - Editor stage (lines 247-300) → polishes final summary
- `_run_pipeline_stage()` helper (lines 85-135) handles acquire/release/fallback
- Prompts correctly built for each stage via `build_reader_prompt()`, `build_writer_prompt()`, `build_editor_prompt()`

### 4. Article Processing Stage Responsibilities
- **`services/researcher.py`**: `build_research_prompt()` function builds research briefs with web search context, related articles, trend memory. Stage: `research_article`
- **`services/writer.py`**: `build_writer_prompt()` function writes condensed articles in Smart Brevity format with key points, citations. Stage: `write_article`
- **`services/editor.py`**: `build_editor_prompt()` and `build_editor_prompt_with_context()` functions edit and contextualize. Stage: `edit_article`

### 5. Trend Memory Service Operations (`services/trend_memory.py`)
- `propose_trend_memory()` (lines 216-277): Extracts 0-3 memory entries from completed articles
- `consolidate_topic()` (lines 300-347): Upgrades LOW importance entries to MEDIUM when HIGH importance entry arrives
- `consolidate_all_topics()` (lines 350-364): Runs consolidation across all topics
- `semantic_search_trends()` (lines 391-440): Embedding-based similarity search with cosine similarity
- `purge_expired()` (lines 367-388): Removes expired entries

### 6. Search Provider Inventory (`services/search/`)
Confirmed implementations:
- **DuckDuckGo** (`duckduckgo.py`): `@register_search_provider("duckduckgo")` - line 45
- **Google** (`google.py`): `@register_search_provider("google")` - line 58
- **SearxNG** (`searxng.py`): `@register_search_provider("searxng")` - line 58
- **SQLite FTS** (`sqlite_fts.py`): `@register_db_search_provider("sqlite_fts")` - line 52
- **Hybrid** (`hybrid.py`): `@register_search_provider("hybrid")` - provides FTS5 + vector similarity

### 7. Rate Limiter Pattern
- `services/limiter.py` implements `ModelLimiter` class with `acquire()` and `release()` methods
- `newsletter_pipeline.py` `_run_pipeline_stage()` (lines 108-135) uses `try`/`finally` pattern correctly for slot release
- **NOTE**: `limiter.acquire()` returns boolean, not the slot key - slots released via `limiter.release(provider_id, model, timeout)`

### 8. Content Extraction Cascade (`services/content_extractor.py`)
- Primary: `trafilatura` for main content extraction (line 95)
- Fallback: `readability` for article parsing (lines 106-118)
- Final fallback: Returns `ExtractionStatus.EMPTY` (line 123)
- trafilatura fetch with configurable timeout (lines 57-64)

### 9. Webhooks Security Features (`services/webhooks.py`)
- HMAC-SHA256 signatures with timestamp replay protection (lines 101-122)
- Encrypted secrets at rest via Fernet (lines 69-98)
- Retry logic with exponential backoff (lines 155-189)
- Event tracking via `WebhookEvent` model (lines 271-280)

### 10. Cost Tracking (`services/cost_tracker.py`)
- Tracks tokens used (prompt/completion) via metrics counters
- Cost per model via configurable rates (lines 17-37 default rates, lines 63-74 env override)
- Daily/monthly budget tracking via `get_cost_summary()` function
- Uses blended rate (60% input, 40% output) since metrics don't distinguish token types

---

## Discrepancies Found

### 1. Missing `hybrid.py` Search Provider in Architecture Document
**Severity**: Low (documentation gap)

The architecture document lists 4 search providers (DuckDuckGo, Google, SearxNG, SQLite FTS), but `services/search/hybrid.py` implements `HybridSearchProvider` combining FTS5 + vector similarity. This provider exists and is enabled but is missing from the documentation.

**File**: `services/search/hybrid.py`
**Fix**: Add Hybrid provider to the search provider table in `architecture/services.md`

### 2. Missing `content_extractor.py` in Architecture Tree
**Severity**: Low (documentation gap)

The architecture tree at lines 7-39 doesn't list `content_extractor.py` even though it exists at `services/content_extractor.py`. The document mentions content extraction at lines 245-249 but doesn't include it in the file inventory.

**File**: `services/content_extractor.py`
**Fix**: Add `content_extractor.py` to the file inventory tree

### 3. Missing `pipeline_utils.py` and Related Pipeline Services in Architecture Tree
**Severity**: Low (documentation gap)

Several pipeline-related services exist but are missing from the architecture tree:
- `pipeline_utils.py` - provides `_dispatch_next()`, `_dispatch_for_status()`, `_log_pipeline()`
- `pipeline_monitor.py` - pipeline health monitoring
- `pipeline_degradation.py` - graceful degradation logic
- `pipeline_failure.py` - failure handling

**Fix**: Add these to the file inventory or remove from tree if intentionally undocumented

### 4. Missing `article_fallback.py` in Architecture Tree
**Severity**: Low (documentation gap)

`services/article_fallback.py` exists but is not listed in the architecture tree.

---

## Layering Violations

### 1. `services/crawling.py` Imports from Adapters (Line 12-13) - DOCUMENTED
**Severity**: Low (known exception)

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.base import RawItem
```

This is a documented exception in `services/AGENTS.override.md`:
> **Exception:** `TYPE_CHECKING` blocks are acceptable for type hints only.

**Impact**: Low - only used for type hints in function signatures, no runtime import occurs.

**Files**: `services/crawling.py:12-13`

---

## Bugs Identified

### 1. RATE LIMITER SLOT LEAK: `provider_id` and `model` Can Be None in Finally Block
**Severity**: High
**File**: `tasks/pipeline.py:422-436`

In `run_stage()` function, `provider_id` and `model` are set to `None` at lines 422-423 before the try block:

```python
model = None
provider_id = None
try:
    result, provider_id, model = _run_stage_core(stage, article_id, work_fn, rc, t0, run_id)
    return result
except SoftTimeLimitExceeded:
    ...
except CircuitOpenError as ce:
    ...
except Exception as e:
    return _handle_stage_exception(e, stage, article_id, run_id, t0, provider_id, model)
finally:
    if limiter is not None:
        limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```

**Problem**: If `_run_stage_core` raises an exception before it returns (e.g., `CircuitOpenError` from `_get_provider_for_stage()` at line 369), `provider_id` and `model` remain `None`. The `finally` block releases with `(None, None, timeout)` which silently fails, causing a slot leak until TTL expires.

Note that `rc.provider` and `rc.model` are set at line 414 BEFORE the try block, but the finally block doesn't use them as fallbacks.

**Affected Code Path**: Any exception in `_run_stage_core` before it successfully returns.

**Fix**: Change line 436 from:
```python
limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```
To:
```python
limiter.release(provider_id or rc.provider, model or rc.model, rc.timeout_seconds)
```

### 2. `trend_memory.py` Missing `json` Import (Line 240)
**Severity**: Medium
**File**: `services/trend_memory.py:240`

```python
except (ImportError, json.JSONDecodeError, ValidationError,
        SQLAlchemyError, ValueError, AttributeError) as e:
```

The `json` module is used at line 240 for `json.JSONDecodeError` but is never imported. This would cause a `NameError` at runtime if a JSON decode error occurs.

**Fix**: Add `import json` at the top of the file.

---

## Questions for Architecture

### 1. `hybrid.py` Search Provider Status
Should `services/search/hybrid.py` (`HybridSearchProvider`) be added to the architecture document as a 5th search provider? It provides FTS5 + vector similarity hybrid search.

### 2. Missing Services in Architecture Tree
Several services exist but are missing from the tree:
- `content_extractor.py`
- `article_fallback.py`
- `pipeline_utils.py`
- `pipeline_monitor.py`
- `pipeline_degradation.py`
- `pipeline_failure.py`
- `context_service.py`
- `cache.py`
- `cost_tracker.py`
- `email.py`
- `webhooks.py`

Should these be added to the architecture document, or is there a reason they're undocumented?

### 3. `limiter.py` Return Value Inconsistency
The Rate Limiter documentation says `acquire()` returns `True` if slot acquired, `False` on timeout. However, the actual implementation at line 62 returns `True` when `result` is truthy. The Lua script returns the incremented count (1, 2, 3...) or 0 on failure. This is correct behavior - just needs clarification in docs.

---

## Improvement Recommendations

### 1. Add `hybrid` to Search Provider Documentation
Add `services/search/hybrid.py` to the search provider table in `architecture/services.md`:

| Provider | File | Status |
|----------|------|--------|
| DuckDuckGo | `duckduckgo.py` | Default, enabled |
| Google | `google.py` | Disabled (requires API key) |
| SearxNG | `searxng.py` | Disabled (self-hosted) |
| Hybrid | `hybrid.py` | Enabled (FTS5 + vector) |
| SQLite FTS | `sqlite_fts.py` | Internal article search |

### 2. Fix Rate Limiter Slot Leak Bug in `tasks/pipeline.py`
**HIGH PRIORITY** - This causes resource leaks in production.

Change `tasks/pipeline.py:436` from:
```python
limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```
To:
```python
limiter.release(provider_id or rc.provider, model or rc.model, rc.timeout_seconds)
```

### 3. Add Missing `json` Import to `services/trend_memory.py`
Add `import json` after existing imports (around line 11).

### 4. Document `content_extractor.py` in Architecture Tree
Add `content_extractor.py` to the file inventory at line 23 (between `crawling.py` and `trend_detector.py`).

### 5. Add Missing Services to Architecture Tree or Document Why They're Undocumented
Services missing from architecture tree that exist in `services/`:
- `article_fallback.py`
- `pipeline_utils.py`
- `pipeline_monitor.py`
- `pipeline_degradation.py`
- `pipeline_failure.py`
- `context_service.py`
- `cache.py`
- `cost_tracker.py`
- `email.py`
- `webhooks.py`

Either add them to the architecture document or create a section explaining which services are internal/implementation details.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct | 10 |
| Discrepancies (Documentation) | 4 |
| Layering Violations (Documented) | 1 |
| Bugs Identified | 2 |
| Questions for Architecture | 3 |
| Improvement Recommendations | 5 |

**Overall Assessment**: The architecture document is mostly accurate. The main concerns are:

1. **[HIGH]** Rate limiter slot leak bug in `tasks/pipeline.py:436` - `provider_id` and `model` can be `None` in finally block
2. **[MED]** Missing `json` import in `services/trend_memory.py:240`
3. **[LOW]** Missing `hybrid.py` search provider in architecture document
4. **[LOW]** Multiple services missing from architecture tree
5. **[LOW]** Layering violation in `services/crawling.py` (but documented as acceptable exception)
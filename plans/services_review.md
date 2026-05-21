# Services Module Architecture Review

Review of `architecture/services.md` against actual implementation in `services/` directory.

---

## Verified Correct

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

### 7. Rate Limiter Pattern
- `services/limiter.py` implements `ModelLimiter` class with `acquire()` and `release()` methods
- `newsletter_pipeline.py` `_run_pipeline_stage()` (lines 108-135) uses `try`/`finally` pattern correctly for slot release
- **NOTE**: `limiter.acquire()` returns boolean, not the slot key - slots released via `limiter.release(provider_id, model, timeout)`

---

## Discrepancies Found

### 1. Missing `hybrid.py` Search Provider in Documentation
The architecture document lists 4 search providers (DuckDuckGo, Google, SearxNG, SQLite FTS), but `services/search/hybrid.py` implements `HybridSearchProvider` combining FTS5 + vector similarity. This is a documented provider but missing from the architecture document.

### 2. Missing `content_extractor.py` in Architecture Tree
The architecture tree doesn't list `content_extractor.py` even though it exists at `services/content_extractor.py`.

### 3. Missing `pipeline_utils.py` and `pipeline_monitor.py` Descriptions
`pipeline_utils.py` exists and provides `_dispatch_next()`, `_dispatch_for_status()`, and `_log_pipeline()` functions. `pipeline_monitor.py` exists for health monitoring. Both are listed in the architecture tree but not described.

### 4. `services/article_parser.py` vs `article_validation.py`
Both exist in `services/` but the architecture document only shows `article_parser.py` in the tree. `article_validation.py` is mentioned in the architecture doc but not shown in the tree.

---

## Bugs Identified

### 1. LAYER VIOLATION: `services/crawling.py` Imports from Adapters (Line 13)
```python
if TYPE_CHECKING:
    from adapters.base import RawItem
```
While wrapped in `TYPE_CHECKING`, this is still an import from `adapters.base` in the services layer. Per AGENTS.md, "Services should NOT import from adapters" (clean layering). However, AGENTS.md also documents this as intentional for type hints.

**Impact**: Low - only used for type hints in function signatures, no runtime import.

### 2. RATE LIMITER SLOT LEAK RISK: `provider_id` Can Be None in Finally Block (`tasks/pipeline.py`)

In `run_stage()` function (lines 389-442):

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

**Problem**: If `_run_stage_core` raises an exception before line 369 (`provider, model, max_tokens, provider_id = _get_provider_for_stage(stage)`) completes successfully, `provider_id` and `model` remain `None`. The `finally` block would call:
```python
limiter.release(None, None, rc.timeout_seconds)
```

**Impact**: This would fail silently (as seen in `limiter.py` lines 101-130), causing slot leak until TTL expires.

**Affected Code Path**: When `_get_provider_for_stage()` raises `CircuitOpenError` before provider is assigned, or any exception in `_run_stage_core` before line 369.

**Fix Needed**: Use `rc.provider` and `rc.model` as fallback when `provider_id`/`model` are `None`, OR set `provider_id` and `model` from `rc` before the try block.

---

## Questions for Architecture

### 1. Layering Exception for Type Hints
`services/crawling.py` uses `TYPE_CHECKING` block to import `RawItem` from `adapters.base`. Is this intentional exception documented anywhere? The AGENTS.md mentions "Documented - MED-8" but doesn't explain the pattern.

### 2. `hybrid.py` Search Provider Status
Should `services/search/hybrid.py` (`HybridSearchProvider`) be added to the architecture document as a 5th search provider? It provides FTS5 + vector similarity hybrid search.

### 3. Missing Services in Architecture Tree
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

Should these be added, or is there a reason they're undocumented?

---

## Improvement Suggestions

### 1. Add `hybrid` to Search Provider Documentation
Add `Hybrid` (hybrid.py) to the search provider table in `architecture/services.md`:

| Provider | File | Status |
|----------|------|--------|
| DuckDuckGo | `duckduckgo.py` | Default, enabled |
| Google | `google.py` | Disabled (requires API key) |
| SearxNG | `searxng.py` | Disabled (self-hosted) |
| Hybrid | `hybrid.py` | Enabled (FTS5 + vector) |
| SQLite FTS | `sqlite_fts.py` | Internal article search |

### 2. Fix Rate Limiter Slot Leak in `tasks/pipeline.py`
Change line 436 from:
```python
limiter.release(provider_id, model if model is not None else None, rc.timeout_seconds)
```
To:
```python
limiter.release(provider_id or rc.provider, model or rc.model, rc.timeout_seconds)
```

Or set `provider_id` and `model` from `rc` before the try block as a fallback.

### 3. Document `content_extractor.py` Approach
The architecture document mentions "Primary: trafilatura, Fallback: readability, Final fallback: Raw HTML" but doesn't describe how `content_extractor.py` handles this cascading.

### 4. Add `pipeline_utils.py` Description
This module provides critical pipeline utilities (`_dispatch_next`, `_log_pipeline`) that should be documented.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Correct | 7 |
| Discrepancies Found | 4 |
| Bugs Identified | 2 |
| Questions for Architecture | 4 |
| Improvement Suggestions | 4 |

**Overall Assessment**: The architecture document is mostly accurate. The main concerns are:
1. Missing `hybrid.py` search provider
2. Potential slot leak in `tasks/pipeline.py` when `provider_id` is `None`
3. Layering exception for TYPE_CHECKING imports from adapters

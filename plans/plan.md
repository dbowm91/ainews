# AINews Consolidated Implementation Plan

**Status:** IN PROGRESS
**Last Updated:** 2026-05-07
**Goal:** Address critical bugs, documentation drift, and remaining architecture issues identified in architecture reviews.

---

## Executive Summary

All waves of the original plan (2026-05-05) have been completed. This document consolidates findings from architecture reviews conducted on 2026-05-07.

**New Waves Overview:**
- **Wave 5: Critical Bug Fixes** (P0 runtime failures) - Immediate priority
- **Wave 6: Layering & Architecture Corrections** (HIGH priority violations)
- **Wave 7: Implementation Gaps** (Missing features)
- **Wave 8: Documentation Alignment** (Schema/model drift)

---

## Wave 5: Critical Bug Fixes (P0 Runtime Failures)

### Task 5.1: Fix P0 Runtime Bugs

#### BUG-5.1.1: Limiter Slot Leak with `model=None` on Early Return

**Location:** `tasks/pipeline.py:414-419`

**Issue:** When stage lock cannot be acquired, the limiter slot is released with `rc.model` which is `None` at that point (before `_run_stage_core` executes). The limiter key is `ainews:llm:{provider}:{model}`, so releasing with `model=None` creates a different key than the actual slot acquired.

**Code at lines 414-419:**
```python
limiter, redis_client, lock_acquired = _acquire_stage_resources(rc, task_self, retry_countdown, retry_max, lock_key, task_id)
if not lock_acquired:
    if limiter is not None:
        limiter.release(rc.provider, rc.model, rc.timeout_seconds)  # BUG: model is None here
    logger.info("TraceID=%s: Stage %s already running for article %s, skipping", trace_id, stage, article_id)
    return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```

**Impact:** Slot leak until TTL expires (default 300 seconds). Could cause artificial rate limiting under high load.

**Fix Options:**
1. Store the acquired model before the lock check and use it for release
2. Restructure early return to happen after model is known
3. Only release the limiter if we have the actual model, otherwise let TTL handle it

**Verification:** Run `test_skips_when_stage_locked` and verify limiter release is called with correct key pattern.

---

#### BUG-5.1.2: `_log_pipeline` Argument Order

**Location:** `tasks/pipeline.py:60-67`

**Status:** VERIFIED FIXED - The code at lines 61, 64, 67 now uses correct argument order:
```python
_log_pipeline(run_id, failed_stage, "info", "degraded_to_research", article_id=article.id)
```

The `_log_pipeline` signature is `_log_pipeline(run_id, stage, level, message, *args, article_id=None)`.

**No action needed for this bug.**

---

## Wave 6: Layering & Architecture Corrections

### Task 6.1: SSRF Layering - VERIFIED CORRECT

**Status:** COMPLETED - No action needed.

Verified that:
- `utils/url.py` contains `validate_url_safe` and `UnsafeURLError`
- All adapters import from `utils/url.py` (NOT `services/url.py`):
  - `adapters/rss.py:12` - `from utils.url import validate_url_safe`
  - `adapters/api.py:11` - `from utils.url import validate_url_safe`
  - `adapters/web.py:15` - `from utils.url import UnsafeURLError, validate_url_safe`
  - `adapters/session.py:8` - `from utils.url import UnsafeURLError, validate_url_safe`
- `services/url.py` re-exports from utils for backward compatibility

---

### Task 6.2: Services↔Adapters Layering

**Location:** `services/crawling.py:13`

**Issue:** `from adapters.base import RawItem` inside `TYPE_CHECKING` block.

**Status:** ACCEPTABLE - The `TYPE_CHECKING` block means this is only used for type hints at static analysis, not at runtime. This is the correct pattern for services to use adapter types without creating runtime imports.

**No action needed.**

---

### Task 6.3: `review` Stage in `_STAGE_TASKS`

**Location:** `services/pipeline_utils.py:18`

**Status:** VERIFIED PRESENT - Already fixed:
```python
_STAGE_TASKS = {
    ...
    "review": ("tasks.edit", "edit_article"),
}
```

**No action needed.**

---

## Wave 7: Implementation Gaps

### Task 7.1: `StageConfig` is Empty Stub

**Location:** `schemas/pipeline.py:140-141`

**Issue:** `StageConfig` only has `tools: list[str]` but documentation claims 7 fields (`enabled`, `model`, `prompt_variant`, `temperature`, `max_tokens`, `timeout`).

**Current code:**
```python
class StageConfig(BaseModel):
    tools: list[str] = Field(default_factory=list)
```

**Analysis:** The `StageConfig` in the schema is different from `SubagentStageConfig` which handles actual stage configuration. The schema `StageConfig` appears to be a placeholder or used differently than documented.

**Action Required:** Either:
- (A) Implement missing fields if StageConfig is actually used
- (B) Document that `SubagentStageConfig` is the actual used class for stage configuration

---

### Task 7.2: Missing Utils Implementations

**Status:** CONFIRMED - Implementation gaps exist.

| File | Current State | Documented Functions | Action |
|------|---------------|----------------------|--------|
| `utils/text.py` | XML escaping (`esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`) | `truncate()`, `sanitize_html()`, `extract_hashtags()` | Add missing functions |
| `utils/datetime.py` | MISSING | `parse_date()`, `format_date()`, `time_ago()` | Create module, move from `services/date_utils.py` |
| `utils/hash.py` | MISSING | `generate_hash()`, `verify_hash()` | Create module |
| `utils/html.py` | MISSING | `strip_tags()`, `linkify()`, `extract_text()` | Create module |
| `utils/security.py` | MISSING | `generate_token()`, `constant_time_compare()`, `hash_password()`, `verify_password()` | Create module |

**Implementation Order (can parallelize):**
1. Create `utils/datetime.py` - move from `services/date_utils.py`
2. Add missing functions to `utils/text.py` (truncate, sanitize_html, extract_hashtags)
3. Create `utils/security.py`
4. Create `utils/hash.py`
5. Create `utils/html.py`

---

### Task 7.3: DeepSeek Provider Missing

**Location:** `services/llm/` - no `deepseek.py`

**Issue:** `architecture/services.md` references `services/llm/deepseek.py` but file doesn't exist. Also `cost_tracker.py` references `deepseek/deepseek-chat`.

**Current LLM providers:** `openai.py`, `anthropic.py`, `gemini.py`, `ollama.py`, `base.py`

**Action Required:** Either:
- (A) Implement DeepSeek provider following the `BaseLLMProvider` pattern
- (B) Remove references from `cost_tracker.py` and documentation

---

### Task 7.4: RSS Adapter Gaps

**Missing implementations in `adapters/rss.py`:**
- Malformed feed fallback (BeautifulSoup) - document claims it exists but doesn't
- Feed validation - document claims it exists but doesn't
- Auth header injection - document claims Bearer/API key but not implemented in `adapters/api.py`

**Action Required:**
1. Implement `_scrape_feed()` fallback method for malformed feeds OR update documentation
2. Add feed validation OR update documentation
3. Add auth header support to APIAdapter OR update documentation

---

## Wave 8: Documentation Alignment

### Task 8.1: Pipeline Documentation Drift

| Document Says | Actual | Action |
|----------------|--------|--------|
| `metadata` (PipelineLog) | `meta` | Update `architecture/pipeline.md` |
| Circuit breaker: 5 failures/1min, half-open 30s | 5 failures/2min, half-open 60s | Update doc or code |
| `backfill_embeddings`: Weekly | Daily at 2 AM | Update doc |
| Write stage `max_tokens`: 1500 | 4096 | Update doc |

---

### Task 8.2: Subagent Documentation Drift

| Document Says | Actual | Action |
|----------------|--------|--------|
| `run_subagent(task, context, tools, model)` | `run_subagent(task_type, stage, prompt_data, response_model, article_id)` | Update doc |
| Tool classes with `execute()` | Module-level functions | Update doc |
| Async middleware `on_request/on_response` | Sync `wrap()` pattern | Update doc |
| Return `SubagentResult` | Return `SubagentResponse` | Update doc |

---

### Task 8.3: Schemas Documentation Drift

| Document Says | Actual | Action |
|----------------|--------|--------|
| `StageConfig` with 7 fields | Only `tools` field | Update doc or implement |
| `ResearchBrief.key_findings` | `key_claims` | Update doc |
| `CondensedArticle.title/summary/word_count` | `headline/tldr/body` | Update doc |
| `NewsletterBrief.newsletter_id, subject` | `themes, highlights, connections` | Update doc |

---

### Task 8.4: Models Documentation Drift

| Document Says | Actual | Action |
|----------------|--------|--------|
| `embedding = Column(Vector(1536))` | `embedding = db.Text` | Update doc |
| `ip_binding`, `user_agent_hash` on AdminUser | NOT IMPLEMENTED | Update doc |
| `TrendMemory.observation` | `signal` | Update doc |
| `Source.type` | `source_type` | Update doc |
| `Source.last_fetch_at` | `last_crawled` | Update doc |
| Article `finalized_at` | `published_at` | Update doc |

---

### Task 8.5: Routes Documentation Drift

| Document Says | Actual | Action |
|----------------|--------|--------|
| `/api/articles` | `/api/v1/articles` | Update doc |
| `/share/<platform>/<article_id>` | NOT FOUND | Implement or remove from doc |
| `/click/<tracking_id>` | `/track/newsletter-click/<int:article_id>` | Update doc |
| Nested template dirs | Flat structure | Update doc |

---

### Task 8.6: Utils Documentation (P0)

**Issue:** `architecture/utils.md` is ~70% inaccurate - describes modules that don't exist.

**Action:** Update to reflect actual state:
1. Document actual `utils/url.py` (SSRF protection, URL normalization)
2. Document actual `utils/text.py` (XML escaping for LLM prompts)
3. Mark missing modules as "not implemented" or implement them

---

## Wave Parallelization Guide

### Can Run in Parallel (Subagents)

**Wave 6 (Layering) - COMPLETED:**
- Task 6.1 (SSRF verification) - DONE
- Task 6.2 (services↔adapters) - DONE
- Task 6.3 (review stage) - DONE

**Wave 7 Tasks (Implementation Gaps) - Can parallelize:**
- Task 7.1 (StageConfig) - Quick analysis, can run with others
- Task 7.2 (Utils) - Can split by file: Agent A for datetime, Agent B for text/hash/security/html
- Task 7.3 (DeepSeek) - Independent, single provider
- Task 7.4 (RSS) - Independent, single adapter

**Wave 8 Tasks (Documentation) - Can parallelize by module:**
- Task 8.1 (Pipeline docs) - Agent for pipeline.md
- Task 8.2 (Subagent docs) - Agent for subagent.md
- Task 8.3 (Schemas docs) - Agent for schemas.md
- Task 8.4 (Models docs) - Agent for models.md
- Task 8.5 (Routes docs) - Agent for routes.md
- Task 8.6 (Utils docs) - Agent for utils.md

### Sequential Dependencies

- Wave 5 must complete before Wave 6 (Wave 5 bugs are blocking) - **DONE**
- Wave 6 is complete
- Wave 8 can run concurrently with Wave 7 after bugs fixed

---

## Suggested Agent Assignments

**Agent A (HIGH PRIORITY):** Wave 5 - Fix limiter slot leak bug in `tasks/pipeline.py`

**Agent B (HIGH PRIORITY):** Wave 7.2 Utils - Implement missing utils modules (can split):
- Agent B1: `utils/datetime.py` (move from services)
- Agent B2: `utils/text.py` additions (truncate, sanitize_html, extract_hashtags)
- Agent B3: `utils/security.py`, `utils/hash.py`, `utils/html.py`

**Agent C (MEDIUM):** Wave 7.3 DeepSeek - Either implement provider or remove references

**Agent D (MEDIUM):** Wave 7.4 RSS - Implement malformed feed fallback, feed validation, auth headers

**Agent E (LOW):** Wave 7.1 StageConfig - Analyze and document actual usage

**Agent F (DOCUMENTATION):** Wave 8 - Can run multiple documentation agents in parallel by module

---

## Status Tracking

| Task | Status | Notes |
|------|--------|-------|
| 5.1.1 Limiter slot leak | PENDING | Bug confirmed at pipeline.py:417 |
| 5.1.2 _log_pipeline args | COMPLETED | Already fixed in code |
| 6.1 SSRF layering | COMPLETED | Adapters correctly import from utils.url |
| 6.2 Services↔adapters | COMPLETED | TYPE_CHECKING import is acceptable |
| 6.3 review stage | COMPLETED | Already present in pipeline_utils.py |
| 7.1 StageConfig | PENDING | Empty stub confirmed |
| 7.2 Utils gaps | PENDING | 5 files missing or wrong |
| 7.3 DeepSeek | PENDING | Missing provider |
| 7.4 RSS gaps | PENDING | Missing fallback/validation/auth |
| 8.1-8.6 Docs | PENDING | Multiple drift issues |

---

## Known Verification Results (2026-05-07)

### Items FIXED:
- `adapters/web.py:2` - `import random` PRESENT
- `services/pipeline_utils.py:18` - `"review": ("tasks.edit", "edit_article")` PRESENT
- `adapters/web.py:15` - imports from `utils.url`, not `services.url`
- `tasks/newsletter.py:429` - `idempotency_key` defined locally
- `_log_pipeline` argument order - FIXED (correct order now used)

### Items PENDING (Need Fixing):
- `tasks/pipeline.py:417` - early return releases with `rc.model` which is `None`
- `schemas/pipeline.py:140-141` - `StageConfig` empty stub
- `utils/text.py` - wrong contents (XML escaping, not text utilities)
- `utils/datetime.py` - missing
- `utils/hash.py` - missing
- `utils/html.py` - missing
- `utils/security.py` - missing
- `services/llm/deepseek.py` - missing

---

## Implementation Detail: Limiter Slot Leak Fix

### Understanding the Bug

The limiter uses Redis keys in format: `ainews:llm:{provider_id}:{model}`

When `limiter.acquire()` is called, it increments a counter for the specific provider+model combination.

When `limiter.release()` is called, it decrements the same key.

**The Bug:** At line 417, early return releases with:
- `provider`: `rc.provider` (configured primary provider, e.g., "ollama-local")
- `model`: `rc.model` (which is `None` at this point - before `_run_stage_core` runs)

The actual acquired key was something like `ainews:llm:ollama-local:qwen3:8b`, but release uses `ainews:llm:ollama-local:None`.

The Redis Lua script for release operates on the wrong key, so the actual slot is never released.

### Fix Approach

Option A - Store model before lock check:
```python
def run_stage(...):
    limiter, redis_client, lock_acquired = _acquire_stage_resources(...)
    acquired_model = rc.model  # Store model that was actually used
    if not lock_acquired:
        if limiter is not None:
            limiter.release(rc.provider, acquired_model, rc.timeout_seconds)
        return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```

But `rc.model` is still None at this point. The model comes from `_get_provider_for_stage` which is called inside `_run_stage_core`.

Option B - Restructure to ensure model is known before early return:
```python
# Move provider/model resolution before lock acquisition
rc.provider, rc.model = _get_provider_for_stage(stage)
limiter, redis_client, lock_acquired = _acquire_stage_resources(...)
```

Option C - Accept TTL-based cleanup:
The slot will expire via TTL (300s default). Add monitoring for slot leaks instead of fixing the race condition.

**Recommended:** Option B - restructure to resolve provider/model before acquiring resources, allowing correct release on early return.

---

## Implementation Detail: Utils Modules

### utils/datetime.py (Create from services/date_utils.py)

Move the following from `services/date_utils.py`:
- `parse_date(date_str: str) -> datetime | None`
- `format_date(dt: datetime, format: str = "%Y-%m-%d") -> str`
- `time_ago(dt: datetime) -> str`

These are pure functions with no external dependencies.

### utils/text.py (Add to existing)

Add alongside existing XML escaping functions:
```python
def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on word boundaries."""
    
def sanitize_html(html: str) -> str:
    """Remove dangerous HTML tags and attributes."""
    
def extract_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text."""
```

### utils/security.py (Create new)

```python
import secrets
import hmac

def generate_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_urlsafe(length)

def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison (timing attack prevention)."""
    return hmac.compare_digest(a, b)
```

### utils/hash.py (Create new)

```python
import hashlib

def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash of data."""
    
def verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool:
    """Verify hash matches data."""
```

### utils/html.py (Create new)

```python
import re

def strip_tags(html: str) -> str:
    """Remove all HTML tags."""
    
def linkify(text: str) -> str:
    """Convert URLs to clickable links."""
    
def extract_text(html: str) -> str:
    """Extract readable text from HTML."""
```

---

## Implementation Detail: DeepSeek Provider

### Option A: Implement DeepSeek Provider

Follow pattern from existing providers (`services/llm/ollama.py`):

```python
# services/llm/deepseek.py
class DeepSeekProvider(BaseLLMProvider):
    provider_name = "deepseek"
    
    def __init__(self, config: dict):
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.deepseek.com")
        # ...
    
    def chat(self, messages: list[dict], model: str, **kwargs) -> LLMResponse:
        # Implement chat completion
```

Update `services/llm/__init__.py` to register the provider.

### Option B: Remove References

1. Remove `deepseek` from `cost_tracker.py` cost rates
2. Update `architecture/services.md` to remove deepseek from provider list

**Recommendation:** Option B unless DeepSeek is actively needed.

---

*End of file*
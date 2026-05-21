# Services Module Architecture Review

**Review Date:** 2026-05-21
**Module:** services
**Document:** `architecture/services.md`

## Summary

The `architecture/services.md` document provides a good high-level overview of the services module but contains several discrepancies, missing items, and a few bugs. Most architectural patterns are correctly documented, but implementation details diverge in notable ways.

---

## Verified Claims

### ✅ File Inventory
Most files listed in the architecture diagram exist and are accurate:

| File | Status | Notes |
|------|--------|-------|
| `services/llm/provider_base.py` | ✅ Exists | Named `services/provider_base.py` (different path) |
| `services/subagent/runner.py` | ✅ Exists | Contains `run_subagent` and `run_subagent_with_tools` |
| `services/search/*.py` | ✅ All exist | duckduckgo, google, searxng, hybrid, sqlite_fts |
| `services/newsletter_pipeline.py` | ✅ Exists | Implements 3-stage pipeline |
| `services/content_extractor.py` | ✅ Exists | trafilatura + readability + raw fallback |
| `services/trend_memory.py` | ✅ Exists | Module-level functions (class not implemented) |
| `services/related.py` | ✅ Exists | `find_related_articles()` function |
| `services/webhooks.py` | ✅ Exists | HMAC-SHA256, encryption, retry logic |
| `services/limiter.py` | ✅ Exists | Redis-based concurrency limiter |
| `services/circuit_breaker.py` | ✅ Exists | CLOSED→OPEN→HALF_OPEN pattern |
| `services/email.py` | ✅ Exists | Module-level functions, not class-based |

### ✅ Layering Rule
The document correctly states: "Services should NOT import from adapters." Verification:
- Only `services/crawling.py:13` has `from adapters.base import RawItem` under `TYPE_CHECKING` block
- This is a type-hint only import (runtime-only) - technically compliant but still creates coupling

### ✅ Circuit Breaker Pattern
State diagram correctly shows Closed→Open→HalfOpen→Closed transitions. `circuit_breaker.py` implements this correctly with both in-memory and Redis-backed variants.

### ✅ Rate Limiter Pattern
`limiter.py` correctly implements acquire/release with pub/sub notification and Lua scripts for atomicity.

### ✅ Webhook Security Features
All documented features verified:
- HMAC-SHA256 signatures with timestamp replay protection (`services/webhooks.py:101-122`)
- Fernet encryption for secrets at rest (`services/webhooks.py:69-98`)
- Exponential backoff retry (`services/webhooks.py:155-189`)
- WebhookEvent model tracking

### ✅ Content Extraction
Primary: trafilatura, Fallback: readability, Final: raw HTML with boilerplate removal - correctly implemented in `services/content_extractor.py`.

### ✅ Search Providers
All 5 providers exist with correct status: DuckDuckGo (enabled), Google (disabled), SearxNG (disabled), Hybrid (enabled), SQLite FTS (internal).

---

## Discrepancies and Issues

### 1. CRIT: `BaseLLMProvider` Interface Mismatch

**Location:** `services/llm/base.py`

The documented interface shows `chat_with_tools` as a concrete method, but the actual signature in the doc differs from implementation:

**Doc says (lines 91-101):**
```python
def chat_with_tools(
    self,
    messages: list[dict[str, str]],
    tools: list[ToolDefinition],
    tool_choice: Optional[str],
    model: Optional[str],
    system: Optional[str],
    temperature: float,
    max_tokens: int,
    max_iterations: int = 5,
) -> ToolCallingResponse: ...
```

**Actual (line 450-565):** Same signature, but method is NOT abstract - it's fully implemented in base class. The abstract methods are `_call_api_with_tools`, `_extract_text_and_tool_calls`, and `_format_tool_result`.

**Missing from doc:**
- `chat_structured_batch()` (line 313-387) - batch processing method
- `default_model` class attribute
- `RETRY_BASE_DELAY`, `RETRY_MAX_DELAY`, `RETRY_MAX_ATTEMPTS` class attributes
- `_retry_with_backoff()` method
- `_record_success()` and `_record_failure()` methods

### 2. HIGH: `TrendMemoryService` Class Not Implemented

**Location:** `services/trend_memory.py`

**Doc says (lines 228-237):**
```python
class TrendMemoryService:
    def propose(self, article: Article) -> list[TrendMemory]:
    def consolidate(self, timeframe_days: int = 7):
    def search(self, query: str, limit: int = 5) -> list[TrendMemory]:
```

**Actual:** No `TrendMemoryService` class exists. Instead, module-level functions are used:
- `propose_trend_memory(article, engagement_data)` - not `propose()`
- `consolidate_topic(topic)` / `consolidate_all_topics()` - not `consolidate(timeframe_days)`
- `semantic_search_trends(query, limit)` - not `search()`

### 3. MED: `RateLimiter` Class Not Used

**Doc says (lines 186-195):**
```python
class RateLimiter:
    def acquire(self, slots: int = 1, timeout: float = 30) -> bool:
    def release(self, slots: int = 1) -> None:
    def is_available(self, slots: int = 1) -> bool:
```

**Actual:** The class is named `ModelLimiter` in `services/limiter.py:32`. The `is_available` method doesn't exist - the closest is `get_active()` at line 132.

### 4. MED: Email Service Uses Functions, Not Class

**Doc says (lines 204-210):**
```python
class EmailService:
    def send_newsletter(self, newsletter: Newsletter, subscribers: list[Subscriber]):
    def send_verification(self, subscriber: Subscriber, token: str):
```

**Actual:** `services/email.py` uses module-level functions:
- `send_newsletter_email()` (not `send_newsletter`)
- `send_verification_email()` (not `send_verification`)
- `send_welcome_email()` - not documented

### 5. MED: Newsletter Pipeline Has Disabled Stage Handling

**Doc says (lines 159-165):**
```
reader (extracts key points) → writer (generates summary) → editor (polishes)
```

**Actual:** The pipeline at `services/newsletter_pipeline.py:239-245` has explicit handling when writer is disabled, returning early with `fallback_stages: ["writer_disabled"]`. Similar for editor (lines 286-300).

### 6. MED: Subagent Functions Documentation Gap

**Issue:** The document mentions the subagent system but doesn't describe the actual function signatures:
- `run_subagent()` at `services/subagent/runner.py:38`
- `run_subagent_with_tools()` at `services/subagent/runner.py:338`
- `_finalize_subagent_result()` at `services/subagent/runner.py:277` (internal function)

### 7. LOW: `Article.finalized_at` Referenced But Doesn't Exist

**Issue:** The model field naming section in AGENTS.md mentions `Article.finalized_at` doesn't exist - use `published_at` instead. The document doesn't reference this, but the architecture shouldn't imply a field that doesn't exist.

---

## Bugs in Implementation

### BUG-1: Duplicate `_finalize_subagent_result` Logic

**Location:** `services/subagent/runner.py`

Both `run_subagent()` (line 38) and `run_subagent_with_tools()` (line 338) implement similar finalization logic inline (lines 227-274 and 505-508 respectively) rather than calling the shared `_finalize_subagent_result()` function (line 277).

`run_subagent_with_tools()` at line 505 does call `_finalize_subagent_result()`, but `run_subagent()` does not - it duplicates the logic inline.

**Impact:** Code duplication, maintenance burden, potential for inconsistency.

**Fix:** Have `run_subagent()` also call `_finalize_subagent_result()`.

### BUG-2: `_get_provider_chain()` Creates New Iterator Each Call

**Location:** `services/llm/__init__.py:57-97`

```python
def get_provider_chain(role: str):
    """Generator yielding (provider, model, max_tokens, provider_id) tuples."""
    # ... creates new generator every call
```

**Impact:** On every LLM call, this iterates through enabled providers and filters by circuit state. While not incorrect, this could be optimized with caching.

**Not critical:** The circuit breaker state is dynamic (can change), so caching would need to be short-lived.

---

## Layering Violations

### LV-1: `services/crawling.py` Imports From Adapters

**Location:** `services/crawling.py:12-13`
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.base import RawItem
```

**Assessment:** This is a `TYPE_CHECKING` block, so the import doesn't happen at runtime. However, it still creates a conceptual coupling - services should depend on schemas/models, not adapters.

**Per AGENTS.md:** "Services should NOT import from adapters." While `TYPE_CHECKING` is a common pattern to avoid circular imports, it violates the clean layering principle.

**Recommendation:** Use a protocol/class definition in `schemas/` instead of importing from `adapters/`.

---

## Missing Items (In Code But Not Documented)

1. **`services/article_validation.py`** - exists but not in doc
2. **`services/article_fallback.py`** - exists but not in doc
3. **`services/article_parser.py`** - mentioned in doc, exists
4. **`services/trend_detector.py`** - exists with `classify()` and `compute_velocity()` functions, not documented
5. **`services/pipeline_monitor.py`** - exists, not documented in services.md (mentioned in AGENTS.md)
6. **`services/pipeline_degradation.py`** - exists, not documented
7. **`services/context_service.py`** - exists with `get_topic_note()`, not documented
8. **`services/embeddings.py`** - mentioned in doc (Trend Memory section), exists but implementation details not documented

---

## Security Assessment

### ✅ No Issues Found
- URL validation properly uses SSRF protection
- Webhook secrets are encrypted with Fernet
- HMAC-SHA256 with timestamp replay protection
- No hardcoded credentials
- No SQL injection vulnerabilities (uses SQLAlchemy ORM)
- Input sanitization in `sanitize_final_article()` using bleach

---

## Performance Concerns

### PC-1: `_get_provider_chain()` Iterates Every Call

**Location:** `services/llm/__init__.py:57-97`

The function iterates through all enabled providers on every LLM call to check circuit breaker state. While necessary for fail-over, this could be optimized by caching provider chain order.

**Severity:** LOW - only happens on circuit failures (rare)

### PC-2: Trend Memory `semantic_search_trends()` Loads All Memories

**Location:** `services/trend_memory.py:414-430`

```python
_SEMANTIC_SEARCH_LIMIT = 500
# ...
memories = db.session.execute(
    select(TrendMemory)
    # ... loads up to 500 memories into memory
).scalars().all()
```

Then computes cosine similarity in Python for all 500. This could be slow with large trend memory tables.

**Severity:** MED - 500 is a reasonable limit but the similarity computation is in-memory

---

## Recommendations

### CRIT-1: Document `BaseLLMProvider` Interface Accurately

**Priority:** CRIT
**Files:** `architecture/services.md`

Update the `BaseLLMProvider` interface to reflect actual implementation:
- Add `chat_structured_batch()` method
- Add `_retry_with_backoff()`, `_record_success()`, `_record_failure()`
- Document that `chat_with_tools` is concrete, not abstract
- Add class attributes: `default_model`, `RETRY_BASE_DELAY`, `RETRY_MAX_DELAY`, `RETRY_MAX_ATTEMPTS`

### CRIT-2: Fix Duplicate Finalization Logic

**Priority:** CRIT
**Files:** `services/subagent/runner.py:227-274`

Have `run_subagent()` call `_finalize_subagent_result()` instead of duplicating the logic inline.

### HIGH-1: Document `TrendMemoryService` Actual Implementation

**Priority:** HIGH
**Files:** `architecture/services.md`, `services/trend_memory.py`

Either:
- (A) Update doc to show actual function-based API, OR
- (B) Refactor `trend_memory.py` to use a class

Recommendation: Option A (document current state) is simpler.

### HIGH-2: Update `RateLimiter` Documentation

**Priority:** HIGH
**Files:** `architecture/services.md`

- Class is actually `ModelLimiter`
- `is_available` is actually `get_active`
- Add documentation about pub/sub notification mechanism

### HIGH-3: Document Email Service Functions

**Priority:** HIGH
**Files:** `architecture/services.md`

- Document actual function names: `send_newsletter_email`, `send_verification_email`, `send_welcome_email`
- Note that module-level functions are used instead of class

### MED-1: Add Missing Services to Architecture

**Priority:** MED
**Files:** `architecture/services.md`

Add these to the file inventory:
- `article_validation.py` - Article quality validation
- `article_fallback.py` - Fallback content extraction
- `trend_detector.py` - Trend detection logic
- `pipeline_monitor.py` - Pipeline health monitoring
- `pipeline_degradation.py` - Graceful degradation logic
- `context_service.py` - Context management

### MED-2: Add Subagent Function Signatures

**Priority:** MED
**Files:** `architecture/services.md`

Document:
- `run_subagent(task_type, stage, prompt_data, response_model, article_id)`
- `run_subagent_with_tools(task_type, stage, prompt_data, response_model, tools, article_id)`

### MED-3: Remove `TYPE_CHECKING` Import From Adapters

**Priority:** MED
**Files:** `services/crawling.py:12-13`

Replace `from adapters.base import RawItem` with a protocol definition in `schemas/` to maintain clean layering.

### LOW-1: Optimize Provider Chain Caching

**Priority:** LOW
**Files:** `services/llm/__init__.py:57-97`

Consider adding short-lived cache for provider chain order, invalidated on circuit state changes.

---

## Verification Checklist

| Claim | Status | Notes |
|-------|--------|-------|
| Services should NOT import from adapters | ⚠️ Partial | `crawling.py` uses TYPE_CHECKING import |
| BaseLLMProvider interface | ❌ Mismatch | Missing methods, wrong structure |
| Circuit breaker pattern | ✅ Verified | Correct implementation |
| Rate limiter pattern | ⚠️ Partial | Class named differently, missing method |
| Email service class | ❌ Not implemented | Uses module-level functions |
| Webhook security features | ✅ Verified | All present |
| Trend memory service | ❌ Not implemented | Class doesn't exist |
| Content extraction chain | ✅ Verified | trafilatura → readability → raw |
| Search providers | ✅ Verified | All 5 correct |
| Newsletter pipeline | ✅ Verified | Has disabled stage handling |
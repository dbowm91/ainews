# Services Architecture Review (review_02_services.md)

**Date:** 2026-05-07
**Reviewer:** Architecture Review Agent
**Document:** `architecture/services.md`
**Codebase:** `/home/sugarwookie/projects/ainews/services/`

---

## Executive Summary

The `architecture/services.md` document accurately describes the overall architecture and most service implementations. However, several discrepancies exist between the documented structure and actual implementation, including file naming inconsistencies, missing providers, and API mismatches. This review identifies all discrepancies and provides specific improvement recommendations.

---

## 1. Verification of Major Claims

### 1.1 LLM Provider System

| Documented | Actual | Status |
|------------|--------|--------|
| `llm/provider_base.py` | `llm/base.py` | **DISCREPANCY** - File renamed |
| `llm/anthropic.py` | `llm/anthropic.py` | MATCH |
| `llm/openai.py` | `llm/openai.py` | MATCH |
| `llm/gemini.py` | `llm/gemini.py` | MATCH |
| `llm/ollama.py` | `llm/ollama.py` | MATCH |
| `llm/deepseek.py` | **MISSING** | **BUG** - Provider not implemented |

**Issue 1.1.1: File Naming Inconsistency**
- **Location:** `services/llm/`
- **Problem:** Documentation references `provider_base.py` but actual file is `base.py`
- **Impact:** Developer confusion when navigating code
- **Recommendation:** Update doc to `llm/base.py` OR rename `base.py` to `provider_base.py` for consistency

**Issue 1.1.2: Missing DeepSeek Provider**
- **Location:** Document line 15
- **Problem:** `deepseek.py` is listed in the architecture but doesn't exist
- **Impact:** Documentation is inaccurate; no DeepSeek support implemented
- **Recommendation:** Either implement `services/llm/deepseek.py` following the `BaseLLMProvider` pattern, or remove from documentation

---

### 1.2 Provider Base Interface

**Documented at lines 49-63:**
```python
class BaseLLMProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> LLMResponse: ...

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], **kwargs) -> LLMResponse: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...
```

**Actual at `services/llm/base.py` lines 196-224:**
```python
@abc.abstractmethod
def chat(self, messages: list[dict[str, str]], ...) -> LLMResponse: ...

@abc.abstractmethod
def chat_streaming(self, messages: list[dict[str, str]], ...) -> Iterator[str]: ...
```

**Discrepancies:**
1. `complete()` method documented but not implemented
2. `embed()` method documented but not implemented in base class
3. `chat()` signature differs: documented uses `list[ChatMessage]`, actual uses `list[dict[str, str]]`
4. No `async` methods - all methods are synchronous

**Issue 1.2.1: Base Interface Mismatch**
- **Severity:** Medium
- **Recommendation:** Update documentation to reflect actual interface, OR update code if the documented interface is desired

---

### 1.3 Circuit Breaker Pattern

**Documented at lines 65-75:**
```
Closed (正常) -> Open (熔断) -> Half-Open (半开)
     |              |              |
     └── 失败计数 -> |              |
                      └── 超时后 -> |
                                  └── 成功 -> Closed
```

**Actual at `services/circuit_breaker.py`:** VERIFIED
- Implements `CLOSED -> OPEN -> HALF_OPEN -> CLOSED` pattern correctly
- Uses Redis for distributed state
- Chinese comments in doc match implementation logic

---

### 1.4 Cost Tracking

**Documented at lines 77-84:**
> Tracks tokens used (prompt/completion), cost per model, daily/monthly budgets

**Actual at `services/cost_tracker.py`:** PARTIAL

**Verified:**
- Token tracking per provider/model
- Configurable cost rates
- Blended rate calculation (60% input, 40% output)

**Not Implemented:**
- Daily/monthly budgets (no budget enforcement)
- Budget alerts/thresholds

**Recommendation:** Update documentation to accurately describe current implementation (token counting + cost estimation, no budget enforcement)

---

## 2. Pipeline Services Verification

### 2.1 Newsletter Pipeline

**Documented at lines 87-93:**
```
reader (extracts key points) -> writer (generates summary) -> editor (polishes)
```

**Actual at `services/newsletter_pipeline.py`:** VERIFIED

The `generate_executive_summary()` function (lines 166-301) correctly implements:
1. **Reader stage** (lines 191-212): Builds research brief with `NewsletterBrief` schema
2. **Writer stage** (lines 214-245): Generates summary with `ExecutiveSummary` schema
3. **Editor stage** (lines 247-301): Polishes with fallback handling

**Verified correctly:**
- Stage ordering matches documentation
- Each stage has independent fallback handling
- Metrics tracking for fallback scenarios

---

### 2.2 Article Processing Services

| Documented | Stage | Actual File | Status |
|------------|-------|-------------|--------|
| `researcher.py` | `research_article` | `services/researcher.py` | MATCH |
| `writer.py` | `write_article` | `services/writer.py` | MATCH |
| `editor.py` | `edit_article` | `services/editor.py` | MATCH |

**All three services verified:** Functions build prompts correctly, use experiment variants, and integrate with the pipeline system.

---

## 3. Infrastructure Services Verification

### 3.1 Rate Limiter

**Documented at lines 109-125:**
```python
class RateLimiter:
    def acquire(self, slots: int = 1, timeout: float = 30) -> bool: ...
    def release(self, slots: int = 1) -> None: ...
    def is_available(self, slots: int = 1) -> bool: ...
```

**Actual at `services/limiter.py`:** DIFFERENT API

**Actual class is `ModelLimiter` with:**
```python
def acquire(self, provider_id: str, model: str, max_concurrent: int, timeout: int = 300) -> bool: ...
def release(self, provider_id: str, model: str, timeout: int = 300) -> None: ...
def get_active(self, provider_id: str, model: str) -> int | None: ...
```

**Discrepancies:**
1. Class name differs: `RateLimiter` vs `ModelLimiter`
2. Method signatures differ significantly
3. `is_available()` method not present
4. `cleanup_stale_slots()` and `is_healthy()` bonus methods not documented

**Issue 3.1.1: API Mismatch**
- **Recommendation:** Update documentation to match actual `ModelLimiter` API

---

### 3.2 Email Service

**Documented at lines 127-138:**
```python
class EmailService:
    def send_newsletter(self, newsletter: Newsletter, subscribers: list[Subscriber]): ...
    def send_verification(self, subscriber: Subscriber, token: str): ...
```

**Actual at `services/email.py`:** DIFFERENT API

**Actual implementation uses module-level functions:**
- `send_newsletter_email(email, subject, html_content, unsubscribe_url)`
- `send_verification_email(email, newsletter_type, verification_url, unsubscribe_url, site_name)`
- `send_welcome_email(email, newsletter_type, unsubscribe_url, site_name)`
- `SMTPConnectionPool` class for connection management

**Issue 3.2.1: API Mismatch**
- **Severity:** Low
- **Recommendation:** Update documentation to reflect actual module-level function API

---

### 3.3 Webhooks

**Documented at lines 140-147:**
> - HMAC-SHA256 signatures with timestamp replay protection
> - Encrypted secrets at rest
> - Retry logic with exponential backoff
> - Event tracking via `WebhookEvent` model

**Actual at `services/webhooks.py`:** ALL VERIFIED

| Feature | Verification |
|---------|--------------|
| HMAC-SHA256 signatures | `_sign_payload()` at line 101-122 |
| Timestamp replay protection | `timestamp` included in signature at line 115 |
| Encrypted secrets | `_encrypt_secret()` / `_decrypt_secret()` with Fernet |
| Retry with exponential backoff | `_send_webhook_with_retry()` at line 126-191 |
| Event tracking | `WebhookEvent` model used in `dispatch_webhook()` |

**Issue 3.3.1: None** - Webhook implementation fully matches documentation

---

## 4. Context & Trend Services

### 4.1 Trend Memory

**Documented at lines 151-165:**
```python
class TrendMemoryService:
    def propose(self, article: Article) -> list[TrendMemory]: ...
    def consolidate(self, timeframe_days: int = 7): ...
    def search(self, query: str, limit: int = 5) -> list[TrendMemory]: ...
```

**Actual at `services/trend_memory.py`:** DIFFERENT API

**Actual module-level functions:**
- `propose_trend_memory(article, engagement_data)` - returns `SubagentResponse`
- `consolidate_topic(topic)` / `consolidate_all_topics()` - returns dict
- `semantic_search_trends(query, limit)` - returns list[dict]
- `get_memory_for_topics(topics, min_importance, max_age_days)` - returns list[TrendMemory]

**Issue 4.1.1: No `TrendMemoryService` Class**
- **Problem:** Documentation describes a class that doesn't exist
- **Recommendation:** Update documentation to reflect actual module-level function API

---

### 4.2 Related Articles

**Documented at lines 167-169:**
> Finds related articles by topics and content similarity.

**Actual at `services/related.py`:** VERIFIED

- `find_related_articles(article, limit)` - Returns Article ORM objects
- `find_related_articles_cached(article, limit)` - Cached wrapper
- `find_related_articles_dicts(topics, exclude_id, limit)` - Returns dicts for prompts

**Content similarity** is implemented via keyword extraction and scoring algorithm.

---

## 5. Content Extraction

**Documented at lines 173-177:**
> Primary: trafilatura for main content extraction
> Fallback: readability for article parsing
> Final fallback: Raw HTML with boilerplate removal

**Actual at `services/content_extractor.py`:** VERIFIED

Extraction hierarchy:
1. **trafilatura** (lines 95-104) - Primary extraction with `bare_extraction()`
2. **readability** (lines 106-118) - Second fallback via `Document()` and BeautifulSoup
3. **EMPTY status** returned (line 123) - No raw HTML fallback mentioned

**Issue 5.1: Missing Raw HTML Fallback**
- The third fallback in the documentation ("Raw HTML with boilerplate removal") is NOT implemented
- Code returns `ExtractionStatus.EMPTY` instead of attempting raw HTML extraction
- **Recommendation:** Either implement raw HTML fallback or update documentation

---

## 6. Search Providers

**Documented at lines 179-188:**
| Provider | File | Status |
|----------|------|--------|
| DuckDuckGo | `duckduckgo.py` | Default, enabled |
| Google | `google.py` | Disabled (requires API key) |
| SearxNG | `searxng.py` | Disabled (self-hosted) |
| Hybrid | `sqlite_fts.py` | Internal article search |

**Actual at `services/search/`:** PARTIAL DISCREPANCY

| Provider | File | Verification |
|----------|------|--------------|
| DuckDuckGo | `duckduckgo.py` | Matches |
| Google | `google.py` | Matches |
| SearxNG | `searxng.py` | Matches |
| Hybrid | `hybrid.py` | Not `sqlite_fts.py` |
| Internal | `sqlite_fts.py` | Present but named differently |

**Issue 6.1: Documentation Names Wrong File for Hybrid**
- `hybrid.py` is the actual Hybrid provider
- `sqlite_fts.py` is a separate FTS provider
- Documentation incorrectly associates "Hybrid" with `sqlite_fts.py`

---

## 7. Bugs and Issues

### Bug 7.1: Slot Leak Potential in Rate Limiter (Low Severity)

**Location:** `services/limiter.py` lines 98-130

**Problem:** If `release()` fails twice (lines 98-115), the slot leaks until TTL expires. While there's error handling and metrics recording, there's no retry queue or alert for this scenario.

**Code Reference:**
```python
def release(self, provider_id: str, model: str, timeout: int = 300) -> None:
    ...
    try:
        self._release_script(keys=[key])
        self._redis.publish(channel, "1")
    except redis.exceptions.RedisError as e:
        logger.error(...)  # First failure - logs and retries
        time.sleep(0.1)
        try:
            self._release_script(keys=[key])
            self._redis.publish(channel, "1")
        except redis.exceptions.RedisError:
            logger.error(...)  # Second failure - logs only, slot leaks
```

**Recommendation:** Consider adding an alert/metric for double-failure scenarios.

---

### Bug 7.2: Potential JSON Injection in Editor Prompt

**Location:** `services/editor.py` lines 71-74

```python
parts.append(
    f"    <citation title='{esc_xml_attr(c.get('title', ''))}' "
    f"url='{esc_xml_attr(c.get('url', ''))}' />",
)
```

**Problem:** Uses `esc_xml_attr()` for URL attribute which is good, but `esc_xml_attr()` only escapes XML special characters. A malformed URL could potentially cause issues.

---

## 8. Layering Violations

### Issue 8.1: Services Importing from Adapters

**Location:** `services/llm/__init__.py`

The doc states: "Services should NOT import from adapters"

**Finding:** The LLM services are used by tasks, but the providers themselves are in `services/llm/`. The adapters layer (e.g., `adapters/rss.py`, `adapters/web.py`) does not appear to be imported by services - this appears correct.

**Verification needed:** Complete adapter layer review to confirm no violations.

---

## 9. Improvement Recommendations

### Priority 1 (High Impact)

1. **Update documentation file reference** - Change `llm/provider_base.py` -> `llm/base.py`
2. **Implement or remove DeepSeek** - Either implement `services/llm/deepseek.py` or remove from documentation
3. **Fix Content Extractor doc** - Either add raw HTML fallback or remove it from documentation

### Priority 2 (Medium Impact)

4. **Update Rate Limiter documentation** - Rename to `ModelLimiter` and update method signatures
5. **Update Trend Memory documentation** - Change from class to module-level functions
6. **Update Email documentation** - Change from `EmailService` class to module-level functions
7. **Fix Search Provider table** - Correct "Hybrid" file association (`hybrid.py` not `sqlite_fts.py`)

### Priority 3 (Low Impact)

8. **Document bonus methods** - Add `cleanup_stale_slots()`, `is_healthy()` to Rate Limiter docs
9. **Update BaseLLMProvider interface** - Document actual interface or update code
10. **Add circuit breaker diagram legend** - Chinese characters may confuse international developers

---

## 10. Files Referenced

| File | Lines | Status |
|------|-------|--------|
| `services/llm/base.py` | 1-587 | Has `BaseLLMProvider` |
| `services/llm/__init__.py` | 1-150 | Provider registry |
| `services/llm/anthropic.py` | 1-310 | Anthropic provider |
| `services/llm/openai.py` | 1-323 | OpenAI provider |
| `services/llm/gemini.py` | 1-326 | Gemini provider |
| `services/llm/ollama.py` | 1-291 | Ollama provider |
| `services/newsletter_pipeline.py` | 1-301 | Pipeline implementation |
| `services/researcher.py` | 1-90 | Research prompt builder |
| `services/writer.py` | 1-67 | Writer prompt builder |
| `services/editor.py` | 1-157 | Editor prompt builder |
| `services/limiter.py` | 1-192 | `ModelLimiter` not `RateLimiter` |
| `services/email.py` | 1-379 | Module functions not class |
| `services/webhooks.py` | 1-353 | Fully matches |
| `services/trend_memory.py` | 1-440 | Module functions not class |
| `services/content_extractor.py` | 1-123 | Primary + readability, missing raw HTML |
| `services/related.py` | 1-301 | Verified |
| `services/embeddings.py` | 1-66 | Verified |
| `services/search/duckduckgo.py` | - | Verified |
| `services/search/google.py` | - | Verified |
| `services/search/searxng.py` | - | Verified |
| `services/search/hybrid.py` | - | Not in doc table |
| `services/circuit_breaker.py` | 1-454 | Verified |

---

## Conclusion

The `services/` module is generally well-structured and the documentation is mostly accurate. The main issues are:

1. **File naming discrepancies** (provider_base.py vs base.py, missing deepseek.py)
2. **API mismatches** between documented classes and actual module-level functions
3. **Missing features** (raw HTML fallback in content extraction)

All critical business logic (pipeline, webhooks, circuit breaker) is correctly implemented and matches documentation.

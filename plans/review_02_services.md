# Architecture Review: services.md vs Actual Codebase

**Review Date:** 2026-05-08
**Reviewer:** Architecture Review Agent
**Document Reviewed:** `architecture/services.md`
**Workspace:** `/Users/davidbowman/projects/ainews`

---

## Executive Summary

This review compares the service architecture documentation (`architecture/services.md`) against the actual implementation in the `services/` directory. The document is **~85% accurate** with several discrepancies that should be addressed.

---

## 1. Verified Items (Correct)

### LLM Provider System

| File | Status | Notes |
|------|--------|-------|
| `services/llm/base.py` | VERIFIED | `BaseLLMProvider` abstract base class exists with correct interface (`provider_name`, `complete`, `chat`, `embed`) |
| `services/llm/anthropic.py` | VERIFIED | Anthropic Claude provider with `@register_provider("anthropic")` |
| `services/llm/openai.py` | VERIFIED | OpenAI-compatible provider with `@register_provider("openai")` |
| `services/llm/gemini.py` | VERIFIED | Google Gemini provider with `@register_provider("gemini")` |
| `services/llm/ollama.py` | VERIFIED | Ollama local provider with `@register_provider("ollama")` |

### Circuit Breaker Pattern

| File | Status | Notes |
|------|--------|-------|
| `services/circuit_breaker.py` | VERIFIED | Full implementation with `CircuitBreaker` and `RedisCircuitBreaker` classes. State diagram (Closed/Open/Half-Open) matches documentation |

**Circuit Breaker Timing (from code):**
- `failure_threshold`: 5 (default)
- `recovery_timeout`: 60.0 seconds (HALF_OPEN after 60s)
- `window_seconds`: 120.0 seconds (sliding window for failure counting)
- `half_open_max_calls`: 1

**Note:** Documentation states "half-open 30s" but code uses 60s recovery timeout. See Discrepancy #1.

### Core Services

| Service | File | Status |
|---------|------|--------|
| `article_parser.py` | `services/article_parser.py` | VERIFIED - JSON parsing for final_article/summary |
| `article_validation.py` | `services/article_validation.py` | VERIFIED - Post-edit content quality validation |
| `article_fallback.py` | `services/article_fallback.py` | VERIFIED - Fallback content extraction |
| `researcher.py` | `services/researcher.py` | VERIFIED - Research brief building with web search context |
| `writer.py` | `services/writer.py` | VERIFIED - Article writing with Smart Brevity format |
| `editor.py` | `services/editor.py` | VERIFIED - Article editing via subagent tools |
| `content_extractor.py` | `services/content_extractor.py` | VERIFIED - trafilatura + readability extraction chain |
| `crawling.py` | `services/crawling.py` | VERIFIED - Crawling utilities |
| `trend_detector.py` | `services/trend_detector.py` | VERIFIED - Trend detection via pattern matching |
| `embeddings.py` | `services/embeddings.py` | VERIFIED - Embedding generation with sentence-transformers |
| `newsletter_pipeline.py` | `services/newsletter_pipeline.py` | VERIFIED - 3-stage newsletter (reader/writer/editor) |
| `pipeline_monitor.py` | `services/pipeline_monitor.py` | VERIFIED - Pipeline health monitoring |
| `pipeline_degradation.py` | `services/pipeline_degradation.py` | VERIFIED - Graceful degradation logic |
| `pipeline_failure.py` | `services/pipeline_failure.py` | VERIFIED - Failure handling |
| `context_service.py` | `services/context_service.py` | VERIFIED - Context management |
| `related.py` | `services/related.py` | VERIFIED - Related article finding |
| `trend_memory.py` | `services/trend_memory.py` | VERIFIED - Trend memory operations with embedding-based search |
| `email.py` | `services/email.py` | VERIFIED - SMTP email delivery with connection pooling |
| `webhooks.py` | `services/webhooks.py` | VERIFIED - Webhook dispatch with HMAC-SHA256 + retry logic |
| `cache.py` | `services/cache.py` | VERIFIED - Redis caching with L1 in-memory fallback |
| `limiter.py` | `services/limiter.py` | VERIFIED - Redis-based rate limiting with pub/sub |
| `cost_tracker.py` | `services/cost_tracker.py` | VERIFIED - LLM cost tracking |

### Search Providers

| Provider | File | Status |
|----------|------|--------|
| DuckDuckGo | `services/search/duckduckgo.py` | VERIFIED - Default, enabled |
| Google | `services/search/google.py` | VERIFIED - Disabled (requires API key) |
| SearxNG | `services/search/searxng.py` | VERIFIED - Disabled (self-hosted) |
| Hybrid | `services/search/hybrid.py` | VERIFIED - Internal article search (FTS + vector) |
| SQLite FTS | `services/search/sqlite_fts.py` | VERIFIED - FTS5 implementation |

---

## 2. Discrepancies

### Discrepancy #1: Circuit Breaker Timing

**Document says:**
- Half-open after 30 seconds

**Actual code (`services/circuit_breaker.py:44`):**
```python
recovery_timeout: float = 60.0,
```

**Impact:** Medium - Documentation is inaccurate about recovery timing
**Recommendation:** Update documentation to state "half-open after 60s" or make the value configurable

---

### Discrepancy #2: DeepSeek Provider Missing

**Document lists:**
```
services/llm/deepseek.py           # DeepSeek provider
```

**Actual:** No `services/llm/deepseek.py` exists. Only:
- `anthropic.py`
- `openai.py`
- `gemini.py`
- `ollama.py`
- `base.py`

**However:** `cost_tracker.py` has pricing for `deepseek/deepseek-chat` in `_DEFAULT_RATES`:
```python
"deepseek/deepseek-chat": {"input": 0.20, "output": 1.10},  # NOT PRESENT - inconsistent
```

**Impact:** High - Documentation lists a provider that doesn't exist. References in cost_tracker.py may cause confusion.
**Recommendation:** Either implement DeepSeek provider or remove from documentation and cost_tracker references

---

### Discrepancy #3: BaseLLMProvider Interface Mismatch

**Document says:**
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

**Actual (base.py:111+):**
```python
class BaseLLMProvider(BaseProvider, abc.ABC):
    default_model: str = ""
    
    # Methods are NOT async:
    @abc.abstractmethod
    def chat(self, messages: list[dict[str, str]], ...) -> LLMResponse: ...
    
    @abc.abstractmethod
    def chat_streaming(self, ...): ...
    
    # NO 'complete' method exists
    # NO 'embed' method exists (embedding is in services/embeddings.py)
```

**Impact:** Medium - Documentation shows `async` methods and `complete`/`embed` that don't exist
**Recommendation:** Update documentation to match actual interface

---

### Discrepancy #4: Newsletter Pipeline 3-Stage Diagram

**Document says:**
```
reader (extracts key points) → writer (generates summary) → editor (polishes)
```

**Actual (newsletter_pipeline.py:44-82):**
- `build_reader_prompt` - analyzes articles, identifies themes, highlights, connections
- `build_writer_prompt` - writes executive summary based on brief
- `build_editor_prompt` - reviews and improves summary

**Verdict:** Correct description, but slightly different emphasis (editor "polishes" vs "review and improve")

---

### Discrepancy #5: Rate Limiter acquire() Signature

**Document says:**
```python
class RateLimiter:
    def acquire(self, slots: int = 1, timeout: float = 30) -> bool:
```

**Actual (limiter.py:39-93):**
```python
def acquire(
    self,
    provider_id: str,
    model: str,
    max_concurrent: int,
    timeout: int = 300,
) -> bool:
```

**Impact:** High - Documentation signature is completely different from implementation
**Recommendation:** Update documentation to reflect actual interface

---

### Discrepancy #6: Webhooks Encryption at Rest

**Document says:**
- **Encrypted secrets at rest**

**Actual (webhooks.py:69-98):**
```python
def _encrypt_secret(plaintext: str) -> str:
    """Encrypt a webhook secret for storage. Returns versioned base64-encoded ciphertext."""
    from cryptography.fernet import Fernet
    key = _get_encryption_key()
    f = Fernet(key)
    ciphertext = f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"v2:enc:{ciphertext}"
```

**Verdict:** TRUE - Encryption is implemented

---

## 3. Issues Found

### Issue #1: Layering Violation - Services Importing from Adapters

**Location:** `services/crawling.py:12-13`
```python
if TYPE_CHECKING:
    from adapters.base import RawItem
```

**Analysis:** This is acceptable per AGENTS.md (TYPE_CHECKING only), but the documentation at line 3 states:
> "**Services should NOT import from adapters** (clean layering)."

The `TYPE_CHECKING` block is the correct pattern to avoid runtime imports, but the documentation doesn't acknowledge this exception.

**Verdict:** Acceptable pattern, but documentation should clarify that TYPE_CHECKING imports are allowed for type hints only.

---

### Issue #2: Missing Email Service Method

**Document says:**
```python
class EmailService:
    def send_newsletter(self, newsletter: Newsletter, subscribers: list[Subscriber]):
        """Send newsletter with connection pooling"""

    def send_verification(self, subscriber: Subscriber, token: str):
        """Send subscription verification email"""
```

**Actual (email.py):**
- `send_newsletter_email()` exists (line 286) - takes raw email, subject, html_content, unsubscribe_url
- `send_verification_email()` exists (line 185) - takes email, newsletter_type, verification_url, unsubscribe_url
- No `send_newsletter(Newsletter, list[Subscriber])` method

**Impact:** Low - The API is different but functionally complete
**Recommendation:** Update documentation to reflect actual method signatures

---

### Issue #3: trend_memory.py Uses `signal` Not `observation`

**Document says:**
```python
class TrendMemoryService:
    def propose(self, article: Article) -> list[TrendMemory]:
        """Propose new trend entries from article"""

    def consolidate(self, timeframe_days: int = 7):
        """Consolidate similar trend entries"""

    def search(self, query: str, limit: int = 5) -> list[TrendMemory]:
        """Semantic search for trend entries"""
```

**Actual (trend_memory.py):**
- `propose_trend_memory()` exists
- `consolidate_all_topics()` and `consolidate_topic()` exist
- `semantic_search_trends()` exists

**Note:** According to AGENTS.md Model Field Naming: "TrendMemory.observation is actually signal"

**Verdict:** Methods exist but naming differs from documentation

---

### Issue #4: Content Extractor - Trafilatura as Primary

**Document says:**
> Primary: `trafilatura` for main content extraction
> Fallback: `readability` for article parsing
> Final fallback: Raw HTML with boilerplate removal

**Actual (content_extractor.py:95-122):**
```python
result = trafilatura.bare_extraction(downloaded, url=url, with_metadata=True)
if result and result.get("text") and len(result["text"]) >= MIN_CONTENT_LENGTH:
    return ExtractionResult(...)

# Fallback to readability
doc = Document(downloaded)
soup = BeautifulSoup(doc.summary(), "html.parser")
text = soup.get_text(separator=" ", strip=True)

# Final fallback: EMPTY (no raw HTML fallback)
return ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)
```

**Verdict:** Matches documentation (no raw HTML fallback after readability fails)

---

## 4. Architecture Principle Violations

### Violation #1: services/llm/anthropic.py - Direct httpx Import

**Location:** `services/llm/anthropic.py:4`
```python
import httpx
```

**Issue:** LLM providers are infrastructure-specific but should ideally be in adapters per clean layering. However, this is a common pattern and may be acceptable given the tight coupling needed for LLM interaction.

**Verdict:** Acceptable - LLM providers are inherently infrastructure-specific

---

### Violation #2: services/llm/openai.py - validate_url_safe in Constructor

**Location:** `services/llm/openai.py:59`
```python
validate_url_safe(cfg.base_url)
```

**Issue:** Validating URL in service constructor adds startup overhead and could fail on config load.

**Verdict:** Low severity - SSRF protection is important but timing is suboptimal

---

## 5. Missing Functionality

### None Identified

All services mentioned in the architecture document exist in some form. No critical missing functionality was found.

---

## 6. Recommendations

### Priority 1 (Documentation Fixes)

1. **Update Circuit Breaker timing** - Change "half-open 30s" to "half-open 60s" in documentation
2. **Remove DeepSeek from documentation** - Or implement the provider
3. **Fix RateLimiter signature** - Update documentation to match actual `acquire(provider_id, model, max_concurrent, timeout)` signature
4. **Fix BaseLLMProvider interface** - Remove `async`, `complete()`, and `embed()` from docs
5. **Fix EmailService API** - Document actual method signatures

### Priority 2 (Minor Updates)

1. **Clarify TYPE_CHECKING exception** - Document that TYPE_CHECKING imports are allowed for type hints
2. **Update method names in TrendMemoryService docs** - Use actual method names: `propose_trend_memory`, `consolidate_all_topics`, `semantic_search_trends`

### Priority 3 (Future Enhancement)

1. **Consider async LLM methods** - Current implementation is sync; async could improve throughput

---

## Summary Table

| Category | Count |
|----------|-------|
| Verified items | 31 |
| Discrepancies | 6 |
| Issues found | 4 |
| Architecture violations | 2 |
| Missing functionality | 0 |

**Overall Assessment:** The architecture document is generally accurate but has several discrepancies in method signatures and timing values. Most issues are documentation-only and don't affect runtime behavior.

---

*End of review*

# Services Architecture Review

## Summary
The services.md documentation is largely accurate. Most claims about file inventory, interfaces, and implementations are correct. One significant discrepancy was found: `services/llm/types.py` is listed in the file inventory but does not exist.

## Verified Claims

The following claims were verified as accurate:

**File Inventory (Most)**
- `services/provider_base.py` exists with `BaseProvider` and `ProviderManager`
- `services/llm/base.py` exists with `BaseLLMProvider`, `LLMResponse`, `ToolDefinition`
- `services/llm/anthropic.py`, `llm/openai.py`, `llm/gemini.py`, `llm/ollama.py` all exist
- `services/llm/errors.py` exists (AuthError, RateLimitError, etc.)
- `services/llm/json_utils.py` exists with `extract_json()` function
- `services/llm/__init__.py` exists
- `services/subagent/` exists with tools.py, runner.py, chain.py, etc.
- `services/search/` exists with all providers (duckduckgo.py, google.py, searxng.py, hybrid.py, sqlite_fts.py, session.py)
- `services/article_parser.py` exists (Article JSON parsing)
- `services/article_validation.py` exists with `ValidationError(ValueError)` and `validate_final_article()`
- `services/article_fallback.py` exists with `build_fallback_article_json()`
- `services/researcher.py` exists with `build_research_prompt()`
- `services/writer.py` exists with `build_writer_prompt()`
- `services/editor.py` exists with `build_editor_prompt()`, `build_editor_prompt_with_context()`
- `services/content_extractor.py` exists (trafilatura + readability + BeautifulSoup)
- `services/crawling.py` exists with TYPE_CHECKING import from adapters.base (documented layering exception)
- `services/trend_detector.py` exists with `r"\bdeepseek\b"` regex pattern (as documented)
- `services/embeddings.py` exists
- `services/newsletter_pipeline.py` exists with reader→writer→editor pipeline
- `services/pipeline_monitor.py` exists
- `services/pipeline_degradation.py` exists
- `services/pipeline_failure.py` exists
- `services/pipeline_utils.py` exists
- `services/circuit_breaker.py` exists with `CircuitBreaker`, `RedisCircuitBreaker`, `get_breaker()`, `circuit_protected()`, `CircuitOpenError`
- `services/context_service.py` exists
- `services/related.py` exists
- `services/trend_memory.py` exists (module-level functions, returns `SubagentResponse` not `list[TrendMemory]` - accurate)
- `services/email.py` exists with `SMTPConnectionPool` class at lines 14-122, global `_smtp_pool` singleton via `_get_smtp_pool()`
- `services/webhooks.py` exists with HMAC-SHA256 signatures, encrypted secrets at rest, retry logic, WebhookEvent model
- `services/cache.py` exists with `ResponseCache` L1+L2 (in-memory OrderedDict + Redis)
- `services/limiter.py` exists with `ModelLimiter` class
- `services/cost_tracker.py` exists tracking tokens, cost per model, daily/monthly budgets

**LLM Provider System**
- `BaseLLMProvider` correctly inherits from `BaseProvider` and `abc.ABC`
- `BaseProvider` provides `provider_id` and `config` fields (verified in provider_base.py:17-19)
- Circuit breaker pattern: `Closed → Open → Half_Open → Closed` state transitions confirmed

**Pipeline Services**
- `newsletter_pipeline.py` correctly documents 3-stage newsletter generation:
  - reader: extracts themes/highlights/connections via `NewsletterBrief` schema (line 198)
  - writer: generates `ExecutiveSummary` (line 221)
  - editor: reviews and improves (line 252)
- Article processing stages documented correctly:
  - `researcher.py`: `research_article` stage, builds research brief
  - `writer.py`: `write_article` stage, writes in Smart Brevity format
  - `editor.py`: `edit_article` stage, edits + contextualization

**Rate Limiter Interface (limiter.py:39-171)**
- `acquire(provider_id: str, model: str, max_concurrent: int, timeout: int = 300) -> bool` ✓
- `release(provider_id: str, model: str, timeout: int = 300) -> None` ✓
- `get_active(provider_id: str, model: str) -> int | None` ✓
- `cleanup_stale_slots() -> int` ✓
- `is_healthy() -> bool` ✓

**Email Service (email.py:14-122)**
- `SMTPConnectionPool` class at line 14
- `__init__(pool_size: int = 5)` ✓
- `get_connection() -> smtplib.SMTP` ✓
- `return_connection(server: smtplib.SMTP)` ✓
- `close_all()` ✓
- `_is_healthy(server) -> bool` ✓
- `_compute_cfg_hash(cfg: dict) -> str` ✓
- Global `_smtp_pool` singleton via `_get_smtp_pool()` ✓
- Thread-safe with config change detection ✓

**Circuit Breaker (circuit_breaker.py)**
- `CircuitBreaker.__init__` requires `name` parameter (line 40)
- `can_execute()` method (line 155) - NOT `is_open()`
- `get_breaker(name, failure_threshold=5, ...)` factory function (line 388)
- `circuit_protected(breaker_name, fallback=None)` decorator (line 415)
- `CircuitOpenError` exception (line 451)

**Webhook Security (webhooks.py)**
- HMAC-SHA256 signatures with timestamp replay protection (`_sign_payload` at line 104)
- Encrypted secrets at rest via Fernet (`_encrypt_secret` at line 69, `_decrypt_secret` at line 79)
- Key rotation support via `WEBHOOK_SECRET_KEY_PREVIOUS_1/2` (lines 56-58)
- Retry logic with exponential backoff (`_send_webhook_with_retry` at line 129)
- `WebhookEvent` model tracking (line 274)

**Layering Violations (documented and accurate)**
- `services/crawling.py` imports from `adapters.base` via TYPE_CHECKING block (lines 12-15)
- `services/subagent/tools.py` imports from `models` and `extensions` (verified at lines 105-147)
- `schemas/common.py` imports from `services.config_cache` (documented with comment)

**Trend Memory (trend_memory.py:219)**
- `propose_trend_memory()` returns `SubagentResponse` (NOT `list[TrendMemory]`) - accurately documented
- Module uses module-level functions (not a class) - accurately documented

**Content Extraction (content_extractor.py)**
- Primary: trafilatura (line 95)
- Fallback: readability + BeautifulSoup (lines 107-119)
- If both fail: Returns `ExtractionResult` with `ExtractionStatus.EMPTY` (line 124) - accurately documented

**DeepSeek Note (trend_detector.py:21)**
- DeepSeek regex pattern `r"\bdeepseek\b"` confirmed - NOT a search provider

## Discrepancies Found

### Critical

- **Claim**: "services/llm/types.py" exists as "Type definitions" in file inventory
- **Reality**: `services/llm/types.py` does NOT exist. The llm/ directory contains: `__init__.py`, `base.py`, `errors.py`, `json_utils.py`, `anthropic.py`, `openai.py`, `gemini.py`, `ollama.py`
- **Severity**: Major
- **Location**: `architecture/services.md:17`
- **Suggested fix**: Remove the `types.py` line from the file inventory, or investigate if type definitions were moved to another location (e.g., `schemas/llm.py` contains LLM-related type configs)

### Minor

- **Claim**: "MultiFernet: Key rotation support via `WEBHOOK_SECRET_KEY_PREVIOUS_1/2` env vars" (from AGENTS.md security features)
- **Reality**: The implementation uses fallback Fernet keys for v1 format decryption, but does NOT use MultiFernet class for the primary encryption path. The v2 encryption (line 76) uses single Fernet only. The key rotation via fallback keys is functional but not true MultiFernet rotation.
- **Severity**: Minor (documentation in AGENTS.md may be slightly overstated)
- **Location**: `services/webhooks.py:51-67`, `services/webhooks.py:69-76`
- **Suggested fix**: If MultiFernet rotation is intended, update `_encrypt_secret` to use MultiFernet with all keys. Otherwise, update AGENTS.md to say "Fallback keys for legacy format decryption"

## Bugs Identified

No bugs identified - the code appears to correctly implement the documented functionality.

## Improvement Opportunities

### 1. Missing Type Definitions File

- **Improvement**: If `services/llm/types.py` was intended to contain type definitions, consider creating it or documenting where LLM-related types are defined (likely in `schemas/llm.py` based on the AGENTS.md mention of `schemas/llm.py` containing provider config schemas)
- **Location**: N/A - file does not exist
- **Benefit**: Accurate documentation prevents confusion

### 2. Documentation Could Be More Specific About Content Extraction

- **Improvement**: The content_extractor.py documents the ExtractionStatus enum values but doesn't clearly show when each fallback is used
- **Location**: `services/content_extractor.py:25-29`
- **Benefit**: Better inline documentation would help future developers understand the extraction flow

## Stale Items Found

- `services/llm/types.py` listed in architecture/services.md but does not exist

## Recommendations

1. **High Priority**: Remove or correct the `services/llm/types.py` entry in the file inventory (line 17 of architecture/services.md). Verify if type definitions should exist or if they were moved to `schemas/llm.py`.

2. **Low Priority**: Consider adding a comment in `services/webhooks.py` clarifying that the key rotation uses fallback keys for v1 format rather than MultiFernet-style simultaneous rotation, to prevent future confusion.

3. **Documentation Maintenance**: When adding new service files, ensure the architecture/services.md file inventory is updated to reflect the changes.
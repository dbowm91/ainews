# AINEWS - Implemented Features (as of 2026-04-30)

This document lists all features implemented from plans/plan.md across Waves 1-5.

## Wave 1: Critical Issues (COMPLETED)

### 1.1 Celery Task `acks_late=True` ✅
All Celery tasks now include `acks_late=True` and `task_reject_on_worker_lost=True` in their decorator to ensure task is not lost on worker crash.

**Files modified:** tasks/select.py, tasks/research.py, tasks/write.py, tasks/edit.py, tasks/crawl.py, tasks/extract.py, tasks/newsletter.py, tasks/retry.py, tasks/cleanup.py

### 1.2 ResponseCache Stampede Protection ✅
Replaced polling-based stampede protection with Redis pub/sub pattern using `blpop` alternative.

**File:** services/cache.py - `get_or_set()` method

### 1.3 Fix `resolve_env_var()` Silent Empty String Fallback ✅
Added `required` parameter. When `required=True`, raises `ValueError` on missing env var.

**Files modified:** schemas/common.py, schemas/llm.py, config.py

### 1.4-1.6 CSS Consolidation ✅
- Removed duplicate `:root` and `[data-theme="light"]` blocks from critical.css
- Added `@import "./variables.css"` to critical.css
- Created build/generate-critical-css.js for auto-generating critical_css.html
- Deduplicated layout.css rules

**Files modified:** static/css/critical.css, static/css/layout.css, build/generate-critical-css.js

## Wave 2: High Priority (COMPLETED)

### 2.1 SMTP Connection Pooling ✅
Implemented `SMTPConnectionPool` class with configurable pool size via `SMTP_POOL_SIZE`.

**Files modified:** services/email.py, config.py

### 2.2 Admin Dashboard Query Consolidation ✅
Added caching with 60s TTL and consolidated queries using `with_entities()` to avoid loading full objects.

**File:** routes/admin/dashboard.py

### 2.3 Bulk Article N+1 Query Fix ✅
Added `joinedload` for `Article.source` and `Article.tags` to bulk article queries.

**File:** routes/admin/api/articles.py

### 2.4 Webhook Dispatch Async ✅
Moved webhook dispatch to Celery task (`dispatch_webhook_task`) for non-blocking operation.

**Files modified:** routes/admin/api/webhooks.py, tasks/webhook.py (new)

### 2.5 HMAC Task Signing ✅
Added `verify_task()` HMAC verification to all 10 beat-scheduled tasks.

**Files modified:** tasks/scheduler.py, tasks/retry.py, tasks/newsletter.py, tasks/cleanup.py

### 2.6 Audit Logging ✅
Added `log_admin_action()` to 16+ admin mutation endpoints across 8 files.

**Files modified:** routes/admin/review.py, routes/admin/sources.py, routes/admin/api/config.py, routes/admin/topic_notes.py, routes/admin/trend_memory.py, routes/admin/articles.py, routes/admin/pipelines.py, routes/admin/newsletters.py

### 2.7 Response Cache Invalidation ✅
Added `cache.invalidate_prefix()` calls to admin mutations for cache consistency.

**Files modified:** routes/admin/trend_memory.py, routes/admin/topic_notes.py, routes/admin/sources.py, routes/admin/review.py

### 2.8 Per-Process Cache Stats - Redis Backend ✅
Replaced in-memory counters with Redis-backed stats using `ainews:cache:stats` hash. Falls back to in-memory if Redis unavailable.

**File:** services/cache.py

### 2.9 L1/L2 Cache TTL Refresh Fix ✅
Added `self._redis.expire(full_key, self._ttl)` on L1 cache hits to refresh Redis TTL.

**File:** services/cache.py

## Wave 3: Medium Priority (COMPLETED)

### 3.1 Admin Article Form Input Validation ✅
Added field length limits: MAX_HEADLINE_LENGTH=500, MAX_TLDR_LENGTH=300, MAX_BODY_LENGTH=50000, etc.

**File:** routes/admin/articles.py

### 3.2 Database Indexes ✅
Added missing indexes: Webhook.active, Source.active, Subscriber.newsletter_type, PipelineRun.run_type, composite (run_type, status).

**Files modified:** models.py, migrations/versions/030_add_missing_indexes.py

### 3.3 OpenTelemetry Exporter Fix ✅
Replaced no-op span processor with real `OTLPSpanExporter` when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured.

**Files modified:** services/logging_utils.py, pyproject.toml, config.py, .env.example

### 3.4 Subagent Exception Handling ✅
Replaced 16 bare `except Exception` with specific exception types (SQLAlchemyError, KeyError, AttributeError, etc.) with fallback to `except Exception` for unexpected errors.

**File:** services/subagent.py

### 3.5 Fix Content Sanitization Double-Escaping ✅
Removed `|e` filter from bleached content in templates (bleach.clean() already sanitizes).

**File:** templates/partials/condensed_article.html

### 3.6 Create Admin API Schemas ✅
Created `schemas/admin.py` with Pydantic models for request validation.

**Files modified:** schemas/admin.py (new), routes/admin/api/articles.py, routes/admin/api/sources.py

### 3.7 OTel Tracing for Subagent LLM Calls ✅
Added `traced_llm_call` context manager to subagent LLM invocations.

**File:** services/subagent.py

### 3.8 Newsletter Tasks Bare Commits Fix ✅
Added `db.session.rollback()` to exception handlers in newsletter tasks.

**File:** tasks/newsletter.py

## Wave 4: LLM Pipeline Improvements (COMPLETED)

### 4.1 Memory Summarization for Context Overflow ✅
Added LLM-based summarization for large context overflow via `smart_truncate_context()`.

**Files modified:** services/prompts.py, schemas/pipeline.py

### 4.2 Quality Assessment Infrastructure ✅
Created `services/quality.py` with QualityScore, LLMQualityAssessor, lightweight_quality_signals(), and hallucination detection.

**File:** services/quality.py (new)

### 4.3 Stage-Aware Tool Selection Enhancement ✅
Created `services/tool_selection.py` with ToolSelector protocol, StageAwareToolSelector, and KeywordToolSelector.

**Files modified:** services/tool_selection.py (new), services/subagent.py

### 4.4 Streaming Support for LLM Adapters ✅
Added `chat_streaming()` method to BaseLLMProvider and all provider adapters (OpenAI, Anthropic, Ollama, Gemini).

**Files modified:** services/llm/base.py, services/llm/openai.py, services/llm/anthropic.py, services/llm/ollama.py, services/llm/gemini.py

### 4.5 Redis-Backed Circuit Breaker ✅
Created `RedisCircuitBreaker` class storing state in Redis with in-memory fallback.

**Files modified:** services/circuit_breaker.py, services/llm/__init__.py

## Wave 5: Additional Improvements (COMPLETED)

### 5.1 API Response Format Standardization ✅
Created `api_response()` helper in `routes/admin/api/utils.py` for standardized JSON envelope.

**Files modified:** routes/admin/api/utils.py (new), routes/admin/api/sources.py, routes/admin/api/health.py, routes/admin/api/pipeline.py

### 5.2 PATCH Method Support ✅
Added PATCH method to sources and webhooks API for partial updates.

**Files modified:** routes/admin/api/sources.py, routes/admin/api/webhooks.py

### 5.3 API Versioning (Prefix) ✅
Added `/api/v1/` prefix to admin API blueprint.

**File:** routes/admin/api/__init__.py

### 5.4 OAuth2/API Token Support ✅
Created ApiToken model and token authentication for admin API.

**Files modified:** models.py, migrations/versions/032_add_api_tokens.py, routes/admin/__init__.py, routes/admin/api_tokens.py (new)

### 5.5 Redis-Backed Metrics with Fallback ✅
Added Redis-backed counters/gauges/histograms with in-memory fallback.

**File:** services/metrics.py

### 5.6 Importance-Weighted Context Truncation ✅
Implemented `importance_weighted_truncate()` that scores segments by key topic relevance.

**File:** services/prompts.py

### 5.7 FTS5 Index for Article Search ✅
Created FTS5 virtual table for fast article search with ILIKE fallback.

**Files modified:** migrations/versions/031_add_fts5_search.py, routes/admin/api/articles.py

### 5.8 Container Queries Support ✅
Added `container-type: inline-size` to feed containers with `@supports` fallback.

**File:** static/css/articles.css

### 5.9 CSS @layer Organization ✅
Added `@layer` directives to style.css for better cascade control.

**File:** static/css/style.css

### 5.10 LLM Token-Aware Truncation ✅
Added optional `model` parameter to `sliding_window_truncate()` for token-aware truncation.

**Files modified:** services/prompts.py, tasks/write.py, tasks/edit.py

## Summary

All 28 items across Waves 1-5 have been implemented. The codebase now has:
- Better reliability (Celery acks_late, HMAC signing, circuit breakers)
- Improved performance (caching, FTS5 search, DB indexes, query consolidation)
- Enhanced security (API tokens, audit logging, cache invalidation)
- LLM pipeline improvements (streaming, quality assessment, memory summarization)
- Frontend enhancements (CSS organization, container queries)

Total commits: 28+ across multiple waves.

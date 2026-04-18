# Consolidated Implementation Plan

This document consolidates all improvement items from the planning phase into a unified, prioritized implementation plan with wave-based parallelization.

## Overview

This plan merges items from:
- `plans/plan2.md` — Code Quality Improvement Plan
- `plans/plan4.md` — Performance Improvement Plan

The implementation is organized into **6 waves** of parallelizable work:

| Wave | Focus | Priority | Items | Parallelizable |
|------|-------|----------|-------|----------------|
| **Wave 1** | Security Hardening | Critical | W1.1-W1.3 | Yes |
| **Wave 2** | LLM Provider Refactoring | High | W2.1-W2.3 | Yes (per-provider) |
| **Wave 3** | Database & Indexing | High | W3.1-W3.3 | Yes |
| **Wave 4** | Error Handling & Cleanup | Medium | W4.1-W4.5 | Yes |
| **Wave 5** | Performance Optimization | Medium | W5.1-W5.8 | Partial |
| **Wave 6** | Test Coverage | Low | W6.1-W6.2 | Yes |

---

## Wave 1: Security Hardening

### W1.1: Extract Error Handler Factory
**Priority**: Critical | **Impact**: Security/DRY | **Effort**: Medium

**Files**: `services/llm/errors.py`, `services/llm/openai.py`, `services/llm/anthropic.py`, `services/llm/ollama.py`, `services/llm/gemini.py`

**Status**: NOT DONE — Individual `_handle_*_error` functions still exist in each provider

**Problem**: All four LLM providers have nearly identical error handler functions.

**Current state** (each provider has its own copy):
```python
# services/llm/openai.py:18-33
# services/llm/anthropic.py:18-33
# services/llm/ollama.py:18-29
# services/llm/gemini.py:17-28
```

**Solution**: Create a factory function in `services/llm/errors.py`:
```python
def make_error_handler(
    provider_name: str,
    rate_limit_exc: tuple[type, ...],
    auth_exc: type,
    timeout_exc: tuple[type, ...],
) -> Callable[[Exception], Exception]:
    def handler(e: Exception) -> Exception:
        return handle_provider_error(
            e, provider_name,
            rate_limit_exc=rate_limit_exc,
            auth_exc=auth_exc,
            timeout_exc=timeout_exc,
        )
    return handler
```

**Usage**:
```python
_handle_openai_error = make_error_handler(
    "OpenAI",
    rate_limit_exc=(RateLimitError,),
    auth_exc=AuthenticationError,
    timeout_exc=(APITimeoutError, APIConnectionError),
)
```

---

### W1.2: Move Client Initialization to Base Class
**Priority**: High | **Impact**: DRY | **Effort**: Medium

**Files**: `services/llm/base.py`, all provider files

**Status**: NOT DONE — Each provider has its own client property with double-checked locking

**Problem**: All four providers implement identical double-checked locking for client initialization.

**Solution**: Move to `BaseLLMProvider` in `services/llm/base.py`:
1. Add abstract `_create_client()` method
2. Add shared `client` property with thread-safe lazy initialization

---

### W1.3: Consolidate Tool Calling Loop
**Priority**: Medium | **Impact**: DRY | **Effort**: High

**Files**: `services/llm/base.py`, `services/llm/openai.py`, `services/llm/ollama.py`, `services/llm/gemini.py`

**Status**: NOT DONE — ~100+ lines of nearly identical tool calling logic per provider

**Problem**: `chat_with_tools()` implementations share ~100+ lines of nearly identical logic.

**Solution**: Abstract common loop structure into `BaseLLMProvider` with provider-specific hooks.

---

## Wave 2: LLM Provider Refactoring

### W2.1: Pre-compile Regex Patterns in LLM Modules
**Priority**: High | **Impact**: Performance | **Effort**: Low

**Files**: `services/llm/openai.py`, `services/llm/anthropic.py`, `services/llm/ollama.py`, `services/llm/gemini.py`

**Status**: NOT VERIFIED — Need to check each provider for uncompiled regex

**Solution**: Pre-compile regex patterns at module level:
```python
_TITLE_WORDS_RE = re.compile(r"[a-z0-9]+")
```

---

### W2.2: Add LLM Provider Tests
**Priority**: Medium | **Impact**: Reliability | **Effort**: Medium

**Files**: `tests/test_llm_adapters/`

**Status**: NOT VERIFIED

**Solution**: Ensure all LLM providers have comprehensive test coverage.

---

## Wave 3: Database & Indexing

### W3.1: Add Index on Article.source_id
**Priority**: High | **Impact**: Performance | **Effort**: Low

**Files**: `models.py`, new migration

**Status**: NOT DONE — No index found on Article.source_id

**Problem**: Dashboard queries group by `source_id` without an explicit index.

**Solution**: Add index:
```python
db.Index("ix_articles_source_id", "source_id"),
```

---

### W3.2: Add Index on Source.name
**Priority**: High | **Impact**: Performance | **Effort**: Low

**Files**: `models.py`, new migration

**Status**: NOT DONE — No index found on Source.name

**Problem**: Admin article list sorts sources by name without index.

**Solution**: Add `index=True` to Source.name column or via migration.

---

### W3.3: Add Composite Indexes
**Priority**: High | **Impact**: Performance | **Effort**: Low

**Files**: New migrations

**Status**: NOT VERIFIED — Need to check if composite indexes exist

**Solution**:
```python
# Migration: ix_subscribers_newsletter_active_deleted
op.create_index('ix_subscribers_newsletter_active_deleted', 'subscribers',
    ['newsletter_type', 'active', 'deleted_at'], unique=False)

# Migration: ix_pipeline_logs_run_created
op.create_index('ix_pipeline_logs_run_created', 'pipeline_logs',
    ['run_id', 'created_at'], unique=False)
```

---

## Wave 4: Error Handling & Cleanup

### W4.1: Break Pipeline Circular Dependency
**Priority**: High | **Impact**: Maintainability | **Effort**: Medium

**Files**: `services/pipeline_utils.py` (new), `services/pipeline_degradation.py`, `tasks/pipeline.py`

**Status**: NOT DONE — `pipeline_degradation.py` still imports `_dispatch_next` from `tasks.pipeline`

**Problem**: Deferred imports between `tasks/pipeline.py` and `services/pipeline_degradation.py`.

**Solution**:
1. Create `services/pipeline_utils.py` with `_log_pipeline` and `_dispatch_next`
2. Update both modules to import from `pipeline_utils`

---

### W4.2: Remove Unreachable Code in article.py
**Priority**: Low | **Impact**: Cleanliness | **Effort**: Trivial

**Files**: `services/article.py`

**Status**: NOT DONE — Line 75 has `db.session.expire_all()` after `raise`

**Problem**: Unreachable code after `raise` statement.

**Solution**: Remove line 75.

---

### W4.3: Verify Search Provider Exception Handling
**Priority**: Medium | **Impact**: Reliability | **Effort**: Low

**Files**: `services/search/duckduckgo.py`, `services/search/google.py`, `services/search/searxng.py`

**Status**: PARTIALLY DONE — google.py and searxng.py catch `requests.RequestException`

**Problem**: duckduckgo.py still catches bare `Exception`.

**Solution**: Add `type(e).__name__` to log message for better debugging.

---

### W4.4: Fix API Adapter Exception Handling
**Priority**: Medium | **Impact**: Reliability | **Effort**: Low

**Files**: `adapters/api.py`

**Status**: NOT VERIFIED

**Solution**: Use `requests.RequestException` for consistency.

---

### W4.5: Fix SoftTimeLimitExceeded Handling in All Pipeline Tasks
**Priority**: Medium | **Impact**: Reliability | **Effort**: Medium

**Files**: `tasks/pipeline.py`, `tasks/crawl.py`, `tasks/extract.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`

**Status**: NOT VERIFIED — Need to verify all pipeline tasks handle SoftTimeLimitExceeded

**Solution**: Add explicit handling before generic exception handling:
```python
from billiard.exceptions import SoftTimeLimitExceeded

try:
    # ... stage work ...
except SoftTimeLimitExceeded:
    db.session.rollback()
    logger.error("SoftTimeLimitExceeded in %s for article %s", stage, article_id)
    raise
```

---

## Wave 5: Performance Optimization

### W5.1: Fix Related Articles Query (200 Candidates)
**Priority**: P0 | **Impact**: High | **Effort**: Medium

**Files**: `services/related.py`

**Status**: NOT DONE

**Problem**: Every article page load loads 200 candidates, iterates all 200, returns top 5.

**Solution**:
1. Reduce candidate limit from 200 to 50
2. Implement scored SQL query for database-level filtering

---

### W5.2: Cache Admin Dashboard Stats
**Priority**: P1 | **Impact**: High | **Effort**: Medium

**Files**: `routes/admin/dashboard.py`

**Status**: NOT VERIFIED

**Problem**: `Source.query.all()` loads ALL sources; no caching of dashboard stats.

**Solution**:
1. Cache dashboard stats in Redis with 60-second TTL
2. Use single aggregated query

---

### W5.3: Tune Redis Connection Pool
**Priority**: P1 | **Impact**: High | **Effort**: Low

**Files**: `extensions.py`

**Status**: NOT VERIFIED

**Problem**: 50 connections may be undersized; no `socket_timeout` configured.

**Solution**:
```python
_redis_pool = redis.ConnectionPool.from_url(
    url,
    max_connections=100,
    socket_timeout=5,
    socket_connect_timeout=3,
    socket_keepalive=True,
)
```

---

### W5.4: Optimize find_duplicate_titles() Two-Query Pattern
**Priority**: P2 | **Impact**: Medium | **Effort**: Medium

**Files**: `services/article.py`

**Status**: NOT DONE — Two-query pattern still exists (lines 264-280)

**Problem**: First query scans titles, second query loads full articles on match.

**Solution**: Use single batched query or compute title hash signature during extraction.

---

### W5.5: Cache Top Impact Articles
**Priority**: P2 | **Impact**: Medium | **Effort**: Low

**Files**: `routes/public/feeds.py`

**Status**: NOT VERIFIED

**Problem**: `_get_top_impact()` runs on every homepage load when cache is cold.

**Solution**: Add Redis cache with key `top_impact:3` and 300s TTL.

---

### W5.6: Tighten Article Version Retry Logic
**Priority**: P3 | **Impact**: Low | **Effort**: Trivial

**Files**: `services/article.py`

**Status**: NOT DONE — `max_retries = 3` at line 160

**Problem**: Up to 3 database round-trips on IntegrityError race condition.

**Solution**: Change `max_retries = 3` to `max_retries = 2`.

---

### W5.7: Add HTTP Request Metrics Middleware
**Priority**: P3 | **Impact**: Observability | **Effort**: Medium

**Files**: `app.py`, `services/metrics.py`

**Status**: NOT VERIFIED — `record_request()` exists but is never called

**Problem**: No automatic HTTP request instrumentation.

**Solution**: Add request timing middleware to call `record_request()`.

---

### W5.8: Add Request ID Tracing Across Pipeline
**Priority**: Low | **Impact**: Observability | **Effort**: Medium

**Files**: `tasks/pipeline.py`, `tasks/*`, `services/logging_utils.py`

**Status**: NOT VERIFIED

**Solution**: Propagate Celery task ID through all pipeline stages for correlation.

---

## Wave 6: Test Coverage

### W6.1: Add Newsletter HTML Escape Test
**Priority**: Medium | **Impact**: Security | **Effort**: Low

**Files**: `tests/test_newsletter.py`

**Status**: NOT VERIFIED

**Solution**:
```python
def test_html_escaping_in_newsletter():
    html = build_newsletter_html(articles=[], subject="Test <script>alert('xss')</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
```

---

### W6.2: Add Subagent Escape Function Test
**Priority**: Medium | **Impact**: Security | **Effort**: Low

**Files**: `tests/test_subagent.py`

**Status**: NOT VERIFIED

**Solution**: Test `_escape_prompt_data()` with various inputs including edge cases.

---

## Items Already Complete

The following items from the previous plan were verified as COMPLETE:

- **W1 (XSS in templates)**: All templates use `|e` filter for LLM-generated content
- **W2 (Prompt injection in subagents)**: `_escape_prompt_data()` and `esc_xml_text()` are used
- **W3 (eval() replacement)**: AST-based `_evaluate_condition()` implemented in `services/subagent.py`
- **W4.2 (Eager loading)**: `joinedload(Article.source)` and `joinedload(Article.tags)` added to routes
- **W4.3 (Cache stampede)**: Per-key locking with `SET NX EX` + polling implemented
- **W4.4 (ThreadPoolExecutor reuse)**: `future.cancel()` before shutdown implemented
- **W4.5 (Limiter acquire timeout)**: Polling loop with exponential backoff implemented
- **W4.8 (String concatenation)**: `para_parts` list with `"".join()` implemented
- **W5.1 (Newsletter parallelization)**: Celery group for topic newsletters implemented
- **W5.2 (Email batching)**: Batches of 500 implemented
- **W5.3 (retry_stuck batching)**: Batches of 50 implemented
- **W5.7 (Source health hysteresis)**: `HEALTHY_THRESHOLD=3` implemented
- **W5.9 (Trend memory optimization)**: Batched lookups implemented
- **W5.10 (Newsletter transaction safety)**: Draft state and rollback implemented

---

## Implementation Order

### Phase 1: Quick Wins (Parallel)
- W4.2: Remove unreachable code (trivial)
- W5.6: Tighten retry logic (trivial constant change)
- W4.3: Verify search provider exception handling
- W6.1, W6.2: Add test coverage

### Phase 2: Security & Indexes (Parallel)
- W1.1: Extract error handler factory
- W3.1, W3.2, W3.3: Add database indexes
- W4.4: Fix API adapter exception handling
- W4.5: Fix SoftTimeLimitExceeded handling

### Phase 3: LLM Refactoring (Parallel per provider)
- W1.2: Move client initialization to base class
- W1.3: Consolidate tool calling loop
- W2.1: Pre-compile regex in LLM modules

### Phase 4: Circular Import Resolution
- W4.1: Break pipeline circular dependency (depends on Phase 2-3 for context)

### Phase 5: Performance (Some dependencies on Phase 2)
- W5.1: Fix related articles query
- W5.2: Cache admin dashboard
- W5.3: Tune Redis pool
- W5.4: Optimize duplicate detection
- W5.5: Cache top impact articles
- W5.7: Add HTTP metrics middleware
- W5.8: Add request ID tracing

---

## Verification

After each phase, run:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

For database migrations:
```bash
scripts/verify_backup.sh
.venv/bin/python -m pytest tests/test_migration.py -v
```

---

## Notes

- All security improvements use existing `html` and `services.prompts` utilities
- Database migrations use SQLite-compatible operations only
- No new external dependencies required
- Backward compatible — all changes are internal refactoring

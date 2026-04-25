# Consolidated Implementation Plan

**Created:** April 25, 2026
**Last Updated:** April 25, 2026
**Status:** PLANNED — Not yet implemented
**Source:** Consolidated from plan.md, plan2.md, plan3.md, plan4.md, plan5.md, plan6.md, plan7.md, plan9.md

---

## Overview

This plan consolidates all pending implementation items from 8 plan files into a single coherent roadmap with wave-based parallelization. Items are grouped into waves that can be implemented in parallel by sub-agents.

**Wave Structure:**
- Wave 1: Quick wins (standalone, low risk)
- Wave 2: Testing infrastructure
- Wave 3: Core performance & reliability
- Wave 4: Agent harness improvements
- Wave 5: Security hardening
- Wave 6: UI/UX improvements
- Wave 7: Architecture & infra
- Wave 8: Advanced agent features
- Wave 9: Documentation

---

## Wave 1: Quick Wins

*Independent, low-effort items that provide immediate value. Can be implemented in parallel.*

### 1.1 Precompile Regex in `services/llm/base.py`

**Source:** plan2.md Priority 1
**Files:** `services/llm/base.py`
**Status:** NOT YET DONE — regex still compiled inline at lines 36 and 45

**Current code (lines 36, 45):**
```python
match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw, re.MULTILINE)
match = re.search(r'\{[\s\S]*\}', raw)
```

**Fix:** Add module-level precompiled patterns:
```python
_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*([\s\S]+?)\s*```', re.MULTILINE)
_JSON_BRACES_RE = re.compile(r'\{[\s\S]*\}')
```

**Verification:** Run LLM adapter tests after change.

---

### 1.2 Add Logging to Bare Excepts (6 locations)

**Source:** plan2.md Priority 4
**Files:** `tasks/extract.py`, `services/content_extractor.py`, `services/llm/__init__.py`, `services/trend_detector.py`, `services/health.py`

| Line | File | Fix |
|------|------|-----|
| 343 | `tasks/extract.py` | `logger.warning("Metrics increment failed: %s", e)` |
| 60 | `services/content_extractor.py` | `logger.warning("Content extraction failed: %s", e)` |
| 127 | `services/llm/__init__.py` | `logger.warning("Cache fallback triggered: %s", e)` |
| 83 | `services/trend_detector.py` | `logger.warning("Config load failed: %s", e)` |
| 97 | `services/trend_detector.py` | `logger.warning("Redis error, using file fallback: %s", e)` |
| 183 | `services/health.py` | `logger.debug("Version info read failed: %s", e)` |

---

### 1.3 Subagent Thread Pool Configurability

**Source:** plan4.md Priority 3
**Files:** `services/subagent.py`
**Status:** NOT YET DONE — hardcoded `max_workers=8` at line 28

**Current code:**
```python
_subagent_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="subagent")
```

**Fix:**
```python
SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "8"))
_subagent_executor = ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS, thread_name_prefix="subagent")
```

---

### 1.4 Add Cost Pricing for Additional Providers

**Source:** plan6.md Item 7
**Files:** `services/cost_tracker.py`
**Status:** PARTIALLY DONE — base pricing exists, missing newer providers

**Add to `_DEFAULT_RATES`:**
```python
"deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
"deepseek/deepseek-coder": {"input": 0.14, "output": 0.28},
"minimax/MiniMax-M2.5": {"input": 0.10, "output": 0.30},
"gemini/gemini-2.0-flash": {"input": 0.10, "output": 0.40},
"groq/llama-3.3-70b": {"input": 0.20, "output": 0.20},
```

---

## Wave 2: Testing Infrastructure

*Items that improve test reliability and developer experience.*

### 2.1 Fix Test Mock Return Values

**Source:** plan5.md Item 1
**Priority:** HIGH — ~10-12 pre-existing test failures
**Files:** `tests/helpers/pipeline_mocks.py`, `tests/test_pipeline_*.py`, `tests/test_llm_adapters/test_anthropic.py`

**Problem:** Mock returns dict but pipeline code expects `.tokens_used` attribute.

**Affected tests:**
| Test File | Failure | Fix |
|-----------|---------|-----|
| `test_pipeline_e2e.py` | Multiple | Mock needs `.tokens_used` |
| `test_pipeline_edit.py` (x3) | Multiple edit tests | Missing `final_article` field |
| `test_pipeline_write.py` | `test_write_populates_draft` | Mock setup incomplete |
| `test_llm_adapters/test_anthropic.py` | `test_chat_with_schema` | Missing `betas` kwarg |

**Fix in `tests/helpers/pipeline_mocks.py`:**
- Convert mock return from dict to object with `tokens_used` attribute
- Add `used_fallback` as attribute (not just key)
- Ensure mock matches `BaseLLMProvider.call()` return signature

---

### 2.2 Test Helper Refactoring

**Source:** plan5.md Item 7
**Files:** `tests/test_pipeline_edit.py`, `tests/test_pipeline_write.py`, `tests/mock_redis.py`, `tests/test_subagent.py`

**Items:**
1. Refactor test files to use `setup_pipeline_mocks` helper
2. Split `test_subagent.py` (994 lines) by test class
3. Extend `mock_redis.py` with missing methods (`LREM`, `SMEMBERS`)

---

## Wave 3: Core Performance & Reliability

### 3.1 HTTP Session Pooling for Search Providers

**Source:** plan4.md Priority 1
**Files:** Create `services/search/session.py`, modify `services/search/searxng.py`, `services/search/google.py`

**Implementation:**

Create `services/search/session.py`:
```python
"""Shared HTTP session for search providers with connection pooling."""

import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_SEARCH_POOL_MAXSIZE = int(os.environ.get("SEARCH_POOL_MAXSIZE", "10"))
_SEARCH_POOL_CONNECTIONS = int(os.environ.get("SEARCH_POOL_CONNECTIONS", "5"))

_search_session = None

def get_session() -> requests.Session:
    """Get the shared search session (singleton pattern)."""
    global _search_session
    if _search_session is None:
        session = requests.Session()
        retry_strategy = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(pool_connections=_SEARCH_POOL_CONNECTIONS, pool_maxsize=_SEARCH_POOL_MAXSIZE, max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _search_session = session
    return _search_session
```

Update `searxng.py` and `google.py` to use `get_session()` instead of `requests.get()`.

**Note:** DuckDuckGo uses context manager pattern from `duckduckgo_search` library — leave as-is.

---

### 3.2 Duplicate Detection Memory Optimization

**Source:** plan4.md Priority 2
**Files:** `services/article.py`
**Status:** NOT YET DONE — hardcoded limit(1000) at line 307

**Current code:**
```python
.limit(1000)
```

**Fix:**
```python
DUPLICATE_DETECTION_LIMIT = int(os.environ.get("DUPLICATE_DETECTION_LIMIT", "100"))
# ...
.limit(DUPLICATE_DETECTION_LIMIT)
```

The function already breaks on first match (line 314), so reducing from 1000 to 100 is safe.

---

### 3.3 Add Index on `Article.updated_at`

**Source:** plan2.md Priority 3
**Files:** `models.py`, new migration
**Status:** NOT YET DONE

**Fix:** Add `index=True` to `updated_at` column in `models.py:128-131`, create migration.

---

### 3.4 Newsletter Dead Letter Retry Task

**Source:** plan5.md Item 3
**Files:** `tasks/newsletter.py`

**Implementation:**
1. Create `retry_failed_newsletter_deliveries` Celery task
2. Runs every 2 hours via Celery Beat
3. Queries `Newsletter` where `delivered_count < recipients AND error_message IS NOT NULL`
4. Uses same retry logic as `send_single_email` (autoretry_for/dont_autoretry_for)

**Pattern to follow:** `send_single_email` task at `tasks/newsletter.py`

---

### 3.5 Split Trend Memory Consolidation

**Source:** plan5.md Item 4
**Files:** `services/trend_memory.py`, `config.py`

**Implementation:**
1. Split `consolidate_trend_memory` into two tasks:
   - `consolidate_trend_memory` — promotes LOW to MEDIUM
   - `purge_trend_memory` — deletes expired entries
2. Stagger execution by 30 minutes in Celery Beat

---

## Wave 4: Agent Harness Improvements

### 4.1 Enable Tool-Calling in Research/Edit Stages

**Source:** plan6.md Item 1
**Files:** `services/subagent.py`, `schemas/pipeline.py`, `tasks/research.py`, `tasks/edit.py`

**What's needed:**
1. `resolve_subagent_config()` doesn't pass `tools` field through (see `schemas/pipeline.py:184-203`)
2. Add helper functions in `subagent.py`:
   - `get_tool_definition(name: str) -> ToolDefinition | None`
   - `get_tools_by_names(names: list[str]) -> list[ToolDefinition]`
   - `provider_supports_tools(provider) -> bool`
3. Update `run_subagent_with_tools()` to fallback gracefully when provider doesn't support tools

**Current issue:** `resolve_subagent_config()` builds kwargs but omits `tools` field entirely.

---

### 4.2 Multi-Provider Fallback Chain

**Source:** plan6.md Item 2
**Files:** `services/llm/__init__.py`, `tasks/pipeline.py`

**Current behavior:** Only triggers on circuit breaker OPEN state.

**Errors that should trigger fallback (but don't):**
| Error | Rationale |
|-------|----------|
| `RateLimitError` | Another provider may have capacity |
| `ProviderTimeoutError` | Transient, try again |
| `ProviderServerError` | Another provider may work |
| `ConnectionError` | Network issue |

**Fatal errors (don't catch):**
| Error | Rationale |
|-------|----------|
| `AuthError` | Invalid API key - all providers fail |
| `CircuitOpenError` | All circuits open - wait for recovery |

**Implementation:** Add `get_provider_chain()` function that returns ordered list of (provider, model, max_tokens, provider_id), filter out open circuits, iterate through chain on recoverable errors.

---

### 4.3 Context Injection in Research/Write Stages

**Source:** plan6.md Item 3
**Files:** `services/researcher.py`, `services/writer.py`, `tasks/research.py`, `tasks/write.py`

**Current state:**
- Research: NO topic notes
- Write: NO related articles or trend memory
- Edit: HAS topic notes and trend memory

**What's needed:**
1. In `tasks/research.py` — fetch and pass topic notes to prompt
2. In `services/researcher.py` — add `topic_notes` parameter to prompt builder
3. In `tasks/write.py` — fetch related articles and trend memory
4. In `services/writer.py` — add `related_articles`, `trend_memory` parameters

---

### 4.4 Quality Gates Per Stage

**Source:** plan6.md Item 4
**Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`

**Implementation:**
1. **Select stage:** Check text preview length < 100 chars → skip
2. **Research stage:** Web search returns no results → route to REVIEW
3. **Write stage:** Impact score < 30 → route to REVIEW

---

### 4.5 Add Type Hints to Admin Routes

**Source:** plan2.md Priority 2
**Files:** ~35 route handlers in `routes/admin/*.py`

**Affected routes:** Add `-> Response` return type to all admin route handlers.

---

## Wave 5: Security Hardening

### 5.1 Secret Rotation Support

**Source:** plan3.md Section 1
**Files:** `config.py`, `services/task_security.py`, `services/webhooks.py`

**Components:**
1. **Flask `SECRET_KEY_FALLBACKS`** — add `SECRET_KEY_PREVIOUS_1`, `SECRET_KEY_PREVIOUS_2` env vars
2. **Celery task secret rotation** — support multiple secrets via `_get_task_secrets()` in `task_security.py`
3. **Webhook key versioning** — support `v1:` / `v2:` prefix in `services/webhooks.py`
4. **Documentation** — update `docs/security.md` with rotation procedures

---

### 5.2 Audit Logging Expansion

**Source:** plan3.md Section 2
**Files:** `models.py`, migrations, `routes/admin/subscribers.py`, `routes/admin/api/articles.py`

**Components:**
1. Add `category` column to `AuditLog` model
2. Audit subscriber CSV export
3. Audit bulk operations
4. GDPR considerations (log IDs not emails)

---

### 5.3 Request Size Limits Enhancement

**Source:** plan3.md Section 3
**Files:** `routes/admin/api/articles.py`

**Add `@limit_content_length(65536)` to bulk article endpoint.**

---

## Wave 6: UI/UX Improvements

### 6.1 Search Clear Button

**Source:** plan7.md Item 1
**Files:** `templates/partials/feed.html`, `static/css/articles.css`, `static/js/app.js`

**Implementation:**
1. Add `<button type="button" class="search-clear" aria-label="Clear search">&times;</button>` after search input
2. Add CSS for positioning and display logic (show when input has value)
3. Add JavaScript to clear input and trigger HTMX refresh

---

### 6.2 Base Font Size Increase (14px → 15px)

**Source:** plan7.md Item 2
**Files:** `static/css/variables.css`

**Change `--text-base` from `0.875rem` to `0.9375rem` (15px).**

---

### 6.3 Date Format Clarity

**Source:** plan7.md Item 3
**Files:** `services/date_utils.py` (create), `templates/partials/article_card.html`

**Implementation:** Create Jinja2 filter for hybrid date display:
- < 24 hours: "X hours ago" / "yesterday"
- < 7 days: "X days ago"
- < 1 year: "MMM d"
- Previous year: "MMM d, YYYY"

---

### 6.4 Remaining UX Items

**Source:** plan7.md Items 4-7
**Files:** `templates/partials/feed.html`, `static/css/articles.css`, `static/js/app.js`, `templates/admin/dashboard.html`

| Item | Fix |
|------|-----|
| Filter tab ARIA | Add `aria-controls="feed"` to filter tabs |
| Pagination improvements | Add `aria-controls="feed"` and `aria-live="polite"` to scroll sentinel |
| Keyboard shortcut visibility | Ensure `<kbd>/</kbd>` is visible |
| Loading state feedback | Add toast after trigger crawl |

---

## Wave 7: Architecture & Infrastructure

### 7.1 Enforce Pipeline State Machine Validation

**Source:** plan5.md Item 5
**Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `services/pipeline_failure.py`, `services/pipeline_degradation.py`

**Problem:** Direct `pipeline_status = X` assignment bypasses `_transition_article_status()` validation.

**Fix:** Replace direct assignments with `_transition_article_status(article, PipelineStatus.X)` in:
- `tasks/select.py` (lines 85, 110)
- `tasks/research.py` (lines 53, 136)
- `tasks/write.py` (line 63)
- `tasks/edit.py` (lines 142, 163, 190)
- `services/pipeline_failure.py` (lines 78, 101, 134)
- `services/pipeline_degradation.py` (multiple locations)

**Note:** Test files are intentionally excluded (they mock state).

---

### 7.2 Docker Compose for Development

**Source:** plan5.md Item 2
**Files:** `docker-compose.yml`, `.env.docker` (template)

**Services:** redis, web, worker, beat, (optional) flower
**Key configs:** Health checks, `worker_prefetch_multiplier=1`, persistent volumes.

---

### 7.3 CI/CD Pipeline Setup

**Source:** plan5.md Item 6
**Files:** `.github/workflows/ci.yml`, `.github/workflows/cd.yml`

**ci.yml:** Ruff lint, pytest, type check on PR
**cd.yml:** Build Docker, push to registry, deploy on push to main

---

### 7.4 Beat Schedule Reload Endpoint

**Source:** plan9.md Code Issue #2
**Files:** `routes/admin/api.py`

**Problem:** `POST /admin/api/config/reload` doesn't call `Config.reload_beat_schedule()`.

**Fix:** Either add dedicated `POST /admin/api/config/beat/reload` endpoint, or integrate into existing reload endpoint.

---

### 7.5 `traced_stage()` Integration

**Source:** plan9.md Code Issue #3
**Files:** `services/logging_utils.py`, `tasks/pipeline.py`

**Problem:** `traced_stage()` is defined but never called.

**Fix:** Wire into `run_stage()` in `tasks/pipeline.py`, or mark as deprecated.

---

### 7.6 Make `TITLE_SIMILARITY_THRESHOLD` Configurable

**Source:** plan9.md Code Issue #4
**Files:** `constants.py`, `services/config_utils.py`

**Problem:** Hardcoded in `constants.py`, should use `get_config_with_default()` pattern.

---

## Wave 8: Advanced Agent Features

### 8.1 Feedback Loop from Published Articles

**Source:** plan6.md Item 5
**Files:** `models.py`, `services/newsletter.py`, `routes/public/links.py`, `services/trend_memory.py`

**Phase 1 — Tracking:**
1. Add `newsletter_clicks` column to `ArticleMetric`
2. Create tracking endpoint `/track/newsletter-click/<int:article_id>`
3. Use trackable URLs in newsletter

**Phase 2 — Feedback Integration:**
1. Enhance `propose_trend_memory()` to include engagement
2. Create `recalculate_impact_scores` nightly task

---

### 8.2 Confidence Scoring in Responses

**Source:** plan6.md Item 6
**Files:** `schemas/llm_responses.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`

**Implementation:**
1. Add `confidence: str = Field(default="medium", pattern="^(low|medium|high)$"` to `SelectionResult`
2. Update prompts to request confidence field
3. Route low-confidence selections to REVIEW instead of automatically advancing

---

### 8.3 Trend Memory SQL Consolidation

**Source:** plan6.md Item 8
**Files:** `services/trend_memory.py`

**Replace Python loop with SQL UPDATE in `consolidate_topic()`.**

---

### 8.4 A/B Testing for Prompts

**Source:** plan6.md Item 9
**Files:** `pipeline.yaml`, `models.py`, `tasks/select.py`, `routes/admin/api.py`

**Implementation:**
1. Add `experiments` config in `pipeline.yaml`
2. Add `experiment_group` column to `Article` model
3. Assign variant in select stage
4. Track results for comparison

---

### 8.5 Context Window Optimization

**Source:** plan6.md Item 10
**Files:** `services/prompts.py`, `services/writer.py`, `services/editor.py`

**Implementation:** Add sliding window truncate helper:
```python
def sliding_window_truncate(text: str, max_chars: int = 8000, ellipsis: str = "\n\n[... truncated ...]\n\n") -> str:
    if not text or len(text) <= max_chars:
        return text
    half = (max_chars - len(ellipsis)) // 2
    return text[:half] + ellipsis + text[-half:]
```

Apply to `research_brief` in write stage and draft in edit stage.

---

## Wave 9: Documentation

### 9.1 Critical Metric Naming Fixes

**Source:** plan9.md Section: Metric Naming Discrepancies
**Files:** `docs/monitoring.md`

**Fix these critical errors that cause monitoring to silently fail:**
| Docs Show | Code Emits |
|----------|------------|
| `circuit_breaker_state_change` | `circuit_breaker.state_change` |
| `pipeline_stage_duration_seconds` | `pipeline.stage_duration_seconds` |

Also add documentation for `pipeline_sla_seconds` histogram.

---

### 9.2 New Documentation Files

**Source:** plan9.md

| File | Contents |
|------|----------|
| `docs/pipeline.md` | State machine diagram, degradation system, retry budget, per-stage failure tracking, duplicate detection |
| `docs/operations.md` | All 9 Celery Beat tasks, dead letter queue, config cache reload, task HMAC signing, distributed lock pattern |
| `docs/webhooks.md` | All 7 API endpoints, event types, encryption at rest, trigger integration, idempotency |
| `docs/analytics.md` | Search analytics endpoint, topic notes CRUD, subscriber export, pipeline SLA endpoint |

---

### 9.3 Documentation Fixes

**Source:** plan9.md

| File | Fix |
|------|-----|
| `docs/api.md` | Add missing endpoints, workflow context, error examples |
| `docs/fallback-providers.md` | Fix outdated API format, document all providers |
| `docs/development.md` | Correct pipeline flow, add env vars reference, add LLM provider docs |
| `docs/runbook.md` | Add missing admin endpoints |
| `docs/configuration.md` | Add Celery Beat schedule section |
| `docs/components/badge.md` | Remove `.confidence-label` (not in CSS) |

---

### 9.4 Shares Toggle Logic Review

**Source:** plan9.md Code Issue #7
**Files:** `routes/admin/shares.py`

**Problem:** POST handler exists but actual toggle logic (read current state, flip it) may not be implemented.

**Action:** Verify toggle works correctly or implement missing logic.

---

### 9.5 AGENTS.md Task Count Correction

**Source:** plan9.md Code Issue #5
**Files:** `AGENTS.md`

**Fix:** Count is 8 but should be 9 — `consolidate-trend-memory` is missing from the count.

---

## Items Verified as Correct (No Action Needed)

These items were investigated and require no changes:

| Item | Source | Finding |
|------|--------|---------|
| `tasks/edit.py:300` commit | plan2.md | Already has try/except with rollback |
| `services/subagent.py:1029` silent except | plan2.md | Intentional — returns False appropriately |
| `retry_stuck` / `publish_scheduled` autoretry | plan2.md | Fail-closed is correct design |
| Lock release pattern | plan2.md | Uses atomic `release_lock` from redis_utils |
| `services/trend_memory.py` unbounded loading | plan2.md | Self-bounded by TTLs |
| ResponseCache L1/L2 | plan4.md | Excellent 2-tier caching with stampede protection |
| Eager loading | plan4.md | Consistent joinedload usage |
| ThreadPoolExecutor usage | plan4.md | Proper non-blocking I/O |
| Streaming CSV export | plan4.md | Uses yield_per(500) |
| Database indexes | plan4.md | All critical indexes in place |

---

## Deferred Items (Do Not Implement Without Explicit Direction)

| Item | Source | Reason |
|------|--------|--------|
| Newsletter subagent chain | plan5.md | Lower priority |
| Trend memory admin UI | plan5.md | Nice-to-have |
| Public API rate limiting | plan5.md | AGENTS.md says don't add |
| Pagination cursor-based | plan4.md | Works for current scale |
| Global LLM circuit breaker | plan4.md | Per-provider sufficient |
| Batch duplicate detection | plan4.md | Option A sufficient |
| Redis pool segregation | plan4.md | Hasn't hit limits |
| CSS minification | plan4.md | CDN handles gzip |
| Announcement banner | plan4.md | Only if needed |
| Tool expansion/validation | plan6.md | Low ROI |
| Admin route fragmentation | plan5.md | Current split acceptable |
| docs/api.md missing endpoints | plan5.md | Lower priority |
| Tool registry auto-init | plan6.md | Optional |
| Input/output token separation | plan6.md | Requires provider changes |
| Provider logprobs confidence | plan6.md | Complex, not universal |
| Ollama tool-calling | plan6.md | Not all models support |
| Full editor with tools | plan6.md | Higher effort |
| Persistent DuckDuckGo instance | plan4.md | Rate limits make pooling less impactful |

---

## Testing Requirements

### Before any changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After each wave:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Rollback Methods

| Change | Rollback Method |
|--------|----------------|
| Precompiled regex | Remove constants, revert to inline `re.search()` |
| Type hints | Remove `-> Response` annotations |
| Database index | `flask db downgrade` |
| Logging additions | Revert logger calls |
| Session pooling | Remove session import, revert to `requests.get()` |
| Duplicate limit | Revert to `limit(1000)` |
| Subagent workers | Remove env var, revert to `max_workers=8` |
| Cost pricing | Remove pricing entries |
| State machine | Revert to direct assignment |
| Docker Compose | Remove docker-compose.yml |
| CI/CD pipeline | Remove .github/workflows/ |

---

## Dependencies Summary

| Wave | Items | Key Dependencies |
|------|-------|-----------------|
| 1 | 1.1-1.4 | Independent |
| 2 | 2.1-2.2 | Wave 1 recommended first |
| 3 | 3.1-3.5 | Independent |
| 4 | 4.1-4.5 | Wave 3 for provider chain |
| 5 | 5.1-5.3 | Wave 4 for context injection |
| 6 | 6.1-6.4 | Independent |
| 7 | 7.1-7.6 | Independent |
| 8 | 8.1-8.5 | Wave 4 base features |
| 9 | 9.1-9.5 | Can run in parallel with any wave |

---

## Parallelization Strategy for Sub-Agents

**Sub-agents can implement items in parallel within each wave:**

- **Wave 1:** 4 independent items → 4 sub-agents
- **Wave 2:** 2 items → 2 sub-agents
- **Wave 3:** 5 items → 3-5 sub-agents (session pooling needs its own, rest can parallelize)
- **Wave 4:** 4 items with dependencies → suggest sequential or 2 parallel (4.1→4.2 chain)
- **Wave 5:** 3 items → 3 sub-agents
- **Wave 6:** 4 UX items → 4 sub-agents
- **Wave 7:** 6 items → 4-6 sub-agents
- **Wave 8:** 5 items with dependencies → suggest sequential or 2 parallel
- **Wave 9:** Documentation only → 1-2 sub-agents

**Recommended sub-agent assignments:**
1. **Performance sub-agent:** Wave 1 (1.1, 1.2, 1.3, 1.4), Wave 3 (3.1, 3.2, 3.3)
2. **Testing sub-agent:** Wave 2 (2.1, 2.2)
3. **Agent sub-agent:** Wave 4 (4.1-4.5), Wave 8 (8.1-8.5)
4. **Security sub-agent:** Wave 5 (5.1-5.3)
5. **UX sub-agent:** Wave 6 (6.1-6.4)
6. **Infra sub-agent:** Wave 7 (7.1-7.6)
7. **Docs sub-agent:** Wave 9 (9.1-9.5)

---

*Consolidated April 25, 2026*

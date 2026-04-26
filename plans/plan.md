# Consolidated Implementation Plan

**Created:** April 26, 2026
**Status:** PLANNING
**Source:** plan2.md, plan3.md, plan4.md, plan5.md, plan6.md, plan7.md, plan8.md, plan9.md

---

## Overview

This plan consolidates all identified issues from the codebase review into a parallelized implementation strategy. Items are organized into 9 waves that can be executed in parallel where dependencies allow.

**Verified items:** All items in this plan have been verified against current code. The plan reflects the actual state of the codebase as of April 26, 2026.

---

## Deferred Items (Do Not Implement Without Explicit Direction)

| Item | Reason |
|------|--------|
| Newsletter subagent chain | Lower priority |
| Public API rate limiting | AGENTS.md says don't add `@limiter.limit()` |
| Pagination cursor-based | Works for current scale |
| Global LLM circuit breaker | Per-provider sufficient |
| Batch duplicate detection | Current approach sufficient |
| Redis pool segregation | Hasn't hit limits |
| CSS minification | CDN handles gzip |
| Announcement banner | Only if needed |
| Tool expansion/validation | Low ROI |
| Admin route fragmentation | Current split acceptable |
| Tool registry auto-init | Optional |
| Input/output token separation | Requires provider changes |
| Provider logprobs confidence | Complex, not universal |
| Ollama tool-calling | Not all models support |
| Full editor with tools | Higher effort |
| Persistent DuckDuckGo instance | Rate limits make pooling less impactful |
| Search highlighting | Significant architectural change (FTS5) |
| Keyboard navigation ARIA feed | Complex, low signal |
| Reader counts display | Simple but low signal |
| Beat task last-run display | Nice to have |
| Theme toggle keyboard shortcut | Minor convenience |
| Newsletter dry-run styling | Minor |
| Create contrib/ainews.nginx | Medium effort, lower priority |
| Docker healthchecks | Low priority |

---

## Implementation Waves

### WAVE 1: Independent Critical Fixes (No Cross-Dependencies)

These can be implemented in parallel by separate agents.

#### wave1_1: Wrong field reference in pipeline stats API
- **File:** `routes/admin/api/pipeline.py:130`
- **Bug:** `s.last_error.isoformat()` used where `s.disabled_at.isoformat()` should be
- **Fix:**
  ```python
  "disabled_at": s.disabled_at.isoformat() if s.disabled_at else None,
  ```

#### wave1_2: Invalid state transition + silent failure in extract task
- **File:** `tasks/extract.py:182-186`
- **Bug:** Direct `pipeline_status = "failed"` bypasses state machine; also does NOT track failure properly
- **Fix:** Remove direct status assignment, let exception propagate so Celery retries naturally. Use rollback instead of commit.

#### wave1_3: health_check function indentation bug
- **File:** `services/search/google.py:81-104`
- **Bug:** `health_check` defined at module level instead of inside `GoogleSearchProvider` class
- **Fix:** Indent entire `health_check` function body by 4 spaces to become a method of the class

#### wave1_4: Remove ast.Call from condition evaluator (SECURITY)
- **File:** `services/subagent.py:1025-1029`
- **Bug:** `ast.Call` handler allows arbitrary function execution in conditions
- **Fix:** Remove the `elif isinstance(node, ast.Call)` block entirely

#### wave1_5: Narrow safe_href exception handling
- **File:** `app.py:237-252`
- **Bug:** `except Exception` too broad — catches unrelated errors
- **Fix:** Change to `except (UnsafeURLError, ValueError) as e:`

#### wave1_6: Add missing entries to .dockerignore
- **File:** `.dockerignore`
- **Fix:** Add `.ruff_cache/`, `tests/`, `plans/`, `dump.rdb`, `.DS_Store`, `*.log`

#### wave1_7: Dead letters table missing columns
- **File:** `templates/admin/dead_letters.html:63-76`
- **Bug:** tbody only renders 6 columns, missing status and error
- **Fix:** Add `<td>{{ pipeline_badge(article.pipeline_status) }}</td>` and `<td>{{ article.last_error|e if article.last_error else '—' }}</td>`

---

### WAVE 2: State Machine and Validation Fixes

#### wave2_1: Add REVIEW to PENDING valid transitions
- **File:** `constants.py:41`
- **Bug:** PENDING→REVIEW was invalid, but `tasks/select.py:89` calls it
- **Fix:**
  ```python
  PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
  ```

#### wave2_2: Add rollback handling in _create_article_record
- **File:** `tasks/extract.py:150`
- **Bug:** Unguarded `db.session.commit()`
- **Fix:** Wrap in try/except with rollback on SQLAlchemyError

#### wave2_3: Use _transition_article_status() in set_status action
- **File:** `routes/admin/api/articles.py:243-280`
- **Bug:** Direct assignment bypasses state machine; no VALID_TRANSITIONS check
- **Fix:** Add transition validation before assignment; use `_transition_article_status()` semantics

#### wave2_4: Add rollback to SoftTimeLimitExceeded blocks in cleanup tasks
- **File:** `tasks/cleanup.py`
- **Affected:** `consolidate_trend_memory` (lines 137-139), `purge_trend_memory` (lines 213-215)
- **Fix:** Add `db.session.rollback()` before re-raising in both except blocks

#### wave2_5: Return False on SQLAlchemyError in trigger_webhook
- **File:** `services/webhooks.py:276-284`
- **Bug:** Falls through to return prior success value after rollback
- **Fix:** After rollback on SQLAlchemyError, return `False, f"Database error: {e}"`

#### wave2_6: Use yield_per(500) for subscriber queries
- **File:** `tasks/newsletter.py:507` and `tasks/newsletter.py:513-520`
- **Bug:** `.all()` loads all subscribers into memory — OOM risk
- **Fix:** Change to `.yield_per(500)` for streaming batches

---

### WAVE 3: Subagent and LLM Provider Fixes

#### wave3_1: Fix initialize_tool_registry() signature mismatch
- **File:** `services/subagent.py:328-333`
- **Bug:** Function takes no args but callers pass `stage_config.tools`
- **Fix:** Modify to accept `tool_names: list[str] | None = None`, filter tools, return list
- **Also fix:** Update callers in `tasks/edit.py:108` and `tasks/research.py:106`

#### wave3_2: Add error handling to tool functions
- **File:** `services/subagent.py:43-177`
- **Bug:** All 7 tool functions have no error handling for DB/Redis failures
- **Fix:** Add try/except to each function — catch SQLAlchemyError and RedisError, return human-readable error strings, log at warning level

#### wave3_3: Add AuthError to provider fallback tuple
- **File:** `tasks/pipeline.py:188`
- **Bug:** AuthError not in exception tuple that triggers fallback
- **Fix:** Add `AuthError` to the tuple

#### wave3_4: Retry loop in run_subagent_chain iterates providers
- **File:** `services/subagent.py:868-878` (context: lines 867-933)
- **Bug:** Retry loop retries same provider, doesn't try fallback providers
- **Fix:** Move `_get_subagent_provider_and_config()` inside attempt loop so each retry picks fresh provider

#### wave3_5: Fix retry backoff formula
- **File:** `services/subagent.py:512`
- **Bug:** Uses `2 ** (attempt - 1)` instead of `2 ** attempt`
- **Fix:** Change to `2 ** attempt`

#### wave3_6: Add `previous` to `_ALLOWED_NAMES`
- **File:** `services/subagent.py:966`
- **Bug:** Chain conditions use `previous` but it's not in allowed names
- **Fix:** Add `"previous"` to `_ALLOWED_NAMES`

#### wave3_7: Fix single-brace template variable detection
- **File:** `services/subagent.py:1050`
- **Bug:** Only checks for `{{` not `{`
- **Fix:** Change `"{" in value` (currently checks `{{`)

---

### WAVE 4: Search and Circuit Breaker Fixes

#### wave4_1: DuckDuckGo SSRF validation on result URLs
- **File:** `services/search/duckduckgo.py:16-29`
- **Bug:** No SSRF validation on result URLs
- **Fix:** Validate each result URL with `validate_url_safe()` before returning

#### wave4_2: Make `_LLM_FAILURE_THRESHOLD` configurable
- **File:** `services/llm/__init__.py:18`
- **Bug:** Hardcoded to 5
- **Fix:** `int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))`

#### wave4_3: Add _record_success/failure to BaseLLMProvider
- **File:** `services/llm/base.py`
- **Bug:** Circuit breaker tracking gaps in retry loop and chat_with_tools
- **Fix:** Add `_record_success()` and `_record_failure()` methods; call at end of successful/failed LLM calls

#### wave4_4: Add search circuit breaker helpers
- **File:** `services/search/__init__.py`
- **Bug:** Search providers don't record failures for circuit breaker
- **Fix:** Add `record_search_success()` and `record_search_failure()` helpers; update each search provider's `search()` method

#### wave4_5: Change retry_backoff=30 to retry_backoff=True
- **Files:** `tasks/select.py:24`, `tasks/write.py:41`, `tasks/research.py:54`, `tasks/edit.py:354`
- **Bug:** `retry_backoff=30` is fixed 30s delay, not exponential backoff
- **Fix:** Change all four to `retry_backoff=True`

#### wave4_6: Add socket-level timeouts and connection pooling to RSS adapter
- **File:** `adapters/rss.py:22`
- **Bug:** No socket-level `connect` or `read` timeouts
- **Fix:** Add `connect_timeout=2`, `read_timeout=DEFAULT_LLM_TIMEOUT_SECONDS`, `pool_connections=5`, `pool_maxsize=10`

#### wave4_7: Add HTTPAdapter with connection pooling to API and Web adapters
- **Files:** `adapters/api.py`, `adapters/web.py`
- **Bug:** Raw `requests.Session()` without connection pooling
- **Fix:** Add `get_crawl_session()` helper with `HTTPAdapter` pooling; use singleton pattern

---

### WAVE 5: Performance and Cache Fixes

#### wave5_1: Replace blpop polling with direct cache key check
- **File:** `services/cache.py:141-158`
- **Bug:** blpop return value not used to verify cache data readiness
- **Fix:** Replace blpop polling with bounded polling loop that checks actual cache key existence

#### wave5_2: Add joinedload for source in metrics queries
- **File:** `routes/admin/metrics.py:33-68`
- **Bug:** N+1 query potential when template accesses `article.source`
- **Fix:** Add `.options(joinedload(Article.source))` to `top_by_views`, `top_by_shares`, `top_by_link_views`

#### wave5_3: Clear stage failure Redis keys on reprocess
- **Files:** `routes/admin/api/articles.py` (_bulk_reprocess), `routes/admin/articles.py` (reprocess_article)
- **Bug:** Redis keys not cleared on reprocess — causes early termination
- **Fix:** Delete `ainews:article:stage_failures:{article_id}:*` keys when reprocessing

#### wave5_4: Invalidate pub:related:* cache in bulk operations
- **File:** `routes/admin/api/articles.py`
- **Bug:** Related articles cache never invalidated on article mutations
- **Fix:** Add `cache.invalidate_prefix("pub:related")` to all bulk operation cache invalidation blocks

#### wave5_5: Call _evict_stale() in get() miss path
- **File:** `services/cache.py:52-58`
- **Bug:** LRU eviction only on set(), not on get() miss path
- **Fix:** Call `_evict_stale()` at start of `get()` method

#### wave5_6: Add autoretry to aggregate_crawl_results
- **File:** `tasks/crawl.py:207-240`
- **Bug:** No autoretry_for on chord callback
- **Fix:** Add `autoretry_for=(ConnectionError, TimeoutError)` and `retry_backoff=True`; increase max_retries to 3

#### wave5_7: Add autoretry to retry_stuck task
- **File:** `tasks/retry.py:43-50`
- **Bug:** No autoretry_for on retry_stuck
- **Fix:** Add `autoretry_for=(ConnectionError, TimeoutError)` and `retry_backoff=True`

#### wave5_8: Add max_retries to cleanup_stale_limiter_slots
- **File:** `tasks/cleanup.py:94-111`
- **Bug:** No max_retries setting
- **Fix:** Add `max_retries=3`

---

### WAVE 6: UI/UX Improvements

#### wave6_1: Add sort parameter to get_articles_paginated()
- **Files:** `services/article.py`, `routes/public/feeds.py`
- **Bug:** No sort capability; hardcoded `.order_by(Article.created_at.desc())`
- **Fix:** Add `_get_sort_order()` helper and `sort` param; update routes to accept sort query param; update cache keys

#### wave6_2: Add date_from and date_to inputs to admin articles page
- **File:** `templates/admin/articles.html`
- **Bug:** Route accepts date params but UI has no inputs
- **Fix:** Add date range inputs; update all hx-include attributes to include date filters

#### wave6_3: Fix pagination to pass all filter params
- **File:** `templates/admin/partials/articles_table.html:70`
- **Bug:** Pagination missing date_from, date_to, impact_min, impact_max, tag_slug
- **Fix:** Update pagination_nav call to include all filter parameters

#### wave6_4: Add sort dropdown to public feed
- **File:** `templates/partials/feed.html`
- **Fix:** Add sort dropdown with HTMX for recent/impact/published options; add CSS

#### wave6_5: Add "Select all matching" checkbox and endpoint
- **Files:** `templates/admin/partials/articles_table.html`, `routes/admin/api/articles.py`
- **Fix:** Add checkbox that fetches all matching IDs via API; add `/api/articles/ids` endpoint

#### wave6_6: Add hx-push-url to search and fix impact filter triggers
- **File:** `templates/admin/articles.html`
- **Fix:** Add `hx-push-url="true"` to search input; fix impact filters to use `input changed delay:500ms, change`

#### wave6_7: Make "What To Watch" collapsible
- **File:** `templates/partials/condensed_article.html`
- **Fix:** Wrap in `<details>/<summary>` pattern; add CSS for disclosure widget

#### wave6_8: Improve "View Original" link and limit tags to 3
- **File:** `templates/partials/article_card.html`
- **Fix:** Make View Original link more visible with inline-flex style; limit tags to 3 with "+N more" pattern; add CSS

#### wave6_9: Remove aria-haspopup from share button summary
- **File:** `templates/partials/share_macro.html`
- **Fix:** Remove `aria-haspopup="true"` from summary element

---

### WAVE 7: Documentation Files (Can Be Parallelized)

#### wave7_1: Create docs/subagent.md
- Document subagent system: tool registry (9 tools), chain execution, configuration reference, failure scenarios, known bugs

#### wave7_2: Create docs/trend-memory.md
- Document trend memory system: importance tiers, memory lifecycle, consolidation algorithm, admin endpoints, known bugs

#### wave7_3: Create docs/search-providers.md
- Document search provider system: BaseSearchProvider interface, provider comparison, SSRF validation, known bugs

#### wave7_4: Create docs/context-service.md
- Document context service: TopicNote model, CRUD operations, related articles algorithm, caching, known bugs

#### wave7_5: Create docs/pipeline-failure-tracking.md
- Document pipeline failure tracking: Redis key structure, decision tree, stage degradation, known bugs

#### wave7_6: Create docs/newsletter-pipeline.md
- Document newsletter generation: orchestrator flow, 3-stage pipeline, delivery tracking, known bugs

#### wave7_7: Create docs/cost-tracking.md
- Document LLM cost tracking: token counting, blended rate formula, default rates, shortcomings

---

### WAVE 8: Deployment Script Improvements

#### wave8_1: scripts/install.sh improvements
- Replace hardcoded REPO_URL with `${REPO_URL:-}`
- Add `-d|--dir` argument for APP_DIR override
- Add `--pull-ollama-model` flag
- Improve end-of-run messaging

#### wave8_2: scripts/deploy.sh improvements
- Add `unset GIT_DIR GIT_WORK_TREE ...`
- Add detached HEAD check
- Improve .git directory validation

#### wave8_3: Fix docs/deployment.md Docker Nginx example
- Fix path routing bug (location /static/ should use alias not proxy_pass)

#### wave8_4: docker-compose.yml healthchecks
- Add healthcheck for celery-worker and celery-beat using redis-cli ping

#### wave8_5: .env.example ADMIN_PASSWORD instruction
- Add inline instruction for hashing with hash_password.py

---

### WAVE 9: PWA and Additional UI

#### wave9_1: Create static/manifest.json
- PWA manifest with name, icons, theme colors

#### wave9_2: Create static/js/service-worker.js
- Service worker with cache-first strategy and offline fallback

#### wave9_3: Add manifest link and service worker registration
- Update templates/base.html and static/js/app.js

#### wave9_4: Add reading_time calculation to article_detail
- **File:** `routes/public/links.py`
- **Fix:** Calculate `word_count // 200` and pass to template

#### wave9_5: Display reading_time in condensed_article template
- **File:** `templates/partials/condensed_article.html`
- **Fix:** Add reading time display with meta separator

#### wave9_6: Add WebhookEvent payload column and resend endpoint
- **Files:** New migration, models.py, services/webhooks.py, routes/admin/api/webhooks.py
- **Fix:** Store event_data as payload; add resend endpoint for failed events

#### wave9_7: Add pagination to dead letters queries
- **File:** `routes/admin/dashboard.py`
- **Fix:** Add failed_page and stuck_page params; query with offset/limit

---

## Implementation Order Summary

### Wave 1 → Wave 9 (Dependencies allow interleaving)

**Independent groups within each wave** can be parallelized:
- Wave 1 items are fully independent — assign to separate agents
- Wave 2-6 items have internal ordering where noted
- Wave 7 (docs) can be created in parallel by separate agents
- Wave 8 (scripts) items are independent
- Wave 9 (PWA) items are independent

### Key Dependencies:
- wave3_1 (initialize_tool_registry fix) must complete before wave7_1 (subagent.md docs) can accurately document
- wave4_1 (DuckDuckGo SSRF) should complete before wave7_3 (search-providers.md) documents SSRF validation
- wave1_3 (Google health_check indent) is a prerequisite for wave4_4 (search circuit breaker)

---

## Test Coverage Gaps to Address

| Issue | Missing Test |
|-------|--------------|
| pipeline.py:130 wrong field | Test with non-empty last_error on source |
| webhooks.py:276 rollback | Test DB commit failure propagation |
| newsletter.py:507 yield_per | Test with large subscriber count (mock) |
| google.py health_check | Test method call on provider instance |
| subagent.py ast.Call removal | Test function calls in conditions raise ValueError |
| cleanup.py rollback | Test rollback called on SoftTimeLimitExceeded |
| state machine validation | Test InvalidStateTransitionError for invalid transitions |
| set_status bypass | Test PENDING→DONE returns 400 |

---

## Notes

- **Subagent chain template resolution result:** The verification showed this item is INACCURATE — the result IS used via `prompt_data_escaped` in the `.format()` call. Do not implement this fix.
- **Existing plan.md items marked COMPLETED:** These were from prior implementation and are already done. Do not re-implement.
- **Defer indefinitely items:** Listed in Deferred Items section above.

---

*Consolidated and verified April 26, 2026*
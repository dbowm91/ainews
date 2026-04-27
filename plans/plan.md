# Consolidated Implementation Plan

**Date:** April 27, 2026
**Status:** PENDING — Not yet implemented

---

## Overview

This plan consolidates items from plan2-8 plus existing plan.md deferred/removed items. All items have been verified against the codebase. Items marked IMPLEMENTED are already done; NOT_IMPLEMENTED items are pending.

**Total verified items:** 38 pending action items across 4 waves.

---

## Wave Structure (Parallelization Opportunities)

### Wave A — Independent Hot Fixes (Can run in parallel)
- A1: Import sorting (ruff --fix)
- A2: DeepSeek cost rate correction + missing model pricing
- A3: Add debug logging to 3 silent exception blocks
- A4: Remove console.log from app.js

### Wave B — Security & Share Fixes (Can run in parallel, separate files)
- B1: CSP missing directives (connect-src, object-src, base-uri, form-action)
- B2: safe_href filter in share templates
- B3: ShareConfig validation on save
- B4: Merge share-a11y.js into app.js

### Wave C — Performance Fixes (Can run in parallel, separate files)
- C1: Fix uncached related articles query
- C2: Fix O(n) cache eviction (remove _evict_stale sampling)
- C3: Add date prefilter (30-day window) to related articles
- C4: Add Source health indexes (migration + model)

### Wave D — Pipeline & Webhook Fixes (Can run in parallel, separate files)
- D1: Always route degraded content to review (> 0 instead of >= 2)
- D2: Fire article.failed webhook event
- D3: Fire newsletter.failed webhook event
- D4: Add stage label to LLM metrics (llm.calls, llm.tokens)
- D5: Add failure reason tracking to stage metrics

---

## Detailed Action Items

### Wave A: Independent Hot Fixes

#### A1: Import sorting auto-fix
- **Priority:** Medium
- **Location:** Entire codebase (~133 files)
- **Action:** Run `.venv/bin/ruff check . --exclude .venv --fix`
- **Verification:** `.venv/bin/ruff check . --select I --exclude .venv` returns zero
- **Note:** This is safe to run anytime; no logic changes

#### A2: LLM cost rate correction
- **Priority:** Medium
- **Location:** `services/cost_tracker.py:24`
- **Fixes needed:**
  - DeepSeek: `output: 1.10` → `output: 0.42`
  - Add `ollama-local/qwen3:8b`: `input: 0.00, output: 0.00`
  - Add `anthropic/claude-sonnet-4-5-20250929`: `input: 3.00, output: 15.00`
  - Add `opencode/opencode`: `input: 0.00, output: 0.00` (credit-based)
  - Add `gemini/gemini-2.0-flash`: already present
  - Add `gemini/gemini-2.5-flash`: `input: 0.60, output: 2.40`
- **Reference:** AGENTS.md line 94 confirms pricing may need updating

#### A3: Add debug logging to silent exception blocks
- **Priority:** Low
- **Locations:**
  - `routes/public/links.py:61-62` — reading time calculation silent except
  - `routes/admin/api/webhooks.py:337-338` — event payload parsing silent except
  - `tasks/extract.py:347-348` — metrics increment silent except
- **Action:** Add `logger.debug("message: %s", e)` to each block
- **Pattern:** Use `%`-formatting, not f-strings, per AGENTS.md logging conventions

#### A4: Remove console.log from production code
- **Priority:** Low
- **Location:** `static/js/app.js:328-330`
- **Action:** Remove or wrap in environment check
- **Evidence:** Service worker registration debug logs

---

### Wave B: Security & Share Fixes

#### B1: CSP missing directives
- **Priority:** High
- **Location:** `app.py:108-113`
- **Current:** Only `default-src`, `style-src`, `script-src`, `img-src` defined
- **Add:**
  - `connect-src` — for API calls to LLM providers
  - `object-src` — prevent plugin embedding
  - `base-uri` — prevent base tag injection
  - `form-action` — limit form submission targets
- **Context:** AGENTS.md line 485-489 covers HTML escaping patterns; CSP is complementary

#### B2: safe_href filter in share templates
- **Priority:** High
- **Locations:**
  - `templates/partials/share_macro.html:21` — currently `{{ share_href }}` without filter
  - `templates/share_redirect.html:31` — currently `{{ share_url }}` without filter
- **Filter exists:** `app.py:238-252` (safe_href filter validates http/https, returns `#` for invalid)
- **Action:** Change `href="{{ share_href }}"` → `href="{{ share_href|safe_href }}"`
- **Already used in:** article_card.html, condensed_article.html, article_edit.html

#### B3: ShareConfig validation on save
- **Priority:** Medium
- **Location:** Admin webhook/config routes for ShareConfig
- **Action:** Add schema validation ensuring `url_template` only allows http/https schemes
- **Purpose:** Defense-in-depth alongside B2

#### B4: Merge share-a11y.js into app.js
- **Priority:** Medium
- **Files:**
  - Merge focus logic from `static/js/share-a11y.js:4-16` into `static/js/app.js:56-76`
  - Fix aria-expanded handling: `e.target.open.toString()` (currently missing `.toString()`)
  - Delete `static/js/share-a11y.js` after merge
  - Remove script tag from `templates/base.html` and `templates/base_admin.html`
- **Current bug:** app.js line 61 sets `aria-expanded` to boolean instead of string

---

### Wave C: Performance Fixes

#### C1: Fix uncached related articles query
- **Priority:** High
- **Location:** `routes/public/links.py:50`
- **Current:** Uses `find_related_articles()` directly
- **Change:** Use `find_related_articles_cached()` from `services/related.py:11-42`
- **Cache:** 600s TTL, key `pub:related:{article_id}`
- **Evidence:** AGENTS.md line 378 explicitly recommends cached version for article detail routes

#### C2: Fix O(n) cache eviction
- **Priority:** High
- **Location:** `services/cache.py:23,50,52-58`
- **Current:** Full O(n) scan every 100 calls via `_evict_stale()`
- **Remove:**
  - `_EVICT_SAMPLE_RATE = 100` (line 23)
  - `self._evict_sample_counter = 0` (line 50)
  - `_evict_stale()` method (lines 52-58)
- **Replace with:** Incremental eviction — check first 5 entries on each access

#### C3: Add date prefilter to related articles
- **Priority:** Medium
- **Location:** `services/related.py:75-104`
- **Action:**
  - Add 30-day date window to candidate query
  - Make `_RELATED_CANDIDATE_LIMIT` configurable via env var
- **Purpose:** Reduce memory usage for related article lookup

#### C4: Add Source health indexes
- **Priority:** Medium
- **Locations:**
  - Migration: `migrations/versions/029_sources_health_indexes.py`
  - Model: `models.py` Source class — add `index=True` on `consecutive_failures` and `disabled_at`
- **Action:** Create migration + update model
- **Reference:** AGENTS.md line 242 covers source health tracking

---

### Wave D: Pipeline & Webhook Fixes

#### D1: Always route degraded content to review
- **Priority:** High
- **Location:** `services/pipeline_degradation.py:142`
- **Current:** `if article.degradation_count >= 2 or _should_route_to_review(article)`
- **Change:** `if article.degradation_count > 0` — any degradation requires human review
- **Evidence:** Verified at line 142, uses `>= 2` check

#### D2: Fire article.failed webhook event
- **Priority:** Medium
- **Location:** `tasks/pipeline.py` — when article exhausts all retries
- **Current:** Event defined in `KNOWN_WEBHOOK_EVENTS` but never triggered
- **Action:** Add `trigger_event("article.failed", ...)` when `total_retries >= MAX_TOTAL_RETRIES`
- **Reference:** AGENTS.md line 692 confirms this event is defined but not fired

#### D3: Fire newsletter.failed webhook event
- **Priority:** Medium
- **Location:** `tasks/newsletter.py` — when delivery fails after all retries
- **Current:** Event defined in `KNOWN_WEBHOOK_EVENTS` but never triggered
- **Action:** Add `trigger_event("newsletter.failed", ...)` when delivery fails
- **Reference:** AGENTS.md line 692 confirms this event is defined but not fired
- **Note:** Also fix `newsletter_id` being NULL — currently passes `NewsletterConfig` (Pydantic) instead of `Newsletter` model (line 259)

#### D4: Add stage label to LLM metrics
- **Priority:** Medium
- **Location:** `services/llm/__init__.py:99-114` — `record_provider_success()`
- **Current:** Metrics have `provider` and `model` labels only
- **Add:** `stage` label (select, research, write, edit)
- **Affected metrics:** `llm.calls`, `llm.tokens`

#### D5: Add failure reason tracking to stage metrics
- **Priority:** Medium
- **Location:** `services/pipeline_monitor.py`, `services/pipeline_failure.py`
- **Action:** Extend `record_stage_result(stage, result, reason=None)` with reason tracking
- **Reasons to track:** rate_limit, timeout, server_error, validation, circuit_open, unknown

---

## Items Removed During This Review

The following items from previous plan.md were removed:

| Item | Reason |
|------|--------|
| "aggregate_crawl_results autoretry" — wave5_6 | Already had `autoretry_for=(ConnectionError, TimeoutError)` at line 198 |
| "RSS adapter socket timeout" | Per-request `timeout=cfg.request_timeout` at line 38 provides actual timeout |
| "Subagent chain template resolution 'result unused'" | Verified: result IS used via `prompt_data_escaped` in `.format()` call |
| `_find_overlapping_low_entries` dead code removal | Low priority, just dead code, no functional impact |

---

## Deferred Items (Do Not Implement Without Further Analysis)

These items were intentionally deferred in previous planning sessions:

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
| Search highlighting (FTS5) | Significant architectural change |
| Keyboard navigation ARIA feed | Complex, low signal |
| Reader counts display | Simple but low signal |
| Beat task last-run display | Nice to have |
| Theme toggle keyboard shortcut | Minor convenience |
| Newsletter dry-run styling | Minor |
| Docker healthchecks | Low priority |
| ThreadPool executor lazy init + atexit | Medium effort, low production impact |
| Notification system (AdminPreference model) | Significant new feature |
| Subagent topic scope isolation | Medium effort, needs design |
| CSP `unsafe-inline` removal | Medium effort, risk of breakage |
| Search result caching | Nice-to-have optimization |
| Search provider fallback chain | Nice-to-have optimization |
| Config version coordination | High complexity |
| Audit log decorator | Nice-to-have |
| HSTS subdomains | May break subdomains if added later |
| Redis-Backed Sessions | Current cookie sessions adequate |
| CSS architecture refactor | Intentional duplication per AGENTS.md |
| A/B experiment | Depends on experiment config in pipeline.yaml |
| Pipeline query parallelization | Do NOT parallelize (<1% savings) |
| JS bundling | Not needed for ~8KB footprint |
| opencode pricing | Credit-based billing model |

---

## Implementation Order (Suggested)

```
Week 1: Wave A (Independent Hot Fixes)
├── A1: Import sorting (5 min)
├── A2: DeepSeek cost correction (10 min)
├── A3: Debug logging (15 min)
└── A4: console.log removal (5 min)

Week 2: Wave B (Security & Share Fixes)
├── B1: CSP directives (15 min)
├── B2: safe_href in templates (10 min)
├── B3: ShareConfig validation (15 min)
└── B4: Share dropdown merge (30 min)

Week 3: Wave C (Performance Fixes)
├── C1: Related articles cache (10 min)
├── C2: O(n) cache eviction fix (30 min)
├── C3: Date prefilter (20 min)
└── C4: Source health indexes (30 min + migration)

Week 4: Wave D (Pipeline & Webhook Fixes)
├── D1: Degradation routing (5 min)
├── D2: article.failed webhook (30 min)
├── D3: newsletter.failed webhook (30 min)
├── D4: Stage label on LLM metrics (20 min)
└── D5: Failure reason tracking (30 min)
```

---

## Verification Commands

```bash
# Import sorting check
.venv/bin/ruff check . --select I --exclude .venv

# Full lint check
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Webhook tests (after implementing D2/D3)
.venv/bin/python -m pytest tests/test_webhooks.py -v

# Specific affected tests
.venv/bin/python -m pytest tests/test_routes.py tests/test_subagent.py tests/test_response_cache.py -v
```

---

## Cross-Plan Dependencies

1. **B2 (safe_href in templates)** depends on B1 (filter exists at app.py:238-252)
2. **B3 (ShareConfig validation)** should be implemented alongside B2 as defense in depth
3. **C1 (Related articles cache)** and **C3 (Date prefilter)** both modify `services/related.py`
4. **D2/D3 (Webhook events)** should be verified against `KNOWN_WEBHOOK_EVENTS` at `routes/admin/api/webhooks.py:12-17`
5. **A2 (DeepSeek cost)** is referenced in AGENTS.md line 94

---

## Already Implemented (Verified)

| Item | Evidence |
|------|----------|
| Session Regeneration on Login (H4) | `routes/admin/auth.py:56` — `session.clear()` before `session["admin"] = True` |
| safe_href filter exists | `app.py:238-252` — validates http/https, returns `#` for invalid |
| _find_overlapping_low_entries dead code | `services/trend_memory.py:274-287` — never called |
| trigger_event function | `services/webhooks.py:289` — exists but not called for failed events |
| share-a11y.js file | `static/js/share-a11y.js` — exists, needs merge |

---

*Consolidated: April 27, 2026*
*Verification completed via subagent batch review of plan2-8 and existing plan.md*
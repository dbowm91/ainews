# Consolidated Implementation Plan (Batch 1)

**Consolidated from:** plan2.md, plan3.md, plan4.md, plan5.md
**Date:** April 27, 2026
**Total Original Plans:** 4

---

## Table of Contents

1. [Plan 2: Code Quality Improvement Plan](#plan-2-code-quality-improvement-plan)
2. [Plan 3: Security Improvement Plan](#plan-3-security-improvement-plan)
3. [Plan 4: Performance Improvement Plan](#plan-4-performance-improvement-plan)
4. [Plan 5: Codebase Improvement Plan (Wave 5)](#plan-5-codebase-improvement-plan-wave-5)
5. [Merged Action Items](#merged-action-items)
6. [Future Work / Deferred Items](#future-work--deferred-items)
7. [Already Implemented Items](#already-implemented-items)
8. [Cross-Plan Dependencies](#cross-plan-dependencies)

---

## Plan 2: Code Quality Improvement Plan

**Status:** PENDING — Review completed (April 27, 2026)

### Key Sections

| Section | Status | Notes |
|---------|--------|-------|
| Exception Handling | ✅ Good | 3 minor fixes needed |
| Celery Config Access | ✅ Acceptable | Pattern already handles RuntimeError |
| Silent Exception Handlers | ✅ Good | Already has appropriate logging |
| TODO Items | ✅ Minimal | 1 low-priority item |
| Security | ✅ Robust | No issues found |
| Code Documentation | ⚠️ Optional | Some large files could use docs |

### Files to Modify (3 lines total)

| File | Line | Change | Status |
|------|------|--------|--------|
| `routes/public/links.py` | 61-62 | Add `logger.debug()` to except block | Pending |
| `routes/admin/api/webhooks.py` | 337-338 | Add `logger.debug()` to except block | Pending |
| `tasks/extract.py` | 347-348 | Add `logger.debug()` to except block | Pending |

### Action Items

- [ ] **1.1** Add debug logging to `routes/public/links.py:61` (reading time calculation silent except)
- [ ] **1.2** Add debug logging to `routes/admin/api/webhooks.py:337` (event payload parsing silent except)
- [ ] **1.3** Add debug logging to `tasks/extract.py:347` (metrics increment silent except)

### Optional / Future Items

- [ ] **2.1** Add module docstring to `services/subagent.py` (1107 lines, documentation-only)
- [ ] **3.1** A/B experiment implementation (future, depends on experiment config in pipeline.yaml)

---

## Plan 3: Security Improvement Plan

**Status:** PENDING — Security audit completed (April 27, 2026)

### Key Sections

- **Gap Analysis:** High (4 items), Medium (5 items), Low/Info (4 items)
- **Existing Security:** SSRF, HMAC, password hashing, CSRF, login lockout, webhook encryption, HTML escaping, config allowlist, open redirect protection ✅

### High Priority Items

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| H1 | CSP - Add Missing Security Directives | `app.py:104-125` | Pending |
| H2 | CSP - Add Session Cookie Flags | `config.py:28-33` | Pending |
| H3 | Share Macro XSS Protection | `templates/partials/share_macro.html`, `templates/share_redirect.html` | Pending |
| H4 | Session Regeneration on Login | `routes/admin/auth.py:56-57` | ✅ Already implemented |

### Action Items (High Priority)

- [ ] **H1** Add CSP directives: `connect-src`, `object-src`, `base-uri`, `form-action` to `app.py:104-125`
- [ ] **H2** Add `SESSION_USE_SIGNER = True` to Config class (signs session ID cookie)
- [ ] **H3** Use `|safe_href` filter in share templates (note: filter already exists at `app.py:237-252`)
  - [ ] Update `templates/partials/share_macro.html:21`
  - [ ] Update `templates/share_redirect.html:31`
  - [ ] Add `ShareConfig.url_template` validation on save (defense in depth)

### Medium Priority Items

| Item | Description | Status |
|------|-------------|--------|
| M1 | Audit Logging - Add Missing Events | Pending |
| M2 | CSP - Fix Inline Event Handlers | Pending |
| M3 | ShareConfig Validation on Save | Pending |
| M4 | HSTS Subdomains | Deferred |
| M5 | Input Limits - Admin Form Fields | Pending |

### Action Items (Medium Priority)

- [ ] **M1** Add audit events for:
  - [ ] `source_enable` at `routes/admin/sources.py:91`
  - [ ] `source_disable` at `routes/admin/sources.py:108`
  - [ ] `webhook_create` at `routes/admin/api/webhooks.py:86`
  - [ ] `webhook_update` at `routes/admin/api/webhooks.py:188`
  - [ ] `webhook_delete` at `routes/admin/api/webhooks.py:231`
  - [ ] `config_reload` at `routes/admin/api/config.py:10`
  - [ ] `article_edit` at `routes/admin/articles.py`
  - [ ] `article_delete` at `routes/admin/articles.py`
  - [ ] `trend_memory_delete` at `routes/admin/trend_memory.py:46`
- [ ] **M2** Fix inline event handlers (onclick) - Option B preferred: move to external JS in `static/js/app.js`
- [ ] **M3** Add schema validation for `ShareConfig.url_template` (only http/https schemes)
- [ ] **M4** Set `strict_transport_security_include_subdomains=True` in ProductionConfig (deferred - may break subdomains)
- [ ] **M5** Add max_length to important admin form fields

### Low Priority / Info Items

- [ ] **L1** Add unit tests for `safe_href` filter (edge cases: empty, invalid scheme, SSRF-blocked)
- [ ] **L2** Redis-Backed Sessions (optional - current cookie sessions adequate)
- [ ] **L3** Rate Limiting Verification (WAF/reverse proxy handles, not code change)
- [ ] **L4** CSP unsafe-inline Removal (deferred - do after other CSP fixes)

---

## Plan 4: Performance Improvement Plan

**Status:** Draft - Ready for Review (April 27, 2026)

### Key Sections

- **Priority 1 (Critical):** 3 items - uncached query, cache eviction, missing index
- **Priority 2 (Important):** 3 items - source health cache, Redis configurability
- **Priority 3 (Low):** 5 items documented as no action needed

### Action Items (Priority 1 - Critical Fixes)

- [ ] **1.1** Fix uncached related articles query in `routes/public/links.py:50`
  - Change `find_related_articles()` → `find_related_articles_cached()`
  - Note: `find_related_articles_cached()` exists in `services/related.py` with 600s TTL cache
- [ ] **1.2** Add date prefilter to related articles in `services/related.py:75-104`
  - Add 30-day date window to candidate query
  - Make `_RELATED_CANDIDATE_LIMIT` configurable via env var
- [ ] **1.3** Fix O(n) cache eviction in `services/cache.py:52-58`
  - Replace full O(n) scan with incremental eviction (check first 5 entries)
  - Remove `_EVICT_SAMPLE_RATE = 100` (line 23) and `self._evict_sample_counter = 0` (line 50)
  - Remove entire `_evict_stale()` method

### Action Items (Priority 2 - Important Improvements)

- [ ] **2.1** Cache source health query in `services/subagent.py:141`
  - Add 60-second TTL cache to `_get_source_health()`
  - Prepare for future enablement (tool currently registered but NOT enabled in pipeline.yaml)
- [ ] **2.2** Add indexes on Source health columns
  - Create migration `migrations/versions/029_sources_health_indexes.py`
  - Add index on `consecutive_failures` and `disabled_at` columns
  - Update `models.py` Source class with `index=True` on these columns
- [ ] **2.3** Make Redis `max_connections` configurable
  - Update `extensions.py:109-124` to read `REDIS_MAX_CONNECTIONS` env var
  - Update `services/config_cache.py` to read `CONFIG_CACHE_MAX_CONNECTIONS` env var
  - Add `socket_connect_timeout` and `retry_on_timeout` to pool kwargs
  - Document in `.env.example`

### Priority 3 Items (No Immediate Action)

| Item | Finding | Verdict |
|------|---------|---------|
| 3.1 | Login cleanup algorithm O(n log n) | No action needed (negligible at 1000 entries) |
| 3.2 | Crawl task batching (5-20 per source) | No action needed (correct for retry/fault isolation) |
| 3.3 | Pipeline query parallelization | Do NOT parallelize (<1% savings, added complexity) |
| 3.4 | Cache invalidation O(n) iteration | No action needed at current scale (1000 entries) |
| 3.5 | Dead code cleanup | Already covered in 1.3 |

### Implementation Phases

```
Phase 1: Week 1 (Critical Fixes)
1. Fix uncached related articles call (1.1)
2. Add date prefilter to related articles (1.2)
3. Fix O(n) cache eviction (1.3)

Phase 2: Week 2 (Important Improvements)
4. Cache source health query (2.1)
5. Add Source health indexes (2.2)
6. Make Redis max_connections configurable (2.3)

Phase 3: Testing & Rollout
7. Run full test suite after each change
8. Deploy to staging, monitor performance
9. Deploy to production
```

---

## Plan 5: Codebase Improvement Plan (Wave 5)

**Status:** PLANNED (April 27, 2026)

### Key Sections

- Missing webhook event triggers
- Dead code cleanup
- Cost tracking gaps
- Known limitations in webhook payloads

### Action Items

- [ ] **Item 1** Fire `article.failed` webhook event in `tasks/pipeline.py`
  - Add `trigger_event("article.failed", ...)` when article exhausts all retries
  - Note: Event type is defined in `KNOWN_WEBHOOK_EVENTS` but no code calls it
- [ ] **Item 2** Fire `newsletter.failed` webhook event in `tasks/newsletter.py`
  - Add `trigger_event("newsletter.failed", ...)` when delivery fails after all retries
  - Note: Event type is defined but never triggered
- [ ] **Item 3** Add missing provider pricing to `services/cost_tracker.py`
  - [ ] `ollama-local/qwen3:8b`: 0.00/0.00 (free local model)
  - [ ] `anthropic/claude-sonnet-4-5-20250929`: 3.00/15.00
  - [ ] `opencode/opencode`: 0.00/0.00 (credit-based billing, skip or 0.00)
- [ ] **Item 4** Fix `newsletter_id` being NULL in webhook payload
  - Currently passes `NewsletterConfig` (Pydantic schema) instead of `Newsletter` model
  - Option A: Create `Newsletter` record first, use its ID
- [ ] **Item 5** Remove dead code `_find_overlapping_low_entries`
  - Function at `services/trend_memory.py:274-281` is never called
  - Simple deletion, no callers to update
  - Update `docs/trend-memory.md` if it references this function

### Deferred Items (Do Not Implement)

| Item | Reason |
|------|--------|
| CSS architecture duplication | Intentional by design (documented in AGENTS.md) |
| Test contamination handling | Test skipped to avoid datetime issues (confirmed working as designed) |
| opencode pricing | Uses credit-based billing, not per-token |

---

## Merged Action Items

### Priority Order

#### Critical / High Priority

- [ ] **plan4/1.1** Fix uncached related articles query (`routes/public/links.py:50`) - use `find_related_articles_cached()`
- [ ] **plan4/1.3** Fix O(n) cache eviction (`services/cache.py:52-58`) - incremental eviction
- [ ] **plan3/H1** Add CSP missing directives (`connect-src`, `object-src`, `base-uri`, `form-action`)
- [ ] **plan3/H3** Add `|safe_href` filter to share templates + ShareConfig validation
- [ ] **plan5/Item 1** Fire `article.failed` webhook event in `tasks/pipeline.py`
- [ ] **plan5/Item 2** Fire `newsletter.failed` webhook event in `tasks/newsletter.py`

#### Medium Priority

- [ ] **plan2/1.1** Add debug logging to `routes/public/links.py:61`
- [ ] **plan2/1.2** Add debug logging to `routes/admin/api/webhooks.py:337`
- [ ] **plan2/1.3** Add debug logging to `tasks/extract.py:347`
- [ ] **plan4/1.2** Add date prefilter (30-day window) to related articles
- [ ] **plan3/H2** Add `SESSION_USE_SIGNER = True` to Config class
- [ ] **plan4/2.1** Add 60-second TTL cache to source health query in subagent
- [ ] **plan4/2.2** Add indexes on Source health columns (migration + model update)
- [ ] **plan4/2.3** Make Redis `max_connections` configurable via env vars
- [ ] **plan3/M1** Add 9 missing audit events
- [ ] **plan3/M2** Fix inline event handlers (Option B: external JS)
- [ ] **plan3/M3** Add ShareConfig validation on save
- [ ] **plan5/Item 4** Fix `newsletter_id` NULL in webhook payload

#### Low Priority / Small

- [ ] **plan5/Item 3** Add missing provider pricing to cost tracker (3 providers)
- [ ] **plan5/Item 5** Remove dead code `_find_overlapping_low_entries`
- [ ] **plan2/2.1** Add module docstring to `services/subagent.py` (optional)
- [ ] **plan3/L1** Add `safe_href` filter unit tests
- [ ] **plan3/M5** Add max_length to admin form fields

### Consolidated Implementation Order

```
Week 1: Critical Fixes
├── plan4/1.1: Fix uncached related articles (5 min)
├── plan4/1.3: Fix O(n) cache eviction (30 min)
├── plan3/H1: Add CSP missing directives (15 min)
└── plan3/H3: Add |safe_href to templates (15 min)

Week 2: Debug Logging + Audit Events
├── plan2/1.1, 1.2, 1.3: Add debug logging to 3 locations (15 min)
├── plan4/1.2: Add date prefilter to related articles (20 min)
├── plan3/M1: Add 9 missing audit events (1-2 hrs)
└── plan3/M2: Fix inline event handlers (1 hr)

Week 3: Important Improvements
├── plan4/2.1: Cache source health query (30 min)
├── plan4/2.2: Add Source health indexes (30 min migration + model)
├── plan4/2.3: Make Redis max_connections configurable (30 min)
├── plan3/H2: Add SESSION_USE_SIGNER (15 min)
└── plan3/M3: ShareConfig validation (15 min)

Week 4: Webhook + Cost Tracker
├── plan5/Item 1: Fire article.failed webhook (30 min)
├── plan5/Item 2: Fire newsletter.failed webhook (30 min)
├── plan5/Item 3: Add missing provider pricing (15 min)
├── plan5/Item 4: Fix newsletter_id in webhook (30 min)
└── plan5/Item 5: Remove dead code (5 min)

Optional / Deferred
├── plan3/M4: HSTS subdomains (deferred)
├── plan3/M5: Input limits admin forms
├── plan3/L1: safe_href tests
├── plan3/L2: Redis-backed sessions
├── plan3/L4: unsafe-inline removal
├── plan2/3.1: A/B experiment
└── plan2/2.1: subagent.py docstring
```

---

## Future Work / Deferred Items

The following items are explicitly deferred and should not be implemented without further analysis:

| Source | Item | Reason |
|--------|------|--------|
| plan3 | M4: HSTS Subdomains | May break subdomains if added later |
| plan3 | L2: Redis-Backed Sessions | Current cookie sessions adequate |
| plan3 | L4: CSP unsafe-inline Removal | Do after other CSP fixes |
| plan2 | 3.1: A/B experiment | Depends on experiment config in pipeline.yaml |
| plan2 | 2.1: subagent.py docstring | Documentation-only, low ROI |
| plan5 | Deferred: CSS architecture | Intentional by design (AGENTS.md) |
| plan5 | Deferred: opencode pricing | Credit-based billing model |
| plan4 | 3.3: Pipeline query parallelization | Do NOT parallelize (<1% savings) |

---

## Already Implemented Items

The following items from the plans are already implemented in the codebase:

| Source | Item | Evidence |
|--------|------|----------|
| plan3 | H4: Session Regeneration on Login | `routes/admin/auth.py:56-57` - `session.clear()` already issues new cookie |
| plan3 | H3: \|safe_href filter | Filter exists at `app.py:237-252` and validates http/https, returns `#` for invalid URLs |
| plan4 | 3.5: Dead code cleanup | `_EVICT_SAMPLE_RATE` and `_evict_sample_counter` are covered by plan4/1.3 |
| plan2 | Priority 2: Config Access Pattern | Pattern already correct - no code change needed |
| plan4 | 3.1, 3.2, 3.3, 3.4 | Low priority items with "No action needed" verdict |

---

## Cross-Plan Dependencies

Some items have dependencies across plans:

1. **Plan 3 H3 (Share Macro XSS)** depends on `|safe_href` filter which already exists (`app.py:237-252`)
2. **Plan 3 M3 (ShareConfig validation)** should be implemented alongside H3 as defense in depth
3. **Plan 4/1.1 (Related articles cache)** and **Plan 4/1.2 (Date prefilter)** are related - both modify `services/related.py`
4. **Plan 5/Item 1 & 2 (Webhook events)** should be verified against `KNOWN_WEBHOOK_EVENTS` at `routes/admin/api/webhooks.py:14`

---

## Verification Commands

```bash
# Run ruff linting
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Specific test files for affected code
.venv/bin/python -m pytest tests/test_routes.py tests/test_subagent.py tests/test_response_cache.py -v
```

---

*Consolidated: April 27, 2026*

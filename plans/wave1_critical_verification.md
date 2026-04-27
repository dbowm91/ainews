# Wave 1 Critical Items Verification

**Date:** April 27, 2026
**Purpose:** Verify status of all items marked "pending" or "already implemented" in batch1/batch2 consolidated plans against actual codebase.

---

## Batch 1 High Priority Items

## Item: plan4/1.1 - Fix uncached related articles query
- Status: **NOT_IMPLEMENTED**
- Evidence: `routes/public/links.py:50` uses `find_related_articles(article, limit=5)` directly. The cached version `find_related_articles_cached()` exists in `services/related.py:11-42` with 600s TTL but is NOT being called from the article detail route.
- Location: `routes/public/links.py:50`

## Item: plan4/1.3 - Fix O(n) cache eviction
- Status: **NOT_IMPLEMENTED**
- Evidence: All three items slated for removal still exist:
  - `_EVICT_SAMPLE_RATE = 100` at `services/cache.py:23`
  - `self._evict_sample_counter = 0` at `services/cache.py:50`
  - `_evict_stale()` method at `services/cache.py:52-58` performs full O(n) scan
- Location: `services/cache.py:23,50,52-58`

## Item: plan3/H1 - Add CSP missing directives
- Status: **NOT_IMPLEMENTED**
- Evidence: CSP at `app.py:108-113` only defines `default-src`, `style-src`, `script-src`, `img-src`. Missing directives: `connect-src`, `object-src`, `base-uri`, `form-action`.
- Location: `app.py:108-113`

## Item: plan3/H3 - Add |safe_href filter to share templates
- Status: **PARTIALLY_IMPLEMENTED**
- Evidence: The `safe_href` filter EXISTS at `app.py:238-252` and correctly validates http/https scheme and SSRF. However, share templates do NOT use it:
  - `templates/partials/share_macro.html:21` uses `{{ share_href }}` (no filter)
  - `templates/share_redirect.html:31` uses `{{ share_url }}` (no filter)
- Filter is implemented but not deployed in the templates that need it.
- Location: `app.py:238-252`, `templates/partials/share_macro.html:21`, `templates/share_redirect.html:31`

## Item: plan5/Item 1 - Fire article.failed webhook event
- Status: **NOT_IMPLEMENTED**
- Evidence: `KNOWN_WEBHOOK_EVENTS` at `routes/admin/api/webhooks.py:14` defines `"article.failed"`. The `trigger_event()` function exists in `services/webhooks.py`. However, grep across entire codebase finds NO actual call to `trigger_event("article.failed", ...)`. AGENTS.md:692 confirms: "no code calls `trigger_event('article.failed', ...)`"
- Location: `routes/admin/api/webhooks.py:14`, `services/webhooks.py` (definition), `tasks/pipeline.py` (no trigger call)

## Item: plan5/Item 2 - Fire newsletter.failed webhook event
- Status: **NOT_IMPLEMENTED**
- Evidence: Same pattern as Item 1. `"newsletter.failed"` is defined in `KNOWN_WEBHOOK_EVENTS` at `routes/admin/api/webhooks.py:16` but NO code calls `trigger_event("newsletter.failed", ...)`. AGENTS.md:692 confirms.
- Location: `routes/admin/api/webhooks.py:16`, `tasks/newsletter.py` (no trigger call)

---

## Batch 2 High Priority Items

## Item: plan6-Item1 - Merge duplicate share dropdown event handlers
- Status: **NOT_IMPLEMENTED**
- Evidence: `static/js/share-a11y.js` still exists as a separate file. Batch2 consolidated notes "share-a11y.js is still present at `static/js/share-a11y.js` and referenced in templates" — the merge was planned but not executed.
- Location: `static/js/share-a11y.js` (file still present)

## Item: plan7-Item1 - Import sorting auto-fix
- Status: **NEEDS_VERIFICATION**
- Evidence: Cannot verify from static analysis. Would need to run `.venv/bin/ruff check . --select I --exclude .venv` to determine if imports are sorted.
- Location: N/A

## Item: plan7-Item2 - LLM cost rate correction (DeepSeek)
- Status: **NOT_IMPLEMENTED**
- Evidence: `services/cost_tracker.py:24` still has `"deepseek/deepseek-chat": {"input": 0.27, "output": 1.10}`. Plan specifies output should be `$0.42` not `$1.10`. Also note: batch2 plan mentions adding `gemini/gemini-2.5-flash` pricing but current file only has `gemini/gemini-2.0-flash`.
- Location: `services/cost_tracker.py:24`

## Item: plan8-Item1 - Always route degraded content to review
- Status: **NOT_IMPLEMENTED**
- Evidence: `services/pipeline_degradation.py:142` has `if article.degradation_count >= 2 or _should_route_to_review(article):`. Plan specifies this should be `> 0` so any degraded content requires review. Currently only routes to review after 2+ degradations.
- Location: `services/pipeline_degradation.py:142`

## Item: plan8-Item3 - Add stage label to LLM metrics
- Status: **NEEDS_VERIFICATION**
- Evidence: Cannot verify from static analysis alone. Would need to inspect `services/llm/base.py` metrics implementation to see if `stage` label is present on `llm.calls` and `llm.tokens` counters.
- Location: `services/llm/base.py` (needs inspection)

---

## Already Implemented Items (Verification)

## Item: plan3/H4 - Session Regeneration on Login
- Status: **IMPLEMENTED**
- Evidence: `routes/admin/auth.py:56` has `session.clear()` immediately before `session["admin"] = True` at line 57. This correctly issues a new session cookie on login per Flask 3.x behavior.
- Location: `routes/admin/auth.py:56-57`

## Item: plan3/H3 (already implemented claim) - safe_href filter exists
- Status: **IMPLEMENTED** (filter exists, but templates don't use it — see above)
- Evidence: Filter defined at `app.py:238-252` with correct validation logic. However, share templates at `share_macro.html:21` and `share_redirect.html:31` do NOT apply the filter.
- Location: `app.py:238-252`

---

## Summary Table

| Item | Plan Source | Status |
|------|-------------|--------|
| plan4/1.1 - Uncached related articles | Batch1 | NOT_IMPLEMENTED |
| plan4/1.3 - O(n) cache eviction | Batch1 | NOT_IMPLEMENTED |
| plan3/H1 - CSP missing directives | Batch1 | NOT_IMPLEMENTED |
| plan3/H3 - safe_href in templates | Batch1 | PARTIALLY_IMPLEMENTED |
| plan5/Item 1 - article.failed webhook | Batch1 | NOT_IMPLEMENTED |
| plan5/Item 2 - newsletter.failed webhook | Batch1 | NOT_IMPLEMENTED |
| plan6-Item1 - Share dropdown merge | Batch2 | NOT_IMPLEMENTED |
| plan7-Item1 - Import sorting | Batch2 | NEEDS_VERIFICATION |
| plan7-Item2 - DeepSeek cost rate | Batch2 | NOT_IMPLEMENTED |
| plan8-Item1 - Degrade routing to review | Batch2 | NOT_IMPLEMENTED |
| plan8-Item3 - Stage label on LLM metrics | Batch2 | NEEDS_VERIFICATION |
| H4 - Session regeneration on login | Batch1 | IMPLEMENTED |

---

## Key Findings

1. **Cache/Performance items (plan4)**: Both 1.1 and 1.3 remain unimplemented. The cached helper exists but isn't called, and the O(n) eviction logic is still present.

2. **Security items (plan3 H-series)**: H1 (CSP) and H3 (safe_href in templates) remain unimplemented. H4 (session.clear) is correctly implemented.

3. **Webhook events (plan5 Items 1&2)**: Both `article.failed` and `newsletter.failed` events are defined but never triggered — confirmed by AGENTS.md note and grep results.

4. **Frontend items (plan6)**: Share dropdown merge (Item 1) has not been done — share-a11y.js still exists as separate file.

5. **Cost tracking (plan7 Item 2)**: DeepSeek rate remains at `1.10` instead of corrected `0.42`.

6. **Pipeline degradation (plan8 Item 1)**: Route to review only triggers at `degradation_count >= 2` not `> 0` as specified.

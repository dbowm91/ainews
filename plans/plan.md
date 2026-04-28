# Consolidated Implementation Plan
**Date:** April 28, 2026
**Status:** COMPLETED - All waves finished
**Total verified items:** 17 action items across 3 phases

**Last Update:** Skill file and AGENTS.md updated with all completed implementations

---
## Wave Structure

Items are grouped by **file conflict analysis**: items in the same wave touch different files and can be assigned to parallel sub-agents. Phase 0 must complete before Phase 1. Phase 1 must complete before Phase 2.

```
Phase 0 (1 agent):  A1 - ruff --fix prerequisite ✓
Phase 1 (9 agents): A2 ✓, A3 ✓, A4 ✓, B1 ✓, B5 ✓, B2 ✓, C2 ✓, C4 ✓, D4 ✓
Phase 2 (4 agents): B4 ✓, C1+C3 ✓, D2+D5 ✓, D3 ✓
```

**File conflict map** (why this ordering):
- A1 touches ~133 files -> must go first
- A4 and B4 both touch `static/js/app.js` -> A4 in Phase 1, B4 in Phase 2
- A3 touches `routes/public/links.py`, C1 also touches it -> A3 in Phase 1, C1 in Phase 2
- C1 and C3 both touch `services/related.py` -> combined into one agent in Phase 2
- D2 and D5 both touch `services/pipeline_failure.py` -> combined into one agent in Phase 2

---

## Phase 0: Prerequisite

### A1: Import sorting auto-fix

- **Priority:** Medium
- **Effort:** 5 minutes
- **File:** Entire codebase (~133 files)
- **Action:** Run `.venv/bin/ruff check . --exclude .venv --select I --fix`
- **Verification:** `.venv/bin/ruff check . --select I --exclude .venv` returns zero
- **Why first:** Ruff may reorder imports in files that other items modify. Running it first prevents merge conflicts.
- **Note:** Safe to run anytime; no logic changes. 417 I001 errors currently detected.

---

## Phase 1: Independent Fixes (9 parallel agents)

### A2: LLM cost rate correction

- **Priority:** Medium
- **Effort:** 10 minutes
- **File:** `services/cost_tracker.py`
- **Current code at line 24:**
  ```python
  "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
  ```
- **Changes:**
  1. Fix DeepSeek output price: `1.10` -> `0.42`
  2. Add these entries to `_DEFAULT_RATES` dict (after existing entries, before closing `}`):
     ```python
     "ollama-local/qwen3:8b": {"input": 0.00, "output": 0.00},
     "anthropic/claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
     "opencode/opencode": {"input": 0.00, "output": 0.00},
     "gemini/gemini-2.5-flash": {"input": 0.60, "output": 2.40},
     ```
- **Verification:** Run `.venv/bin/ruff check services/cost_tracker.py`. Run `.venv/bin/python -m pytest tests/test_cost_tracker.py -v` (if exists).

---

### A3: Add debug logging to silent exception blocks

- **Priority:** Low
- **Effort:** 15 minutes
- **Files:** 3 separate files (can be done by one agent)
- **Convention:** Use `%`-formatting in log calls, not f-strings (per AGENTS.md)

**Location 1:** `routes/public/links.py:61-62`
- **Current:**
  ```python
          except Exception:
              word_count = 0
  ```
- **Change to:**
  ```python
          except Exception as e:
              logger.debug("Failed to parse final_article for reading time: %s", e)
              word_count = 0
  ```
- **Logger:** Already imported at line 17

**Location 2:** `routes/admin/api/webhooks.py:337-338`
- **Current:**
  ```python
          except Exception:
              pass
  ```
- **Change to:**
  ```python
          except Exception as e:
              logger.debug("Failed to parse webhook event payload: %s", e)
  ```
- **Logger:** Already imported at line 10

**Location 3:** `tasks/extract.py:347-348`
- **Current:**
  ```python
          except Exception:
              pass
  ```
- **Change to:**
  ```python
          except Exception as e:
              logger.debug("Failed to increment dedup_check_failed metric: %s", e)
  ```
- **Logger:** Already available as `get_task_logger(__name__)` at line 9

- **Verification:** `.venv/bin/ruff check routes/public/links.py routes/admin/api/webhooks.py tasks/extract.py`

---

### A4: Remove console.log from production code

- **Priority:** Low
- **Effort:** 5 minutes
- **File:** `static/js/app.js:328-330`
- **Current:**
  ```javascript
        navigator.serviceWorker.register('/static/js/service-worker.js').then(function(registration) {
          console.log('ServiceWorker registered:', registration.scope);
        }).catch(function(err) {
          console.log('ServiceWorker registration failed:', err);
        });
  ```
- **Action:** Remove both `console.log` calls. Keep the `.then()` and `.catch()` structure but make them no-ops, or remove the `.then()` entirely and keep only the `.catch()` with a no-op:
  ```javascript
        navigator.serviceWorker.register('/static/js/service-worker.js').catch(function() {});
  ```
- **Verification:** Grep for `console.log` in `static/js/app.js` returns zero.

---

### B1: CSP missing directives

- **Priority:** High
- **Effort:** 15 minutes
- **File:** `app.py:108-113`
- **Current CSP dict:**
  ```python
  csp = {
      "default-src": "'self'",
      "style-src": "'self' 'unsafe-inline'",
      "script-src": "'self'",
      "img-src": "'self' data:",
  }
  ```
- **Change to:**
  ```python
  csp = {
      "default-src": "'self'",
      "style-src": "'self' 'unsafe-inline'",
      "script-src": "'self'",
      "img-src": "'self' data:",
      "connect-src": "'self'",
      "object-src": "'none'",
      "base-uri": "'self'",
      "form-action": "'self'",
  }
  ```
- **Notes:**
  - `connect-src 'self'` allows fetch() to same origin (HTMX, share tracking, service worker)
  - `object-src 'none'` prevents plugin embedding (Flash, Java)
  - `base-uri 'self'` prevents base tag injection
  - `form-action 'self'` restricts form submission targets
- **Verification:** Start app, verify no CSP violations in browser console. HTMX requests should still work.

---

### B5: Add SESSION_USE_SIGNER

- **Priority:** Medium
- **Effort:** 5 minutes
- **File:** `config.py:28-33` (Config class session section)
- **Current:**
  ```python
  SESSION_COOKIE_HTTPONLY = True
  SESSION_COOKIE_SAMESITE = "Lax"
  SESSION_COOKIE_SECURE = False  # overridden in ProductionConfig
  SESSION_COOKIE_PATH = "/"
  PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
  ```
- **Add after line 31 (after SESSION_COOKIE_SECURE):**
  ```python
  SESSION_USE_SIGNER = True
  ```
- **What it does:** Cryptographically signs the session cookie so clients cannot tamper with session data. Flask's default is False (plaintext).
- **Note:** This is additive - existing sessions will be re-issued with signatures on next request. No user-visible change.
- **Verification:** Login to admin, inspect session cookie - should be signed (not plaintext JSON).

---

### B2: safe_href filter in share templates

- **Priority:** High
- **Effort:** 10 minutes
- **Files:** `templates/partials/share_macro.html`, `templates/share_redirect.html`
- **The `safe_href` filter already exists** at `app.py:238-253` - validates http/https scheme, checks SSRF via `validate_url_safe()`, returns `#` for invalid URLs.

**Template 1:** `templates/partials/share_macro.html:21`
- **Current:** `href="{{ share_href }}"`
- **Change to:** `href="{{ share_href|safe_href }}"`

**Template 2:** `templates/share_redirect.html:31`
- **Current:** `href="{{ share_url }}"`
- **Change to:** `href="{{ share_url|safe_href }}"`

- **Verification:** Grep both files for `safe_href` to confirm filter applied.

---

### C2: Fix O(n) cache eviction

- **Priority:** High
- **Effort:** 30 minutes
- **File:** `services/cache.py`
- **Problem:** `_evict_stale()` at line 52-58 scans ALL entries on every `get()` (line 68) and `set()` (line 103). This is O(n) per cache access.
- **Items to remove:**
  1. `_EVICT_SAMPLE_RATE = 100` (line 23) - unused constant
  2. `self._evict_sample_counter = 0` (line 50) - unused attribute
  3. `_evict_stale()` method (lines 52-58) - full O(n) scan
- **Replace with incremental eviction:** On each `get()` and `set()`, check the oldest 5 entries (FIFO via `OrderedDict`) and remove expired ones. This amortizes eviction cost:
  ```python
  def _evict_batch(self, batch: int = 5) -> None:
      """Remove expired entries from the head of the OrderedDict."""
      now = time.monotonic()
      with self._memory_lock:
          for _ in range(batch):
              if not self._memory:
                  break
              key, (exp, _, _) = next(iter(self._memory.items()))
              if now >= exp:
                  del self._memory[key]
              else:
                  break
  ```
- **Then replace** `self._evict_stale()` calls at lines 68 and 103 with `self._evict_batch()`.
- **Verification:** `.venv/bin/ruff check services/cache.py`. Run `.venv/bin/python -m pytest tests/test_response_cache.py -v`.
- **Test note:** Tests that directly manipulate `_memory` use 3-tuple format `(expires_at, access_time, raw)`. The new `_evict_batch` method reads this format correctly.

---

### C4: Add Source health indexes

- **Priority:** Medium
- **Effort:** 30 minutes
- **Files:** `models.py`, new migration file

**Step 1:** Update `models.py` Source class
- **File:** `models.py` Source class, around lines 65 and 69
- **Current:**
  ```python
  consecutive_failures = db.Column(db.Integer, nullable=False, default=0)
  ...
  disabled_at = db.Column(db.DateTime, nullable=True)
  ```
- **Change to:**
  ```python
  consecutive_failures = db.Column(db.Integer, nullable=False, default=0, index=True)
  ...
  disabled_at = db.Column(db.DateTime, nullable=True, index=True)
  ```

**Step 2:** Create migration
- **File:** `migrations/versions/029_sources_health_indexes.py` (next number after 028)
- **Migration should add:**
  ```python
  def upgrade():
      op.create_index('ix_sources_consecutive_failures', 'sources', ['consecutive_failures'])
      op.create_index('ix_sources_disabled_at', 'sources', ['disabled_at'])

  def downgrade():
      op.drop_index('ix_sources_consecutive_failures')
      op.drop_index('ix_sources_disabled_at')
  ```

- **Verification:** `.venv/bin/ruff check models.py migrations/versions/029_sources_health_indexes.py`
- **Reference:** Admin sources health endpoint (`GET /admin/api/sources/health`) queries by `consecutive_failures >= 10` and `disabled_at is not None`. These indexes optimize those queries.

---

### D4: Add stage label to LLM metrics

- **Priority:** Medium
- **Effort:** 20 minutes
- **File:** `services/llm/__init__.py`
- **Current signature at line 99:**
  ```python
  def record_provider_success(provider_id: str, model: str, tokens_used: int = 0) -> None:
  ```
- **Change to:**
  ```python
  def record_provider_success(provider_id: str, model: str, tokens_used: int = 0, stage: str = "") -> None:
  ```
- **Update metric labels at lines 106-114** to include stage:
  ```python
  labels = {"provider": provider_id, "model": model}
  if stage:
      labels["stage"] = stage
  ```
- **Callers to update** (pass `stage` parameter):
  - `services/llm/base.py` - the `generate()` method needs a `stage` parameter
  - `tasks/select.py` - pass `stage="select"` when recording success
  - `tasks/research.py` - pass `stage="research"`
  - `tasks/write.py` - pass `stage="write"`
  - `tasks/edit.py` - pass `stage="edit"`
- **Note:** The `stage` parameter is optional with empty default for backward compatibility. Existing callers without stage will continue to work.
- **Verification:** `.venv/bin/ruff check services/llm/__init__.py services/llm/base.py tasks/select.py tasks/research.py tasks/write.py tasks/edit.py`

---

## Phase 2: Dependent Fixes (4 parallel agents)

These items depend on Phase 1 completing (file conflicts resolved).

### B4: Merge share-a11y.js into app.js + fix aria-expanded

- **Priority:** Medium
- **Effort:** 30 minutes
- **Files:** `static/js/app.js`, `static/js/share-a11y.js` (delete), `templates/base.html`, `templates/base_admin.html`
- **Depends on:** Phase 1 A4 (also touches app.js)

**Step 1:** Merge focus behavior from share-a11y.js into app.js

`static/js/share-a11y.js` (entire file, 17 lines) has two behaviors:
1. Line 9: `summary.setAttribute("aria-expanded", e.target.open.toString())` - **already duplicated** in app.js line 61, but app.js line 61 uses `e.target.open` (boolean) instead of `e.target.open.toString()` (string). **Fix: add `.toString()`**.
2. Lines 12-14: Focus first focusable element when dropdown opens - **NOT in app.js**. Must be preserved.

**In `static/js/app.js` around lines 57-76**, the toggle handler currently:
```javascript
  document.addEventListener("toggle", function (e) {
    if (!e.target.classList.contains("share-details")) return;
    var summary = e.target.querySelector("summary");
    if (summary) {
      summary.setAttribute("aria-expanded", e.target.open);  // BUG: boolean, not string
    }
    // ... flip-top logic ...
  });
```

**Change line 61 to use `.toString()`:**
```javascript
      summary.setAttribute("aria-expanded", e.target.open.toString());
```

**Add focus behavior after line 62** (after aria-expanded), before the dropdown/flip-top logic:
```javascript
    if (e.target.open) {
      var focusable = e.target.querySelector(".share-dropdown input, .share-dropdown button, .share-dropdown a");
      if (focusable) focusable.focus();
    }
```

**Step 2:** Delete `static/js/share-a11y.js`

**Step 3:** Remove script tags from templates:
- `templates/base.html` line ~27: Remove `<script src="{{ url_for('static', filename='js/share-a11y.js') }}" defer></script>`
- `templates/base_admin.html` line ~15: Remove the same script tag

- **Verification:** Confirm `static/js/share-a11y.js` no longer exists. Grep templates for `share-a11y` returns zero. Test share dropdown opens, aria-expanded updates, and focus moves to first element.

---

### C1+C3: Fix uncached related articles + add date prefilter

- **Priority:** High
- **Effort:** 30 minutes total
- **Files:** `routes/public/links.py`, `services/related.py`
- **Depends on:** Phase 1 A3 (also touches links.py)

**C1: Switch to cached version**

In `routes/public/links.py`:
- **Line 25 current:** `from services.related import find_related_articles`
- **Change to:** `from services.related import find_related_articles_cached`
- **Line 50 current:** `related = parse_articles(find_related_articles(article, limit=5))`
- **Change to:** `related = parse_articles(find_related_articles_cached(article, limit=5))`

**C3: Add 30-day date prefilter**

In `services/related.py`, the `find_related_articles()` function (called internally by the cached version). The candidate queries at lines 75-104 filter on `pipeline_status == DONE` and `final_article.isnot(None)` but have **no date constraint**.

- **Add at the top of the file:**
  ```python
  from datetime import datetime, timedelta, timezone
  ```
- **In the candidate query** (around lines 78-85 and 90-97), add a date filter:
  ```python
  .filter(Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30))
  ```
  This goes alongside the existing `.filter(Article.id != article.id)` and other filters.
- **Make `_RELATED_CANDIDATE_LIMIT` configurable** (currently hardcoded):
  ```python
  _RELATED_CANDIDATE_LIMIT = int(os.environ.get("RELATED_CANDIDATE_LIMIT", "50"))
  ```
  Add `import os` at the top if not present.

- **Verification:** `.venv/bin/ruff check routes/public/links.py services/related.py`. Run `.venv/bin/python -m pytest tests/test_related.py -v` (if exists).

---

### D2+D5: Fire article.failed webhook + add failure reason tracking

- **Priority:** Medium
- **Effort:** 45 minutes
- **Files:** `services/pipeline_failure.py`, `tasks/pipeline.py`, `services/pipeline_monitor.py`
- **Depends on:** Nothing in Phase 1 directly, but grouped for pipeline_failure.py coordination

**D2: Fire article.failed webhook**

The `trigger_event()` function exists at `services/webhooks.py:289-321`. The `"article.failed"` event is defined in `KNOWN_WEBHOOK_EVENTS` at `routes/admin/api/webhooks.py:12-17`.

In `services/pipeline_failure.py`, two places set `PipelineStatus.FAILED`:
1. **Line 80-82** (total retries exhausted):
   ```python
   if article.total_retries >= max_total:
       article.pipeline_status = PipelineStatus.FAILED
       return True
   ```
   After setting FAILED status and before returning, add:
   ```python
   try:
       from services.webhooks import trigger_event
       trigger_event("article.failed", {
           "article_id": article.id,
           "stage": stage,
           "reason": article.last_error or "total_retries_exceeded",
       })
   except Exception as wh_exc:
       logger.warning("Failed to trigger article.failed webhook: %s", wh_exc)
   ```
   **Important:** This must include a `db.session.commit()` before the webhook trigger. Currently line 82 just returns True without committing. The caller (`run_stage` in tasks/pipeline.py) handles the commit. Move the trigger to the caller after the commit, OR add a commit here. **Prefer adding it in `tasks/pipeline.py` after the commit that happens when `_handle_stage_failure` returns True.**

2. **Lines 84-103** (per-stage failure limit exceeded):
   This block already has a `db.session.commit()` at line 88. Add the webhook trigger after line 103 (`return True`), before the return:
   ```python
   try:
       from services.webhooks import trigger_event
       trigger_event("article.failed", {
           "article_id": article.id,
           "stage": stage,
           "reason": f"per_stage_limit ({stage_failures} failures)",
       })
   except Exception as wh_exc:
       logger.warning("Failed to trigger article.failed webhook: %s", wh_exc)
   ```

**D5: Add failure reason tracking to stage metrics**

In `services/pipeline_monitor.py`, the `record_stage_result()` function at line 26:
```python
def record_stage_result(
    stage: str, success: bool, run_id: Optional[int] = None
) -> None:
```

**Add `reason` parameter:**
```python
def record_stage_result(
    stage: str, success: bool, run_id: Optional[int] = None, reason: Optional[str] = None
) -> None:
```

**When recording failure** (the `else` branch for `success=False`), add a reason counter:
```python
if reason:
    reason_key = f"{_PIPELINE_COUNTER_PREFIX}{stage}:{current_minute}:failure:{reason}"
    redis_client.incr(reason_key)
    redis_client.expire(reason_key, _PIPELINE_WINDOW_SECONDS * 10)
```

**Reason values to use:** `rate_limit`, `timeout`, `server_error`, `validation`, `circuit_open`, `unknown`

**Update callers** in `tasks/pipeline.py` to pass reason when recording failures.

- **Verification:** `.venv/bin/ruff check services/pipeline_failure.py services/pipeline_monitor.py tasks/pipeline.py`

---

### D3: Fire newsletter.failed webhook + fix newsletter_id

- **Priority:** Medium
- **Effort:** 30 minutes
- **File:** `tasks/newsletter.py`
- **Depends on:** Nothing in Phase 1

**Part 1: Fix newsletter_id being NULL**

At line 259, the webhook payload for `newsletter.sent` has:
```python
"newsletter_id": nl.id if hasattr(nl, "id") else None,
```
The variable `nl` is a `NewsletterConfig` (Pydantic config from pipeline.yaml), NOT a `Newsletter` model. It has no `.id` attribute, so `newsletter_id` is always `None`.

The actual Newsletter model is created at line ~182 inside `_generate_topic_newsletter_impl` as the local variable `newsletter`. Fix by using `newsletter.id` instead of `nl.id`:
```python
"newsletter_id": newsletter.id,
```
(No `hasattr` guard needed - newsletter is always created before this point.)

**Part 2: Fire newsletter.failed webhook**

Find where email delivery fails in `_generate_topic_newsletter_impl` (around lines 216-223, the error handling for email sending). Add:
```python
try:
    from services.webhooks import trigger_event
    trigger_event("newsletter.failed", {
        "newsletter_id": newsletter.id,
        "newsletter_type": topic_key,
        "error": str(email_error),
    })
except Exception as wh_exc:
    logger.warning("Failed to trigger newsletter.failed webhook: %s", wh_exc)
```

- **Verification:** `.venv/bin/ruff check tasks/newsletter.py`. Run `.venv/bin/python -m pytest tests/test_webhooks.py -v`.

---

## Deferred Items

These items are intentionally deferred. Do not implement without further analysis.

| Item | Reason |
|------|--------|
| B3: ShareConfig validation on save | No CRUD route exists for ShareConfig; records are seed data only. Add when admin CRUD is built. |
| D1: Degradation routing threshold change | Current `>= 2` behavior is intentional design. Changing to `> 0` may cause review queue overflow. Needs stakeholder input. |
| CSS architecture refactor | Intentional duplication per AGENTS.md (critical.css must work standalone) |
| Session cookie name prefix (`__Secure-`) | Requires HTTPS in all environments including local dev |
| CSP `unsafe-inline` removal | Medium effort, risk of breakage. Do after other CSP fixes stabilize. |
| Audit logging for admin actions | Significant effort (9 events). No audit infrastructure exists yet. |
| HSTS include_subdomains | May break subdomains if added later |
| Redis-backed sessions | Current cookie sessions adequate |
| Pipeline query parallelization | Do NOT parallelize (<1% savings) |
| JS bundling | Not needed for ~8KB footprint |
| CSS token sync (critical.css) | Shared tokens already match; missing tokens are below-the-fold |
| Pagination accessibility announcements | Nice-to-have, low signal |
| Queue depth backpressure | Significant new feature, needs design |
| Pipeline throughput counters | Nice-to-have observability |
| Source health query cache in subagent | Tool registered but NOT enabled in pipeline.yaml |
| Redis max_connections env var | Nice-to-have, hasn't hit limits |
| safe_href filter unit tests | Important but low priority, no active vulnerability |
| A/B experiment implementation | Depends on experiment config in pipeline.yaml |
| Static analysis (mypy/ty) | Future tooling enhancement |
| _find_overlapping_low_entries dead code | Harmless dead code in trend_memory.py:274-287 |
| Inline event handler CSP fix | Already clean - no onclick/onerror handlers found in templates |

---

## Verification Commands

```bash
# Phase 0: Import sorting
.venv/bin/ruff check . --select I --exclude .venv

# Full lint check (after each phase)
.venv/bin/ruff check . --exclude .venv

# Run tests (after each phase)
.venv/bin/python -m pytest tests/ -x -q

# Webhook tests (after Phase 2 D2+D3)
.venv/bin/python -m pytest tests/test_webhooks.py -v

# Cache tests (after Phase 1 C2)
.venv/bin/python -m pytest tests/test_response_cache.py -v

# Specific affected tests
.venv/bin/python -m pytest tests/test_routes.py tests/test_subagent.py -v
```

---

*Consolidated and verified: April 27, 2026*
*All line numbers and code snippets verified against actual codebase*

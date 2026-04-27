# Consolidated Implementation Plan (Batch 2)

**Source Plans:** plan6.md (Frontend), plan7.md (Backend), plan8.md (Pipeline)  
**Status:** PLANNED — Compiled April 27, 2026  
**Workspace:** /home/sugarwookie/projects/ainews

---

## Plan 6: Frontend Improvements

### Overview

Addresses CSS architecture, JavaScript event handling, and accessibility identified during a frontend deep dive.

**Key Sections:**
- Item 1: Merge duplicate share dropdown event handlers
- Item 2: Add missing CSS tokens to inlined critical CSS
- Item 3: Remove console.log from production code
- Item 4: Add pagination accessibility announcements
- Item 5: CSS architecture refactor (DEFERRED)
- Item 6: JS bundling consideration (REJECTED)
- Item 7: Verify search accessibility (NO ACTION NEEDED)

**Implementation Order (suggested):**
1. Item 3 (Console logging) — Trivial warm-up
2. Item 4 (Pagination a11y) — Quick accessibility improvement
3. Item 1 (JS event merge) — Higher impact, low effort
4. Item 2 (Missing CSS tokens) — Medium effort, prevents FOUC

---

## Plan 7: Codebase Improvements

### Overview

Backend and tech stack review covering import sorting, LLM cost tracking, dead webhook events, and documentation cleanup.

**Key Sections:**
- Item 1: Import sorting auto-fix (133 files)
- Item 2: LLM cost rate correction
- Item 3: Dead webhook event handlers
- Item 4: AGENTS.md documentation cleanup
- Item 5: Static analysis enhancement (Future)
- Item 6: Test coverage verification (Info)

**Implementation Order:**
1. Item 1 — Import sorting (`ruff --fix`)
2. Item 2 — Cost rate correction
3. Item 3 — Webhook events decision + implementation
4. Item 4 — AGENTS.md cleanup
5. Items 5-6 — Future/info

---

## Plan 8: Pipeline Improvements

### Overview

AI agent pipeline review covering degradation routing, backpressure, observability, and metrics.

**Key Sections:**
- Item 1: Always route degraded content to review
- Item 2: Add backpressure with queue depth limiting
- Item 3: Add stage label to LLM metrics
- Item 4: Add failure reason tracking to stage metrics
- Item 5: Add pipeline throughput counters

**Implementation Order:**
1. Item 1 (High priority, low effort)
2. Item 3 (High priority, low effort)
3. Item 4 (Medium priority, builds on #3)
4. Item 5 (Medium priority, completes observability)
5. Item 2 (Medium priority, optional backpressure)

**Dependencies:** Item 3 should be implemented before Item 5; Item 4 builds on existing `pipeline_monitor.py` pattern.

---

## Merged Action Items

### High Priority

- [ ] **plan6-Item1: Merge duplicate share dropdown event handlers**
  - Location: `static/js/app.js`, `static/js/share-a11y.js`
  - Merge focus logic from `share-a11y.js` into `app.js` handler
  - Change `aria-expanded` handling to string (ARIA-compliant)
  - Delete `share-a11y.js` after merge
  - Files to modify: `static/js/app.js`, `static/js/share-a11y.js` (delete), `templates/base.html`, `templates/base_admin.html`
  - **Already exists:** `share-a11y.js` is still present at `static/js/share-a11y.js` and referenced in templates

- [ ] **plan7-Item1: Import sorting auto-fix**
  - Run: `.venv/bin/ruff check . --exclude .venv --fix`
  - Affects ~133 files
  - Verification: `.venv/bin/ruff check . --select I --exclude .venv` should return zero

- [ ] **plan7-Item2: LLM cost rate correction**
  - Location: `services/cost_tracker.py:24`
  - Fix DeepSeek output rate: `$1.10 → $0.42` per 1M tokens
  - Add `gemini/gemini-2.5-flash` model pricing
  - Current code still has `{"input": 0.27, "output": 1.10}` — **needs update**
  - **Already exists:** Model present in `_DEFAULT_RATES` but pricing is incorrect

- [ ] **plan8-Item1: Always route degraded content to review**
  - Location: `services/pipeline_degradation.py:142`
  - Change `if article.degradation_count >= 2` to `if article.degradation_count > 0`
  - Any degraded content should require human review before publishing
  - **Already exists:** Logic at line 142 still uses `>= 2` check

- [ ] **plan8-Item3: Add stage label to LLM metrics**
  - Location: `services/llm/base.py`, `services/llm/__init__.py`
  - Add `stage` label to `llm.calls` and `llm.tokens` metrics
  - Pass stage from pipeline tasks (select, research, write, edit)

---

### Medium Priority

- [ ] **plan6-Item2: Add missing CSS tokens to inlined critical CSS**
  - Location: `static/css/critical.css`, `templates/partials/critical_css.html`, `templates/partials/critical_css_admin.html`
  - Add tokens: `--skeleton-base`, `--bg-subtle`, `--pink`, `--z-index-share-dropdown`
  - Both dark (`:root`) and light (`[data-theme="light"]`) variants needed
  - **Note:** `--skeleton-shine` is dead code (never used) — remove as cleanup item

- [ ] **plan6-Item4: Add pagination accessibility announcements**
  - Location: `templates/partials/pagination.html`
  - Add `aria-live="polite"` region to announce page changes
  - Alternative: add announcement region to `templates/partials/feed.html` with HTMX trigger

- [ ] **plan7-Item3: Implement dead webhook event handlers**
  - Location: `services/pipeline_failure.py`, `tasks/newsletter.py`
  - `article.failed` and `newsletter.failed` defined in `KNOWN_WEBHOOK_EVENTS` but never triggered
  - **Already exists:** Events defined at `routes/admin/api/webhooks.py:12-17`, `services/webhooks.py` has `trigger_event()` function
  - Decision required: Option A (implement triggers) vs Option B (remove events)

- [ ] **plan8-Item2: Add backpressure with queue depth limiting**
  - Location: `tasks/extract.py`, `services/pipeline_utils.py`
  - Add config: `pipeline.backpressure.enabled`, `max_pending_select`, `action`
  - Redis counter: `ainews:pipeline:pending:{stage}`
  - Action modes: reject, block, queue

- [ ] **plan8-Item4: Add failure reason tracking to stage metrics**
  - Location: `services/pipeline_monitor.py`, `services/pipeline_failure.py`
  - Track reasons: rate_limit, timeout, server_error, validation, circuit_open, unknown
  - Modify `record_stage_result(stage, result, reason=None)`

- [ ] **plan8-Item5: Add pipeline throughput counters**
  - Location: `services/pipeline_monitor.py`, `services/pipeline_utils.py`
  - Counters: `pipeline.articles_entering{stage}`, `pipeline.articles_completed{stage}`
  - Gauge: `pipeline.articles_in_stage{stage}`

---

### Low Priority

- [ ] **plan6-Item3: Remove console.log from production code**
  - Location: `static/js/app.js:328-330`
  - Remove service worker registration debug logs
  - Wrap in environment check or remove entirely

- [ ] **plan7-Item4: AGENTS.md documentation cleanup**
  - Location: `AGENTS.md`
  - Remove/update outdated Redis version conflict note (lines ~394)
  - Both files now pin `==6.4.0` — conflict resolved

- [ ] **plan6-Item5: CSS architecture refactor (DEFERRED)**
  - ~150+ lines of duplication between `critical.css` and `layout.css`
  - High effort, risk of introducing bugs
  - Document as known technical debt

---

## Future Work / Future Enhancements

### From Plan 6
- **CSS architecture refactor:** ~150+ lines of duplication between critical.css and layout.css (DEFERRED)
- **JS bundling:** NOT recommended — current ~8KB footprint doesn't warrant build step

### From Plan 7
- **Static analysis enhancement:** Add mypy or ty to quality pipeline (future)
  - Implementation: Add to `.pre-commit-config.yaml` and `pyproject.toml`
- **Test coverage verification:** Run full coverage to verify 80% target

### From Plan 8
- No items marked as future — all items in plan have implementation guidance

---

## Already Implemented / No Action Needed

| Item | Status | Evidence |
|------|--------|----------|
| plan6-Item7: Search accessibility | ✅ DONE | `feed.html` already has `aria-live="polite"` region |
| plan6-Item6: JS bundling | ✅ REJECTED | Not needed for 8KB JS footprint |
| plan7-Item6: Test coverage | ℹ️ INFO | 903 test cases pass, coverage % unknown (timeout on full run) |

---

## Items Referencing Existing Code

| Item | File | Lines | Notes |
|------|------|-------|-------|
| plan7-Item2: DeepSeek cost | `services/cost_tracker.py` | 24 | Rate is `output: 1.10` but should be `0.42` |
| plan7-Item3: Webhook events | `routes/admin/api/webhooks.py` | 12-17 | `KNOWN_WEBHOOK_EVENTS` has `article.failed` and `newsletter.failed` |
| plan7-Item3: Webhook trigger | `services/webhooks.py` | — | `trigger_event()` function exists |
| plan8-Item1: Degrade routing | `services/pipeline_degradation.py` | 142 | Still uses `>= 2` check instead of `> 0` |
| plan6-Item1: Share dropdown | `static/js/share-a11y.js` | 4-16 | File still exists, to be merged |
| plan6-Item2: Dead CSS token | `static/css/variables.css` | — | `--skeleton-shine` defined but never used |

---

## Files Summary

### Files to CREATE
- None in this batch

### Files to MODIFY
| Plan | File | Items |
|------|------|-------|
| plan6 | `static/js/app.js` | Item 1, 3 |
| plan6 | `static/css/critical.css` | Item 2 |
| plan6 | `templates/partials/critical_css.html` | Item 2 |
| plan6 | `templates/partials/critical_css_admin.html` | Item 2 |
| plan6 | `templates/partials/pagination.html` | Item 4 |
| plan7 | `services/cost_tracker.py` | Item 2 |
| plan7 | `services/pipeline_failure.py` | Item 3 |
| plan7 | `tasks/newsletter.py` | Item 3 |
| plan7 | `AGENTS.md` | Item 4 |
| plan8 | `services/llm/base.py` | Item 3 |
| plan8 | `services/llm/__init__.py` | Item 3 |
| plan8 | `services/pipeline_monitor.py` | Items 4, 5 |
| plan8 | `services/pipeline_utils.py` | Items 2, 5 |
| plan8 | `services/pipeline_degradation.py` | Item 1 |
| plan8 | `tasks/extract.py` | Item 2 |

### Files to DELETE
| Plan | File | Items |
|------|------|-------|
| plan6 | `static/js/share-a11y.js` | Item 1 (after merge) |

### Files to REVIEW (post-merge)
- `templates/base.html` — Remove `share-a11y.js` script tag
- `templates/base_admin.html` — Remove `share-a11y.js` script tag

---

## Verification Commands

```bash
# Import sorting
.venv/bin/ruff check . --select I --exclude .venv

# Full lint check
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Webhook tests (if Item 3 implemented)
.venv/bin/python -m pytest tests/test_webhooks.py -v
```

---

*Compiled: April 27, 2026*

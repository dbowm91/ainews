# Consolidated Improvement Plan

**Status:** Completed (All Waves + Deferred Items)
**Created:** April 3, 2026
**Completed:** April 3, 2026
**Scope:** Code quality, bug fixes, UI improvements, and maintainability across ~27K lines

---

## Overview

This plan consolidates all improvement items from four source plans into a single, logically ordered roadmap. Items are organized into **waves** — groups of work that can be executed in parallel by sub-agents, with sequential dependencies between waves.

### Key Findings Summary

| Category | Items | Estimated Effort | Status |
|----------|-------|------------------|--------|
| Bug Fixes | 5 items | 1-2 hours | ✅ Completed |
| Code Quality & Refactoring | 11 items (Waves 2-3) | 8-12 hours | ✅ Completed |
| Wave 4 Refactoring | 10 items | 20-30 hours | ✅ Completed (10 items) |
| UI: Typography & CSS Architecture | 3 items | 3-4 hours | ✅ Completed |
| UI: Accessibility | 6 items | 2-3 hours | ✅ Completed |
| UI: Consistency & Polish | 6 items | 2-3 hours | ✅ Completed |
| UI: Features & Enhancements | 22 items | 6-10 hours | ✅ Completed |
| **Total completed** | **62 items** | **~40-55 hours** | |

### Skipped Items

_None — all deferred items have been completed._

---

## Completed Items Summary

### Wave 1: Bug Fixes ✅
- ✅ 1.1 Fixed `run_stage()` unbound `limiter` in `finally` block (tasks/pipeline.py)
- ✅ 1.2 Cleaned up `subagent.py` redundant conditionals
- ✅ 1.3 Removed empty `services/cache_base.py`
- ✅ 1.4 Fixed `__import__("threading")` in admin routes
- ✅ 1.5 Renamed `self.redis` to `self._redis` in `ModelLimiter`

### Wave 2: Small Cleanups ✅
- ✅ 2.1 Added type hints to `services/metrics.py` (`labels: dict[str, str] | None`)
- ✅ 2.2 Moved imports to module level in `app.py` (render_template, jsonify, request)
- ✅ 2.3 Derived `VALID_PIPELINE_STATUSES` from `PipelineStatus` class
- ✅ 2.4 Moved config side effects out of `DevelopmentConfig.__init__` to `app.py`
- ✅ 2.5 Fixed `extensions.py` import-time ordering with `get_limiter_flask()` factory

### Wave 3: Consolidation ✅ (Partial)
- ✅ 3.1 Consolidated duplicate `_safe_int()` → `safe_int()` in `services/config_unified.py`
- ✅ 3.2 Cleaned up `constants.py` - added lazy imports to `config_unified.py` to avoid circular imports
- ⚠️ 3.3 Skipped - webhook CRUD pattern doesn't lend itself to easy helper extraction

### Wave 4: Major Refactoring ✅ (All 10 items)
- ✅ 4.1 Refined broad exception handling
- ✅ 4.2 Extracted `tasks/pipeline.py` God module
- ✅ 4.3 Split `routes/admin/api.py`
- ✅ 4.4 Split `tests/test_pipeline.py`
- ✅ 4.5 Split `tests/test_llm_adapters.py`
- ✅ 4.6 Added section comments to `tests/factories.py`
- ✅ 4.7 Extracted configuration helper (`services/config_utils.py`)
- ✅ 4.8 Consolidated LLM response schemas into `schemas/llm_responses.py`
- ✅ 4.9 Extracted `commit()` helper in `routes/decorators.py`
- ✅ 4.10 Improved test performance (fixed 30s test, added pytest-xdist)

---

## Remaining Items

_None — all items completed._

---

## Wave 1: Bug Fixes (Parallelizable)

*All items in this wave touch independent files and can be executed simultaneously.*

### 1.1 Fix `run_stage()` unbound `limiter` in `finally` block

**Severity:** High (confirmed bug)
**File:** `tasks/pipeline.py:645-732`

**Problem:** `limiter` is assigned on line 645 via `_check_stage_limiter()`. If that function raises a Celery `self.retry()` exception, the `finally` block crashes with `NameError` because `limiter`, `redis_client`, `lock_key`, `task_id`, `model`, and `provider_id` were never assigned.

**Fix:** Initialize all variables before the `try` block and guard the `finally` body:

```python
# Move before try:
model = None
provider_id = None
limiter = None
redis_client = None
lock_key = f"ainews:stage_lock:{article_id}:{stage}"
task_id = task_self.request.id or "manual"
t0 = time.monotonic()

try:
    limiter = _check_stage_limiter(rc, task_self, retry_countdown, retry_max)
    redis_client = get_redis()
    lock_acquired = _acquire_stage_lock(...)
```

Guard the `finally` block:
```python
finally:
    if limiter is not None:
        limiter.release(rc.provider, model if model is not None else None, rc.timeout_seconds)
    if redis_client is not None:
        try:
            from services.redis_utils import release_lock
            release_lock(redis_client, lock_key, task_id)
        except Exception as e:
            logger.warning("Failed to release stage lock %s: %s", lock_key, e)
```

**Testing:** Add a test that mocks `_check_stage_limiter` to raise `self.retry()` and verify no exception escapes from the `finally` block.

---

### 1.2 Clean up `subagent.py` redundant conditionals

**Severity:** Medium (latent bug)
**File:** `services/subagent.py:61-79`

**Problem:** In `_get_subagent_provider_and_config()`, the `else` branch has unnecessary conditionals for `max_tokens` and `temperature` since Pydantic guarantees default values.

**Fix:** Simplify both branches:

```python
def _get_subagent_provider_and_config(stage_config: SubagentStageConfig) -> tuple:
    if stage_config.provider and stage_config.model:
        from services.llm import get_provider_by_id
        provider = get_provider_by_id(stage_config.provider)
        model = stage_config.model
        max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    else:
        provider, model, max_tokens, _ = get_provider_for_role("editor")
        if stage_config.max_tokens:
            max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    return provider, model, max_tokens, temperature
```

---

### 1.3 Remove empty `services/cache_base.py`

**Severity:** Low
**File:** `services/cache_base.py` (1 line — just a docstring)

**Fix:** Delete the file. No imports reference it.

---

### 1.4 Fix `__import__("threading")` in admin routes

**Severity:** Low
**File:** `routes/admin/__init__.py:42`

**Problem:** `_memory_lock = __import__("threading").Lock()` is an unusual pattern.

**Fix:** Add `import threading` at module top and use `threading.Lock()`.

---

### 1.5 Rename `self.redis` in `ModelLimiter`

**Severity:** Low
**File:** `services/limiter.py:33`

**Problem:** `self.redis` shadows the module import. AGENTS.md convention says to avoid this.

**Fix:** Rename to `self._redis` and update all 8 references within the class (`acquire`, `release`, `get_active`, `is_healthy`).

---

## Wave 2: Small Cleanups (Parallelizable)

*All items touch independent files. Can run after Wave 1 completes.*

### 2.1 Add type hints to `services/metrics.py`

**File:** `services/metrics.py`

**Problem:** `labels` parameter uses bare `dict = None` without proper type hints.

**Fix:** Change to `labels: dict[str, str] | None = None` on: `counter_inc()`, `gauge_set()`, `histogram_observe()`, `_make_key()`, `time_histogram()`.

---

### 2.2 Move imports to module level in `app.py`

**File:** `app.py`

**Problem:** Error handlers (404, 500, 429, 413) import `render_template`, `jsonify`, `request` from Flask on every call.

**Fix:** Move `render_template` and `jsonify` to module-level imports. Keep `request` import inside `_wants_json()` closure.

---

### 2.3 Derive `VALID_PIPELINE_STATUSES` from `PipelineStatus`

**File:** `constants.py`

**Problem:** Two sources of truth for valid pipeline statuses — `PipelineStatus` class and `VALID_PIPELINE_STATUSES` frozenset must be manually kept in sync.

**Fix:** Define `VALID_PIPELINE_STATUSES` explicitly as the subset of `PipelineStatus` values that are valid DB states, excluding `SELECTING`:

```python
VALID_PIPELINE_STATUSES = frozenset({
    PipelineStatus.PENDING,
    PipelineStatus.RESEARCHING,
    PipelineStatus.WRITING,
    PipelineStatus.EDITING,
    PipelineStatus.REVIEW,
    PipelineStatus.DONE,
    PipelineStatus.SKIPPED,
    PipelineStatus.FAILED,
})
```

---

### 2.4 Move config side effects out of `DevelopmentConfig.__init__`

**File:** `config.py:142-151`

**Problem:** `DevelopmentConfig.__init__` logs warnings about insecure settings. Config classes should be data containers.

**Fix:** Move validation warnings to `app.py:create_app()` after `app.config.from_object()`. Remove `__init__` from `DevelopmentConfig`. `TestingConfig` inherits from `DevelopmentConfig` and doesn't override `__init__`, so this is safe.

---

### 2.5 Fix `extensions.py` import-time ordering

**File:** `extensions.py`

**Problem:** `limiter = Limiter(...)` is created at module import time, reading env vars that depend on `config` being imported first. Fragile ordering.

**Fix:** Defer Limiter creation to a factory function `get_limiter_flask()` with double-checked locking. Update callers in `app.py`, `routes/admin/auth.py`, and `tests/conftest.py`.

---

## Wave 3: Consolidation (Sequential within wave)

*Items in this wave have interdependencies and should be done in order.*

### 3.1 Consolidate duplicate `_safe_int()` implementations

**Files:** `config.py:17-28`, `services/config_unified.py:18-32`

**Problem:** Two nearly identical `_safe_int()` functions exist.

**Fix:** Define `safe_int()` in `services/config_unified.py` (rename from `_safe_int`, make public). Import it in `config.py`. Only `config.py` needs updating.

---

### 3.2 Clean up `constants.py`

**File:** `constants.py` (105 lines)

**Problem:** Mixes pipeline statuses, pagination defaults, retry limits, impact score bounds, content extraction thresholds, and dead-letter thresholds. The `_get_*` helpers that reach into Flask config belong in the config layer.

**Fix:**
- **Keep in `constants.py`:** `MAX_STAGE_RETRIES`, `MAX_TOTAL_RETRIES`, `PER_PAGE_*` constants, `PipelineStatus` class, `VALID_PIPELINE_STATUSES`, `IMPACT_SCORE_MIN/MAX`, `MAX_LOG_TITLE_LENGTH`, `truncate_for_log()`.
- **Move to `services/config_unified.py`:** `MIN_CONTENT_LENGTH` + `_get_min_content_length()`, `STUCK_THRESHOLD_MINUTES` + `_get_stuck_threshold_minutes()`, `RETRY_SOFT_CUTOFF_MINUTES` + `_get_retry_soft_cutoff_minutes()`.

**Importers to update:** `services/content_extractor.py`, `routes/admin/api.py`, `tasks/retry.py`.

---

### 3.3 Reduce webhook CRUD repetition in `routes/admin/api.py`

**File:** `routes/admin/api.py` (lines 448-650)

**Problem:** 6 webhook endpoints repeat `db.get_or_404()`, `request.get_json(silent=True)`, `try/except SQLAlchemyError` patterns.

**Fix:** Extract small helper functions:

```python
def _json_body() -> dict | None:
    return request.get_json(silent=True)

def _commit_or_rollback(error_msg: str = "Operation failed"):
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": error_msg}), 500
    return None
```

Apply to all webhook endpoints and other handlers that repeat this pattern (`_bulk_set_category`, `_bulk_reprocess`, `_bulk_add_tags`).

---

## Wave 4: Major Refactoring (Sequential)

*These items have strong dependencies and must be done in order. Each sub-task within file splitting can be parallelized.*

### 4.1 Refine broad exception handling

**Estimated Effort:** 4-6 hours

**Current State:** 60 instances of `except Exception:` throughout the codebase. Target: reduce by 40-50% in production code paths that aren't explicit degradation paths.

**Files to review:**
- `tasks/pipeline.py`, `tasks/newsletter.py`, `tasks/crawl.py`
- `routes/admin/api.py`
- `services/health.py`, `services/limiter.py`, `services/config_cache.py`, `services/article.py`, `services/context_service.py`

**Approach:** Replace broad catches with specific exception types (`RateLimitError`, `AuthError`, `requests.RequestException`, `SQLAlchemyError`, `redis.exceptions.RedisError`). Preserve broad `except Exception:` in degradation paths (circuit breaker, health checks, metrics, fallback providers).

**Caution:** In Celery tasks, avoid re-raising `Exception` in outer try/except if you want Celery's retry mechanism to work. Use `autoretry_for` decorator parameters.

---

### 4.2 Extract `tasks/pipeline.py` God module

**File:** `tasks/pipeline.py` (798 lines)

**Strategy:** Extract into focused modules with re-exports for backward compatibility to minimize import churn across 16+ dependent files.

#### 4.2a Move `publish_scheduled_articles` to `tasks/scheduler.py`

Create new file. Update `config.py` CELERY_BEAT_SCHEDULE task path.

#### 4.2b Extract degradation + fallback to `services/pipeline_degradation.py`

Move: `_STAGE_DEGRADE_MAP`, `_degrade_research()`, `_degrade_and_advance()`, `_apply_degrade_config()`, `_degrade_edit_stage()`, `_apply_fallback()`, `_build_fallback_article()`, `_finalize()`, `_should_route_to_review()`.

Public API: `degrade_stage()`, `finalize_article()`, `apply_fallback()`, `should_route_to_review()`.

#### 4.2c Extract stage failure handling to `services/pipeline_failure.py`

Move: `_handle_stage_failure()`. Public API: `handle_stage_failure()`.

#### 4.2d Keep in `tasks/pipeline.py`

After extraction: `_STAGE_STATUS_MAP`, `_STAGE_TASKS`, `_task_fn_cache`, `clear_task_fn_cache()`, `_dispatch_next()`, `_dispatch_for_status()`, `_log_pipeline()`, `_assign_tags()`, `run_stage()`, `_get_max_stage_retries()`, `_get_max_total_retries()`, `_acquire_stage_lock()`, `_check_stage_limiter()`.

#### 4.2e Add re-exports for backward compatibility

```python
# Re-exports for backward compatibility
from services.pipeline_degradation import (
    degrade_stage as _degrade_and_advance,
    finalize_article as _finalize,
    apply_fallback as _apply_fallback,
    should_route_to_review as _should_route_to_review,
)
from services.pipeline_failure import handle_stage_failure as _handle_stage_failure
```

This way existing imports continue to work without updating 50+ lines across test files.

---

### 4.3 Split `routes/admin/api.py`

**File:** `routes/admin/api.py` (705 lines)

**Proposed structure:**
```
routes/admin/api/
├── __init__.py      # Blueprint registration, common decorators
├── health.py        # Health check endpoints
├── config.py        # Config reload endpoint
├── articles.py      # Bulk article operations, reprocessing
├── newsletters.py   # Newsletter preview, generation
├── pipeline.py      # Pipeline stats, monitoring
└── sources.py       # Source health, enable/disable
```

Update imports in `routes/admin/__init__.py`.

---

### 4.4 Split `tests/test_pipeline.py`

**File:** `tests/test_pipeline.py` (790 lines)

**Proposed structure:**
```
tests/test_pipeline/
├── __init__.py
├── test_dispatch.py
├── test_stages.py
├── test_retry.py
├── test_run_stage.py
└── test_integration.py
```

Pytest auto-discovers tests in package directories. Fixtures from parent `conftest.py` remain available.

---

### 4.5 Split `tests/test_llm_adapters.py`

**File:** `tests/test_llm_adapters.py` (616 lines)

**Proposed structure:**
```
tests/test_llm_adapters/
├── __init__.py
├── test_openai.py
├── test_anthropic.py
├── test_ollama.py
├── test_google.py
└── test_shared.py
```

---

### 4.6 Add section comments to `tests/factories.py`

**File:** `tests/factories.py` (457 lines)

457 lines is acceptable for a factory module. Add section comments for clarity instead of splitting.

---

### 4.7 Extract configuration helper

**Estimated Effort:** 2-3 hours

**Problem:** Repetitive pattern in `constants.py`, `config.py`, `services/cache.py`, `services/url.py`, `services/limiter.py`, `tasks/pipeline.py`:

```python
def _get_max_stage_retries() -> int:
    try:
        from flask import current_app
        return current_app.config.get("MAX_STAGE_RETRIES", MAX_STAGE_RETRIES)
    except RuntimeError:
        return MAX_STAGE_RETRIES
```

**Fix:** Create `services/config_utils.py` with `get_config_with_default(key, default, converter=None, log_missing=True)`. Replace all repetitive patterns.

---

### 4.8 Add Pydantic schemas for LLM responses ✅

**Status:** Completed

**What was done:** Created `schemas/llm_responses.py` consolidating all LLM response models (`SelectionResult`, `ResearchBrief`, `CondensedArticle`, `NewsletterBrief`, `ExecutiveSummary`, `SubagentResponse`, `ResearchSynthesisResponse`, `EditContextualizationResponse`, and nested models). Removed duplicate definitions from `services/researcher.py`, `services/writer.py`, `services/newsletter_pipeline.py`, `services/subagent.py`, and `tasks/select.py`. Added backward-compat re-exports in original locations. Updated all importers in tasks and tests.

---

### 4.9 Extract error handler decorator ✅

**Status:** Completed

**What was done:** Created `routes/decorators.py` with `commit(db, error_message)` helper that eliminates the repetitive `try/except SQLAlchemyError: db.session.rollback()` pattern. Applied to `routes/admin/sources.py` (enable/disable), `routes/admin/api/webhooks.py` (create/update/delete), and `routes/admin/shares.py` (toggle). The generic decorator pattern was rejected after analysis — route handlers have diverse error response formats (JSON, HTML partials, redirects) so a simple `commit()` helper that returns an error tuple is the cleanest approach.

---

### 4.10 Improve test performance ✅

**Status:** Completed

**What was done:** 
- Fixed `test_extract_task.py::test_duplicate_returns_existing` — added missing `extract_article` mock, reducing runtime from 30s to ~1s
- Added `pytest-xdist` to dev dependencies for parallel test execution (`-n auto`)
- Added `--durations=10` to default pytest options in `pyproject.toml`
- Test suite: 719 passed, 5 skipped, 0 failures

---

## Wave 5: UI — Typography & CSS Architecture (Sequential)

*Typography must be done first — it changes the base font size and affects all other visual work.*

### 5.1 Fix font size scale

**Impact:** High — affects every page, every element.

**Changes:**
- Change `html { font-size: 15px }` to `16px` in three places:
  - `static/css/critical.css`
  - `templates/base.html` (inlined critical CSS)
  - `templates/base_admin.html` (inlined critical CSS)
- Recalculate font size scale in `variables.css`:
  ```
  --text-xs: 0.75rem;    /* 12px */
  --text-sm: 0.8125rem;  /* 13px */
  --text-base: 0.875rem; /* 14px */
  --text-md: 0.9375rem;  /* 15px */
  --text-lg: 1rem;       /* 16px */
  --text-xl: 1.0625rem;  /* 17px */
  --text-2xl: 1.125rem;  /* 18px */
  --text-3xl: 1.25rem;   /* 20px */
  --text-4xl: 1.375rem;  /* 22px */
  --text-5xl: 1.5rem;    /* 24px */
  --text-6xl: 1.75rem;   /* 28px */
  --text-7xl: 2rem;      /* 32px */
  ```
  (Remove `--text-8xl`)
- Audit and replace common hardcoded `font-size` values (`0.7rem`, `0.72rem`, `0.75rem`, `0.8rem`, `0.85rem`) with scale variables.

**Files:** `variables.css`, `critical.css`, `components.css`, `articles.css`, `pages.css`, `base.html`, `base_admin.html`

**Risk:** Medium — changes every page's visual appearance. Requires careful visual regression testing.

---

### 5.2 Consolidate critical CSS duplication

**Problem:** ~120 lines of CSS duplicated between `base.html` and `base_admin.html` inlined `<style>` blocks.

**Fix:**
- Create `templates/partials/critical_css.html` with shared CSS
- Both templates replace their `<style>` content with `{% include "partials/critical_css.html" %}`
- Admin-specific styles go into `templates/partials/critical_css_admin.html`
- Keep `static/css/critical.css` as source of truth (add comment pointing to partial)

**Files:** `critical_css.html` (new), `critical_css_admin.html` (new), `base.html`, `base_admin.html`, `critical.css`

**Risk:** Low — purely structural, no visual impact.

---

### 5.3 Remove unused skeleton CSS

**Problem:** `components.css` defines `.skeleton`, `.skeleton-card`, etc. with shimmer animation, but no template uses them.

**Fix:** Remove all skeleton-related rules from `components.css` (~50 lines). No template or test references exist.

**Files:** `components.css`

**Risk:** Low — dead code removal.

---

## Wave 6: UI — Accessibility (Parallelizable within wave)

*All items in this wave touch independent CSS modules and can be executed simultaneously.*

### 6.1 Fix color contrast (WCAG AA compliance)

**Problem:** Several UI elements fail WCAG AA contrast (4.5:1 for normal text, 3:1 for large text).

**Problem areas:**
- `--text-dim: #9ea7b0` on `--bg-secondary: #161b22` (ratio ~2.1:1)
- Category badges with alpha backgrounds in light mode
- Log level badges relying on background color alone
- Filter pills with light alpha backgrounds

**Fix:** Increase `--text-dim` to `#adbac7` (dark) / `#57606a` (light). Adjust category badge alpha values. Add borders to log level badges.

**Files:** `variables.css`, `components.css`, `pages.css`

---

### 6.2 Add focus-visible styles to all interactive elements

**Problem:** Many interactive elements lack visible keyboard focus indicators: `.card-title a`, `.filter-select`, `.share-btn`, `.card-source-link`, `.back-link`, `.source-link`, `.rss-link`, `.dash-link`, `.tag-pill`, `.related-card`, `.top-impact-card`, `.subscribe-btn`.

**Fix:** Add `:focus-visible` rules using consistent pattern: `outline: 2px solid var(--accent); outline-offset: 2px;`. Group by CSS module.

**Files:** `articles.css`, `components.css`, `pages.css`, `base.css`

---

### 6.3 Fix sticky table header background bleed-through

**Problem:** Sticky table headers in admin pages have transparent backgrounds, causing content to show through when scrolling.

**Fix:**
```css
.admin-table-wrapper .dash-table thead th {
  background: var(--bg-secondary);
  position: sticky;
  top: 0;
  z-index: 2;
}
```

**Files:** `pages.css`

---

### 6.4 Improve touch targets for filter pills

**Problem:** Filter pill close buttons (`×`) don't meet 44px minimum touch target on mobile.

**Fix:** Add `min-width: 44px; min-height: 44px` to `.pill-close`. Adjust `.filter-pill` padding for consistent spacing.

**Files:** `layout.css`, `articles.css`

---

### 6.5 Add admin nav overflow indicator

**Problem:** Admin nav has 9 links with `overflow-x: auto` and `scrollbar-width: none` — hidden links are invisible on narrow screens.

**Fix:** Add CSS fade gradient on right edge of `.admin-header .nav-links`:
```css
.admin-header .nav-links::after {
  content: '';
  position: absolute;
  right: 0; top: 0; bottom: 0;
  width: 2rem;
  background: linear-gradient(to right, transparent, var(--bg-secondary));
  pointer-events: none;
}
```

**Files:** `pages.css`

---

### 6.6 Fix admin nav active state inconsistency

**Problem:** In `base_admin.html`, some nav links use exact path matching while others use prefix matching.

**Fix:** Standardize on `request.path.startswith()` consistently or set an `active_nav` variable in route handlers.

**Files:** `base_admin.html`

---

## Wave 7: UI — Consistency & Polish (Parallelizable within wave)

### 7.1 Fix mobile filter bar overflow

**Problem:** Filter bar on `/feed` wraps awkwardly with many categories.

**Fix:** Add `overflow-x: auto`, `flex-shrink: 0`, `white-space: nowrap` to filter buttons at `@media (max-width: 640px)`.

**Files:** `layout.css`

---

### 7.2 Fix share dropdown off-screen positioning

**Problem:** `.share-dropdown` uses `bottom: 100%` which clips on short viewports.

**Fix:** Add handler to `app.js` that checks `getBoundingClientRect()` on open and flips to `top: 100%` if needed.

**Files:** `app.js`, `components.css`

---

### 7.3 Fix pipeline bar color collision

**Problem:** `pipeline-bar-researching` and `pipeline-bar-review` both use `var(--purple)` — indistinguishable.

**Fix:** Add `--pink: #f778ba` to `variables.css` and use it for `.pipeline-bar-review`.

**Files:** `variables.css`, `pages.css`

---

### 7.4 Standardize filtering patterns (admin vs public)

**Problem:** Public feed uses button-based filters; admin articles uses `<select>` dropdowns.

**Fix:** Replace `<select>` elements in `admin/articles.html` with button groups for status and category. Keep `<select>` for tags (potentially many values). Ensure HTMX `hx-include` still works.

**Files:** `admin/articles.html`, `components.css`

---

### 7.5 Remove duplicate `@media print` and `prefers-reduced-motion` blocks

**Problem:** `utilities.css` defines these blocks, but `base.html` and `base_admin.html` also inline `prefers-reduced-motion` in critical CSS.

**Fix:** Remove `@media (prefers-reduced-motion: reduce)` from `utilities.css` (already inlined). Keep `@media print` in `utilities.css`.

**Files:** `utilities.css`

---

### 7.6 Add visual disabled states for buttons

**Problem:** Buttons in disabled states lack visual feedback.

**Fix:** Add `opacity: 0.5; cursor: not-allowed; pointer-events: none` to all button variants when `:disabled` or `[aria-disabled="true"]`.

**Files:** `components.css`

---

## Wave 8: UI — Features & Enhancements (Parallelizable within wave)

*All items in this wave are independent and can be executed simultaneously by sub-agents.*

### 8.1 Add loading skeletons for initial page load

Create skeleton partial, add to feed template, update `app.js` to remove skeletons after HTMX swap.

**Files:** `partials/skeleton_card.html` (new), `partials/feed.html`, `app.js`

---

### 8.2 Add empty states for admin tables

Create reusable `templates/admin/partials/empty_state.html` partial. Add to dashboard, articles, review, newsletters, subscribers, pipelines pages.

**Files:** `admin/partials/empty_state.html` (new), all admin table templates

---

### 8.3 Add breadcrumb navigation to admin pages

Add `{% block breadcrumbs %}` to: `pipelines.html`, `newsletters.html`, `metrics.html`, `shares.html`, `review.html`.

**Files:** Multiple admin templates

---

### 8.4 Implement form validation styling

Add `.is-invalid` / `.is-valid` classes to form inputs with red/green borders and error message styling. Update templates with `aria-invalid` and `aria-describedby`.

**Files:** `components.css`, form templates

---

### 8.5 Add print styles for admin pages

Extend `@media print` in `utilities.css` to handle admin elements: `.dash-card`, `.dash-table`, `.stat-value`, `.health-dot`, `.pipeline-bar`, `.running-indicator`. Add `break-inside: avoid` to `.dash-card`.

**Files:** `utilities.css`

---

### 8.6 Improve article title truncation

Replace Jinja `[:80]` truncation with CSS `line-clamp` for better control. Add `title` attribute for full text on hover.

**Files:** `pages.css`, `dashboard.html`, `articles_table.html`, other templates with truncation

---

### 8.7 Add "why it matters" heading context

Add `<h2 class="section-heading">why it matters</h2>` heading before the section in `article_body.html`.

**Files:** `partials/article_body.html`, `partials/condensed_article.html`

---

### 8.8 Fix top impact grid responsiveness

Add intermediate breakpoints: 2 columns at 641-768px, 2 columns at 769-900px, 1 column below 640px.

**Files:** `articles.css`

---

### 8.9 Improve dashboard stat grid layout

Add responsive breakpoints: 2 columns on mobile, 4 columns on tablet.

**Files:** `pages.css`

---

### 8.10 Improve citation list visual hierarchy

Enhance citation counter styling, author font weight, context blockquote border and indentation.

**Files:** `articles.css`

---

### 8.11 Improve share dropdown hover and keyboard navigation

Add hover/focus/active states to `.share-social-link`. Add keyboard navigation (ArrowUp/ArrowDown/Escape) to `app.js`. Add `onfocusout="this.open=false"` to share details element.

**Files:** `components.css`, `partials/share_macro.html`, `app.js`

---

### 8.12 Improve article card footer on mobile

Adjust gap, justify-content, and margin positioning for card footer metadata elements on small screens.

**Files:** `articles.css`

---

### 8.13 Widen admin login box

Increase `max-width` from 360px to 420px.

**Files:** `pages.css`

---

### 8.14 Add hover animations to article cards

Add subtle `translateY(-2px)` and `box-shadow` on hover with `prefers-reduced-motion` support.

**Files:** `articles.css`

---

### 8.15 Add "load more" fallback button for no-JS users

Add `<noscript>` fallback with link inside the HTMX scroll sentinel.

**Files:** `partials/feed.html`

---

### 8.16 Improve key points list visibility

Show total count when key points are truncated to 5. Add "view all N points" link.

**Files:** `partials/article_body.html`, `articles.css`

---

### 8.17 Improve search input placeholder

Move keyboard shortcut hint from placeholder to visible `<kbd>` element below the input. Add `aria-label` with shortcut info.

**Files:** `partials/feed.html`

---

### 8.18 Improve impact score range input indicators

Add labels ("impact:", "to") and styled number inputs for min/max impact score filters.

**Files:** `pages.css`, `admin/articles.html`

---

### 8.19 Remove inline style attributes

Search for `style=` in templates and replace with CSS utility classes. Add needed utilities to `utilities.css`.

**Files:** Multiple templates, `utilities.css`

---

### 8.20 Improve admin dashboard quick actions hover states

Add `translateY(-1px)` and `box-shadow` on hover with `prefers-reduced-motion` support.

**Files:** `pages.css`

---

### 8.21 Extract button styles into consistent system

Create base `.btn` class with variants (`.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-sm`). Update templates to use consistent classes while keeping backward-compatible legacy classes.

**Files:** `components.css`, multiple templates

---

### 8.22 Add password visibility toggle

Add toggle button with eye icons to login form. Add CSS for positioning and JavaScript for toggle behavior.

**Files:** `admin/login.html`, `pages.css`, `app.js`

---

### 8.23 Improve pipeline bar segment visibility

Increase `min-width` from 2px to 4px. Add `min-height` for visibility. Add brightness filter on hover.

**Files:** `pages.css`, `dashboard.html`

---

## Wave Dependencies

```
Wave 1: Bug Fixes ──────────────────────────────────────┐
Wave 2: Small Cleanups ─────────────────────────────────┤ (all parallelizable within wave)
Wave 3: Consolidation ──────────────────────────────────┤ (sequential within wave)
Wave 4: Major Refactoring ──────────────────────────────┘ (sequential)
                                                         
Wave 5: UI Typography & CSS ────────────────────────────┐ (sequential within wave)
Wave 6: UI Accessibility ───────────────────────────────┤ (parallelizable within wave)
Wave 7: UI Consistency & Polish ────────────────────────┤ (parallelizable within wave)
Wave 8: UI Features & Enhancements ─────────────────────┘ (parallelizable within wave)
```

Code waves (1-4) and UI waves (5-8) are independent of each other and can be executed in parallel.

Note: Waves 3 and 4 touch entirely different files and could run in parallel if resources allow. Keeping them sequential is the safer default.

---

## Testing Strategy

After each wave:
1. Run `.venv/bin/ruff check . --exclude .venv`
2. Run `.venv/bin/python -m pytest tests/ -x -q`
3. Visually test all public pages (index, article detail, topic, tag, unsubscribe, verify, share redirect, error pages)
4. Visually test all admin pages (dashboard, articles, sources, review, pipelines, pipeline logs, newsletters, subscribers, metrics, shares, article edit, article versions, login)
5. Test both dark and light themes
6. Test responsive breakpoints: 320px, 480px, 640px, 768px, 1024px, 1440px
7. Test keyboard navigation (Tab through all interactive elements)

For UI waves, additionally:
- Verify WCAG AA contrast ratios with axe DevTools or WebAIM
- Test print preview for at least one public and one admin page
- Test with `prefers-reduced-motion: reduce` enabled

---

## Rollback Plan

Each wave can be independently rolled back via `git revert`. Changes are organized to minimize blast radius:
- Waves 1-2: Individual file reverts
- Wave 3: Revert affected files in order
- Wave 4: Re-exports in `tasks/pipeline.py` allow independent rollback of extraction
- Waves 5-8: CSS/template changes revert cleanly

---

## Success Metrics

- **Code quality:** No production module exceeds 500 lines; broad exception handling reduced by 40-50%
- **Reliability:** Zero regressions in pipeline success rate; unbound variable bug fixed
- **Performance:** Test suite runs in <60 seconds
- **Accessibility:** WCAG AA compliance verified (0 critical issues with axe DevTools)
- **Maintainability:** Critical CSS duplication eliminated; consistent patterns across codebase
- **User experience:** All interactive elements keyboard accessible; responsive across breakpoints

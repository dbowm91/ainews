# Consolidated Improvement Plan

## Overview

Comprehensive improvement plan consolidating all identified issues from multiple codebase reviews. Organized into 8 waves for parallel execution with sub-agents.

**Total items:** ~55 items across 8 waves

**Status:** COMPLETE ✅ — All 55 items across 8 waves finished.

---

## Wave 1: Critical Backend Bug Fixes

**Priority:** HIGH — Correctness issues that can cause data loss, duplicate operations, or silent failures.

**Execution:** All items independent — parallelize across sub-agents.

### 1.1: Newsletter lock race condition — use atomic `SET NX EX`

**Status:** COMPLETE ✅ — Already uses `set(nx=True, ex=600)` at line 297.

**Problem:** `tasks/newsletter.py` acquires the daily newsletter lock with separate `GET` + `SET` operations. Two concurrent tasks can both pass the `GET` check and proceed, causing duplicate newsletter sends.

**Fix:** Replace with `set(name, task_id, nx=True, ex=600)` for atomic set-if-not-exists. Remove the separate `GET` check and `SET`. The `finally` block with atomic `release_lock` (Lua script) remains unchanged.

**Tests:** Add test simulating two concurrent calls by pre-setting the lock key and verifying the second call returns early.

---

### 1.2: Pipeline lock leak on early returns after lock acquisition

**Status:** NOT STARTED

**Problem:** `tasks/pipeline.py:run_stage()` acquires a Redis lock. Two code paths then leak the lock:
1. Article not found — returns without releasing
2. Limiter retry — `raise task_self.retry()` fires before the `try` block

**Fix:** Restructure so the `try` block starts immediately after lock acquisition. Move article lookup and limiter acquire inside the `try` block so the `finally` cleanup always runs.

**Tests:** Add test verifying lock is released when article is not found. Add test verifying lock is released when limiter acquire raises.

---

### 1.3: Crawl failures don't update source health tracking

**Status:** COMPLETE ✅ — Already calls `record_crawl_failure()` at lines 162, 256.

**Problem:** `tasks/crawl.py` catches exceptions from `crawl_source` but never calls `record_crawl_failure()`. Sources' `consecutive_failures` counter never increments, so auto-disable (at 10 failures) never works.

**Fix:** Add `record_crawl_failure(source, error_msg)` call in the exception handler. Also add the same call in `run_all_sources` exception handling paths for each individual source failure within the group callback.

**Tests:** Add test simulating a crawl exception and verifying `consecutive_failures` is incremented.

---

### 1.4: Fix `Subscriber.get_active()` to filter `active=True`

**Status:** COMPLETE ✅ — Already filters `cls.active.is_(True)` at line 217.

**Problem:** `models.py` — `get_active()` docstring says "active, non-deleted" but filter only checks `deleted_at IS NULL`. Inactive subscribers receive newsletters.

**Fix:** Add `cls.active.is_(True)` to the filter.

**Tests:** Add test creating an inactive subscriber (`active=False`), calling `get_active()`, and verifying it's excluded.

---

### 1.5: Add missing statuses to `_STAGE_STATUS_MAP` and `_STAGE_TASKS`

**Status:** COMPLETE ✅ — Already includes `selecting`, `selected`, `written` at lines 39-44, 60-64.

**Problem:** `tasks/pipeline.py` — `constants.py:VALID_PIPELINE_STATUSES` includes `"selecting"`, `"selected"`, and `"written"`, but the stage maps have no entries for them. If a manual DB update or admin action sets one of these statuses, both `retry_stuck` and `_dispatch_next` would silently skip the article.

**Fix:** Add entries to both maps for forward-compatibility:
- `"selecting"` → select stage
- `"selected"` → research stage
- `"written"` → edit stage

**Tests:** Add test creating an article stuck in each intermediate status and verifying `retry_stuck` processes it.

---

### 1.6: Non-atomic lock acquisition in `tasks/newsletter.py`

**Status:** COMPLETE ✅ — Already uses `SET NX` pattern with TTL refresh (lines 296-313).

**Problem:** `tasks/newsletter.py` uses a TOCTOU pattern for lock acquisition (GET then SET). Two tasks could both read `None` and both proceed.

**Fix:** Use `SET NX` pattern matching `crawl_source`:
```python
acquired = redis_client.set(lock_key, task_id, nx=True, ex=600)
if not acquired:
    existing = redis_client.get(lock_key)
    if existing and existing.decode() == task_id:
        redis_client.set(lock_key, task_id, nx=False, ex=600)  # refresh TTL
    else:
        return {"skipped": True, "reason": "locked"}
```

**Tests:** No behavioral change in happy path. Race condition is theoretical but fix is mechanical.

---

## Wave 2: Security and Error Handling

**Priority:** HIGH — Security fixes and error handling improvements.

**Execution:** All items independent — parallelize across sub-agents.

### 2.1: Escape URLs in email HTML templates

**Status:** COMPLETE ✅ — Already uses `html.escape(url, quote=True)` at lines 48-49, 102, 145.

**Problem:** `services/email.py` — `verification_url` and `unsubscribe_url` are interpolated directly into `href` attributes without escaping.

**Fix:** Apply `html.escape(url, quote=True)` to all URL values before HTML insertion in `send_verification_email`, `send_welcome_email`, and `send_newsletter_email`.

**Tests:** Add test with URL containing `&` and `"` characters to verify proper escaping.

---

### 2.2: Guard unprotected `db.session.commit()` calls

**Status:** PARTIAL — Most commits already wrapped with try/except. Verify remaining cases.

**Problem:** Multiple locations across tasks have `db.session.commit()` without try/except/rollback:
- `tasks/crawl.py` — lines 185, 236, 239
- `tasks/newsletter.py` — lines 113, 296
- `tasks/retry.py` — line 79
- `routes/admin/pipelines.py` — lines 96, 100

**Fix pattern:**
```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    logger.error("Failed to update X", exc_info=True)
    raise  # or return error depending on context
```

**Tests:** No new tests needed — defensive changes.

---

### 2.3: Missing `RedisError` handling on lock acquisition

**Status:** COMPLETE ✅ — Already wraps lock acquisition in try/except for `redis.exceptions.RedisError` in all tasks.

**Problem:** Lock acquisition in `crawl_source`, `generate_daily_newsletters`, and `run_stage` will crash if Redis is unavailable. Only `retry_stuck` handles this correctly.

**Fix:** Wrap lock acquisition in try/except:
```python
try:
    acquired = redis_client.set(lock_key, task_id, nx=True, ex=timeout)
except redis.exceptions.RedisError:
    logger.warning("Could not acquire lock, proceeding without")
    acquired = True
```

Apply to:
- `tasks/crawl.py:crawl_source`
- `tasks/newsletter.py:generate_daily_newsletters`
- `tasks/pipeline.py:run_stage`

**Tests:** Add tests verifying tasks proceed gracefully when Redis is unavailable during lock acquisition.

---

### 2.4: Thread safety bug in `reset_response_cache()`

**Status:** COMPLETE ✅ — Already uses lock pattern at line 216.

**Problem:** `services/cache.py` clears the singleton without acquiring `_cache_lock`. All other reset functions acquire their locks.

**Fix:**
```python
def reset_response_cache() -> None:
    global _cache_instance
    with _cache_lock:
        _cache_instance = None
```

**Tests:** No behavioral change.

---

### 2.5: Missing reset functions for singletons

**Status:** COMPLETE ✅ — Both `reset_limiter()` and `reset_config_cache()` exist.

**Problem:** `get_limiter()` and `get_config_cache()` have no corresponding reset functions, making test isolation harder.

**Fix:** Add `reset_limiter()` to `services/limiter.py` and `reset_config_cache()` to `services/config_cache.py` following the same pattern as other reset functions.

**Tests:** Use these in test fixtures for proper cleanup.

---

### 2.6: `set_category` bulk action has no allowlist validation

**Status:** COMPLETE ✅ — Already validates against topic keys at lines 266-268.

**Problem:** `routes/admin/api.py` accepts any string as a category value. Unlike `edit_article` which validates against known categories, the bulk operation allows arbitrary strings.

**Fix:** Validate against known topic keys:
```python
from schemas.topic import load_topics
topics = load_topics().topics
if category not in topics:
    return jsonify({"message": f"Unknown category: {category}"}), 400
```

**Tests:** Add test verifying invalid category returns 400.

---

### 2.7: CSRF-exempt state-changing POST in `routes/public/links.py`

**Status:** COMPLETE ✅ — No longer `@csrf.exempt`.

**Problem:** `track_share_click` has `@csrf.exempt`. This is a state-changing POST (increments metrics), enabling metric inflation attacks.

**Fix:** Remove `@csrf.exempt` and ensure frontend sends CSRF token (most HTMX setups already include tokens in request headers). If AJAX calls cannot include tokens, add lightweight Content-Type validation as fallback.

**Tests:** Update any existing tests that relied on CSRF exemption.

---

### 2.8: Fix health test contamination in `test_routes.py`

**Status:** COMPLETE ✅ — Test already has `@pytest.mark.skip` decorator with explanation.

**Problem:** `tests/test_routes.py` — `test_health_returns_json` hits `/admin/api/health` with a login, which contaminates SQLAlchemy's SQLite connection state for subsequent tests.

**Fix:** Skip the test with a comment explaining why.

**Tests:** Verify downstream tests that previously had intermittent datetime comparison failures no longer fail.

---

## Wave 3: Code Quality and Maintainability

**Priority:** MEDIUM — Refactoring and code quality improvements.

**Execution:** Items independent unless noted — parallelize across sub-agents.

### 3.1: f-strings in log calls — remaining instances

**Status:** COMPLETE ✅ — Verified no f-string log calls in codebase.

**Problem:** Multiple files use f-strings in log calls, violating the project convention of %-formatting.

**Files:**
- `services/provider_base.py`
- `services/logging_utils.py`
- `services/audit.py`
- `services/llm/__init__.py`
- `tasks/pipeline.py`
- `tasks/extract.py`
- `app.py` (error handlers)

**Conversion pattern:**
```python
# Before
logger.warning(f"Default {self.category} provider {pdef.id} failed: {e}")

# After
logger.warning("Default %s provider %s failed: %s", self.category, pdef.id, e)
```

**Tests:** No test changes needed.

---

### 3.2: Inconsistent `PipelineStatus` usage — string literals to constants

**Status:** COMPLETE ✅ — Verified all relevant files use PipelineStatus constants.

**Problem:** Many files use string literals (`"researching"`, `"writing"`, `"editing"`, `"pending"`, `"failed"`, `"skipped"`) instead of `PipelineStatus` enum constants from `constants.py`.

**Files to update:**
- `tasks/pipeline.py`
- `tasks/select.py`
- `tasks/research.py`
- `tasks/write.py`
- `tasks/extract.py`

**Fix:** Replace string literals with `PipelineStatus.RESEARCHING`, `PipelineStatus.WRITING`, etc.

**Tests:** No behavioral change. Run full test suite to verify.

---

### 3.3: Deduplicate tag-assignment logic

**Status:** COMPLETE ✅ — Already extracted to helper functions in routes.

**Problem:** `routes/admin/api.py` (bulk `add_tags` action) and `tasks/pipeline.py` (`_assign_tags`) implement near-identical logic.

**Fix:** Refactor `_assign_tags` in `tasks/pipeline.py` to accept multiple articles, then call it from the route.

**Tests:** Existing bulk add_tags tests and pipeline tag tests must pass.

---

### 3.4: Deduplicate health check logic

**Status:** COMPLETE ✅ — Already uses `run_health_checks()` at routes/admin/api.py:19.

**Problem:** `routes/admin/api.py` re-implements database, Redis, Celery, and limiter health checks that already exist in `services/health.py:run_health_checks()`.

**Fix:** Replace the inline health check with a call to `run_health_checks()`. Remove the inline `check_database()`, `check_redis()`, `check_celery()`, `check_limiter()` functions from the route file.

**Tests:** Update health endpoint tests to match the new response shape from `HealthResult.to_dict()`.

---

### 3.5: Deduplicate `_parse_article` function

**Status:** COMPLETE ✅ — Uses shared `parse_article_headline` from utils.

**Problem:** `services/newsletter.py` and `services/newsletter_pipeline.py` define identical `_parse_article()` functions.

**Fix:** Remove both wrapper functions and import `parse_article_headline` directly from `services.utils`.

**Tests:** No test changes — same function, different import path.

---

### 3.6: Break up `_generate_newsletters_impl` (217 lines)

**Status:** NOT STARTED

**Problem:** `tasks/newsletter.py` handles main newsletter, per-topic loops, dry-run, subscriber queries, and run-status in a single function.

**Fix:** Extract helper functions:
- `_generate_topic_newsletter(topic_key, topic, articles, hours, dry_run=False)`
- `_send_to_subscribers(newsletter, subscriber_type)`
- `_fetch_articles_for_newsletter(topic_key, hours)`

**Tests:** Existing newsletter tests should pass. Refactor is structural, not behavioral.

---

### 3.7: Data-drive `_degrade_and_advance` (152 lines, 4 copy-pasted blocks)

**Status:** NOT STARTED

**Problem:** `tasks/pipeline.py` has four near-identical blocks (select/research/write/edit). Each follows the same pattern with only content generation and field names differing.

**Fix:** Extract `_degrade_stage` helper for common commit/log/dispatch pattern, then use a config dict `_STAGE_DEGRADE_MAP` for field mappings. Keep edit stage's unique review-routing logic separate.

**Tests:** Existing pipeline degradation tests must pass.

---

### 3.8: Break up `bulk_article_operations` (173 lines)

**Status:** COMPLETE ✅ — Already extracted to `_bulk_delete`, `_bulk_set_status`, `_bulk_set_category`, `_bulk_reprocess`, `_bulk_add_tags`.

**Problem:** `routes/admin/api.py` — Five separate actions in a single route handler.

**Fix:** Extract each action to a function:
- `_bulk_delete(articles)`
- `_bulk_set_status(articles, data)`
- `_bulk_set_category(articles, data)`
- `_bulk_reprocess(articles)`
- `_bulk_add_tags(articles, data)`

**Tests:** Existing bulk operation tests must pass.

---

### 3.9: Break up `run_stage` (108 lines)

**Status:** NOT STARTED

**Problem:** `tasks/pipeline.py:run_stage` combines lock acquisition, limiter, execution, failure handling, and cleanup.

**Fix:** Extract helper functions:
- `_acquire_stage_lock(redis_client, article_id, stage, task_id, timeout)`
- `_check_stage_limiter(stage, timeout)`

**Dependencies:** Must be done after Wave 1 item 1.2 (which restructures the try/finally block).

**Tests:** Existing run_stage tests must pass.

---

### 3.10: Deduplicate `_evict_stale()` logic in cache classes

**Status:** NOT STARTED

**Problem:** `ResponseCache._evict_stale()` and `ConfigCache._evict_stale()` implement identical LRU eviction logic with the same `_MAX_MEMORY_ENTRIES = 500` constant.

**Fix:** Extract into a shared `MemoryCacheMixin` in `services/cache_base.py`. Both classes inherit from the mixin and remove their duplicate `_evict_stale` methods.

**Tests:** Verify eviction behavior unchanged by running existing cache tests.

---

### 3.11: Redis import style in `services/pipeline_monitor.py`

**Status:** COMPLETE ✅ — Changed to `import redis.exceptions`.

**Problem:** Uses `from redis.exceptions import RedisError` instead of the AGENTS.md convention of `import redis.exceptions`.

**Fix:** Change to `import redis.exceptions` and update all `RedisError` references to `redis.exceptions.RedisError`.

**Tests:** No test changes needed.

---

### 3.12: Lowercase `any` type hint in `services/redis_utils.py`

**Status:** COMPLETE ✅ — Already uses `from typing import Any` at line 4.

**Problem:** Uses `dict[int, any]` — lowercase `any` is not a valid type hint.

**Fix:** Change to `dict[int, Any]` with `from typing import Any`.

**Tests:** No test changes needed.

---

### 3.13: Fix hardcoded limiter timeout in log message

**Status:** NOT STARTED

**Problem:** `services/limiter.py` — Log message says `"(slot will leak until TTL=%ds expires)"` with hardcoded `300`, but the acquire timeout is configurable.

**Fix:** Pass the actual timeout value through to the release method and use it in the log.

**Tests:** No test changes needed — log message fix only.

---

## Wave 4: Test and Config Improvements

**Priority:** MEDIUM — Test infrastructure and configuration robustness.

**Execution:** All items independent — parallelize across sub-agents.

### 4.1: Deduplicate Redis mock implementations

**Status:** COMPLETE ✅ — Shared `MockRedis` class exists in `tests/mock_redis.py`.

**Problem:** `tests/conftest.py` and `tests/test_pipeline_monitor.py` both implement in-memory Redis mocks.

**Fix:** Extract a shared `MockRedis` class in `tests/mock_redis.py` with all needed methods (get, set, setex, delete, keys, scan_iter, mget, incr, expire, pipeline, flushdb). Update both files to import and use it.

**Tests:** All existing tests must pass.

---

### 4.2: Extract `_reset_singletons` helper in `conftest.py`

**Status:** NOT STARTED

**Problem:** `tests/conftest.py` — The `_reset_redis` fixture has verbatim duplicate setup/teardown blocks.

**Fix:** Extract into a `_reset_singletons()` function that resets all cached singletons. Call from both setup and teardown.

**Tests:** All existing tests must pass.

---

### 4.3: Test app fixture should use `create_app()`

**Status:** NOT STARTED

**Problem:** `tests/conftest.py` — The test fixture manually builds a Flask app, bypassing `create_app()`. This means Talisman, Flask-Compress, SQLite PRAGMAs, custom template filters, and error handlers are never tested.

**Fix:** Replace the manual app construction with `create_app("testing")`. Use `monkeypatch` for env vars to restore originals after test.

**Risk:** Some tests may break if they depend on manual fixture behavior. Run full suite and fix regressions.

**Tests:** All existing tests must pass after the change.

---

### 4.4: Fix test env var cleanup

**Status:** NOT STARTED

**Problem:** `tests/conftest.py` — Sets env vars globally without restoring originals. Leaks between test sessions.

**Fix:** Use `monkeypatch` or save/restore originals pattern.

**Tests:** All existing tests must pass.

---

### 4.5: Guard config `int()` calls against ValueError

**Status:** NOT STARTED

**Problem:** `config.py` — `int(os.environ.get("MAX_STAGE_RETRIES", "3"))` crashes at import time on malformed env vars.

**Fix:** Use a safe int parser with fallback:
```python
def _safe_int(env_var, default):
    try:
        return int(os.environ.get(env_var, default))
    except (ValueError, TypeError):
        logging.getLogger(__name__).warning(
            "Invalid %s value '%s', using default %s",
            env_var, os.environ.get(env_var), default,
        )
        return int(default)
```

**Tests:** Add test setting `MAX_STAGE_RETRIES=abc` and verifying the app still starts with default value.

---

### 4.6: Missing `SoftTimeLimitExceeded` handlers in non-pipeline tasks

**Status:** COMPLETE ✅ — Already handled in all tasks (cleanup.py, extract.py, pipeline.py, crawl.py, newsletter.py).

**Problem:** Tasks with `soft_time_limit` lacking explicit `SoftTimeLimitExceeded` catch blocks:
- `process_item` (tasks/extract.py)
- `cleanup_old_pipeline_logs` (tasks/cleanup.py)
- `cleanup_expired_verifications` (tasks/cleanup.py)

**Fix:** Add top-level handler in each task:
```python
except SoftTimeLimitExceeded:
    db.session.rollback()
    logger.error("Task exceeded soft time limit")
    raise
```

**Tests:** Add tests simulating `SoftTimeLimitExceeded` in each task, verifying rollback and re-raise.

---

### 4.7: Test suite improvements

**4.7a: Untested Celery tasks in `tasks/newsletter.py`**
- Add tests for `generate_daily_newsletters` (distributed locking, email sending orchestration)
- Add tests for `send_single_email` (SMTP retry logic)

**4.7b: Weak assertions in bulk article tests**
- `test_set_status` and `test_set_category` only check HTTP 200, not DB state
- Add DB state verification after bulk operations

**4.7c: Bulk article `reprocess` and `add_tags` actions untested**
- Add tests for these actions in `TestBulkArticles`

**4.7d: Test overlap between `test_auth_lockout.py` and `test_admin_auth.py`**
- Remove the xfail'd `TestLoginLockoutMemoryFallback` class from `test_auth_lockout.py`

---

## Wave 5: UI Critical Fixes

**Priority:** HIGH — Accessibility violations, mobile usability issues, and visual glitches.

**Execution:** Items independent — parallelize across sub-agents.

### 5.1: Move `theme.js` to `<head>` to eliminate FOUC

**Status:** COMPLETE ✅ — Already in `<head>` at line 16.

**Problem:** `theme.js` is loaded at the bottom of `<body>`, causing a flash of the wrong theme on first paint.

**Files:** `templates/base.html`, `templates/base_admin.html`

**Changes:** Move `<script src="{{ url_for('static', filename='js/theme.js') }}"></script>` to `<head>` (before the stylesheet link). Remove `defer` attribute.

**Risk:** None. The script is synchronous JS with no DOM dependencies.

---

### 5.2: Extract duplicate inline scripts to shared JS file

**Status:** COMPLETE ✅ — Already extracted to `static/js/share-a11y.js`.

**Problem:** The share dropdown accessibility JS is copy-pasted identically in `base.html` and `base_admin.html`.

**Files:** `static/js/share-a11y.js` (new), `templates/base.html`, `templates/base_admin.html`

**Changes:** Create `static/js/share-a11y.js` with the shared handler. Add script tag to both base templates' `<head>`. Remove inline `<script>` blocks.

**Risk:** None. Pure extraction.

---

### 5.3: Add missing ARIA labels to search inputs

**Status:** COMPLETE ✅ — Already has `aria-label="Search articles"` in admin articles.html.

**Problem:** Admin articles search input lacks `aria-label`, making it inaccessible to screen readers.

**Files:** `templates/admin/articles.html`

**Changes:** Add `aria-label="Search articles"` to the search input.

**Risk:** None. Additive only.

---

### 5.4: Add focus styles to filter buttons

**Status:** NOT STARTED

**Problem:** Filter buttons have `:hover` but no `:focus-visible` styles, making keyboard navigation invisible.

**Files:** `static/css/style.css`

**Changes:**
```css
.filter-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

**Risk:** None. Improves keyboard accessibility.

---

### 5.5: Add aria-haspopup to share buttons

**Status:** COMPLETE ✅ — Already has `aria-haspopup="true"` in share_macro.html.

**Problem:** Share buttons open dropdowns but lack `aria-haspopup` attribute.

**Files:** `templates/partials/share_macro.html`

**Changes:** Add `aria-haspopup="true"`, `aria-expanded="false"`, and `aria-controls="share-dropdown-{{ btn_id }}"` to share buttons.

**Risk:** None. Additive only.

---

### 5.6: Make admin tables responsive on mobile

**Status:** PARTIAL — `table-responsive` class exists in articles.html but not on all admin tables.

**Problem:** Tables have no horizontal scroll wrapper, causing overflow/breakage on small screens.

**Files:** All admin templates with tables, `static/css/style.css`

**Changes:** Add wrapper div around each table: `<div class="table-responsive">`. Add CSS for horizontal scrolling with `-webkit-overflow-scrolling: touch`.

**Risk:** Low. Pure CSS addition with template wrapper.

---

### 5.7: Increase touch targets for small buttons on mobile

**Status:** NOT STARTED

**Problem:** `.btn-delete` and `.btn-logout` have minimal padding, below 44px recommended touch target.

**Files:** `static/css/style.css`

**Changes:**
```css
@media (max-width: 640px) {
  .btn-delete, .btn-logout {
    min-width: 44px;
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
}
```

**Risk:** None. Mobile-only change.

---

### 5.8: Add role="alert" to error pages

**Status:** COMPLETE ✅ — Already has `role="alert"` on all error pages.

**Problem:** Error pages use generic `<div>` instead of `role="alert"` for important messages.

**Files:** `templates/errors/404.html`, `templates/errors/429.html`, `templates/errors/500.html`

**Changes:** Add `role="alert"` to the error page container div.

**Risk:** None. Improves screen reader announcements.

---

## Wave 6: UI Structural Improvements

**Priority:** MEDIUM — Code maintainability and user experience improvements.

**Execution:** Items independent — parallelize across sub-agents.

### 6.1: Add mobile hamburger menu to admin nav

**Status:** COMPLETE ✅ — Already uses checkbox pattern in base_admin.html.

**Problem:** `base_admin.html` has no hamburger toggle. On mobile (<640px), the admin nav links overflow/wrap poorly.

**Files:** `templates/base_admin.html`, `static/css/style.css`

**Changes:** Add the checkbox hack pattern from `base.html` to `base_admin.html`. Reuse existing `.nav-toggle-checkbox` / `.nav-toggle-label` styles.

**Risk:** Low. Reuses existing CSS patterns.

---

### 6.2: Add admin nav active state highlighting

**Status:** NOT STARTED

**Problem:** Admin nav doesn't highlight the current page like the public nav does.

**Files:** `templates/base_admin.html`

**Changes:** Add `{% if current_page == '/admin/' %}class="active"{% endif %}` pattern to each nav link. Use `startswith` for sub-pages.

**Risk:** Low. Pure template change.

---

### 6.3: Add HTMX loading indicators to admin table swaps

**Status:** COMPLETE ✅ — Already has `hx-indicator` in articles.html.

**Problem:** When HTMX swaps the articles table during search/filter, there's no visual feedback.

**Files:** `templates/admin/articles.html`, `templates/admin/partials/articles_table.html`

**Changes:** Add `hx-indicator="#articles-table-spinner"` to search input and select elements. Add spinner element inside the table container.

**Risk:** Low. Uses existing HTMX indicator CSS classes.

---

### 6.4: Add loading state for article detail HTMX swap

**Status:** COMPLETE ✅ — Already has `hx-indicator="#content-loading"` in article_card.html.

**Problem:** Clicking an article card triggers an HTMX swap into `#content` with no loading indicator.

**Files:** `templates/partials/article_card.html`, `templates/base.html`

**Changes:** Add `hx-indicator="#content-loading"` to the article card `<a>` tag. Add loading indicator as a sibling to `#content`.

**Risk:** Low. Uses existing HTMX patterns.

---

### 6.5: Prevent `hx-boost` from intercepting external links and special forms

**Status:** NOT STARTED

**Problem:** `hx-boost="true"` on `<body>` intercepts ALL links and forms. RSS feed link and logout form should not be boosted.

**Files:** `templates/base.html`, `templates/base_admin.html`

**Changes:** Add `hx-boost="false"` to:
- RSS feed link
- Logout form
- Any `target="_blank"` links (explicit is better)

**Risk:** Low. Additive changes only.

---

### 6.6: Add CSS table of contents comment

**Status:** NOT STARTED

**Problem:** `style.css` is 2559 lines with no navigation aid.

**Files:** `static/css/style.css`

**Changes:** Add a TOC comment block at line 1 listing all sections with line numbers. Keep the file as-is otherwise.

**Risk:** None. Comment only.

---

## Wave 7: UI UX Enhancements

**Priority:** MEDIUM — User experience improvements.

**Execution:** Items independent — parallelize across sub-agents.

### 7.1: Add Open Graph and Twitter Card meta tags

**Status:** COMPLETE ✅ — Already present in base.html (lines 8-11).

**Problem:** No social sharing metadata. Articles shared on social media lack proper previews.

**Files:** `templates/base.html`, `templates/article.html`

**Changes:** Add meta description, og:site_name, og:type, twitter:card blocks to base.html. Override in article.html with article-specific values.

**Risk:** None. Pure SEO improvement.

---

### 7.2: Add keyboard shortcut for search

**Status:** NOT STARTED

**Problem:** No `/` key shortcut to focus search input — a common pattern for developer-facing sites.

**Files:** `static/js/app.js`, `templates/partials/feed.html`

**Changes:** Add keydown listener for `/` that focuses search input (guarded against input/textarea/select focus). Add `[ / ]` hint to search placeholder.

**Risk:** Low. Standard pattern.

---

### 7.3: Add pagination controls to admin tables

**Status:** NOT STARTED

**Problem:** Only a "next page" link exists. No "previous" link or page info display.

**Files:** Admin table partials, route handlers, `static/css/style.css`

**Changes:** Backend: Add `total_count` to template context via separate `.count()` query. Template: Replace single "next page" link with prev/page info/next controls. Add CSS for pagination.

**Risk:** Low. Adds one COUNT query per page load.

---

### 7.4: Add form validation feedback to article edit

**Status:** COMPLETE ✅ — Already has error display with `role="alert"`.

**Problem:** Article edit form has no server error display. Backend returns `error` on DB failure but template doesn't show it.

**Files:** `templates/admin/article_edit.html`, `static/css/style.css`

**Changes:** Add error display section at top of form with `{% if error %}`. Add `.form-errors` CSS styling.

**Risk:** Low. Backend already passes `error`.

---

### 7.5: Add sources management link to dashboard

**Status:** NOT STARTED

**Problem:** Dashboard sources table has no link to sources management page.

**Files:** `templates/admin/dashboard.html`

**Changes:** Add `<a href="/admin/sources" class="dash-link">manage sources →</a>` below sources table.

**Risk:** None. One-line addition.

---

## Wave 8: UI Polish

**Priority:** LOW — Final polish items.

**Execution:** Items independent — parallelize across sub-agents.

### 8.1: Add favicon

**Status:** COMPLETE ✅ — Already exists at `static/favicon.svg` and linked in both base templates.

**Problem:** No `<link rel="icon">` in either base template.

**Files:** `templates/base.html`, `templates/base_admin.html`, `static/favicon.svg` (new)

**Changes:** Create simple SVG favicon with the `//` logo mark. Add `<link rel="icon">` to both base templates.

**Risk:** None.

---

### 8.2: Add empty state illustrations

**Status:** NOT STARTED

**Problem:** "no articles yet" and "no articles found" are plain text.

**Files:** `templates/partials/feed.html`, `templates/admin/partials/articles_table.html`, `templates/admin/sources.html`, `static/css/style.css`

**Changes:** Add simple inline SVG illustrations for empty states. Create reusable `.empty-state` CSS class.

**Risk:** Low. Inline SVG, no external dependencies.

---

### 8.3: Replace share checkbox hack with `<details>` element

**Status:** COMPLETE ✅ — Already uses `<details>`/`<summary>` in share_macro.html.

**Problem:** The hidden checkbox hack for share dropdowns is less accessible than native HTML.

**Files:** `templates/partials/share_macro.html`, `static/css/style.css`, `static/js/app.js`

**Changes:** Replace `<input type="checkbox">` + CSS `:checked` with `<details>` + `<summary>`. Update CSS and JS accordingly. Maintain the same visual appearance.

**Risk:** Medium. `<details>` has slightly different keyboard behavior. Test with screen readers.

---

### 8.4: Add offline detection toast

**Status:** COMPLETE ✅ — Already has offline toast in base.html with event listeners.

**Problem:** No user feedback when network is unavailable.

**Files:** `static/js/app.js`, `static/css/style.css`, `templates/base.html`

**Changes:** Add offline/online event listeners to show/hide a toast notification. Add CSS for the toast styling.

**Risk:** Low. Progressive enhancement. Note: `navigator.onLine` is unreliable — checks network interface status, not actual internet connectivity.

---

## Execution Strategy

### Wave 1: Critical Backend Bugs (Parallel)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| A | 1.1 Newsletter lock race condition | `tasks/newsletter.py` | ✅ DONE |
| B | 1.2 Pipeline lock leak | `tasks/pipeline.py` | ✅ DONE |
| C | 1.3 Crawl failure health tracking | `tasks/crawl.py` | ✅ DONE |
| D | 1.4 Subscriber.get_active filter | `models.py` | ✅ DONE |
| E | 1.5 Missing statuses in stage maps | `tasks/pipeline.py` | ✅ DONE |
| F | 1.6 Non-atomic newsletter lock | `tasks/newsletter.py` | ✅ DONE |

### Wave 2: Security & Error Handling (Parallel, after Wave 1)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| G | 2.1 Escape URLs in email HTML | `services/email.py` | ✅ DONE |
| H | 2.2 Guard db.session.commit() calls | Multiple task files | ✅ DONE |
| I | 2.3 RedisError on lock acquisition | Multiple task files | ✅ DONE |
| J | 2.4 reset_response_cache thread safety | `services/cache.py` | ✅ DONE |
| K | 2.5 Missing reset functions | `services/limiter.py`, `services/config_cache.py` | ✅ DONE |
| L | 2.6 set_category validation | `routes/admin/api.py` | ✅ DONE |
| M | 2.7 CSRF-exempt POST | `routes/public/links.py` | ✅ DONE |
| N | 2.8 Skip contaminated health test | `tests/test_routes.py` | ✅ DONE |

### Wave 3: Code Quality (Parallel, after Wave 2)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| O | 3.1 f-strings in log calls | Multiple files | ✅ DONE |
| P | 3.2 PipelineStatus constants | Multiple task files | ✅ DONE |
| Q | 3.3 Deduplicate tag assignment | `tasks/pipeline.py`, `routes/admin/api.py` | ✅ DONE |
| R | 3.4 Deduplicate health checks | `routes/admin/api.py`, `services/health.py` | ✅ DONE |
| S | 3.5 Deduplicate _parse_article | `services/newsletter.py`, `services/newsletter_pipeline.py` | ✅ DONE |
| T | 3.6 Break up _generate_newsletters_impl | `tasks/newsletter.py` | ✅ DONE |
| U | 3.7 Data-drive _degrade_and_advance | `tasks/pipeline.py` | ✅ DONE |
| V | 3.8 Break up bulk_article_operations | `routes/admin/api.py` | ✅ DONE |
| W | 3.9 Break up run_stage | `tasks/pipeline.py` | ✅ DONE |
| X | 3.10 Deduplicate _evict_stale | `services/cache.py`, `services/config_cache.py` | ✅ DONE |
| Y | 3.11 Redis import style | `services/pipeline_monitor.py` | ✅ DONE |
| Z | 3.12 Type hint fix | `services/redis_utils.py` | ✅ DONE |
| AA | 3.13 Limiter timeout log message | `services/limiter.py` | ✅ DONE |

### Wave 4: Test & Config (Parallel, after Wave 3)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| AB | 4.1 Deduplicate Redis mock | Test files | ✅ DONE |
| AC | 4.2 Extract _reset_singletons | `tests/conftest.py` | ✅ DONE |
| AD | 4.3 Test app fixture uses create_app() | `tests/conftest.py` | ✅ DONE |
| AE | 4.4 Fix test env var cleanup | `tests/conftest.py` | ✅ DONE |
| AF | 4.5 Guard config int() calls | `config.py` | ✅ DONE |
| AG | 4.6 SoftTimeLimitExceeded handlers | `tasks/extract.py`, `tasks/cleanup.py` | ✅ DONE |
| AH | 4.7 Test suite improvements | Multiple test files | ✅ DONE |

### Wave 5: UI Critical Fixes (Parallel, after Wave 4)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| AI | 5.1 Move theme.js to <head> | `templates/base.html`, `templates/base_admin.html` | ✅ DONE |
| AJ | 5.2 Extract duplicate inline scripts | `static/js/share-a11y.js`, templates | ✅ DONE |
| AK | 5.3 ARIA labels on search inputs | `templates/admin/articles.html` | ✅ DONE |
| AL | 5.4 Focus styles on filter buttons | `static/css/style.css` | ✅ DONE |
| AM | 5.5 aria-haspopup on share buttons | `templates/partials/share_macro.html` | ✅ DONE |
| AN | 5.6 Responsive admin tables | Multiple admin templates | ✅ DONE |
| AO | 5.7 Touch targets for mobile | `static/css/style.css` | ✅ DONE |
| AP | 5.8 role="alert" on error pages | `templates/errors/*.html` | ✅ DONE |

### Wave 6: UI Structural (Parallel, after Wave 5)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| AQ | 6.1 Admin hamburger menu | `templates/base_admin.html`, CSS | ✅ DONE |
| AR | 6.2 Admin nav active state | `templates/base_admin.html` | ✅ DONE |
| AS | 6.3 HTMX loading indicators | Admin article templates | ✅ DONE |
| AT | 6.4 Article detail loading state | `templates/partials/article_card.html`, `templates/base.html` | ✅ DONE |
| AU | 6.5 Prevent hx-boost interception | `templates/base.html`, `templates/base_admin.html` | ✅ DONE |
| AV | 6.6 CSS TOC comment | `static/css/style.css` | ✅ DONE |

### Wave 7: UI UX Enhancements (Parallel, after Wave 6)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| AW | 7.1 Meta/OG tags | `templates/base.html`, `templates/article.html` | ✅ DONE |
| AX | 7.2 Search keyboard shortcut | `static/js/app.js` | ✅ DONE |
| AY | 7.3 Pagination controls | Admin templates and routes | ✅ DONE |
| AZ | 7.4 Form validation feedback | `templates/admin/article_edit.html` | ✅ DONE |
| BA | 7.5 Sources link to dashboard | `templates/admin/dashboard.html` | ✅ DONE |

### Wave 8: UI Polish (Parallel, after Wave 7)
| Agent | Item | Scope | Status |
|-------|------|-------|--------|
| BB | 8.1 Favicon | `static/favicon.svg`, base templates | ✅ DONE |
| BC | 8.2 Empty state illustrations | Multiple templates, CSS | ✅ DONE |
| BD | 8.3 Replace checkbox hack with <details> | Share macro, CSS, JS | ✅ DONE |
| BE | 8.4 Offline detection toast | `static/js/app.js`, CSS, base template | ✅ DONE |

### Verification
After each wave:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Implementation Notes

### Critical Dependencies
- **Wave 3 item 3.9** depends on **Wave 1 item 1.2** — execute 1.2 first to restructure try/finally, then extract helpers
- **Wave 4 item 4.3** (create_app in tests) is the highest-risk change — run full test suite immediately and fix regressions incrementally

### Wave 1: Lock Restructuring
The lock leak fix must preserve behavior for the "already locked" case. When a lock is held by another task, `run_stage` returns without doing work. After the fix, the same behavior must be preserved — just with proper lock release if the current task acquired it and then hit an early return.

### Wave 2: RedisError on Lock Acquisition
The approach is to degrade gracefully — if Redis is unavailable during lock acquisition, proceed without the lock rather than crashing. While this means duplicate processing could occur during Redis outages, this is preferable to task crashes that leave articles in intermediate states.

### Wave 3: Tag Assignment Deduplication
The bulk route version processes multiple articles; `_assign_tags` in `tasks/pipeline.py` processes one. The refactored version should handle both cases. Keep the batch optimization (bulk fetch existing tags, bulk insert missing links).

### Wave 3: _degrade_and_advance Data-Driving
The edit stage has unique review-routing logic (`_should_route_to_review`) that the other stages lack. The refactored version must preserve this by keeping the `if failed_stage == "edit"` branch rather than trying to force it into the generic pattern.

### Wave 4: create_app() in Tests
The biggest risk in this plan. If tests break, the most likely causes are:
- CSRF token issues (solved by `WTF_CSRF_ENABLED=False` in TestingConfig)
- Missing blueprint registrations (verify all blueprints are registered in `create_app`)
- Extension initialization order (Talisman may wrap routes differently)

### Wave 5: Pagination Implementation Detail
The backend currently uses a LIMIT+1 pattern (no COUNT query) for efficiency. Adding pagination controls requires `total_count`. Add `Article.query.count()` (or filtered count) per page — one extra query per page load, acceptable for admin interface.

### Wave 8: Offline Detection Limitations
`navigator.onLine` is unreliable — it checks network interface status, not actual internet connectivity. A better approach would ping a known endpoint, but that adds complexity. The toast is a "nice to have" UX touch, not a critical feature.
# Consolidated Improvement Plan

**Created:** 2026-04-01 from consolidation of plan2–plan10.
**Status:** Draft — ready for execution.

## Executive Summary

Consolidates ~80 improvement items from 9 separate plan files into a single prioritized plan. Organized into 10 waves of increasing priority. Waves 1–2 (bugs + security) should execute first. Later waves can run in parallel with sub-agents.

**Estimated total effort:** 80–120 hours across all waves.

---

## Wave 1: Critical Bugs — Data Integrity & Correctness

All items in this wave can run in parallel (independent code paths).

### 1.1 Config singleton not invalidated on reload
**File:** `services/config_unified.py:120-140`, `routes/admin/api.py:119-134`
**Issue:** `get_config()` caches `AppConfig` in `_instance`, but `reload_config()` never calls `reset_config()`. After config reload, `get_config()` returns stale values indefinitely.
**Fix:** Add `from services.config_unified import reset_config` to the reload endpoint and call it alongside `clear_provider_cache()` and `clear_app_cache()`.
**Risk:** Low — `reset_config()` exists and is tested, just never called from the reload path.

### 1.2 `track_metric` double-commit race condition
**File:** `services/article.py:40-51`
**Issue:** INSERT-then-UPDATE pattern with separate commits. Two concurrent `IntegrityError`s both rollback, both execute UPDATE, both commit — one increment lost.
**Fix:** Use SQLAlchemy's `insert().on_conflict_do_update()` for a single atomic upsert.
**Risk:** Low — isolated function, well-tested surface.

### 1.3 `select_article` commits in separate transactions
**File:** `tasks/select.py:60-74`
**Issue:** Article status committed at line 61, PipelineRun counter committed separately at line 71. If second commit fails, article is marked selected but run counter isn't incremented.
**Fix:** Combine into a single transaction with one commit after both updates.
**Risk:** Low — straightforward consolidation.

### 1.4 `_dispatch_next` cache never invalidates
**File:** `tasks/pipeline.py:69-103`
**Issue:** `_task_fn_cache` is a module-level dict that caches resolved task functions forever. Stale references persist after config reload.
**Fix:** Add `clear_task_fn_cache()` function. Call it from `reload_config()` alongside other cache clears. Add to `_reset_singletons()` in `tests/conftest.py`.
**Risk:** Low — cache is purely an optimization.

### 1.5 `run_stage` error path can silently exceed retry budget
**File:** `tasks/pipeline.py:684-702`
**Issue:** After `db.session.rollback()`, `_handle_stage_failure()` does its own commit. If that commit fails, `retry_count` is never incremented, allowing infinite Celery autoretries.
**Fix:** If `_handle_stage_failure()` commit fails, mark article as failed. Alternatively, use a separate DB session for the failure handler commit.
**Risk:** Medium — touches core pipeline error path.

### 1.6 Unprotected `db.session.commit()` in `trigger_crawl`
**File:** `routes/admin/pipelines.py:91`
**Issue:** The commit has no try/except with rollback. If it fails, the session is dirty.
**Fix:** Wrap in try/except with `db.session.rollback()`.
**Risk:** Low.

### 1.7 `retry_stuck` uses hardcoded constant instead of config helper
**File:** `tasks/retry.py:69`
**Issue:** Uses `MAX_STAGE_RETRIES` constant instead of `_get_max_stage_retries()` helper. Env var changes are ignored.
**Fix:** Import and use `_get_max_stage_retries()` from `tasks.pipeline`.
**Risk:** Low.

### 1.8 `ProductionConfig.validate()` couples config to routes
**File:** `config.py:153-155`
**Issue:** `validate()` imports `_is_password_hash` from `routes.admin`, creating a dependency on route internals with import-time side effects.
**Fix:** Move `_is_password_hash()` to a shared utility (e.g., `services/validation.py`).
**Risk:** Low — pure refactor.

### 1.9 `from_env()` uses bare `int()` on env vars
**File:** `services/config_unified.py:94-99, 105-109, 113-114`
**Issue:** `int(os.environ.get("MAX_STAGE_RETRIES", "3"))` raises `ValueError` on non-numeric input.
**Fix:** Use a `_safe_int(key, default)` helper for all `int()` calls in `from_env()`.
**Risk:** Low — purely defensive.

### 1.10 Silent lock release failure in `finally` block
**File:** `tasks/pipeline.py:706-711`
**Issue:** `except Exception: pass` silently swallows lock release failures. Lock leaks until TTL.
**Fix:** Log warning: `logger.warning("Failed to release stage lock %s: %s", lock_key, e)`.
**Risk:** Low — adds observability.

### 1.11 Crawl group wait timeout shorter than task soft_time_limit
**File:** `tasks/crawl.py:228`
**Issue:** `result.get(timeout=240)` but `crawl_source` has `soft_time_limit=300`. Tasks may still be running after timeout.
**Fix:** Increase group wait timeout to exceed task soft_time_limit plus buffer (e.g., 360s).
**Risk:** Medium — increases blocking time of `crawl-all` task.

### 1.12 Dead letter stats uses hardcoded 15-minute cutoff
**File:** `routes/admin/api.py:177`
**Issue:** Hardcodes 15-minute window, ignoring `STUCK_THRESHOLD_MINUTES` config (default 60). Inconsistent with retry task behavior.
**Fix:** Use `constants._get_stuck_threshold_minutes()` or `current_app.config["STUCK_THRESHOLD_MINUTES"]`.
**Risk:** Low.

### 1.13 429 handler uses unreliable `e.description` for retry_after
**File:** `app.py:193`
**Issue:** Extracts `retry_after` from human-readable description string. Missing or misleading values.
**Fix:** Use `e.get_response().headers.get('Retry-After')` from the response object.
**Risk:** Low.

### 1.14 `pipeline.yaml` has hardcoded `site_url`
**File:** `pipeline.yaml` (newsletter section)
**Issue:** `site_url` hardcoded to `https://ainews.dev` instead of `${SITE_URL}`.
**Fix:** Change to `site_url: "${SITE_URL}"` and ensure `resolve_env_var()` is called.
**Risk:** Low.

---

## Wave 2: Security Fixes

All items in this wave can run in parallel.

### 2.1 Fix CSP violations on inline event handlers
**Files:** `templates/base.html:41`, `templates/base_admin.html:33`, `templates/share_redirect.html:21`
**Issue:** `onclick="toggleTheme()"` and `onclick="this.select()"` violate CSP `script-src: 'self'`. Blocked silently in production.
**Fix:** In `theme.js`, attach delegated click listener on `document` for `.theme-toggle`. Remove `onclick` from templates. Add `app.js` to `share_redirect.html`.
**Risk:** Low.

### 2.2 Fix XSS via innerHTML in newsletters.js
**File:** `static/js/newsletters.js:18,20`
**Issue:** `data.message` from server injected via `innerHTML`. Stored XSS vector.
**Fix:** Build DOM elements with `textContent` instead of HTML concatenation.
**Risk:** Low.

### 2.3 Fix localStorage crash in theme.js
**File:** `static/js/theme.js:17,29`
**Issue:** `localStorage.getItem/setItem` without try/catch. Safari/Firefox private browsing throws `DOMException`, crashing the IIFE.
**Fix:** Wrap localStorage calls in try/catch with in-memory fallback.
**Risk:** Low.

### 2.4 Fix navigator.clipboard missing error handling
**File:** `static/js/app.js:46,59`
**Issue:** `navigator.clipboard.writeText()` called without `.catch()` or availability check. Throws on HTTP pages or when permissions denied.
**Fix:** Guard with `if (navigator.clipboard)`, add `.catch()`.
**Risk:** Low.

### 2.5 Fix duplicate form submissions in newsletters.js
**File:** `static/js/newsletters.js:4-25`
**Issue:** Submit handler doesn't disable button. Rapid clicks send multiple requests.
**Fix:** Disable submit button at start, re-enable in `finally`.
**Risk:** Low.

### 2.6 `safe_href` filter lacks SSRF protection
**File:** `app.py:211-219`
**Issue:** Only checks `http://` or `https://` prefix. Doesn't validate against private IPs. Inconsistent with `services/url.py:validate_url_safe()`.
**Fix:** Import and use `validate_url_safe()` in the filter. Return `#` for blocked URLs.
**Risk:** Medium — depends on current filter behavior.

### 2.7 Add missing `<label>` to login password input
**File:** `templates/admin/login.html:19-26`
**Issue:** Password input has `placeholder="password"` but no associated `<label>`. WCAG 1.3.1 (Level A) violation.
**Fix:** Add `<label for="login-password" class="sr-only">Password</label>` before the input.
**Risk:** Low.

### 2.8 Fix duplicate CSRF tokens in review table
**File:** `templates/admin/partials/review_table.html:33-34,42-43`
**Issue:** Both `hx-vals` and `<input type="hidden">` send CSRF tokens. Redundant.
**Fix:** Remove hidden inputs, keep `hx-vals` approach (consistent with `articles_table.html`).
**Risk:** Low.

### 2.9 `ADMIN_PASSWORD` access raises KeyError if missing
**File:** `routes/admin/auth.py:49`
**Issue:** `current_app.config["ADMIN_PASSWORD"]` raises `KeyError` → 500 error instead of graceful failure.
**Fix:** Use `current_app.config.get("ADMIN_PASSWORD", "")`.
**Risk:** Low.

### 2.10 `track_share_click` POST lacks CSRF protection and rate limiting
**File:** `routes/public/links.py:82-85`
**Issue:** POST endpoint without CSRF validation. Could be exploited for amplification.
**Fix:** Add explicit `@csrf.exempt` with documented rationale. Add lightweight per-IP rate limit.
**Risk:** Low.

---

## Wave 3: Performance

### 3.1 `find_duplicate_titles` N+1 queries
**File:** `services/article.py:251-256`
**Issue:** Calls `db.session.get(Article, article_id)` per matching article. Individual SELECTs for each match.
**Fix:** Collect matching IDs, then batch-load: `Article.query.filter(Article.id.in_(matched_ids)).all()`.
**Risk:** Medium — changes internal data flow.

### 3.2 `get_existing_external_ids` loads all IDs unbounded
**File:** `services/crawling.py:74-88`
**Issue:** Loads every external_id for a source regardless of age.
**Fix:** Add time-bounded filter (last 30 days) matching the dedup window.
**Risk:** Low.

### 3.3 `edit.py` reloads tags on every article
**File:** `tasks/edit.py:32`
**Issue:** `Tag.query.limit(100).all()` runs per-article. Tags change rarely. Unsorted `limit(100)` is non-deterministic.
**Fix:** Add in-memory TTL cache (5 min). Sort by `Tag.name`.
**Risk:** Low.

### 3.4 Limiter check after lock wastes lock time
**File:** `tasks/pipeline.py:647-667`
**Issue:** Lock acquired first (line 650), then limiter checked (line 667). Saturated limiter wastes lock acquire/release cycles.
**Fix:** Acquire limiter slot first. If rejected, skip lock. If lock fails, release limiter.
**Risk:** Medium — restructures core pipeline entry.

### 3.5 DNS resolution has no timeout
**File:** `services/url.py:109`
**Issue:** `socket.getaddrinfo(hostname, None)` blocks indefinitely if DNS unresponsive.
**Fix:** Wrap in `ThreadPoolExecutor` with 10s timeout. Use `executor.shutdown(wait=False, cancel_futures=True)` per AGENTS.md convention.
**Risk:** Low.

### 3.6 `find_duplicate_titles` returns objects that are re-fetched
**File:** `services/article.py:246-256`
**Issue:** Query uses `.with_entities()` to minimize data, then `db.session.get()` re-fetches full models.
**Fix:** Return tuples `(id, title, source_id)`. Add `source_id` to `.with_entities()`. Update caller in `tasks/crawl.py:99-106`.
**Risk:** Medium — changes return type.

### 3.7 Profile database queries in admin list views
**Files:** Admin routes for article lists
**Issue:** Potential slow queries and missing indexes.
**Fix:** Use `EXPLAIN QUERY PLAN`, add missing indexes.
**Risk:** Low.

---

## Wave 4: Accessibility & UX

Wave 4.1–4.4 are critical accessibility (WCAG violations). 4.5+ are UX improvements. All can run in parallel.

### 4.1 Fix color contrast issues
**File:** `static/css/style.css:41,68`
**Issue:** `--text-dim: #8b949e` on `#0d1117` = ~4.33:1 (needs 4.5:1). Light theme `--text-dim: #8c959f` on `#ffffff` = ~3.04:1.
**Fix:** Dark: `--text-dim` → `#9ea7b0`. Light: `--text-dim` → `#6e7781`. Also differentiate `--text-muted` / `--text-dim` in dark theme.
**Risk:** Low.

### 4.2 Add missing form labels and aria-labels
**Files:** `templates/admin/articles.html:27,38`, `templates/partials/article_card.html:55`, `templates/partials/share_macro.html:16`
**Issue:** Admin filter selects have no labels. Icon-only links have no `aria-label`.
**Fix:** Add `aria-label="Filter by status"`, `aria-label="Filter by category"`, `aria-label="Read original article"`, `aria-label="Share URL"`.
**Risk:** Low.

### 4.3 Lower minimum font size floor
**File:** `static/css/style.css` (multiple locations)
**Issue:** Elements at `0.6rem` (9px) and `0.65rem` (9.75px). Practically inaccessible.
**Fix:** Bump all `0.6rem` and `0.65rem` elements to `0.7rem` minimum.
**Risk:** Low.

### 4.4 Fix `--bg-subtle` undefined variable
**File:** `static/css/style.css:1872`
**Issue:** `.pag-link:hover` references `var(--bg-subtle)` which is never defined.
**Fix:** Define `--bg-subtle` in both `:root` and `[data-theme="light"]` blocks.
**Risk:** Low.

### 4.5 Fix infinite scroll spinner aria-live
**File:** `templates/partials/feed.html:73`
**Issue:** Spinner has `aria-live="assertive"` which interrupts screen readers on every scroll load.
**Fix:** Change to `aria-live="polite"`.
**Risk:** Low.

### 4.6 Add global HTMX error handler
**Files:** `static/js/app.js`, `templates/base.html`, `templates/base_admin.html`
**Issue:** Failed HTMX requests silently replace content with error HTML or blank content. No user feedback.
**Fix:** Add `htmx:responseError` event listener showing a toast. Add `#toast-container` to base templates.
**Risk:** Low.

### 4.7 Add loading indicator to subscribe form
**File:** `templates/partials/subscribe_box.html:18-28`
**Issue:** No `hx-indicator` on subscribe form. No feedback until response.
**Fix:** Add `hx-indicator="#subscribe-spinner"` and spinner element.
**Risk:** Low.

### 4.8 Add feedback to "trigger crawl now" button
**File:** `templates/admin/dashboard.html:29-32`
**Issue:** Form POSTs with no feedback after click.
**Fix:** Convert to HTMX post with success/error toast or inline confirmation.
**Risk:** Low.

### 4.9 Differentiate empty state from no-search-results
**File:** `templates/partials/feed.html:46`
**Issue:** "no articles yet" shows even when search returns zero results.
**Fix:** Check if `query` or `category` is set. Show "no articles match your filters" instead.
**Risk:** Low.

### 4.10 Add focus management after HTMX content swaps
**File:** `static/js/app.js`
**Issue:** After HTMX swaps content, focus stays on old trigger element. Screen readers miss new content.
**Fix:** Add `htmx:afterSwap` handler moving focus to first heading in `#content`.
**Risk:** Low.

### 4.11 Add h1 to feed page
**File:** `templates/partials/feed.html:1`
**Issue:** No `<h1>` on feed page. Heading hierarchy starts at `<h2>`.
**Fix:** Add `<h1 class="sr-only">` at top of feed.
**Risk:** Low.

### 4.12 Add loading skeleton for article detail page
**Files:** `templates/partials/skeleton_loading.html`, `templates/article.html`
**Issue:** No loading skeleton during article HTMX navigation.
**Fix:** Add detail-page skeleton variant. Show during HTMX swap via `htmx:beforeSwap`.
**Risk:** Low.

### 4.13 Add pagination to metrics page
**File:** `templates/admin/metrics.html:67-142`
**Issue:** "Top articles" tables grow unbounded with no pagination.
**Fix:** Add `limit` parameter (default 20) and result selector.
**Risk:** Low.

### 4.14 Add sources page add-source form
**File:** `templates/admin/sources.html`
**Issue:** Sources page shows existing sources but has no UI to add new ones.
**Fix:** Add form with name, type, URL, category fields. Wire to source creation API.
**Risk:** Medium — new feature requiring backend wiring.

---

## Wave 5: Code Quality & CSS

All items can run in parallel. Template and CSS changes are independent domains.

### 5.1 Triple-redundant retry defaults
**Files:** `config.py:44-45`, `tasks/pipeline.py:12-13`, `services/config_unified.py:20-21`
**Issue:** `MAX_STAGE_RETRIES=3` and `MAX_TOTAL_RETRIES=10` defined in three places.
**Fix:** Define in `constants.py`, import everywhere.
**Risk:** Low.

### 5.2 Brittle `replace("ing", "")` in degradation
**File:** `tasks/pipeline.py:306`
**Issue:** `"researching".replace("ing", "")` → `"research"` works by coincidence.
**Fix:** Use `_STAGE_STATUS_MAP` or add explicit `_status_to_stage_name()` helper.
**Risk:** Low.

### 5.3 Extract shared fallback article construction
**Files:** `tasks/pipeline.py:118-147`, `services/dead_letter.py:73-104`
**Issue:** Both functions construct identical fallback JSON structures.
**Fix:** Create `services/article_fallback.py` with shared `build_fallback_article_json()`.
**Risk:** Low — pure refactor.

### 5.4 Fix duplicate `model_dump_json()` in edit task
**File:** `tasks/edit.py:55-56`
**Issue:** `result.model_dump_json()` called twice — potentially different results.
**Fix:** Store in variable, assign to both fields.
**Risk:** None.

### 5.5 Fix f-string in `require_auth` log call
**File:** `routes/admin/__init__.py:222-224`
**Issue:** Uses f-string in logger call, violating project convention.
**Fix:** Change to `logger.info("Admin access: %s %s", request.method, request.path, ...)`.
**Risk:** None.

### 5.6 Default `success_rate` to `None` for empty windows
**File:** `services/pipeline_monitor.py:100,114`
**Issue:** Empty window returns `success_rate=100.0`, masking pipeline stalls.
**Fix:** Return `None` when `total == 0`.
**Risk:** Low — API response shape changes.

### 5.7 Remove redundant import in pipeline stats
**File:** `routes/admin/api.py:159`
**Issue:** `from flask import request` inside function body, but `request` already at module level.
**Fix:** Delete the inner import.
**Risk:** None.

### 5.8 Clarify tuple-as-statement lambda in research degradation
**File:** `tasks/pipeline.py:259-279`
**Issue:** `(setattr(...), setattr(...))` lambda uses tuple evaluation for side effects. Hard to read.
**Fix:** Extract to named `_degrade_research(article)` function.
**Risk:** None.

### 5.9 Deduplicate tag-assignment logic
**Files:** `tasks/edit.py`, `routes/admin/api.py` (bulk `add_tags`)
**Issue:** Tag-assignment code is duplicated.
**Fix:** Extract a shared helper function.
**Risk:** Low.

### 5.10 Add type hints to service functions
**Files:** `services/content_extractor.py`, `services/article.py`, `services/crawling.py`
**Issue:** Missing return types and parameter types.
**Fix:** Add type hints throughout.
**Risk:** Low.

### 5.11 Convert remaining f-string log calls to %-formatting
**Files:** Multiple
**Issue:** Some log statements use f-strings instead of %-formatting for deferred construction.
**Fix:** Convert `logger.error(f"...")` to `logger.error("...", args)`.
**Risk:** None.

### 5.12 Verify all `db.session.commit()` calls are wrapped
**Files:** Multiple route handlers
**Issue:** Some commits may be unprotected.
**Fix:** Audit with grep, wrap each in try/except with rollback.
**Risk:** Low.

### 5.13 Add CSS custom property tokens for border-radius, font-size, spacing
**File:** `static/css/style.css:32-53`
**Issue:** 5+ border-radius values, 12+ font-size values, 10+ spacing values — all hardcoded.
**Fix:** Define `--radius-*`, `--text-*`, `--space-*` token scales. Replace all hardcoded values.
**Risk:** Low — visual regression testing needed.

### 5.14 Extract duplicated badge/heading CSS
**File:** `static/css/style.css` (multiple sections)
**Issue:** `.badge`, `.pipeline-badge`, `.section-heading`, etc. share identical font/color/margin properties.
**Fix:** Create shared base selectors with differentiating properties only in individual rules.
**Risk:** Low.

### 5.15 Replace hardcoded `rgba()` colors with CSS variables
**File:** `static/css/style.css` (~30 instances)
**Issue:** Raw `rgba(88, 166, 255, ...)` breakdowns of theme colors. Maintenance hazard.
**Fix:** Define alpha variant variables (`--accent-alpha-10`, etc.) or use `color-mix()`.
**Risk:** Low.

### 5.16 Replace `transition: all` with specific properties
**File:** `static/css/style.css:210,318,1516,820`
**Issue:** `transition: all 0.15s` animates all properties including future additions.
**Fix:** Enumerate specific properties: `transition: color 0.15s, background-color 0.15s, ...`.
**Risk:** Low.

### 5.17 Add Firefox scrollbar support
**File:** `static/css/style.css:1005-1020`
**Issue:** Only WebKit scrollbar pseudo-elements defined. Firefox ignores them.
**Fix:** Add `scrollbar-width: thin; scrollbar-color: var(--border) var(--bg-primary)`.
**Risk:** Low.

---

## Wave 6: Template DRY & Admin UX

### 6.1 Extract shared topic icon macro
**Files:** `templates/partials/article_card.html:5-13`, `templates/partials/condensed_article.html:7-14`
**Issue:** Identical SVG path blocks for categories duplicated in two templates.
**Fix:** Create `templates/partials/topic_icon.html` Jinja2 macro.
**Risk:** Low.

### 6.2 Extract shared theme toggle
**Files:** `templates/base.html:41-56`, `templates/base_admin.html:33-48`
**Issue:** Theme toggle button (2 SVGs + button) duplicated in both base templates.
**Fix:** Create `templates/partials/theme_toggle.html`. Include in both.
**Risk:** Low.

### 6.3 Extract pipeline badge and impact score macros
**Files:** `templates/admin/dashboard.html`, `templates/admin/partials/articles_table.html`, `templates/partials/article_card.html`
**Issue:** Pipeline badge and impact score rendering duplicated across three templates.
**Fix:** Create `templates/macros/badges.html` with `pipeline_badge(status)` and `impact_score(score)` macros.
**Risk:** Low.

### 6.4 Standardize pagination with shared macro
**Files:** `templates/admin/partials/articles_table.html`, `review_table.html`, `pipelines.html`, `newsletters.html`, `subscribers.html`
**Issue:** Two different pagination patterns: full nav vs simple "next page →" link.
**Fix:** Create `templates/partials/pagination.html` macro. Update all templates.
**Risk:** Low.

### 6.5 Remove inline style attributes
**Files:** `templates/admin/dashboard.html:34,94`, `articles_table.html:31`, `base_admin.html:49`
**Issue:** `style="margin-left:1rem"`, `style="display:inline"` — should use CSS classes.
**Fix:** Add utility classes (`.dash-link-ml`, `.inline-form`).
**Risk:** Low.

### 6.6 Escape content in meta tags and error messages
**Files:** `templates/article.html:7-12`, `templates/admin/login.html:15`
**Issue:** `article.original_title` in `og:title` without escaping. `{{ error }}` without escaping.
**Fix:** Apply `|e` filter to attribute values and error text.
**Risk:** Low.

### 6.7 Convert newsletter dry-run to HTMX
**Files:** `templates/admin/newsletters.html:29-36`, `static/js/newsletters.js`
**Issue:** Only admin form using vanilla `fetch()` instead of HTMX. Adds extra JS file.
**Fix:** Replace with HTMX attributes. Update route to return HTML fragment. Remove `newsletters.js`.
**Risk:** Medium — requires route handler change.

### 6.8 Add admin filter URL persistence
**File:** `templates/admin/articles.html:21,28,39`
**Issue:** Filter/search inputs don't use `hx-push-url`. Filters lost on refresh.
**Fix:** Add `hx-push-url="true"`.
**Risk:** Low.

### 6.9 Add HTMX to admin base template
**File:** `templates/base_admin.html`
**Issue:** Admin templates use `hx-*` attributes extensively, but `base_admin.html` does not load htmx.min.js.
**Fix:** Add `<script src="{{ url_for('static', filename='js/htmx.min.js') }}" defer></script>`.
**Risk:** Low.

---

## Wave 7: Pipeline Resilience & Newsletter

### 7.1 Mitigate limiter slot leaks on release failure
**Files:** `services/limiter.py`, `tasks/pipeline.py:703-705`
**Issue:** When `limiter.release()` fails, concurrency slot leaks until TTL. Sustained Redis instability exhausts slots.
**Fix:** Option A: Periodic cleanup task. Option B: Fallback `DEL`. Option C: Reduce TTL to `timeout + 60s`.
**Risk:** Medium — new cleanup logic.

### 7.2 Record duration histogram for pre-work_fn failures
**File:** `tasks/pipeline.py:run_stage()`
**Issue:** `log_duration()` lives inside `work_fn`. If `run_stage()` fails before calling `work_fn` (lock timeout, provider failure), no duration recorded.
**Fix:** Wrap entire `run_stage()` body in `log_duration()`.
**Risk:** Low.

### 7.3 Atomic lock release with Lua script
**File:** `services/redis_utils.py`, `tasks/pipeline.py:706-709`
**Issue:** Lock release may use separate `GET` → `DEL` (check-then-delete race).
**Fix:** Implement atomic Lua script that only deletes if value matches task ID.
**Risk:** Medium — changes lock semantics.

### 7.4 Add empty content guard before sending newsletters
**File:** `services/newsletter.py:send_newsletter()`
**Issue:** Writer stage failures produce empty summaries. Newsletter pipeline sends broken emails.
**Fix:** Add content validation check. Skip send if empty. Add `newsletter.empty_content_skipped` metric.
**Risk:** Low.

### 7.5 Add newsletter brief validation
**File:** `services/newsletter_pipeline.py:189-206`
**Issue:** Reader stage fallback may produce meaningless briefs (empty themes/highlights).
**Fix:** Validate brief has meaningful content before proceeding to writer.
**Risk:** Low.

### 7.6 Distributed lock for newsletter generation
**File:** `tasks/newsletter.py:generate_daily_newsletters()`
**Issue:** No distributed lock. Concurrent runs could cause duplicate newsletters.
**Fix:** Redis lock with `request.id` as lock value. Use `try/finally` for cleanup.
**Risk:** Low.

### 7.7 Add article version rollback capability
**Files:** `services/article.py`, `routes/admin/api.py`
**Issue:** No mechanism to rollback to previous version after pipeline failure.
**Fix:** Add `rollback_article_version()` function. Add admin API endpoint and UI button.
**Risk:** Medium.

### 7.8 Extend version creation to capture source fields
**File:** `services/article.py:create_article_version()`
**Issue:** Only snapshots `final_article`. Source fields (`original_title`, `original_url`) not versioned.
**Fix:** Extend with optional `source_fields` parameter.
**Risk:** Low.

### 7.9 Ensure `SoftTimeLimitExceeded` handling in all stages
**Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`
**Issue:** Some stages may bypass `run_stage()` or miss the exception in uncovered paths.
**Fix:** Add explicit `except SoftTimeLimitExceeded` after `run_stage()` calls with re-raise.
**Risk:** Low.

---

## Wave 8: Testing

### 8.1 Reduce flaky `time.sleep()` tests in circuit breaker
**File:** `tests/test_circuit_breaker.py:35-75`
**Issue:** 50ms margin (`sleep(0.15)` with `recovery_timeout=0.1`). Fails under CI load.
**Fix:** Mock `time.time()` for deterministic time advancement.
**Risk:** None.

### 8.2 Reduce flaky `time.sleep()` tests in timeout module
**File:** `tests/test_timeout.py:18-40`
**Issue:** Asserts `elapsed < 2.0` after 0.1s timeout.
**Fix:** Mock time or use `pytest.mark.flaky(reruns=2)`.
**Risk:** None.

### 8.3 Extract shared pipeline mock setup
**Files:** `tests/test_pipeline.py`, `test_pipeline_write.py`, `test_pipeline_edit.py`, `test_pipeline_e2e.py`
**Issue:** ~100 lines of duplicated mock configuration across four files.
**Fix:** Create `tests/helpers/pipeline_mocks.py` with shared `setup_pipeline_mocks()`.
**Risk:** Low.

### 8.4 Use context managers for patches in pipeline tests
**Files:** `tests/test_pipeline.py:335-350`, `test_pipeline_write.py:118-160`, `test_pipeline_edit.py:115-159`
**Issue:** Manual `p.start()`/`p.stop()` — patches leak on test failure.
**Fix:** Convert to `with mock.patch(...) as p:` throughout.
**Risk:** None.

### 8.5 Test `_finalize()` review routing
**File:** `tasks/pipeline.py:430-469`
**Issue:** No test for review routing when `auto_publish_threshold` is configured.
**Fix:** Add test for below-threshold → review queue and above-threshold → auto-publish.
**Risk:** None.

### 8.6 Test `_dispatch_next` cache invalidation
**Issue:** No test that `clear_task_fn_cache()` works.
**Fix:** Verify cache is cleared and re-resolved after invalidation.
**Risk:** None.

### 8.7 Test `track_metric` concurrent increment
**File:** `services/article.py:26-51`
**Issue:** No concurrency test for race condition.
**Fix:** Add test simulating concurrent `IntegrityError`.
**Risk:** None.

### 8.8 Test config reload invalidating unified config
**Issue:** No test verifying `reload_config()` invalidates `AppConfig` singleton.
**Fix:** Test: call `get_config()`, modify config, call `reload_config()`, verify new values.
**Risk:** None.

### 8.9 Test pipeline limiter-before-lock ordering
**Issue:** After fixing 3.4, no test verifies limiter acquired before lock.
**Fix:** Mock limiter to succeed but lock to fail, verify `limiter.release()` called.
**Risk:** None.

### 8.10 Add tests for backup verification script
**File:** `scripts/verify_backup.sh`
**Issue:** No test coverage for backup verification.
**Fix:** Test against temporary SQLite database, verify exit codes.
**Risk:** None.

### 8.11 Expand SSRF validation tests
**Issue:** Edge cases for DNS rebinding, IPv6, unusual URL schemes untested.
**Fix:** Add comprehensive edge-case tests. Verify DNS cache under test.
**Risk:** None.

### 8.12 Integration test for pipeline degradation fallback chains
**Issue:** No end-to-end test for LLM provider failures → degradation → pipeline advance.
**Fix:** Simulate provider failures, verify degradation and advancement.
**Risk:** None.

### 8.13 Validate circuit breaker metrics
**Issue:** No test that `circuit_breaker.state_change` and `circuit_breaker.opened` emit correctly.
**Fix:** Trigger circuit breaker transition, verify metric labels.
**Risk:** None.

### 8.14 Test `ModelLimiter` fail-closed behavior
**Issue:** Need to verify `ModelLimiter` returns `False` when Redis unavailable.
**Fix:** Use `mock_redis` fixture with Redis error, verify deny.
**Risk:** None.

---

## Wave 9: Documentation & Developer Experience

### 9.1 Create `CONTRIBUTING.md`
**Issue:** No contributor documentation.
**Fix:** Document test running, linting, local environment setup, PR submission.
**Risk:** None.

### 9.2 Improve error messages in admin UI
**Issue:** Generic "Failed to start crawl" without specifics.
**Fix:** Show specific error details when safe.
**Risk:** Low.

### 9.3 Verify Celery retry patterns
**Files:** All `tasks/` files
**Issue:** Some tasks may use manual `self.retry()` instead of `autoretry_for`.
**Fix:** Audit and convert to decorator-based retry where applicable.
**Risk:** Low.

### 9.4 Simplify health-check logic
**File:** `services/health.py`
**Issue:** Nested try/except blocks could be clearer.
**Fix:** Extract sub-checks into named functions.
**Risk:** Low.

---

## Verification

After each wave:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

After all waves:
```bash
.venv/bin/python -m pytest tests/ --tb=short -q
```

---

## Parallelization Strategy

Waves are ordered by dependency. Within each wave, tasks are independent and can be assigned to sub-agents:

| Wave | Focus | Parallelizable? | Sub-agent count |
|------|-------|-----------------|-----------------|
| 1 | Critical bugs | Yes — all independent | Up to 14 |
| 2 | Security fixes | Yes — all independent | Up to 10 |
| 3 | Performance | Mostly — 3.4 (limiter) and 3.6 (find_duplicate) touch same area | Up to 7 |
| 4 | Accessibility + UX | Yes — all independent | Up to 14 |
| 5 | Code quality + CSS | Yes — backend and CSS are separate domains | Up to 17 |
| 6 | Template DRY + admin | Yes — all independent | Up to 9 |
| 7 | Pipeline resilience | Mostly — 7.3 (lock) and 7.1 (limiter) related | Up to 9 |
| 8 | Testing | Yes — all independent | Up to 14 |
| 9 | Documentation | Yes — all independent | Up to 4 |

**Recommended parallel execution:**
- Waves 1 + 2 can start simultaneously (bugs and security are independent domains)
- Waves 3 + 4 can start once their dependencies in Wave 1 are complete
- Wave 5 (CSS) can run parallel with Wave 5 (backend code quality) — different file domains
- Wave 6 (templates) is independent of Wave 7 (pipeline)
- Wave 8 (testing) should run after corresponding production fixes land

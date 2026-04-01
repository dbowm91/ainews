# Consolidated Improvement Plan

Consolidated from plan2–plan7 (original review date: 2026-04-01). Items verified against the codebase before inclusion. Organized into waves for parallel sub-agent execution — each wave contains independent items that can be worked on simultaneously.

**Status: Not started**

---

## Wave 1 — Security & Critical Bugs (parallel: different files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 1.1 | plan3 #5 | Critical | Remove dead `_hash_password()` (SHA256, no salt) — never called but a footgun if accidentally used | `services/validation.py:128-132` |
| 1.2 | plan3 #1 | Critical | `run_stage()` sets `retry_count=0` and `last_error=None` after success but never commits — resets silently lost | `tasks/pipeline.py:674-675` |
| 1.3 | plan3 #2 | Critical | `run_all_sources` never marks pipeline runs as `"completed"` — stays in `"running"` forever | `tasks/crawl.py:261-272` |
| 1.4 | plan3 #3 | Critical | `_dead_letter()` skips `create_article_version()` — breaks audit trail for dead-lettered articles | `tasks/retry.py:128-152` |
| 1.5 | plan3 #4 | Critical | Missing `try/except redis.exceptions.RedisError` around `redis_client.get()` in newsletter lock check — crashes task on Redis failure | `tasks/newsletter.py:308-320` |

**1.1 Fix:** Delete `_hash_password()` and its import references. Verify `scripts/hash_password.py` uses werkzeug if it exists. The actual login system uses `werkzeug.security.check_password_hash()`.

**1.2 Fix:** Add `db.session.commit()` after resetting retry counters, wrapped in try/except with rollback.

**1.3 Fix:** Set `run.status = "completed"` in the success path (when `not timed_out and not (errors > 0 and total_new == 0)`).

**1.4 Fix:** Call `create_article_version(article, change_reason="dead_letter", changed_by="retry_stuck")` before marking article as failed in `_dead_letter()`.

**1.5 Fix:** Wrap `redis_client.get(lock_key)` and `existing.decode()` block (lines 308-320) in `try/except redis.exceptions.RedisError` and treat failure as "lock held" (skip execution).

---

## Wave 2 — Pipeline Correctness & Concurrency (parallel: different files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 2.1 | plan2 #5 | Medium | Limiter slot leak — acquire uses `rc.model` but release uses potentially different `model` from `get_provider_for_role()` | `tasks/pipeline.py:598,669,721-723` |
| 2.2 | plan2 #6 | Medium | Circuit breaker TOCTOU race — `can_execute()` reads `self.state` outside lock, HALF_OPEN branch re-acquires separately | `services/circuit_breaker.py:156-179` |
| 2.3 | plan2 #7 | Medium | None dereference — `article.original_title[:50]` crashes if title is None | `routes/admin/review.py:69,94` |
| 2.4 | plan2 #13 | Low | Dead code — `_check_stage_limiter()` never returns falsy value, `if not limiter` branch unreachable | `tasks/pipeline.py:646-647` |
| 2.5 | plan2 #15 | Low | Non-thread-safe `_task_fn_cache` dict — needs `threading.Lock` | `tasks/pipeline.py:100-106` |
| 2.6 | plan3 #10 | Medium | `_bulk_reprocess` non-atomic — commits DB first, dispatches tasks second; if dispatch fails, articles stuck | `routes/admin/api.py:284-312` |
| 2.7 | plan3 #11 | Medium | `_log_pipeline` re-raises on error-level — log write failure can mask original exception | `tasks/pipeline.py:188-190` |

**2.1 Fix:** Save acquire-time provider/model and use those for release. Or restructure to call `get_provider_for_role()` before limiter acquire so `CircuitOpenError` degrades without acquiring.

**2.2 Fix:** Perform state check and half-open increment in a single lock hold. Eliminate the separate `state` property's lock-release-reacquire pattern for internal callers.

**2.3 Fix:** Use `(article.original_title or "")[:50]` in both `approve_article` and `reject_article`.

**2.4 Fix:** Remove the `if not limiter:` branch and the associated return statement.

**2.5 Fix:** Add `threading.Lock` around cache read-check-then-write in `_dispatch_next()`.

**2.6 Fix:** Dispatch tasks first (collecting results), then commit only if all dispatches succeed. Rollback on any dispatch failure.

**2.7 Fix:** Remove the `if level == "error": raise` block. The write failure is already logged via stdlib logger.

---

## Wave 3 — UI: Missing CSS Classes (parallel: single file additions)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 3.1 | plan5 #1 / plan6 #3 | High | Error page templates use `.error-page`, `.error-title`, `.error-message` — no CSS defined | `static/css/style.css` (add rules) |
| 3.2 | plan5 #2 / plan6 #2 | High | `.unsubscribe-confirm-btn` used in `unsubscribe.html` — no CSS defined | `static/css/style.css` (add rules) |
| 3.3 | plan5 #3 / plan6 #1 | High | `.btn-small` used in sources templates — only `.btn-sm` exists | `templates/admin/sources.html`, `templates/admin/partials/source_row.html` (rename to `.btn-sm`) |
| 3.4 | plan6 #10 | Low | `.card-author` used in `article_card.html` — no specific CSS | `static/css/style.css` (add subtle rule) |
| 3.5 | plan6 #11 | Medium | `.btn-primary` missing `display: inline-block` — causes padding/margin quirks | `static/css/style.css:2312` (add display rule) |

**3.1 Fix:** Add `.error-page` (centered flexbox, min-height), `.error-title` (large monospace, accent color), `.error-message` (muted text) in the Errors & Empty States section.

**3.2 Fix:** Add `.unsubscribe-confirm-btn` rule matching `.btn-primary` pattern.

**3.3 Fix:** Rename `btn-small` to `btn-sm` in both `sources.html` (lines 99, 101) and `source_row.html` (lines 33, 35). Cleaner than maintaining two class names.

**3.4 Fix:** Add subtle `.card-author` rule for visual distinction.

**3.5 Fix:** Add `display: inline-block` to `.btn-primary`. Remove redundant `inline-block` utility class from `admin/sources.html` button markup.

---

## Wave 4 — Template Cleanup & Deduplication (parallel: different files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 4.1 | plan6 #4 (partial) | High | Delete dead template partials — never `{% include %}`'d | Delete: `partials/article_detail.html`, `partials/cards.html`, `partials/skeleton_loading.html`, `partials/skeleton_card.html`, `admin/partials/pipeline_logs.html` |
| 4.2 | plan5 #4 / plan6 #8 | Medium | Extract shared article rendering from `article.html` into a partial (after deleting dead `article_detail.html`) | `templates/partials/article_body.html` (new), `templates/article.html`, `templates/partials/article_detail.html` |
| 4.3 | plan5 #5 | Medium | Use shared `pagination_nav` macro in `review_table.html` and `pipeline_logs.html` | `templates/admin/partials/review_table.html:50-66`, `templates/admin/partials/pipeline_logs.html:26-42` |
| 4.4 | plan5 #6 | Medium | Fix pagination macro — add `urlencode` filter to values | `templates/partials/pagination.html:3-7` |

**Note:** `admin/partials/source_row.html` is NOT dead — it's used as an HTMX swap target by `routes/admin/sources.py:66`. Do NOT delete.

**4.1 Fix:** Delete the 5 dead partials listed above. They duplicate content that exists inline in parent templates.

**4.2 Fix:** Create `partials/article_body.html` with the `_fa` / `_summary` / fallback branching logic. Both `article.html` and `article_detail.html` (if kept) should `{% include %}` it.

**4.3 Fix:** Import `pagination_nav()` macro and replace inline pagination in both templates.

**4.4 Fix:** Apply `urlencode` filter to values in the query string builder.

---

## Wave 5 — Admin Templates & Script Gaps (parallel: different files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 5.1 | plan6 #6 | High | `base_admin.html` missing `app.js` — no offline detection, HTMX error toasts, search shortcut | `templates/base_admin.html` (add script tag) |
| 5.2 | plan6 #13 | Low | `base_admin.html` missing offline toast markup | `templates/base_admin.html` (add `#offline-toast`) |
| 5.3 | plan6 #14 | Low | `base_admin.html` missing toast container | `templates/base_admin.html` (add `#toast-container`) |
| 5.4 | plan6 #7 | High | `share_redirect.html` missing `theme.js` — always renders dark theme | `templates/share_redirect.html` (add script) |
| 5.5 | plan5 #8 | Medium | `admin/login.html` missing `data-theme` on `<html>` | `templates/admin/login.html:2` (add `data-theme="dark"`) |
| 5.6 | plan5 #7 | Medium | `verify.html` uses inline hardcoded colors — doesn't use site design system | `templates/verify.html`, `static/css/style.css` |
| 5.7 | plan5 #9 | Medium | Inline styles in `share_redirect.html` and `base_admin.html` — extract to CSS classes | `templates/share_redirect.html`, `templates/base_admin.html:35`, `static/css/style.css` |
| 5.8 | plan6 #12 | Low | Duplicate share toggle listeners in `app.js` and `share-a11y.js` — consolidate | `static/js/app.js:32-38`, `static/js/share-a11y.js:5-12` |
| 5.9 | plan5 #17 | Low | No `<noscript>` fallback — HTMX-dependent app has no message for non-JS users | `templates/base.html`, `templates/base_admin.html`, `static/css/style.css` |

**5.1 Fix:** Add `<script src="{{ url_for('static', filename='js/app.js') }}" defer></script>` to `base_admin.html`.

**5.2 Fix:** Add `<div id="offline-toast" class="offline-toast" hidden>You are offline.</div>` after `<body>`.

**5.3 Fix:** Add `<div id="toast-container" aria-live="polite" aria-atomic="true"></div>` after `<body>`.

**5.4 Fix:** Add `<script src="{{ url_for('static', filename='js/theme.js') }}"></script>` before `app.js`.

**5.5 Fix:** Add `data-theme="dark"` to `<html>` tag. Optionally load `theme.js`.

**5.6 Fix:** Remove inline `<style>`, load `style.css`, set `data-theme`, add `.verify-page` class.

**5.7 Fix:** Replace inline `style` attributes with CSS classes. Add `.share-redirect-*` classes to `style.css`. Replace `style="display:inline"` on admin logout form with `.inline` class.

**5.8 Fix:** Merge the two `toggle` event listeners into `share-a11y.js`. Remove duplicate from `app.js`.

**5.9 Fix:** Add `.noscript-warning` class to CSS. Add `<noscript>` block after `<body>` in both base templates.

---

## Wave 6 — Subscriber Export & Dashboard (parallel: different files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 6.1 | plan2 #8 | Medium | Subscriber export loads all records into memory — OOM risk at scale | `routes/admin/subscribers.py:57-61` |
| 6.2 | plan2 #1 | Low | Dashboard N+1 potential — template doesn't access `article.source` today but the query lacks eager loading | `routes/admin/dashboard.py:26` |

**6.1 Fix:** Use `yield_per(500)` with a generator to stream CSV output. Return `Response` with `mimetype="text/csv"`.

**6.2 Fix:** Add `joinedload(Article.source)` to the dashboard query as a preventive measure. Currently not triggered but will become a problem if template changes.

---

## Wave 7 — Testing & Coverage (parallel: different test files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 7.1 | plan2 #3 | High | Skipped health endpoint test — permanently `@pytest.mark.skip` | `tests/test_admin_api.py:21-24` |
| 7.2 | plan2 #12 / plan3 #9 | Medium | Missing test coverage: article edit, newsletter preview, bulk add_tags, circuit breaker HALF_OPEN→OPEN | Various test files |
| 7.3 | plan3 #6 | Medium | No coverage metrics — add `pytest-cov` with threshold | `requirements-dev.txt`, `pyproject.toml`, `Makefile` |
| 7.4 | plan3 #7 | Medium | Convert `patch.start()/stop()` patterns to fixtures — patches leak on assertion failure | `tests/test_pipeline.py`, `tests/helpers/pipeline_mocks.py` |
| 7.5 | plan3 #8 | Medium | Duplicate `auth_client` fixture in `test_admin_api.py` and `test_routes.py` — consolidate to `conftest.py` | `tests/conftest.py`, `tests/test_admin_api.py`, `tests/test_routes.py` |
| 7.6 | plan3 #18 | Low | `test_integration.py` manually creates models instead of using factory fixtures | `tests/test_integration.py` |

**7.1 Fix:** Add `db.session.remove()` after health endpoint call to reset SQLAlchemy connection state. If that fails, move the test to a separate file with its own app fixture.

**7.2 Fix:** Add tests for: article edit GET/POST, newsletter preview endpoint, bulk `add_tags` action, circuit breaker failure in HALF_OPEN state.

**7.3 Fix:** Add `pytest-cov` to dev deps. Configure `[tool.coverage]` in `pyproject.toml` with 70% threshold initially. Exclude `.venv/`, `migrations/`, `instance/`.

**7.4 Fix:** Convert to `@pytest.fixture` with `yield` and proper cleanup. Use generator-style fixtures.

**7.5 Fix:** Move `auth_client` fixture to `tests/conftest.py`. Remove from `test_admin_api.py` and `test_routes.py`.

**7.6 Fix:** Replace manual `Source()`/`Article()` construction with `create_source()`/`create_article()` factories.

---

## Wave 8 — Code Quality & Maintenance (parallel: different files)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 8.1 | plan2 #2 | High | Duplicated reprocess stage logic — three near-identical blocks | `routes/admin/articles.py:339-396` |
| 8.2 | plan2 #10 | Medium | Silent exception swallowing — `except Exception: pass` in reader stage | `services/newsletter_pipeline.py:205` |
| 8.3 | plan2 #14 | Low | Duplicate dead-letter logic — `_dead_letter()` reimplements `dead_letter_article()` | `tasks/retry.py:128-152`, `services/dead_letter.py` |
| 8.4 | plan2 #16 | Low | Misleading operator precedence — `and`/`or` without explicit parens | `routes/admin/articles.py:12-19` |
| 8.5 | plan3 #12 | Low | F-string log calls violate project convention (use %-formatting) | `tasks/extract.py:167,172` |
| 8.6 | plan3 #13 | Low | Non-thread-safe `_TAG_CACHE` | `tasks/edit.py:10-25` |
| 8.7 | plan3 #14 | Low | Duplicate `_admin_categories()` function — consolidate | `routes/admin/__init__.py:93-100`, `routes/admin/articles.py:5` |
| 8.8 | plan2 #18 | Low | Lock TTL buffer too tight — `rc.timeout_seconds + 60` equals hard kill limit | `tasks/pipeline.py:653` |

**8.1 Fix:** Refactor to a data-driven table mapping stage → (status, fields_to_clear, task_function). Single handler replaces three blocks.

**8.2 Fix:** Replace `pass` with `logger.warning("Failed to parse reader stage output", exc_info=True)`. Also check `services/limiter.py:72`.

**8.3 Fix:** Replace `_dead_letter()` in `retry.py` with a call to `dead_letter_article()` from `services/dead_letter.py`.

**8.4 Fix:** Add explicit parentheses: `or ("/" in query and "." in query)`.

**8.5 Fix:** Convert `f"..."` to `logger.info("...", arg)` %-formatting in `tasks/extract.py:167,172`.

**8.6 Fix:** Add `threading.Lock` with double-checked locking pattern around `_TAG_CACHE` access.

**8.7 Fix:** Extract to a shared function in `services/` or `schemas/` and import from a single location.

**8.8 Fix:** Increase buffer to `rc.timeout_seconds + 120` for a 2-minute window after hard kill.

---

## Wave 9 — UI Polish & Responsive (parallel: different CSS areas)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 9.1 | plan5 #10 | Medium | Add tablet breakpoint (~768px) — 3-column grids jump to 1 column | `static/css/style.css` |
| 9.2 | plan5 #11 | Medium | Theme toggle and RSS link inaccessible in mobile hamburger menu | `templates/base.html`, `templates/base_admin.html`, `static/css/style.css` |
| 9.3 | plan5 #12 | Low | Toast entrance animation — toasts pop into existence with no animation | `static/css/style.css` |
| 9.4 | plan5 #13 | Low | Hamburger menu has no transition — snaps open/closed | `static/css/style.css` |
| 9.5 | plan5 #14 | Low | Hardcoded z-index values — extract to CSS custom properties | `static/css/style.css` |
| 9.6 | plan5 #15 | Low | Missing standard `line-clamp` alongside `-webkit-line-clamp` | `static/css/style.css:585` |
| 9.7 | plan5 #16 | Low | Tracked `.DS_Store` file in repo | `static/.DS_Store` (git rm --cached) |
| 9.8 | plan6 #9 | Medium | Font size scale naming mismatch — `--text-8xl: 1.6rem` is misleading | `static/css/style.css:58-70` |

**9.1 Fix:** Add `@media (max-width: 768px)` rules: 3-col → 2-col grids, intermediate font sizes.

**9.2 Fix:** Duplicate theme toggle and RSS link inside `.nav-links` container for mobile hamburger menu. On admin, include logout too.

**9.3 Fix:** Add `@keyframes toast-in` with translateY + opacity transition.

**9.4 Fix:** Replace `display: none/flex` with `max-height` + `opacity` transition on `.nav-links` mobile state.

**9.5 Fix:** Add `--z-header: 100`, `--z-dropdown: 200`, `--z-toast: 9999`, `--z-progress: 9999` custom properties. Replace all hardcoded values.

**9.6 Fix:** Add `line-clamp: 2` immediately after each `-webkit-line-clamp` declaration.

**9.7 Fix:** `git rm --cached static/.DS_Store`.

**9.8 Fix:** Rename scale to purpose-based names or add clarifying comments. ~20-30 references to update.

---

## Wave 10 — API Standardization & Deployment (parallel: different concerns)

| # | Source | Severity | Item | File(s) |
|---|--------|----------|------|---------|
| 10.1 | plan2 #9 | Medium | Inconsistent API error response format — some use `"message"`, some `"error"` | Multiple route files |
| 10.2 | plan2 #4 | High | Duplicate dependency declarations in `requirements.txt` and `pyproject.toml` | `requirements.txt`, `pyproject.toml` |
| 10.3 | plan2 #11 | Low | `granian` not version-pinned in Dockerfile | `Dockerfile`, `pyproject.toml` |
| 10.4 | plan2 #19 | Low | Dev dependencies not pinned — `pytest>=7.0` etc. | `requirements-dev.txt`, `pyproject.toml` |
| 10.5 | plan2 #17 | Low | Missing return type annotations on route handlers | Multiple route files |
| 10.6 | plan3 #15 | Low | Feed route doesn't validate category against topic config | `routes/public/feeds.py` |
| 10.7 | plan3 #16 | Low | Wasted query in `track_share_click` — fetches article but never uses it | `routes/public/links.py` |
| 10.8 | plan3 #17 | Low | Missing `# HELP` lines in Prometheus metrics output | `services/metrics.py:87-104` |

**10.1 Fix:** Standardize on `{"error": "..."}` for error responses, keep `{"message": "..."}` for success. Update test assertions.

**10.2 Fix:** Make `pyproject.toml` the single source of truth. Add Makefile target to generate `requirements.txt` via `pip-compile`.

**10.3 Fix:** Pin granian version in Dockerfile. Add as optional dependency in `pyproject.toml`.

**10.4 Fix:** Pin dev deps to exact versions: `pytest==8.3.4`, `pytest-cov==6.0.0`, `ruff==0.9.0`.

**10.5 Fix:** Add `-> str | Response` return type annotations to route handlers.

**10.6 Fix:** Validate category against topic config in `feed_topic()`. Return 404 for unknown categories.

**10.7 Fix:** Replace `get_or_404` with simple existence check, or remove query entirely.

**10.8 Fix:** Add `# HELP` lines before each `# TYPE` line in `get_prometheus()`.

---

## Wave 11 — New Feature: Subagent System + Editor Contextualization (sequential: large feature)

| # | Source | Item | File(s) |
|---|--------|------|---------|
| 11.1 | plan7 #1 | Schema: Add `SubagentConfig`, `SubagentStageConfig` models and `resolve_subagent_config()` | `schemas/pipeline.py` |
| 11.2 | plan7 #2 | DB: New `TopicNote` model + migration | `models.py`, `migrations/versions/` |
| 11.3 | plan7 #3 | New service: `services/subagent.py` — `run_subagent()`, task templates, response models | `services/subagent.py` (new) |
| 11.4 | plan7 #4 | New service: `services/context_service.py` — topic note CRUD, related articles lookup | `services/context_service.py` (new) |
| 11.5 | plan7 #5 | Editor flow: Add contextualization phase before LLM call | `tasks/edit.py`, `services/editor.py` |
| 11.6 | plan7 #6 | Research flow: Pre-process web results via subagent | `tasks/research.py`, `services/researcher.py` |
| 11.7 | plan7 | Config: Add `subagent.default` section and update editor system prompt | `pipeline.yaml` |
| 11.8 | plan7 #9 | Tests: Unit + integration tests for subagent framework | `tests/test_subagent.py`, `tests/test_context_service.py`, `tests/test_edit_contextualization.py`, `tests/test_research_subagent.py` |

**Design decisions (from plan7):**
- Subagents run synchronously within parent Celery task (no new task types)
- Notes stored in SQLite `topic_notes` table with service layer
- Research subagent splits work by search type (sequential calls)
- All subagent calls are non-blocking — failures degrade gracefully
- Subagents never perform I/O — caller fetches data, passes to subagent for synthesis

---

## Wave 12 — CSS Architecture & Documentation (sequential: large refactoring)

| # | Source | Item | File(s) |
|---|--------|------|---------|
| 12.1 | plan4 #1.1 | CSS module extraction — split `style.css` (2,774 lines) into focused modules | `static/css/` restructure |
| 12.2 | plan4 #1.2 | Component documentation — badge system, article card, share button, theme toggle | `docs/components/` (new) |
| 12.3 | plan4 #1.3 | CSS custom properties audit — add semantic aliases, document all variables | `static/css/style.css` |
| 12.4 | plan4 #2.1 | Critical CSS extraction — inline above-the-fold styles | `templates/base.html` |

---

## Verification Checklist

After each wave, run:

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

After UI waves (3, 4, 5, 9), also visually verify:
- Error pages at `/nonexistent` and admin 500 trigger
- Unsubscribe page with valid token
- Admin sources page enable/disable buttons
- Mobile hamburger menu at 640px and 768px
- Share redirect page theme support

---

## Dependencies Between Waves

- **Wave 4.1** (delete dead partials) should precede **Wave 4.2** (extract article_body partial)
- **Wave 5.1** (add app.js to admin) should precede **Wave 5.2/5.3** (add offline toast and toast container)
- **Wave 11** (subagent system) is a large feature — do after waves 1-8 are stable
- **Wave 12** (CSS architecture) is a large refactoring — do after waves 3-5 fix immediate CSS issues

All other waves are fully independent and can be parallelized.

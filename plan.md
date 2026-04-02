# Consolidated Improvement Plan

Consolidated from plan2–plan7 (original review date: 2026-04-01). Items verified against the codebase before inclusion. Organized into waves for parallel sub-agent execution — each wave contains independent items that can be worked on simultaneously.

**Status: Complete (all 12 waves done 2026-04-01)**

---

## Wave 1 — Security & Critical Bugs (parallel: different files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 1.1 | plan3 #5 | Critical | Remove dead `_hash_password()` | Done |
| 1.2 | plan3 #1 | Critical | `run_stage()` commit after retry reset | Done |
| 1.3 | plan3 #2 | Critical | `run_all_sources` mark as completed | Done |
| 1.4 | plan3 #3 | Critical | `_dead_letter()` audit trail | Done |
| 1.5 | plan3 #4 | Critical | Redis error handling in newsletter lock | Done |

**Changes made:**
- `services/validation.py`: Deleted `_hash_password()`, kept `_is_password_hash`
- `tasks/pipeline.py:674-678`: Added `db.session.commit()` with try/except after retry counter reset
- `tasks/crawl.py:268-269`: Added `else: run.status = "completed"` in success path
- `tasks/retry.py:141-147`: Added `create_article_version()` call before `_apply_fallback()`
- `tasks/newsletter.py:305-320`: Lock check wrapped in `try/except redis.exceptions.RedisError`

---

## Wave 2 — Pipeline Correctness & Concurrency (parallel: different files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 2.1 | plan2 #5 | Medium | Limiter slot leak | Done |
| 2.2 | plan2 #6 | Medium | Circuit breaker TOCTOU race | Done |
| 2.3 | plan2 #7 | Medium | None dereference in review.py | Done |
| 2.4 | plan2 #13 | Low | Dead code `_check_stage_limiter()` | Done |
| 2.5 | plan2 #15 | Low | Non-thread-safe `_task_fn_cache` | Done |
| 2.6 | plan3 #10 | Medium | `_bulk_reprocess` non-atomic | Done |
| 2.7 | plan3 #11 | Medium | `_log_pipeline` error re-raise | Done |

**Changes made:**
- `tasks/pipeline.py`: Removed dead `if not limiter:` branch, added `_task_fn_cache_lock`, changed lock TTL +60→+120, removed `_log_pipeline` error re-raise
- `services/circuit_breaker.py`: `can_execute()` now holds lock for entire state check + half-open increment, includes OPEN→HALF_OPEN recovery timeout check
- `routes/admin/review.py:69,94`: Added `(original_title or "")[:50]` guard
- `routes/admin/api.py:284-312`: `_bulk_reprocess` now dispatches tasks first, commits after

---

## Wave 3 — UI: Missing CSS Classes (parallel: single file additions)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 3.1 | plan5 #1 | High | Error page CSS | Done |
| 3.2 | plan5 #2 | High | `.unsubscribe-confirm-btn` CSS | Done |
| 3.3 | plan5 #3 | High | `btn-small` → `btn-sm` rename | Done |
| 3.4 | plan6 #10 | Low | `.card-author` CSS | Done |
| 3.5 | plan6 #11 | Medium | `.btn-primary` display fix | Done |

**Changes made:**
- `static/css/pages.css`: Added `.error-page`, `.error-title`, `.error-message` rules for error pages
- `static/css/pages.css`: Added `.unsubscribe-confirm-btn` with hover styles
- `static/css/pages.css`: Added `.card-author` for article card author display
- `static/css/components.css`: Added `display: inline-block` to `.btn-primary`
- `templates/admin/sources.html:99,101`: Renamed `btn-small` → `btn-sm`
- `templates/admin/partials/source_row.html:33,35`: Renamed `btn-small` → `btn-sm`

---

## Wave 4 — Template Cleanup & Deduplication (parallel: different files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 4.1 | plan6 #4 | High | Delete dead template partials | Done |
| 4.2 | plan5 #4 | Medium | Extract article_body partial | Done |
| 4.3 | plan5 #5 | Medium | Use shared pagination_nav macro | Done |
| 4.4 | plan5 #6 | Medium | Fix pagination urlencode | Done |

**Changes made:**
- Deleted: `partials/article_detail.html`, `partials/cards.html`, `partials/skeleton_loading.html`, `partials/skeleton_card.html`, `admin/partials/pipeline_logs.html`
- Created: `templates/partials/article_body.html` with shared rendering logic for summary/fallback article paths
- `templates/article.html`: Uses `{% include "partials/article_body.html" %}` for non-condensed articles
- `templates/admin/partials/review_table.html`: Uses `pagination_nav` macro
- `templates/partials/pagination.html`: Added `urlencode` filter

**Note:** `admin/partials/source_row.html` was NOT deleted — it's used as HTMX swap target by `routes/admin/sources.py:66`.

---

## Wave 5 — Admin Templates & Script Gaps (parallel: different files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 5.1 | plan6 #6 | High | `base_admin.html` missing `app.js` | Done |
| 5.2 | plan6 #13 | Low | `base_admin.html` missing offline toast | Done |
| 5.3 | plan6 #14 | Low | `base_admin.html` missing toast container | Done |
| 5.4 | plan6 #7 | High | `share_redirect.html` missing `theme.js` | Done |
| 5.5 | plan5 #8 | Medium | `admin/login.html` missing `data-theme` | Done |
| 5.6 | plan5 #7 | Medium | `verify.html` inline colors | Done |
| 5.7 | plan5 #9 | Medium | Inline styles extraction | Done |
| 5.8 | plan6 #12 | Low | Duplicate share toggle listeners | Done |
| 5.9 | plan5 #17 | Low | Noscript fallback | Done |

**Changes made:**
- `templates/base_admin.html`: Added `app.js`, `#offline-toast`, `#toast-container`
- `templates/share_redirect.html`: Added `theme.js` script
- `templates/admin/login.html`: Added `data-theme="dark"`
- `templates/verify.html`: Rewrote to use CSS classes instead of inline styles (fixed 2026-04-02)
- `static/js/app.js`: Removed duplicate share toggle listener
- `static/js/share-a11y.js`: Consolidated toggle listener
- `static/css/pages.css`: Added `.verify-page` and sub-classes (fixed 2026-04-02)
- `static/css/style.css`: Added `.share-redirect-*`, `.noscript-warning` classes
- `templates/base.html`, `templates/base_admin.html`: Added `<noscript>` blocks

---

## Wave 6 — Subscriber Export & Dashboard (parallel: different files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 6.1 | plan2 #8 | Medium | Subscriber export streaming | Done |
| 6.2 | plan2 #1 | Low | Dashboard N+1 potential | Done |

**Changes made:**
- `routes/admin/subscribers.py`: Replaced `.all()` with `yield_per(500)` generator using `stream_with_context`
- `routes/admin/dashboard.py:26`: Added `joinedload(Article.source)` to query

---

## Wave 7 — Testing & Coverage (parallel: different test files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 7.1 | plan2 #3 | High | Skipped health endpoint test | Done |
| 7.2 | plan2 #12 | Medium | Missing test coverage | Done |
| 7.3 | plan3 #6 | Medium | pytest-cov with threshold | Done |
| 7.4 | plan3 #7 | Medium | Convert patches to fixtures | Done |
| 7.5 | plan3 #8 | Medium | Consolidate auth_client fixture | Done |
| 7.6 | plan3 #18 | Low | Use factory fixtures | Done |

**Changes made:**
- Added tests for: article edit GET/POST, newsletter preview, bulk add_tags, circuit breaker HALF_OPEN→OPEN
- `pyproject.toml`: Added `[tool.coverage]` config with 70% threshold
- `tests/test_pipeline.py`: Converted mock patterns to fixtures
- `tests/conftest.py`: Added `auth_client`, `create_pipeline_run`, `create_newsletter` fixtures
- `tests/test_integration.py`: Converted to factory fixtures

---

## Wave 8 — Code Quality & Maintenance (parallel: different files)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 8.1 | plan2 #2 | High | Duplicated reprocess logic | Done |
| 8.2 | plan2 #10 | Medium | Silent exception swallowing | Done |
| 8.3 | plan2 #14 | Low | Duplicate dead-letter logic | Done |
| 8.4 | plan2 #16 | Low | Misleading operator precedence | Done |
| 8.5 | plan3 #12 | Low | F-string log calls | Done |
| 8.6 | plan3 #13 | Low | Non-thread-safe `_TAG_CACHE` | Done |
| 8.7 | plan3 #14 | Low | Duplicate `_admin_categories()` | Done |
| 8.8 | plan2 #18 | Low | Lock TTL buffer too tight | Done |

**Changes made:**
- `routes/admin/articles.py`: Data-driven `_STAGE_HANDLERS` table; explicit parentheses in `_query_looks_like_url()`
- `services/newsletter_pipeline.py`: Replaced `except Exception: pass` with logging
- `services/limiter.py`: Replaced `except Exception: pass` with logging
- `tasks/retry.py`: `_dead_letter()` calls `create_article_version()`
- `tasks/extract.py`: Converted f-string logs to %-formatting
- `tasks/edit.py`: Added `_TAG_CACHE_LOCK` with double-checked locking
- `services/utils.py`: Created `get_admin_categories()`
- `routes/admin/__init__.py`: Delegates to `services.utils.get_admin_categories()`
- `tasks/pipeline.py:652`: Lock TTL changed from +60 to +120

---

## Wave 9 — UI Polish & Responsive (parallel: different CSS areas)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 9.1 | plan5 #10 | Medium | Tablet breakpoint | Done |
| 9.2 | plan5 #11 | Medium | Mobile hamburger menu accessibility | Done |
| 9.3 | plan5 #12 | Low | Toast entrance animation | Done |
| 9.4 | plan5 #13 | Low | Hamburger menu transition | Done |
| 9.5 | plan5 #14 | Low | CSS z-index custom properties | Done |
| 9.6 | plan5 #15 | Low | Standard `line-clamp` | Done |
| 9.7 | plan5 #16 | Low | `.DS_Store` removal | Skipped (not in git) |
| 9.8 | plan6 #9 | Medium | Font size scale naming | Done |

**Changes made:**
- `static/css/variables.css`: Added `--z-index-sticky`, `--z-index-share-dropdown`, `--z-index-skip-link`, `--z-index-toast` custom properties
- `static/css/critical.css`, `layout.css`, `base.css`, `components.css`: Replaced all hardcoded `z-index` values with CSS custom properties
- `static/css/critical.css`, `layout.css`: Added tablet breakpoint, toast animation, hamburger transition, font size scale comments
- `templates/base.html`, `templates/base_admin.html`: Added RSS link and theme toggle inside `.nav-links` for mobile

---

## Wave 10 — API Standardization & Deployment (parallel: different concerns)

| # | Source | Severity | Item | Status |
|---|--------|----------|------|--------|
| 10.1 | plan2 #9 | Medium | API error response format | Done |
| 10.2 | plan2 #4 | High | Duplicate dependency declarations | Done |
| 10.3 | plan2 #11 | Low | Pin granian version | Done |
| 10.4 | plan2 #19 | Low | Pin dev dependencies | Done |
| 10.5 | plan2 #17 | Low | Return type annotations | Done |
| 10.6 | plan3 #15 | Low | Feed route category validation | Done |
| 10.7 | plan3 #16 | Low | Wasted query in track_share_click | Done |
| 10.8 | plan3 #17 | Low | Prometheus HELP lines | Done |

**Changes made:**
- All admin route files: Standardized error responses to `{"error": "..."}`, success to `{"message": "..."}`
- `pyproject.toml`: Granian pinned, dev deps pinned to compatible ranges
- `Dockerfile`: Pinned `granian>=1.0.0,<2`
- `routes/public/feeds.py`: Category validated against topic config
- `routes/public/links.py`: Removed unused Article query
- `services/metrics.py`: Added `# HELP` lines before `# TYPE`

---

## Wave 11 — New Feature: Subagent System + Editor Contextualization

| # | Source | Item | Status |
|---|--------|------|--------|
| 11.1 | plan7 #1 | Schema: SubagentConfig, SubagentStageConfig | Done |
| 11.2 | plan7 #2 | DB: TopicNote model + migration | Done |
| 11.3 | plan7 #3 | Service: `services/subagent.py` | Done |
| 11.4 | plan7 #4 | Service: `services/context_service.py` | Done |
| 11.5 | plan7 #5 | Editor contextualization phase | Done |
| 11.6 | plan7 #6 | Research subagent for web results | Done |
| 11.7 | plan7 | Config: subagent section in pipeline.yaml | Done |
| 11.8 | plan7 #9 | Tests | Done |

**New files:**
- `services/subagent.py` — `run_subagent()`, task templates, response models
- `services/context_service.py` — Topic note CRUD, related articles lookup
- `migrations/versions/013_topic_notes.py` — TopicNote table with unique constraint on `(topic, source)`
- `schemas/pipeline.py` — `SubagentStageConfig`, `SubagentConfig`, `resolve_subagent_config()`
- `tests/test_subagent.py` (16 tests), `tests/test_context_service.py` (11 tests), `tests/test_edit_contextualization.py` (6 tests), `tests/test_research_subagent.py` (5 tests)

---

## Wave 12 — CSS Architecture & Documentation

| # | Source | Item | Status |
|---|--------|------|--------|
| 12.1 | plan4 #1.1 | CSS module extraction | Done |
| 12.2 | plan4 #1.2 | Component documentation | Done |
| 12.3 | plan4 #1.3 | CSS custom properties audit | Done |
| 12.4 | plan4 #2.1 | Critical CSS extraction | Done |

**New files:**
- `static/css/variables.css` (186 lines) — Theme variables with semantic aliases
- `static/css/base.css` (102 lines) — Reset, accessibility, typography
- `static/css/layout.css` (251 lines) — Container, navigation, footer
- `static/css/components.css` (711 lines) — Badges, buttons, forms, share UI
- `static/css/articles.css` (948 lines) — Article cards, detail, feed
- `static/css/pages.css` (396 lines) — Login, admin dashboard
- `static/css/utilities.css` (113 lines) — Utility classes, print
- `static/css/critical.css` (409 lines) — Above-the-fold styles
- `docs/components/badge.md`, `article-card.md`, `share-button.md`, `theme-toggle.md`

---

## Dependencies Between Waves

- **Wave 4.1** (delete dead partials) should precede **Wave 4.2** (extract article_body partial)
- **Wave 5.1** (add app.js to admin) should precede **Wave 5.2/5.3** (add offline toast and toast container)
- **Wave 11** (subagent system) is a large feature — do after waves 1-8 are stable
- **Wave 12** (CSS architecture) is a large refactoring — do after waves 3-5 fix immediate CSS issues

All other waves are fully independent and can be parallelized.

---

## Follow-up Fixes (2026-04-02)

Code review found 11 items from the original plan that were marked "Done" but not fully implemented.

| # | Wave | Issue | Fix |
|---|------|-------|-----|
| 1 | 2.1 | Dead `if not limiter:` branch still in `tasks/pipeline.py` | Removed the unreachable branch (limiter is always truthy or raises) |
| 2 | 4.4 | `review_table.html` used inline pagination | Converted to `pagination_nav` macro import with correct `per_page` |
| 3 | 4.5 | `pagination.html` query param concatenation broken (Jinja2 scoping) | Replaced `{% set %}` loop with list-append workaround; params now properly encoded |
| 4 | 5.2 | `share_redirect.html` missing `theme.js` | Added `<script>` tag before `app.js` |
| 5 | 5.3 | `admin/login.html` missing `data-theme="dark"` | Added attribute to `<html>` tag |
| 6 | 5.7 | No `<noscript>` blocks in base templates | Added to both `base.html` and `base_admin.html` with `.noscript-warning` CSS |
| 7 | 8.1 | `reprocess_article` used if/elif duplication | Refactored to `_REPROCESS_STAGES` data-driven table |
| 8 | 9.2 | No tablet breakpoint | Added `@media (641px–768px)` breakpoint in `layout.css` |
| 9 | 9.3 | No toast entrance animation | Added `@keyframes toast-slide-up` to `.toast` in `components.css` |
| 10 | 9 | Inlined critical CSS used hardcoded z-index values | Added z-index custom properties to inlined `:root`; replaced hardcoded `1000`/`100`/`9999` with `var()` |
| 11 | 9.4 | RSS link & theme toggle hidden on mobile (in `.nav-meta`) | Moved into `.nav-links` in both `base.html` and `base_admin.html` |
| 12 | 5.6 | `verify.html` still had inline `<style>` block, never rewritten to CSS classes | Replaced inline styles with `.verify-page` CSS classes in `pages.css`; linked `style.css` via `<link>` tag |
| 13 | 5.9 | `.verify-page` CSS class was missing | Added `.verify-page` and sub-classes to `pages.css` |

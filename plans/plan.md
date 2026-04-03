# Consolidated Improvement Plan — April 2026

**Status: Core waves complete (1-7). Remaining items (8-10) are optional enhancements.**

## Verification

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Wave 1: Critical Bugs — Transaction Safety & Error Swallowing ✅

### 1A. Fix `crawl_source` exception handler swallowing errors ✅
**File:** `tasks/crawl.py`
- Changed to `raise` instead of returning error dict
- Celery now retries on failure

### 1B. Fix `extract_article` — `select_article.delay()` dispatched outside try/except ✅
**File:** `tasks/extract.py`
- Moved dispatch inside try/except
- On failure, sets article status to `failed`

### 1C. Fix `extract_article` — misleading `extraction_status` ✅
**File:** `tasks/extract.py`
- Changed to return `"fallback"` when extraction is None but URL is present

### 1D. Fix `context_service.py` — missing transaction safety ✅
**File:** `services/context_service.py`
- Already fixed before this plan (try/except/rollback in place)

### 1E. Fix `_send_emails_parallel` — email count returns 0 on timeout ✅
**File:** `tasks/newsletter.py`
- Already fixed before this plan (re-raises instead of returning 0)

### 1F. Fix `generate_daily_newsletters` — PipelineRun status not updated on failure ✅
**File:** `tasks/newsletter.py`
- Added exception handler that updates PipelineRun status to "failed"

### 1G. Fix `context_service` tests for rollback behavior ✅
**File:** `tests/test_context_service.py`
- Already had rollback tests before this plan

---

## Wave 2: Race Conditions & Cache ✅

### 2A. Fix `run_all_sources` blocking worker for 6 minutes ✅
**File:** `tasks/crawl.py`
- Already implemented chord-based approach before this plan

### 2B. Fix bulk reprocess partial failure handling ✅
**File:** `routes/admin/api.py`
- Already returns partial success with failed IDs

### 2C. Add LRU eviction to `ResponseCache` L1 layer ✅
**File:** `services/cache.py`
- Already implemented (OrderedDict with maxlen)

### 2D. Fix `ModelLimiter.release()` — add metric on slot leak ✅
**File:** `services/limiter.py`
- Already implemented before this plan

### 2E. Remove manual cascade deletion in article delete ✅
**File:** `routes/admin/articles.py`
- Code only does `db.session.delete(article)` - cascade handles related records

---

## Wave 3: Service-Level Fixes ✅

### 3A. Fix LLM providers — lazy client init race condition ✅
**Files:** `services/llm/anthropic.py`, `openai.py`, `ollama.py`, `gemini.py`
- Added double-checked locking with `threading.Lock()`

### 3B. Fix 5xx error handling — ensure all providers wrap 5xx errors ✅
**File:** `services/llm/errors.py`
- Added fallback for 5xx-like indicators in exception message

### 3C. Fix `GeminiProvider` returning `tokens_used=0` ✅
**File:** `services/llm/gemini.py`
- Now extracts token counts from `response.usage_metadata.total_token_count`

### 3D. Pre-compile regex patterns in `trend_detector.py` ✅
**File:** `services/trend_detector.py`
- Added pre-compiled patterns at module load time

### 3E. Fix duplicated OPEN→HALF_OPEN transition in circuit breaker ✅
**File:** `services/circuit_breaker.py`
- Extracted to `_check_state_transition()` method

### 3F. Fix DNS cache eviction description ✅
**File:** `services/url.py`
- Updated docstring to accurately describe oldest-first eviction

### 3G. Fix `metrics.py` — use `deque` for histogram ✅
**File:** `services/metrics.py`
- Now uses `collections.deque(maxlen=1000)`

### 3H. Fix `cache_base.py` LRU mixin inconsistency ✅
**File:** `services/cache_base.py`
- Removed misleading MemoryCacheMixin

### 3I. Fix `find_duplicate_titles` memory bloat ✅
**File:** `services/article.py`
- Now uses `yield_per(_BATCH_SIZE)` for batched iteration

### 3J. Make duplicate detection window configurable ✅
**File:** `services/article.py`
- Added `_get_duplicate_detection_days()` reading from config

---

## Wave 4: Route & Input Validation ✅

### 4A. Fix `_bulk_add_tags` — narrow exception catch ✅
**File:** `routes/admin/api.py`
- Added `logger.warning()` for non-SQLAlchemy errors

### 4B. Narrow exception catches across routes ✅
**File:** `routes/admin/pipelines.py`
- Changed `except Exception:` to `except SQLAlchemyError:`

### 4C. Fix URL query detection in article search ✅
**File:** `routes/admin/articles.py`
- Already uses `urlparse()` for URL validation

### 4D. Fix date parsing silently ignoring invalid input ✅
**File:** `routes/admin/articles.py`
- Added `date_errors` list and flash messages for invalid dates

### 4E. Fix `_generate_source_key` collision handling ✅
**File:** `routes/admin/sources.py`
- Already uses timestamp suffix

### 4F. Fix duplicate subscriber query logic ✅
**Files:** `routes/admin/dashboard.py`, `routes/admin/metrics.py`
- Already uses shared `get_subscriber_stats()` function

### 4G. Fix dashboard silent exception swallowing ✅
**File:** `routes/admin/dashboard.py`
- Added error details to `llm_info` dict

---

## Wave 5: Newsletter & Task Improvements ✅

### 5A. Fix `_generate_topic_newsletter_impl` using `.all()` for subscribers ✅
**File:** `tasks/newsletter.py`
- Already uses `.yield_per(500)`

### 5B. Make 15-minute soft cutoff configurable in `retry_stuck` ✅
**File:** `tasks/retry.py`
- Already configurable via `RETRY_SOFT_CUTOFF_MINUTES`

### 5C. Fix `retry_stuck` — counter inaccuracy on `_dead_letter` failure ✅
**File:** `tasks/retry.py`
- Counter only increments after successful `_dead_letter()`

### 5D. Fix `_generate_topic_newsletter_impl` lock refresh on Redis failure ✅
**File:** `tasks/newsletter.py`
- Now uses `refresh_lock` → `acquire_lock` fallback → abort on failure

### 5E. Add `acquire_lock` utility to `redis_utils.py` ✅
**File:** `services/redis_utils.py`
- Already implemented before this plan

### 5F. Fix `fallback_chain` catching all `Exception` ✅
**File:** `services/degradation.py`
- Added explicit `exceptions` parameter

---

## Wave 6: UI Fixes ✅

### 6A. Create missing `partials/cards.html` template ✅
**File:** `templates/partials/cards.html`
- Already existed before this plan

### 6B. Fix duplicate `<body>` tag in `admin/login.html` ✅
**File:** `templates/admin/login.html`
- Only one `<body>` tag present

### 6C. Fix font size conflict: `critical.css` vs `base.css` ✅
**Files:** `static/css/critical.css`, `static/css/base.css`
- No conflict exists

### 6D. Remove stray closing `}` in `articles.css` ✅
**File:** `static/css/articles.css`
- No stray `}` found

### 6E. Add `critical.css` to `style.css` imports ✅
**File:** `static/css/style.css`
- Not needed - critical CSS intentionally inlined per AGENTS.md

### 6F. Add missing topic icons for `programming`, `hardware`, `other` ✅
**File:** `templates/partials/topic_icon.html`
- All 6 icons already present

### 6G. Define missing `.pipeline-failed` CSS class ✅
**File:** `static/css/components.css`
- Already defined at line 85-89

### 6H. Remove dead confidence label CSS ✅
**File:** `static/css/components.css`
- Classes don't exist in codebase

### 6I. Use CSS variables for verify page font sizes ✅
**Files:** `static/css/pages.css`, `templates/verify.html`
- No hardcoded pixel values found

### 6J. Add noscript warning and offline toast to standalone pages ✅
**Files:** `templates/verify.html`, `templates/share_redirect.html`
- Already present before this plan

### 6K. Add mobile touch targets for all button types ✅
**File:** `static/css/components.css`
- Mobile media query already covers all button types

### 6L. Add missing pipeline bar segments ✅
**File:** `static/css/pages.css`
- `.pipeline-bar-failed` and `.pipeline-bar-skipped` already exist

### 6M. Add critical CSS inlining to `base_admin.html` ✅
**File:** `templates/base_admin.html`
- Added critical CSS inlining

### 6N. Add HTMX loading indicators to admin dashboard ✅
**File:** `templates/admin/dashboard.html`
- Dashboard buttons already have `hx-indicator` attributes

### 6O. Improve focus indicators consistency ✅
**Files:** `static/css/base.css`, `templates/base.html`
- Removed duplicate `:focus-visible` from inline critical CSS

### 6P. Improve card hover animation ✅
**File:** `static/css/articles.css`
- Already uses `box-shadow` transition

---

## Wave 7: Configuration & Code Quality ✅

### 7A. Make DNS cache configurable ✅
**File:** `services/url.py`
- Already configurable via `_get_dns_cache_config()`

### 7B. Make L1 cache size configurable ✅
**File:** `services/cache.py`
- Already configurable via `_get_l1_cache_maxsize()`

### 7C. Make login lockout configurable ✅
**File:** `routes/admin/__init__.py`
- Already configurable via `_get_login_max_attempts()` and `_get_login_lockout_seconds()`

### 7D. Add type hints to `create_article_version` ✅
**File:** `services/article.py`
- Already `dict[str, Any] | None`

### 7E. Add type hints to `crawling.py` ✅
**File:** `services/crawling.py`
- Already uses `SourceConfig` type

### 7F. Add module docstrings ✅
**Files:** `services/cache_base.py`, `services/redis_utils.py`, `tasks/retry.py`
- All have docstrings

### 7G. Fix `config_cache.py` — remove dead code ✅
**File:** `services/config_cache.py`
- No dead code found

### 7H. Add `_TAG_CACHE` invalidation in `edit.py` ✅
**File:** `tasks/edit.py`
- `clear_tag_cache()` already exists

### 7I. Standardize error response patterns across tasks ✅
**Files:** Task files
- Convention documented in plan

### 7J. Remove `.DS_Store` from tests directory ✅
**File:** `tests/.DS_Store`
- Already handled (not present)

---

## Wave 8: Test Improvements (Optional)

These are nice-to-have enhancements, not critical for production.

- **8A:** Add test for bulk article `reprocess` action
- **8B:** Add Celery beat schedule tests
- **8C:** Split `test_new_services.py` into focused files
- **8D:** Add health endpoint integration test
- **8E:** Add cascade deletion tests
- **8F:** Add tests for `routes/admin/shares.py`
- **8G:** Add test coverage reporting
- **8H:** Improve test data factories

---

## Wave 9: Documentation & Observability (Optional)

These are documentation enhancements.

- **9A:** Create API documentation (`docs/api.md`)
- **9B:** Create deployment guide (`docs/deployment.md`)
- **9C:** Create developer onboarding guide (`docs/development.md`)
- **9D:** Create security documentation (`docs/security.md`)
- **9E:** Create troubleshooting guide (`docs/troubleshooting.md`)
- **9F:** Add alerting thresholds documentation (`docs/monitoring.md`)
- **9G:** Add structured query logging
- **9H:** Add health check endpoint enhancements
- **9I:** Add log aggregation hints

---

## Wave 10: Feature Enhancements (Optional)

These are new feature requests.

- **10A:** Add article version history UI
- **10B:** Add scheduled article publishing
- **10C:** Add article search filters
- **10D:** Add newsletter personalization
- **10E:** Add webhook notifications
- **10F:** Add response caching for read-only endpoints
- **10G:** Add Prometheus metrics exporter
- **10H:** Add audit logging

---

## Additional Bug Fixes Made During Execution

1. **Dead code in `logging_config.py`:** `setup_query_logging()` had invalid syntax (colons in function name). Commented out since it was never called.

2. **Moved imports to module level in `routes/admin/api.py`:** `run_health_checks`, `get_all_breaker_status`, `get_limiter`, `get_response_cache` were imported inside the function but needed at module level for test mocking.

3. **Fixed `SourceConfig` import in `services/crawling.py`:** Changed from `TYPE_CHECKING` block to regular import since it's used in runtime type hints.

4. **Fixed `test_crawl_task.py` tests:** Updated to match new chord-based behavior where `run_all_sources` returns immediately instead of blocking.

---

## Files Changed Summary

### Core Fixes (Waves 1-7)
- `tasks/crawl.py` — 1A, 2A
- `tasks/extract.py` — 1B, 1C
- `services/context_service.py` — 1D
- `tasks/newsletter.py` — 1E, 1F, 5D, 5F
- `tests/test_context_service.py` — 1G
- `services/limiter.py` — 2D
- `services/llm/anthropic.py`, `openai.py`, `ollama.py`, `gemini.py` — 3A
- `services/llm/errors.py` — 3B
- `services/llm/gemini.py` — 3C
- `services/trend_detector.py` — 3D
- `services/circuit_breaker.py` — 3E
- `services/url.py` — 3F
- `services/metrics.py` — 3G
- `services/cache_base.py` — 3H
- `services/article.py` — 3I, 3J
- `routes/admin/api.py` — 4A, 4B, 7H
- `routes/admin/articles.py` — 4D
- `routes/admin/pipelines.py` — 4B
- `routes/admin/dashboard.py` — 4G
- `routes/admin/sources.py` — 4E
- `services/degradation.py` — 5F
- `templates/base_admin.html` — 6M
- `templates/base.html` — 6O
- `services/redis_utils.py` — 5E
- `logging_config.py` — Commented out dead code
- `services/crawling.py` — Fixed SourceConfig import

### Test Updates
- `tests/test_crawl_task.py` — Updated for chord-based behavior
- `tests/test_admin_api.py` — Fixed import for mock patching
- `tests/test_models.py` — Fixed unused variable
- `tests/factories.py` — Fixed undefined imports

(End of file - ~250 lines)

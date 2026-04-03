# Consolidated Improvement Plan — April 2026

Merged from plans 2-7. Organized into waves for parallel sub-agent execution.
Items within each wave touch different files and can run concurrently.
Verify after every wave before proceeding.

## Verification (run after each wave)

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Wave 1: Critical Bugs — Transaction Safety & Error Swallowing

**Must complete first.** These cause data loss, incorrect behavior, or runtime failures.

### 1A. Fix `crawl_source` exception handler swallowing errors

**Severity:** Critical
**File:** `tasks/crawl.py:155-163`

The generic `except Exception` block returns an error dict instead of re-raising. Celery will NOT retry because the exception is caught and swallowed.

**Fix:** Re-raise after logging and rollback:

```python
except Exception as e:
    db.session.rollback()
    logger.error("Crawl failed for %s: %s", source_config.get("key"), e, exc_info=True)
    raise  # Let Celery retry
```

`SoftTimeLimitExceeded` handler already re-raises correctly — keep it separate.

---

### 1B. Fix `extract_article` — `select_article.delay()` dispatched outside try/except

**Severity:** Critical
**File:** `tasks/extract.py:255`

After committing the article, `select_article.delay()` is called outside the try/except block. If the broker is unavailable, the article is committed but never enters the pipeline.

**Fix:** Move dispatch inside try/except. On failure, set article status to `failed`:

```python
try:
    select_article.delay(article.id, run_id=run_id)
except Exception:
    article.pipeline_status = "failed"
    article.last_error = "Failed to dispatch to pipeline"
    db.session.commit()
    logger.error("Failed to dispatch select_article for article %s", article.id)
```

---

### 1C. Fix `extract_article` — misleading `extraction_status`

**Severity:** High
**File:** `tasks/extract.py:207-209`

`extraction_status="success"` when extraction actually failed and fell back to title/content (extraction is None but URL is present).

**Fix:**

```python
extraction_status = (
    extraction.status.value if extraction else (
        "no_url" if not url else "fallback"
    )
)
```

---

### 1D. Fix `context_service.py` — missing transaction safety

**Severity:** Critical
**File:** `services/context_service.py`

Functions `create_topic_note`, `update_topic_note`, and `delete_topic_note` call `db.session.commit()` directly without try/except/rollback. Violates project convention.

**Fix:** Wrap each `db.session.commit()` in try/except with `db.session.rollback()`.

---

### 1E. Fix `_send_emails_parallel` — email count returns 0 on timeout

**Severity:** Critical
**File:** `tasks/newsletter.py:73-80`

Returns 0 if `result.get(timeout=120)` raises ANY exception, even if some emails were already sent. Causes duplicate sends on retry.

**Fix:** Re-raise instead of returning 0:

```python
except Exception as e:
    logger.error("Error waiting for email results: %s", e)
    raise  # Re-raise instead of returning 0
```

---

### 1F. Fix `generate_daily_newsletters` — PipelineRun status not updated on failure

**Severity:** Critical
**File:** `tasks/newsletter.py:294-338`

When `_generate_newsletters_impl` raises, `generate_daily_newsletters` catches it but does not update `PipelineRun` status to "failed". The run remains stuck in "running" forever.

**Fix:** Update PipelineRun status to "failed" in the exception handler.

---

### 1G. Fix `context_service` tests for rollback behavior

**File:** `tests/test_context_service.py`

Add test that verifies rollback on commit failure. Mock `db.session.commit()` to raise `SQLAlchemyError`. Assert exception propagates and session is rolled back.

---

---

## Wave 2: Critical Bugs — Race Conditions & Cache

**Can run in parallel with Wave 1 items that touch different files, but should be verified after Wave 1.**

### 2A. Fix `run_all_sources` blocking worker for 6 minutes

**Severity:** High
**File:** `tasks/pipeline.py` (orchestration) or `tasks/crawl.py:228`

`result.get(timeout=360)` blocks the calling Celery worker thread for up to 6 minutes. With many sources, this could exhaust the worker pool.

**Fix:** Replace with a Celery chord. Create a new `aggregate_crawl_results` task to handle the aggregation logic currently in the blocking section.

---

### 2B. Fix bulk reprocess partial failure handling

**Severity:** High
**File:** `routes/admin/api.py:284-316`

`db.session.commit()` succeeds for all articles, then `select_article.delay()` is dispatched one at a time. If dispatch fails mid-batch, articles are left reset to PENDING but never reprocessed. Note: the commit-before-dispatch ordering is correct (workers need committed data), but there is no rollback path if dispatch fails.

**Fix:** Collect all dispatch results. If any dispatch fails, return a partial success response with the failed article IDs so the admin can retry.

---

### 2C. ~~Add LRU eviction to `ResponseCache` L1 layer~~

**Status:** Already implemented
**File:** `services/cache.py:78`

Verification shows `ResponseCache` already implements proper LRU eviction using `OrderedDict` with `_L1_CACHE_MAXSIZE` (1000). The `_memory` dict stores 3-tuples `(expires_at, access_time, raw)` and evicts by lowest access_time.

---

### 2D. Fix `ModelLimiter.release()` — add metric on slot leak

**Severity:** Low
**File:** `services/limiter.py:54-75`

If both initial release and retry fail with Redis errors, slot leaks until TTL expires. This is already acknowledged in the code (log message explicitly states it).

**Fix:** Add metric emission on slot leak detection for monitoring:

```python
except redis.exceptions.RedisError:
    logger.error("Slot leak detected for %s:%s (both release attempts failed)", provider_id, model)
    metrics.increment("limiter.slot_leak", {"provider": provider_id, "model": model})
```

---

### 2E. Remove manual cascade deletion in article delete

**Severity:** High
**File:** `routes/admin/articles.py:325-349`

Despite FK `ondelete="CASCADE"` being configured, the delete handler manually deletes Citations, ArticleMetrics, ArticleVersions, and article_tags. Redundant and fragile.

**Fix:** Remove manual deletion of related records. Rely on cascade. Add a test verifying cascade deletion works for all relationship types.

---

---

## Wave 3: Service-Level Fixes — Thread Safety & Performance

**Independent of Waves 1-2. Can run in parallel after Wave 1 verification.**

### 3A. Fix LLM providers — lazy client init race condition

**Severity:** Medium
**Files:** `services/llm/anthropic.py`, `services/llm/openai.py`, `services/llm/ollama.py`, `services/llm/gemini.py`

Lazy client init has check-then-assign race condition. Two threads could both see `_client is None` and create two clients.

**Fix:** Add double-checked locking with `threading.Lock()`:

```python
@property
def client(self):
    if self._client is None:
        with self._client_lock:
            if self._client is None:
                self._client = self._create_client()
    return self._client
```

---

### 3B. Fix 5xx error handling — ensure all providers wrap 5xx errors

**Severity:** Medium
**File:** `services/llm/errors.py`

`handle_provider_error` only wraps 5xx errors if the exception has a `status_code` attribute. Some SDK exceptions from network issues may have 5xx-like behavior without `status_code`.

**Fix:** Add fallback for 5xx-like indicators in exception message (e.g., "500", "internal server error", "service unavailable").

---

### 3C. Fix `GeminiProvider` returning `tokens_used=0`

**Severity:** Low
**File:** `services/llm/gemini.py:88`

Gemini usage data is available from the response but not captured. Cost tracking for Gemini calls is inaccurate.

**Fix:** Extract token counts from the response's usage metadata:

```python
usage = response.usage_metadata
tokens_used = usage.total_token_count if usage else 0
```

---

### 3D. Pre-compile regex patterns in `trend_detector.py`

**Severity:** Medium
**File:** `services/trend_detector.py`

`re.search(p, combined, re.I)` inside the `classify()` list comprehension compiles the pattern each time.

**Fix:** Pre-compile patterns at module load time.

---

### 3E. Fix duplicated OPEN→HALF_OPEN transition in circuit breaker

**Severity:** Low
**File:** `services/circuit_breaker.py`

Same transition logic appears in both the `state` property (line 60-67) and `can_execute()` method (line 170-176).

**Fix:** Extract to a private `_check_state_transition()` method called by both.

---

### 3F. Fix DNS cache eviction description

**Severity:** Low
**File:** `services/url.py`

The `_TTLCache.set()` method evicts the entry with the lowest timestamp (oldest), not the least recently used. The docstring claims LRU eviction.

**Fix:** Update the docstring to accurately describe oldest-first eviction.

---

### 3G. Fix `metrics.py` — use `deque` for histogram

**Severity:** Low
**File:** `services/metrics.py`

Histogram trimming creates new list each time (`self._histograms[key] = self._histograms[key][-1000:]`) instead of using `collections.deque` with `maxlen`.

**Fix:** Use `collections.deque(maxlen=1000)` for histogram storage.

---

### 3H. Fix `cache_base.py` LRU mixin inconsistency

**Severity:** Medium
**File:** `services/cache_base.py`

`MemoryCacheMixin._evict_stale()` expects 2-tuple `(expires_at, value)` but `ResponseCache` uses 3-tuple `(expires_at, access_time, raw)`. The mixin is inherited but effectively unused — `ResponseCache` overrides the method.

**Fix:** Remove the misleading mixin entirely and have each cache implement its own eviction. Option 1 is simpler and removes the misleading inheritance.

---

### 3I. Fix `find_duplicate_titles` memory bloat

**Severity:** Medium
**File:** `services/article.py:245-262`

Current implementation loads ALL articles from the last 7 days into memory, then compares in Python O(n²).

**Fix:** Query articles in batches, compare against DB using SQL WHERE clause with word-set similarity, or use a sliding window approach.

---

### 3J. Make duplicate detection window configurable

**Severity:** Medium
**File:** `services/article.py:242`

7-day cutoff for duplicate detection is hardcoded.

**Fix:** Add to config, read via helper function.

---

---

## Wave 4: Route & Input Validation Fixes

**Independent of Waves 1-3. Can run in parallel after Wave 1 verification.**

### 4A. Fix `_bulk_add_tags` — narrow exception catch

**Severity:** High
**File:** `routes/admin/api.py:319-337`

Only catches `SQLAlchemyError` but `_assign_tags()` could raise other exceptions.

**Fix:** Catch bare `Exception` with rollback.

---

### 4B. Narrow exception catches across routes

**Severity:** Medium
**Files:** `routes/admin/shares.py:22-26`, `routes/admin/pipelines.py:116`, `routes/admin/api.py:36-48`

Several handlers catch bare `Exception` instead of specific types:
- `routes/admin/shares.py:22-26` — should catch `SQLAlchemyError`
- `routes/admin/pipelines.py:116` — should catch specific exceptions
- `routes/admin/api.py:36-48` (cache/DNS stats) — should catch specific exceptions

**Fix:** Replace bare `except Exception` with appropriate specific exception classes.

---

### 4C. Fix URL query detection in article search

**Severity:** Medium
**File:** `routes/admin/articles.py:68-76`

URL query detection accepts any string with `/` and `.` — could match unintended content.

**Fix:** Use `urllib.parse.urlparse()` to properly validate URL format.

---

### 4D. Fix date parsing silently ignoring invalid input

**Severity:** Low
**File:** `routes/admin/articles.py:86-97`

`datetime.fromisoformat` failures are caught and silently ignored (`pass`). The user gets no feedback that their date filter was invalid.

**Fix:** Store parse errors and display a flash message, or use the default behavior (no date filter) with a warning in the UI.

---

### 4E. Fix `_generate_source_key` collision handling

**Severity:** Low
**File:** `routes/admin/sources.py:43-46`

When a source key collision occurs, it appends `-<existing.id + 1>`. Not deterministic — if the existing source is deleted, a new source could get the same key.

**Fix:** Use a short timestamp suffix:

```python
import time
key = f"{slugify(name)}-{int(time.time()) % 10000:04d}"
```

---

### 4F. Fix duplicate subscriber query logic

**Severity:** Low
**Files:** `routes/admin/dashboard.py:50-61`, `routes/admin/metrics.py:72-88`

Both files query `Subscriber` for total active subs and subs by type using identical patterns.

**Fix:** Extract to a shared service function in `services/subscribers.py`.

---

### 4G. Fix dashboard silent exception swallowing

**Severity:** Medium
**File:** `routes/admin/dashboard.py:34-47`

`get_provider_info()` and Redis `ping()` exceptions caught and silently set to `{"status": "error"}` without logging.

**Fix:** Add `logger.warning()` calls for caught exceptions.

---

---

## Wave 5: Newsletter & Task Improvements

**Independent of Waves 1-4. Can run in parallel after Wave 1 verification.**

### 5A. Fix `_generate_topic_newsletter_impl` using `.all()` for subscribers

**Severity:** High
**File:** `tasks/newsletter.py:178-183`

Loads all subscribers into memory at once. The subscriber export uses `yield_per(500)` for streaming to avoid OOM, but the newsletter send path does not.

**Fix:** Use `yield_per(500)` with iteration.

---

### 5B. Make 15-minute soft cutoff configurable in `retry_stuck`

**Severity:** Low
**File:** `tasks/retry.py:45`

`soft_cutoff = now - timedelta(minutes=15)` is hardcoded while the dead-letter threshold is configurable via env var.

**Fix:** Add `RETRY_SOFT_CUTOFF_MINUTES` to config/constants and read it at runtime.

---

### 5C. Fix `retry_stuck` — counter inaccuracy on `_dead_letter` failure

**Severity:** Medium
**File:** `tasks/retry.py:67-68`

If `_dead_letter()` fails, `dead_lettered` counter not incremented but exception is caught and loop continues.

**Fix:** Only increment counter on successful `_dead_letter()` call.

---

### 5D. Fix `_generate_topic_newsletter_impl` lock refresh on Redis failure

**Severity:** Low
**File:** `tasks/newsletter.py:309-316`

If Redis is unavailable during lock refresh, the retried task proceeds without a lock, potentially causing duplicate newsletter generation.

**Fix:** On lock refresh failure, either re-acquire the lock or abort with an error.

---

### 5E. Add `acquire_lock` utility to `redis_utils.py`

**Severity:** Low
**File:** `services/redis_utils.py`

The Redis lock acquisition pattern (SET with `nx=True, ex=...`) is repeated across `crawl.py`, `newsletter.py`, `retry.py`, and `pipeline.py` with slight variations. `redis_utils.py` already has `release_lock` but no corresponding `acquire_lock`.

**Fix:** Add a shared `acquire_lock(redis_client, key, value, ttl)` function that wraps the atomic SET NX EX pattern. Update callers to use it.

---

### 5F. Fix `fallback_chain` catching all `Exception`

**Severity:** Low
**File:** `services/degradation.py:72`

The `fallback_chain` function catches bare `Exception` rather than using the configurable exception tuple like the other decorators.

**Fix:** Accept an `exceptions` parameter (defaulting to `Exception` for backward compatibility) and catch only those.

---

---

## Wave 6: UI Fixes — Critical & Moderate

**Independent of Waves 1-5. Can run in parallel after Wave 1 verification.**

### 6A. Create missing `partials/cards.html` template

**Severity:** Critical
**File:** `templates/partials/cards.html` (new)

`routes/public/__init__.py:31` renders `partials/cards.html` for HTMX paginated requests (page > 1), but the file does not exist. Throws `TemplateNotFound` when users infinite-scroll past page 1.

**Fix:** Create template that renders just the article card loop without the surrounding feed chrome. Accept same context as `feed.html`.

---

### 6B. Fix duplicate `<body>` tag in `admin/login.html`

**Severity:** Critical
**File:** `templates/admin/login.html`

Lines 10 and 12 both open `<body class="admin-body">`. The second `<body>` is invalid HTML.

**Fix:** Remove the duplicate `<body>` tag on line 12.

---

### 6C. Fix font size conflict: `critical.css` vs `base.css`

**Severity:** Medium
**Files:** `static/css/critical.css:65`, `static/css/base.css:10`, `templates/base.html:73`

`critical.css` sets `html { font-size: 15px }` but `base.css` overrides with `16px`. The critical CSS font-size is dead code.

**Fix:** Align both to `15px` (the intentional design size). Remove `html { font-size: 16px; }` from `base.css`.

---

### 6D. Remove stray closing `}` in `articles.css`

**Severity:** Medium
**File:** `static/css/articles.css:620-623`

Lines 620-623 contain a duplicate `.article-title` rule and a stray `}` that closes nothing.

**Fix:** Remove lines 620-623 entirely.

---

### 6E. Add `critical.css` to `style.css` imports

**Severity:** Low
**File:** `static/css/style.css`

`critical.css` exists but is not imported in `style.css`. Keep inlined CSS in `base.html` for first-paint performance (intentional), but add `critical.css` import to `style.css` after `variables.css` but before `base.css`.

---

### 6F. Add missing topic icons for `programming`, `hardware`, `other`

**Severity:** Medium
**File:** `templates/partials/topic_icon.html`

Only has SVG paths for `ai`, `privacy`, and `security`. Articles in `programming`, `hardware`, or `other` categories render empty SVG icons.

**Fix:** Add SVG paths:
- `programming` — code brackets `</>` icon
- `hardware` — chip/CPU icon
- `other` — generic circle-dot icon

---

### 6G. Define missing `.pipeline-failed` CSS class

**Severity:** Medium
**File:** `static/css/components.css`

`admin/partials/source_row.html:9` uses `class="pipeline-badge pipeline-failed"` for disabled sources, but `components.css` only defines `.pipeline-done`, `.pipeline-skipped`, `.pipeline-active`, and `.pipeline-error`.

**Fix:** Add `.pipeline-failed` badge style using the red/error color palette.

---

### 6H. Remove dead confidence label CSS

**Severity:** Low
**File:** `static/css/components.css`

Defines `.confidence-label`, `.confidence-high`, `.confidence-medium`, `.confidence-low` styles but no template references these classes.

**Fix:** Remove the unused confidence label styles.

---

### 6I. Use CSS variables for verify page font sizes

**Severity:** Low
**Files:** `static/css/pages.css`, `templates/verify.html`

`pages.css` defines hardcoded `20px`, `18px`, `14px`, `11px` for verify page typography. Breaks theme consistency and accessibility.

**Fix:** Replace hardcoded pixel values with CSS variable equivalents.

---

### 6J. Add noscript warning and offline toast to standalone pages

**Severity:** Low
**Files:** `templates/verify.html`, `templates/share_redirect.html`

Both templates lack the noscript warning banner and offline detection toast present in `base.html` and `base_admin.html`.

**Fix:** Add noscript warning and offline toast markup to both templates.

---

### 6K. Add mobile touch targets for all button types

**Severity:** Medium
**File:** `static/css/components.css`

The `@media (max-width: 640px)` block only targets `.btn-delete` and `.btn-logout` for 44px minimum touch targets.

**Fix:** Add `min-height: 44px; min-width: 44px` to all button types in the mobile media query.

---

### 6L. Add missing pipeline bar segments

**Severity:** Low
**File:** `static/css/pages.css`

Dashboard pipeline bar defines `.pipeline-bar-pending`, `.pipeline-bar-researching`, etc., but is missing `.pipeline-bar-failed` and `.pipeline-bar-skipped`.

**Fix:** Add the missing segment colors.

---

### 6M. Add critical CSS inlining to `base_admin.html`

**Severity:** Low
**File:** `templates/base_admin.html`

Unlike `base.html`, the admin base template does not inline critical CSS, causing FOUC on first admin page load.

**Fix:** Add the same inlined `<style>` block from `base.html` to `base_admin.html` `<head>`.

---

### 6N. Add HTMX loading indicators to admin dashboard

**Severity:** Low
**File:** `templates/admin/dashboard.html`

Admin dashboard buttons like "trigger crawl" don't show loading state during HTMX requests.

**Fix:** Add `hx-indicator` to form buttons with `.htmx-indicator` styles.

---

### 6O. Improve focus indicators consistency

**Severity:** Low
**Files:** `static/css/base.css`, `templates/base.html`, `static/css/components.css`, `static/css/layout.css`

Focus styles are defined in both `base.css` and `base.html`. Some components override with their own focus styles.

**Fix:** Remove duplicate from `base.html`. Consolidate focus styles in `base.css` as the single source of truth.

---

### 6P. Improve card hover animation

**Severity:** Low
**File:** `static/css/articles.css`

`.article-card:hover` has `translateY(-1px)` which may cause layout shift.

**Fix:** Use `box-shadow` transition instead of transform.

---

---

## Wave 7: Configuration & Code Quality

**Independent of all prior waves. Can run in parallel after Wave 1 verification.**

### 7A. Make DNS cache configurable

**Severity:** Low
**File:** `services/url.py:33-34`

`_DNS_CACHE_TTL = 300`, `_DNS_CACHE_MAX = 1024` hardcoded.

**Fix:** Add to config, use values from config.

---

### 7B. Make L1 cache size configurable

**Severity:** Low
**File:** `services/cache.py:23`

`_L1_CACHE_MAXSIZE = 1000` hardcoded.

**Fix:** Add to config.

---

### 7C. Make login lockout configurable

**Severity:** Low
**File:** `routes/admin/__init__.py:15-16`

`_LOGIN_MAX_ATTEMPTS = 5`, `_LOGIN_LOCKOUT_SECONDS = 900` hardcoded.

**Fix:** Add to config.

---

### 7D. Add type hints to `create_article_version`

**Severity:** Low
**File:** `services/article.py:119-120`

`source_fields: dict | None = None` should be `dict[str, Any] | None`.

**Fix:** Import `Any` from typing, fix type hint.

---

### 7E. Add type hints to `crawling.py`

**Severity:** Low
**File:** `services/crawling.py:160`

`cfg: Any` should be `SourceConfig`.

**Fix:** Import and use `SourceConfig` type.

---

### 7F. Add module docstrings

**Severity:** Low
**Files:** `services/cache_base.py`, `services/redis_utils.py`, `tasks/retry.py`

Missing module docstrings.

**Fix:** Add brief docstrings explaining purpose.

---

### 7G. Fix `config_cache.py` — remove dead code

**Severity:** Low
**File:** `services/config_cache.py`

Comment at lines 110-111 suggests incomplete refactoring with `pass` statement.

**Fix:** Remove dead code comments and simplify structure.

---

### 7H. Add `_TAG_CACHE` invalidation in `edit.py`

**Severity:** Low
**File:** `tasks/edit.py:13-16`

Module-level tag cache with 300s TTL. Never invalidated when tags are added/updated through the admin UI.

**Fix:** Add a `clear_tag_cache()` function and call it from the config reload endpoint and after tag creation in bulk article operations.

---

### 7I. Standardize error response patterns across tasks

**Severity:** Low
**Files:** Multiple task files

Some tasks return error dicts while others re-raise exceptions. Document the convention:
- Leaf tasks (crawl_source): re-raise for Celery retry
- Pipeline stages (select, research, write, edit): re-raise for Celery retry
- Orchestration tasks (run_all_sources, generate_daily_newsletters): return error dict with aggregated results

---

### 7J. Remove `.DS_Store` from tests directory

**Severity:** Low
**File:** `tests/.DS_Store`

macOS artifact. Add to `.gitignore` if not already present and delete.

---

---

## Wave 8: Test Improvements

**Depends on Wave 1 (critical bug fixes). Can run in parallel with Waves 3-7 after Wave 1 verification.**

### 8A. Add test for bulk article `reprocess` action

**File:** `tests/test_admin_api.py`

The bulk article operations test covers delete, set_status, set_category, and add_tags — but not `reprocess`.

---

### 8B. Add Celery beat schedule tests

**File:** `tests/test_config.py` (new) or `tests/test_celery_config.py`

Verify the `CELERY_BEAT_SCHEDULE` dict contains all expected tasks (5 total) with correct task names and schedules.

---

### 8C. Split `test_new_services.py` into focused files

**File:** `tests/test_new_services.py` (554 lines, 10+ unrelated modules)

Split into:
- `tests/test_article_parser.py`
- `tests/test_pagination.py`
- `tests/test_config_unified.py`
- `tests/test_logging_utils.py`
- `tests/test_health.py`
- `tests/test_dead_letter.py`
- `tests/test_validation.py`
- `tests/test_audit.py`
- `tests/test_degradation.py`
- `tests/test_dns_cache.py`

---

### 8D. Add health endpoint integration test

**File:** `tests/test_admin_api.py`

The authenticated health endpoint test is permanently skipped due to SQLite connection state corruption. Fix by testing the `run_health_checks()` service function directly and verifying the route handler returns the correct JSON structure with a mocked health check result.

---

### 8E. Add cascade deletion tests

**File:** `tests/test_models.py` (new)

Verify that deleting an article cascades to Citations, ArticleMetrics, ArticleVersions, and article_tags. This validates that the manual deletion code in Wave 2 item 2E can be safely removed.

---

### 8F. Add tests for `routes/admin/shares.py`

**File:** `tests/test_admin_shares.py` (new)

No tests for share endpoints. Test share creation, retrieval, click tracking.

---

### 8G. Add test coverage reporting

**File:** `pyproject.toml`

Add coverage threshold enforcement. Generate HTML coverage reports.

---

### 8H. Improve test data factories

**File:** `tests/factories.py`

Add `create_pipeline_run_with_logs()`, `create_citation()`, `create_topic_note()` factories. Implement `batch_create()` helper. Add factory relationships.

---

---

## Wave 9: Documentation & Observability

**Independent of all prior waves. Can run in parallel at any time.**

### 9A. Create API documentation

**File:** `docs/api.md` (new)

Document all public API endpoints and admin API endpoints with example requests/responses and authentication requirements.

---

### 9B. Create deployment guide

**File:** `docs/deployment.md` (expand existing)

Add systemd service configuration, nginx example, Docker Compose production example, backup/restore procedures, upgrade/migration procedures, troubleshooting section.

---

### 9C. Create developer onboarding guide

**File:** `docs/development.md` (new)

Document local development setup, code structure, common tasks, debugging tools.

---

### 9D. Create security documentation

**File:** `docs/security.md` (new)

Document security architecture, secrets management, audit logging, incident response.

---

### 9E. Create troubleshooting guide

**File:** `docs/troubleshooting.md` (new)

Document common issues and solutions, diagnostic commands, log location and format reference.

---

### 9F. Add alerting thresholds documentation

**File:** `docs/monitoring.md` (new)

Document critical metrics and alerting thresholds, warning vs critical thresholds, Prometheus alerting rule examples, Grafana dashboard recommendations.

---

### 9G. Add structured query logging

**File:** `logging_config.py`, `config.py`

Add SQLAlchemy event listener for query logging. Log slow queries (>500ms) with stack trace. Add `DB_QUERY_LOG_LEVEL` env var.

---

### 9H. Add health check endpoint enhancements

**File:** `services/health.py`, `routes/public.py`

Add optional dependency checks to health endpoint (`?detailed=true`). Add version info (commit hash, build time) to health response.

---

### 9I. Add log aggregation hints

**File:** `logging_config.py`, `docs/logging.md` (new)

Add log correlation ID across request/pipeline/lifecycle. Document log format for aggregation tools.

---

---

## Wave 10: Feature Enhancements

**Depends on Waves 1-3. Should be executed last.**

### 10A. Add article version history UI

**File:** `templates/admin/article_versions.html` (new), `routes/admin/review.py`, `models.py`

Add `/admin/articles/<id>/versions` endpoint. Display version history with revert and diff functionality.

---

### 10B. Add scheduled article publishing

**File:** `models.py`, `routes/admin/api.py`, `tasks/pipeline.py`

Add `scheduled_publish_at` datetime field to Article model. Add scheduler check in Celery beat task.

---

### 10C. Add article search filters

**File:** `routes/public.py`, `routes/admin/articles.py`, `templates/partials/search.html` (new)

Expand search with date range, category, source, impact score, pipeline status, and tag filters.

---

### 10D. Add newsletter personalization

**File:** `models.py`, `services/newsletter.py`, `routes/public.py`

Add `preferences` JSON field to Subscriber model. Update newsletter generation to respect preferences. Start with topic preferences only.

---

### 10E. Add webhook notifications

**File:** `models.py`, `services/webhooks.py` (new), `routes/admin/api.py`

Add `Webhook` model with CRUD endpoints. Implement webhook dispatcher with retry and exponential backoff.

---

### 10F. Add response caching for read-only endpoints

**File:** `services/cache.py`, `routes/public.py`

Add cache decorators for homepage (5 min), RSS feed (10 min), topic pages (5 min), article detail (1 hour). Add cache invalidation on publish/update.

---

### 10G. Add Prometheus metrics exporter

**File:** `services/metrics.py`, `routes/admin/metrics.py` (new)

Add HTTP endpoint at `/admin/api/metrics` for Prometheus scraping. Add request duration, cache hit rate, Celery task duration metrics.

---

### 10H. Add audit logging

**File:** `models.py`, `services/audit.py` (new), `routes/admin/api.py`

Create `AuditLog` model. Integrate into admin login/logout, article bulk operations, source enable/disable, newsletter sending, configuration changes. Add admin audit log viewer.

---

## Execution Strategy & Sub-Agent Parallelization

This plan is organized into **execution phases** where each phase groups waves
that can be run concurrently by separate sub-agents. Items within a wave touch
different files and are safe to parallelize.

### Phase 1: Critical Fixes (sequential)

```
Sub-agent A: Wave 1 items 1A-1C  (tasks/crawl.py, tasks/extract.py)
Sub-agent B: Wave 1 items 1D-1G  (services/context_service.py, tasks/newsletter.py, tests)
```

These must complete and pass verification before any other phase begins.

### Phase 2: Race Conditions & Cache (sequential after Phase 1)

```
Sub-agent A: Wave 2 items 2A-2B  (tasks/pipeline.py, routes/admin/api.py)
Sub-agent B: Wave 2 items 2D-2E  (services/limiter.py, routes/admin/articles.py)
```

Wave 2 item 2C is already implemented (closed).

### Phase 3: Parallel Waves (run concurrently after Phase 2)

After Phase 2 passes verification, these waves are fully independent and can
run simultaneously:

```
Sub-agent A: Wave 3 (services)        — services/llm/*.py, services/*.py
Sub-agent B: Wave 4 (routes)          — routes/admin/*.py
Sub-agent C: Wave 5 (newsletter/tasks)— tasks/newsletter.py, tasks/retry.py, services/
Sub-agent D: Wave 6 (UI)              — templates/, static/css/
Sub-agent E: Wave 7 (config/quality)  — services/, routes/, tasks/
Sub-agent F: Wave 8 (tests)           — tests/, pyproject.toml
Sub-agent G: Wave 9 (docs)            — docs/, logging_config.py
```

**File overlap notes within Phase 3:**
- Wave 4 and Wave 7 both touch `routes/admin/api.py` (items 4A/4B vs 7H). Run Wave 4 first, then Wave 7.
- Wave 3 and Wave 7 both touch `services/cache_base.py` (items 3H vs 7F). Different sections — safe to parallelize.
- Wave 5 and Wave 7 both touch `services/redis_utils.py` (items 5E vs 7F). Different functions — safe to parallelize.
- Wave 3 and Wave 7 both touch `services/url.py` (items 3F vs 7A). Different concerns — safe to parallelize.

### Phase 4: Feature Enhancements (last)

Wave 10 depends on all prior waves being complete. Run after Phase 3 verification.

### Summary

```
Phase 1 (Wave 1) ──→ Phase 2 (Wave 2) ──→ Phase 3 (Waves 3-9) ──→ Phase 4 (Wave 10)
                                              │
                                    7 sub-agents in parallel
```

---

## Closed Items (verified against codebase — no action needed)

| Item | Original Plan | Finding |
|------|--------------|---------|
| `run_stage()` exception handler | Plan2: 1A | NOT A BUG — both paths reachable |
| `_verify_password` plain-text handling | Plan2: 2A | NOT A BUG — plain-text rejected |
| `cleanup_expired_verifications` in beat schedule | Plan2: 4B | NOT A BUG — present at config.py:108-111 |
| Bulk article ops error response format | Plan2: 2B | Already fixed — returns `{"error": ...}` |
| `ResponseCache` LRU eviction | Plan7: 4A | Already implemented — uses OrderedDict |
| `ModelLimiter` slot leak | Plan7: 4B | Acknowledged behavior — only needs metric |
| `dead_letter.py` commit guards | Plan3: 2A | Already fixed |
| `pipeline.py` commit guard | Plan3: 2B | Already fixed |
| Eager loading for sources/pipelines/articles | Plan3: 3A-3C | Not needed |
| SQL LIKE wildcard escaping | Plan3: 4A | Not needed — uses `escape="\"` |
| `context_service.py` tests | Plan3: 6B | Already exists |
| `config_cache.py` tests | Plan3: 6A | Already exists |
| Empty state icons | Plan5: 4.2 | Already implemented |

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| 1A: Re-raising in `crawl_source` may increase retry storms | Monitor retry rates; adjust `max_retries` if needed |
| 1E: Re-raising in `_send_emails_parallel` may cause duplicate emails | Ensure Celery task is idempotent |
| 2A: Chord-based crawl aggregation | Test with multiple sources; verify error handling |
| 2B: Bulk reprocess dispatch failure handling | Test with mocked Celery |
| 2E: Removing manual cascade deletion | Add cascade tests first (Wave 8E), then remove |
| 3A: LLM provider thread safety | Test with concurrent requests |
| 3I: SQL similarity matching performance | Benchmark with production data volume |
| 8C: Splitting test file | Run full suite after each split |
| 10D: Newsletter personalization complexity | Start with topic preferences only; measure performance impact |

---

## Files Changed Summary

### Wave 1 — Critical Bugs
- `tasks/crawl.py` — 1A
- `tasks/extract.py` — 1B, 1C
- `services/context_service.py` — 1D
- `tasks/newsletter.py` — 1E, 1F
- `tests/test_context_service.py` — 1G

### Wave 2 — Race Conditions & Cache
- `tasks/pipeline.py` / `tasks/crawl.py` — 2A
- `routes/admin/api.py` — 2B
- `services/cache.py` — 2C
- `services/limiter.py` — 2D
- `routes/admin/articles.py` — 2E

### Wave 3 — Service-Level Fixes
- `services/llm/anthropic.py`, `openai.py`, `ollama.py`, `gemini.py` — 3A
- `services/llm/errors.py` — 3B
- `services/llm/gemini.py` — 3C
- `services/trend_detector.py` — 3D
- `services/circuit_breaker.py` — 3E
- `services/url.py` — 3F
- `services/metrics.py` — 3G
- `services/cache_base.py` — 3H
- `services/article.py` — 3I, 3J

### Wave 4 — Route & Input Validation
- `routes/admin/api.py` — 4A, 4B
- `routes/admin/shares.py` — 4B
- `routes/admin/pipelines.py` — 4B
- `routes/admin/articles.py` — 4C, 4D
- `routes/admin/sources.py` — 4E
- `routes/admin/dashboard.py` — 4F, 4G
- `routes/admin/metrics.py` — 4F

### Wave 5 — Newsletter & Task Improvements
- `tasks/newsletter.py` — 5A, 5D
- `tasks/retry.py` — 5B, 5C
- `services/redis_utils.py` — 5E
- `services/degradation.py` — 5F

### Wave 6 — UI Fixes
- `templates/partials/cards.html` — 6A (new)
- `templates/admin/login.html` — 6B
- `static/css/critical.css` — 6C
- `static/css/base.css` — 6C
- `templates/base.html` — 6C
- `static/css/articles.css` — 6D, 6P
- `static/css/style.css` — 6E
- `templates/partials/topic_icon.html` — 6F
- `static/css/components.css` — 6G, 6H, 6K
- `static/css/pages.css` — 6I, 6L
- `templates/verify.html` — 6I, 6J
- `templates/share_redirect.html` — 6J
- `templates/base_admin.html` — 6M
- `templates/admin/dashboard.html` — 6N
- `static/css/layout.css` — 6O

### Wave 7 — Configuration & Code Quality
- `services/url.py` — 7A
- `services/cache.py` — 7B
- `routes/admin/__init__.py` — 7C
- `services/article.py` — 7D
- `services/crawling.py` — 7E
- `services/cache_base.py` — 7F
- `services/redis_utils.py` — 7F
- `tasks/retry.py` — 7F
- `services/config_cache.py` — 7G
- `tasks/edit.py` — 7H
- `routes/admin/api.py` — 7H
- `.gitignore` — 7J
- `tests/.DS_Store` — 7J (delete)

### Wave 8 — Test Improvements
- `tests/test_admin_api.py` — 8A, 8D
- `tests/test_config.py` — 8B (new)
- `tests/test_new_services.py` — 8C (split)
- `tests/test_models.py` — 8E (new)
- `tests/test_admin_shares.py` — 8F (new)
- `pyproject.toml` — 8G
- `tests/factories.py` — 8H

### Wave 9 — Documentation & Observability
- `docs/api.md` — 9A (new)
- `docs/deployment.md` — 9B
- `docs/development.md` — 9C (new)
- `docs/security.md` — 9D (new)
- `docs/troubleshooting.md` — 9E (new)
- `docs/monitoring.md` — 9F (new)
- `logging_config.py` — 9G, 9I
- `config.py` — 9G
- `services/health.py` — 9H
- `routes/public.py` — 9H
- `docs/logging.md` — 9I (new)

### Wave 10 — Feature Enhancements
- `templates/admin/article_versions.html` — 10A (new)
- `routes/admin/review.py` — 10A
- `models.py` — 10A, 10B, 10D, 10E, 10H
- `routes/admin/api.py` — 10B, 10E
- `tasks/pipeline.py` — 10B
- `routes/public.py` — 10C, 10F
- `templates/partials/search.html` — 10C (new)
- `services/newsletter.py` — 10D
- `services/webhooks.py` — 10E (new)
- `services/cache.py` — 10F
- `services/metrics.py` — 10G
- `routes/admin/metrics.py` — 10G (new)
- `services/audit.py` — 10H (new)

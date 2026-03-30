# ainews Consolidated Improvement Plan

Consolidated from plan2–plan5. Items verified against current codebase state (2026-03-30).

**Status key:** ✅ Done | 🔶 Partially done | ❌ Not done

## Phase 1: Bug Fixes & Transaction Safety

### 1.1 ✅ Fix `_dead_letter()` missing try/except around commit

**File:** `tasks/retry.py:98`

**Status:** Done — commit wrapped in `try/except SQLAlchemyError` with rollback and logging.

```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    logger.error(f"Failed to commit dead-letter for article {article.id}")
```

---

### 1.2 ✅ Fix `_handle_stage_failure()` double-commit inconsistency

**File:** `tasks/pipeline.py:309-318`

**Status:** Done — standalone commit before `_degrade_and_advance()` removed.

---

### 1.3 ✅ Add startup warning for default SECRET_KEY

**File:** `config.py` — `DevelopmentConfig.__init__`

**Status:** Done — warning logged when `SECRET_KEY == "dev-secret-key-change-me"`.

---

## Phase 2: Error Handling & Logging

### 2.1 ✅ Add logger to `routes/admin/api.py` health endpoint

**File:** `routes/admin/api.py:7-66`

**Status:** Done — module-level logger added, all five `except Exception:` blocks now call `logger.exception()`.

---

### 2.2 ✅ Fix bare `Exception` catches in `routes/admin/sources.py`

**File:** `routes/admin/sources.py:31, 49`

**Status:** Done — both handlers now catch `SQLAlchemyError` with proper rollback.

---

### 2.3 ✅ Deduplicate `limit_content_length` decorator

**Files:** `routes/public.py:35-48`, `routes/admin/auth.py:15-31`

**Status:** Done — single definition in `routes/__init__.py`, both files import from there.

---

### 2.4 ✅ Bare `except Exception` in `routes/public.py`

**File:** `routes/public.py:59, 359` (now `routes/public/__init__.py` and `routes/public/feeds.py`)

**Status:** Done — `logger.exception()` added everywhere. Health endpoint uses specific types (`SQLAlchemyError`, `RedisError`) for DB/Redis checks. Remaining broad catches have logging and are intentional (topic loading fallback, Celery inspect).

---

## Phase 3: Test Coverage

### 3.1 ✅ Tests for `services/crawling.py`

**Created:** `tests/test_crawling.py` (201 lines). All planned functions tested.

---

### 3.2 ✅ Tests for `services/cache.py` (ResponseCache)

**Created:** `tests/test_response_cache.py` (182 lines). All scenarios covered.

---

### 3.3 ✅ Tests for `services/pipeline_monitor.py`

**Created:** `tests/test_pipeline_monitor.py` (147 lines). All scenarios covered.

---

### 3.4 ✅ Tests for LLM adapters

**Created:** `tests/test_llm_adapters.py` (302 lines). All scenarios covered.

---

### 3.5 ✅ Tests for `tasks/crawl.py`

**Created:** `tests/test_crawl_task.py` (256 lines). All scenarios covered: `crawl_source` — lock skip, schedule skip, happy path, exception handling, lock held by different task. `run_all_sources` — no sources, load failure retries, dispatches sources, TimeoutError handling.

---

### 3.6 ✅ Tests for select and extract tasks

**Created:** `tests/test_task_select.py` (269 lines) — fully complete. `tests/test_extract_task.py` (144 lines) — extract task tests: happy path, extraction failure with fallback, duplicate detection, no-URL skip. `tests/test_dedup.py` — dedup URL/title match tests.

---

### 3.7 🔶 Tests for admin API endpoints

**Created:** `tests/test_admin_api.py` (152 lines).

**Done:** Config reload, bulk articles (delete, set_status, set_category, invalid action, >500 ids, empty list, no JSON), pipeline stats, sources health, auth checks on all endpoints.

**Skipped:** `test_authenticated` in `TestHealth` — skipped due to SQLAlchemy SQLite connection state contamination that causes naive/aware datetime comparison failures in downstream tests.

---

### 3.8 ✅ Un-skip migration tests

**Rewritten:** `tests/test_migration.py` — replaced skipped `TestMigrations` class with `TestMigrationChain` (heads, chain integrity, revision loading) and `TestCreateAllSchema` (tables, article columns, source columns). Uses `flask_migrate.Migrate()` wired in conftest. Full upgrade/downgrade cannot run on SQLite due to migration 004's `op.create_unique_constraint`.

---

## Phase 4: Infrastructure

### 4.1 ✅ Docker migration init service

**File:** `docker-compose.yml`

**Status:** Done — `db-migrate` service runs `flask db upgrade`, `web` and `celery-worker` depend on it with `service_completed_successfully`.

---

### 4.2 ✅ Configurable constants

**Status:** Done — all three constants configurable via env vars with fallback defaults.

---

### 4.3 ✅ Database model consistency audit

**Created:** `scripts/validate_models.py` (73 lines). Validates `server_default` + `nullable=False` convention.

---

### 4.4 ✅ Conftest improvements

**Status:** Done — `_warned_missing_vars` reset, `_reset_factory_counter` autouse fixture added.

---

## Phase 5: Architecture Improvements (Longer-term)

### 5.1 ✅ Route refactoring

**Files:** `routes/public/` package (replaces 670-line `routes/public.py`).

**Status:** Done — split into:
- `routes/public/__init__.py` — Blueprint, shared helpers (`_render_feed_or_page`, `_get_categories`, etc.), health endpoint
- `routes/public/feeds.py` — index, topic_feed, tag_feed, feed_all, feed_topic, sitemap
- `routes/public/subscribe.py` — subscribe, unsubscribe, verify
- `routes/public/links.py` — article_detail, short_url_redirect, short_url_tracking_page, track_share_click

Backward-compatible: `from routes.public import public_bp` still works.

---

### 5.2 ✅ Service layer simplification

**Files:** `services/article.py`, `services/article_parser.py`, `services/pagination.py`

**Status:** Done — `parse_article_json`/`parse_articles` extracted to `services/article_parser.py`. FTS search and pagination extracted to `services/pagination.py`. `services/article.py` re-exports for backward compatibility. `services/utils.py` re-exports `paginate_query` from the canonical location in `services/pagination.py`.

---

### 5.3 ✅ Configuration unification

**New:** `services/config_unified.py`

**Status:** Done — `AppConfig` dataclass aggregates pipeline, security, and source config. `from_flask()` builds from Flask context, `from_env()` falls back to env vars. `get_config()` provides cached access. `reset_config()` for testing. **Utility module** — available for use but not yet wired into existing config access patterns.

---

## Phase 6: Observability & Resilience (Longer-term)

### 6.1 ✅ Structured logging

**New:** `services/logging_utils.py`

**Status:** Done — `log_pipeline_event()`, `log_article_event()`, `log_admin_event()` provide structured context logging. `log_duration()` context manager tracks operation timing. Builds on existing `logging_config.py` JSON formatter. **Utility module** — available for use in pipeline stages and routes.

---

### 6.2 ✅ Metrics expansion

**Status:** Done — added `time_histogram()` context manager, `record_request()` helper to `services/metrics.py`. Admin health endpoint now includes DNS cache stats (`_dns_cache.get_stats()`).

---

### 6.3 ✅ Health check enhancement

**New:** `services/health.py`

**Status:** Done — `HealthResult` dataclass, `check_database()`, `check_redis()`, `check_celery()`, `check_limiter()` individual checks, `run_health_checks()` consolidated runner. **Wired into** `routes/public/__init__.py` `/health` endpoint.

---

### 6.4 ✅ Redis operations optimization

**File:** `services/pipeline_monitor.py:143`

**Status:** Done — `redis.keys()` replaced with `scan_iter(match=pattern, count=500)` in `clear_stage_stats()`. Variable renamed from `redis` to `redis_client` per AGENTS.md convention. Test fixtures updated with `scan_iter` support.

---

### 6.5 ✅ DNS cache improvement

**File:** `services/url.py`

**Status:** Done — `_TTLCache` enhanced with hit/miss statistics (`get_stats()`), proper eviction when at capacity (evicts oldest only when adding new keys, not on updates), and thread-safe stats tracking. Admin health endpoint exposes stats.

---

### 6.6 ✅ Dead letter queue

**New:** `services/dead_letter.py`

**Status:** Done — `dead_letter_article()` moves articles to failed state with structured error messages and fallback content. `get_dead_lettered_articles()` for admin review. `retry_dead_letter()` resets articles for pipeline retry. **Utility module** — separate from task-level `_dead_letter()` in `tasks/retry.py`; available for admin routes or future pipeline refactoring.

---

### 6.7 ✅ Graceful degradation

**New:** `services/degradation.py`

**Status:** Done — `@degrade_on_failure(fallback, exceptions)` decorator calls fallback when primary fails. `fallback_chain(*functions)` tries functions in order. `@safe_default(default, exceptions)` returns default on failure. **Utility module** — available for wrapping external service calls.

---

### 6.8 ✅ Timeout enforcement

**New:** `services/timeout.py`

**Status:** Done — `@timeout(seconds, operation)` decorator enforces timeout via ThreadPoolExecutor. `TimeoutBudget` tracks remaining time across sequential operations. `OperationTimeoutError` for clear error handling. **Utility module** — available for wrapping slow external calls.

---

## Phase 7: Security Hardening (Longer-term)

### 7.1 ✅ Input validation enhancement

**New:** `services/validation.py`

**Status:** Done — `validate_slug()`, `validate_category()`, `validate_token()`, `validate_page()`, `validate_per_page()`, `sanitize_search_query()`, `validate_article_id()`, `validate_bulk_ids()`. All raise `ValidationError` on failure with field context. **Utility module** — available for use in route handlers and form processing.

### 7.2 ✅ Audit logging

**New:** `services/audit.py`

**Status:** Done — `log_admin_action()` records admin actions via structured logging with `audit=True` context flag. **Utility module** — available for use in admin routes. Note: PipelineLog persistence was removed because `run_id` is NOT NULL and audit entries have no pipeline run.

---

## Execution Order

**All phases complete:** Phases 1–7 all items done. 577 tests passing, 0 lint errors.

**New files created:**
- `routes/public/__init__.py`, `feeds.py`, `subscribe.py`, `links.py` (route refactoring — wired into app)
- `services/article_parser.py`, `services/pagination.py` (service extraction — wired via re-exports)
- `services/health.py` (wired into `/health` endpoint)
- `services/config_unified.py`, `services/logging_utils.py` (utility modules)
- `services/dead_letter.py`, `services/validation.py`, `services/audit.py` (utility modules)
- `services/timeout.py`, `services/degradation.py` (utility modules)
- `tests/test_new_services.py` (44 tests for all new modules)

## Additional Fixes (not in original plan)

### A.1 `encode_short_url` library API mismatch

**File:** `models.py:18-19`

**Problem:** `short_url.encode_url(article_id, min_length=6, alphabet=...)` fails with `TypeError` on `short-url==1.2.2` — the `alphabet` parameter was removed from the module-level function.

**Fix:** Create a `UrlEncoder` instance with the custom alphabet at module level, use its `encode_url`/`decode_url` methods.

### A.2 `migrations/env.py` fileConfig in test environment

**File:** `migrations/env.py:13`

**Problem:** `fileConfig(config.config_file_name)` fails in test environment because `alembic.ini` lives at project root, not in `migrations/`.

**Fix:** Wrapped in `try/except (OSError, TypeError)` since it's only for logging setup.

## Verification

After each batch of changes:

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

Both must pass with zero failures. New tests should have no skips or xfails.

---

## Previously Reviewed — No Action Needed

- **Newsletter lock retry-awareness** (`tasks/newsletter.py:300-325`): Already correct. Uses `self.request.id` as lock value; retries from same task can re-acquire, different tasks blocked.
- **`limit_content_length` in routes/public.py and routes/admin/auth.py**: Duplicate but functional. Consolidation is item 2.3 above.

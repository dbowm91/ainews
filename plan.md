# ainews Consolidated Improvement Plan

Consolidated from plan2–plan5. Items verified against current codebase state (2026-03-29).

## Phase 1: Bug Fixes & Transaction Safety

### 1.1 Fix `_dead_letter()` missing try/except around commit

**File:** `tasks/retry.py:98`

**Problem:** `_dead_letter()` calls `db.session.commit()` without try/except. If the commit fails, the exception crashes the entire `retry_stuck` sweep — all other stuck articles lose their retry opportunity.

**Fix:** Wrap commit in try/except with rollback (matching codebase pattern). Add `from sqlalchemy.exc import SQLAlchemyError` import.

```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    logger.error(f"Failed to commit dead-letter for article {article.id}")
```

---

### 1.2 Fix `_handle_stage_failure()` double-commit inconsistency

**File:** `tasks/pipeline.py:309-318`

**Problem:** When `retry_count >= max_stage`, the function commits `retry_count` at line 310, then calls `_degrade_and_advance()` which does its own commit (resetting `retry_count = 0`). If the first commit succeeds but `_degrade_and_advance` raises, the article has an incremented `retry_count` but was never advanced.

**Fix:** Remove the standalone commit before `_degrade_and_advance()`. Let `_degrade_and_advance()` own the full transaction:

```python
if article.retry_count >= max_stage:
    _degrade_and_advance(article, stage, run_id=run_id)
    return True
```

`_degrade_and_advance()` already sets `retry_count = 0`, resets `last_error`, and commits with proper try/except/rollback.

---

### 1.3 Add startup warning for default SECRET_KEY

**File:** `config.py` — `DevelopmentConfig.__init__`

**Problem:** `SECRET_KEY` defaults to `"dev-secret-key-change-me"`. If `FLASK_CONFIG` is accidentally left as `"development"` in production, sessions are insecure.

**Fix:** Add warning check in `DevelopmentConfig.__init__`, same pattern as existing `ADMIN_PASSWORD` warning.

---

## Phase 2: Error Handling & Logging

### 2.1 Add logger to `routes/admin/api.py` health endpoint

**File:** `routes/admin/api.py:7-66`

**Problem:** Five bare `except Exception:` blocks silently swallow errors in the health endpoint. No log output for debugging.

**Fix:** Add module-level logger, use `logger.exception()` in each catch block. Resilience is preserved while making failures visible.

---

### 2.2 Fix bare `Exception` catches in `routes/admin/sources.py`

**File:** `routes/admin/sources.py:31, 49`

**Problem:** `enable_source` and `disable_source` catch bare `Exception` instead of `SQLAlchemyError`, potentially masking non-DB errors.

**Fix:** Replace with `except SQLAlchemyError:` in both handlers.

---

### 2.3 Deduplicate `limit_content_length` decorator

**Files:** `routes/public.py:35-48`, `routes/admin/auth.py:15-31`

**Problem:** Identical decorator defined in two files (auth.py version has leading underscore).

**Fix:** Move single definition to `routes/__init__.py` (currently empty). Import from there in both files. No circular dependency risk since `routes/__init__.py` doesn't import from submodules.

---

### 2.4 Bare `except Exception` in `routes/public.py`

**File:** `routes/public.py:75, 375`

**Problem:** Bare `except Exception:` catches all exceptions including `KeyboardInterrupt` and `SystemExit`.

**Fix:** Use `except Exception as e:` with logging, or more specific exception types where identifiable.

---

## Phase 3: Test Coverage

### 3.1 Tests for `services/crawling.py`

**Create:** `tests/test_crawling.py`

**Functions to test:**
- `create_pipeline_run()`, `should_skip_source()`, `get_existing_external_ids()`
- `filter_new_items()`, `filter_non_other_topics()`, `get_or_create_source()`
- `update_source_crawl_time()`, `update_pipeline_run_stats()`
- `record_crawl_success()` — resets failures, re-enables disabled source
- `record_crawl_failure()` — increments failures, auto-disables at threshold (10)

---

### 3.2 Tests for `services/cache.py` (ResponseCache)

**Create:** `tests/test_response_cache.py`

**Tests:** `get()` empty/hit/expiry, `set()`/`get()` round-trip, L1 memory hit, L2 Redis hit, `get_or_set()`, `invalidate()`, `invalidate_prefix()`, `get_stats()`, Redis `RedisError` handling, key hashing for keys > 200 chars.

---

### 3.3 Tests for `services/pipeline_monitor.py`

**Create:** `tests/test_pipeline_monitor.py`

**Tests:** `record_stage_result()` success/failure/RedisError, `get_stage_stats()` aggregation and defaults on RedisError, `get_all_stages_stats()`, `clear_stage_stats()` per-stage and all.

---

### 3.4 Tests for LLM adapters

**Create:** `tests/test_llm_adapters.py`

**Tests:** `OllamaProvider.chat()` with/without system message, error translation, `_chat_with_schema()`, `health_check()`, lazy client initialization, `handle_provider_error()` with `ConnectionError` → `ProviderTimeoutError`, auth errors → `AuthError`.

---

### 3.5 Tests for `tasks/crawl.py`

**Create:** `tests/test_crawl_task.py`

**Tests:** `crawl_source` happy path, source not found, source disabled, schedule skip, exception handling. `run_all_sources` dispatch and TimeoutError handling.

---

### 3.6 Tests for select and extract tasks

**Create:** `tests/test_task_select.py`, extend `tests/test_dedup.py`

**Tests for select:** score ≥ threshold → researching + dispatches next, score < threshold → skipped, selector disabled → dispatches researching directly.

**Tests for extract:** happy path, extraction failure with empty text, dedup URL match, dedup title match, source not found.

---

### 3.7 Tests for admin API endpoints

**Create:** `tests/test_admin_api.py`

**Tests:** `GET /admin/api/health` (authenticated + 401), `POST /admin/api/config/reload`, bulk article operations (delete, set_status, set_category, invalid action, >500 ids, empty list), `GET /admin/api/pipeline/stats`, `GET /admin/api/sources/health`.

---

### 3.8 Un-skip migration tests

**File:** `tests/test_migration.py`

**Problem:** Tests skipped because Flask-Migrate not wired in test fixture.

**Fix:** Add `Migrate()` init in `tests/conftest.py` after `db.init_app(app)`. May need to remove `db.create_all()` and rely on migrations. Then un-skip the `TestMigrations` class.

---

## Phase 4: Infrastructure

### 4.1 Docker migration init service

**File:** `docker-compose.yml`

**Add:** `db-migrate` service that runs `flask db upgrade`. Set `depends_on` with `service_completed_successfully` condition on both `web` and `celery-worker` services. Use `restart: "no"`.

---

### 4.2 Configurable constants

**Files:** `config.py`, `services/crawling.py`, `constants.py`

**Move to Config class with env var support:**
- `MAX_CONSECUTIVE_FAILURES` (currently module-level `= 10` in `services/crawling.py:13`)
- `STUCK_THRESHOLD_MINUTES` (currently module-level `= 60` in `constants.py:61`)
- `MIN_CONTENT_LENGTH` (currently hardcoded 200 in content extraction)

Default values unchanged for backward compatibility.

---

### 4.3 Database model consistency audit

**Files:** All model files, migration files

**Create:** `scripts/validate_models.py`

Check that all columns with `server_default` also have `nullable=False` in Python models. The `AGENTS.md` already documents this convention but it's not enforced. Validate at CI time.

---

### 4.4 Conftest improvements

**File:** `tests/conftest.py`

- Reset `_warned_missing_vars` from `schemas/common.py` in `_reset_redis` autouse fixture (prevents warning suppression leaking across tests)
- Add `_reset_factory_counter` autouse fixture to reset `factories._counter = 0` between tests

---

## Phase 5: Architecture Improvements (Longer-term)

### 5.1 Route refactoring

**Files:** `routes/public.py` (689 lines) → split into blueprint modules

Split into: `routes/public/articles.py`, `routes/public/feed.py`, `routes/public/subscribe.py`. Keep common routes (index, health, topic, tag) in `routes/public/__init__.py`. Provide 301 redirects for any URL changes. Target: each file under 200 lines.

---

### 5.2 Service layer simplification

**Files:** `services/article.py`

Extract: metrics tracking → `services/metrics.py`, pagination → `services/pagination.py`, JSON parsing → `services/article_parser.py`. Apply Single Responsibility Principle.

---

### 5.3 Configuration unification

**New:** `services/config_unified.py`

Unified config loader with precedence: DB > Env > YAML > Defaults. Pydantic schema validation at startup. Hot-reload via file watchers. Backward-compatible wrapper for existing `config.KEY` access patterns.

---

## Phase 6: Observability & Resilience (Longer-term)

### 6.1 Structured logging

**New:** `services/logging_utils.py`

Context vars for `request_id` and `article_id`. Structured log filter adding these fields automatically. Standardize log levels across codebase.

---

### 6.2 Metrics expansion

Extend `services/metrics.py` with histogram metrics for LLM call latency, content extraction duration, DB query time. Add Prometheus exposition via `/admin/api/metrics/prometheus`. Leverage existing `pipeline_monitor.py` Redis counters.

---

### 6.3 Health check enhancement

**New:** `services/health.py`

Comprehensive health checker with circuit breaker pattern. Parallel checks for database, Redis, Ollama, SMTP, pipeline. Add `/health/detailed` and `/health/dependencies/<name>` endpoints.

---

### 6.4 Redis operations optimization

**File:** `services/pipeline_monitor.py:143`

Replace `redis.keys()` with `scan_iter()` batched iteration in `clear_stage_stats()`. Add connection pool metrics. Consider instrumented Redis client wrapper.

---

### 6.5 DNS cache improvement

**File:** `services/url.py:35-66`

Replace `_TTLCache` (evicts oldest by timestamp) with LRU eviction policy. Add hit rate statistics. Add cache warming for active source domains.

---

### 6.6 Dead letter queue

**New:** `services/dead_letter.py`, model in `models.py`

Archive articles exceeding `MAX_TOTAL_RETRIES` to `dead_letter_articles` table with full failure context. Admin UI for viewing and manual retry. Audit trail for permanently failed articles.

---

### 6.7 Graceful degradation

Extend LLM fallback chain with explicit model-level fallbacks per role. Add fallback article extraction (trafilatura → readability → raw HTML). "Best effort" mode that continues pipeline with degraded quality.

---

### 6.8 Timeout enforcement

Review all HTTP request timeouts. Add Celery task soft/hard timeouts. Add database query timeouts. Make configurable in `pipeline.yaml`.

---

## Phase 7: Security Hardening (Longer-term)

### 7.1 Input validation enhancement

Comprehensive Pydantic validation on all route inputs. Validate all query parameters. Sanitize user inputs in templates.

### 7.2 Audit logging

**New:** `services/audit.py`, model in `models.py`

Log all admin actions (CRUD, config changes, source modifications) to `audit_logs` table. Admin UI for viewing audit trail.

---

## Execution Order

**Immediate (bugs + safety):** Items 1.1, 1.2, 1.3
**Quick wins (error handling):** Items 2.1, 2.2, 2.3, 2.4
**Test foundation:** Items 4.4 (conftest), then 3.1–3.8
**Infrastructure:** Items 4.1, 4.2, 4.3
**Architecture:** Phase 5 items
**Observability:** Phase 6 items
**Security:** Phase 7 items

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

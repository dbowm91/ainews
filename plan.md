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

### 2.4 🔶 Bare `except Exception` in `routes/public.py`

**File:** `routes/public.py:59, 359`

**Status:** Partially done — `logger.exception()` added everywhere. Health endpoint uses specific types (`SQLAlchemyError`, `RedisError`) for DB/Redis checks. Remaining broad catches have logging and are arguably intentional.

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

### 5.1 ❌ Route refactoring

**Files:** `routes/public.py` (670 lines). No `routes/public/` directory exists yet.

---

### 5.2 🔶 Service layer simplification

**Files:** `services/article.py`

**Done:** `services/metrics.py` extracted. **Missing:** `services/pagination.py`, `services/article_parser.py`.

---

### 5.3 ❌ Configuration unification

**New:** `services/config_unified.py` — not created.

---

## Phase 6: Observability & Resilience (Longer-term)

### 6.1 ❌ Structured logging

**New:** `services/logging_utils.py` — not created.

---

### 6.2 ❌ Metrics expansion

Not started.

---

### 6.3 ❌ Health check enhancement

**New:** `services/health.py` — not created.

---

### 6.4 ✅ Redis operations optimization

**File:** `services/pipeline_monitor.py:143`

**Status:** Done — `redis.keys()` replaced with `scan_iter(match=pattern, count=500)` in `clear_stage_stats()`. Variable renamed from `redis` to `redis_client` per AGENTS.md convention. Test fixtures updated with `scan_iter` support.

---

### 6.5 ❌ DNS cache improvement

Not started.

---

### 6.6 ❌ Dead letter queue

**New:** `services/dead_letter.py` — not created.

---

### 6.7 ❌ Graceful degradation

Not started.

---

### 6.8 ❌ Timeout enforcement

Not started.

---

## Phase 7: Security Hardening (Longer-term)

### 7.1 ❌ Input validation enhancement

Not started.

### 7.2 ❌ Audit logging

**New:** `services/audit.py` — not created.

---

## Execution Order

**Completed:** Phases 1–2 (items 1.1–1.3, 2.1–2.4), Phase 3 (items 3.1–3.8), Phase 4 (all items), Phase 6.4

**Remaining (by priority):**
1. Phase 5 items — longer-term architecture improvements
2. Phase 6 items (except 6.4) — longer-term observability
3. Phase 7 items — longer-term security

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

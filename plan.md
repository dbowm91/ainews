# ainews Improvement Plan

## 1. Inconsistent Error Handling ✅

### Problem
Broad `except Exception:` blocks catch too many exceptions, making debugging harder and potentially masking real errors.

### Key Files
- `services/crawling.py:32-36` — bare `except Exception` with re-raise
- `tasks/pipeline.py` — multiple locations with broad exception handling
- `services/config_cache.py` — catches all exceptions silently

### Changes
1. Replace broad `except Exception:` with specific exception types where known:
   - `sqlalchemy.exc.IntegrityError` for DB constraint violations
   - `sqlalchemy.exc.OperationalError` for connection issues
   - `redis.exceptions.ConnectionError` for Redis failures
   - `requests.exceptions.RequestException` for HTTP calls

2. Keep `except Exception:` only for top-level safety nets where re-logging is appropriate

3. Add exception context to log messages (include article_id, stage, provider where relevant)

### Status
**Done.** Replaced `except Exception:` with `redis.exceptions.RedisError` in `services/limiter.py`, `services/config_cache.py`. Replaced with `SQLAlchemyError` in `services/crawling.py`, `tasks/pipeline.py`. Safety-net catches in `tasks/crawl.py`, `tasks/newsletter.py` left as broad `Exception` (re-raised).

### Files Modified
- `services/crawling.py`
- `tasks/pipeline.py`
- `services/config_cache.py`
- `services/limiter.py`

---

## 2. Type Hints Coverage ✅

### Problem
Several functions lack return type hints and parameter type hints, reducing IDE support and catching errors at development time.

### Key Gaps
- `services/limiter.py` — `acquire()`, `release()`, `get_active()` missing return hints
- `services/circuit_breaker.py` — `can_execute()` returns `bool` but not annotated
- `services/config_cache.py` — `get()` method generic type not preserved
- `routes/public.py` — many route handlers untyped

### Status
**Done.** Most gaps were already filled in the codebase. Added return type annotations to helper functions in `routes/public.py` (`_render_feed_or_page`, `_get_categories`, `_get_topic_icons`, `_get_tag_cloud`, `_get_share_configs`). Route handlers left untyped (Flask's own type stubs handle these).

### Files Modified
- `routes/public.py`

---

## 3. Config Caching Invalidation ✅ (no change needed)

### Problem
`config_cache.py` uses Redis TTL but no explicit invalidation. Config changes (editing `pipeline.yaml`, `topics.yaml`, `sources.yaml`) require waiting for TTL expiry.

**Verified:** `routes/admin/api.py:60-68` already has `POST /admin/api/config/reload` that calls `invalidate_all()` and `clear_provider_cache()`. This endpoint exists but is not called automatically after config saves in admin routes.

### Status
**No change needed.** Config files (pipeline.yaml, topics.yaml, sources.yaml) are edited on disk, not through admin UI routes. The existing `POST /admin/api/config/reload` is the correct manual invalidation point. If admin config-editing routes are added later, they should call invalidation.

### Deferred
If admin config editor routes are added, wire up `get_config_cache().invalidate_all()` after saves.

---

## 4. Celery Task Idempotency ✅

### Problem
Multiple Celery workers can process the same source simultaneously. `tasks/crawl.py` fetches items but doesn't prevent duplicate processing across workers.

### Status
**Done.** Added Redis distributed locking to both crawl and newsletter tasks.

### Changes
1. `tasks/crawl.py`: Redis lock with `nx=True, ex=30` per source. `try/finally` cleanup.
2. `tasks/newsletter.py`: Task-ID-aware lock (`self.request.id` as value). Same task retries can re-acquire; different tasks blocked. TTL=600s.

### Files Modified
- `tasks/crawl.py`
- `tasks/newsletter.py`

### Deferred
Pipeline stage locking (`ainews:stage_lock:{article_id}:{stage}`) in `tasks/pipeline.py:run_stage()` was in the original plan but not implemented. The existing limiter-based slot acquisition provides similar protection. Could be added if double-execution of the same stage on the same article is observed.

---

## 5. Retry Budget ✅

### Problem
Pipeline degradation in `tasks/pipeline.py` advances articles to next stage after `MAX_STAGE_RETRIES=3` failures, but has no global retry budget. An article could theoretically retry forever if staged across different pipeline runs.

### Status
**Done.**

### Changes
1. Added `total_retries` column to `Article` model (`nullable=False, default=0`)
2. `_handle_stage_failure()` increments `total_retries` alongside `retry_count`
3. When `total_retries >= MAX_TOTAL_RETRIES` (10), article marked `pipeline_status="failed"`
4. `reprocess_article` admin route resets `total_retries` on manual reprocessing
5. Migration `006_total_retries.py`

### Files Modified
- `models.py`
- `tasks/pipeline.py`
- `routes/admin/articles.py`
- `migrations/versions/006_total_retries.py` (new)

---

## 6. Session Security Hardening ✅

### Problem
8-hour session lifetime (`config.py:22`) increases attack window if session is compromised. Logout lacks CSRF token in the frontend form (`routes/admin/auth.py:73-76`).

### Status
**Done.** Reduced lifetime from 8h to 2h. Added `SESSION_COOKIE_PATH = "/"`. CSRF token was already present in the logout form template.

### Files Modified
- `config.py`

---

## 7. SSRF DNS Rebinding Protection ✅

### Problem
`services/url.py:57` resolves DNS on every call but does not cache results. A DNS rebinding attack could resolve to a safe IP on first check and a private IP on the actual fetch.

### Status
**Done.**

### Changes
1. Added `_TTLCache` class — bounded dict with maxsize=1024, TTL=60s
2. DNS results cached on first resolution, reused on subsequent calls for same hostname
3. Cache evicts oldest entry when full
4. Test fixture `_clear_dns_cache` prevents cross-test contamination

### Files Modified
- `services/url.py`

---

## 8. Content Extraction Timeout ✅

### Problem
`services/content_extractor.py:55` calls `trafilatura.fetch_url(url)` without an explicit timeout. Slow or unresponsive sites can block the pipeline indefinitely.

### Status
**Done.** Uses `trafilatura.settings.use_config()` to set `DOWNLOAD_TIMEOUT=30`.

### Files Modified
- `services/content_extractor.py`

---

## 9. Database Connection Pooling ✅

### Problem
SQLAlchemy without explicit pool configuration. Under load, connection exhaustion can occur.

### Status
**Done.** Added `SQLALCHEMY_ENGINE_OPTIONS` with `pool_pre_ping=True` and `pool_recycle=3600` to `ProductionConfig`.

### Files Modified
- `config.py`

---

## 10. Redis Connection Pooling ✅

### Problem
`extensions.py:42-61` creates a single Redis client without connection pooling.

### Status
**Done.** Switched to `redis.ConnectionPool.from_url(url, max_connections=20)`. Added `reset_redis()` that properly disconnects the pool.

### Files Modified
- `extensions.py`

---

## 11. Pipeline Log Cleanup ✅

### Problem
`models.py:230-244` PipelineLog grows unbounded.

### Status
**Done.**

### Changes
1. New `tasks/cleanup.py` with `cleanup_old_pipeline_logs()` — deletes logs >30 days
2. Scheduled via Celery Beat at 3am daily

### Files Created/Modified
- `tasks/cleanup.py` (new)
- `config.py`

---

## 12. RSS XXE Protection ✅

### Problem
`adapters/rss.py:41` uses `feedparser.parse()` without explicit XXE protection.

### Status
**Done.** Added `defusedxml==0.7.1` to requirements.txt as defensive dependency. Feedparser itself is generally safe; defusedxml is available if raw XML parsing is added later.

### Files Modified
- `requirements.txt`

---

## 13. Pipeline Stage Integration Tests ✅

### Problem
The pipeline has 4 LLM-powered stages: `select`, `research`, `write`, `edit`. Current tests lack coverage for actual pipeline stage execution.

### Status
**Done.**

### Changes
1. `tests/test_pipeline_research.py`: Degradation tests (5 tests)
2. `tests/test_pipeline_write.py`: Fallback tests with attribution preservation (5 tests)
3. `tests/test_pipeline_edit.py`: Degradation, retry reset, review routing (6 tests)
4. `tests/test_pipeline.py`: `TestRetryBudget` class (4 tests)
5. `tests/test_cleanup.py`: Log cleanup integration (2 tests)
6. `tests/test_limiter.py`: `is_healthy()` tests (2 tests)
7. `tests/test_routes.py`: 413 handler test (1 test)
8. `tests/test_url_validate.py`: DNS cache fixture (1 test)

### Files Created/Modified
- `tests/test_pipeline_research.py` (new)
- `tests/test_pipeline_write.py` (new)
- `tests/test_pipeline_edit.py` (new)
- `tests/test_pipeline.py`
- `tests/test_cleanup.py` (new)
- `tests/test_limiter.py` (new)
- `tests/test_routes.py`
- `tests/test_url_validate.py` (new)

### Deferred
Full end-to-end test (pending → researching → writing → editing → done) was in the plan but not implemented. The individual stage tests plus the existing `test_integration.py` provide reasonable coverage. Could be added if pipeline regressions are observed.

---

## 14. Request Size Limits ✅

### Problem
Large request bodies could cause memory issues or be used for DoS.

### Status
**Done.** `MAX_CONTENT_LENGTH = 64 * 1024` (64KB, raised from planned 16KB). 413 error handler with JSON/text content negotiation.

### Files Modified
- `config.py`
- `app.py`

---

## 15. Limiter Health Check ✅

### Problem
`ModelLimiter` fails closed (denies slots) when Redis is unavailable, but there's no way to diagnose this from health endpoints.

### Status
**Done.**

### Changes
1. `ModelLimiter.is_healthy()` — pings Redis, returns bool
2. `GET /health` includes `limiter: "ok" | "degraded"`
3. `GET /admin/api/health` includes `limiter.healthy` boolean

### Files Modified
- `services/limiter.py`
- `routes/public.py`
- `routes/admin/api.py`

---

## Implementation Order

| Phase | Items | Rationale | Status |
|-------|-------|-----------|--------|
| **1** | Type Hints (#2), Error Handling (#1) | Low risk, developer experience | ✅ |
| **2** | Config Invalidation (#3), Request Limits (#14), Limiter Health (#15) | Small changes, immediate benefit | ✅ |
| **3** | Celery Idempotency (#4), Retry Budget (#5), Session Security (#6) | Production resilience | ✅ |
| **4** | Content Timeout (#8), DB/Redis Pooling (#9, #10) | Performance hardening | ✅ |
| **5** | SSRF (#7), RSS XXE (#12), Log Cleanup (#11) | Security hardening | ✅ |
| **6** | Pipeline Tests (#13) | Ongoing, high coverage value | ✅ |

## Testing Strategy

Each change should:
1. Pass existing test suite: `.venv/bin/python -m pytest tests/ -x -q`
2. Pass linter: `.venv/bin/ruff check . --exclude .venv`
3. Add new tests for new behavior (invalidation, locking, retry budget)
4. Manual verification via admin dashboard for UI-facing changes

## Deferred Items (Detailed Plans)

### D1. Pipeline Stage Locking

#### Motivation

The `ModelLimiter` controls concurrency per provider/model pair, but does not prevent the same article from being processed in the same stage by two different workers simultaneously. This can happen if:
- A Celery task crashes mid-execution and is re-queued (task is retried while old worker's limiter slot is still held)
- Beat and manual trigger fire at the same time
- Network partition causes duplicate delivery

Adding a per-article, per-stage lock ensures exactly-once execution.

#### Design

Use a Redis lock keyed by `(article_id, stage)` with a TTL matching the stage's `timeout_seconds`. Acquire the lock before the limiter in `run_stage()`. If the lock can't be acquired, skip (another worker is processing this article in this stage).

```python
# In tasks/pipeline.py:run_stage(), before the limiter acquire
lock_key = f"ainews:stage_lock:{article_id}:{stage}"
redis = get_redis()
task_id = task_self.request.id or "manual"
lock_acquired = redis.set(lock_key, task_id, nx=True, ex=rc.timeout_seconds + 60)
if not lock_acquired:
    logger.info(f"Stage {stage} already running for article {article_id}, skipping")
    return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
```

Release the lock in the `finally` block (same task-id-aware pattern as `tasks/newsletter.py`):
```python
finally:
    limiter.release(rc.provider, model)
    try:
        stored = redis.get(lock_key)
        if stored and stored.decode() == task_id:
            redis.delete(lock_key)
    except Exception:
        pass
```

#### Key decisions
- Lock TTL = `rc.timeout_seconds + 60` — slightly longer than the limiter timeout so the lock outlives the stage
- Lock value = `task_self.request.id` — same retry-aware pattern as newsletter locking
- If lock acquisition fails, return early with `{"skipped": True}` rather than retrying — avoids thundering herd

#### Files to Modify
- `tasks/pipeline.py` — add lock in `run_stage()`

#### Tests
- `tests/test_pipeline.py` — test that `run_stage` returns `skipped` when lock is held by a different task ID
- Test that retries from the same task can re-acquire

#### Verification
- Run `.venv/bin/python -m pytest tests/ -x -q`
- Run `.venv/bin/ruff check . --exclude .venv`

---

### D2. Automatic Config Invalidation After Saves

#### Motivation

Config files (`pipeline.yaml`, `topics.yaml`, `sources.yaml`) are edited on disk. Currently, admins must manually call `POST /admin/api/config/reload` to clear caches. If config editor routes are added to the admin UI, they should auto-invalidate.

#### Design

**Phase 1 (if config editor routes are added):** Each config save endpoint should call invalidation after a successful write:

```python
@admin_bp.route("/api/config/pipeline", methods=["PUT"])
@require_auth
def save_pipeline_config():
    # ... validate and write pipeline.yaml ...
    get_config_cache().invalidate("pipeline")
    clear_provider_cache()
    return jsonify({"message": "Pipeline config saved"}), 200
```

**Phase 2 (alternative — file watcher):** If configs remain file-based without UI editing, add mtime-based staleness detection:

```python
# In services/config_cache.py
def invalidate_if_stale(self, key: str, config_path: Path) -> None:
    """Invalidate cache entry if the config file has been modified since last load."""
    full_key = f"{self.prefix}:{key}"
    mtime = config_path.stat().st_mtime
    cached_mtime = self._memory_cache.get(f"{full_key}:mtime")
    if cached_mtime is not None and mtime > cached_mtime:
        self.invalidate(key)
        self._memory_cache.pop(f"{full_key}:mtime", None)

def _record_mtime(self, key: str, config_path: Path) -> None:
    """Record the mtime of a config file after a successful load."""
    full_key = f"{self.prefix}:{key}"
    self._memory_cache[f"{full_key}:mtime"] = config_path.stat().st_mtime
```

Wrap the loader to record mtime after each load:
```python
def get_with_mtime(self, key: str, config_path: Path, loader_fn, ttl=300):
    self.invalidate_if_stale(key, config_path)
    result = self.get(key, loader_fn, ttl)
    self._record_mtime(key, config_path)
    return result
```

This is called at the top of `load_pipeline_config()` / `load_sources()` / `load_topics()`:
```python
def load_pipeline_config(...):
    cfg = get_config_cache()
    cfg.invalidate_if_stale("pipeline", BASE_DIR / "pipeline.yaml")
    return cached_config(...)
```

#### Key decisions
- Phase 1 is preferred if UI routes exist; Phase 2 as fallback for file-only workflows
- Both approaches are low-risk (invalidation already exists, we're just calling it automatically)

#### Files to Modify (Phase 1)
- New `routes/admin/config.py` — config editor endpoints with auto-invalidation
- `routes/admin/__init__.py` — register config blueprint

#### Files to Modify (Phase 2)
- `services/config_cache.py` — add `invalidate_if_stale()` and `_record_mtime()` methods
- `schemas/pipeline.py`, `schemas/source.py`, `schemas/topic.py` — call `invalidate_if_stale` on load

#### Tests
- Verify config reload happens automatically after file write
- Verify stale configs are reloaded without manual intervention

---

### D3. End-to-End Pipeline Integration Test

#### Motivation

Individual stage tests (research, write, edit) verify degradation and fallback behavior, but don't test the full pipeline flow or stage transitions. An end-to-end test catches integration issues like:
- Status not advancing correctly between stages
- `_dispatch_next` failing to call the next task
- `_finalize` not being called at the end
- Review routing logic not working

#### Design

Create `tests/test_pipeline_e2e.py` with a test that mocks LLM providers at each stage and verifies the full flow.

```python
class TestPipelineEndToEnd:
    """Test full pipeline: pending -> researching -> writing -> editing -> done."""

    def test_full_pipeline_no_review(self, app, create_source, mock_celery_tasks):
        """Article passes all stages and ends as done."""
        with app.app_context():
            article = create_article(
                source=create_source(),
                pipeline_status="pending",
                original_title="Test Article",
                extracted_text="Long text content...",
            )
            db.session.commit()

            # Stage 1: Select
            with patch("tasks.select.select_article") as mock_select:
                mock_select.delay.side_effect = lambda aid, **kw: _run_select(aid)
                mock_select.delay(article.id)
            article = db.session.get(Article, article.id)
            assert article.pipeline_status == "researching"

            # Stage 2: Research
            with patch("tasks.research.research_article") as mock_research:
                mock_research.delay.side_effect = lambda aid, **kw: _run_research(aid)
                mock_research.delay(article.id)
            article = db.session.get(Article, article.id)
            assert article.pipeline_status == "writing"

            # Stage 3: Write
            with patch("tasks.write.write_article") as mock_write:
                mock_write.delay.side_effect = lambda aid, **kw: _run_write(aid)
                mock_write.delay(article.id)
            article = db.session.get(Article, article.id)
            assert article.pipeline_status == "editing"

            # Stage 4: Edit (editor may be skipped)
            with patch("services.llm.get_provider_for_role") as mock_provider:
                mock_provider.return_value = (MagicMock(), "qwen3:8b", 2048)
                # If editor is disabled, _finalize is called
                from tasks.pipeline import _finalize
                _finalize(article.id)

            article = db.session.get(Article, article.id)
            assert article.pipeline_status in ("done", "review")
            assert article.final_article is not None
            assert article.retry_count == 0

    def test_pipeline_degrades_on_max_retries(self, app, create_article):
        """Article degrades to next stage after MAX_STAGE_RETRIES failures."""
        with app.app_context():
            article = create_article(
                pipeline_status="researching",
                extracted_text="Content",
            )

            from tasks.pipeline import _handle_stage_failure, MAX_STAGE_RETRIES

            for i in range(MAX_STAGE_RETRIES - 1):
                _handle_stage_failure(article, "research", Exception("fail"))
                assert article.pipeline_status == "researching"

            # Last retry triggers degradation
            _handle_stage_failure(article, "research", Exception("fail"))
            assert article.pipeline_status == "writing"
            assert article.retry_count == 0

    def test_pipeline_fails_on_global_budget(self, app, create_article):
        """Article marked failed when total_retries exceeds MAX_TOTAL_RETRIES."""
        with app.app_context():
            article = create_article(
                pipeline_status="writing",
                extracted_text="Content",
            )
            article.total_retries = 9
            article.retry_count = 0

            from tasks.pipeline import _handle_stage_failure, MAX_TOTAL_RETRIES

            _handle_stage_failure(article, "write", Exception("fail"))
            assert article.total_retries == MAX_TOTAL_RETRIES
            assert article.pipeline_status == "failed"
```

#### Key decisions
- Mock `Celery task.delay` calls with side effects that run the real logic inline (bypasses task queue)
- Use existing `create_article` and `create_source` factories
- Test both happy path and failure/degradation paths
- Avoid mocking the LLM itself — mock at the `run_stage` / `_handle_stage_failure` level

#### Files to Create
- `tests/test_pipeline_e2e.py`

#### Files to Modify
- `tests/conftest.py` — no changes needed, fixtures already exist

#### Verification
- `.venv/bin/python -m pytest tests/test_pipeline_e2e.py -v`
- `.venv/bin/ruff check . --exclude .venv`

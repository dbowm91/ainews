# ainews Improvement Plan

## 1. Inconsistent Error Handling ✅

### Problem
Broad `except Exception:` blocks catch too many exceptions, making debugging harder and potentially masking real errors.

### Key Files
- `services/crawling.py` — bare `except Exception` with re-raise (pre-fix)
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
**Done.** All config files now use `cached_config_with_mtime()` for automatic mtime-based invalidation:
- `schemas/pipeline.py` — loads `pipeline.yaml`
- `schemas/topic.py` — loads `topics.yaml`
- `schemas/source.py` — loads `sources.yaml` (fixed as a gap from review)

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

### ~~Deferred~~ — Done
Pipeline stage locking (`ainews:stage_lock:{article_id}:{stage}`) implemented in `tasks/pipeline.py:run_stage()` with task-ID-aware cleanup. See [D1](#d1-pipeline-stage-locking--done) for details.

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
8-hour session lifetime (`config.py:22`) increases attack window if session is compromised. Logout form in template lacked CSRF token verification.

### Status
**Done.** Reduced lifetime from 8h to 2h. Added `SESSION_COOKIE_PATH = "/"`. CSRF token was already present in the logout form template.

### Files Modified
- `config.py`

---

## 7. SSRF DNS Rebinding Protection ✅

### Problem
`services/url.py` resolves DNS on every call but does not cache results. A DNS rebinding attack could resolve to a safe IP on first check and a private IP on the actual fetch.

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
`services/content_extractor.py` calls `trafilatura.fetch_url(url)` without an explicit timeout. Slow or unresponsive sites can block the pipeline indefinitely.

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
`extensions.py` created a single Redis client without connection pooling. Under concurrent Celery workers, connections could be exhausted.

### Status
**Done.** Switched to `redis.ConnectionPool.from_url(url, max_connections=20)`. Added `reset_redis()` that properly disconnects the pool.

### Files Modified
- `extensions.py`

---

## 11. Pipeline Log Cleanup ✅

### Problem
`models.py` PipelineLog grows unbounded — no TTL or cleanup mechanism.

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

### ~~Deferred~~ — Done
Full end-to-end test implemented in `tests/test_pipeline_e2e.py` (4 tests: happy path, degradation, failure budget, stage locking). See [D3](#d3-end-to-end-pipeline-integration-test--done).

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

### D1. Pipeline Stage Locking ✅ Done

#### Motivation

The `ModelLimiter` controls concurrency per provider/model pair, but does not prevent the same article from being processed in the same stage by two different workers simultaneously. This can happen if:
- A Celery task crashes mid-execution and is re-queued (task is retried while old worker's limiter slot is still held)
- Beat and manual trigger fire at the same time
- Network partition causes duplicate delivery

Adding a per-article, per-stage lock ensures exactly-once execution.

#### Design

Use a Redis lock keyed by `(article_id, stage)` with a TTL matching the stage's `timeout_seconds`. Acquire the lock before the limiter in `run_stage()`. If the lock can't be acquired, skip (another worker is processing this article in this stage).

#### Status
**Done.** Implemented in `tasks/pipeline.py:run_stage()` (lines 452-506). Lock acquisition with `nx=True, ex=timeout_seconds+60`. Task-ID-aware cleanup in `finally` block. Returns `{"skipped": True, "reason": "stage_locked"}` when lock is held by another task.

#### Files Modified
- `tasks/pipeline.py`
- `tests/test_pipeline_e2e.py` — `test_stage_lock_prevents_duplicate_processing`

---

### D2. Automatic Config Invalidation After Saves

#### Motivation

Config files (`pipeline.yaml`, `topics.yaml`, `sources.yaml`) are edited on disk. Currently, admins must manually call `POST /admin/api/config/reload` to clear caches. If config editor routes are added to the admin UI, they should auto-invalidate.

#### Status
**Done.** Phase 2 (mtime-based staleness detection) implemented and wired to all config loaders. Phase 1 (UI config editor routes) deferred until needed.

#### Phase 2 — Done
`services/config_cache.py` implements:
- `invalidate_if_stale(key, config_path)` — compares cached mtime vs file's current mtime; invalidates if file was modified
- `_record_mtime(key, config_path)` — records mtime after successful load (Redis-backed, TTL=86400s)

Called from `schemas/common.py` in config loader wrappers:
- `schemas/pipeline.py` — loads `pipeline.yaml`
- `schemas/topic.py` — loads `topics.yaml`
- `schemas/source.py` — loads `sources.yaml` (added during gap fix)

#### Phase 1 — Not implemented
Config editor endpoints (`routes/admin/config.py`) not created. Config files remain edited on disk. The manual `POST /admin/api/config/reload` endpoint is the primary invalidation mechanism.

#### Key decisions
- Phase 2 chosen over Phase 1 because configs are edited on disk, not through UI
- If admin config editor routes are added later, each save endpoint should call `get_config_cache().invalidate()` + `clear_provider_cache()`

---

### D3. End-to-End Pipeline Integration Test ✅ Done

#### Motivation

Individual stage tests (research, write, edit) verify degradation and fallback behavior, but don't test the full pipeline flow or stage transitions. An end-to-end test catches integration issues like:
- Status not advancing correctly between stages
- `_dispatch_next` failing to call the next task
- `_finalize` not being called at the end
- Review routing logic not working

#### Status
**Done.** `tests/test_pipeline_e2e.py` (4 tests):

| Test | What it covers |
|------|---------------|
| `test_full_pipeline_select_through_edit` | Happy path: select → research → write → edit → done |
| `test_pipeline_degrades_on_max_retries` | Article degrades from "researching" to "writing" after MAX_STAGE_RETRIES failures |
| `test_pipeline_fails_on_global_budget` | Article marked "failed" when total_retries >= MAX_TOTAL_RETRIES |
| `test_stage_lock_prevents_duplicate_processing` | `run_stage` returns `skipped` when lock held by another task |

#### Files Created
- `tests/test_pipeline_e2e.py`

---

## 16. Newsletter Pipeline Tests ✅

### Problem
The newsletter pipeline (`services/newsletter_pipeline.py`) generates executive summaries using reader → writer → editor LLM stages, but has no dedicated test coverage. The pipeline follows similar patterns to the article pipeline but lacks verification of:
- Pydantic model parsing for NewsletterBrief and ExecutiveSummary
- Fallback behavior when stages fail
- Topic context building for main vs topic-specific newsletters

### Status
**Done.** `tests/test_newsletter_pipeline.py` (13 tests):

| Test Class | Tests |
|-----------|-------|
| `TestNewsletterBriefModel` | Valid data, connections default, serialization |
| `TestExecutiveSummaryModel` | Required field, JSON serialization |
| `TestBuildReaderPrompt` | Topic context, articles section |
| `TestBuildWriterPrompt` | Brief JSON embedding, topic context |
| `TestBuildEditorPrompt` | Review instructions, tone |
| `TestRoleConfig` | Config loading for reader role |
| `TestNewsletterPipelineIntegration` | Happy path (generate returns string), all-stages-disabled fallback |

### Files Created
- `tests/test_newsletter_pipeline.py` (new)

---

## 17. RSS Service Tests ✅

### Problem
`services/rss.py` generates RSS feeds and XML sitemaps but has no test coverage. This is public-facing output that could break rendering if malformed.

### Status
**Done.** `tests/test_rss.py` (19 tests):

| Test Class | Tests |
|-----------|-------|
| `TestGenerateRSSFeed` | Valid XML, required fields, article item/link/guid, description, category, author, pubDate, multiple articles |
| `TestGenerateSitemap` | Valid XML, homepage, topic pages (mocked), article URLs, lastmod |
| `TestFormatDate` | Naive datetime UTC conversion, aware datetime, RFC 2822 format |
| `TestParseFinalArticle` | Headline/tldr extraction, fallback to original title |

### Files Created
- `tests/test_rss.py` (new)

---

## 18. Trend Detector Tests ✅

### Problem
`services/trend_detector.py` classifies articles into topics using regex pattern matching but has no test coverage. Misclassification could cause articles to be dropped during crawling or assigned wrong categories.

### Status
**Done.** `tests/test_trend_detector.py` (21 tests):

| Test Class | Tests |
|-----------|-------|
| `TestClassify` | AI keywords, LLM variations, CVE patterns, hardware, privacy, programming, multi-topic, no-match fallback, case insensitive, body text param, deep learning variants |
| `TestComputeVelocity` | Newer > older, age floor, score proportionality, correct calculation |
| `TestLoadPatterns` | Cache integration, fallback on failure, fallback completeness |
| `TestTopicMatching` | Security, privacy, and AI+hardware article classification (integration) |

### Files Created
- `tests/test_trend_detector.py` (new)

---

## Areas Not Covered by This Plan

The following exist in the codebase but are not addressed above. They are stable and don't need changes, but are documented here for completeness.

### Deployment Infrastructure
- **ASGI adapter** — `run.py` exports `WsgiToAsgi(flask_app)` for granian (documented in AGENTS.md)
- **Docker** — `docker-compose.yml` (4 services: web, worker, beat, redis), `Dockerfile` (Python 3.12-slim, non-root user)
- **systemd** — 3 unit files in `systemd/` with memory limits and security hardening (`NoNewPrivileges`, `ProtectSystem=strict`)
- **Scripts** — `scripts/` (dev, test, install, deploy, backup, hash_password)
- **Makefile** — 14 targets (install, dev, test, docker, lint, backup, clean)

### Celery
- **Beat schedule** — 4 tasks in `config.py`: crawl (30m), retry stuck (60m), newsletters (daily 8am), log cleanup (daily 3am)
- **FlaskTask pattern** — `celery_app.py` wraps tasks in Flask app context with proper session cleanup

### Frontend
- **Templates** — 37 Jinja2 templates with HTMX for dynamic admin/public UI
- **Static assets** — CSS, JS (theme toggle, HTMX vendored), SVG topic icons

### Documentation
- `docs/quickstart.md`, `docs/deployment.md`, `docs/configuration.md`

### Gaps
- **CI/CD** — No automated pipeline (no GitHub Actions, GitLab CI). `scripts/test.sh` and Makefile are ready but unconnected.
- **Observability** — Health checks only (`/health`, `/admin/api/health`). No APM/error tracking (Sentry, Datadog, etc.).

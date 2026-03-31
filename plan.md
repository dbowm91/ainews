# Consolidated Plan: ainews Codebase Improvements

## Overview

This plan consolidates all items from prior plan files (plan2–plan5) into a single prioritized roadmap. Items are organized into phases by priority, with parallelization guidance for sub-agent execution. Plan3 (plan3.md) contained no actionable items — all its findings were already covered by other plans.

**Verification status:** All items below have been verified against the codebase as of 2026-03-31.

**Implementation status:** Phases 1–6 complete (623 tests passing, 0 lint violations). Phase 7 (P3 backlog) items remain.

**Prerequisites for all phases:**
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Phase 1: Security Fixes (High Priority) [DONE]

These items address real security vulnerabilities. Implement first.

### 1.1 Stored XSS in Newsletter/Email HTML

**Files:** `services/newsletter.py:54-56`, `services/email.py:59,108,143`

**Problem:** Headlines, categories, and TL;DR text from LLM-generated `final_article` JSON are injected unescaped into HTML email templates. A headline like `<script>alert(1)</script>` would execute in email clients. Confirmed: no `html.escape()` calls exist in either file.

**Fix:**
1. In `services/newsletter.py`, add `import html`. Escape all text before embedding:
   ```python
   safe_headline = html.escape(headline)
   safe_category = html.escape(category)
   safe_tldr = html.escape(tldr)
   ```
2. In `services/email.py`, escape `newsletter_label` and `site_name` in both `send_verification_email()` and `send_welcome_email()`.
3. Add tests in `tests/test_newsletter_sanitize.py` for `<script>`, `<img onerror=...>`, and HTML entities.

---

### 1.2 `timeout.py` Does Not Abandon Stuck Functions

**Files:** `services/timeout.py:47`

**Problem:** The `with ThreadPoolExecutor(...)` context manager calls `shutdown(wait=True)` on exit, blocking indefinitely until the stuck thread finishes. This completely negates the timeout. Confirmed: line 47 uses context manager pattern.

**Fix:**
1. Replace the context manager with explicit `executor.shutdown(wait=False, cancel_futures=True)` in a `finally` block.
2. Update docstring to clarify the thread continues in background.
3. Add tests in `tests/test_timeout.py` (new file) — verify timeout returns promptly (wall-clock check).

---

### 1.3 Ollama Error Misclassification

**Files:** `services/llm/ollama.py:15-21`, `services/llm/errors.py:24-50`

**Problem:** `_handle_ollama_error()` passes `ResponseError` as both `rate_limit_exc` and `auth_exc`. The `isinstance(e, rate_limit_exc)` check runs first, so all `ResponseError`s become `RateLimitError`. Circuit breakers incorrectly open on auth errors. Confirmed: lines 15-21 show both mapped to `ResponseError`.

**Fix:**
1. Set `auth_exc=()` in `_handle_ollama_error()`. Ollama is self-hosted and doesn't distinguish auth errors.
2. The existing `hasattr(e, "status_code")` branch in `handle_provider_error()` will catch HTTP 401/403 if they occur.
3. Add tests in `tests/test_llm_adapters.py`.

---

### 1.4 `_import_class` Deserialization Risk

**Files:** `services/config_cache.py:54-60`

**Problem:** `_import_class()` calls `importlib.import_module()` with a dotted path from Redis data with no allowlist. If an attacker writes to Redis, they could trigger arbitrary module imports (e.g., `os.system`). Confirmed: no validation exists.

**Fix:**
1. Add an allowlist of permitted class paths (all schema classes used by the config cache).
2. Raise `ValueError` if the path is not in the allowlist.
3. Add tests: allowed paths work, disallowed paths raise `ValueError`, attacker paths like `os.system` are rejected.

---

## Phase 2: Correctness & Stability (Medium-High Priority) [DONE]

These items fix concurrency bugs and configuration issues. Many are independent and can be parallelized.

### 2.1 Lock Release Race Conditions

**Files:** `tasks/pipeline.py:530-532`, `tasks/crawl.py:119-122`, `tasks/newsletter.py:321-325`

**Problem:** Lock release uses check-then-delete (`redis.get` → `redis.delete`) which is not atomic. Between get and delete, another task could acquire the lock.

**Fix:**
1. Create `services/redis_utils.py` with an atomic `release_lock()` using a Lua script.
2. Replace check-then-delete in all three files.
3. Add tests for lock ownership, race conditions, and idempotent release.

---

### 2.2 `retry_stuck` Missing Distributed Lock

**Files:** `tasks/retry.py:14-74`

**Problem:** `retry_stuck` can run on multiple workers simultaneously. Two instances could re-dispatch the same article's stage.

**Fix:**
1. Add Redis-based lock (`SET NX EX`) at task start using `self.request.id` as lock value.
2. Use `release_lock()` from 2.1 in `finally` block.
3. Add tests: skips when locked, proceeds when unlocked, releases after completion.

---

### 2.3 Explicit `WTF_CSRF_ENABLED = True` in ProductionConfig

**Files:** `config.py:123`

**Problem:** CSRF protection relies on Flask-WTF's default (`True`). If the default ever changes, CSRF would be silently disabled. Confirmed: `ProductionConfig` does not set this explicitly.

**Fix:** Add `WTF_CSRF_ENABLED = True` to `ProductionConfig`. One-line change, no tests needed.

---

### 2.4 Unbounded Memory Growth in L1 Caches

**Files:** `services/cache.py:30`, `services/config_cache.py:67`, `services/metrics.py:31`

**Problem:**
- `ResponseCache._memory` and `ConfigCache._memory_cache` grow indefinitely — stale entries are lazily cleaned on `get()`, but never-accessed keys accumulate forever.
- `MetricsCollector._histograms` unique key count grows without bound (especially with labeled metrics).

**Fix:**
1. In `services/cache.py`, add `_evict_stale()` triggered on `set()` when dict exceeds threshold (e.g., 500 entries). Purge expired first, then drop oldest if still over limit.
2. Same pattern for `services/config_cache.py`.
3. In `services/metrics.py`, add `_MAX_HISTOGRAM_KEYS = 200` guard in `histogram_observe()`.
4. Add tests for bounded growth.

---

### 2.5 Pipeline Monitor Sequential Redis GETs

**Files:** `services/pipeline_monitor.py:74-111`

**Problem:** `get_stage_stats()` performs 2*N sequential Redis GETs (30 round trips for 15-min window). `get_all_stages_stats()` (7 stages) = 210 round trips. Confirmed: individual `redis.get()` calls in a loop.

**Fix:**
1. Collect all keys upfront, then use `redis.mget()` for a single round trip.
2. Update existing tests to mock `mget` instead of individual `get` calls.

---

### 2.6 Inconsistent Singleton Patterns

**Files:** `services/cache.py:128-137`, `services/config_cache.py:183-191`

**Problem:** `get_response_cache()` and `get_config_cache()` create singleton instances without thread synchronization. Confirmed: no `threading.Lock` in either file. Compare with `services/limiter.py` which correctly uses double-checked locking.

**Fix:** Add `threading.Lock` with double-checked locking to both, matching the pattern in `get_limiter()`.

---

### 2.7 Newsletter Pipeline Code Duplication

**Files:** `services/newsletter_pipeline.py:129-250`

**Problem:** Reader, writer, and editor stages follow an identical pattern (~120 lines duplicated): check enabled → get provider → acquire limiter → call LLM → release limiter → handle fallback.

**Fix:** Extract a `_run_pipeline_stage()` helper. Refactor all three stages to use it. Run existing `tests/test_newsletter_pipeline.py` to verify.

---

### 2.8 DNS Cache TTL vs Pipeline Delay

**Files:** `services/url.py:31`

**Problem:** DNS cache has 60s TTL. If pipeline congestion delays fetch > 60s after validation, a re-resolve could return a different (malicious) IP. Confirmed: `_DNS_CACHE_TTL = 60`.

**Fix:** Increase TTL to 300s (5 minutes) to cover typical pipeline delays. Update comment to explain rationale.

---

## Phase 3: Stability & Observability (Medium Priority) [DONE]

### 3.1 Missing Cascade Delete Rules

**Files:** `models.py`, `migrations/versions/` (new migration)

**Problem:** Deleting a Source doesn't cascade to Articles. Deleting an Article orphans Citations, ArticleMetrics, ArticleVersions, PipelineLogs, and article_tags entries.

**Fix:**
1. Create migration `011_cascade_deletes.py` to add `ondelete="CASCADE"` to all FK constraints.
2. Update `models.py` FK definitions to match.
3. Add cascade delete tests in `tests/test_models.py`.
4. Do this after other changes — migrations should be last to avoid conflicts.

---

### 3.2 Rate Limiter Slot Leak on Redis Failure

**Files:** `services/limiter.py:49-60`

**Problem:** If Redis is unavailable during `release()`, the concurrency slot is leaked until TTL expires. Current logging is `logger.warning`. Confirmed.

**Fix:** Upgrade to `logger.error` with `exc_info=True` and include recovery time estimate (TTL seconds). Keep existing `limiter.release_failure` counter.

---

### 3.3 `ModelLimiter.get_active()` Misleading on Errors

**Files:** `services/limiter.py:62-67`

**Problem:** Returns `0` when Redis is unavailable, indistinguishable from actually-zero active slots. Confirmed: return type is `int`, silently returns `0` on `RedisError`.

**Fix:** Return `Optional[int]` — `None` on Redis error. Update admin metrics endpoint to display "unknown" for `None`.

---

### 3.4 Cost Tracker Hardcoded 60/40 Ratio

**Files:** `services/cost_tracker.py`

**Problem:** Blended rate calculation assumes 60% input / 40% output tokens. Actual ratios vary by stage.

**Fix:** Add env var overrides (`COST_INPUT_RATIO`, `COST_OUTPUT_RATIO`) with sensible defaults.

---

### 3.5 Logging Format Inconsistency

**Files:** Various `services/` files

**Problem:** Some log calls use f-strings (`logger.error(f"Reader failed: {e}")`) while others use %-formatting. %-style is preferred for deferred string construction.

**Fix:** Mechanical conversion of f-string log calls to %-style across `services/`. Run ruff after.

---

### 3.6 Default Unsubscribe URL Placeholder

**Files:** `services/newsletter.py:13`

**Problem:** Default `unsubscribe_url` is `"{site_url}/unsubscribe/placeholder"`. If `site_url` is empty, produces a broken relative URL in email clients.

**Fix:** Change default to empty string. Add guard in footer: if URL is empty, show "unsubscribe link unavailable" instead of broken link.

---

## Phase 4: Observability & Monitoring (P1) [DONE]

### 4.1 Circuit Breaker State Change Metrics

**Files:** `services/circuit_breaker.py`

**Problem:** Circuit breaker tracks state internally but emits no metrics. Confirmed: zero references to `metrics`, `counter`, or `gauge` in the file. Operators cannot alert on provider failures or track recovery.

**Fix:**
1. Add `_on_state_change()` method that emits `circuit_breaker.state_change` counter with `provider`, `from`, `to` labels.
2. Emit `circuit_breaker.opened` counter on OPEN transitions.
3. Call from state transition methods. Wrap in try/except to avoid breaking circuit on metrics failure.
4. Add tests in `tests/test_circuit_breaker.py`.

---

### 4.2 Pipeline Stage Duration Histograms

**Files:** `services/pipeline_monitor.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`

**Problem:** Pipeline monitoring tracks success/failure counts but not stage duration. Cannot identify slow stages or track performance regression.

**Fix:**
1. Add `histogram_observe()` to `services/metrics.py` (if not already present from Phase 2.4).
2. Wrap pipeline stage logic with `perf_counter()` timing.
3. Emit `pipeline.stage_duration_seconds` with `stage` label.
4. Add tests in `tests/test_metrics.py`.

---

### 4.3 Dead Letter Queue Alerting

**Files:** `tasks/retry.py`, `routes/admin/api.py`

**Problem:** Dead letter queue grows silently. No alerting when stuck article count exceeds threshold.

**Fix:**
1. Add `pipeline.stuck_articles` gauge in `retry_stuck()`.
2. Log error when count exceeds configurable threshold (default 10).
3. Add admin API endpoint `GET /admin/api/pipeline/dead-letter/stats`.
4. Add tests in `tests/test_retry.py`.

---

## Phase 5: Performance (P2) [DONE]

### 5.1 FTS Search Optimization

**Files:** `services/article.py`, `routes/public.py`

**Problem:** FTS5 queries lack stemming, fuzzy matching, and result highlighting.

**Fix:**
1. Update FTS table creation to use `porter unicode61` tokenizer.
2. Create migration to rebuild FTS index.
3. Add search result highlighting in templates.
4. Add tests in `tests/test_fts.py` for stemming and ranking.

---

### 5.2 Connection Pool Monitoring

**Files:** `extensions.py`, `services/health.py`

**Problem:** No visibility into database connection pool utilization.

**Fix:** Add pool stats (size, checked_in, checked_out, overflow, invalid) to health endpoint. Add tests.

---

### 5.3 Redis Pipeline Batching

**Files:** `services/pipeline_monitor.py`, `services/config_cache.py`

**Problem:** Redis operations use individual calls for related operations.

**Fix:** Use Redis pipelines for batched operations in `record_stage_result()` and config cache multi-key ops.

---

## Phase 6: Operational Improvements (P2) [DONE]

### 6.1 Automated Backup Verification

**Files:** `scripts/backup.sh`, new `scripts/verify_backup.sh`

**Problem:** Backup script exists but no verification that backups are valid.

**Fix:** Create `verify_backup.sh` that checks file non-empty, SQLite integrity, and required tables. Call from backup script.

---

### 6.2 Health Check Graceful Degradation

**Files:** `services/health.py`, `routes/public.py`

**Problem:** Health check returns 503 if any dependency fails. A Redis outage (which only affects caching) causes the entire service to appear down to load balancers.

**Fix:**
1. Return "degraded" status for partial outages. Only return "unhealthy" when core functionality is broken (DB down).
2. Return 200 for healthy/degraded, 503 only for unhealthy.
3. Add tests for degraded state behavior.

---

### 6.3 Structured Logging for Pipeline Stages

**Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `logging_config.py`

**Problem:** Pipeline logging uses f-strings without structured fields. Difficult to parse for metrics/alerting.

**Fix:**
1. Add `StructuredLogger` with `pipeline_stage()` method outputting JSON with structured fields.
2. Update pipeline stages to use it.
3. Configure JSON output format for production.

---

### 6.4 Config Validation on Reload

**Files:** `routes/admin/api.py`, `services/config_unified.py`

**Problem:** Config reload clears cache but doesn't validate new config. Invalid config can cause runtime errors after reload.

**Fix:**
1. Add `validate_config()` returning `(is_valid, errors)`.
2. Call before clearing cache in reload endpoint. Return 400 with errors if invalid.
3. Add tests in `tests/test_config.py`.

---

## Phase 7: Code Quality & Features (P3 — Backlog) [NOT STARTED]

### 7.1 Type Hints for Public API

**Files:** `services/article.py`, `services/crawling.py`, `routes/public.py`, `routes/admin/api.py`

Add comprehensive type hints and return types to all public functions.

---

### 7.2 Docstrings for Complex Functions

**Files:** `tasks/pipeline.py`, `services/pipeline_monitor.py`, `services/circuit_breaker.py`

Add docstrings with Args, Returns, Raises sections to complex pipeline and service functions.

---

### 7.3 Article Duplicate Detection Enhancement

**Files:** `services/article.py`, `tasks/crawl.py`

Add content similarity detection (Jaccard similarity on title word sets) for articles from different sources or with different URLs.

---

### 7.4 Newsletter Send Retry

**Files:** `tasks/newsletter.py`, `services/email.py`

Add Celery retry logic for transient SMTP failures (`autoretry_for=(smtplib.SMTPException, TimeoutError)`).

---

### 7.5 Admin Bulk Operations Extension

**Files:** `routes/admin/api.py`

Add `reprocess` and `add_tags` actions to `bulk_article_operations()`.

---

## Parallelization Guide

Most items are independent and can be implemented concurrently by sub-agents. Use this grouping for maximum parallelization:

### Group A — Security (all independent, parallel)
- Agent 1: Phase 1.1 (XSS in newsletter/email)
- Agent 2: Phase 1.2 (timeout.py fix)
- Agent 3: Phase 1.3 (Ollama error classification)
- Agent 4: Phase 1.4 (_import_class allowlist)

### Group B — Correctness (parallel, no shared files)
- Agent 1: Phase 2.1 (atomic lock release) — **must finish before Group C**
- Agent 2: Phase 2.3 (WTF_CSRF_ENABLED) + Phase 2.8 (DNS cache TTL)
- Agent 3: Phase 2.4 (L1 cache bounds) + Phase 2.6 (singleton locking) — both touch `cache.py`, run together
- Agent 4: Phase 2.5 (pipeline monitor MGET)

### Group C — After Group B Agent 1 completes
- Agent 1: Phase 2.2 (retry_stuck lock) — depends on 2.1 `release_lock`
- Agent 2: Phase 2.7 (newsletter pipeline refactor)

### Group D — Stability (parallel, no shared files)
- Agent 1: Phase 3.2 + 3.3 (limiter.py logging + get_active)
- Agent 2: Phase 3.4 (cost tracker ratio) + Phase 3.6 (unsubscribe URL)
- Agent 3: Phase 3.5 (logging format — cross-file mechanical change)

### Group D2 — After all other groups complete
- Agent 1: Phase 3.1 (cascade deletes — migration risk, do last)

### Group E — Observability (all independent, parallel)
- Agent 1: Phase 4.1 (circuit breaker metrics)
- Agent 2: Phase 4.2 (pipeline duration histograms)
- Agent 3: Phase 4.3 (dead letter alerting)

### Group F — Performance & Operational (all independent, parallel)
- Agent 1: Phase 5.1 (FTS optimization)
- Agent 2: Phase 5.2 (connection pool) + Phase 6.2 (health degradation)
- Agent 3: Phase 5.3 (Redis pipeline batching)
- Agent 4: Phase 6.1 (backup verification) + Phase 6.4 (config validation)
- Agent 5: Phase 6.3 (structured logging)

### Group G — Backlog (no time pressure, parallel)
- Agents can pick any items from Phase 7 independently.

---

## Dependency Map

```
2.1 (release_lock) ──→ 2.2 (retry_stuck lock)
2.4 (metrics histogram_observe) ──→ 4.2 (pipeline duration)
Everything else ──→ independent
```

All other items have no cross-dependencies. The only hard ordering constraints are:
1. Phase 2.1 must complete before Phase 2.2 (2.2 imports `release_lock` from 2.1)
2. Phase 3.1 (migration) should be done last to avoid migration conflicts with other schema changes

---

## Verification

After each phase:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

After all phases:
- [ ] Full test suite passes (577+ tests)
- [ ] No ruff violations
- [ ] Migration upgrade/downgrade tested (Phase 3.1)
- [ ] Load test for performance items (Phase 5)
- [ ] Staging deployment verification

---

## Rollback

All items are individually revertable:

- **Security items (Phase 1):** Revert specific escaping/parsing changes. Risk: vulnerability returns.
- **Concurrency items (Phase 2.1-2.2):** Revert to check-then-delete. Risk: rare race condition.
- **Config items (Phase 2.3):** Remove explicit setting. Risk: implicit default reliance.
- **Cache items (Phase 2.4, 2.6):** Remove eviction/locking. Risk: memory growth / race condition.
- **Migration item (Phase 3.1):** Flask-Migrate downgrade. Risk: orphaned records remain.
- **Observability items (Phase 4):** Remove metric calls. No functional impact.
- **All P3 items (Phase 7):** Purely additive, safe to revert.

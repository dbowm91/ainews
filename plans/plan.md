# Implementation Plan — Consolidated

**Created:** April 22, 2026
**Status:** CLOSED (Waves 1-6 complete)
**Consolidated from:** plan.md, plan2.md, plan3.md, plan4.md, plan5.md

---

## Executive Summary

AINews is a well-architected AI-powered news aggregation platform. The codebase demonstrates strong engineering discipline: 847 tests pass, ruff passes for F/E/W codes, Docker Compose deployment is production-ready, and the multi-stage LLM pipeline is thoughtfully designed.

**Overall Grade: B+**

The codebase has solid foundations. Identified issues fall into three categories:
- **High**: Security vulnerabilities requiring immediate attention (3 items)
- **Medium**: Performance improvements and security enhancements (13 items)
- **Low**: Code quality and informational items (6 items)

**Already Verified as Implemented** (no action needed):
- Duplicate title detection with SQL pre-filtering (`services/article.py:289-294`)
- RSS feed caching via `ResponseCache` with 600s TTL (`routes/public/feeds.py`)
- Tag cloud caching via `ConfigCache` with 10-minute TTL
- Pipeline monitor using `mget` for batch retrieval
- SSRF prevention via `validate_url_safe()` and DNS caching
- OpenTelemetry helpers (`get_tracer()`, `traced_llm_call()`, `traced_stage()`)
- Structured logging (`PipelineLogger`, `log_pipeline_event()`, `log_duration()`)
- Pipeline duration histograms for select, research, write, edit stages
- API response format consistency (all routes follow `{"error"}`/`{"message"}` convention)
- Celery app cache clearing on config reload
- CSS token consistency between `critical.css` and `variables.css`
- Session fixation prevention documented in AGENTS.md
- `raise last_exc` guards verified safe in `services/llm/base.py` and `services/degradation.py`

---

## Deferred Items

| Item | Source | Reason |
|------|--------|--------|
| E.2: Celery Task Event Streaming | plan.md | Requires significant infrastructure work (celery.events.RealabilityMonitor or pubsub consumer, Redis streaming, MetricsCollector updates) |
| E.1: Celery Task Input Schema Validation | plan4.md | Add Pydantic schemas for task entry points — larger refactor |
| E.2: Structured Tool Result Format | plan4.md | Refactor tool results from raw strings to JSON — makes injection harder |
| E.3: Celery Worker Network Isolation | plan4.md | Run workers on isolated network segment |
| 2.6: Dashboard Event-Based Invalidation | plan5.md | Requires identifying all article state transitions |
| 1.1: CI/CD Pipeline | plan5.md | Requires project to be hosted on platform with GitHub Actions or equivalent |
| 6.2: EXPLAIN ANALYZE Script | plan5.md | Low priority, informational |

---

## Implementation Waves

### Wave 1: Quick Security Fixes
*Can be implemented in parallel by separate agents.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 1.1 | **DNS Cache TTL: Reduce from 300s to 60s** — Prevents DNS rebinding between validation and fetch | plan4.md A.3 | `services/url.py:38` | Low |
| 1.2 | **Session Fixation: Add `session.regenerate_id()`** — Prevents session hijacking after login | plan4.md B.1 | `routes/admin/auth.py:56-57` | Low |
| 1.3 | **Subagent Chain Escaping: Add `_escape_prompt_data()` to `run_subagent_chain()`** — Prevents XML injection from LLM output | plan4.md A.2 | `services/subagent.py:748` | Low |
| 1.4 | **Token Validation: Add `validate_token()` to unsubscribe/verify** — Prevents malformed token exploits | plan4.md B.7 | `routes/public/subscribe.py:129,143,171` | Low |
| 1.5 | **Tool Result Sanitization: Apply `esc_xml_text()` to LLM tool results** — Prevents instruction injection via tool output | plan4.md B.6 | `services/llm/base.py:338` | Low |
| 1.6 | **short_id Validation: Add regex validation to path parameter** — Prevents malformed ID exploits | plan4.md C.4 | `routes/public/links.py:74,81` | Low |
| 1.7 | **Failed Login Audit: Add logging to failure path** — Improves accountability for brute force | plan4.md C.1 | `routes/admin/auth.py` | Low |

**Wave 1 Verification:**
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
.venv/bin/python -m pytest tests/test_subagent.py -x -v
.venv/bin/python -m pytest tests/test_admin_api.py -x -v
.venv/bin/python -m pytest tests/test_url_ssrf.py -x -v
```

---

### Wave 2: Webhook & CSRF Fixes
*Can be implemented in parallel with Wave 1.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 2.1 | **Webhook CSRF: Add `@validate_csrf_json` to PUT/DELETE endpoints** — Prevents CSRF attacks on webhook config | plan4.md B.2 | `routes/admin/api/webhooks.py:150,187` | Low |
| 2.2 | **HTMX CSRF Pattern: Use `hx-headers` instead of `hx-vals` for CSRF tokens** — Fixes HTMX requests to JSON endpoints | plan4.md C.5 | `templates/admin/dead_letters.html:133`, `templates/admin/partials/share_row.html:14`, `templates/admin/partials/articles_table.html:61`, `templates/admin/article_versions.html:46`, `templates/admin/partials/review_table.html:33,41` | Low |

**Wave 2 Verification:**
```bash
# Test HTMX requests to JSON endpoints
# Test webhook PUT/DELETE without X-CSRFToken header
```

---

### Wave 3: Search Provider SSRF Validation
*Can be implemented in parallel with Wave 1 & 2.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 3.1 | **Search Provider SSRF: Add `validate_url_safe()` before HTTP requests** — Prevents SSRF via search provider config | plan4.md B.3 | `services/search/searxng.py:34-38`, `services/search/google.py:36-44` | Low |

**Wave 3 Verification:**
```bash
.venv/bin/python -m pytest tests/test_search.py -x -v
```

---

### Wave 4: Larger Security Infrastructure
*Requires more planning. Can run in parallel with Wave 5.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 4.1 | **Celery Task HMAC Signing: Add task authentication** — Prevents unauthorized task execution if broker is compromised | plan4.md A.1 | `tasks/*.py` (entry points), new `services/task_security.py` | High |
| 4.2 | **Redis AUTH: Add password authentication** — Prevents unauthorized Redis access | plan4.md B.4 | `extensions.py:68-94` | Medium |
| 4.3 | **Webhook Replay Protection: Add timestamp to signature** — Prevents infinite replay of intercepted webhooks | plan4.md B.5 | `services/webhooks.py:21-27` | Medium |

**Wave 4 Implementation Details:**

**A.1 Celery Task HMAC Signing:**
```python
# services/task_security.py
import hmac
import hashlib

def sign_task(task_name: str, args: tuple, kwargs: dict, secret: str) -> str:
    payload = f"{task_name}:{args}:{sorted(kwargs.items())}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def verify_task(task_name: str, args: tuple, kwargs: dict, signature: str, secret: str) -> bool:
    expected = sign_task(task_name, args, kwargs, secret)
    return hmac.compare_digest(expected, signature)
```

Apply to all public-facing tasks: `crawl_source`, `process_item`, `retry_article`, `send_single_email`, etc.

**B.5 Webhook Timestamp Signature:**
```python
def _sign_payload(payload: str, secret: str, timestamp: int) -> str:
    data = f"{timestamp}:{payload}"
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()

def _verify_timestamp(timestamp: int, max_age_seconds: int = 300) -> bool:
    import time
    return abs(time.time() - timestamp) <= max_age_seconds
```

**Wave 4 Verification:**
```bash
# Test unsigned tasks are rejected
# Test Redis connection with password
# Test old webhooks (beyond 5min window) are rejected
```

---

### Wave 5: Performance Improvements
*Can be implemented in parallel with Wave 4.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 5.1 | **ResponseCache L1 Read Eviction: Add sampled stale eviction on read path** — Prevents stale entry accumulation under high read volume | plan3.md A.3, plan5.md 2.2 | `services/cache.py:64-92` | Low |
| 5.2 | **ConfigCache L1 Eviction: Add time-based stale eviction** — Prevents stale config entries persisting indefinitely | plan3.md B.3, plan5.md 2.3 | `services/config_cache.py:84-94` | Low |
| 5.3 | **Related Articles SQL Scoring: Push tag matching to SQL** — Reduces O(n) Python scoring | plan3.md A.1 | `services/related.py:10-58` | Medium |
| 5.4 | **Newsletter Streaming: Don't materialize full subscriber list** — Reduces memory usage during large newsletter sends | plan3.md A.4, plan5.md 2.5 | `tasks/newsletter.py:187` | Medium |
| 5.5 | **Search Query Async Logging: Use Celery task for fire-and-forget** — Reduces request latency | plan3.md B.4 | `services/article.py:27-36` | Low |
| 5.6 | **Sitemap Pagination: Make limit configurable** — Safer for large sites | plan3.md B.5 | `routes/public/feeds.py:281-292` | Low |
| 5.7 | **created_at Index: Add database index for duplicate detection** — Improves query performance as article volume grows | plan5.md 6.1 | New migration | Low |

**Wave 5 Implementation Details:**

**5.1 ResponseCache L1 (Sampled Eviction):**
```python
_ACCESSES_BEFORE_EVICT = 100

def get(self, key: str) -> Any | None:
    # ... existing L1 check ...
    self._evict_sample_counter += 1
    if self._evict_sample_counter >= _ACCESSES_BEFORE_EVICT:
        self._evict_stale()
        self._evict_sample_counter = 0
```

**5.2 ConfigCache L1 (Time-Based Eviction):**
```python
def _evict_stale(self) -> None:
    now = time.monotonic()
    expired = [k for k, (exp, _) in self._memory.items() if now >= exp]
    for k in expired:
        del self._memory[k]
    # Also call this on get() after the fast-path check
```

**5.3 Related Articles SQL Scoring:**
```python
tag_count_subq = (
    db.session.query(
        article_tags.c.article_id,
        db.func.count(article_tags.c.tag_id).label("tag_count")
    )
    .group_by(article_tags.c.article_id)
    .subquery()
)
# Build candidate query with joined tag count and topic match score in SQL
```

**5.4 Newsletter Streaming:**
```python
# Instead of building subscriber_list, iterate directly:
subscriber_count = subscriber_query.count()
for i, sub in enumerate(subscriber_query.yield_per(500)):
    # dispatch batch when reaching BATCH_SIZE
    pass  # track sent count in-memory
```

**Wave 5 Verification:**
```bash
.venv/bin/python -m pytest tests/test_cache.py -x -v
.venv/bin/python -m pytest tests/test_related.py -x -v
.venv/bin/python -m pytest tests/test_newsletter.py -x -v
.venv/bin/python -m pytest tests/test_article.py -x -v
# Memory profiling: verify RSS resident memory stays flat during large newsletter sends
```

---

### Wave 6: Infrastructure & Code Quality
*Can be implemented in parallel with Wave 4 & 5.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 6.1 | **CI/CD Pipeline: Add GitHub Actions workflow** — Automates lint and test on push/PR | plan5.md 1.1 | `.github/workflows/ci.yml` (new) | Medium |
| 6.2 | **Deployment Runbook: Document operational procedures** — Covers rollback, monitoring, dead letter handling | plan5.md 1.2 | `docs/runbook.md` (new) | Medium |
| 6.3 | **E501 Line Length: Fix 163 violations** — Tier approach: auto-fix, targeted suppressions, structural changes | plan2.md A | Multiple | Medium |
| 6.4 | **Email Config Error Handling: Distinguish config vs network errors** — Prevents masking real issues | plan5.md 4.1 | `services/email.py:28-35` | Low |
| 6.5 | **Test Coverage: Verify performance items have tests** — Ensure sampled eviction works | plan5.md 9.1 | `tests/test_cache.py` | Low |

**Wave 6 Implementation Details:**

**6.3 E501 Line Length Approach:**
1. Run `ruff check . --exclude .venv --fix` and capture remaining violations
2. For LLM prompt strings / HTML: Add `# noqa: E501` at file or function level
3. For SQLAlchemy column definitions: Consider breaking into multiple lines
4. For User-Agent strings: Suppress at the list level

```bash
# Before: 163 violations
ruff check . --exclude .venv --select=E501 | wc -l

# After fix:
ruff check . --exclude .venv --select=E501
# Should return zero
```

---

### Wave 7: Follow-up Security & Webhook Improvements
*Can be implemented in parallel.*

| Order | Item | Source | Files | Effort |
|-------|------|--------|-------|--------|
| 7.1 | **Webhook trigger_event Integration: Call from pipeline stages** — Enables automated webhook delivery on article publish, newsletter sent | plan4.md C.2 | `services/webhooks.py:173-197`, pipeline stages | Medium |
| 7.2 | **ModelLimiter SoftTimeout Handler: Release slots on soft timeout** — Prevents slot leaks until TTL expires | plan4.md C.3 | `services/limiter.py` | Low |
| 7.3 | **Webhook Secret Encryption: Encrypt at rest** — Protects secrets if DB is compromised | plan4.md C.6 | `models.py:411`, `services/webhooks.py` | Medium |
| 7.4 | **Webhook Idempotency Key: Add deduplication** — Prevents duplicate deliveries on retry | plan4.md C.7 | `models.py:429-444`, `services/webhooks.py` | Medium |
| 7.5 | **Category CSS Escaping: Add `|e` filter** — Prevents CSS class injection | plan4.md D.1 | `templates/partials/condensed_article.html:11` | Low |
| 7.6 | **Webhook Attempt Tracking: Store actual attempt number** — Improves debugging | plan4.md D.2 | `services/webhooks.py:150`, `models.py:440` | Low |
| 7.7 | **Bulk Audit Logging: Add logging for all bulk operations** — Improves accountability | plan4.md D.4 | `routes/admin/api/articles.py` | Low |
| 7.8 | **Config Cache API Key Isolation: Use separate Redis DB** — Reduces blast radius on Redis compromise | plan4.md D.5 | `services/config_cache.py` | Medium |

**Wave 7 Verification:**
```bash
# Test webhook fires on article publish
# Test soft timeout behavior and verify slot cleanup
# Test retry behavior with duplicate detection
```

---

## Critical Implementation Notes

### Thread Safety
- `ResponseCache` and `ConfigCache` both use `threading.Lock` for `_memory` access
- `ThreadPoolExecutor` instances are thread-safe for `submit()`/`result()`
- Executor shutdown not needed on module reload

### Redis Error Handling
- All Redis operations catch `redis.exceptions.RedisError` (not bare `Exception`)
- `ModelLimiter` fails closed on Redis errors — intentional behavior
- Webhook event queue uses separate Redis DB or key prefix to avoid collisions

### Celery Task Patterns
- All long-running tasks should have both `soft_time_limit` and `time_limit`
- Use `autoretry_for` / `retry_backoff` decorators instead of manual `self.retry()`
- Tasks that touch database should commit in try/except with rollback on failure
- Re-raise after logging when the exception should trigger Celery retry
- Task signature changes require worker restart to pick up new code

### Template Escaping
- All user-controlled data in templates should use `|e` filter
- Database fields populated from external sources (RSS feeds, LLM output) are NOT exempt
- Compromised feed sources could inject malicious content via these fields

### LLM Input Validation
- Treat LLM responses as untrusted input
- Parse JSON with error handling
- Validate structure before use
- Never pass unsanitized LLM output to system calls or dangerous functions

### Metrics Naming
Follow Prometheus naming conventions:
- Counters: `ainews_<subsystem>_<name>_total`
- Gauges: `ainews_<subsystem>_<name>`
- Histograms: `ainews_<subsystem>_<name>_seconds`

### Session Security
- `session.regenerate_id()` must be called AFTER `session.clear()` but BEFORE setting any session data
- CSRF tokens stored by Flask-WTF are in a separate signed cookie, not affected by `session.clear()`

### Webhooks
- Timestamp-based replay protection requires consumer-side verification
- Encrypted secrets at rest require key rotation planning

### SSRF
- Reducing DNS cache TTL improves security but increases DNS lookup frequency
- Search provider validation adds overhead on every search call

---

## Database Notes

- SQLite WAL mode configured in `app.py:153-159`
- All new SQL filters must be verified with `EXPLAIN` to confirm index usage
- Cascade rules enforced at SQLAlchemy model level (SQLite doesn't support ALTER TABLE for FK)
- Test Jaccard similarity threshold with real article titles after pre-filtering changes

---

## Rollback Plan

If any change causes issues:
1. Revert the specific file change: `git checkout -- <file>`
2. Run tests to confirm restoration
3. Re-analyze before re-applying
4. For model changes, generate downgrade migration
5. Clear relevant Redis keys (config cache, locks): `ainews:cache:*`, `ainews:llm:*`
6. For Celery task changes, ensure workers pick up changes (may need restart)
7. For template changes, clear any template cache
8. For env var changes, remove new env vars (CELERY_TASK_SECRET, REDIS_PASSWORD, etc.)

---

## Verification Commands

```bash
# Full lint check (F/E/W codes)
.venv/bin/ruff check . --exclude .venv

# Line length only (before: 163 violations)
.venv/bin/ruff check . --exclude .venv --select=E501

# Tests (847 tests)
.venv/bin/python -m pytest tests/ -x -q

# Combined pre-commit style
.venv/bin/ruff check . --exclude .venv && .venv/bin/python -m pytest tests/ -x -q

# Security-specific tests
.venv/bin/python -m pytest tests/test_url_ssrf.py -x -v
.venv/bin/python -m pytest tests/test_subagent.py -x -v
.venv/bin/python -m pytest tests/test_admin_api.py -x -v
.venv/bin/python -m pytest tests/test_llm_adapters/ -x -v

# Performance-specific tests
.venv/bin/python -m pytest tests/test_cache.py -x -v
.venv/bin/python -m pytest tests/test_related.py -x -v
.venv/bin/python -m pytest tests/test_newsletter.py -x -v
.venv/bin/python -m pytest tests/test_article.py -x -v
.venv/bin/python -m pytest tests/test_search.py -x -v
```

---

## Key Test Files by Area

| Area | Test File |
|------|-----------|
| DNS/URL validation | `tests/test_url_ssrf.py` |
| Subagent | `tests/test_subagent.py` |
| Cleanup tasks | `tests/test_cleanup.py` |
| LLM adapters | `tests/test_llm_adapters/` |
| Admin API | `tests/test_admin_api.py` |
| Search/FTS | `tests/test_search.py`, `tests/test_fts.py` |
| Cache | `tests/test_cache.py` |
| Related articles | `tests/test_related.py` |
| Newsletter | `tests/test_newsletter.py` |
| Article | `tests/test_article.py` |
| Public routes | `tests/test_public.py` |

---

## References

- **plan.md** — Performance, Observability & Security (deferred items, implementation notes)
- **plan2.md** — Code Quality Improvements (E501 violations, CSS tokens, test coverage)
- **plan3.md** — Performance Improvements (database scoring, cache eviction, streaming)
- **plan4.md** — Security Improvements (HMAC signing, CSRF, SSRF, webhooks, session security)
- **plan5.md** — General Review & Improvement Recommendations (CI, runbook, error handling)

---

## Implementation Order Summary

| Wave | Items | Priority | Parallelizable |
|------|-------|----------|----------------|
| 1 | 1.1-1.7 (Quick security fixes) | Critical | Yes |
| 2 | 2.1-2.2 (Webhook/CSRF) | High | Yes (with Wave 1) |
| 3 | 3.1 (Search SSRF) | High | Yes (with Wave 1&2) |
| 4 | 4.1-4.3 (Larger security) | High | Yes (with Wave 5) |
| 5 | 5.1-5.7 (Performance) | Medium | Yes (with Wave 4) |
| 6 | 6.1-6.5 (Infrastructure) | Medium | Yes (with Wave 4&5) |
| 7 | 7.1-7.8 (Follow-up) | Medium/Low | Yes |

---

*End of consolidated plan*

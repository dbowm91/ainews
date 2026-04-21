# Implementation Plan — Performance, Observability & Security

## Summary

This plan consolidates pending improvements from previous planning sessions. All items from Waves 1-8 (plan.md root) have been completed. This plan covers Performance (from plan2.md), Observability & Resilience (from plan3.md), and Security (from plan4.md).

**Created:** April 21, 2026
**Status:** COMPLETED (April 21, 2026) - All waves completed

---

## Plan Relationship

| Plan | Focus | Status |
|------|-------|--------|
| plan.md (root) | Security, code quality, LLM, performance, UI/UX (Waves 1-8) | COMPLETED |
| **THIS PLAN** | Performance, Observability, LLM Resilience, Security | PENDING |

---

## Wave Overview

| Wave | Focus | Items | Effort |
|------|-------|-------|--------|
| **Wave A** | ThreadPool & Cache Performance | A.1-A.3 | Low-Medium |
| **Wave B** | Database & Query Performance | B.1-B.3 | Medium |
| **Wave C** | Celery Task Security & Resilience | C.1-C.5 | Low-Medium |
| **Wave D** | XSS Prevention | D.1-D.3 | Low |
| **Wave E** | LLM Resilience & Observability | E.1-E.3 | Medium |
| **Wave F** | SLA Tracking & Analytics | F.1-F.3 | Medium |
| **Wave G** | Optional Hardening | G.1 | Low |

---

## Wave A: ThreadPool & Cache Performance

### A.1: Shared ThreadPoolExecutor for DNS Resolution

**Location:** `services/url.py:139-148`

**Problem:**
Every DNS lookup creates a new `ThreadPoolExecutor(max_workers=1)`, executes the lookup, then destroys the executor. Under concurrent URL validation load, this creates and tears down many threads unnecessarily.

```python
def _resolve_and_check(hostname: str) -> list[str]:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(socket.getaddrinfo, hostname, None)
        addr_infos = future.result(timeout=_DNS_RESOLVE_TIMEOUT)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
```

**Impact:** Thread creation/destruction overhead under concurrent URL validation.

**Fix:**
Create a module-level shared `ThreadPoolExecutor` with a small pool (4 workers) for DNS lookups.

**Implementation:**
1. Add module-level executor: `_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")`
2. Replace the per-call executor pattern with `submit` to the shared pool
3. Use `shutdown(wait=False, cancel_futures=True)` on module cleanup if needed (optional, executors clean up on process exit)

**Files affected:** `services/url.py`

---

### A.2: Shared ThreadPoolExecutor for Subagent Calls

**Location:** `services/subagent.py:417,588`

**Problem:**
Both `run_subagent()` and `run_subagent_with_tools()` create a new `ThreadPoolExecutor(max_workers=1)` for every LLM call to enforce the timeout. This creates thread overhead on every subagent invocation.

```python
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(_call_with_timeout)
    result = future.result(timeout=stage_config.timeout_seconds)
```

**Impact:** Thread creation overhead on every subagent pipeline stage (potentially 2+ per article: research + edit).

**Fix:**
Create a shared `ThreadPoolExecutor` for subagent calls at module level. Since each call needs its own timeout, use `future.result(timeout=timeout)` to enforce per-call timeouts against the shared executor.

**Implementation:**
1. Add module-level executor: `_subagent_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="subagent")`
2. Replace per-call `ThreadPoolExecutor(max_workers=1)` with submit to shared executor
3. Keep `future.result(timeout=stage_config.timeout_seconds)` for per-call timeout enforcement

**Files affected:** `services/subagent.py`

---

### A.3: O(1) LRU Cache Eviction

**Location:** `services/cache.py:105`, `services/url.py:78`

**Problem:**
Both caches use `min()` with a key function to find the oldest/LRU entry when at capacity:

```python
# services/cache.py:104-106
lru_key = min(self._memory, key=lambda k: self._memory[k][1])
del self._memory[lru_key]

# services/url.py:76-79
oldest = min(self._store, key=lambda k: self._store[k][0])
del self._store[oldest]
```

This is O(n) on every cache write when the cache is full (n=1000 for L1, n=1024 for DNS cache).

**Impact:** Slowdown on cache writes as size grows.

**Fix:**
Use `collections.OrderedDict` which provides O(1) `move_to_end()` for LRU updates and O(1) `popitem(last=False)` for FIFO/LRU eviction.

For `ResponseCache`:
- On access (cache hit): `move_to_end()` on the key
- On eviction: `popitem(last=False)` for LRU (oldest by insertion order)

For `_TTLCache` (DNS cache):
- Use `popitem(last=False)` instead of `min()` scan

**Implementation:**
1. `ResponseCache`: Change `_memory` from `dict` to `OrderedDict`. On hit, call `move_to_end()`. On eviction, call `popitem(last=False)`.
2. `_TTLCache`: Change `_store` from `dict` to `OrderedDict`. On eviction, call `popitem(last=False)`.

**Files affected:** `services/cache.py`, `services/url.py`

**Note:** `ResponseCache` uses `time.monotonic()` for access_time tracking. After changing to `OrderedDict`, the eviction changes from true LRU (least recently accessed) to FIFO (oldest by insertion order). The performance benefit of O(1) eviction outweighs the minor behavioral difference.

---

## Wave B: Database & Query Performance

### B.1: Missing Eager Loading in Article Detail Route

**Location:** `routes/public/links.py:35`

**Problem:**
```python
article = Article.query.options(joinedload(Article.tags)).get_or_404(article_id)
```

`Article.source` is not eagerly loaded. The `article_card.html` template accesses `article.source.name`, confirming source access patterns exist.

**Impact:** 1 additional query per article view if `article.source` is accessed.

**Fix:**
Add `joinedload(Article.source)` alongside the existing `joinedload(Article.tags)`:

```python
article = Article.query.options(
    joinedload(Article.tags),
    joinedload(Article.source)
).get_or_404(article_id)
```

**Files affected:** `routes/public/links.py`

---

### B.2: Large Batch Deletes Without Chunking

**Location:** `tasks/cleanup.py:24` and `tasks/cleanup.py:145`

**Problem:**
Both `cleanup_old_pipeline_logs` and `cleanup_old_article_versions` perform unbounded deletes. Could delete millions of rows in a single transaction.

**Impact:** Long-held locks, potential OOM on large deletes, soft time limit exceeded.

**Fix:**
Chunk the deletes into batches of 10,000 rows with periodic commits:

```python
BATCH_SIZE = 10000
total_deleted = 0
while True:
    deleted = (
        PipelineLog.query
        .filter(PipelineLog.created_at < cutoff)
        .limit(BATCH_SIZE)
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        break
    total_deleted += deleted
    db.session.commit()
logger.info("Cleaned up %s pipeline logs older than 30 days", total_deleted)
```

Apply the same pattern to `cleanup_old_article_versions`.

**Files affected:** `tasks/cleanup.py`

---

### B.3: Dashboard Cache Stores Model Instances

**Location:** `routes/admin/dashboard.py:167-178`

**Problem:**
The cache stores live SQLAlchemy model instances which may not be pickle-compatible across code changes and keeps DB connection alive during cache lifetime.

**Impact:** Cache invalidation issues, potential memory bloat, pickle compatibility across deploys.

**Fix:**
Serialize to plain dicts before caching:

```python
cache_data = {
    "sources": [{"id": s.id, "name": s.name, "active": s.active} for s in sources],
    "recent": [
        {
            "id": a.id,
            "title": a.original_title,
            "pipeline_status": a.pipeline_status,
            "source_name": a.source.name if a.source else None,
        }
        for a in recent
    ],
}
```

**Files affected:** `routes/admin/dashboard.py`

---

## Wave C: Celery Task Security & Resilience

### C.1: Celery Task Missing Timeout

**Location:** `tasks/crawl.py:190-191`

**Problem:**
```python
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def aggregate_crawl_results(self, results: list, run_id: int) -> dict:
```

No `soft_time_limit` or `time_limit`. If the task hangs or processes a very large results list, it could run indefinitely.

**Impact:** DoS risk — task can run forever consuming worker resources.

**Fix:**
```python
@shared_task(bind=True, max_retries=3, default_retry_delay=30, soft_time_limit=120, time_limit=180)
def aggregate_crawl_results(self, results: list, run_id: int) -> dict:
```

**Files affected:** `tasks/crawl.py`

---

### C.2: Silent Exception Swallowing Breaks Celery Retry

**Location:** `tasks/extract.py:266`

**Problem:**
```python
except Exception:
    article.pipeline_status = "failed"
    article.last_error = "Failed to dispatch to pipeline"
    db.session.commit()
    logger.error("Failed to dispatch select_article for article %s", article.id)
```

Sets article to `failed` status but does NOT re-raise. Per AGENTS.md guidance, this prevents Celery's built-in retry mechanism from triggering.

**Impact:** Articles fail permanently on transient errors instead of retrying.

**Fix:**
Re-raise the exception after logging and updating the article status:

```python
except Exception as e:
    article.pipeline_status = "failed"
    article.last_error = "Failed to dispatch to pipeline"
    db.session.commit()
    logger.error("Failed to dispatch select_article for article %s: %s", article.id, e)
    raise
```

**Files affected:** `tasks/extract.py`

---

### C.3: LLM Tool Call Arguments Parsed Without Validation

**Location:** `services/llm/base.py:269-273`, `services/llm/openai.py:167-169`, `services/llm/ollama.py:146`

**Problem:**
LLM tool call arguments are parsed from JSON strings without error handling:

```python
fn_args = json.loads(tc.arguments)  # base.py:273
fn_args = json.loads(tc.function.arguments)  # openai.py:169
fn_args = json.loads(fn.get("arguments", "{}"))  # ollama.py:146
```

Malformed JSON or unexpected structure could cause errors.

**Impact:** Potential for unexpected behavior if LLM returns malformed arguments.

**Fix:**
Add defensive JSON parsing with error handling:

```python
def _parse_tool_arguments(arguments: str, expected_fields: list[str]) -> dict:
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    if not isinstance(args, dict):
        return {}
    return {k: v for k, v in args.items() if k in expected_fields}
```

**Files affected:** `services/llm/base.py`, `services/llm/openai.py`, `services/llm/ollama.py`

---

### C.4: Silent Audit Logging Failures

**Location:** `routes/admin/auth.py:58,76`

**Problem:**
```python
try:
    log_admin_action("admin_login", user="admin")
except Exception:
    pass
```

Admin login audit failures are silently swallowed.

**Impact:** Security monitoring gap — failed audit logging could hide malicious activity.

**Fix:**
Log the failure instead of silently swallowing:

```python
try:
    log_admin_action("admin_login", user="admin")
except Exception as e:
    logger.error("Failed to log admin login action: %s", e)
```

Apply same pattern to both locations (line 58 and line 76).

**Files affected:** `routes/admin/auth.py`

---

### C.5: Silent Cache Invalidation Failures

**Location:** `routes/admin/articles.py:285`, `routes/admin/review.py:87`

**Problem:**
```python
try:
    cache.invalidate_prefix("index")
    cache.invalidate_prefix("topic")
except Exception:
    pass
```

Cache invalidation failures are silently ignored.

**Impact:** Users see stale content; cache invalidation failures are invisible to operators.

**Fix:**
Log the failure:

```python
try:
    cache.invalidate_prefix("index")
    cache.invalidate_prefix("topic")
except Exception as e:
    logger.warning("Failed to invalidate article cache: %s", e)
```

**Files affected:** `routes/admin/articles.py`, `routes/admin/review.py`

---

## Wave D: XSS Prevention

### D.1: XSS in Admin Templates (Source Name and Error)

**Location:** `templates/admin/partials/source_row.html:3,26`

**Problem:**
```html
<strong>{{ s.name }}</strong>
<small title="{{ s.last_error }}" class="text-muted">{{ s.last_error[:80] }}...</small>
```

Source name and last error are not escaped. RSS feed content (which populates these fields) could contain malicious scripts if a feed source is compromised.

**Impact:** Stored XSS if attacker controls feed source content.

**Fix:**
Add `|e` filter:

```html
<strong>{{ s.name | e }}</strong>
<small title="{{ s.last_error | e }}" class="text-muted">{{ s.last_error[:80] | e }}...</small>
```

**Files affected:** `templates/admin/partials/source_row.html`

---

### D.2: XSS in Article Templates (Author Field)

**Location:** `templates/partials/article_card.html:46`, `templates/partials/condensed_article.html:16`

**Problem:**
Both templates render `article.original_author` without escaping:

```html
<span class="card-author">{{ article.original_author }}</span>
<span class="meta-author">{{ article.original_author }}</span>
```

**Fix:**
Add `|e` filter to both locations:

```html
<span class="card-author">{{ article.original_author | e }}</span>
<span class="meta-author">{{ article.original_author | e }}</span>
```

**Files affected:** `templates/partials/article_card.html`, `templates/partials/condensed_article.html`

---

### D.3: Template Attribute Injection

**Location:** `templates/admin/topic_notes.html:27,33`

**Problem:**
```html
value="{{ topic }}"
value="{{ source }}"
```

Unescaped values in HTML attributes could allow attribute injection.

**Fix:**
Use `|e` filter:

```html
value="{{ topic | e }}"
value="{{ source | e }}"
```

Note: Line 69 already has `value="{{ topic|e }}"` which is correct.

**Files affected:** `templates/admin/topic_notes.html`

---

## Wave E: LLM Resilience & Observability

### E.1: LLM Retry with Exponential Backoff

**Location:** `services/llm/base.py`

**Problem:**
LLM calls that fail with transient errors (rate limits, timeouts, 5xx errors) are not retried at the provider level. The circuit breaker opens after repeated failures, but there's no automatic retry with backoff.

**Impact:** Unnecessary circuit breaker opens for transient failures; higher latency for users on recoverable errors.

**Fix:**
1. Add `with_retry(max_retries=3, base_delay=1.0, max_delay=30.0)` wrapper to `BaseLLMProvider`
2. Retry on: `ProviderTimeoutError`, `ProviderRateLimitError`, 5xx server errors
3. Do NOT retry on: `AuthError`, `ProviderClientError` (4xx except 429), `CircuitOpenError`
4. Use exponential backoff: `delay = min(base_delay * 2^attempt + jitter, max_delay)`

**Files affected:** `services/llm/base.py`, `services/llm/errors.py`

---

### E.2: Celery Task Event Streaming

**Location:** `celery_app.py`, `services/metrics.py`

**Status:** DEFERRED. This requires significant infrastructure work:
- Setting up `celery.events.ReabilityMonitor` or pubsub consumer
- Streaming events to Redis
- Updating `MetricsCollector` with task-specific metrics

The implementation is complex and invasive. Given the plan's guidance about avoiding rewrites of complex code from scratch, this item should be documented as deferred in the plan status but NOT implemented as a stub.

**Files affected:** `celery_app.py`, `services/metrics.py`, `tasks/monitor.py` (new)

---

### E.3: Webhook Event Audit Trail (Partial Improvement)

**Location:** `services/webhooks.py`

**Status:** ✅ COMPLETED
- `WebhookEvent` model exists for delivery history
- Events are logged with status_code, response_body, error_message, attempt_number
- Admin UI at `/admin/webhooks` with event history display
- API endpoint `GET /admin/api/webhooks/<webhook_id>/events` returns events

**Files affected:** `models.py`, `services/webhooks.py`, `routes/admin/webhooks.py`, `routes/admin/api/webhooks.py`, `templates/admin/webhooks.html`, `templates/admin/partials/webhook_events.html`

---

## Wave F: SLA Tracking & Analytics

### F.1: Article Processing SLA Tracking

**Location:** `models.py`, `tasks/pipeline.py`

**Problem:**
No tracking of article processing SLA (time from crawl to publish). Pipeline timeouts are enforced, but there's no visibility into where time is spent within the pipeline or whether SLAs are being met.

**Impact:** No way to measure pipeline efficiency; no alerting on SLA breaches.

**Fix:**
1. Add timestamps to article model:
   - `crawled_at` (when article first entered system)
   - `selected_at` (when selector confirmed article)
   - `published_at` (when article went live)
2. Add computed fields in pipeline stages
3. Add `pipeline_sla_seconds` histogram to track end-to-end processing time
4. Add admin endpoint `GET /admin/api/pipeline/sla` returning SLA metrics

**Files affected:** `models.py` (Article model), `tasks/pipeline.py`, `routes/admin/api/` (new endpoint), `services/metrics.py`

---

### F.2: Newsletter Delivery Reporting

**Location:** `services/email.py`, `models.py`

**Problem:**
Newsletter delivery is attempted via SMTP but there's no tracking of delivery status (opened, bounced, complained).

**Impact:** No visibility into newsletter deliverability; potential silent failures.

**Fix:**
1. Track `sent_at` on Newsletter model (already exists)
2. Add a `delivered_count` estimate based on SMTP response
3. For SMTP failures, increment `Newsletter.error` field
4. Add newsletter delivery stats to admin dashboard

**Files affected:** `services/email.py`, `models.py`, `routes/admin/newsletters.py`

---

### F.3: Search Query Analytics

**Location:** `services/search/`, `routes/public/feeds.py`

**Problem:**
FTS5 search exists but there's no tracking of search queries, zero-result queries, or search result clicks.

**Impact:** No data-driven improvement of search or content selection.

**Fix:**
1. Add `SearchQuery` model to track: `query`, `results_count`, `clicked_article_id`, `created_at`
2. Log searches with result counts
3. Add admin endpoint showing top queries, zero-result queries

**Files affected:** `models.py` (new `SearchQuery` model), `routes/public/feeds.py`, `routes/admin/api/` (new analytics endpoint)

---

## Wave G: Optional Hardening

### G.1: DEBUG Warning in Production

**Location:** `config.py`, `app.py`

**Problem:**
If someone misconfigures `FLASK_CONFIG=production` but inherits `DevelopmentConfig`, debug mode could be enabled.

**Status:** Low risk — ProductionConfig doesn't inherit from DevelopmentConfig. The issue would only occur if someone explicitly set `FLASK_CONFIG=development` in production.

**Fix (optional):**
Add a startup warning if `DEBUG = True` in production context:

```python
if current_app.debug and not current_app.testing:
    logger.warning("DEBUG mode is enabled - do not use in production")
```

**Files affected:** `app.py` (optional)

---

## Implementation Order

### Phase 1: High-Impact Low-Effort (Wave A, C)
All items in Waves A and C are independent and can be implemented in parallel:
- **A.1** (DNS executor)
- **A.2** (Subagent executor)
- **A.3** (O(1) cache eviction)
- **C.1** (aggregate_crawl_results timeout)
- **C.2** (Exception re-raise)
- **C.3** (LLM tool call validation)
- **C.4** (Audit logging failures)
- **C.5** (Cache invalidation failures)

### Phase 2: Database & Template (Wave B, D)
All items are independent and can be implemented in parallel:
- **B.1** (Eager loading)
- **B.2** (Chunked deletes)
- **B.3** (Dashboard cache dicts)
- **D.1** (Admin template XSS)
- **D.2** (Article template XSS)
- **D.3** (Template attribute injection)

### Phase 3: LLM & Observability (Wave E)
All items are independent:
- **E.1** (LLM retry with backoff)
- **E.2** (Celery event streaming)
- **E.3** (Webhook audit trail)

### Phase 4: Analytics (Wave F)
All items are independent:
- **F.1** (SLA tracking)
- **F.2** (Newsletter delivery reporting)
- **F.3** (Search query analytics)

### Phase 5: Optional (Wave G)
- **G.1** (DEBUG warning)

---

## Parallelization Strategy

Items within each wave are independent and can be executed in parallel by separate agents. The waves must be executed sequentially (Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5) due to potential file conflicts and testing dependencies.

**Wave Execution Model:**
```
Phase 1 (Wave A + C): 8 items in parallel
Phase 2 (Wave B + D): 9 items in parallel
Phase 3 (Wave E): 3 items in parallel
Phase 4 (Wave F): 3 items in parallel
Phase 5 (Wave G): 1 item
```

---

## Testing Commands

After making changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

Specific tests to run by item:
- **A.1 (DNS executor):** `tests/test_url_ssrf.py`
- **A.2 (Subagent executor):** `tests/test_subagent.py`
- **A.3 (Cache eviction):** `tests/test_newsletter_sanitize.py`
- **B.1 (Eager loading):** `routes/public/links.py` tests
- **B.2 (Chunked deletes):** `tests/test_cleanup.py`
- **B.3 (Dashboard cache):** `tests/test_admin_api.py`
- **C.1 (Task timeout):** `tests/test_pipeline.py`, `tests/test_celery_config.py`
- **C.2 (Exception re-raise):** `tests/test_pipeline.py`
- **C.3 (LLM parsing):** `tests/test_llm_adapters/`
- **C.4 (Audit logging):** `tests/test_admin_auth.py`
- **C.5 (Cache invalidation):** `tests/test_admin_articles.py`
- **D.1-D.3 (Template escaping):** Template rendering tests if any exist
- **E.1 (LLM retry):** `tests/test_llm_adapters/`
- **E.2 (Celery events):** `tests/test_celery_config.py`
- **E.3 (Webhook audit):** `tests/` (webhook-related)
- **F.1 (SLA tracking):** `tests/test_pipeline/`, `tests/test_pipeline_e2e.py`
- **F.2 (Newsletter):** `tests/test_newsletter.py`, `tests/test_email.py`
- **F.3 (Search analytics):** `tests/test_search.py`, `tests/test_fts.py`

---

## Rollback Plan

If any change causes issues:
1. Revert the specific file change
2. Run tests to confirm restoration
3. Re-analyze before re-applying
4. For model changes, generate downgrade migration
5. Clear relevant Redis keys (config cache, locks)
6. For Celery task changes, ensure workers pick up changes (may need restart)
7. For template changes, clear any template cache

---

## Notes

### Thread Safety
- The shared executors are accessed from Celery task threads. `ThreadPoolExecutor` is thread-safe for `submit()` and `result()`. The `ResponseCache` already uses `threading.Lock` for `_memory` access — no additional synchronization needed for the executor changes.
- Executor shutdown is not needed on module reload — executors clean up automatically when the process exits.

### Redis Error Handling
- All new Redis operations should catch `redis.exceptions.RedisError` (not bare `Exception`)
- Webhook event queue should use separate Redis DB or key prefix to avoid collisions
- Celery event streaming to Redis should be fire-and-forget (don't block on Redis errors)

### Celery Task Patterns
- All long-running tasks should have both `soft_time_limit` and `time_limit`
- Use `autoretry_for` / `retry_backoff` decorators instead of manual `self.retry()`
- Tasks that touch database should commit in try/except with rollback on failure
- Re-raise after logging when the exception should trigger Celery retry

### Template Escaping
- All user-controlled data in templates should use `|e` filter
- This includes database fields populated from external sources (RSS feeds, LLM output)
- Admin templates are not exempt from escaping — compromised feed sources could inject malicious content

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

### Already Implemented (from previous plans)
- Structured JSON logging in production (`logging_config.py`)
- Prometheus metrics export endpoint (`GET /admin/api/metrics/prometheus`)
- Source health auto-recovery (`record_crawl_success()` in `services/crawling.py`)
- Session fixation prevention (session.clear() before login)
- Password hashing (werkzeug's check_password_hash)
- SQL injection prevention (SQLAlchemy ORM)
- SSRF protection (private IP blocking in url.py)
- CSRF protection (form tokens, JSON decorator)
- Open redirect protection (_safe_redirect_url)
- Celery content restriction (CELERY_ACCEPT_CONTENT = ["json"])
- Error responses (no stack traces to users)
- Deserialization allowlist (schemas.* prefix only)

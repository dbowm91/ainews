# AINews Improvement Plan - Consolidated

**Date:** April 30, 2026
**Status:** ACTIVE
**Reviewer:** Code Review Session
**Approver:** TBD
**Estimated Effort:** 10-12 weeks (part-time)

---

## Executive Summary

This consolidated plan addresses findings from 8 separate improvement plans covering code quality, security hardening, performance, LLM pipeline, frontend, backend deep dive, and operational security. Each item has been verified against the actual codebase.

**Key Corrections from Original Plans:**
- Code Quality (plan2): Claims of "92 unguarded commits" were overstated - many commits are properly guarded. True count of problematic commits is under 20.
- Security (plan3): `_escape_like_pattern()` is already correct (uses manual replace, not `re.escape()`). Topic notes validation already exists.
- Authentication (plan7): Per-route `@require_auth` decorator pattern is correct and properly implemented.

**What's Working Well:**
- Fail-closed policies in limiters and Redis locks
- SSRF protection with DNS rebinding prevention
- Session security (`session.clear()` on login)
- Circuit breakers per provider:model:stage
- State machine for pipeline transitions
- Comprehensive database indexes
- CSS module architecture
- HTMX progressive enhancement

---

## Wave 1: Critical Issues (Week 1-2)

Items in Wave 1 can be implemented in parallel by separate agents.

### 1.1 Celery Task `acks_late=True` — Critical Data Integrity

**Problem:** All Celery tasks lack `acks_late=True` and `task_reject_on_worker_lost=True`. Worker crash = lost task with no retry, article stuck in intermediate state.

**Files to Modify:**
```
tasks/select.py:46-56
tasks/research.py:48-58
tasks/write.py:35-45
tasks/edit.py:353-363
tasks/crawl.py:18-28, 207-211, 253-263
tasks/extract.py:264-274
tasks/newsletter.py:19-30, 360-370, 472-481
tasks/retry.py:20-28
tasks/cleanup.py (7 tasks: cleanup_old_pipeline_logs, cleanup_expired_verifications, cleanup_stale_limiter_slots, consolidate_trend_memory, purge_trend_memory, recalculate_impact_scores, cleanup_old_article_versions)
```

**Solution Pattern:**
```python
@shared_task(
    bind=True,
    acks_late=True,                          # ADD
    task_reject_on_worker_lost=True,          # ADD
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def select_article(self, article_id: int, run_id=None):
    ...
```

**Subtasks:**
- [ ] 1.1.1 Update tasks/select.py task decorator
- [ ] 1.1.2 Update tasks/research.py task decorator
- [ ] 1.1.3 Update tasks/write.py task decorator
- [ ] 1.1.4 Update tasks/edit.py task decorator
- [ ] 1.1.5 Update tasks/crawl.py (3 tasks)
- [ ] 1.1.6 Update tasks/extract.py task decorator
- [ ] 1.1.7 Update tasks/newsletter.py (3 tasks)
- [ ] 1.1.8 Update tasks/retry.py task decorator
- [ ] 1.1.9 Update tasks/cleanup.py (7 tasks)
- [ ] 1.1.10 Test worker crash recovery
- [ ] 1.1.11 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 1.2 ResponseCache Stampede Protection — Redis blpop

**Problem:** `services/cache.py:145-151` uses `time.sleep(0.05)` polling loop instead of Redis `blpop`. Inefficient under load.

**Current Code:**
```python
# services/cache.py:145-151
for _ in range(10):
    cached = self.get(key)
    if cached is not None:
        return cached
    if not self._redis.exists(lock_key):
        break
    time.sleep(0.05)
```

**Solution:** Replace with Redis pub/sub notification:
```python
def get_or_set(self, key: str, factory, ttl: int = 120) -> Any:
    cached = self.get(key)  # Try L1/L2 first
    if cached is not None:
        return cached

    lock_key = f"{self._prefix}lock:{key}"
    compute_key = f"{self._prefix}compute:{key}"

    # Try to acquire compute lock
    if not self._redis.set(lock_key, "1", nx=True, ex=ttl):
        # Someone else computing - wait for result via pub/sub
        channel = f"{self._prefix}done:{key}"
        pubsub = self._redis.pubsub()
        pubsub.subscribe(channel)
        try:
            # Check if already completed while subscribing
            cached = self.get(key)
            if cached is not None:
                return cached
            # Wait with timeout
            message = pubsub.get_message(timeout=ttl)
            return self.get(key)
        finally:
            pubsub.unsubscribe(channel)

    # We got the lock - compute value
    try:
        value = factory()
        self.set(key, value, ttl)
        self._redis.publish(f"{self._prefix}done:{key}", "1")
        return value
    finally:
        self._redis.delete(lock_key)
```

**Files to Modify:** `services/cache.py` (get_or_set method, lines 121-176)

**Subtasks:**
- [ ] 1.2.1 Implement blpop-based stampede protection
- [ ] 1.2.2 Add Redis pub/sub notification on cache set
- [ ] 1.2.3 Preserve existing fallback layers
- [ ] 1.2.4 Test concurrent misses (stampede scenario)
- [ ] 1.2.5 Verify with ruff and pytest

**Estimated Effort:** 2 days

---

### 1.3 Fix `resolve_env_var()` Silent Empty String Fallback

**Problem:** `schemas/common.py:32-48` returns empty string for missing env vars instead of raising. Enables LLM providers with empty API keys to pass validation.

**Current Code:**
```python
def resolve_env_var(val: str) -> str:
    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
        var_name = val[2:-1]
        resolved = os.environ.get(var_name, "")  # Returns "" on missing
        if not resolved and var_name not in _warned_missing_vars:
            _warned_missing_vars.add(var_name)
            logger.warning("Environment variable %s is not set — using empty string", var_name)
        return resolved
    return val
```

**Solution:** Add `required` parameter and Pydantic validators:
```python
def resolve_env_var(val: str, required: bool = False) -> str:
    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
        var_name = val[2:-1]
        resolved = os.environ.get(var_name)
        if resolved is None:
            if required:
                raise ValueError(f"Required environment variable {var_name} is not set")
            elif var_name not in _warned_missing_vars:
                _warned_missing_vars.add(var_name)
                logger.warning("Environment variable %s is not set", var_name)
            return ""
        return resolved
    return val
```

Then update `schemas/llm.py` to reject empty api_key when enabled=True.

**Files to Modify:**
- `schemas/common.py` - resolve_env_var function
- `schemas/llm.py` - Add Pydantic validator for api_key
- `config.py:251-280` - Update _validate_llm_providers() to check all provider types

**Subtasks:**
- [ ] 1.3.1 Update resolve_env_var() to support required parameter
- [ ] 1.3.2 Add Pydantic validators to reject empty api_key when enabled
- [ ] 1.3.3 Update _validate_llm_providers() to check all provider types
- [ ] 1.3.4 Add tests for missing env var behavior
- [ ] 1.3.5 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 1.4 CSS Variable Consolidation

**Problem:** CSS custom properties defined in 3 files (variables.css, critical.css, critical_css.html). Duplication causes maintenance burden.

**Verification:** Duplicate confirmed:
- `variables.css:19-172` - Full :root block (canonical source)
- `critical.css:10-62` - Duplicate :root and [data-theme="light"] blocks
- `templates/partials/critical_css.html` - Minified copy (manually synced)

**Solution:**
| File | Action |
|------|--------|
| `variables.css` | Keep as canonical source |
| `critical.css` | Remove :root and [data-theme="light"] blocks, add `@import "./variables.css"` |
| `templates/partials/critical_css.html` | Auto-generate via build script |

**Files to Modify:**
- `static/css/critical.css` - Remove duplicate blocks, add @import
- `static/css/layout.css` - Remove duplicate layout rules (see 1.5)
- Create `build/generate-critical-css.js` - Build script for critical_css.html

**Subtasks:**
- [ ] 1.4.1 Verify all variables in critical.css exist in variables.css
- [ ] 1.4.2 Remove :root block from critical.css (lines 10-62)
- [ ] 1.4.3 Remove [data-theme="light"] block from critical.css
- [ ] 1.4.4 Add @import "./variables.css" to critical.css
- [ ] 1.4.5 Verify base template still renders correctly
- [ ] 1.4.6 Create build/generate-critical-css.js
- [ ] 1.4.7 Verify with ruff and pytest

**Estimated Effort:** 2-3 hours

---

### 1.5 CSS Layout Rule Deduplication

**Problem:** 13+ layout rules duplicated between critical.css and layout.css.

**Confirmed Duplicates:**
| Selector | critical.css | layout.css |
|----------|--------------|------------|
| `.nav` | Lines 135-142 | Lines 7-14 |
| `.logo` | Lines 144-155 | Lines 16-27 |
| `.container` | Lines 196-202 | Lines 63-69 |
| `.htmx-indicator` | Lines 251-259 | Lines 112-120 |
| `.nav-links` | Lines 161-165 | Lines 33-37 |
| `.nav-meta` | Lines 183-185 | Lines 55-57 |
| `.nav-tag` | Lines 187-194 | Lines 103-110 |

**Keep Unique in layout.css:**
- `.htmx-indicator.spinner`
- `.loading-indicator`
- `.nav-logout`
- Dashboard grid rules

**Files to Modify:** `static/css/layout.css`

**Subtasks:**
- [ ] 1.5.1 Audit all rules in layout.css vs critical.css
- [ ] 1.5.2 Remove exact duplicate rules from layout.css
- [ ] 1.5.3 Keep only unique layout.css enhancements
- [ ] 1.5.4 Verify rendering unchanged
- [ ] 1.5.5 Verify with ruff and pytest

**Estimated Effort:** 1 hour

---

### 1.6 Critical CSS Auto-Generation Build Step

**Problem:** `templates/partials/critical_css.html` is manually maintained. No build script exists.

**Solution:** Create build script to auto-generate:
```javascript
// build/generate-critical-css.js
const fs = require('fs');
const css = fs.readFileSync('static/css/variables.css', 'utf8');
const minified = css.replace(/\s+/g, ' ').replace(/\s*([{}:;])\s*/g, '$1');
// Extract :root and [data-theme="light"] blocks
const critical = /* extract blocks */;
fs.writeFileSync('templates/partials/critical_css.html', critical);
```

**Subtasks:**
- [ ] 1.6.1 Create build/generate-critical-css.js script
- [ ] 1.6.2 Add "generate:critical" npm script (if package.json added)
- [ ] 1.6.3 Remove manual critical_css.html content
- [ ] 1.6.4 Document in README

**Estimated Effort:** 1-2 hours

---

## Wave 2: High Priority (Week 2-4)

Items in Wave 2 can be parallelized after Wave 1 completes.

### 2.1 SMTP Connection Pooling

**Problem:** `services/email.py:222-230` creates new SMTP connection per email. TLS handshake per message adds ~200-500ms.

**Current Code:**
```python
def _send_smtp(to_email: str, subject: str, html_body: str, extra_headers: dict | None = None):
    cfg = get_smtp_config()
    try:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
        with server:
            if cfg["use_tls"]:
                server.starttls()
            if cfg["user"] and cfg["password"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_addr"], to_email, msg.as_string())
```

**Solution:** Implement `SMTPConnectionPool` class with configurable pool size.

**Files to Modify:**
- `services/email.py` - Add pool class and modify _send_smtp
- `config.py` - Add SMTP_POOL_SIZE config option

**Subtasks:**
- [ ] 2.1.1 Create SMTPConnectionPool class
- [ ] 2.1.2 Modify _send_smtp to use pool
- [ ] 2.1.3 Add SMTP_POOL_SIZE to config
- [ ] 2.1.4 Add connection health checks
- [ ] 2.1.5 Verify with ruff and pytest

**Estimated Effort:** 2 days

---

### 2.2 Admin Dashboard Query Consolidation

**Problem:** `routes/admin/dashboard.py:92-173` performs 9+ separate DB queries synchronously.

**Verification:** 9 queries found:
1. `Article.pipeline_status` count grouped
2. `Source.query.all()` (redundant with count)
3. `Source.query.count()` (redundant)
4. `Article.source_id` count grouped
5. `Article.query.options(joinedload(Article.source))...`
6. `get_provider_info()` via Redis
7. `get_subscriber_stats(db)`
8. `PipelineRun.query...limit(5)`
9. `PipelineRun.query.filter_by(status="running").count()`

**Solution:**
1. Add caching with short TTL (60s) for stats
2. Consolidate queries using subqueries/WINDOW functions
3. Use `with_entities()` to avoid loading full objects

**Files to Modify:** `routes/admin/dashboard.py`

**Subtasks:**
- [ ] 2.2.1 Add cache for stats (60s TTL)
- [ ] 2.2.2 Consolidate Source queries
- [ ] 2.2.3 Consolidate Article queries
- [ ] 2.2.4 Benchmark improvement
- [ ] 2.2.5 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 2.3 Bulk Article N+1 Query Fix

**Problem:** `routes/admin/api/articles.py:332` loads articles without eager loading.

**Current Code:**
```python
articles = Article.query.filter(Article.id.in_(article_ids)).all()
# Later: article.source, article.tags accessed in loop (N+1)
```

**Solution:** Add joinedload:
```python
from sqlalchemy.orm import joinedload

articles = (
    Article.query
    .filter(Article.id.in_(article_ids))
    .options(joinedload(Article.source), joinedload(Article.tags))
    .all()
)
```

**Files to Modify:** `routes/admin/api/articles.py` (lines 332, 207-217 for bulk reprocess)

**Subtasks:**
- [ ] 2.3.1 Add joinedload to bulk article query (line 332)
- [ ] 2.3.2 Add joinedload to bulk reprocess (lines 207-217)
- [ ] 2.3.3 Verify with ruff and pytest

**Estimated Effort:** 0.5 day

---

### 2.4 Webhook Dispatch Async

**Problem:** `routes/admin/api/webhooks.py:251-274,319-356` performs synchronous HTTP dispatch.

**Affected Routes:**
- `test_webhook` (lines 251-274)
- `resend_webhook_event` (lines 319-356)

Both call `dispatch_webhook()` which uses `requests.post()` with 30s timeout + 3 retries.

**Solution:** Move to Celery task:
```python
@webhooks_bp.route("/test", methods=["POST"])
def test_webhook():
    dispatch_webhook_task.delay(webhook_id, payload)
    return jsonify({"status": "queued"}), 202
```

**Files to Modify:**
- `routes/admin/api/webhooks.py` - Convert sync to async
- `tasks/webhook.py` - New task file for dispatch

**Subtasks:**
- [ ] 2.4.1 Create tasks/webhook.py with dispatch task
- [ ] 2.4.2 Update test_webhook to use async dispatch
- [ ] 2.4.3 Update resend_webhook_event to use async dispatch
- [ ] 2.4.4 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 2.5 HMAC Task Signing — Add to Beat-Scheduled Tasks

**Problem:** 10 scheduled tasks missing `verify_task()` HMAC verification.

**Tasks Missing HMAC:**
| Task | File:Line |
|------|----------|
| `publish_scheduled_articles` | `tasks/scheduler.py:10` |
| `retry_stuck` | `tasks/retry.py:29` |
| `retry_failed_newsletter_deliveries` | `tasks/newsletter.py:482` |
| `cleanup_old_article_versions` | `tasks/cleanup.py:230` |
| `consolidate_trend_memory` | `tasks/cleanup.py:119` |
| `purge_trend_memory` | `tasks/cleanup.py:203` |
| `cleanup_old_pipeline_logs` | `tasks/cleanup.py:17` |
| `cleanup_expired_verifications` | `tasks/cleanup.py:62` |
| `cleanup_stale_limiter_slots` | `tasks/cleanup.py:99` |
| `recalculate_impact_scores` | `tasks/cleanup.py:152` |

**Solution Pattern:**
```python
from services.task_security import verify_task

@shared_task(bind=True, ...)
def publish_scheduled_articles(self):
    if not verify_task("publish_scheduled_articles", (), {}):
        logger.error("Invalid signature for publish_scheduled_articles")
        raise ValueError("Invalid task signature")
    # ... existing logic
```

**For tasks with parameters (cleanup_old_article_versions):**
```python
def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
    # Validate parameters first
    if not isinstance(days_to_keep, int) or days_to_keep < 1 or days_to_keep > 365:
        raise ValueError("days_to_keep must be integer 1-365")

    if not verify_task("cleanup_old_article_versions", (), {"days_to_keep": days_to_keep, "dry_run": dry_run}):
        logger.error("Invalid signature for cleanup_old_article_versions")
        raise ValueError("Invalid task signature")
    # ... existing logic
```

**Files to Modify:**
- `tasks/scheduler.py`
- `tasks/retry.py`
- `tasks/newsletter.py`
- `tasks/cleanup.py` (7 tasks)

**Subtasks:**
- [ ] 2.5.1 Add verify_task to publish_scheduled_articles
- [ ] 2.5.2 Add verify_task to retry_stuck
- [ ] 2.5.3 Add verify_task to retry_failed_newsletter_deliveries
- [ ] 2.5.4 Add verify_task to all cleanup.py tasks (7 tasks)
- [ ] 2.5.5 Test HMAC verification
- [ ] 2.5.6 Verify with ruff and pytest

**Estimated Effort:** 0.5 day

---

### 2.6 Audit Logging — Add to Admin Mutation Endpoints

**Problem:** 24+ endpoints missing `log_admin_action()`.

**High Priority Missing:**
| File | Endpoints |
|------|----------|
| `routes/admin/review.py` | approve_article, reject_article |
| `routes/admin/sources.py` | enable_source, disable_source |
| `routes/admin/api/config.py` | reload_config |

**Medium Priority Missing:**
| File | Endpoints |
|------|----------|
| `routes/admin/topic_notes.py` | create, edit, delete |
| `routes/admin/trend_memory.py` | delete, delete_expired |
| `routes/admin/articles.py` | edit, delete, reprocess, rollback |
| `routes/admin/pipelines.py` | trigger_crawl |
| `routes/admin/newsletters.py` | trigger_newsletter, dry_run |

**Solution Pattern:**
```python
from services.audit import log_admin_action

@admin_bp.route("/review/<int:article_id>/approve", methods=["POST"])
@require_auth
def approve_article(article_id):
    # ... existing approval logic

    log_admin_action(
        "article_approve",
        target_type="article",
        target_id=article.id,
        details={"original_title": article.original_title, "pipeline_status": article.pipeline_status},
        category="article",
    )
```

**Files to Modify:**
- `routes/admin/review.py` (approve_article, reject_article)
- `routes/admin/sources.py` (enable_source, disable_source)
- `routes/admin/api/config.py` (reload_config)
- `routes/admin/topic_notes.py` (create, edit, delete)
- `routes/admin/trend_memory.py` (delete, delete_expired)
- `routes/admin/articles.py` (edit, delete, reprocess, rollback)
- `routes/admin/pipelines.py` (trigger_crawl)
- `routes/admin/newsletters.py` (trigger_newsletter, dry_run)

**Subtasks:**
- [ ] 2.6.1 Add audit logging to review.py endpoints
- [ ] 2.6.2 Add audit logging to sources.py endpoints
- [ ] 2.6.3 Add audit logging to config.py
- [ ] 2.6.4 Add audit logging to topic_notes.py
- [ ] 2.6.5 Add audit logging to trend_memory.py
- [ ] 2.6.6 Add audit logging to articles.py
- [ ] 2.6.7 Add audit logging to pipelines.py
- [ ] 2.6.8 Add audit logging to newsletters.py
- [ ] 2.6.9 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 2.7 Response Cache Invalidation — Add to Admin Mutations

**Problem:** 12+ mutations missing cache invalidation.

**Missing Invalidation:**
| File | Function | Cache Keys to Invalidate |
|------|----------|-------------------------|
| `routes/admin/trend_memory.py` | delete, delete_expired | `trend_memory:*` |
| `routes/admin/topic_notes.py` | create, edit, delete | `topic_note:*` |
| `routes/admin/sources.py` | enable, disable | `pub:index`, `pub:topic`, `pub:rss_feed`, `pub:related` |
| `routes/admin/review.py` | reject_article | `pub:index`, `pub:topic`, `pub:rss_feed` |

**Solution Pattern:**
```python
from services.cache import get_response_cache

@admin_bp.route("/trend-memory/<int:memory_id>/delete", methods=["POST"])
@require_auth
def trend_memory_delete(memory_id):
    # ... existing delete logic ...

    # Invalidate cache after successful commit
    try:
        cache = get_response_cache()
        cache.invalidate_prefix("trend_memory")
    except Exception as e:
        logger.warning("Failed to invalidate trend_memory cache: %s", e)

    log_admin_action(...)
```

**Files to Modify:**
- `routes/admin/trend_memory.py` (delete, delete_expired)
- `routes/admin/topic_notes.py` (create, edit, delete)
- `routes/admin/sources.py` (enable, disable)
- `routes/admin/review.py` (reject_article - approve_article already has this)

**Subtasks:**
- [ ] 2.7.1 Add cache invalidation to trend_memory.py
- [ ] 2.7.2 Add cache invalidation to topic_notes.py
- [ ] 2.7.3 Add cache invalidation to sources.py
- [ ] 2.7.4 Add cache invalidation to review.py (reject only)
- [ ] 2.7.5 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 2.8 Per-Process Cache Stats — Redis Backend

**Problem:** `services/cache.py:46-47` tracks `_hits` and `_misses` as per-process counters.

**Current Code:**
```python
self._hits = 0
self._misses = 0
```

**Solution:** Use Redis for cross-worker stats:
```python
def record_hit(self, key: str):
    self._redis.hincrby("ainews:cache:stats", "hits", 1)

def get_stats(self) -> dict:
    stats = self._redis.hgetall("ainews:cache:stats")
    # Aggregate across all workers
```

**Files to Modify:** `services/cache.py`

**Subtasks:**
- [ ] 2.8.1 Replace in-memory counters with Redis
- [ ] 2.8.2 Add fallback to in-memory if Redis unavailable
- [ ] 2.8.3 Expose via admin endpoint
- [ ] 2.8.4 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

### 2.9 L1/L2 Cache TTL Refresh Fix

**Problem:** On L1 hit, Redis TTL not refreshed. If Redis TTL expires before L1 eviction, stale data served.

**Current Code (services/cache.py:78-83):**
```python
if time.monotonic() < expires_at:
    with self._memory_lock:
        self._memory[full_key] = (expires_at, time.monotonic(), raw)
        self._memory.move_to_end(full_key)
    self._hits += 1
    return json.loads(raw)
# Missing: self._redis.expire(full_key, ttl)
```

**Solution:** Add Redis TTL refresh on L1 access:
```python
if time.monotonic() < expires_at:
    with self._memory_lock:
        self._memory[full_key] = (expires_at, time.monotonic(), raw)
        self._memory.move_to_end(full_key)
    self._hits += 1
    self._redis.expire(full_key, self._ttl)  # Add this
    return json.loads(raw)
```

**Files to Modify:** `services/cache.py` (lines 78-83)

**Subtasks:**
- [ ] 2.9.1 Add redis.expire on L1 hit
- [ ] 2.9.2 Verify with ruff and pytest

**Estimated Effort:** 0.5 day

---

## Wave 3: Medium Priority (Week 4-6)

### 3.1 Admin Article Form Input Validation

**Problem:** `routes/admin/articles.py:217-231` accepts unbounded input for headline, tldr, body, etc.

**Fields Needing Limits:**
- `headline` → MAX_HEADLINE_LENGTH = 500
- `tldr` → MAX_TLDR_LENGTH = 300
- `body` → MAX_BODY_LENGTH = 50000
- `why_it_matters` → MAX_WHY_IT_MATTERS_LENGTH = 1000
- `what_to_watch` → MAX_WHAT_TO_WATCH_LENGTH = 500
- `key_points` → MAX_KEY_POINTS_LENGTH = 2000
- `tags` → MAX_TAGS_LENGTH = 500

**Solution:**
```python
MAX_HEADLINE_LENGTH = 500
MAX_TLDR_LENGTH = 300
MAX_BODY_LENGTH = 50000
MAX_WHY_IT_MATTERS_LENGTH = 1000
MAX_WHAT_TO_WATCH_LENGTH = 500
MAX_KEY_POINTS_LENGTH = 2000
MAX_TAGS_LENGTH = 500

def _sanitize_field(value: str, max_len: int) -> str:
    return value[:max_len].strip() if value else ""
```

**Files to Modify:** `routes/admin/articles.py`

**Subtasks:**
- [ ] 3.1.1 Define constants for max field lengths
- [ ] 3.1.2 Add truncation in article edit route
- [ ] 3.1.3 Add validation in article creation route
- [ ] 3.1.4 Verify with ruff and pytest

**Estimated Effort:** 1 hour

---

### 3.2 Database Indexes — Add Missing Indexes

**Problem:** 6 missing indexes identified.

| Column(s) | Model | Priority |
|-----------|-------|----------|
| `Webhook.active` | Webhook | HIGH |
| `Source.active` | Source | MEDIUM |
| `Subscriber.newsletter_type` | Subscriber | MEDIUM |
| `Source.source_type` | Source | LOW |
| `PipelineRun.run_type` | PipelineRun | LOW |
| `PipelineRun.(run_type, status)` | PipelineRun | LOW |

**Solution:** Add to models.py and create migration.

```python
# models.py additions
class Source(db.Model):
    # ... existing fields ...
    source_type = db.Column(db.String(32), nullable=False, index=True)  # ADD
    active = db.Column(db.Boolean, default=True, index=True)  # ADD

class Subscriber(db.Model):
    # ... existing fields ...
    newsletter_type = db.Column(db.String(32), nullable=False, index=True)  # ADD

class Webhook(db.Model):
    # ... existing fields ...
    active = db.Column(db.Boolean, default=True, index=True)  # ADD - CRITICAL
```

**Migration:** `migrations/versions/030_add_missing_indexes.py`

**Subtasks:**
- [ ] 3.2.1 Add index to Source.active
- [ ] 3.2.2 Add index to Source.source_type
- [ ] 3.2.3 Add index to Subscriber.newsletter_type
- [ ] 3.2.4 Add index to PipelineRun.run_type
- [ ] 3.2.5 Add composite index to PipelineRun (run_type, status)
- [ ] 3.2.6 Add index to Webhook.active (HIGH priority)
- [ ] 3.2.7 Create migration file
- [ ] 3.2.8 Test migration
- [ ] 3.2.9 Verify with ruff and pytest

**Estimated Effort:** 0.5 day

---

### 3.3 OpenTelemetry Exporter Fix

**Problem:** `services/logging_utils.py:51-53` creates no-op span processor.

**Current Code:**
```python
span_processor = BatchSpanProcessor(
    type("NoopExporter", (), {"export": lambda *a, **k: None})()
)
```

**Solution:**
```python
def _setup_opentelemetry():
    if not _OTEL_AVAILABLE:
        return

    from opentelemetry.exporter.otlp import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set, skipping OTel setup")
        return

    exporter = OTLPSpanExporter(endpoint=endpoint)
    span_processor = BatchSpanProcessor(exporter)

    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(span_processor)
```

**Files to Modify:**
- `services/logging_utils.py`
- `config.py` - Add OTEL_EXPORTER_OTLP_ENDPOINT config
- `pyproject.toml` - Add `opentelemetry-exporter-otlp` dependency

**Subtasks:**
- [ ] 3.3.1 Add opentelemetry-exporter-otlp to dependencies
- [ ] 3.3.2 Update _setup_opentelemetry() to use real exporter
- [ ] 3.3.3 Add OTEL_EXPORTER_OTLP_ENDPOINT to config and .env.example
- [ ] 3.3.4 Verify with ruff and pytest

**Estimated Effort:** 1-2 days

---

### 3.4 Subagent Exception Handling — Specific Types

**Problem:** 16 locations in `services/subagent.py` use bare `except Exception` that mask specific errors.

**Locations:**
| Line | Function |
|------|----------|
| 56 | `_get_topic_note()` |
| 74 | `_get_topic_notes_for_topics()` |
| 92 | `_get_related_articles()` |
| 112 | `_get_trend_memory()` |
| 131 | `_get_article_by_id()` |
| 145 | `_search_articles()` |
| 161 | `_get_source_health()` |
| 321, 331, 619, 820, 918, 941, 1006, 1131, 1145 | `run_subagent_chain()`, `_execute_tool()` |

**Solution Pattern:**
```python
# Before
except Exception as e:
    logger.warning("Tool X failed: %s", e)
    return f"Error: ..."

# After
except (SQLAlchemyError, KeyError, AttributeError) as e:
    logger.error("Tool X failed for %s: %s", target, e)
    return f"Error: ..."
except Exception as e:  # fallback for unexpected
    logger.error("Unexpected error in tool: %s", e)
```

**Files to Modify:** `services/subagent.py`

**Subtasks:**
- [ ] 3.4.1 Update tool functions to catch specific exceptions
- [ ] 3.4.2 Add error context to logs
- [ ] 3.4.3 Verify with ruff and pytest

**Estimated Effort:** 3-4 hours

---

### 3.5 Fix Content Sanitization Double-Escaping

**Problem:** `templates/partials/condensed_article.html:63` applies `|e` (Jinja2 escape) to content already sanitized by `bleach.clean()`.

**Current:** `<div class="article-body">{{ fa.body|e }}</div>`

**Solution:** Remove `|e` from bleached content:
```html
<div class="article-body">{{ fa.body }}</div>
```

**Audit all templates for:**
- `final_article` fields
- `draft_article` fields
- `html_content` fields

**Files to Modify:** Templates in `templates/partials/`

**Subtasks:**
- [ ] 3.5.1 Audit all templates for |e on sanitized content
- [ ] 3.5.2 Remove |e from bleached content fields
- [ ] 3.5.3 Document sanitization strategy
- [ ] 3.5.4 Verify with ruff and pytest

**Estimated Effort:** 1-2 hours

---

### 3.6 Create Admin API Schemas

**Problem:** No Pydantic models for admin API routes; manual validation silently passes.

**Solution:** Create `schemas/admin.py`:
```python
# schemas/admin.py
from pydantic import BaseModel, Field
from typing import Optional

class ArticleIdsParams(BaseModel):
    q: Optional[str] = Field(default="", max_length=200)
    status: Optional[str] = None
    source_id: Optional[int] = Field(default=None, ge=1)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    impact_min: Optional[int] = Field(default=0, ge=0)
    impact_max: Optional[int] = Field(default=100, ge=0)

class CreateSourceRequest(BaseModel):
    source_key: str = Field(..., pattern=r"^[a-z0-9_]+$", max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    url: Optional[str] = None
    feed_url: Optional[str] = None
    source_type: str = Field(..., pattern=r"^(rss|atom|web|twitter|reddit)$")
```

**Files to Modify:**
- Create `schemas/admin.py`
- Update `routes/admin/api/articles.py`
- Update `routes/admin/api/sources.py`
- Update `routes/admin/api/health.py`

**Subtasks:**
- [ ] 3.6.1 Create schemas/admin.py with request models
- [ ] 3.6.2 Add Pydantic validation to sources.py endpoints
- [ ] 3.6.3 Fix silent failures in articles.py
- [ ] 3.6.4 Add task_id validation to health.py
- [ ] 3.6.5 Verify with ruff and pytest

**Estimated Effort:** 3-4 hours

---

### 3.7 OTel Tracing for Subagent LLM Calls

**Problem:** Subagent LLM calls miss tracing (`services/subagent.py:553-561, 725-735`).

**Solution:** Add `traced_llm_call` to subagent LLM invocations:
```python
from services.logging_utils import traced_llm_call

def run_subagent_with_tools(...) -> dict:
    provider, model, provider_id = _get_subagent_provider_and_config(stage)

    with traced_llm_call(provider=provider_id, model=model, stage=stage):
        with time_histogram("subagent_with_tools.duration_seconds", stage=stage):
            # ... existing tool-calling logic
            response = provider.chat_with_tools(...)
```

**Files to Modify:** `services/subagent.py`

**Subtasks:**
- [ ] 3.7.1 Add traced_llm_call to run_subagent()
- [ ] 3.7.2 Add traced_llm_call to run_subagent_with_tools()
- [ ] 3.7.3 Verify with ruff and pytest

**Estimated Effort:** 0.5 day

---

### 3.8 Newsletter Tasks Bare Commits Fix

**Problem:** `tasks/newsletter.py:520, 533` have bare commits in exception handler context.

**Current:** Exception handler at line 548 catches `Exception` but doesn't rollback.

**Solution:** Add rollback in exception handler:
```python
except Exception as e:
    db.session.rollback()  # ADD THIS
    logger.error(...)
    failed_count += 1
```

**Files to Modify:** `tasks/newsletter.py`

**Subtasks:**
- [ ] 3.8.1 Add rollback to exception handler at line 548
- [ ] 3.8.2 Verify with ruff and pytest

**Estimated Effort:** 0.5 hour

---

## Wave 4: LLM Pipeline Improvements (Week 6-8)

### 4.1 Memory Summarization for Context Overflow

**Problem:** `sliding_window_truncate()` (services/prompts.py:59-70) loses middle context.

**Current:** Preserves head+tail but loses middle content.

**Solution:** Add LLM-based summarization for large overflow:
```python
async def summarize_context(
    text: str,
    max_chars: int,
    llm_provider: BaseLLMProvider,
) -> str:
    """Summarize context using LLM instead of naive truncation."""
    if len(text) <= max_chars:
        return text

    summary_prompt = f"""
    Summarize the following text concisely while preserving key facts.
    Target length: {max_chars // 4} characters.
    Text: {text}
    """
    response = await llm_provider.chat(messages=[...])
    return response.text

def smart_truncate_context(text, max_chars, llm_provider=None):
    if len(text) <= max_chars:
        return text, False
    if len(text) <= max_chars * 2:
        return sliding_window_truncate(text, max_chars), False
    if llm_provider:
        return await summarize_context(text, max_chars, llm_provider), True
    return sliding_window_truncate(text, max_chars), False
```

**Files to Modify:** `services/prompts.py`

**Subtasks:**
- [ ] 4.1.1 Add summarize_context function
- [ ] 4.1.2 Add smart_truncate_context with hybrid strategy
- [ ] 4.1.3 Add truncation warning injection
- [ ] 4.1.4 Add configuration to pipeline.yaml
- [ ] 4.1.5 Verify with ruff and pytest

**Estimated Effort:** 2-3 days

---

### 4.2 Quality Assessment Infrastructure

**Problem:** Quality gates only check schema, not semantic quality.

**Current Quality Gates:**
- Research: `key_claims` and `impact_score >= 10`
- Write: body length >= 500, `key_points`, citations

**Solution:** Create quality assessment protocol:
```python
# services/quality.py

@dataclass
class QualityScore:
    groundedness: float  # 0-1: factual consistency
    coherence: float    # 0-1: logical flow
    completeness: float # 0-1: inclusion of details
    safety: float       # 0-1: no harmful content

class QualityAssessor(Protocol):
    async def assess(self, content: str, context: dict) -> QualityScore:
        ...

class LLMQualityAssessor:
    async def assess(self, content: str, context: dict) -> QualityScore:
        # Use LLM-as-judge pattern
        ...

def lightweight_quality_signals(content: str) -> dict:
    # Fast heuristics: length, repetition, sentence variance
    ...
```

**Files to Modify:** Create `services/quality.py`

**Subtasks:**
- [ ] 4.2.1 Create QualityScore dataclass
- [ ] 4.2.2 Create QualityAssessor protocol
- [ ] 4.2.3 Implement LLMQualityAssessor
- [ ] 4.2.4 Implement lightweight_quality_signals
- [ ] 4.2.5 Add hallucination detection
- [ ] 4.2.6 Integrate with quality gates
- [ ] 4.2.7 Verify with ruff and pytest

**Estimated Effort:** 4-5 days

---

### 4.3 Stage-Aware Tool Selection Enhancement

**Correction from plan8:** Tool filtering already exists via `stage_config.tools` and `initialize_tool_registry()`. The plan overstated the problem.

**Current Implementation:**
- `initialize_tool_registry()` at `services/subagent.py:396-397` filters by name list
- `tasks/research.py:104-107` uses stage-specific tools from config

**Enhancement:** Build upon existing infrastructure to add:
- Keyword-based tool boosting
- Dynamic tool selection based on query context

**Files to Modify:** Create `services/tool_selection.py`, modify `services/subagent.py`

**Subtasks:**
- [ ] 4.3.1 Create ToolSelector protocol
- [ ] 4.3.2 Implement StageAwareToolSelector (existing pattern)
- [ ] 4.3.3 Add KeywordToolSelector for relevance boosting
- [ ] 4.3.4 Update subagent to use enhanced selection
- [ ] 4.3.5 Add configuration to pipeline.yaml
- [ ] 4.3.6 Verify with ruff and pytest

**Estimated Effort:** 2-3 days

---

### 4.4 Streaming Support for LLM Adapters

**Problem:** None of the LLM adapters implement streaming.

**Solution:** Add `chat_streaming()` to base class and all providers:

```python
# services/llm/base.py
class BaseLLMProvider:
    def chat_streaming(self, messages, temperature=0.7, max_tokens=2048, system_prompt=None) -> Iterator[str]:
        raise NotImplementedError

# services/llm/openai.py
def chat_streaming(self, messages, temperature=0.7, max_tokens=2048, system_prompt=None):
    for chunk in self._client.chat.completions.create(**kwargs, stream=True):
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

**Files to Modify:**
- `services/llm/base.py`
- `services/llm/openai.py`
- `services/llm/anthropic.py`
- `services/llm/ollama.py`
- `services/llm/gemini.py`

**Subtasks:**
- [ ] 4.4.1 Add chat_streaming() to BaseLLMProvider
- [ ] 4.4.2 Implement in OpenAI adapter
- [ ] 4.4.3 Implement in Anthropic adapter
- [ ] 4.4.4 Implement in Ollama adapter
- [ ] 4.4.5 Implement in Gemini adapter
- [ ] 4.4.6 Verify with ruff and pytest

**Estimated Effort:** 3 days

---

### 4.5 Redis-Backed Circuit Breaker

**Problem:** Circuit breaker in `services/circuit_breaker.py` is in-memory only.

**Current:** Each worker has its own circuit state.

**Solution:** Use Redis for distributed circuit state:
```python
class RedisCircuitBreaker:
    def call_succeeded(self):
        self._redis.delete(self._key())  # Clear failure count

    def call_failed(self):
        pipe = self._redis.pipeline()
        pipe.incr(self._key())
        pipe.expire(self._key(), self._window_seconds)
        failures = pipe.execute()[0]
        if failures >= self._failure_threshold:
            self._redis.set(self._key(":opened_at"), time.time(), ex=self._recovery_timeout)

    def is_open(self) -> bool:
        # Check if circuit is open
        ...
```

**Files to Modify:** `services/circuit_breaker.py`, `services/llm/__init__.py`

**Subtasks:**
- [ ] 4.5.1 Design Redis data structure
- [ ] 4.5.2 Implement RedisCircuitBreaker
- [ ] 4.5.3 Update get_breaker() to use Redis version
- [ ] 4.5.4 Add fallback to in-memory (fail-closed)
- [ ] 4.5.5 Test across workers
- [ ] 4.5.6 Verify with ruff and pytest

**Estimated Effort:** 2-3 days

---

## Wave 5: Additional Improvements (Week 8-12)

### 5.1 API Response Format Standardization

**Problem:** Admin API returns inconsistent formats (HTML/JSON/string).

**Solution:** Standardize JSON envelope:
```python
def api_response(data=None, error=None, status=200, meta=None):
    payload = {}
    if data is not None:
        payload["data"] = data
    if meta:
        payload["meta"] = meta
    if error:
        payload["error"] = error
    return jsonify(payload), status
```

**Files to Modify:** `routes/admin/api/*.py`, `app.py` error handlers

**Subtasks:**
- [ ] 5.1.1 Create api_response() helper
- [ ] 5.1.2 Audit all admin API endpoints
- [ ] 5.1.3 Migrate endpoints to standardized format
- [ ] 5.1.4 Update error handlers
- [ ] 5.1.5 Verify with ruff and pytest

**Estimated Effort:** 2 days

---

### 5.2 PATCH Method Support

**Problem:** REST endpoints only support GET, POST, PUT - no PATCH for partial updates.

**Solution:** Add PATCH to sources and webhooks:
```python
@sources_bp.route("/<int:source_id>", methods=["PATCH"])
def update_source_partial(source_id):
    source = Source.query.get_or_404(source_id)
    data = request.get_json()
    if "name" in data:
        source.name = data["name"]
    # ... only update present fields
```

**Files to Modify:**
- `routes/admin/api/sources.py`
- `routes/admin/api/webhooks.py`

**Subtasks:**
- [ ] 5.2.1 Add PATCH to sources API
- [ ] 5.2.2 Add PATCH to webhooks API
- [ ] 5.2.3 Add tests for partial updates
- [ ] 5.2.4 Verify with ruff and pytest

**Estimated Effort:** 1-2 days

---

### 5.3 API Versioning (Prefix)

**Problem:** API routes lack version prefix.

**Solution:** Add `/api/v1/` prefix:
```python
def create_admin_api_blueprint():
    bp = Blueprint("admin_api", __name__, url_prefix="/api/v1")
    # All routes now under /api/v1/
```

**Files to Modify:** All `routes/admin/api/*.py`, `routes/public/feeds.py`

**Subtasks:**
- [ ] 5.3.1 Update admin API blueprint with /api/v1/ prefix
- [ ] 5.3.2 Update public API routes
- [ ] 5.3.3 Update internal callers
- [ ] 5.3.4 Verify with ruff and pytest

**Estimated Effort:** 1-2 days

---

### 5.4 OAuth2/API Token Support

**Problem:** Admin API only supports session-based auth.

**Solution:** Add API token model:
```python
# models.py
class ApiToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
```

**Files to Modify:**
- `models.py` - Add ApiToken model
- `routes/admin/__init__.py` - Add token auth
- Create `routes/admin/api_tokens.py` - Token management

**Subtasks:**
- [ ] 5.4.1 Design API token model
- [ ] 5.4.2 Add ApiToken model + migration
- [ ] 5.4.3 Add token authentication
- [ ] 5.4.4 Add token management UI
- [ ] 5.4.5 Add rate limiting per token
- [ ] 5.4.6 Verify with ruff and pytest

**Estimated Effort:** 3 days

---

### 5.5 Redis-Backed Metrics with Fallback

**Problem:** All metrics in process memory - lost on restart.

**Solution:** Add Redis-backed counters:
```python
def _counter_inc_redis(self, key: str, value: int):
    try:
        redis_client = get_redis_client()
        redis_client.incrby(f"metrics:counter:{key}", value)
    except redis.exceptions.RedisError:
        self._counters[key] += value  # Fallback
```

**Files to Modify:** `services/metrics.py`

**Subtasks:**
- [ ] 5.5.1 Add Redis-backed counter/gauge methods
- [ ] 5.5.2 Preserve in-memory fallback
- [ ] 5.5.3 Add TTL for histograms in Redis
- [ ] 5.5.4 Verify with ruff and pytest

**Estimated Effort:** 4-5 hours

---

### 5.6 Importance-Weighted Context Truncation

**Problem:** `sliding_window_truncate()` treats all content equally.

**Solution:** Priority-based truncation:
```python
def importance_weighted_truncate(
    text: str,
    max_chars: int = 8000,
    key_topics: list[str] = None,
) -> str:
    segments = _split_into_segments(text)
    scored_segments = [(calc_priority(s), s) for s in segments]
    scored_segments.sort(reverse=True)

    result = []
    for priority, segment in scored_segments:
        if len(result) + len(segment) <= max_chars:
            result.append(segment)
    return "".join(result)
```

**Files to Modify:** `services/prompts.py`

**Subtasks:**
- [ ] 5.6.1 Implement importance scoring
- [ ] 5.6.2 Add key_topics boosting
- [ ] 5.6.3 Add configuration to pipeline.yaml
- [ ] 5.6.4 Verify with ruff and pytest

**Estimated Effort:** 2 days

---

### 5.7 FTS5 Index for Article Search

**Problem:** Title/URL search uses ILIKE with leading wildcard.

**Solution:** Create FTS5 virtual table:
```sql
CREATE VIRTUAL TABLE articles_fts USING fts5(
    original_title, original_author,
    content='articles', content_rowid='id'
);
```

**Files to Modify:**
- Create migration `030_add_fts5_search.py`
- `routes/admin/api/articles.py` - Update search query

**Subtasks:**
- [ ] 5.7.1 Create FTS5 migration
- [ ] 5.7.2 Update search query to use FTS5
- [ ] 5.7.3 Benchmark before/after
- [ ] 5.7.4 Verify with ruff and pytest

**Estimated Effort:** 2 days

---

### 5.8 Container Queries Support

**Problem:** Card layouts use viewport-based media queries.

**Solution:** Add container queries:
```css
.article-feed {
  container-type: inline-size;
  container-name: feed;
}

@supports (container-type: inline-size) {
  .article-card {
    width: 100cqi;
  }
}
```

**Files to Modify:** `static/css/articles.css`

**Subtasks:**
- [ ] 5.8.1 Add container-type to feed containers
- [ ] 5.8.2 Add container queries for cards
- [ ] 5.8.3 Keep auto-fit fallback
- [ ] 5.8.4 Test in Chrome, Firefox, Safari

**Estimated Effort:** 2-3 hours

---

### 5.9 CSS @layer Organization

**Problem:** No CSS layer organization.

**Solution:**
```css
@layer reset, variables, layout, components, pages, utilities;

@import "./variables.css" layer(variables);
@import "./layout.css" layer(layout);
/* etc */
```

**Files to Modify:** `static/css/style.css` or create `main.css`

**Subtasks:**
- [ ] 5.9.1 Create layer structure
- [ ] 5.9.2 Add @layer directives
- [ ] 5.9.3 Test rendering unchanged

**Estimated Effort:** 2 hours

---

### 5.10 LLM Token-Aware Truncation

**Problem:** Hardcoded 8000 char limit not token-aware.

**Solution:** Add token counting option:
```python
def sliding_window_truncate(text, max_chars=8000, model=None):
    if model and token_counter:
        tokens = count_tokens(text, model)
        if tokens > max_tokens_for_model(model):
            # Truncate based on token count
    return text[:max_chars]
```

**Files to Modify:** `services/prompts.py`, `tasks/write.py`, `tasks/edit.py`

**Subtasks:**
- [ ] 5.10.1 Add token counting option
- [ ] 5.10.2 Pass model context to truncation
- [ ] 5.10.3 Verify with ruff and pytest

**Estimated Effort:** 1 day

---

## Implementation Order Summary

| Wave | Items | Timeline | Can Parallelize |
|------|-------|----------|-----------------|
| **Wave 1** | 1.1-1.6 (CSS, Celery, Cache, EnvVar) | Week 1-2 | Yes - 4 agents |
| **Wave 2** | 2.1-2.9 (SMTP, Dashboard, Queries, Webhooks, HMAC, Audit, Cache) | Week 2-4 | Yes - 3-4 agents |
| **Wave 3** | 3.1-3.8 (Validation, Indexes, OTel, Exception handling, Schema) | Week 4-6 | Yes - 2-3 agents |
| **Wave 4** | 4.1-4.5 (LLM improvements) | Week 6-8 | Yes - 2 agents |
| **Wave 5** | 5.1-5.10 (Additional features) | Week 8-12 | Yes - 2-3 agents |

---

## Verification Protocol

All changes must pass:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Dependencies by Wave

**Wave 1:**
- 1.4 (CSS consolidation) depends on 1.5 (deduplication)

**Wave 2:**
- 2.7 (cache invalidation) can parallel with 2.6 (audit logging)

**Wave 3:**
- 3.3 (OTel tracing) has no dependencies

**Wave 4:**
- 4.1 (memory summarization) can parallel with 4.2 (quality infrastructure)
- 4.3 (tool selection) depends on understanding existing infrastructure

---

## Risk Assessment

| Priority | Risk | Mitigation |
|----------|------|------------|
| **Critical** | Celery acks_late changes | Test worker crash recovery thoroughly |
| **Critical** | CSS consolidation | Thorough visual testing, maintain backup |
| **High** | SMTP connection pool | Add connection health checks, monitor |
| **High** | Cache blpop changes | Test stampede with multiple workers |
| **Medium** | FTS5 migration | Test on copy of production data |

---

## Notes for Future Agents

1. **Subagent parallelization:** Waves 1-3 items can be implemented by separate agents working in parallel on different files/functional areas.

2. **Test first:** For each item, write tests before making changes to ensure the fix is verifiable.

3. **Preserve fallback layers:** The codebase has good fallback patterns (e.g., ResponseCache has multiple fallback strategies). Preserve these when making changes.

4. **Configuration-driven:** Many items support configuration via `pipeline.yaml` or environment variables. Use this pattern when adding new features.

5. **Existing patterns:** Before implementing, search for existing patterns in the codebase (e.g., `commit()` helper in routes/decorators.py, `get_response_cache()` pattern).

---

## Files to Modify Summary

| Category | Files |
|----------|-------|
| **Tasks** | tasks/select.py, tasks/research.py, tasks/write.py, tasks/edit.py, tasks/crawl.py, tasks/extract.py, tasks/newsletter.py, tasks/retry.py, tasks/cleanup.py, tasks/scheduler.py, tasks/webhook.py (new) |
| **Services** | services/cache.py, services/email.py, services/subagent.py, services/llm/base.py, services/llm/*.py, services/prompts.py, services/quality.py (new), services/tool_selection.py (new), services/circuit_breaker.py, services/logging_utils.py, services/metrics.py |
| **Routes** | routes/admin/dashboard.py, routes/admin/api/articles.py, routes/admin/api/webhooks.py, routes/admin/review.py, routes/admin/sources.py, routes/admin/articles.py, routes/admin/topic_notes.py, routes/admin/trend_memory.py, routes/admin/pipelines.py, routes/admin/newsletters.py, routes/admin/api/config.py, routes/admin/__init__.py, routes/admin/api/sources.py |
| **Models** | models.py |
| **Schemas** | schemas/common.py, schemas/llm.py, schemas/admin.py (new) |
| **CSS** | static/css/critical.css, static/css/layout.css, static/css/variables.css, static/css/articles.css, static/css/style.css |
| **Templates** | templates/partials/condensed_article.html |
| **Config** | config.py |
| **Migrations** | migrations/versions/030_*.py (new) |

---

## Plan Review Log

| Date | Reviewer | Notes |
|------|----------|-------|
| 2026-04-30 | Initial review | Consolidated 8 plans into single plan |
| 2026-04-30 | Verification pass | Confirmed items against codebase, corrected claims |
| 2026-04-30 | Wave organization | Organized for parallelization |

---

*End of consolidated plan*
# Implementation Plan — Consolidated

**Created:** April 22, 2026
**Last Updated:** April 23, 2026
**Status:** PLANNED — Not started
**Total Items:** ~75 across 8 waves

---

## Overview

This plan consolidates all improvement items from plans 2-10. Items are organized into waves based on:
1. **Priority** — Critical items first
2. **Parallelization potential** — Items affecting different files can run concurrently
3. **Dependencies** — Some items must complete before others

**Wave Structure:**
- Wave 1: Critical Security (Templates/XSS) — 6 items, can parallelize by file
- Wave 2: High-Priority Security & Config — 5 items, mostly independent
- Wave 3: Performance (Critical) — 4 items, can parallelize with other waves
- Wave 4: Error Handling & Reliability — 4 items, can parallelize
- Wave 5: Database Indexes & Migrations — 6 items, sequential (migration order)
- Wave 6: Test Infrastructure — 5 items, can parallelize
- Wave 7: Code Quality & Configuration — 10 items, can parallelize
- Wave 8: Frontend (CSS/Build) — 7 items, some dependencies

---

## Deferred Items (from previous plan.md)

These items were intentionally deferred and remain deferred:

| Item | Source | Reason |
|------|--------|--------|
| E.2: Celery Task Event Streaming | plan.md | Requires celery.events.RealityMonitor or pubsub consumer, Redis streaming, MetricsCollector updates — not practical |
| E.3: Structured Tool Result Format | plan4.md | Already implemented via `esc_xml_text` in `services/prompts.py` — 65+ uses across codebase |
| E.4: Celery Worker Network Isolation | plan4.md | Requires hosting platform + CI/CD that don't exist |
| 2.6: Dashboard Event-Based Invalidation | plan5.md | 60-second TTL covers the need — event-based adds 150+ LOC for marginal benefit |
| 1.1: CI/CD Pipeline | plan5.md | Requires project to be hosted on platform with GitHub Actions or equivalent |

---

## WAVE 1: Critical Security — XSS & Input Validation

**Target:** Template files, routes validation
**Parallelization:** Items can run in parallel by agent — each handles different files
**Estimated Time:** ~90 minutes total (parallel)

### 1.1 CRITICAL — Admin Article Edit Form XSS

**Files:** `templates/admin/article_edit.html`
**Risk:** Stored XSS allows execution of malicious scripts when admin views the edit page.

**Required Changes:**

| Line | Field | Current | Fix |
|------|-------|---------|-----|
| 48 | headline | `value="{{ fa.get('headline', '')... }}"` | Add `\|e` |
| 53 | tldr | `<textarea>{{ fa.get('tldr', '')... }}</textarea>` | Add `\|e` |
| 58 | why_it_matters | `<textarea>{{ fa.get('why_it_matters', '')... }}</textarea>` | Add `\|e` |
| 63 | body | `<textarea>{{ fa.get('body', '')... }}</textarea>` | Add `\|e` |
| 68 | what_to_watch | `<textarea>{{ fa.get('what_to_watch', '')... }}</textarea>` | Add `\|e` |
| 73 | key_points | `<textarea>{{ '\n'.join(...) }}</textarea>` | Add `\|e` |
| 79 | tags | `value="{{ ', '.join(...) }}"` | Add `\|e` |
| 28-31 | error | `{{ error }}` | Add `\|e` |

**Example:**
```html
<!-- Line 48: Add |e to headline value -->
value="{{ (fa.get('headline', '') if fa else article.original_title or '') | e }}"
```

**Action Items:**
- [ ] Fix line 48 — add `|e` to headline value
- [ ] Fix line 53 — add `|e` to tldr textarea
- [ ] Fix line 58 — add `|e` to why_it_matters textarea
- [ ] Fix line 63 — add `|e` to body textarea
- [ ] Fix line 68 — add `|e` to what_to_watch textarea
- [ ] Fix line 73 — add `|e` to key_points textarea
- [ ] Fix line 79 — add `|e` to tags input
- [ ] Fix lines 28-31 — add `|e` to error message

---

### 1.2 CRITICAL — Admin Dead Letters Page XSS

**Files:** `templates/admin/dead_letters.html`

**Required Changes:**

| Line | Current | Fix |
|------|---------|-----|
| 66 | `{{ article.original_title if article.original_title else '(no title)' }}` | Add `\|e` |
| 106 | `{{ article.original_title if article.original_title else '(no title)' }}` | Add `\|e` |

**Note:** Lines 65 and 105 correctly use `{{ article.original_title|e }}` in title attributes.

**Action Items:**
- [ ] Fix line 66 — add `|e` to article title
- [ ] Fix line 106 — add `|e` to article title

---

### 1.3 HIGH — Public Template XSS

**Files:** `templates/article.html`, `templates/partials/condensed_article.html`

**Required Changes:**

| File | Line | Field | Fix |
|------|------|-------|-----|
| `templates/article.html` | 3 | `{{ article.original_title }}` in `<title>` | `{{ article.original_title|e }}` |
| `templates/partials/condensed_article.html` | 88 | `{{ article.writer_model }}` | `{{ article.writer_model|e }}` |

**Action Items:**
- [ ] Fix `templates/article.html:3` — add `|e` filter to `article.original_title` in `<title>`
- [ ] Fix `templates/partials/condensed_article.html:88` — add `|e` filter to `article.writer_model`

---

### 1.4 HIGH — Bulk Article IDs Validation

**Files:** `routes/admin/api/articles.py`

**Current:** `bulk_article_operations()` doesn't validate that `article_ids` elements are integers.

**Required Changes:**
```python
# Add after length check (line ~188)
from services.validation import validate_bulk_ids

try:
    article_ids = validate_bulk_ids(article_ids)
except ValueError as e:
    return jsonify({"error": str(e)}), 400
```

**Note:** `validate_bulk_ids()` exists in `services/validation.py:90` but is NOT used by this endpoint.

**Action Items:**
- [ ] Import `validate_bulk_ids` from `services.validation`
- [ ] Call `validate_bulk_ids(article_ids)` before the query
- [ ] Handle `ValueError` with proper error response

---

### 1.5 HIGH — WEBHOOK_SECRET_KEY Documentation

**Files:** `.env.example`, `docs/configuration.md`

**Required Changes:**

Add to `.env.example`:
```bash
# Webhook secret encryption key (44 base64 characters)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
WEBHOOK_SECRET_KEY=
```

Add to `docs/configuration.md` in Optional variables section:
```markdown
| WEBHOOK_SECRET_KEY | Yes | Fernet key for webhook secret encryption |
```

**Action Items:**
- [ ] Add `WEBHOOK_SECRET_KEY` to `.env.example` with generation instructions
- [ ] Add `WEBHOOK_SECRET_KEY` to `docs/configuration.md`

---

## WAVE 2: High-Priority Security & Configuration

**Target:** Security infrastructure, config files
**Parallelization:** Items are independent
**Estimated Time:** ~4 hours total (parallel)

### 2.1 CRITICAL — Redis TLS/SSL Connection Security

**Files:** `extensions.py`, `services/config_cache.py`, `config.py`, `docs/security.md`

**Risk:** All Redis traffic transmitted in plaintext. Man-in-the-middle attacks possible.

**Required Changes:**

1. **Add SSL support to connection pools** (`extensions.py:106-113`):
```python
redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
ssl_enabled = redis_url.startswith("rediss://") or os.environ.get("REDIS_SSL") == "true"

pool = redis.ConnectionPool.from_url(
    redis_url,
    max_connections=100,
    socket_timeout=5,
    socket_connect_timeout=3,
    socket_keepalive=True,
    ssl=ssl_enabled,
)
```

2. **Update config cache** (`services/config_cache.py:248`):
```python
ssl_enabled = url.startswith("rediss://") or os.environ.get("REDIS_SSL") == "true"
pool = redis.ConnectionPool.from_url(url, max_connections=20, socket_timeout=5, ssl=ssl_enabled)
```

3. **Update documentation** (`docs/security.md`):
   - Add "Redis TLS/SSL required for all Redis connections" requirement
   - Document `REDIS_SSL=true` env var
   - Document `rediss://` protocol support

4. **Environment variable support:**
   - `REDIS_SSL=true` — Force TLS regardless of protocol
   - `REDIS_SSL=false` — Disable TLS regardless of protocol

**Action Items:**
- [ ] Add TLS support to `extensions.py` Redis pool
- [ ] Add TLS support to `config_cache.py` Redis pool
- [ ] Update Celery broker URL handling for TLS
- [ ] Document in `docs/security.md`
- [ ] Add tests for TLS connections
- [ ] Update `.env.example` with Redis TLS variables

---

### 2.2 HIGH — DEBUG Mode Enforcement in Production

**Files:** `config.py`, `app.py`

**Risk:** Accidental DEBUG mode enables may expose sensitive stack traces.

**Required Changes:**

Add to `ProductionConfig.validate()` (`config.py`):
```python
if cls.DEBUG:
    errors.append("DEBUG must be False in production")
```

Optional: Add `FLASK_DEBUG` env var check (`app.py`):
```python
flask_debug = os.environ.get("FLASK_DEBUG", "").lower()
if flask_debug == "true" and config_name == "production":
    raise RuntimeError("FLASK_DEBUG cannot be used with production config")
```

**Action Items:**
- [ ] Add DEBUG check to `ProductionConfig.validate()`
- [ ] Add test for DEBUG enforcement
- [ ] (Optional) Check `FLASK_DEBUG` env var

---

### 2.3 MEDIUM — Celery Task Signature Verification for Beat Tasks

**Files:** `tasks/cleanup.py`, `config.py`

**Risk:** `cleanup_old_article_versions` accepts args from Beat without HMAC signing.

**Required Changes:**

1. **Add signature verification to `cleanup_old_article_versions`** (`tasks/cleanup.py`):
```python
from services.task_security import verify_task

@shared_task(...)
def cleanup_old_article_versions(self, days_to_keep: int = 90, dry_run: bool = False):
    if not verify_task("cleanup_old_article_versions", (), {"days_to_keep": days_to_keep, "dry_run": dry_run}):
        raise ValueError("Invalid task signature")
```

2. **Update beat schedule in `config.py`** to sign kwargs:
```python
from services.task_security import sign_task

# In get_beat_schedule():
"kwargs": sign_task(
    "cleanup_old_article_versions",
    (),
    {"days_to_keep": versions_days, "dry_run": False}
),
```

**Note:** `sign_task()` returns unsigned dict if `CELERY_TASK_SECRET` not configured (fail-closed behavior).

**Action Items:**
- [ ] Add `verify_task()` to `cleanup_old_article_versions`
- [ ] Update beat schedule in `config.py` to include signed kwargs

---

### 2.4 MEDIUM — Health Endpoint Information Disclosure

**Files:** `routes/public/__init__.py`, `services/health.py`

**Risk:** Unauthenticated `/health?detailed=true` exposes git commit hash and pool stats.

**Required Changes:**

Option A — Require auth for detailed mode (preferred):
```python
@public_bp.route("/health")
def health() -> tuple[Response, int]:
    detailed = request.args.get("detailed", "false").lower() == "true"
    if detailed and not session.get("admin"):
        detailed = False  # Downgrade if not authenticated
    result = run_health_checks(include_celery=True, detailed=detailed)
```

**Action Items:**
- [ ] Implement auth check for detailed health endpoint
- [ ] Add test for detailed mode with/without auth

---

### 2.5 MEDIUM — Missing Environment Variables Documentation

**Files:** `.env.example`, `docs/configuration.md`

**Risk:** 15+ environment variables used in code are not documented.

**Required Changes:**

Add to `.env.example`:
```bash
# === REQUIRED FOR PRODUCTION ===

# HMAC signing secret for Celery tasks (min 32 characters)
CELERY_TASK_SECRET=

# Fernet encryption key for webhook secrets (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
WEBHOOK_SECRET_KEY=

# Public site URL for newsletter links (no trailing slash)
SITE_URL=https://ainews.example.com

# === REDIS ===

# Redis password (if authentication enabled)
REDIS_PASSWORD=

# === SEARCH PROVIDERS ===

# Google Custom Search API (for web search)
GOOGLE_API_KEY=
GOOGLE_CSE_ID=

# === LLM PROVIDERS (Optional) ===

# Uncomment and fill in as needed
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
XAI_API_KEY=
TOGETHERAI_API_KEY=
FIREWORKS_API_KEY=
CEREBRAS_API_KEY=
ZAI_API_KEY=
MINIMAX_API_KEY=
OPENCODE_API_KEY=

# === OPERATIONAL (Optional) ===

# Content extraction timeout in seconds (default: 30)
CONTENT_EXTRACTOR_TIMEOUT=30

# Logging format: json or text (default: json)
LOG_FORMAT=json

# Rate limit default (default: 60 per minute)
RATELIMIT_DEFAULT=60 per minute

# Duplicate detection window in days (default: 7)
DUPLICATE_DETECTION_DAYS=7

# Ollama configuration (if using local models)
OLLAMA_MODEL=llama3.1
OLLAMA_HOST=http://localhost:11434
```

**Action Items:**
- [ ] Add critical production variables to `.env.example`
- [ ] Add search provider variables
- [ ] Add LLM provider variables
- [ ] Add operational configuration variables

---

## WAVE 3: Critical Performance Improvements

**Target:** Query optimization, caching
**Parallelization:** Items are independent
**Estimated Time:** ~6 hours total (parallel)

### 3.1 CRITICAL — SLA Metrics Query SQL Aggregation

**Files:** `routes/admin/api/pipeline.py`

**Risk:** OOM for large date ranges; 30-day query could consume ~750MB+

**Current:** Loads ALL articles into memory, then computes stats in Python.

**Solution:** Use SQLite window functions (`ROW_NUMBER() OVER()`) to compute percentiles in SQL.

**Implementation:**

Add helper function after imports:
```python
def _compute_duration_stats(session, Article, cutoff, start_col, end_col, base_filters=None):
    """Compute avg/p50/p95 for a duration in SQL."""
    if base_filters is None:
        base_filters = []

    duration_expr = (func.julianday(end_col) - func.julianday(start_col)) * 86400
    base_filters = base_filters + [start_col.isnot(None), end_col.isnot(None)]

    # Count
    total = session.query(func.count()).filter(*base_filters).scalar()
    if total == 0:
        return {"avg": None, "p50": None, "p95": None}

    # AVG
    avg = session.query(func.avg(duration_expr)).filter(*base_filters).scalar()

    # P50 and P95 using ROW_NUMBER() window function
    p50_subq = session.query(
        duration_expr.label('duration'),
        func.row_number().over(order_by=duration_expr).label('rn'),
        total.label('total')
    ).filter(*base_filters).subquery()

    p50_offset = (total // 2) + 1
    p95_offset = max(1, int(total * 0.95))

    p50 = session.query(p50_subq.c.duration).filter(p50_subq.c.rn == p50_offset).scalar()
    p95 = session.query(p50_subq.c.duration).filter(p50_subq.c.rn == p95_offset).scalar()

    return {
        "avg": round(avg, 1) if avg else None,
        "p50": round(p50, 1) if p50 else None,
        "p95": round(p95, 1) if p95 else None,
    }
```

Replace the `articles = ... .all()` block with:
```python
base_filters = [Article.published_at.isnot(None), Article.published_at >= cutoff]

c2s = _compute_duration_stats(db.session, Article, cutoff, Article.crawled_at, Article.selected_at, base_filters)
s2p = _compute_duration_stats(db.session, Article, cutoff, Article.selected_at, Article.published_at, base_filters)
c2p = _compute_duration_stats(db.session, Article, cutoff, Article.crawled_at, Article.published_at, base_filters)
```

**Action Items:**
- [ ] Add `_compute_duration_stats()` helper function
- [ ] Replace `articles = ... .all()` block with SQL-side computation
- [ ] Remove Python loops that build duration lists
- [ ] Update import to include `func` from sqlalchemy if not present

---

### 3.2 CRITICAL — N+1 Query Fix in Public Feeds

**Files:** `routes/public/feeds.py`

**Risk:** N+1 queries on homepage load.

**Current:** `article.source` triggers separate query per article.

**Required Changes:**
```python
# Add to imports:
from sqlalchemy.orm import joinedload

# Before (line ~37):
articles = Article.query.filter(Article.id.in_(cached_ids)).all()

# After:
articles = (
    Article.query
    .options(joinedload(Article.source), joinedload(Article.tags))
    .filter(Article.id.in_(cached_ids))
    .all()
)
```

**Action Items:**
- [ ] Add `joinedload(Article.source)` to `_get_top_impact()` query at line 37
- [ ] Add `joinedload(Article.tags)` for defensive consistency

---

### 3.3 CRITICAL — Cache Invalidation Scoping

**Files:** `routes/public/feeds.py`, `routes/public/links.py`, `routes/admin/articles.py`, `routes/admin/review.py`

**Risk:** Admin operations blast public cache, causing cache churn.

**Solution:** Namespace public cache keys with `pub:` prefix.

**Changes:**

`routes/public/feeds.py`:
```python
# Line 31: top_impact cache key
cache_key = f"pub:top_impact:{limit}"

# Line 69: index page cache key
cache_key = f"pub:index:page:{page}:cat:{category}:q:{query}"

# Line 113: topic cache key
cache_key = f"pub:topic:{category}:page:{page}"

# Line 199: rss_feed all cache key
cache_key = f"pub:rss_feed:all:{site_url}"

# Line 242: rss_feed category cache key
cache_key = f"pub:rss_feed:{category}:{site_url}"
```

`routes/public/links.py`:
```python
# Line 30: article detail cache key
cache_key = f"pub:article_detail:{article_id}"
```

`routes/admin/articles.py:284-286`:
```python
# Change from:
cache.invalidate_prefix("index")
cache.invalidate_prefix("topic")
cache.invalidate_prefix("rss")

# To:
cache.invalidate_prefix("pub:index")
cache.invalidate_prefix("pub:topic")
cache.invalidate_prefix("pub:rss")
```

`routes/admin/review.py:91-95`:
```python
# Same prefix changes
cache.invalidate_prefix("pub:index")
cache.invalidate_prefix("pub:topic")
if article.category:
    cache.invalidate_prefix(f"pub:topic:{article.category}")
```

**Action Items:**
- [ ] Update all public cache keys in `routes/public/feeds.py` with `pub:` prefix
- [ ] Update `routes/public/links.py` cache key with `pub:` prefix
- [ ] Update admin invalidation calls in `routes/admin/articles.py`
- [ ] Update admin invalidation calls in `routes/admin/review.py`

---

### 3.4 HIGH — Provider Info Caching

**Files:** `services/llm/__init__.py`

**Risk:** Uncached API call on every dashboard load; latency + rate limit risk.

**Current:** `get_provider_info()` → `provider.health_check()` → `client.models.list()` (HTTP API call)

**Solution:** Wrap in `ResponseCache.get_or_set()` with 5-minute TTL.

**Implementation:**
```python
def get_provider_info() -> dict:
    from services.cache import get_response_cache
    cache = get_response_cache()

    def _fetch():
        provider = get_provider()
        return provider.health_check()

    try:
        return cache.get_or_set("llm:provider:info", _fetch, ttl=300)
    except Exception:
        # Fallback to uncached if Redis unavailable
        return _fetch()
```

**Action Items:**
- [ ] Wrap `get_provider_info()` with ResponseCache in `services/llm/__init__.py`
- [ ] Set TTL to 300 seconds (5 minutes)
- [ ] Add fallback for Redis unavailability

---

## WAVE 4: Error Handling & Reliability

**Target:** Pipeline error handling, retry configuration
**Parallelization:** Items are independent
**Estimated Time:** ~2 hours total (parallel)

### 4.1 CRITICAL — JSON Parse Without Error Handling in Edit Stage

**Files:** `tasks/edit.py`

**Risk:** Malformed `final_article` causes pipeline crash. Article stuck in EDITING.

**Current:** `json.loads()` without try/except at line 270-274.

**Required Changes:**
```python
if isinstance(final_article, str):
    try:
        fa = json.loads(final_article)
    except json.JSONDecodeError as e:
        logger.warning("Malformed final_article JSON for article %d: %s", article.id, e)
        # Use draft_article as fallback
        if isinstance(article.draft_article, str):
            try:
                fa = json.loads(article.draft_article)
            except json.JSONDecodeError:
                fa = {"headline": article.original_title, "body": "", "tldr": ""}
        else:
            fa = {"headline": article.original_title, "body": "", "tldr": ""}
else:
    fa = final_article
```

**Action Items:**
- [ ] Add try/except around `json.loads(final_article)` at line 270
- [ ] Implement fallback to `draft_article` on parse failure
- [ ] Add final fallback with original_title if both fail

---

### 4.2 CRITICAL — Silent Duplicate Check Failure in Extract

**Files:** `tasks/extract.py`

**Risk:** Duplicate detection fails silently, creating duplicate articles.

**Current:** Exception in `_find_duplicate_article()` is swallowed.

**Required Changes:**
```python
try:
    duplicate = _find_duplicate_article(source_id, url, title, text_content)
except Exception as e:
    logger.warning("Dedup check failed for %s: %s", url, e)
    duplicate = None
    # Emit metric for monitoring
    metrics.increment("pipeline.dedup_check_failed", tags={"source": source_key})
```

**Action Items:**
- [ ] Add metric emission on dedup check failure
- [ ] Consider failing the stage if dedup is critical (configurable)

---

### 4.3 MEDIUM — Redis Error Handling in get_or_set()

**Files:** `services/cache.py`

**Risk:** When Redis is unavailable, `get_or_set()` raises unhandled `RedisError`.

**Current:** Lines 136, 150, 155 make raw Redis calls without exception handling.

**Required Changes:**
```python
try:
    if self._redis.set(lock_key, "1", nx=True, ex=10):
        # ...
except redis.exceptions.RedisError as e:
    logger.warning("Failed to acquire cache lock for %s: %s", lock_key, e)
    # Fall through to compute value directly without stampede protection
    value = loader_fn()
    self.set(key, value, ttl)
    return value
```

**Action Items:**
- [ ] Wrap lines 136, 150, 155 in try/except for `redis.exceptions.RedisError`
- [ ] Add proper fallback logging instead of bare `except Exception`
- [ ] Verify `get()` and `set()` error handling still works correctly

---

### 4.4 MEDIUM — Missing Retry Configuration in generate_daily_newsletters

**Files:** `tasks/newsletter.py`

**Risk:** Without `retry_jitter`, concurrent failures create thundering herd.

**Current:** Missing `autoretry_for`, `retry_backoff`, `retry_jitter` in decorator.

**Required Changes:**
```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
```

**Action Items:**
- [ ] Add `autoretry_for=(ConnectionError, TimeoutError)`
- [ ] Add `retry_backoff=True`
- [ ] Add `retry_backoff_max=300`
- [ ] Add `retry_jitter=True`

---

## WAVE 5: Database Indexes & Migrations

**Target:** Database schema
**Parallelization:** Sequential (migration order matters)
**Estimated Time:** ~2 hours total

### 5.1 Create Migration for Missing Indexes

**Files:** `migrations/versions/` (new files)

**Required Migrations:**

1. **025_article_pipeline_status_partial_indexes.py** — For dead-letter queries
```python
# Index for FAILED articles
op.create_index("ix_articles_pipeline_status_failed", "articles", ["updated_at"],
    unique=False, where="pipeline_status = 'failed'")
# Index for REVIEW articles
op.create_index("ix_articles_pipeline_status_review", "articles", ["impact_score"],
    unique=False, where="pipeline_status = 'review'")
# Index for active/stuck articles
op.create_index("ix_articles_pipeline_status_active", "articles", ["updated_at"],
    unique=False, where="pipeline_status IN ('pending', 'researching', 'writing', 'editing')")
```

2. **026_subscriber_active_index.py** — For newsletter delivery
```python
op.create_index("ix_subscribers_active_deleted", "subscribers", ["active", "deleted_at"], unique=False)
```

3. **027_webhook_event_index.py** — For event history queries
```python
op.create_index("ix_webhook_events_webhook_delivered", "webhook_events", ["webhook_id", "delivered_at"], unique=False)
```

4. **028_pipeline_run_type_status_index.py** — For admin dashboard
```python
op.create_index("ix_pipeline_runs_type_status", "pipeline_runs", ["run_type", "status"], unique=False)
```

5. **029_audit_log_action_index.py** — For audit log analysis
```python
op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"], unique=False)
```

**Action Items:**
- [ ] Create migration `025_article_pipeline_status_partial_indexes.py`
- [ ] Create migration `026_subscriber_active_index.py`
- [ ] Create migration `027_webhook_event_index.py`
- [ ] Create migration `028_pipeline_run_type_status_index.py`
- [ ] Create migration `029_audit_log_action_index.py`
- [ ] Apply migrations: `flask db upgrade`

---

### 5.2 Bulk Operations Transaction Ordering

**Files:** `routes/admin/api/articles.py`

**Risk:** Cache invalidation happens BEFORE DB commit. If commit fails, stale cache.

**Required Changes:**
```python
# For _bulk_set_category, _bulk_reprocess, _bulk_add_tags:

# Step 1: DB changes
for article in articles:
    article.category = new_category

# Step 2: Commit FIRST
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    return jsonify({"error": "Failed to update articles"}), 500

# Step 3: Cache invalidation AFTER successful commit
try:
    from services.cache import get_response_cache
    cache = get_response_cache()
    for article in articles:
        cache.invalidate(f"article_detail:{article.id}")
    cache.invalidate_prefix("articles:list")
except redis.exceptions.RedisError as e:
    logger.error("Cache invalidation failed after DB commit: %s", e)
```

**Action Items:**
- [ ] Fix `_bulk_set_category` transaction ordering
- [ ] Fix `_bulk_reprocess` transaction ordering
- [ ] Fix `_bulk_add_tags` transaction ordering

---

### 5.3 Unbounded Memory in Duplicate Detection

**Files:** `services/article.py`

**Risk:** `find_duplicate_titles()` loads ALL matching articles into memory.

**Required Changes:**
```python
rows = (
    Article.query.filter(
        Article.source_id != source_id,
        Article.created_at >= cutoff,
        Article.original_title.isnot(None),
    )
    .filter(
        db.func.length(db.func.replace(Article.original_title, " ", "")) + 1
        >= min_words,
        db.func.length(db.func.replace(Article.original_title, " ", "")) + 1
        <= max_words,
    )
    .order_by(Article.created_at.desc())  # Prefer recent articles
    .with_entities(Article.id, Article.original_title)
    .limit(1000)  # Bound memory: max ~1000 articles at once
    .all()
)
```

**Action Items:**
- [ ] Add `ORDER BY created_at.desc()` before `.all()`
- [ ] Add `.limit(1000)` before `.all()`

---

## WAVE 6: Test Infrastructure

**Target:** Test fixtures and helpers
**Parallelization:** Items can parallelize
**Estimated Time:** ~4 hours total

### 6.1 Create Shared MockRedis Fixture

**Files:** `tests/conftest.py`

**Required Changes:**
```python
@pytest.fixture
def mock_redis_client():
    """In-memory Redis mock with real side effects."""
    from tests.mock_redis import MockRedis
    return MockRedis()
```

**Action Items:**
- [ ] Create `mock_redis_client` fixture in conftest.py
- [ ] Update tests needing stateful Redis to use new fixture

---

### 6.2 Add Autouse DNS Cache Clear Fixture

**Files:** `tests/conftest.py`

**Required Changes:**
```python
from services.url import _dns_cache

@pytest.fixture(autouse=True)
def _clear_dns_cache():
    """Clear DNS cache before and after each test to prevent cross-test contamination."""
    _dns_cache.clear()
    yield
    _dns_cache.clear()
```

**Action Items:**
- [ ] Add `_clear_dns_cache` autouse fixture to conftest.py
- [ ] Remove duplicate fixtures from individual test files

---

### 6.3 Create Celery Task Test Helper

**Files:** `tests/helpers/celery.py` (new file)

**Required Implementation:**
```python
import os
from contextlib import contextmanager
from unittest.mock import MagicMock
import uuid

@contextmanager
def celery_task_context(app, task_fn, secret="test-secret-key-at-least-32-chars-long"):
    """Context manager for Celery task testing."""
    with patch.dict("os.environ", {"CELERY_TASK_SECRET": secret}):
        with app.app_context():
            task_self = MagicMock()
            task_self.request.id = f"task-{uuid.uuid4().hex[:8]}"
            yield task_self

def call_task(task_fn, *args, app=None, **kwargs):
    """Call a Celery task's __wrapped__ method with proper setup."""
    # Implementation...
```

**Action Items:**
- [ ] Create `tests/helpers/celery.py` with helper functions
- [ ] Update key test files to use the helper

---

### 6.4 Add ResponseCache Test Fixture

**Files:** `tests/conftest.py`

**Required Changes:**
```python
@pytest.fixture
def response_cache_setup(mock_redis_client):
    """Provide ResponseCache with mocked Redis for testing."""
    from services.cache import ResponseCache
    cache = ResponseCache()
    cache._redis = mock_redis_client
    return cache
```

**Action Items:**
- [ ] Create `response_cache_setup` fixture in conftest.py
- [ ] Update tests to use shared fixture

---

### 6.5 Missing Test Coverage

**Files:** `tests/` (new test files)

**Required Tests:**

1. **Task HMAC Signing Tests** (`tests/test_task_security.py`):
   - `test_sign_task_creates_valid_signature`
   - `test_verify_task_accepts_valid_signature`
   - `test_verify_task_rejects_tampered_signature`
   - `test_verify_task_fails_closed_on_missing_secret`
   - `test_verify_task_allows_internal_call`

2. **Webhook Delivery Tracking Tests** (`tests/test_webhooks.py`):
   - `test_dispatch_creates_event_record`
   - `test_trigger_event_only_calls_subscribed_webhooks`
   - `test_webhook_idempotency_prevents_duplicate_events`
   - `test_webhook_retry_on_failure`

3. **Subscriber Export Streaming Tests** (add to `tests/test_admin_api.py`):
   - `test_export_subscribers_streams_csv`
   - `test_export_subscribers_correct_format`

4. **Trend Memory Tests** (`tests/test_trend_memory.py`):
   - 4 tests for the trend memory system

**Action Items:**
- [ ] Create `tests/test_task_security.py` with 5 HMAC tests
- [ ] Create `tests/test_webhooks.py` with 4 webhook tests
- [ ] Add 2 export tests to `tests/test_admin_api.py`
- [ ] Create `tests/test_trend_memory.py` with 4 trend memory tests

---

## WAVE 7: Code Quality & Configuration

**Target:** Code quality improvements
**Parallelization:** Items are independent
**Estimated Time:** ~5 hours total

### 7.1 Exception Handling Improvements

**Files:** `models.py`, `adapters/web.py`, `routes/admin/api/articles.py`

**Required Changes:**

1. **`models.py:29`** — `decode_short_url`:
```python
except (ValueError, TypeError):
    return None
```

2. **`adapters/web.py:117`** — Add logging:
```python
except Exception as e:
    logger.debug("Trafilatura extraction failed: %s", e)
    pass
```

3. **`routes/admin/api/articles.py:148`** — Change `except Exception` to `except SQLAlchemyError`

**Action Items:**
- [ ] Fix `decode_short_url` exception handling
- [ ] Add logging to trafilatura fallback
- [ ] Change `except Exception` to `except SQLAlchemyError` in articles.py

---

### 7.2 Redis Version Conflict

**Files:** `requirements.txt`

**Current:** `requirements.txt` says `>=7.0.0,<8.0.0` but `pyproject.toml` pins `==6.4.0`.

**Required Change:**
```diff
# requirements.txt line 10
- redis>=7.0.0,<8.0.0
+ redis==6.4.0
```

**Action Items:**
- [ ] Align `requirements.txt` Redis version to `pyproject.toml`

---

### 7.3 Beat Schedule Cleanup

**Files:** `config.py`

**Risk:** `CeleryBeatConfig.CELERY_BEAT_SCHEDULE` is dead code.

**Required Changes:**
```python
class CeleryBeatConfig:
    """DEPRECATED: Use get_beat_schedule() instead.

    This class attribute is kept for reference only.
    Actual beat schedule is loaded from pipeline.yaml.
    """
    CELERY_BEAT_SCHEDULE = {}  # Empty - replaced by get_beat_schedule()
```

**Action Items:**
- [ ] Add deprecation comment to CeleryBeatConfig class attribute
- [ ] Verify get_beat_schedule() is used everywhere

---

### 7.4 Code Quality: Low Priority

**Files:** Various

**Required Changes:**

1. **Citation lazy loading** (`models.py`):
```python
citations = db.relationship("Citation", backref="article", lazy="selectin", cascade="all, delete-orphan")
```

2. **Dead fixture removal** (`tests/conftest.py`):
   - Remove `_reset_factory_counter` fixture (dead code)

3. **SoftTimeLimitExceeded work loss** (`tasks/pipeline.py`):
   - Persist failure state (last_error, retry_count) before raising

4. **Tag.articles backref** (`models.py`):
```python
articles = db.relationship("Article", secondary=article_tags, backref=db.backref("tags", lazy="selectin"), lazy="dynamic")
```

5. **Trend memory deduplication** (`services/trend_memory.py`):
   - Add `_is_duplicate_signal()` function

6. **Subagent chain escaping fix** (`services/subagent.py`):
   - Add re-escape for step results in chain processing

7. **ModelLimiter initial poll interval** (`services/limiter.py`):
   - Adjust initial poll_interval from 0.05s to 0.1s

8. **ResponseCache second SET NX fix** (`services/cache.py`):
   - Add double-check before second SET NX

9. **Stage failure TTL refresh** (`services/pipeline_failure.py`):
   - Add TTL refresh on each stage failure

10. **Trend memory batch consolidation** (`services/trend_memory.py`):
    - Batch query for consolidate_all_topics()

11. **L1 cache sampled eviction** (`services/cache.py`):
    - Add periodic cleanup task for L1 cache

12. **Batch commit for trend memory** (`services/trend_memory.py`):
    - Commit all entries in single transaction

**Action Items:**
- [ ] Change `lazy="select"` to `lazy="selectin"` for citations
- [ ] Remove dead `_reset_factory_counter` fixture
- [ ] Implement SoftTimeLimitExceeded handler fix
- [ ] Add Tag.articles backref
- [ ] Add `_is_duplicate_signal()` for trend memory
- [ ] Fix subagent chain re-escaping
- [ ] Adjust ModelLimiter poll interval
- [ ] Fix ResponseCache second SET NX
- [ ] Add stage failure TTL refresh
- [ ] Batch consolidate trend memory
- [ ] Add L1 cache cleanup task
- [ ] Batch commit trend memory entries

---

## WAVE 8: Frontend (CSS/Build)

**Target:** CSS architecture and build pipeline
**Parallelization:** Items have some dependencies
**Estimated Time:** ~5 hours total

### 8.1 HIGH — Critical CSS and Layout CSS Duplication

**Files:** `static/css/layout.css`, `static/css/critical.css`

**Risk:** 12 classes duplicated across files, maintenance hazard.

**Required Changes:**

Refactor `layout.css` to only add **responsive overrides and additional states**, not re-declare base rules:

1. **Audit all 12 duplicated classes** (`.nav`, `.logo`, `.logo-slash`, `.nav-links`, `.nav-meta`, `.nav-tag`, `.container`, `.site-header`, `.site-footer`, `.htmx-indicator`, `.htmx-request #content`, `.nav-toggle-label`)

2. **Remove duplicate definitions from `layout.css`**

3. **Move responsive overrides to `layout.css` only**

4. **Remove internal `.nav-tag` duplicate in `layout.css`** (lines 108-115)

**Example refactor for `.nav`:**
```css
/* critical.css — keep base definition */
.nav {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 0.75rem 1.25rem;
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

/* layout.css — ONLY add responsive overrides */
@media (max-width: 640px) {
  .nav {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
}
```

**Action Items:**
- [ ] Audit all 12 duplicated classes
- [ ] Remove duplicate definitions from `layout.css`
- [ ] Move responsive overrides to `layout.css` only
- [ ] Remove internal `.nav-tag` duplicate in `layout.css`
- [ ] Verify no visual regression after refactor

---

### 8.2 HIGH — Theme Toggle and Icon Duplication

**Files:** `static/css/components.css`

**Required Changes:**
Remove `.theme-toggle` and `.theme-icon-light` from `components.css` — keep only in `critical.css`.

**Action Items:**
- [ ] Remove `.theme-toggle` rules from `components.css`
- [ ] Remove `.theme-icon-light` rules from `components.css`

---

### 8.3 MEDIUM — Add CSS/JS Minification and Bundling

**Files:** Build pipeline, `templates/base.html`, `templates/base_admin.html`

**Required Changes:**

1. **Install esbuild**:
```bash
npm install -g esbuild
```

2. **Create Makefile target**:
```makefile
build-assets: ## Minify and bundle CSS/JS for production
	esbuild static/css/style.css --bundle --minify --outfile=static/css/style.min.css
	esbuild static/js/app.js static/js/theme.js static/js/share-a11y.js --bundle --minify --outfile=static/js/app.min.js

.PHONY: build-assets
```

3. **Update templates** (`base.html`, `base_admin.html`):
```html
<!-- Replace individual CSS files -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/style.min.css') }}">

<!-- Replace individual JS files -->
<script src="{{ url_for('static', filename='js/app.min.js') }}" defer></script>
<!-- htmx.min.js stays separate — vendor file -->
```

4. **Add to `.gitignore`**:
```
*.min.css
*.min.js
```

**Action Items:**
- [ ] Add `esbuild` to project
- [ ] Create Makefile target `build-assets`
- [ ] Update `base.html` and `base_admin.html` to use minified assets
- [ ] Add `build-assets` to deployment/CI process
- [ ] Add `*.min.css` and `*.min.js` to `.gitignore`

---

### 8.4 LOW — CSS Token Duplication Comment

**Files:** `static/css/critical.css`

**Required Changes:**

Add comment to `critical.css`:
```css
/*
 * IMPORTANT: Tokens are duplicated in this file AND variables.css.
 * Any changes must be made to BOTH files to prevent color flash on first paint.
 * See: AGENTS.md - "CSS consolidation note"
 */
```

**Action Items:**
- [ ] Add comment to critical.css about token duplication

---

### 8.5 LOW — Accessibility Improvements

**Files:** `static/js/app.js`, `static/css/components.css`

**Optional Items:**

1. **Sync aria-expanded on page load** (`app.js`):
```javascript
document.querySelectorAll(".share-details[open]").forEach(function(details) {
  var summary = details.querySelector("summary");
  if (summary) {
    summary.setAttribute("aria-expanded", "true");
  }
});
```

2. **Explicit toast reduced-motion** (`components.css`):
```css
@media (prefers-reduced-motion: reduce) {
  .toast {
    animation: none;
    opacity: 1;
  }
}
```

**Action Items:**
- [ ] Add sync logic for pre-opened details elements (optional)
- [ ] Evaluate if explicit toast reduced-motion is needed (optional)

---

## Implementation Order

```
WAVE 1: Critical Security (XSS)        ~90 min    — 6 items, parallelize by file
WAVE 2: High-Priority Security/Config   ~4 hrs     — 5 items, parallelize
WAVE 3: Critical Performance            ~6 hrs     — 4 items, parallelize
WAVE 4: Error Handling/Reliability      ~2 hrs     — 4 items, parallelize
WAVE 5: Database Indexes                 ~2 hrs     — Sequential (migrations)
WAVE 6: Test Infrastructure             ~4 hrs     — 5 items, parallelize
WAVE 7: Code Quality                    ~5 hrs     — 15 items, parallelize
WAVE 8: Frontend                        ~5 hrs     — Some dependencies

Total estimated: ~28 hours across all waves
```

---

## Wave Dependencies

```
Wave 1 ─┬─► Wave 2 ─┬─► Wave 3 ─┬─► Wave 4 ─┬─► Wave 5 ─┬─► Wave 6 ─┬─► Wave 7 ─┬─► Wave 8
        │           │           │           │           │           │
        └───────────┴───────────┴───────────┴───────────┴───────────┴───────────┘
                        (All waves can start after Wave 1 completes)
```

**Note:** Waves can overlap — while Wave 5 (migrations) runs sequentially, Wave 6-8 can start after earlier waves complete.

---

## Sub-Agent Recommendations

### Agent Pool Structure

**For maximum parallelization, use 4 agents:**

1. **Agent-Security (Waves 1-2)**: Handles all security-related items (XSS, Redis TLS, DEBUG enforcement, task signing, health endpoint)

2. **Agent-Performance (Wave 3)**: Handles SLA aggregation, N+1 fixes, cache scoping, provider caching

3. **Agent-Reliability (Waves 4-5)**: Handles error handling, duplicate detection, migrations, bulk operations

4. **Agent-Quality (Waves 6-8)**: Handles test infrastructure, code quality, CSS/build pipeline

### Key Context for Sub-Agents

**Shared Context (needed by all agents):**
- Run `.venv/bin/ruff check . --exclude .venv` before committing
- Run `.venv/bin/python -m pytest tests/ -x -q` after changes
- Use `commit_or_rollback()` context manager for db operations
- Catch `redis.exceptions.RedisError` for Redis operations

**Wave 1 (Security) agents need:**
- Jinja2 template escaping: use `|e` filter for all user/LLM content
- `validate_bulk_ids()` exists in `services/validation.py:90`

**Wave 3 (Performance) agents need:**
- SQLAlchemy `func` and `func.julianday()` for datetime arithmetic
- `joinedload()` import from `sqlalchemy.orm`

**Wave 5 (Migrations) agents need:**
- Run `flask db upgrade` after creating migrations
- SQLite doesn't support `op.create_unique_constraint` — use application-level enforcement

**Wave 8 (Frontend) agents need:**
- CSS module architecture: `critical.css` (inlined), `style.css` (imports modules)
- Do NOT import `critical.css` in `style.css`

---

## Rollback Plan

| Change | Rollback Method |
|--------|----------------|
| XSS fixes | Remove `|e` filters |
| Redis TLS | Remove `ssl=` parameter |
| DEBUG enforcement | Remove check from `ProductionConfig.validate()` |
| SLA SQL aggregation | Revert to `.all()` + Python loops |
| N+1 feeds fix | Remove `joinedload()` calls |
| Cache scoping | Remove `pub:` prefix from keys |
| Database indexes | `flask db downgrade <migration>` |
| Test fixtures | Revert conftest.py changes |

---

## Appendix A: Complete Issue Summary

| ID | Wave | Priority | Category | Severity | File(s) | Description |
|----|------|----------|----------|----------|---------|-------------|
| XSS-001 | 1 | CRITICAL | XSS | CRITICAL | templates/admin/article_edit.html | Form values without escaping |
| XSS-002 | 1 | CRITICAL | XSS | CRITICAL | templates/admin/dead_letters.html | Title text without escaping |
| XSS-003 | 1 | HIGH | XSS | HIGH | templates/article.html | Missing `|e` on original_title |
| XSS-004 | 1 | HIGH | XSS | HIGH | templates/partials/condensed_article.html | Missing `|e` on writer_model |
| VAL-001 | 1 | HIGH | Validation | HIGH | routes/admin/api/articles.py | Missing integer validation |
| DOC-001 | 1 | HIGH | Documentation | HIGH | .env.example, docs/configuration.md | Missing WEBHOOK_SECRET_KEY |
| SEC-001 | 2 | CRITICAL | TLS | CRITICAL | extensions.py, config_cache.py | No TLS for Redis |
| SEC-002 | 2 | HIGH | Config | HIGH | config.py | DEBUG warning-only enforcement |
| SEC-003 | 2 | MEDIUM | Task | MEDIUM | tasks/cleanup.py | cleanup_old_article_versions lacks signing |
| SEC-004 | 2 | MEDIUM | Info | MEDIUM | services/health.py | Detailed health leaks system info |
| SEC-005 | 2 | MEDIUM | Config | MEDIUM | .env.example | Missing env vars |
| PERF-001 | 3 | CRITICAL | Memory | CRITICAL | routes/admin/api/pipeline.py | SLA loads all articles |
| PERF-002 | 3 | CRITICAL | N+1 | CRITICAL | routes/public/feeds.py | Missing joinedload on source |
| PERF-003 | 3 | CRITICAL | Cache | CRITICAL | routes/admin/articles.py | Overbroad invalidation |
| PERF-004 | 3 | HIGH | API | HIGH | services/llm/__init__.py | Uncached provider info |
| ERR-001 | 4 | CRITICAL | Error | CRITICAL | tasks/edit.py:270 | json.loads without error handling |
| ERR-002 | 4 | CRITICAL | Error | CRITICAL | tasks/extract.py:154 | Silent dedup check failure |
| ERR-003 | 4 | MEDIUM | Error | MEDIUM | services/cache.py:136,150,155 | Missing Redis error handling |
| ERR-004 | 4 | MEDIUM | Celery | MEDIUM | tasks/newsletter.py:351 | Missing retry_jitter |
| DB-001 | 5 | MEDIUM | Index | MEDIUM | migrations/versions/* | Missing partial indexes |
| DB-002 | 5 | MEDIUM | Transaction | MEDIUM | routes/admin/api/articles.py | Bulk ops cache-before-commit |
| DB-003 | 5 | HIGH | Memory | HIGH | services/article.py:289 | Unbounded duplicate detection |
| TEST-001 | 6 | MEDIUM | Test | MEDIUM | conftest.py | No shared MockRedis fixture |
| TEST-002 | 6 | MEDIUM | Test | MEDIUM | conftest.py | No autouse DNS cache clear |
| TEST-003 | 6 | MEDIUM | Test | MEDIUM | tests/helpers/ | No Celery task test helper |
| TEST-004 | 6 | MEDIUM | Test | MEDIUM | conftest.py | No ResponseCache fixture |
| TEST-005 | 6 | MEDIUM | Test | MEDIUM | tests/ | Missing critical tests |
| CQ-001 | 7 | HIGH | Dependency | HIGH | requirements.txt | Redis version conflict |
| CQ-002 | 7 | MEDIUM | Error | MEDIUM | models.py:29 | Broad exception in decode_short_url |
| CQ-003 | 7 | MEDIUM | Config | MEDIUM | config.py | Duplicate beat schedule definition |
| CQ-004 | 7 | LOW | Code | LOW | models.py:139 | Citation lazy loading |
| CQ-005 | 7 | LOW | Code | LOW | tests/conftest.py:39 | Dead fixture |
| CQ-006 | 7 | LOW | Reliability | LOW | tasks/pipeline.py:275 | SoftTimeLimitExceeded work loss |
| FE-001 | 8 | HIGH | CSS | HIGH | critical.css, layout.css | 12 classes duplicated |
| FE-002 | 8 | HIGH | CSS | HIGH | components.css | .theme-toggle duplicated |
| FE-003 | 8 | MEDIUM | Build | MEDIUM | Makefile, templates | No minification/bundling |
| FE-004 | 8 | LOW | CSS | LOW | critical.css | Add token duplication comment |
| FE-005 | 8 | LOW | A11y | LOW | app.js | Sync aria-expanded on load |

---

## Testing Requirements

### Before any changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After each wave:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Wave-specific verification:

**Wave 1 (XSS):**
```bash
# Manual: Navigate to /admin/articles/<id>/edit with crafted final_article
# Verify <script>alert('xss')</script> in any field does NOT execute
```

**Wave 3 (Performance):**
```bash
# Verify SLA endpoint returns same JSON structure
curl -s "http://localhost:5000/admin/api/pipeline/sla?days=7" | python -m json.tool

# Verify cache keys use pub: prefix
redis-cli keys "pub:*"
```

**Wave 5 (Migrations):**
```bash
# Verify EXPLAIN QUERY PLAN shows index usage
./scripts/query_analysis.sh
```

---

*End of consolidated plan*
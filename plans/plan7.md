# Performance Improvement Plan - Plan 7

**Date:** 2026-04-28  
**Scope:** Comprehensive performance improvements based on codebase deep dive  
**Priority Order:** Critical → High → Medium → Low

---

## Executive Summary

Performance review identified **13 distinct issues** across the ainews codebase:
- **3 Critical** (missing DB indexes, cache invalidation gaps, sitemap TTL mismatch)
- **3 High** (N+1 queries, unused queries, dashboard bugs)
- **6 Medium** (stampede protection, eager loading, date filters, thread pool issues)
- **1 Low** (L1 cache monitoring)

**Estimated Impact:**
- **Query performance:** 4 new DB indexes eliminating table scans
- **Cache consistency:** Fix 11+ mutation points missing invalidation
- **Correctness:** Fix dashboard bug (missing `source_type`, `last_crawled`)
- **Resource efficiency:** Fix thread leak, tune pool sizes

---

## 1. CRITICAL PRIORITY

### 1.1 Add Missing Database Indexes

**Files:** `migrations/versions/030_missing_query_indexes.py` (new), `models.py` (optional update for `__table_args__`)

**Findings from Deep Dive:**
- `PipelineRun (status, started_at)` - HIGH priority, used in dashboard queries
- `Citation (article_id, url)` - MEDIUM priority, duplicate detection
- `WebhookEvent (webhook_id, delivered_at)` - LOW-MEDIUM priority
- `WebhookEvent (webhook_id, event_type, idempotency_key)` - LOW priority

**NOT needed:** `extraction_status` (no queries), `original_title` (ILIKE wildcards can't use B-tree), `subscribers` (partially covered by existing index)

**Implementation Steps:**

1. Create migration file `migrations/versions/030_missing_query_indexes.py`:
```python
"""add missing composite indexes for query performance

Revision ID: 030_missing_query_indexes
Revises: 029_sources_health_indexes
"""

from alembic import op

revision = '030_missing_query_indexes'
down_revision = '029_sources_health_indexes'


def upgrade() -> None:
    op.create_index("ix_pipeline_runs_status_started", "pipeline_runs", 
                   ["status", "started_at"], unique=False)
    op.create_index("ix_citations_article_url", "citations", 
                   ["article_id", "url"], unique=False)
    op.create_index("ix_webhook_events_webhook_delivered", "webhook_events", 
                   ["webhook_id", "delivered_at"], unique=False)
    op.create_index("ix_webhook_events_webhook_event_idempotency", "webhook_events", 
                   ["webhook_id", "event_type", "idempotency_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_webhook_events_webhook_event_idempotency", table_name="webhook_events")
    op.drop_index("ix_webhook_events_webhook_delivered", table_name="webhook_events")
    op.drop_index("ix_citations_article_url", table_name="citations")
    op.drop_index("ix_pipeline_runs_status_started", table_name="pipeline_runs")
```

2. Update `models.py` `__table_args__` (optional, for documentation):
```python
__table_args__ = (
    db.UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
    db.Index("ix_articles_status_created", "pipeline_status", "created_at"),
    db.Index("ix_articles_published", "original_published_at"),
    db.Index("ix_articles_impact", "impact_score"),
    db.Index("ix_articles_category_status", "category", "pipeline_status"),
)
# Note: New indexes added via migration 030
```

3. Test migration:
```bash
.venv/bin/flask db upgrade
sqlite3 instance/ainews.db ".schema pipeline_runs"
sqlite3 instance/ainews.db "EXPLAIN QUERY PLAN SELECT * FROM pipeline_runs WHERE status='running' ORDER BY started_at DESC LIMIT 100;"
```

---

### 1.2 Fix Cache Invalidation Gaps

**Files to Modify:**
- `services/cache.py` (add `invalidate_article_mutations()` helper)
- `routes/admin/api/articles.py` (bulk operations)
- `routes/admin/articles.py` (single article ops)
- `routes/admin/review.py` (approve/reject)
- `tasks/edit.py` (post-finalize, clear_tag_cache)
- `tasks/extract.py` (article creation)
- `routes/admin/shares.py` (share config mutations)

**Critical Bug Found:** `routes/admin/articles.py:290` and `routes/admin/review.py:94` use `"pub:rss"` but actual keys are `"pub:rss_feed:*"`. **Invalidation is silently failing.**

**Implementation Steps:**

1. **Add shared helper in `services/cache.py`** (after line 230):
```python
def invalidate_article_mutations(article_id: int | None = None, categories: list[str] | None = None) -> None:
    """Invalidate all caches affected by article mutations.
    
    Call this after any article create/update/delete operation.
    """
    from services.config_cache import get_config_cache
    
    cache = get_response_cache()
    
    # ResponseCache invalidation
    if article_id:
        cache.invalidate(f"pub:article_detail:{article_id}")
    
    cache.invalidate_prefix("pub:index")
    cache.invalidate_prefix("pub:topic")
    cache.invalidate_prefix("pub:rss_feed")  # FIXED: was "pub:rss"
    cache.invalidate("pub:sitemap:xml")
    cache.invalidate_prefix("pub:top_impact")
    cache.invalidate_prefix("pub:related")
    cache.invalidate_prefix("articles:list")
    
    # Also invalidate category-specific topic pages
    if categories:
        for cat in categories:
            cache.invalidate_prefix(f"pub:topic:{cat}")
    
    # ConfigCache invalidation (affects templates)
    try:
        get_config_cache().invalidate("tag_cloud")
        get_config_cache().invalidate("share_configs")
    except Exception as e:
        logger.warning("Failed to invalidate ConfigCache: %s", e)
```

2. **Fix `routes/admin/articles.py`:**
   - Line 290: Change `cache.invalidate_prefix("pub:rss")` to `cache.invalidate_prefix("pub:rss_feed")`
   - Add invalidation to `delete_article()` (after line 396):
     ```python
     try:
         from services.cache import invalidate_article_mutations
         invalidate_article_mutations(article_id, [article.category] if article.category else None)
     except Exception as e:
         logger.warning("Cache invalidation failed: %s", e)
     ```
   - Add invalidation to `reprocess_article()` (after line 434)

3. **Fix `routes/admin/review.py`:**
   - Line 94: Change `cache.invalidate_prefix("pub:rss")` to `cache.invalidate_prefix("pub:rss_feed")`
   - Add invalidation to `reject_article()` (line 109-133)

4. **Update `routes/admin/api/articles.py`:**
   Add to all bulk operations (delete, set_status, set_category, reprocess, add_tags):
   ```python
   try:
       from services.cache import invalidate_article_mutations
       invalidate_article_mutations()
   except Exception as e:
       logger.warning("Bulk cache invalidation failed: %s", e)
   ```

5. **Update `tasks/edit.py`:**
   - Update `clear_tag_cache()` (lines 62-67) to also clear ConfigCache:
     ```python
     def clear_tag_cache() -> None:
         """Clear the tag cache (call after tag changes)."""
         global _TAG_CACHE, _TAG_CACHE_TIME
         with _TAG_CACHE_LOCK:
             _TAG_CACHE = None
             _TAG_CACHE_TIME = 0
         
         # Also clear the ConfigCache tag_cloud
         from services.config_cache import get_config_cache
         try:
             get_config_cache().invalidate("tag_cloud")
         except Exception:
             logger.warning("Failed to invalidate tag_cloud cache")
     ```
   - Add invalidation to `_post_finalize_article()` (after line 217)

6. **Update `tasks/extract.py`:**
   Add after article creation in `process_item()` (after line 372):
   ```python
   try:
       from services.cache import get_response_cache
       cache = get_response_cache()
       cache.invalidate_prefix("pub:rss_feed")
       cache.invalidate("pub:sitemap:xml")
       cache.invalidate_prefix("pub:top_impact")
   except Exception as e:
       logger.warning("Cache invalidation failed for new article: %s", e)
   ```

7. **Update `routes/admin/shares.py`:**
   Add to `add_share()`, `edit_share()`, `delete_share()`, `toggle_share()`:
   ```python
   from services.config_cache import get_config_cache
   get_config_cache().invalidate("share_configs")
   ```

---

### 1.3 Fix Sitemap TTL Mismatch

**File:** `routes/public/feeds.py` (line 323)

**Problem:** Redis TTL=300s (5 min) but Cache-Control `max-age=3600` (1 hour). Browsers serve stale sitemap for up to 55 minutes after Redis expires.

**Implementation Steps:**

1. **Option A (Simple - Recommended):** Match TTLs at 3600s
   ```python
   # Line 323 - CHANGE FROM:
   cache.set(cache_key, xml, ttl=300)
   
   # LINE 323 - CHANGE TO:
   cache.set(cache_key, xml, ttl=3600)
   ```

2. **Option B (Better):** Add `stale-while-revalidate` like RSS feeds
   ```python
   # Line 323
   cache.set(cache_key, xml, ttl=3600)
   
   # Line 328 - CHANGE FROM:
   headers={"Cache-Control": "public, max-age=3600"},
   
   # LINE 328 - CHANGE TO:
   headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=7200"},
   ```

3. **Option C (Best - Additional):** Add event-driven invalidation
   In `tasks/scheduler.py:publish_scheduled_articles()` after line 57 (`db.session.commit()`):
   ```python
   if published:
       from services.cache import get_response_cache
       cache = get_response_cache()
       cache.invalidate("pub:sitemap:xml")
   ```
   
   In `tasks/edit.py:_post_finalize_article()` after marking article DONE:
   ```python
   from services.cache import get_response_cache
   cache = get_response_cache()
   cache.invalidate("pub:sitemap:xml")
   ```

**Recommended:** Start with Option A (simple TTL match), then add Option C (event-driven invalidation) for true freshness. Option B can be applied alongside Option A.

---

## 2. HIGH PRIORITY

### 2.1 Fix N+1 Query: Article.metrics

**File:** `models.py` (lines 146-148)

**Problem:** `lazy="select"` (default) causes N+1 queries when accessing `article.metrics`.

**Fix:**
```python
# Lines 146-148 - CHANGE FROM:
metrics = db.relationship(
    "ArticleMetric", backref="article", uselist=False, cascade="all, delete-orphan"
)

# CHANGE TO:
metrics = db.relationship(
    "ArticleMetric", backref="article", uselist=False,
    cascade="all, delete-orphan", lazy="selectin"
)
```

**Note:** `lazy="selectin"` uses a separate query to batch-load metrics for all articles in the collection. This is better than `"joined"` for optional one-to-one relationships.

---

### 2.2 Remove Unused Query in Newsletter Tasks

**File:** `tasks/newsletter.py` (lines 322-344 and subtasks)

**Problem:** `_generate_newsletters_impl()` pre-fetches articles (lines 322-327) but subtasks re-query the database. Pre-fetched articles are only used for early return check and executive summary.

**Implementation Steps:**

**Option A (Simple - Recommended):** Remove pre-fetching
1. Remove lines 322-327 (the `all_articles` dictionary comprehension)
2. Remove `all_articles[topic_key]` from task signature (lines 333-340)
3. Remove `articles` parameter from `_generate_topic_newsletter_impl()` (line 128)
4. Update `_generate_topic_newsletter_impl()` to query articles once:
   ```python
    def _generate_topic_newsletter_impl(
        topic_key: str,
        # REMOVED: articles: list,
        site_url: str,
        max_articles: int,
        dry_run_email: str | None,
        nl,
    ) -> dict:
        from datetime import datetime, timedelta, timezone
        from constants import PipelineStatus
        from models import Article
        from services.newsletter import generate_main_newsletter, generate_topic_newsletter
        from services.newsletter_pipeline import generate_executive_summary

        # Query articles once here
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        q = Article.query.filter(
            Article.pipeline_status == PipelineStatus.DONE,
            Article.created_at >= cutoff,
        ).options(joinedload(Article.source), joinedload(Article.tags))

        if topic_key == "main":
            q = q.filter(Article.impact_score > 0)
        else:
            q = q.filter(Article.category == topic_key)

        articles = q.order_by(Article.impact_score.desc()).limit(max_articles).all()

        if not articles:
            return {"type": topic_key, "articles": 0, "sent": 0, "skipped": True}

        # Generate executive summary with articles
        exec_summary = ""
        try:
            result = generate_executive_summary(articles, topic_key=topic_key)
            exec_summary = result["summary"]
        except Exception as e:
            logger.error("%s exec summary failed: %s", topic_key, e)

        # Generate HTML using queried articles
        if topic_key == "main":
            html, subject, count = generate_main_newsletter(
                site_url=site_url,
                max_articles=max_articles,
                executive_summary=exec_summary,
            )
        else:
            html, subject, count = generate_topic_newsletter(
                topic_key=topic_key,
                site_url=site_url,
                max_articles=max_articles,
                executive_summary=exec_summary,
            )
   ```

**Option B (Refactor):** Pass articles to subtasks properly
- Modify `services/newsletter.py` functions to accept optional `articles` parameter
- Pass pre-fetched articles from `_generate_newsletters_impl()`

**Recommended:** Option A (simpler, removes inconsistency)

---

### 2.3 Fix Dashboard Sources Query + Bug

**File:** `routes/admin/dashboard.py` (lines 105-106, 146-172)

**Problem 1 (Bug):** Template `dashboard.html` expects `source_type` and `last_crawled` but Python code only provides `id`, `name`, `active`.

**Problem 2 (Performance):** `Source.query.all()` loads all 14 columns when only 5 are needed.

**Fix:**
```python
# Lines 105-106 - CHANGE FROM:
sources = Source.query.all()
source_count = Source.query.count()

# CHANGE TO:
sources = (
    Source.query
    .with_entities(Source.id, Source.name, Source.source_type, Source.active, Source.last_crawled)
    .order_by(Source.name)
    .all()
)
source_count = Source.query.count()

# Lines 146-148 - CHANGE FROM:
    "sources": [{"id": s.id, "name": s.name, "active": s.active} for s in sources],

# CHANGE TO:
"sources": [
    {"id": s.id, "name": s.name, "source_type": s.source_type,
     "active": s.active, "last_crawled": s.last_crawled}
    for s in sources
],
```

**Testing:** Verify dashboard template renders `source_type` and `last_crawled` correctly.

---

## 3. MEDIUM PRIORITY

### 3.1 Add Stampede Protection to ConfigCache

**File:** `services/config_cache.py` (method `get()`)

**Problem:** Multiple workers calling `config_cache.get("key", loader_fn)` simultaneously will each execute `loader_fn()` independently (no distributed lock).

**Risk:** MEDIUM - configs change infrequently, loaders are cheap, but unnecessary work is done.

**Implementation:** Add per-key Redis locking using same pattern as ResponseCache:

```python
def get(self, key: str, loader_fn: Callable[[], Any], ttl: int = 300) -> Any:
    full_key = f"{self.prefix}:{key}"
    lock_key = f"{self.prefix}:lock:{key}"

    # ... (existing memory cache check code) ...

    # Cache miss - use distributed lock to prevent stampede
    try:
        # Dynamic lock timeout based on TTL
        lock_timeout = max(10, min(ttl // 10, 30))

        if self._redis.set(lock_key, "1", nx=True, ex=lock_timeout):
            try:
                # Re-check cache after acquiring lock
                try:
                    cached = self._redis.get(full_key)
                    if cached is not None:
                        if isinstance(cached, bytes):
                            cached = cached.decode("utf-8")
                        value = _deserialize(cached)
                        with self._lock:
                            self._memory[full_key] = (time.monotonic() + ttl, value)
                        return value
                except redis.exceptions.RedisError:
                    pass

                # Only ONE worker executes this
                value = loader_fn()

                try:
                    self._redis.setex(full_key, ttl, _serialize(value))
                except redis.exceptions.RedisError as e:
                    logger.warning("Config cache write failed for %s: %s", key, e)

                with self._lock:
                    self._memory[full_key] = (time.monotonic() + ttl, value)
                    self._evict_stale()
                return value
            finally:
                # Release the lock
                try:
                    self._redis.delete(lock_key)
                except redis.exceptions.RedisError:
                    pass
        else:
            # Another worker has the lock - poll for completion
            logger.debug("Waiting for config cache lock: %s", key)
            for _ in range(20):  # Poll for up to ~1 second
                try:
                    cached = self._redis.get(full_key)
                    if cached is not None:
                        if isinstance(cached, bytes):
                            cached = cached.decode("utf-8")
                        value = _deserialize(cached)
                        with self._lock:
                            self._memory[full_key] = (time.monotonic() + ttl, value)
                        return value

                except redis.exceptions.RedisError:
                    pass
                time.sleep(0.05)

            # If we get here, compute directly (best effort)
            logger.debug("Lock poll timeout for %s, computing directly", key)
            value = loader_fn()
            try:
                self._redis.setex(full_key, ttl, _serialize(value))
            except redis.exceptions.RedisError:
                pass
            with self._lock:
                self._memory[full_key] = (time.monotonic() + ttl, value)
                self._evict_stale()
            return value

    except redis.exceptions.RedisError as e:
        logger.warning("Failed to acquire config cache lock for %s: %s", key, e)
        # Fail-open: compute directly without locking
        value = loader_fn()
        try:
            self._redis.setex(full_key, ttl, _serialize(value))
        except redis.exceptions.RedisError:
            pass
        with self._lock:
            self._memory[full_key] = (time.monotonic() + ttl, value)
            self._evict_stale()
        return value
```

---

### 3.2 Fix Missing Eager Loading

**Files:**
- `routes/public/feeds.py` (lines 48-65)
- `routes/public/links.py` (line 105)
- `tasks/cleanup.py` (lines 163-167)

**Fix 1:** `routes/public/feeds.py` - `_get_top_impact()`
```python
# Line 52 - CHANGE FROM:
.options(joinedload(Article.source))

# CHANGE TO:
.options(joinedload(Article.source), joinedload(Article.tags))
```

**Fix 2:** `routes/public/links.py` - `short_url_tracking_page()`
```python
# Line 105 - CHANGE FROM:
article = Article.query.filter_by(short_id=short_id).first_or_404()

# CHANGE TO:
article = Article.query.options(
    joinedload(Article.tags),
    joinedload(Article.source)
).filter_by(short_id=short_id).first_or_404()
```

**Fix 3:** `tasks/cleanup.py` - `recalculate_impact_scores()`
```python
# Lines 163-167 - CHANGE FROM:
articles = (
    Article.query.filter(Article.pipeline_status == "done")
    .filter(Article.published_at >= cutoff)
    .join(ArticleMetric, Article.id == ArticleMetric.article_id)
    .all()
)

# CHANGE TO:
articles = (
    Article.query
    .options(joinedload(Article.metrics))
    .filter(Article.pipeline_status == "done")
    .filter(Article.published_at >= cutoff)
    .join(ArticleMetric, Article.id == ArticleMetric.article_id)
    .all()
)
```

---

### 3.3 Add Date Filter to find_related_articles_dicts()

**File:** `services/related.py` (lines 159-169)

**Problem:** Missing 30-day cutoff that `find_related_articles()` has. Inconsistent behavior.

**Fix:**
```python
# Lines 159-169 - CHANGE FROM:
candidates = (
    Article.query.filter(
        Article.id != exclude_id,
        Article.pipeline_status == PipelineStatus.DONE,
        Article.final_article.isnot(None),
    )
    .options(joinedload(Article.source), joinedload(Article.tags))
    .order_by(Article.created_at.desc())
    .limit(50)
    .all()
)

# CHANGE TO:
candidates = (
    Article.query.filter(
        Article.id != exclude_id,
        Article.pipeline_status == PipelineStatus.DONE,
        Article.final_article.isnot(None),
        Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
    )
    .options(joinedload(Article.source), joinedload(Article.tags))
    .order_by(Article.created_at.desc())
    .limit(_RELATED_CANDIDATE_LIMIT)
    .all()
)
```

**Note:** Also change hardcoded `50` to `_RELATED_CANDIDATE_LIMIT` (default 50, configurable via env var).

---

### 3.4 Fix ThreadPoolExecutor Thread Leak in timeout.py

**File:** `services/timeout.py` (lines 48-60)

**Problem:** Creates new `ThreadPoolExecutor` on EVERY function call. Should use module-level shared executor.

**Fix:**
```python
# ADD at module level (after imports):
import atexit
import functools
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

_TIMEOUT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="timeout")
atexit.register(lambda: _TIMEOUT_EXECUTOR.shutdown(wait=False, cancel_futures=True))

def timeout(seconds: float, operation: Optional[str] = None):
    def decorator(func):
        op_name = operation or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            future = _TIMEOUT_EXECUTOR.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=seconds)
            except FuturesTimeout:
                future.cancel()
                logger.warning("Operation '%s' timed out after %.1fs", op_name, seconds)
                raise OperationTimeoutError(op_name, seconds)

        return wrapper

    return decorator
```

---

### 3.5 Add ThreadPoolExecutor Shutdown Handlers

**Files:**
- `services/content_extractor.py`
- `services/subagent.py`
- `services/article.py`
- `services/search/searxng.py`
- `services/search/google.py`
- `services/search/duckduckgo.py`
- `services/url.py`

**Fix Pattern (apply to each file):**
```python
import atexit

# Existing executor creation (no change)
_CONTENT_EXTRACTOR = ThreadPoolExecutor(
    max_workers=CONTENT_EXTRACTOR_WORKERS,
    thread_name_prefix="content_extract"
)

# ADD shutdown handler
def _shutdown_content_extractor():
    logger.info("Shutting down content extractor thread pool")
    _CONTENT_EXTRACTOR.shutdown(wait=False, cancel_futures=True)

atexit.register(_shutdown_content_extractor)
```

---

### 3.6 Tune ThreadPoolExecutor Default Sizes

**Files:**
- `services/content_extractor.py` (line 16-17)
- `services/subagent.py` (line 28-29)

**Problem:** Default 8 workers each. With Celery concurrency=4, that's 32 threads per worker process.

**Fix:**
```python
# services/content_extractor.py - CHANGE FROM:
CONTENT_EXTRACTOR_WORKERS = int(os.environ.get("CONTENT_EXTRACTOR_WORKERS", "8"))

# CHANGE TO:
CONTENT_EXTRACTOR_WORKERS = int(os.environ.get("CONTENT_EXTRACTOR_WORKERS", "4"))

# services/subagent.py - CHANGE FROM:
SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "8"))

# CHANGE TO:
SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "4"))
```

**Rationale:** For I/O-bound tasks, 4 threads per pool is sufficient. With Celery concurrency=4, that's 16 threads per pool per worker (down from 32).

---

## 4. LOW PRIORITY

### 4.1 Add L1 Cache Monitoring and Metrics

**File:** `services/cache.py`

**Problem:** L1 (in-memory) cache has no separate hit/miss tracking, no eviction metrics, no utilization stats.

**Implementation Steps:**

1. **Add separate L1/L2 counters:**
   ```python
   def __init__(self, redis_client, prefix: str = "ainews:cache"):
       # ... existing code ...
       self._l1_hits = 0
       self._l2_hits = 0
       self._misses = 0
       self._sets = 0
       self._l1_evictions = 0
       self._invalidations = 0
   ```

2. **Update `get()` to track L1 vs L2 hits:**
   ```python
   # In get(), when L1 hit:
   self._l1_hits += 1
   
   # When L2 hit:
   self._l2_hits += 1
   
   # When miss:
   self._misses += 1
   ```

3. **Update `set()` to track evictions:**
   ```python
   if len(self._memory) >= _get_l1_cache_maxsize() and full_key not in self._memory:
       self._memory.popitem(last=False)
       self._l1_evictions += 1
   ```

4. **Update `get_stats()` to include new metrics:**
   ```python
   def get_stats(self) -> dict:
       total = self._l1_hits + self._l2_hits + self._misses
       l1_size = len(self._memory)
       max_size = _get_l1_cache_maxsize()
       
       return {
           "l1_hits": self._l1_hits,
           "l2_hits": self._l2_hits,
           "misses": self._misses,
           "l1_hit_rate": round(self._l1_hits / total, 3) if total > 0 else 0,
           "l2_hit_rate": round(self._l2_hits / total, 3) if total > 0 else 0,
           "hit_rate": round((self._l1_hits + self._l2_hits) / total, 3) if total > 0 else 0,
           "memory_entries": l1_size,
           "memory_max_size": max_size,
           "memory_utilization": round(l1_size / max_size, 3) if max_size > 0 else 0,
           "l1_evictions": self._l1_evictions,
           "sets": self._sets,
           "invalidations": self._invalidations,
       }
   ```

5. **Optional: Log warning when L1 near capacity:**
   ```python
   # In set(), after eviction check:
   current_size = len(self._memory)
   max_size = _get_l1_cache_maxsize()
   if current_size >= max_size * 0.9:
       logger.warning(
           "L1 cache near capacity: %d/%d (%.1f%%)",
           current_size, max_size, (current_size / max_size) * 100
       )
   ```

---

## 5. IMPLEMENTATION ORDER

**Phase 1: Critical (Do First)**
1. 1.3 Fix sitemap TTL mismatch (1 line change, immediate impact)
2. 1.2 Fix RSS cache prefix bug (wrong prefix in 2 files)
3. 1.1 Add missing DB indexes (migration)
4. 1.2 Implement `invalidate_article_mutations()` + apply to all mutation points

**Phase 2: High (Do Next)**
5. 2.1 Fix N+1: Article.metrics (1 line in models.py)
6. 2.3 Fix dashboard query + bug
7. 2.2 Remove unused newsletter pre-fetching

**Phase 3: Medium (Do After)**
8. 3.4 Fix ThreadPoolExecutor leak in timeout.py
9. 3.5 Add shutdown handlers to all ThreadPools
10. 3.6 Tune ThreadPoolExecutor default sizes (8→4)
11. 3.2 Fix missing eager loading (3 small fixes)
12. 3.3 Add date filter to related articles
13. 3.1 Add stampede protection to ConfigCache

**Phase 4: Low (Nice to Have)**
14. 4.1 Add L1 cache monitoring

---

## 6. TESTING STRATEGY

### Pre-Implementation
```bash
# Run existing tests
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Post-Implementation (Per Phase)

**Phase 1 Tests:**
```bash
# Test DB indexes
sqlite3 instance/ainews.db "EXPLAIN QUERY PLAN SELECT * FROM pipeline_runs WHERE status='running' ORDER BY started_at DESC LIMIT 100;"

# Test cache invalidation
# - Create/update/delete article via admin UI
# - Check that RSS/sitemap cache is invalidated

# Test sitemap TTL
curl -I http://localhost:5000/sitemap.xml  # Check Cache-Control header matches Redis TTL
```

**Phase 2 Tests:**
```bash
# Test N+1 fix
# - Query articles with metrics in template
# - Check SQL log for N+1 (should see batch query)

# Test dashboard fix
# - Load /admin/ page
# - Verify source_type and last_crawled are displayed
```

**Phase 3 Tests:**
```bash
# Test ThreadPoolExecutor fixes
# - Restart Celery worker
# - Check logs for shutdown messages
# - Verify no thread leaks under load

# Test eager loading
# - Access top impact page
# - Check SQL log for proper JOINs
```

**Phase 4 Tests:**
```bash
# Test L1 cache monitoring
# - Access /admin/api/cache/stats (after adding endpoint)
# - Verify L1/L2 hit separation
# - Check eviction tracking
```

---

## 7. ROLLBACK PLAN

### If Migration 030 Causes Issues:
```bash
.venv/bin/flask db downgrade 029
```

### If Cache Invalidation Causes Issues:
- Revert changes to `services/cache.py` (remove `invalidate_article_mutations()`)
- Revert changes to mutation points (they worked before without invalidation, just less efficient)

### If Any Fix Causes Regressions:
```bash
git revert <commit-hash>  # Revert specific change
```

---

## 8. SUCCESS METRICS

After implementation, measure:

1. **DB Query Performance:**
   - `EXPLAIN QUERY PLAN` shows index usage for PipelineRun queries
   - No full table scans on Citations or WebhookEvents

2. **Cache Consistency:**
   - New articles appear in RSS/sitemap within TTL period
   - Tag cloud updates after tag changes
   - Share config changes appear immediately

3. **Correctness:**
   - Dashboard shows `source_type` and `last_crawled`
   - No N+1 queries in SQL logs
   - No thread leaks under load

4. **Resource Efficiency:**
   - Thread count per Celery worker reduced (check with `ps -L`)
   - L1 cache hit rate >80% (if monitoring added)

---

## APPENDIX: File Change Summary

| File | Priority | Change Type | Lines Changed |
|------|----------|--------------|---------------|
| `migrations/versions/030_*.py` | Critical | New file | ~40 lines |
| `services/cache.py` | Critical | Add helper | ~20 lines |
| `routes/admin/articles.py` | Critical | Bug fix + invalidation | ~30 lines |
| `routes/admin/review.py` | Critical | Bug fix + invalidation | ~15 lines |
| `routes/admin/api/articles.py` | Critical | Add invalidation | ~25 lines |
| `tasks/edit.py` | Critical | Update `clear_tag_cache()` | ~10 lines |
| `tasks/extract.py` | Critical | Add invalidation | ~10 lines |
| `routes/admin/shares.py` | Critical | Add invalidation | ~16 lines |
| `routes/public/feeds.py` | Critical | Fix TTL | 1 line |
| `models.py` | High | N+1 fix | 1 line |
| `tasks/newsletter.py` | High | Remove unused query | ~30 lines |
| `routes/admin/dashboard.py` | High | Bug fix + perf | ~15 lines |
| `services/config_cache.py` | Medium | Stampede protection | ~50 lines |
| `routes/public/feeds.py` | Medium | Eager loading | 1 line |
| `routes/public/links.py` | Medium | Eager loading | ~3 lines |
| `tasks/cleanup.py` | Medium | Eager loading | ~3 lines |
| `services/related.py` | Medium | Date filter | ~3 lines |
| `services/timeout.py` | Medium | Thread leak fix | ~10 lines |
| `services/content_extractor.py` | Medium | Shutdown + tune | ~10 lines |
| `services/subagent.py` | Medium | Shutdown + tune | ~10 lines |
| 5 other ThreadPool files | Medium | Add shutdown | ~8 lines each |
| `services/cache.py` | Low | L1 monitoring | ~30 lines |

**Total Estimated Changes:** ~300 lines across 20 files + 1 new migration

---

## 9. VERIFICATION CHECKLIST

After implementing ALL phases, verify:

### Critical Priority Verification
- [ ] Migration 030 applied: `flask db upgrade` runs successfully
- [ ] Indexes exist: `sqlite3 instance/ainews.db ".indices pipeline_runs"`
- [ ] RSS invalidation works: Change an article, check `pub:rss_feed:*` cache cleared
- [ ] Sitemap TTL match: `curl -I http://localhost:5000/sitemap.xml` shows `Cache-Control: max-age=3600` AND Redis TTL is 3600
- [ ] Cache prefix bug fixed: Search code for `pub:rss"` (without `_feed`) returns no results

### High Priority Verification
- [ ] N+1 fix: `models.py` has `lazy="selectin"` in Article.metrics relationship
- [ ] Dashboard bug fixed: `/admin/` page shows `source_type` and `last_crawled` columns
- [ ] Newsletter pre-fetching removed: `tasks/newsletter.py` no longer has `all_articles = {` at line 322-327
- [ ] Dashboard query optimized: `Source.query.all()` replaced with `.with_entities()`

### Medium Priority Verification
- [ ] ConfigCache stampede protection: `services/config_cache.py` has `lock_key` and `set(lock_key, "1", nx=True, ex=...)`
- [ ] Eager loading: `routes/public/feeds.py` has `joinedload(Article.tags)` in `_get_top_impact()`
- [ ] Eager loading: `routes/public/links.py` has `.options(joinedload(Article.tags), joinedload(Article.source))`
- [ ] Related articles date filter: `services/related.py` has `Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30)`
- [ ] Thread leak fixed: `services/timeout.py` uses `_TIMEOUT_EXECUTOR` module-level executor
- [ ] Shutdown handlers: All ThreadPoolExecutor files have `atexit.register(...)`
- [ ] Pool sizes tuned: `CONTENT_EXTRACTOR_WORKERS` and `SUBAGENT_WORKERS` default to 4

### Low Priority Verification
- [ ] L1 cache monitoring: `services/cache.py` has `_l1_hits`, `_l2_hits`, `_l1_evictions` counters
- [ ] Stats updated: `get_stats()` returns `l1_hit_rate`, `l2_hit_rate`, `l1_evictions`

### Code Quality Verification
```bash
# Run linter
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Verify migration chain
.venv/bin/flask db history

# Check for syntax errors in modified files
.venv/bin/python -m py_compile services/cache.py
.venv/bin/python -m py_compile services/config_cache.py
.venv/bin/python -m py_compile tasks/newsletter.py
.venv/bin/python -m py_compile models.py
```

### Integration Testing
```bash
# Start all services
docker compose up -d

# Test cache invalidation end-to-end
# 1. Create article via admin
# 2. Check RSS feed updated within TTL
# 3. Check sitemap updated within TTL

# Test dashboard
curl -s http://localhost:5000/admin/ | grep -q "source_type" && echo "PASS: source_type displayed"

# Test thread pools shutdown
docker compose restart celery-worker
docker compose logs celery-worker | grep -q "Shutting down" && echo "PASS: Thread pools shutdown cleanly"
```

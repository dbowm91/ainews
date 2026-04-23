# Performance Improvement Plan — Full Implementation

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Source**: Performance Review — 2026-04-23

---

## Executive Summary

This plan addresses performance issues identified during a comprehensive performance review of the ainews codebase. The codebase has a solid architectural foundation with proper caching layers, thread pool patterns, and Redis integration. Several areas require optimization to scale efficiently.

| Priority | Category | Issues | Impact |
|----------|----------|--------|--------|
| 🔴 Critical | Memory/Query Issues | SLA endpoint loads all articles, N+1 in feeds | Major |
| 🔴 Critical | Cache Scoping | Overbroad invalidation blasts public cache | Major |
| 🔴 High | LLM Provider | Uncached provider info API call | Latency/Rate limit risk |
| 🟡 Medium | Stampede Risk | Dashboard stats no lock protection | Concurrent recomputation |
| 🟡 Medium | Database Indexes | Missing partial indexes on pipeline_status | Slower dead-letter queries |
| 🟡 Medium | Missing Cache | Related articles, sitemap uncached | Wasted computation |
| 🟢 Low | Query Batching | Duplicate detection N+1 | 30 queries → 1 |
| 🟢 Low | Count Query | Admin articles separate COUNT query | Extra DB round-trip |

---

## Priority 1: 🔴 Critical

### 1.1 SLA Endpoint — SQL-Side Aggregation

**Severity**: CRITICAL
**Risk**: OOM (Out of Memory) for large date ranges; 30-day query could consume ~750MB+

**Current State** (`routes/admin/api/pipeline.py:149-156`):
```python
articles = (
    Article.query.filter(
        Article.published_at.isnot(None),
        Article.published_at >= cutoff,
    )
    .order_by(Article.published_at.desc())
    .all()  # LOADS ALL matching articles into memory
)
```

**Problem**: For 30 days with thousands of articles:
- Each Article object contains heavy fields: `extracted_text`, `final_article`, `research_brief`, `draft_article`
- 3 separate lists built in Python (crawl_to_select, select_to_publish, crawl_to_publish)
- O(n log n) sorting in Python for percentiles

**Solution**: Use SQLite window functions (`ROW_NUMBER() OVER()`) to compute percentiles in SQL. SQLite 3.25+ (2018) supports this.

**Implementation** (`routes/admin/api/pipeline.py`):

Add helper function after imports:
```python
def _compute_duration_stats(
    session,
    Article,
    cutoff,
    start_col,
    end_col,
    base_filters=None,
):
    """Compute avg/p50/p95 for a duration in SQL.

    Args:
        session: SQLAlchemy session
        Article: Article model
        cutoff: datetime cutoff
        start_col: column for start timestamp (e.g., Article.crawled_at)
        end_col: column for end timestamp (e.g., Article.selected_at)
        base_filters: additional base filters

    Returns:
        dict with avg, p50, p95
    """
    if base_filters is None:
        base_filters = []

    # SQLite duration in seconds
    duration_expr = (
        func.julianday(end_col) - func.julianday(start_col)
    ) * 86400

    base_filters = base_filters + [
        start_col.isnot(None),
        end_col.isnot(None),
    ]

    # Count
    total = (
        session.query(func.count())
        .filter(*base_filters)
        .scalar()
    )

    if total == 0:
        return {"avg": None, "p50": None, "p95": None}

    # AVG - single efficient query
    avg = (
        session.query(func.avg(duration_expr))
        .filter(*base_filters)
        .scalar()
    )

    # P50 and P95 using ROW_NUMBER() window function
    # SQLite 3.25+ required
    p50_subq = (
        session.query(
            duration_expr.label('duration'),
            func.row_number().over(order_by=duration_expr).label('rn'),
            total.label('total')
        )
        .filter(*base_filters)
        .subquery()
    )

    p50_offset = (total // 2) + 1  # 1-indexed
    p95_offset = max(1, int(total * 0.95))

    p50 = (
        session.query(p50_subq.c.duration)
        .filter(p50_subq.c.rn == p50_offset)
        .scalar()
    )

    p95 = (
        session.query(p50_subq.c.duration)
        .filter(p50_subq.c.rn == p95_offset)
        .scalar()
    )

    return {
        "avg": round(avg, 1) if avg else None,
        "p50": round(p50, 1) if p50 else None,
        "p95": round(p95, 1) if p95 else None,
    }
```

Replace the `articles = ... .all()` block (lines 149-189) with:
```python
    base_filters = [Article.published_at.isnot(None), Article.published_at >= cutoff]

    c2s = _compute_duration_stats(
        db.session, Article, cutoff, Article.crawled_at, Article.selected_at, base_filters
    )
    s2p = _compute_duration_stats(
        db.session, Article, cutoff, Article.selected_at, Article.published_at, base_filters
    )
    c2p = _compute_duration_stats(
        db.session, Article, cutoff, Article.crawled_at, Article.published_at, base_filters
    )

    return jsonify({
        "period_days": days,
        "article_count": c2s.get("avg") is not None and (
            db.session.query(func.count())
            .filter(*base_filters)
            .scalar()
        ) or 0,
        "sla": {
            "crawl_to_select_avg": c2s["avg"],
            "crawl_to_select_p50": c2s["p50"],
            "crawl_to_select_p95": c2s["p95"],
            "select_to_publish_avg": s2p["avg"],
            "select_to_publish_p50": s2p["p50"],
            "select_to_publish_p95": s2p["p95"],
            "crawl_to_publish_avg": c2p["avg"],
            "crawl_to_publish_p50": c2p["p50"],
            "crawl_to_publish_p95": c2p["p95"],
        },
        "histogram": get_metrics().get_metrics().get("histograms", {}).get(
            "pipeline_sla_seconds", {}
        ),
    })
```

**Action Items**:
- [ ] Add `_compute_duration_stats()` helper function to `routes/admin/api/pipeline.py`
- [ ] Replace `articles = ... .all()` block with SQL-side computation
- [ ] Remove Python loops that build duration lists (lines 181-189)
- [ ] Update import to include `func` from sqlalchemy if not present

**Effort**: 1-2 hours
**Risk**: Low (maintains same JSON output format)
**Tests**: `tests/test_admin_api.py` - verify SLA endpoint returns same structure

---

### 1.2 N+1 Query Fix — joinedload in Public Feeds

**Severity**: CRITICAL
**Risk**: N+1 queries on homepage load

**Current State** (`routes/public/feeds.py:37`):
```python
articles = Article.query.filter(Article.id.in_(cached_ids)).all()
# Templates then access article.source.name → separate query per article
```

**Problem**: `article.source` uses `lazy="dynamic"` on Source.articles backref, triggering a separate query per article when the template renders `article.source.name`.

**Solution**: Add `joinedload(Article.source)` to the query.

**Implementation** (`routes/public/feeds.py:37`):
```python
# BEFORE:
articles = Article.query.filter(Article.id.in_(cached_ids)).all()

# AFTER:
articles = (
    Article.query
    .options(joinedload(Article.source), joinedload(Article.tags))
    .filter(Article.id.in_(cached_ids))
    .all()
)
```

**Action Items**:
- [ ] Add `joinedload(Article.source)` to `_get_top_impact()` query at line 37
- [ ] Add `joinedload(Article.tags)` for defensive consistency (tags already uses selectin)

**Effort**: 10 minutes
**Risk**: None (query returns same data, just more efficiently)

---

### 1.3 Cache Invalidation Scoping

**Severity**: CRITICAL
**Risk**: Admin operations blast public cache, causing cache churn and poor hit rates

**Current State**: Admin code uses `invalidate_prefix("index")` which matches both admin AND public cache keys:
- `pub:index:page:*` (intended invalidation)
- `pub:top_impact:*` (collateral damage on every edit)
- `pub:topic:*` (collateral damage)
- `pub:rss_feed:*` (collateral damage)

**Problem**: When admin edits an article, it calls:
```python
cache.invalidate_prefix("index")   # Also invalidates public index:page:*
cache.invalidate_prefix("topic")   # Also invalidates public topic:*
cache.invalidate_prefix("rss")     # Also invalidates public rss_feed:*
```

**Note**: `invalidate_prefix("articles:list")` in `routes/admin/api/articles.py` only appears in invalidation calls, not as an actual cache key being set. The admin articles list uses `paginate_query()` without a cache layer, so no admin list cache key actually exists. The plan does NOT need to rename this.

**Solution**: Namespace public cache keys with `pub:` prefix so admin invalidation calls target only public keys.

**Files to Change**:

| File | Lines | Change |
|------|-------|--------|
| `routes/public/feeds.py` | 31 | `top_impact:{limit}` → `pub:top_impact:{limit}` |
| `routes/public/feeds.py` | 69 | `index:page:*` → `pub:index:page:*` |
| `routes/public/feeds.py` | 113 | `topic:*` → `pub:topic:*` |
| `routes/public/feeds.py` | 199 | `rss_feed:all:*` → `pub:rss_feed:all:*` |
| `routes/public/feeds.py` | 242 | `rss_feed:{category}:*` → `pub:rss_feed:{category}:*` |
| `routes/public/links.py` | 30 | `article_detail:*` → `pub:article_detail:*` |
| `routes/admin/articles.py` | 284-286 | Change `invalidate_prefix("index")` → `invalidate_prefix("pub:index")` etc. |
| `routes/admin/review.py` | 91-95 | Same prefix changes |

**Detailed Changes**:

`routes/public/feeds.py` — Add `pub:` prefix:
```python
# Line 31:
cache_key = f"pub:top_impact:{limit}"

# Line 69:
cache_key = f"pub:index:page:{page}:cat:{category}:q:{query}"

# Line 113:
cache_key = f"pub:topic:{category}:page:{page}"

# Line 199:
cache_key = f"pub:rss_feed:all:{site_url}"

# Line 242:
cache_key = f"pub:rss_feed:{category}:{site_url}"
```

`routes/public/links.py`:
```python
# Line 30:
cache_key = f"pub:article_detail:{article_id}"
```

`routes/admin/articles.py:284-286`:
```python
# BEFORE:
cache.invalidate_prefix("index")
cache.invalidate_prefix("topic")
cache.invalidate_prefix("rss")

# AFTER:
cache.invalidate_prefix("pub:index")
cache.invalidate_prefix("pub:topic")
cache.invalidate_prefix("pub:rss")
```

`routes/admin/review.py:91-95`:
```python
# BEFORE:
cache.invalidate_prefix("index")
cache.invalidate_prefix("topic")
if article.category:
    cache.invalidate_prefix(f"topic:{article.category}")

# AFTER:
cache.invalidate_prefix("pub:index")
cache.invalidate_prefix("pub:topic")
if article.category:
    cache.invalidate_prefix(f"pub:topic:{article.category}")
```

**Action Items**:
- [ ] Update all public cache keys in `routes/public/feeds.py` with `pub:` prefix
- [ ] Update `routes/public/links.py` cache key with `pub:` prefix
- [ ] Update admin invalidation calls in `routes/admin/articles.py`
- [ ] Update admin invalidation calls in `routes/admin/review.py`
- [ ] Verify no other places use unqualified `index`, `topic`, `rss` prefixes

**Effort**: 1-2 hours
**Risk**: Medium (cache key changes require cache purge; brief cold cache period)

---

### 1.4 Provider Info Caching

**Severity**: HIGH
**Risk**: Uncached API call to LLM provider on every dashboard load; latency + rate limit risk

**Current State**: `get_provider_info()` → `provider.health_check()` → `client.models.list()` (HTTP API call)

**Problem**: No caching layer. Every admin dashboard load triggers a real API call to the LLM provider.

**Solution**: Wrap in `ResponseCache.get_or_set()` with 5-minute TTL.

**Implementation**:

Option A — At dashboard level (`routes/admin/dashboard.py`):
```python
def _get_provider_info_cached():
    from services.llm import get_provider_info
    try:
        return get_provider_info()
    except Exception as e:
        logger.warning("Provider info failed: %s", e)
        return {"status": "error", "error": str(e)}

# In dashboard():
if redis_client:
    try:
        from services.cache import get_response_cache
        cache = get_response_cache()
        llm_info = cache.get_or_set(
            "llm:provider:info",
            _get_provider_info_cached,
            ttl=300  # 5 minutes
        )
    except redis.exceptions.RedisError:
        llm_info = _get_provider_info_cached()
```

Option B — Inside `get_provider_info()` (`services/llm/__init__.py`):
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

**Recommendation**: Option B (inside `get_provider_info()`) — more maintainable, benefits all callers.

**Action Items**:
- [ ] Wrap `get_provider_info()` with ResponseCache in `services/llm/__init__.py`
- [ ] Set TTL to 300 seconds (5 minutes)
- [ ] Add fallback for Redis unavailability

**Effort**: 30 minutes
**Risk**: Low (TTL ensures relatively fresh data; 5 min staleness acceptable for provider info)

---

## Priority 2: 🟡 Medium

### 2.1 Dashboard Stampede Protection

**Severity**: MEDIUM
**Risk**: Thundering herd on cache miss — multiple concurrent requests all recompute stats

**Current State** (`routes/admin/dashboard.py:77-86`):
```python
redis_client.setex(
    _get_dashboard_cache_key(),
    _DASHBOARD_CACHE_TTL,  # 60 seconds
    json.dumps(data),
)
```

**Problem**: Raw `setex` without locking. On cache miss, ALL concurrent requests recompute expensive stats simultaneously.

**Solution**: Use `ResponseCache.get_or_set()` which provides `SET NX EX` stampede protection.

**Implementation** (`routes/admin/dashboard.py`):

Consolidate all stat computation into a single function:
```python
def _compute_dashboard_stats():
    """Compute all dashboard statistics. Called only on cache miss."""
    pipeline_stats = dict(
        db.session.query(Article.pipeline_status, func.count(Article.id))
        .group_by(Article.pipeline_status)
        .all()
    )
    # ... all other stats ...
    return {
        "pipeline_stats": pipeline_stats,
        "sources": [...],
        # ...
    }
```

Then use `get_or_set()`:
```python
if redis_client:
    try:
        from services.cache import get_response_cache
        stats = get_response_cache().get_or_set(
            "dashboard:stats:v2",
            _compute_dashboard_stats,
            ttl=300,  # 5 minutes instead of 60s
        )
        return render_template("admin/dashboard.html", **stats, redis_ok=True)
    except redis.exceptions.RedisError:
        pass  # Fall through to uncached path

# Fallback: compute without caching
stats = _compute_dashboard_stats()
return render_template("admin/dashboard.html", **stats, redis_ok=redis_ok)
```

**Action Items**:
- [ ] Consolidate all stat computation into `_compute_dashboard_stats()`
- [ ] Replace manual cache get/set with `ResponseCache.get_or_set()`
- [ ] Change TTL from 60s to 300s
- [ ] Add Redis error fallback

**Effort**: 1 hour
**Risk**: Low (maintains same output, adds caching + stampede protection)

---

### 2.2 Partial Indexes on pipeline_status

**Severity**: MEDIUM
**Risk**: Slow dead-letter queries, review queue loads

**Current State**: No dedicated index on `pipeline_status` alone. Compound index `ix_articles_status_created` (pipeline_status, created_at) exists but most queries order by `updated_at`, not `created_at`.

**Problem**: Queries filtering `pipeline_status='failed'` with `ORDER BY updated_at DESC` cannot efficiently use the compound index.

**Solution**: Add partial indexes for most common filter patterns.

**Implementation** — Create migration `migrations/versions/025_article_pipeline_status_partial_indexes.py`:

```python
"""add partial indexes on Article.pipeline_status for common query patterns

Revision ID: 025_article_pipeline_status_partial_indexes
Revises: 024_missing_query_indexes
Create Date: 2026-04-23
"""

from alembic import op


def upgrade() -> None:
    # Index for FAILED articles (dashboard dead letters, stuck detection)
    op.create_index(
        "ix_articles_pipeline_status_failed",
        "articles",
        ["updated_at"],
        unique=False,
        where="pipeline_status = 'failed'"
    )

    # Index for REVIEW articles (editor queue)
    op.create_index(
        "ix_articles_pipeline_status_review",
        "articles",
        ["impact_score"],
        unique=False,
        where="pipeline_status = 'review'"
    )

    # Index for active/stuck articles (pending, researching, writing, editing)
    op.create_index(
        "ix_articles_pipeline_status_active",
        "articles",
        ["updated_at"],
        unique=False,
        where="pipeline_status IN ('pending', 'researching', 'writing', 'editing')"
    )


def downgrade() -> None:
    op.drop_index("ix_articles_pipeline_status_active", table_name="articles")
    op.drop_index("ix_articles_pipeline_status_review", table_name="articles")
    op.drop_index("ix_articles_pipeline_status_failed", table_name="articles")
```

**Action Items**:
- [ ] Create migration `025_article_pipeline_status_partial_indexes.py`
- [ ] Apply migration: `flask db upgrade`
- [ ] Add to `scripts/verify_backup.sh` to check index existence

**Effort**: 30 minutes (migration only)
**Risk**: Low (indexes improve read performance; minimal write overhead)

---

### 2.3 Related Articles Caching

**Severity**: MEDIUM
**Risk**: 50-article SQL query + Python O(n) scoring runs on every article view

**Current State**: `find_related_articles()` is called on every `article_detail()` load, not cached.

**Problem**: Expensive computation for what is essentially static data — related articles don't change once an article is published.

**Solution**: Cache result with key pattern `related:{article_id}`, TTL 600s (10 minutes).

**Implementation** (`services/related.py` or at call site):

```python
# In find_related_articles() or wrapper:
def find_related_articles_cached(article_id: int, limit: int = 5):
    from services.cache import get_response_cache
    cache = get_response_cache()
    cache_key = f"related:{article_id}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = find_related_articles(article_id, limit)
    cache.set(cache_key, result, ttl=600)
    return result
```

**Action Items**:
- [ ] Add ResponseCache wrapping to `find_related_articles()`
- [ ] Invalidate cache when article is updated

**Effort**: 30 minutes
**Risk**: Low (cache miss returns same data; cache invalidation handled normally)

---

### 2.4 Sitemap Caching

**Severity**: MEDIUM
**Risk**: XML generated on every request despite infrequent changes

**Current State** (`routes/public/feeds.py:277-303`): No caching. SQL query + XML generation on every request.

**Solution**: Cache sitemap XML with 5-minute TTL.

**Implementation** (`routes/public/feeds.py`):
```python
@public_bp.route("/sitemap.xml")
def sitemap():
    from services.cache import get_response_cache
    cache = get_response_cache()

    cached = cache.get("pub:sitemap:xml")
    if cached:
        return Response(cached, mimetype="application/xml")

    # ... existing logic ...
    xml_content = generate_sitemap(...)  # Your existing code
    cache.set("pub:sitemap:xml", xml_content, ttl=300)
    return Response(xml_content, mimetype="application/xml")
```

**Action Items**:
- [ ] Add ResponseCache get/set to sitemap route
- [ ] Use `pub:sitemap:xml` key

**Effort**: 20 minutes
**Risk**: Low (5-minute staleness acceptable for sitemap)

---

## Priority 3: 🟢 Low

### 3.1 Duplicate Detection Batching

**Severity**: LOW
**Risk**: N queries for N items in a crawl batch

**Current State** (`services/article.py:find_duplicate_titles()`):
```python
for item in new_items:
    dupes = find_duplicate_titles(item.title, source.id)  # N queries for N items
```

**Solution**: Pre-fetch all candidate titles once, compute all similarities in-memory.

**Implementation** (`services/article.py`):

```python
def find_duplicate_titles(title, source_id, threshold=0.5):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=_get_duplicate_detection_days())

    # Single query for all candidates
    candidates = (
        Article.query.filter(
            Article.source_id != source_id,
            Article.created_at >= cutoff,
        )
        .with_entities(Article.id, Article.original_title)
        .all()
    )

    candidate_words = {id_: _title_word_set(t) for id_, t in candidates}
    candidate_ids = set(candidate_words.keys())

    # Find duplicates
    matched_ids = []
    candidate_words_set = _title_word_set(title)

    for article_id, other_words in candidate_words.items():
        if jaccard_similarity(candidate_words_set, other_words) >= threshold:
            matched_ids.append(article_id)
            break

    return matched_ids
```

**Note**: This combines the N queries into 1 but keeps the in-memory similarity computation. Memory impact is minimal (storing title strings vs Article objects).

**Action Items**:
- [ ] Refactor `find_duplicate_titles()` to batch candidate fetch
- [ ] Verify similarity computation still correct

**Effort**: 30 minutes
**Risk**: Low (maintains same behavior, just fewer queries)

---

### 3.2 Admin Articles Count Removal

**Severity**: LOW
**Risk**: Extra COUNT query on every admin articles page load

**Current State** (`routes/admin/articles.py:133`):
```python
total_count = q.count()  # Separate COUNT query
articles, has_next, next_page = paginate_query(q, page, per_page)
```

**Solution**: Remove exact count display; use `total_count=None` and update template to show `"{{ articles|length }}+ articles"`.

**Implementation**:

1. In `routes/admin/articles.py`:
```python
# Remove: total_count = q.count()
# Change to:
total_count = None  # or remove variable entirely
articles, has_next, next_page = paginate_query(q, page, per_page)
```

2. In template (`templates/admin/articles.html` or partial):
```html
<!-- Change from -->
<span class="pag-info">{{ start }}–{{ end }} of {{ total_count }}</span>

<!-- Change to -->
<span class="pag-info">page {{ page }}{% if total_count is none %} ({{ articles|length }}+ articles){% else %} of {{ total_count }}{% endif %}</span>
```

**Action Items**:
- [ ] Remove `total_count = q.count()` from `routes/admin/articles.py`
- [ ] Update template to handle `total_count=None`
- [ ] Update `pagination_nav` macro if shared

**Effort**: 20 minutes
**Risk**: None (UX improvement; `has_next` still works for navigation)

---

## Implementation Order

```
Phase 1: Critical Path (no DB migration needed)
├── 1.2 N+1 feeds fix                (10 min)
├── 1.4 Provider info caching        (30 min)
├── 1.3 Cache scoping               (1-2 hrs)
└── 1.1 SLA SQL aggregation         (1-2 hrs)

Phase 2: After migration
└── 2.2 Partial indexes             (30 min)

Phase 3: Separate PRs
├── 2.1 Dashboard stampede          (1 hr)
├── 2.3 Related articles cache     (30 min)
├── 2.4 Sitemap cache              (20 min)
├── 3.1 Duplicate batching         (30 min)
└── 3.2 Count removal              (20 min)

Total estimated: ~7 hours across all phases
```

---

## Testing Requirements

### Pre-Changes
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After Each Change
```bash
# Verify lint still passes
.venv/bin/ruff check . --exclude .venv

# For SLA fix specifically:
# curl "http://localhost:5000/admin/api/pipeline/sla?days=7"
# Should return same JSON structure with avg/p50/p95
```

### Cache Scoping Verification
```bash
# After cache key changes:
# 1. Load homepage (index) - should cache under pub:index:*
# 2. Edit an article in admin
# 3. Reload homepage - cache should be invalidated (new data)
# 4. Verify pub:index:* keys are invalidated, admin:articles:* are not
```

### SLA Endpoint Verification
```bash
# Compare old vs new output structure:
curl -s "http://localhost:5000/admin/api/pipeline/sla?days=7" | python -m json.tool
# Should contain: period_days, article_count, sla with avg/p50/p95
```

---

## Rollback Plan

| Change | Rollback Method |
|--------|----------------|
| SLA SQL aggregation | Revert to `.all()` + Python loops |
| N+1 feeds fix | Remove `joinedload()` calls |
| Cache scoping | Remove `pub:` prefix from keys |
| Provider info caching | Remove cache wrapper, return raw call |
| Dashboard stampede | Revert to raw `setex` |
| Partial indexes | `flask db downgrade` |
| Related articles cache | Remove cache wrapper |
| Sitemap cache | Remove cache get/set |
| Duplicate batching | Split back to N queries |
| Count removal | Add back `q.count()` |

---

## Appendix A: Issue Summary Table

| ID | Priority | Category | Severity | File | Line | Description |
|----|----------|----------|----------|------|------|-------------|
| SLA-001 | 🔴 Critical | Memory | CRITICAL | routes/admin/api/pipeline.py | 149-156 | Loads all articles into memory |
| FEED-001 | 🔴 Critical | N+1 | CRITICAL | routes/public/feeds.py | 37 | Missing joinedload on source |
| CACHE-001 | 🔴 Critical | Cache | CRITICAL | routes/admin/articles.py | 284-286 | Overbroad invalidation (pub/admin collision) |
| LLM-001 | 🔴 High | API | HIGH | services/llm/__init__.py | 107 | Uncached provider info |
| DASH-001 | 🟡 Medium | Stampede | MEDIUM | routes/admin/dashboard.py | 77-86 | No lock on setex |
| IDX-001 | 🟡 Medium | Index | MEDIUM | models.py | 107 | Missing partial indexes |
| CACHE-002 | 🟡 Medium | Cache | MEDIUM | services/related.py | — | Uncached find_related_articles |
| CACHE-003 | 🟡 Medium | Cache | MEDIUM | routes/public/feeds.py | 277-303 | Sitemap not cached |
| DUP-001 | 🟢 Low | Query | LOW | services/article.py | 290-309 | N+1 in duplicate detection |
| ADMIN-001 | 🟢 Low | Query | LOW | routes/admin/articles.py | 133 | Extra COUNT query |

---

## Appendix B: Investigation Details

### Investigation 1: SLA Endpoint

**Method**: Read full function, analyzed memory impact, researched SQLite percentile alternatives.

**Key Finding**: In-memory histogram in `services/metrics.py` only keeps 1000 entries — cannot use for 30-day SLA.

**Reference**: SQLite `ROW_NUMBER() OVER()` requires 3.25+. All supported SQLite versions support this.

---

### Investigation 2: N+1 in Feeds

**Method**: Read template to find accessed relationships; checked Article model lazy settings.

**Key Finding**: `article.source` backref uses `lazy="dynamic"`, triggers separate query per article. `tags` uses `lazy="selectin"` — already efficient.

---

### Investigation 3: Cache Invalidation

**Method**: Traced all invalidation calls, mapped all public cache key patterns.

**Key Finding**: No namespace separation between admin and public cache keys.

---

### Investigation 4: Provider Info

**Method**: Read `get_provider_info()` and `health_check()` implementations.

**Key Finding**: `health_check()` calls `client.models.list()` — real HTTP API call to LLM provider.

---

### Investigation 5: Duplicate Detection

**Method**: Read `find_duplicate_titles()`, traced caller in `tasks/crawl.py`.

**Key Finding**: Called for every item in a crawl batch — N items = N queries.

---

## Appendix C: Reference Resources

- [SQLite Window Functions](https://www.sqlite.org/windowfunctions.html)
- [SQLAlchemy Window Functions](https://docs.sqlalchemy.org/en/20/tutorial/data.html#window-functions)
- [ResponseCache Pattern](services/cache.py:get_or_set)
- [Partial Indexes in SQLite](https://www.sqlite.org/partialindex.html)

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] Testing plan reviewed
- [ ] Migration plan confirmed (for indexes)

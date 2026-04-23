# Performance Improvement Plan

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Total Issues**: 4 categories

---

## Executive Summary

This plan addresses performance issues identified during a comprehensive code review of the ainews codebase. The codebase is well-architected with proper caching, indexes, and eager loading, but several optimization opportunities were identified.

| Priority | Category | Issues | Impact |
|----------|----------|--------|--------|
| High | SLA Metrics Query | Loads all rows into memory | Major |
| Medium | LRU Cache Eviction | O(n) complexity | Minor |
| Low | Dashboard Stats | Loads all sources | Minor |
| Low | Search Analytics | SQL syntax issue (not breaking) | Minor |

---

## Priority 1: High Priority

### 1.1 SLA Metrics Query - SQL Aggregation

**Rationale**: The `pipeline_sla` endpoint loads ALL articles within the time range into Python memory, then sorts and computes statistics in Python. For 30-day ranges with thousands of articles, this is memory-intensive.

**Current Implementation** (`routes/admin/api/pipeline.py:149-156`):
```python
articles = Article.query.filter(
    Article.published_at.isnot(None),
    Article.published_at >= cutoff,
).order_by(Article.published_at.desc()).all()

# Then iterates through all articles computing:
# - crawl_to_select deltas
# - select_to_publish deltas
# - crawl_to_publish deltas
# Sorts each list, computes avg/p50/p95
```

**Problem**: For 30 days with 10,000 articles:
- Loads 10,000 rows into Python memory
- Creates 3 lists with potentially thousands of items
- O(n log n) sorting in Python

**Recommended Fix**: Hybrid approach using SQL for AVG + bounded LIMIT for percentiles:

```python
from sqlalchemy import func, case

# Step 1: Get averages via SQL (single efficient query)
stats_query = db.session.query(
    func.count(Article.id).label('total_count'),
    func.avg(
        case(
            (Article.crawled_at.isnot(None) & Article.selected_at.isnot(None),
             (func.julianday(Article.selected_at) - func.julianday(Article.crawled_at)) * 86400),
            else_=None
        )
    ).label('c2s_avg'),
    func.avg(
        case(
            (Article.selected_at.isnot(None) & Article.published_at.isnot(None),
             (func.julianday(Article.published_at) - func.julianday(Article.selected_at)) * 86400),
            else_=None
        )
    ).label('s2p_avg'),
    func.avg(
        case(
            (Article.crawled_at.isnot(None) & Article.published_at.isnot(None),
             (func.julianday(Article.published_at) - func.julianday(Article.crawled_at)) * 86400),
            else_=None
        )
    ).label('c2p_avg'),
).filter(
    Article.published_at.isnot(None),
    Article.published_at >= cutoff
).first()

# Step 2: Get bounded sample for percentiles
PERCENTILE_SAMPLE_SIZE = 1000
percentile_data = db.session.query(
    # ... same CASE expressions ...
).filter(
    Article.published_at.isnot(None),
    Article.published_at >= cutoff
).limit(PERCENTILE_SAMPLE_SIZE).all()

# Step 3: Compute p50/p95 in Python on ~1000 rows max
```

**Performance Comparison**:

| Scenario | Current | Fixed |
|----------|---------|-------|
| 30 days, 10k articles | Load 10k rows, sort 3x | 1 AVG query + 1000-row LIMIT |
| Memory | O(n) | O(1000) fixed |
| Time | O(n log n) | O(1) SQL + O(1000 log 1000) |

**Action Items**:
- [ ] Replace `.all()` with SQL aggregation for averages
- [ ] Add bounded LIMIT query for percentiles
- [ ] Compute percentiles on max 1000 rows instead of all
- [ ] Keep exact JSON response format for backward compatibility

**Effort**: 1-2 hours
**Risk**: Low (maintains same output format)
**Tests**: `tests/test_admin_api.py` - verify SLA endpoint returns same structure

---

## Priority 2: Medium Priority

### 2.1 LRU Cache Eviction - O(1) Implementation

**Rationale**: The `ResponseCache` class uses `min()` with a key function to find the LRU item, which is O(n). While the cache is small (1000 max), this is called on every cache write when full.

**Current Implementation** (`services/cache.py:114-118`):
```python
# O(n) - scans all keys
lru_key = min(
    self._memory.keys(),
    key=lambda k: self._memory[k][1]
)
del self._memory[lru_key]
```

**Recommended Fix** - Use `OrderedDict.popitem(last=False)`:
```python
# O(1) - removes first item
lru_key, _ = self._memory.popitem(last=False)
```

**How it works**:
- OrderedDict maintains insertion order
- On access, `move_to_end()` moves item to end (most recently used)
- On insert, item goes to end (most recently used)
- First item is always least recently used
- `popitem(last=False)` removes and returns the first item in O(1)

**Trade-off**: Loses exact access time tracking, uses insertion order instead. In practice, this is functionally equivalent for LRU.

**Action Items**:
- [ ] Replace `min()` pattern with `popitem(last=False)`
- [ ] Update code comments to reflect new behavior
- [ ] Simplify tuple from 3 elements to 2 (remove access_time)

**Effort**: 30 minutes
**Risk**: Very Low (maintains same behavior)
**Tests**: `tests/test_cache.py` if exists; manual verification

**Note**: This optimization is minor given 1000 max cache size. Consider skipping unless write path performance is critical.

---

## Priority 3: Low Priority

### 3.1 Dashboard Stats - Source Query Optimization

**Rationale**: The dashboard loads all sources when only the count is needed.

**Current Implementation** (`routes/admin/dashboard.py:127`):
```python
sources = Source.query.all()
source_count = len(sources)
```

**Recommended Fix**:
```python
source_count = Source.query.count()
# Or if only active sources shown:
source_count = Source.query.filter_by(active=True).count()
```

**Action Items**:
- [ ] Replace `Source.query.all()` with `Source.query.count()`

**Effort**: 10 minutes
**Risk**: Very Low

---

### 3.2 Search Analytics - SQL Syntax Cleanup

**Rationale**: The syntax is confusing - `SearchQuery.query` appears twice (once as the query object, once as the column attribute).

**Current Implementation** (`routes/admin/api/search.py:16-17`):
```python
top_queries = (
    SearchQuery.query.with_entities(
        SearchQuery.query.label("query"),  # Works but confusing naming
        func.count(SearchQuery.id).label("search_count"),
        func.sum(SearchQuery.results_count).label("total_results"),
    )
    .group_by(SearchQuery.query)
    ...
```

**Recommendation**: Simplify for clarity (optional):
```python
from sqlalchemy import func

top_queries = (
    SearchQuery.query.with_entities(
        SearchQuery.query,  # Column reference
        func.count(SearchQuery.id).label("search_count"),
        func.sum(SearchQuery.results_count).label("total_results"),
    )
    .group_by(SearchQuery.query)
    ...
```

**Issue**: `SearchQuery.query` on line 16 is the query object, not the `query` column attribute. This should still work because SQLAlchemy handles it, but it's confusing and potentially fragile.

**Action Items**:
- [ ] Verify query returns correct data
- [ ] Clean up syntax for clarity

**Effort**: 15 minutes
**Risk**: Very Low

---

## Implementation Order

```
1. sla_metrics_sql (1-2 hours, major impact) - RECOMMENDED FIRST
2. search_analytics_bug (15 min, cleanup)
3. lru_eviction_o1 (30 min, optional)
4. dashboard_source_count (10 min, optional)
```

---

## Testing Requirements

1. Before changes: Run baseline tests
   ```bash
   .venv/bin/pytest tests/ -x -q
   ```

2. After SLA changes: Verify endpoint returns same JSON structure
   ```bash
   .venv/bin/ruff check . --exclude .venv
   ```

3. Key test files:
   - `tests/test_admin_api.py` - Other admin API tests (SLA tests may not exist)
   - `tests/test_cache.py` - Cache tests (if exists)

**Note**: There are no existing tests for the `pipeline_sla` endpoint. Testing will require creating test cases or manual verification.

---

## Rollback Plan

- SLA changes: Revert to `.all()` pattern
- LRU changes: Restore `min()` pattern
- Dashboard: Restore `.all()` pattern
- Search: Restore original syntax

---

## Appendix A: Issue Summary Table

| ID | Category | Severity | File | Line | Description |
|----|----------|----------|------|------|-------------|
| SLA-001 | Performance | **HIGH** | routes/admin/api/pipeline.py | 149-156 | Loads all articles into memory |
| CACHE-001 | Performance | Medium | services/cache.py | 114-118 | O(n) LRU eviction |
| DASH-001 | Performance | Low | routes/admin/dashboard.py | 127 | Loads all sources |
| SEARCH-001 | Code Quality | Low | routes/admin/api/search.py | 16 | Confusing SQLAlchemy syntax |

---

## Appendix B: Investigation Details

### Investigation 1: SLA Metrics Query

**Method**: Read full function, understand statistics computed, analyze Article model columns, research SQL aggregation approach.

**Key Files**:
- `routes/admin/api/pipeline.py:140-234`
- `models.py:134-137` (crawled_at, selected_at, published_at columns)

**Reference**: SQLAlchemy `func.avg()`, `func.julianday()` for SQLite datetime arithmetic.

---

### Investigation 2: LRU Eviction

**Method**: Analyzed ResponseCache class, studied OrderedDict behavior.

**Key Files**:
- `services/cache.py:33-232`

**Reference**: Python `collections.OrderedDict.popitem(last=False)` documentation.

---

### Investigation 3: Trend Memory

**Finding**: No N+1 issues. Model has no relationship defined; code only accesses direct columns.

---

### Investigation 4: Dashboard Stats

**Method**: Analyzed `_get_cached_stats` and dashboard() function.

**Key Files**:
- `routes/admin/dashboard.py:67-211`

**Caching**: Redis-based with 60-second TTL.

---

### Investigation 5: Search Analytics

**Method**: Read query syntax, found bug in `with_entities()`.

**Key Files**:
- `routes/admin/api/search.py:8-52`

---

### Investigation 6: Database Indexes

**Method**: Searched for query patterns with source_id filtering.

**Finding**: Good index coverage - `ix_articles_source_id` exists.

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] Testing plan reviewed
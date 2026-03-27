# Plan 2: Remaining Items from plan.md

Items from `plan.md` that remain incomplete.

---

## 1. Redundant Count Query in Review Route

**Location:** `routes/admin/review.py:19-23`

**Problem:** The review queue queries articles twice - once for count, once for pagination:
```python
q = Article.query.filter_by(pipeline_status="review")
total_review = q.count()  # Query 1
articles, has_next, next_page = paginate_query(q, page, per_page)  # Query 2
```

**Fix:** Use `q.with_entities(func.count(Article.id))` to get count in a single query, or use `SELECT COUNT(*) OVER()` window function to include count in the same query as pagination.

**Implementation:**
```python
from sqlalchemy import func, over

q = Article.query.filter_by(pipeline_status="review").order_by(
    Article.impact_score.desc()
)

# Get total count efficiently - use window function to avoid extra query
total_review = db.session.query(
    over(func.count(Article.id))
).select_from(Article).filter(Article.pipeline_status == "review").scalar()

articles, has_next, next_page = paginate_query(q, page, per_page)
```

**Alternative (simpler):** Accept the two queries - it's already efficient for most use cases. The count is needed for pagination UI anyway.

**Files:** `routes/admin/review.py`

**Estimated time:** 15 minutes

**Status:** Low priority - the current implementation is acceptable for admin UI use.

---

## 2. Bare Exception Cleanup

**Location:** Various routes (96 occurrences noted in plan.md)

**Problem:** Many places catch bare `Exception` instead of specific types, which can hide bugs and make debugging harder.

**Current high-priority targets from plan.md:**
- `routes/public.py` - 5 bare Exception catches remain (lines 49, 308, 319, 504, 551)
- `routes/admin/review.py` - ✅ Already uses `SQLAlchemyError` (lines 63, 88)
- `routes/admin/articles.py` - ✅ No bare Exception catches found

**Fix:** Replace bare `Exception` with specific types:
- `SQLAlchemyError` for database operations
- `redis.exceptions.RedisError` for Redis operations
- Keep bare `Exception` in Celery tasks for robustness

**Example:**
```python
# Before
except Exception as e:
    logger.error(f"Failed: {e}")

# After
from sqlalchemy.exc import SQLAlchemyError
except SQLAlchemyError as e:
    logger.error(f"Database error: {e}")
except redis.exceptions.RedisError as e:
    logger.error(f"Redis error: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

**Files:** 
- `routes/public.py`
- `routes/admin/review.py`
- `routes/admin/articles.py`

**Estimated time:** 1-2 hours

**Status:** Medium priority - improves debuggability but low risk.

---

## 3. Request Correlation IDs

**Location:** `app.py`, `logging_config.py`, task modules

**Problem:** No correlation IDs for tracking requests across Flask, Celery, and logs.

**Fix:** 
1. Add middleware in `app.py` to generate/pass `X-Correlation-ID` header
2. Include correlation ID in all log entries via custom formatter
3. Pass correlation ID through Celery tasks using task metadata
4. Store in Flask `g` for request context

**Implementation:**

### 3.1 Middleware (app.py)
```python
from flask import g, request
import uuid

@app.before_request
def set_correlation_id():
    g.correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())
    # Also set for logging
    logging_context = logging.getLoggerClass()
    # Use existing logger's factory if configured
```

### 3.2 Logging integration
Add correlation ID to log format in `logging_config.py`:
```python
LOG_FORMAT = '%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s: %(message)s'
```

Or use a custom formatter that reads from `flask.g`.

### 3.3 Celery tasks
```python
@app.task(bind=True)
def my_task(self, *args, **kwargs):
    correlation_id = self.request.id  # Celery task ID
    # Pass to downstream calls
```

**Files:** 
- `app.py`
- `logging_config.py`
- `celery_app.py`
- Task modules

**Estimated time:** 3-4 hours

**Status:** Medium priority - useful for debugging production issues.

---

## 4. Enhanced Logging

**Location:** `logging_config.py`

**Current state:** Structured logging is "largely implemented" per plan.md.

**Remaining gaps:**
- Structured JSON logging option
- User context (admin ID) in admin route logs
- Request timing logs

**Fix:**

### 4.1 JSON logging option
```python
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if hasattr(record, 'correlation_id'):
            log_data['correlation_id'] = record.correlation_id
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        return json.dumps(log_data)
```

### 4.2 User context in admin logs
```python
from flask import g

# In require_auth decorator, set g.user_id
# Then in logging, access via log filter or custom logger
```

### 4.3 Request timing
```python
import time
from flask import g, request

@app.after_request
def log_request_timing(response):
    if hasattr(g, 'request_start'):
        duration = time.monotonic() - g.request_start
        current_app.logger.info(f"{request.method} {request.path} took {duration:.3f}s")
    return response
```

**Files:** 
- `logging_config.py`
- `app.py`

**Estimated time:** 2-3 hours

**Status:** Low priority - nice to have for production observability.

---

## 5. Cost Tracking

**Location:** New `services/cost_tracker.py`

**Problem:** LLM token usage is tracked in responses but never aggregated for cost analysis.

**Note:** The Article model does NOT currently store token usage. The LLM services return `tokens_used` in responses, but this is not persisted to the database. This item would require:

1. Adding database columns to Article model:
   ```python
   tokens_used = db.Column(db.JSON)  # {"input": 123, "output": 456}
   model_used = db.Column(db.String(128))
   ```

2. Updating LLM services to persist token usage to articles

**Fix:**

### 5.1 Create cost tracker service
```python
# services/cost_tracker.py

# Approximate pricing (USD per 1M tokens)
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "ollama": {"input": 0.0, "output": 0.0},  # Local, free
}

class CostTracker:
    def __init__(self, db_session):
        self.db = db_session
    
    def calculate_article_cost(self, article) -> float:
        """Calculate cost for a single article."""
        if not article.tokens_used or not article.model_used:
            return 0.0
        
        pricing = PRICING.get(article.model_used, {"input": 0, "output": 0})
        tokens = article.tokens_used  # Dict with 'input' and 'output' keys
        
        input_cost = (tokens.get("input", 0) / 1_000_000) * pricing["input"]
        output_cost = (tokens.get("output", 0) / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def get_total_costs(self, start_date=None, end_date=None) -> dict:
        """Aggregate costs over time period."""
        query = Article.query
        
        if start_date:
            query = query.filter(Article.published_at >= start_date)
        if end_date:
            query = query.filter(Article.published_at <= end_date)
        
        total_cost = 0.0
        for article in query.all():
            total_cost += self.calculate_article_cost(article)
        
        return {"total_cost": total_cost, "article_count": query.count()}
    
    def get_costs_by_model(self, start_date=None, end_date=None) -> dict:
        """Group costs by model."""
        # Group and aggregate
        ...
```

### 5.2 Add admin route
```python
# routes/admin/costs.py

@admin_bp.route("/api/costs")
@require_auth
def cost_summary():
    from services.cost_tracker import CostTracker
    
    tracker = CostTracker(db.session)
    return jsonify({
        "total": tracker.get_total_costs(),
        "by_model": tracker.get_costs_by_model(),
    })
```

### 5.3 Optional: Admin dashboard widget
Add to admin metrics page showing cost trends over time.

**Note:** This is optional per plan.md - costs are approximate and LLM pricing changes frequently.

**Files:**
- `services/cost_tracker.py` (new)
- `routes/admin/costs.py` (new)
- Update `app.py` to register blueprint

**Estimated time:** 4 hours

**Status:** Low priority - optional feature with limited ROI.

---

## 6. Enhanced Health Checks

**Location:** `routes/public.py:295-330`

**Status:** ✅ ALREADY IMPLEMENTED

The health endpoint checks:
- Database (`SELECT 1`)
- Redis (ping)
- Rate limiter health

Returns `200` if all OK, `503` if degraded.

**Potential enhancement (not implemented):**
- Celery worker check
- LLM provider availability check

These are optional - the current implementation is sufficient.

---

## Implementation Priority

| # | Item | Priority | Time | Risk |
|---|------|----------|------|------|
| 1 | Bare Exception Cleanup | Medium | 1-2h | Low |
| 2 | Request Correlation IDs | Medium | 3-4h | Medium |
| 3 | Enhanced Logging | Low | 2-3h | Low |
| 4 | Cost Tracking | Optional | 6h | Medium |
| 5 | Redundant Count Query | Low | 15m | Very Low |
| - | Enhanced Health Checks | - | - | ✅ DONE |

**Total estimated time:** 5-7 hours (excluding optional)

---

## Recommendations

Given the low risk and limited ROI, consider deferring or skipping:

1. **Redundant Count Query** - Current implementation is acceptable for admin UI
2. **Cost Tracking** - Optional per plan.md, pricing changes frequently, requires DB schema changes
3. **Enhanced Logging** - Already "largely implemented"
4. **Request Correlation IDs** - Requires significant changes, limited benefit unless debugging complex issues

Focus on:
1. **Bare Exception Cleanup** - Improves debuggability with minimal risk

**Already Done:**
- Enhanced Health Checks - Fully implemented at `routes/public.py:295-330`

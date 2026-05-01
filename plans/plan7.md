# Backend Improvement Plan - Plan 7

**Date:** 2026-05-01  
**Scope:** Comprehensive backend review and improvement plan based on deep-dive investigation  
**Status:** Planning phase - not yet implemented

---

## Executive Summary

This plan addresses 16 identified improvement items across the ainews backend, discovered through systematic code review and subagent investigation. Items are categorized by priority:

- **High Priority (7 items):** Security fixes, bug fixes, and critical improvements
- **Medium Priority (4 items):** Architectural improvements and code quality
- **Low Priority (5 items):** Maintainability and standardization

**Estimated Total Effort:** ~16-20 hours of implementation time

---

## High Priority Items

**Important Notes Before Starting:**
- H3 (limiter fix) changes `acquire()` to raise exceptions on RedisError. Verify callers in `tasks/pipeline.py` handle this properly before implementing.
- H5 (API responses) affects 47 instances across 5 files. Consider doing this in parallel with other high-priority items.

### H1: Fix Missing Authentication on API Tokens Endpoints

**File:** `routes/admin/api_tokens.py`  
**Severity:** CRITICAL - Security vulnerability  
**Estimated Time:** 30 minutes

#### Current State
All three endpoints lack authentication:
- `GET /api-tokens` - Lists all API tokens
- `POST /api-tokens` - Creates new API tokens
- `DELETE /api-tokens/<id>` - Deletes API tokens

The file creates its own Blueprint (`api_tokens_bp`) instead of using the shared `admin_api_bp`, and doesn't import `require_auth`.

#### Required Changes

1. **Fix imports (replace lines 1-8):**
```python
import secrets
import logging

from flask import request

from extensions import db
from models import ApiToken
from routes.admin import admin_api_bp, require_auth
from routes.decorators import validate_csrf_json
from routes.admin.api.utils import api_response

logger = logging.getLogger(__name__)
```

2. **Remove local Blueprint (delete line 8):**
```python
# REMOVE: api_tokens_bp = Blueprint("api_tokens", __name__)
```

3. **Add decorators to all endpoints and fix response format:**
```python
@admin_api_bp.route("/api-tokens", methods=["GET"])
@require_auth
def list_tokens():
    """List all API tokens (without exposing hashes)."""
    tokens = ApiToken.query.all()
    return api_response(data=[
        {
            "id": t.id,
            "name": t.name,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in tokens
    ])

@admin_api_bp.route("/api-tokens", methods=["POST"])
@require_auth
@validate_csrf_json
def create_token():
    ...

@admin_api_bp.route("/api-tokens/<int:token_id>", methods=["DELETE"])
@require_auth
@validate_csrf_json
def delete_token(token_id):
    ...
```

4. **Rewrite `create_token()` function:**
```python
@admin_api_bp.route("/api-tokens", methods=["POST"])
@require_auth
@validate_csrf_json
def create_token():
    """Create a new API token and return the plain text token."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    
    # Input validation
    if not name or len(name) > 128:
        return api_response(error="Invalid name", status=400)
    
    expires_in = data.get("expires_in")
    if expires_in is not None:
        try:
            expires_in = int(expires_in)
        except ValueError:
            return api_response(error="expires_in must be an integer", status=400)
    
    # Generate token
    plain_token = secrets.token_urlsafe(32)
    token_hash = secrets.token_hex(32)
    
    # Store hash, not plain token
    from werkzeug.security import generate_password_hash
    api_token = ApiToken(
        token_hash=generate_password_hash(token_hash),
        name=name,
    )
    
    if expires_in:
        from datetime import datetime, timedelta
        api_token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    db.session.add(api_token)
    from routes.decorators import commit
    error = commit(db, "Failed to create token")
    if error:
        return error
    
    # Audit logging
    from services.audit import log_admin_action
    log_admin_action(
        "api_token_create",
        target_type="api_token",
        target_id=api_token.id,
        details={"name": api_token.name},
        category="config",
    )
    
    return api_response(
        data={
            "id": api_token.id,
            "name": api_token.name,
            "token": plain_token + "." + token_hash,
            "created_at": api_token.created_at.isoformat(),
            "expires_at": api_token.expires_at.isoformat() if api_token.expires_at else None,
        },
        meta={"message": "API token created"},
        status=201
    )
```

5. **Rewrite `delete_token()` function:**
```python
@admin_api_bp.route("/api-tokens/<int:token_id>", methods=["DELETE"])
@require_auth
@validate_csrf_json
def delete_token(token_id):
    """Delete an API token."""
    api_token = db.get_or_404(ApiToken, token_id)
    db.session.delete(api_token)
    from routes.decorators import commit
    error = commit(db, "Failed to delete token")
    if error:
        return error
    
    # Audit logging
    from services.audit import log_admin_action
    log_admin_action(
        "api_token_delete",
        target_type="api_token",
        target_id=token_id,
        category="config",
    )
    
    return api_response(meta={"message": "API token deleted"})
```

#### Verification
- Run `pytest tests/` to ensure no regressions
- Run `.venv/bin/ruff check routes/admin/api_tokens.py`
- Manual test: Attempt to access `/admin/api/v1/api-tokens` without auth - should return 401

---

### H2: Syntax Errors in topic_notes.py

**File:** `routes/admin/topic_notes.py`  
**Severity:** Was reported as CRITICAL - Investigation shows ALREADY FIXED  
**Estimated Time:** 0 minutes

#### Investigation Result
Subagent investigation confirmed that lines 71, 117, and 127 have correct syntax with proper commas in dictionary literals. The reported errors likely existed in a prior commit and were already fixed. No action needed.

#### Verification
```bash
.venv/bin/python -m py_compile routes/admin/topic_notes.py
.venv/bin/ruff check routes/admin/topic_notes.py
```

---

### H3: Fix Limiter Fail-Closed Policy

**File:** `services/limiter.py` (lines 54-61)  
**Severity:** HIGH - Policy compliance  
**Estimated Time:** 15 minutes

#### Current State
The `acquire()` method returns `False` on Redis errors. While this technically complies with AGENTS.md policy (which allows returning `False`), it creates ambiguity since `False` is also returned for "limit reached" and "timeout" conditions.

Other methods have issues:
- `get_active()` returns `None` on RedisError (violates policy)
- `release()` causes slot leaks on RedisError without raising

#### Recommended Fix
Align with AGENTS.md fail-closed policy by raising exceptions on Redis errors.

**Important:** Only raise on RedisError - timeout and limit-reached should still return `False`.

```python
# In acquire() - lines 54-61:
except redis.exceptions.RedisError as e:
    logger.error(
        "Limiter acquire failed for %s/%s: %s",
        provider_id,
        model,
        e,
    )
    raise  # Re-raise instead of return False
```

For `get_active()` (lines 111-117) and `release()` (lines 77-109), apply the same fix - raise RedisError instead of swallowing:
```python
# In get_active():
except redis.exceptions.RedisError as e:
    logger.error("Limiter get_active failed: %s", e)
    raise  # Re-raise instead of return None
```

```python
# In release():
except redis.exceptions.RedisError as e:
    logger.error("Limiter release failed for slot %s: %s", slot_id, e)
    raise  # Re-raise to alert callers of Redis failure
```

#### Verification
- Run `pytest tests/` - ensure callers handle RedisError properly
- Check that `tasks/pipeline.py` catch blocks handle the raised exceptions

---

### H4: Fix N+1 Query in recalculate_impact_scores

**File:** `tasks/cleanup.py` (lines 183-201)  
**Severity:** HIGH - Performance  
**Estimated Time:** 15 minutes

#### Current State
The query uses `.join(ArticleMetric)` for filtering but doesn't eagerly load the relationship. When `article.metrics` is accessed in the loop, it triggers a separate SQL query for each article (N+1 problem).

#### Fix
Use `contains_eager()` to reuse the explicit JOIN:

```python
from sqlalchemy.orm import contains_eager
from models import Article, ArticleMetric

articles = (
    Article.query.filter(Article.pipeline_status == "done")
    .filter(Article.published_at >= cutoff)
    .join(ArticleMetric, Article.id == ArticleMetric.article_id)
    .options(contains_eager(Article.metrics))
    .all()
)
```

Alternatively, use `joinedload()`:
```python
from sqlalchemy.orm import joinedload

articles = (
    Article.query.filter(Article.pipeline_status == "done")
    .filter(Article.published_at >= cutoff)
    .join(ArticleMetric, Article.id == ArticleMetric.article_id)
    .options(joinedload(Article.metrics))
    .all()
)
```

Note: `contains_eager()` is more efficient here as it reuses the existing JOIN.

#### Verification
- Run `pytest tests/test_cleanup.py` or equivalent
- Check query count before/after with SQLAlchemy echo=True

---

### H5: Standardize API Error Responses to Use api_response()

**Files:**
- `routes/admin/api/search.py` (1 instance)
- `routes/admin/api/webhooks.py` (18 instances)
- `routes/admin/api/articles.py` (24 instances)
- `routes/admin/api/config.py` (3 instances)
- `routes/admin/api/audit.py` (1 instance)

**Severity:** HIGH - Consistency  
**Estimated Time:** 1 hour

#### Current State
47 total instances use raw `jsonify()` instead of the standardized `api_response()` format defined in `routes/admin/api/utils.py`.

Correct format (from `routes/admin/api/sources.py`):
```python
# Success with data
return api_response(data={...})

# Success with message
return api_response(meta={"message": "..."})

# Error response
return api_response(error="...", status=400)
```

#### Required Changes

**File 1: `routes/admin/api/search.py`**
```python
# Change import:
from routes.admin.api.utils import api_response

# Change return:
return api_response(
    data={
        "top_queries": [...],
        "zero_result_queries": [...],
    }
)
```

**File 2: `routes/admin/api/webhooks.py`**
```python
# Change import:
from flask import Response, request  # Remove jsonify
from routes.admin.api.utils import api_response

# All 18 instances need conversion - examples:
return api_response(error="Invalid JSON body", status=400)
return api_response(data={...}, meta={"message": "Webhook created"}, status=201)
return api_response(meta={"message": "Webhook updated"})
return api_response(data=[...])  # For list endpoints
```

**File 3: `routes/admin/api/articles.py`** (24 instances)
- Same pattern - replace all `jsonify()` with `api_response()`

**File 4: `routes/admin/api/config.py`** (3 instances)
```python
return api_response(error="Config validation failed", meta={"details": errors}, status=400)
return api_response(meta={"message": "Config cache cleared"})
return api_response(data=get_metrics().get_metrics())
```

**File 5: `routes/admin/api/audit.py`** (1 instance)
```python
return api_response(data={"logs": [...], "page": ..., ...})
```

#### Verification
```bash
.venv/bin/ruff check routes/admin/api/
# Test all API endpoints return proper format
pytest tests/test_api_responses.py
```

---

### H6: Replace Redis KEYS with SCAN in Metrics

**File:** `services/metrics.py` (7 instances)  
**Severity:** HIGH - Production safety  
**Estimated Time:** 30 minutes

#### Current State
The `KEYS` command is O(N) where N is the total number of keys in the database. It blocks the Redis server during execution. In production with large datasets, this can cause cascading failures.

The codebase already uses `scan_iter()` in `cache.py`, `pipeline_monitor.py`, and `limiter.py`.

#### Required Changes

Replace all 7 instances of:
```python
self._redis.keys(f"{self._REDIS_PREFIX}:counter:*")
```

With:
```python
list(self._redis.scan_iter(match=f"{self._REDIS_PREFIX}:counter:*", count=100))
```

**Specific locations:**
- Line 115: `clear()` method
- Line 133: `get_metrics()` counter keys
- Line 150: `get_metrics()` gauge keys
- Line 169: `get_metrics()` histogram keys
- Line 225: `get_prometheus()` counter keys
- Line 241: `get_prometheus()` gauge keys
- Line 259: `get_prometheus()` histogram keys

#### Verification
```bash
.venv/bin/ruff check services/metrics.py
# Test metrics collection still works
pytest tests/test_metrics.py
```

---

### H7: Standardize Retry Configuration with Constants

**Files:**
- `tasks/crawl.py`
- `tasks/extract.py`
- `tasks/select.py`
- `tasks/write.py`
- `tasks/edit.py`
- `tasks/newsletter.py`
- `tasks/pipeline.py`
- `constants.py`

**Severity:** HIGH - Consistency  
**Estimated Time:** 45 minutes

#### Current State
Inconsistent retry values across Celery tasks:

| File | max_retries | default_retry_delay |
|------|-------------|---------------------|
| crawl.py | 2 | 60 |
| extract.py | 2 | 30 |
| select.py | 3 | 30 |
| write.py | 2 | 60 |
| edit.py | 2 | 60 |
| newsletter.py | 3 | 60-120 |

#### Required Changes

Note: `constants.py` already has `MAX_STAGE_RETRIES = 3` for pipeline failure handling. Add separate constants for Celery task decorator settings:

1. **Add to `constants.py`:**
```python
# Celery Task Retry Configuration (single source of truth for task decorators)
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_DEFAULT_RETRY_DELAY = 60  # seconds
CELERY_TASK_RETRY_BACKOFF = True
CELERY_TASK_RETRY_BACKOFF_MAX = 300  # seconds
CELERY_TASK_RETRY_JITTER = True

# Newsletter-specific overrides (uses longer delay)
CELERY_TASK_MAX_RETRIES_NEWSLETTER = 3
CELERY_TASK_RETRY_DELAY_NEWSLETTER = 120  # seconds
```

2. **Update all task files to use constants:**
```python
from constants import (
    CELERY_TASK_MAX_RETRIES,
    CELERY_TASK_DEFAULT_RETRY_DELAY,
    CELERY_TASK_RETRY_BACKOFF,
    CELERY_TASK_RETRY_BACKOFF_MAX,
    CELERY_TASK_RETRY_JITTER,
)

@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=CELERY_TASK_DEFAULT_RETRY_DELAY,
    retry_backoff=CELERY_TASK_RETRY_BACKOFF,
    retry_backoff_max=CELERY_TASK_RETRY_BACKOFF_MAX,
    retry_jitter=CELERY_TASK_RETRY_JITTER,
)
def task_name(self):
    ...
```

3. **Fix `run_stage()` default `retry_max=15`** in `tasks/pipeline.py`:
```python
# Add to constants.py:
STAGE_LIMITER_MAX_RETRIES = 15

# Use in pipeline.py:
def run_stage(..., retry_max=STAGE_LIMITER_MAX_RETRIES):
```

#### Verification
```bash
# Check all tasks use constants
grep -n "max_retries" tasks/*.py
pytest tests/
```

---

## Medium Priority Items

### M1: Reduce Code Duplication

**Files:**
- `routes/admin/articles.py` (lines 67-74)
- `routes/admin/api/articles.py` (lines 56-62)
- `routes/admin/sources.py`
- `routes/admin/api/sources.py`
- `services/article.py`
- `services/subagent.py`

**Severity:** MEDIUM - Maintainability  
**Estimated Time:** 2 hours

#### Current State
Multiple duplicated patterns:
1. `_query_looks_like_url()` duplicated in two files
2. Cache invalidation pattern repeated 8+ times
3. Source serialization logic duplicated between HTML/API routes
4. Source key generation in `routes/admin/sources.py`

#### Required Changes

1. **Create `services/utils.py` with shared utilities:**
```python
from urllib.parse import urlparse
from typing import Optional

def query_looks_like_url(query: str) -> bool:
    """Check if the query string looks like a URL."""
    if not query:
        return False
    if query.startswith("http://") or query.startswith("https://"):
        return True
    parsed = urlparse(query)
    return bool(parsed.scheme and parsed.netloc)

import re

_SOURCE_KEY_STRIP_RE = re.compile(r"[^a-z0-9\s-]")
_SOURCE_KEY_DASH_RE = re.compile(r"[\s]+")

def generate_source_key(name: str, existing_keys: Optional[set] = None) -> str:
    """Generate a unique source key from a name."""
    import time
    
    key = name.lower().strip()
    key = _SOURCE_KEY_STRIP_RE.sub("", key)
    key = _SOURCE_KEY_DASH_RE.sub("-", key)
    key = key[:64] or "source"
    
    if existing_keys and key in existing_keys:
        key = f"{key}-{int(time.time()) % 10000:04d}"
    
    return key

def sanitize_field(value: str, max_length: int) -> str:
    """Truncate a string to max_length characters."""
    if not isinstance(value, str):
        return ""
    return value[:max_length]
```

2. **Create `services/serializers.py`:**
```python
from datetime import datetime
from typing import Any

def serialize_source(source: Any, include_stats: bool = True) -> dict:
    """Serialize a Source model to a dictionary."""
    result = {
        "id": source.id,
        "source_key": source.source_key,
        "name": source.name,
        "url": source.url,
        "feed_url": source.feed_url,
        "source_type": source.source_type,
        "active": source.active,
        "last_crawled": source.last_crawled.isoformat() if source.last_crawled else None,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        "last_error": source.last_error,
        "disabled_at": source.disabled_at.isoformat() if source.disabled_at else None,
    }
    if include_stats:
        result.update({
            "consecutive_failures": source.consecutive_failures or 0,
            "consecutive_successes": source.consecutive_successes or 0,
            "last_success_at": (
                source.last_success_at.isoformat() if source.last_success_at else None
            ),
        })
    return result
```

3. **Create `services/cache_utils.py`:**
```python
from logging import getLogger

logger = getLogger(__name__)

_PUB_CACHE_PREFIXES = ["pub:index", "pub:topic", "pub:rss_feed", "pub:related"]

def invalidate_public_cache(prefixes: list[str] | None = None) -> None:
    """Invalidate public-facing cache prefixes."""
    from services.cache import get_response_cache
    
    try:
        cache = get_response_cache()
        for prefix in (prefixes or _PUB_CACHE_PREFIXES):
            cache.invalidate_prefix(prefix)
    except Exception as e:
        logger.warning("Failed to invalidate cache: %s", e)
```

4. **Update all files to use shared utilities**

#### Verification
```bash
.venv/bin/ruff check services/utils.py services/serializers.py services/cache_utils.py
pytest tests/
```

---

### M2: Add Circuit Breaker to Webhook Deliveries

**File:** `services/webhooks.py`  
**Severity:** MEDIUM - Resilience  
**Estimated Time:** 1.5 hours

#### Current State
Webhook deliveries have retry logic with exponential backoff, but no circuit breaker. A failing webhook endpoint can cause repeated timeouts across multiple delivery attempts.

LLM and search services already use circuit breakers via `services/circuit_breaker.py`.

#### Required Changes

1. **Add circuit breaker configuration (near top of `services/webhooks.py`):**
```python
from services.circuit_breaker import get_breaker

# Circuit breaker settings for webhooks
WEBHOOK_CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("WEBHOOK_CIRCUIT_FAILURE_THRESHOLD", "5"))
WEBHOOK_CIRCUIT_RECOVERY_TIMEOUT = float(os.environ.get("WEBHOOK_CIRCUIT_RECOVERY_TIMEOUT", "60.0"))
WEBHOOK_CIRCUIT_WINDOW_SECONDS = float(os.environ.get("WEBHOOK_CIRCUIT_WINDOW_SECONDS", "120.0"))
```

2. **Modify `dispatch_webhook()` function:**
```python
def dispatch_webhook(
    webhook_id: int,
    name: str,
    url: str,
    secret: str,
    event_type: str,
    event_data: dict[str, Any],
    idempotency_key: str | None = None,
) -> tuple[bool, str | None]:
    
    # ... existing idempotency and URL validation checks ...
    
    # CHECK CIRCUIT BREAKER
    breaker = get_breaker(
        f"webhook:{webhook_id}",
        failure_threshold=WEBHOOK_CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout=WEBHOOK_CIRCUIT_RECOVERY_TIMEOUT,
        window_seconds=WEBHOOK_CIRCUIT_WINDOW_SECONDS,
    )
    
    if not breaker.can_execute():
        logger.warning(
            "Webhook '%s' (ID: %d) skipped: circuit breaker is OPEN",
            name,
            webhook_id,
        )
        # Record skipped event in database
        # ... create WebhookEvent with error status ...
        return False, "Circuit breaker open - webhook delivery skipped"
    
    # Proceed with delivery
    try:
        success, error, status_code, response_body, attempt_number = _send_webhook_with_retry(
            url, payload, secret, event_type
        )
        
        if success:
            breaker.record_success()
        else:
            breaker.record_failure()
            
        # ... rest of existing logic ...
        
    except Exception as e:
        breaker.record_failure()
        raise
```

3. **Add tests in `tests/test_webhooks.py`:**
```python
def test_webhook_circuit_breaker_open_skips_delivery(self, app):
    """When circuit breaker is open, webhook delivery should be skipped."""
    from services.circuit_breaker import get_breaker
    
    with app.app_context():
        webhook = Webhook(...)
        db.session.add(webhook)
        db.session.commit()
        
        # Force circuit open
        breaker = get_breaker(f"webhook:{webhook.id}")
        for _ in range(5):
            breaker.record_failure()
        
        # Now dispatch should skip
        success, error = dispatch_webhook(...)
        assert success is False
        assert "circuit breaker" in error.lower()
```

#### Verification
```bash
pytest tests/test_webhooks.py -v
# Monitor circuit breaker status via admin API
curl /admin/api/v1/config/metrics | jq '.circuit_breaker'
```

---

### M3: Refactor RedisCircuitBreaker to Use Composition

**File:** `services/circuit_breaker.py` (lines 183-380)  
**Severity:** MEDIUM - Architecture  
**Estimated Time:** 3 hours

#### Current State
`RedisCircuitBreaker` extends `CircuitBreaker` but reimplements most of the core logic. This creates:
- Code duplication (state transition logic in 2 places)
- Dual state problem (both Redis and in-memory updated simultaneously)
- Violation of Liskov Substitution Principle

#### Recommended Approach: Strategy Pattern with Storage Backend

1. **Create `CircuitBreakerStorage` abstract base class:**
```python
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreakerStorage(ABC):
    """Abstract storage backend for circuit breaker state."""
    
    @abstractmethod
    def get_state(self) -> Optional[State]: ...
    
    @abstractmethod
    def set_state(self, state: State) -> None: ...
    
    @abstractmethod
    def get_opened_at(self) -> float: ...
    
    @abstractmethod
    def set_opened_at(self, timestamp: float) -> None: ...
    
    @abstractmethod
    def get_half_open_calls(self) -> int: ...
    
    @abstractmethod
    def increment_half_open_calls(self) -> int: ...
    
    @abstractmethod
    def reset_half_open_calls(self) -> None: ...
    
    @abstractmethod
    def get_failure_count(self) -> int: ...
    
    @abstractmethod
    def record_failure(self, now: float, window_seconds: float) -> int: ...
    
    @abstractmethod
    def clear_failures(self) -> None: ...
```

2. **Implement `MemoryCircuitBreakerStorage`:** (in-memory using thread-safe operations)

3. **Implement `RedisCircuitBreakerStorage`:** (Redis-backed using hash maps and sorted sets)

4. **Refactor `CircuitBreaker` to accept storage backend:**
```python
class CircuitBreaker:
    """A circuit breaker that prevents cascading failures.
    
    Uses a pluggable storage backend (memory or Redis).
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        window_seconds: float = 120.0,
        storage: Optional[CircuitBreakerStorage] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.window_seconds = window_seconds
        
        if storage is None:
            storage = MemoryCircuitBreakerStorage(name)
        self._storage = storage
        
        # Fallback for fail-closed (per AGENTS.md)
        self._fallback_storage: Optional[CircuitBreakerStorage] = None
        if not isinstance(storage, MemoryCircuitBreakerStorage):
            self._fallback_storage = MemoryCircuitBreakerStorage(name)
```

5. **Update `get_breaker()` factory:**
```python
def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    redis_client: Optional["redis.Redis"] = None,
    **kwargs,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    with _registry_lock:
        if name not in _breakers:
            redis_storage = RedisCircuitBreakerStorage(name, redis_client)
            _breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                storage=redis_storage,
                **kwargs,
            )
        return _breakers[name]
```

#### Verification
```bash
.venv/bin/ruff check services/circuit_breaker.py
pytest tests/test_circuit_breaker.py -v
```

---

### M4: Cache Encryption Key Validation Result

**File:** `services/webhooks.py` (lines 29-46)  
**Severity:** MEDIUM - Thread safety  
**Estimated Time:** 15 minutes

#### Current State
The `_get_encryption_key()` function caches the validated key in `_ENCRYPTION_KEY` module-level variable. However, the implementation is not thread-safe - there's a race condition where multiple threads could validate and set the key simultaneously.

#### Required Changes
```python
import threading

_ENCRYPTION_KEY: bytes | None = None
_FALLBACK_KEYS: list[bytes] = []
_ENCRYPTION_KEY_LOCK = threading.Lock()  # Add lock

def _get_encryption_key() -> bytes:
    """Get or validate the primary webhook encryption key from environment."""
    global _ENCRYPTION_KEY
    
    # Fast path: return cached key if available
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY
    
    # Slow path: acquire lock and validate
    with _ENCRYPTION_KEY_LOCK:
        # Double-check pattern
        if _ENCRYPTION_KEY is not None:
            return _ENCRYPTION_KEY
        
        key = os.environ.get("WEBHOOK_SECRET_KEY", "")
        if not key:
            raise RuntimeError("WEBHOOK_SECRET_KEY environment variable must be set")
        
        from cryptography.fernet import Fernet
        try:
            Fernet(key.encode("utf-8"))
        except Exception:
            raise ValueError(
                f"WEBHOOK_SECRET_KEY must be a valid Fernet key (44 base64 chars), got length {len(key)}"
            )
        
        _ENCRYPTION_KEY = key.encode("utf-8")
        _load_fallback_keys()
        return _ENCRYPTION_KEY
```

#### Verification
```bash
.venv/bin/ruff check services/webhooks.py
pytest tests/test_webhooks.py -v
```

---

## Low Priority Items

### L1: Make DNS Cache TTL Configurable

**File:** `services/url.py` (line 49)  
**Severity:** LOW - Configurability  
**Estimated Time:** 10 minutes

#### Current State
DNS cache TTL is hardcoded to 5 seconds to prevent DNS rebinding attacks. Should be configurable for environments where longer caching is acceptable.

#### Required Changes
```python
# In services/url.py, change:
# From:
session = requests.Session()
session.adapters["http://"].poolmanager.connection_pool_kw["dns_cache_ttl"] = 5
session.adapters["https://"].poolmanager.connection_pool_kw["dns_cache_ttl"] = 5

# To:
DNS_CACHE_TTL = int(os.environ.get("DNS_CACHE_TTL_SECONDS", "5"))

session = requests.Session()
session.adapters["http://"].poolmanager.connection_pool_kw["dns_cache_ttl"] = DNS_CACHE_TTL
session.adapters["https://"].poolmanager.connection_pool_kw["dns_cache_ttl"] = DNS_CACHE_TTL
```

#### Verification
```bash
DNS_CACHE_TTL_SECONDS=10 .venv/bin/python -c "from services.url import DNS_CACHE_TTL; print(DNS_CACHE_TTL)"
```

---

### L2: Add ConfigCache Deserialization Whitelist

**File:** `services/config_cache.py` (lines 58-73)  
**Severity:** LOW - Security hardening  
**Estimated Time:** 20 minutes

#### Current State
The `_import_class()` function uses a prefix check (`startswith("schemas.")`) which allows ANY class from ANY `schemas.*` module to be imported. Should use explicit whitelist.

#### Required Changes
```python
# Explicit whitelist of allowed classes for deserialization from Redis
_ALLOWED_CLASSES: frozenset[str] = frozenset({
    "schemas.pipeline.PipelineRootConfig",
    "schemas.llm.LLMProvidersConfig",
    "schemas.source.SourceConfig",
    "schemas.topic.TopicsConfig",
    "schemas.search.SearchConfig",
})

def _import_class(dotted_path: str) -> type:
    """Import a class from a dotted module path.
    
    Only classes in the _ALLOWED_CLASSES whitelist are permitted.
    Raises ValueError for any other path to prevent arbitrary module imports.
    """
    if dotted_path not in _ALLOWED_CLASSES:
        raise ValueError(f"Class path not in allowlist: {dotted_path}")
    
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    
    if not (inspect.isclass(cls) and issubclass(cls, BaseModel)):
        raise ValueError(f"Class is not a Pydantic BaseModel: {dotted_path}")
    
    return cls
```

#### Verification
```bash
.venv/bin/ruff check services/config_cache.py
pytest tests/test_config_cache.py -v
```

---

### L3: Use Shared Redis Connection Pool

**Files:**
- `services/cache.py` (already uses shared pool via `extensions.py`)
- `services/config_cache.py` (creates own pool)
- `services/circuit_breaker.py` (creates new connection per instance)
- `extensions.py` (has shared pool)

**Severity:** LOW - Resource management  
**Estimated Time:** 2 hours

#### Current State
Inconsistent Redis connection management across modules. `circuit_breaker.py` doesn't use pooling at all (creates new connections via `redis.from_url()`).

#### Required Changes

1. **Create `services/redis_pool.py`:**
```python
"""Centralized Redis connection pool management."""
import logging
import os
import threading
from typing import Optional

import redis

logger = logging.getLogger(__name__)

_pools: dict[str, redis.ConnectionPool] = {}
_clients: dict[str, redis.Redis] = {}
_lock = threading.Lock()

def get_pool(name: str = "main", url: Optional[str] = None, **kwargs) -> redis.ConnectionPool:
    """Get or create a named Redis connection pool (thread-safe)."""
    if name in _pools:
        return _pools[name]
    
    with _lock:
        if name in _pools:
            return _pools[name]
        
        if url is None:
            url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        
        # Apply kwargs (max_connections, socket_timeout, etc.)
        pool_kwargs = {"max_connections": int(os.environ.get("REDIS_MAX_CONNECTIONS", "100"))}
        pool_kwargs.update(kwargs)
        
        _pools[name] = redis.ConnectionPool.from_url(url, **pool_kwargs)
        logger.info("Created Redis pool '%s'", name)
        return _pools[name]

def get_redis_client(name: str = "main", **pool_kwargs) -> redis.Redis:
    """Get or create a Redis client backed by a shared pool."""
    if name in _clients:
        return _clients[name]
    
    with _lock:
        if name in _clients:
            return _clients[name]
        
        pool = get_pool(name, **pool_kwargs)
        _clients[name] = redis.Redis(connection_pool=pool)
        return _clients[name]

def reset_all_pools() -> None:
    """Disconnect and clear all pools (for testing)."""
    with _lock:
        for pool in _pools.values():
            pool.disconnect()
        _pools.clear()
        _clients.clear()
```

2. **Update `extensions.py` to use shared pool:**
```python
def get_redis():
    """Return a Redis client backed by shared connection pool."""
    from services.redis_pool import get_redis_client
    return get_redis_client("main")
```

3. **Update `services/config_cache.py`:**
```python
def get_config_cache() -> ConfigCache:
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    
    with _cache_lock:
        if _cache_instance is not None:
            return _cache_instance
        
        from services.redis_pool import get_redis_client
        client = get_redis_client("config", db=1)
        _cache_instance = ConfigCache(client, prefix="ainews:config")
        return _cache_instance
```

4. **Update `services/circuit_breaker.py`:**
```python
def _get_redis(self) -> Optional["redis.Redis"]:
    """Get Redis client from shared pool."""
    if self._redis_client is not None:
        return self._redis_client
    try:
        from services.redis_pool import get_redis_client
        self._redis_client = get_redis_client("main")
        return self._redis_client
    except Exception:
        logger.debug("Failed to connect to Redis", exc_info=True)
        return None
```

#### Verification
```bash
.venv/bin/ruff check services/redis_pool.py
pytest tests/test_redis_pool.py
```

---

### L4: Add Type Hints to Internal Functions

**Files:** Multiple service files  
**Severity:** LOW - Code quality  
**Estimated Time:** 1-2 hours

#### Current State
Mixed type hint usage across codebase. Some internal functions lack complete type hints.

#### Standard to Adopt
```python
from __future__ import annotations
from typing import Any, Optional

from models import Article

def _internal_function(
    article: Article,
    config: dict[str, Any],
    run_id: int | None = None,
) -> None:
    ...
```

#### Files Needing Updates
- `services/content_extractor.py` - Add `from __future__ import annotations`
- `services/pipeline_degradation.py` - Add type hints to 8 functions
- `services/pipeline_utils.py` - Add type hints to 3 functions
- `services/pipeline_failure.py` - Add type hints to 3 functions

#### Verification
```bash
.venv/bin/ruff check services/
# Optionally run mypy if configured
```

---

### L5: Standardize Singleton Pattern Across Services

**Files:**
- `services/cache.py`
- `services/metrics.py`
- `services/limiter.py`
- `services/config_cache.py`
- `extensions.py`

**Severity:** LOW - Standardization  
**Estimated Time:** 2 hours

#### Current State
All singletons use double-checked locking pattern with duplicated boilerplate code.

#### Solution: Create `SingletonManager` in `services/singleton.py`

```python
"""Thread-safe singleton manager utility."""
import threading
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")

class SingletonManager(Generic[T]):
    """Thread-safe singleton manager with factory function."""
    
    def __init__(self, factory: Callable[[], T]):
        self._factory = factory
        self._instance: Optional[T] = None
        self._lock = threading.Lock()
    
    def get(self) -> T:
        """Get singleton instance (thread-safe, lazy initialization)."""
        if self._instance is not None:
            return self._instance
        with self._lock:
            if self._instance is not None:
                return self._instance
            self._instance = self._factory()
            return self._instance
    
    def reset(self) -> None:
        """Reset singleton (for testing)."""
        with self._lock:
            self._instance = None
    
    @property
    def is_initialized(self) -> bool:
        return self._instance is not None
```

#### Migration Example (ResponseCache)
```python
from services.singleton import SingletonManager

def _create_response_cache() -> ResponseCache:
    from extensions import get_redis
    return ResponseCache(get_redis())

_response_cache_mgr = SingletonManager(_create_response_cache)

def get_response_cache() -> ResponseCache:
    return _response_cache_mgr.get()

def reset_response_cache() -> None:
    _response_cache_mgr.reset()
```

#### Verification
```bash
.venv/bin/ruff check services/singleton.py
pytest tests/
```

---

## Implementation Order and Dependencies

### Phase 1: Critical Security & Bug Fixes (Do First)
1. **H1** - Fix API tokens auth (security vulnerability)
2. **H3** - Fix limiter fail-closed (policy compliance)
3. **H4** - Fix N+1 query (performance)

### Phase 2: Consistency & Production Safety
4. **H5** - Standardize API responses
5. **H6** - Replace Redis KEYS with SCAN
6. **H7** - Standardize retry configuration

### Phase 3: Medium Priority Improvements
7. **M1** - Reduce code duplication
8. **M4** - Cache encryption key validation
9. **M2** - Add webhook circuit breaker
10. **M3** - Refactor RedisCircuitBreaker (largest task)

### Phase 4: Low Priority Polish
11. **L1** - DNS cache TTL configurable
12. **L2** - ConfigCache whitelist
13. **L3** - Shared Redis pool
14. **L4** - Type hints
15. **L5** - Singleton pattern

---

## Testing Strategy

### For Each Item:
1. **Unit tests:** New tests in `tests/` directory
2. **Lint:** Run `.venv/bin/ruff check . --exclude .venv`
3. **Integration tests:** Run `.venv/bin/python -m pytest tests/ -x -q`
4. **Manual verification:** For security fixes, manually test the fix

### Key Test Files to Create/Update:
- `tests/test_api_auth.py` - Test API token authentication
- `tests/test_circuit_breaker.py` - Test webhook circuit breaker
- `tests/test_redis_pool.py` - Test shared connection pool
- `tests/test_singleton.py` - Test SingletonManager

---

## Rollback Plan

For each change, the pattern is:
1. Create feature branch: `git checkout -b fix/plan7-item-name`
2. Implement change
3. Run tests: `.venv/bin/python -m pytest tests/ -x -q`
4. Run lint: `.venv/bin/ruff check . --exclude .venv`
5. If all passes: `git commit -m "fix: description"`
6. If fails: `git reset --hard HEAD~1` to rollback

For database changes (none in this plan) or Redis changes:
- Config changes can be reverted by removing env vars
- Redis data is ephemeral (cache), so restart Redis if needed

---

## Summary

| Priority | Items | Est. Time | Dependencies |
|----------|-------|-----------|--------------|
| High | H1, H3, H4, H5, H6, H7 | ~3 hours | None |
| Medium | M1, M2, M3, M4 | ~7 hours | H5 (for M1) |
| Low | L1, L2, L3, L4, L5 | ~6 hours | L3 for some |

**Total Estimated Time:** 16-20 hours

**Recommended Approach:** Implement in phases, with testing after each phase. High priority items can be done in parallel by different developers.

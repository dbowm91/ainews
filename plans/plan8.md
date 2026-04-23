# Codebase Improvement Plan — General Enhancements

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Source**: Comprehensive Codebase Review — 2026-04-23

---

## Executive Summary

This plan addresses structural, reliability, and maintainability improvements identified during a comprehensive codebase review. Issues are categorized by priority based on impact and effort.

| Priority | Category | Issues | Effort |
|----------|----------|--------|--------|
| 🔴 Critical | Error Handling | 2 | 30 min |
| 🟡 Medium | Database Indexes | 6 | 45 min |
| 🟡 Medium | Test Infrastructure | 5 | 2 hours |
| 🟡 Medium | Configuration | 4 | 1 hour |
| 🟢 Low | Code Quality | 7 | 3 hours |
| 🟢 Low | Performance | 3 | 2 hours |

---

## Priority 1: 🔴 CRITICAL — Error Handling

### 1.1 JSON Parse Without Error Handling in Edit Stage

**Severity**: CRITICAL
**Risk**: `json.loads()` on malformed `final_article` causes pipeline crash. Article stuck in EDITING with no recovery path.

**Current State**: `tasks/edit.py:270-274`:

```python
# Line 270-274
if isinstance(final_article, str):
    fa = json.loads(final_article)  # No try/except!
else:
    fa = final_article
```

**Vulnerable Flow**:
1. Write stage stores malformed JSON in `draft_article`
2. Edit stage reads `draft_article`, assigns to `final_article`
3. `json.loads(final_article)` raises `json.JSONDecodeError`
4. Exception propagates to `run_stage()` → rollback → article marked FAILED
5. No fallback, article requires manual intervention

**Required Changes**:

```python
# Line 270-274: Wrap in try/except
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

**Action Items**:
- [ ] Add try/except around `json.loads(final_article)` at line 270
- [ ] Implement fallback to `draft_article` on parse failure
- [ ] Add final fallback with original_title if both fail
- [ ] Add warning log with article ID for monitoring

**Effort**: 15 minutes
**Risk**: None (defensive coding improves reliability)

**Testing**:
```bash
# Create article with malformed final_article
# Verify edit stage doesn't crash
# Check logs for warning message
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/test_pipeline.py -v -k edit
```

---

### 1.2 Silent Duplicate Check Failure in Extract

**Severity**: CRITICAL
**Risk**: Duplicate detection fails silently, creating duplicate articles from different sources.

**Current State**: `tasks/extract.py:154-158`:

```python
# Lines 154-158
try:
    duplicate = _find_duplicate_article(source_id, url, title, text_content)
except Exception as e:
    logger.warning("Dedup check failed for %s: %s", url, e)
    duplicate = None  # Swallows error, continues as if no duplicate
```

**Vulnerable Flow**:
1. `_find_duplicate_article()` raises exception (Redis down, DB error, etc.)
2. Exception caught, `duplicate = None`
3. `process_item()` continues, creates new Article record
4. Duplicate articles accumulate

**Required Changes**:

```python
# Lines 154-158: Add alert and metric
try:
    duplicate = _find_duplicate_article(source_id, url, title, text_content)
except Exception as e:
    logger.warning("Dedup check failed for %s: %s", url, e)
    duplicate = None
    # Emit metric for monitoring
    metrics.increment("pipeline.dedup_check_failed", tags={"source": source_key})
```

**Action Items**:
- [ ] Add metric emission on dedup check failure
- [ ] Consider failing the stage if dedup is critical (configurable)
- [ ] Add alert for repeated failures

**Effort**: 15 minutes
**Risk**: Low (improves visibility)

**Testing**:
```bash
# Mock _find_duplicate_article to raise exception
# Verify metric is emitted
# Verify article processing continues (current behavior preserved)
```

---

## Priority 2: 🟡 MEDIUM — Database Indexes

### 2.1 Missing Index: Subscriber (active, deleted_at)

**Severity**: MEDIUM
**Risk**: `get_active()` query slow, affecting newsletter delivery performance.

**Current State**: `models.py:225-233`:

```python
@classmethod
def get_active(cls):
    return cls.query.filter(cls.deleted_at.is_(None), cls.active.is_(True))
```

**Query Plan**: Without index on `(active, deleted_at)`, full table scan on every newsletter send.

**Required Changes**: New migration adding composite index:

```python
# migrations/versions/025_subscriber_active_index.py
from alembic import op

op.create_index(
    "ix_subscribers_active_deleted",
    "subscribers",
    ["active", "deleted_at"],
    unique=False
)
```

**Action Items**:
- [ ] Create migration `025_subscriber_active_index.py`
- [ ] Update model to include index definition
- [ ] Test get_active() with EXPLAIN QUERY PLAN

**Effort**: 15 minutes
**Risk**: None

---

### 2.2 Missing Index: WebhookEvent (webhook_id, delivered_at)

**Severity**: MEDIUM
**Risk**: Event history queries slow for webhooks with many deliveries.

**Current State**: `models.py:429-445` — WebhookEvent has no composite index.

**Required Changes**:

```python
# migrations/versions/026_webhook_event_index.py
op.create_index(
    "ix_webhook_events_webhook_delivered",
    "webhook_events",
    ["webhook_id", "delivered_at"],
    unique=False
)
```

**Action Items**:
- [ ] Create migration for composite index
- [ ] Update model with index definition

**Effort**: 10 minutes

---

### 2.3 Missing Index: PipelineRun (run_type, status)

**Severity**: MEDIUM
**Risk**: Filtering runs by type and status slow in admin dashboard.

**Current State**: `models.py:271-291` — PipelineRun has no composite index.

**Required Changes**:

```python
# migrations/versions/027_pipeline_run_type_status_index.py
op.create_index(
    "ix_pipeline_runs_type_status",
    "pipeline_runs",
    ["run_type", "status"],
    unique=False
)
```

**Action Items**:
- [ ] Create migration for composite index

**Effort**: 10 minutes

---

### 2.4 Missing Index: AuditLog (action, created_at)

**Severity**: MEDIUM
**Risk**: Action-based time queries require full scan for audit log analysis.

**Current State**: `models.py:448-463` — AuditLog has no index on `(action, created_at)`.

**Required Changes**:

```python
# migrations/versions/028_audit_log_action_index.py
op.create_index(
    "ix_audit_logs_action_created",
    "audit_logs",
    ["action", "created_at"],
    unique=False
)
```

**Action Items**:
- [ ] Create migration for composite index

**Effort**: 10 minutes

---

### 2.5 Add Unique Constraint: PipelineRun.task_id

**Severity**: MEDIUM
**Risk**: Duplicate runs can be created with same task_id, causing monitoring issues.

**Current State**: `models.py:271-291` — task_id has no unique constraint.

**Required Changes**:

```python
# Note: SQLite doesn't support ALTER TABLE to add constraint
# This requires recreate table or migration handling
# See migration 011_cascade_deletes.py for SQLite limitations

# For PostgreSQL deployments, add:
op.create_unique_constraint(
    "uq_pipeline_runs_task_id",
    "pipeline_runs",
    ["task_id"]
)
```

**Action Items**:
- [ ] Add note to README about SQLite limitation
- [ ] Add check in application logic to prevent duplicate task_id on create
- [ ] Consider using INSERT ON CONFLICT for PostgreSQL

**Effort**: 15 minutes

---

### 2.6 Add Unique Constraint: Newsletter (newsletter_type, date)

**Severity**: MEDIUM
**Risk**: Duplicate daily newsletters can be generated for same type.

**Current State**: `models.py:176-191` — Newsletter has no date field, but could use `DATE(generated_at)` for uniqueness.

**Required Changes**:

```python
# Alternative: Add computed date column or use unique constraint on (newsletter_type, generated_at::date)
# This is PostgreSQL-specific; SQLite would need different approach

# For PostgreSQL:
op.create_unique_constraint(
    "uq_newsletter_type_date",
    "newsletters",
    ["newsletter_type", "generated_at"]  # Or DATE(generated_at) if supported
)
```

**Action Items**:
- [ ] Determine if SQLite deployment needs different approach
- [ ] Add idempotency check in newsletter generation task

**Effort**: 15 minutes

---

## Priority 3: 🟡 MEDIUM — Test Infrastructure

### 3.1 Create Shared MockRedis Fixture

**Severity**: MEDIUM
**Risk**: Tests using different Redis mock implementations may behave inconsistently.

**Current State**: `conftest.py` provides `mock_redis` as plain `MagicMock()`. `mock_redis.py` has `MockRedis` with real in-memory storage, but tests create their own instances.

**Required Changes**:

```python
# In conftest.py, add:
@pytest.fixture
def mock_redis_client():
    """In-memory Redis mock with real side effects."""
    from tests.mock_redis import MockRedis
    return MockRedis()

# Replace mock_redis fixture with shared implementation
@pytest.fixture
def mock_redis():
    """Legacy fixture - returns plain MagicMock for backwards compatibility."""
    return MagicMock()
```

**Action Items**:
- [ ] Create `mock_redis_client` fixture in conftest.py
- [ ] Update tests needing stateful Redis to use new fixture
- [ ] Keep `mock_redis` for tests needing full control

**Effort**: 30 minutes

---

### 3.2 Add Autouse DNS Cache Clear Fixture

**Severity**: MEDIUM
**Risk**: DNS cache pollution between tests can cause SSRF validation failures.

**Current State**: `_clear_dns_cache` is imported in some tests but not an autouse fixture in conftest.

**Current Usage** (`test_url.py`):
```python
from services.url import _dns_cache

@pytest.fixture(autouse=True)
def _clear_dns_cache():
    _dns_cache.clear()
    yield
    _dns_cache.clear()
```

**Required Changes**: Move fixture to conftest.py:

```python
# In conftest.py
from services.url import _dns_cache

@pytest.fixture(autouse=True)
def _clear_dns_cache():
    """Clear DNS cache before and after each test to prevent cross-test contamination."""
    _dns_cache.clear()
    yield
    _dns_cache.clear()
```

**Action Items**:
- [ ] Add `_clear_dns_cache` autouse fixture to conftest.py
- [ ] Remove duplicate fixtures from individual test files

**Effort**: 15 minutes

---

### 3.3 Create Celery Task Test Helper

**Severity**: MEDIUM
**Risk**: Complex Celery task testing boilerplate leads to errors and incomplete tests.

**Current State**: Testing Celery tasks requires:
1. `@patch.dict("os.environ", {"CELERY_TASK_SECRET": "..."})`
2. Calling `task_fn.__wrapped__(...)` directly
3. Creating `MagicMock()` for `task_self.request.id`
4. Wrapping in `app.app_context()`

**Example from tests**:
```python
@patch.dict("os.environ", {"CELERY_TASK_SECRET": "test-secret-key-at-least-32-chars-long"})
def test_something(self, app):
    with app.app_context():
        task_self = MagicMock()
        task_self.request.id = "task-test"
        result = crawl_source.__wrapped__(cfg, run_id=1)
```

**Required Changes**: Create helper in `tests/helpers/celery.py`:

```python
# tests/helpers/celery.py
import os
from contextlib import contextmanager
from unittest.mock import MagicMock

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

**Action Items**:
- [ ] Create `tests/helpers/celery.py` with helper functions
- [ ] Update key test files to use the helper
- [ ] Document usage in conftest.py

**Effort**: 45 minutes

---

### 3.4 Document get_provider_for_role 4-Tuple Contract

**Severity**: MEDIUM
**Risk**: Tests break when mock return value doesn't match actual function signature.

**Current State**: `get_provider_for_role()` returns 4-tuple `(provider, model, max_tokens, provider_type)`. Tests that mock this function must match this signature exactly.

**Documentation Needed**: Add docstring and test comment:

```python
# In services/llm/__init__.py or wherever get_provider_for_role is defined
def get_provider_for_role(role: str) -> tuple["BaseLLMProvider", str, int, str]:
    """Get LLM provider for pipeline stage role.

    Returns:
        tuple: (provider_instance, model_name, max_tokens, provider_type)
            - provider_instance: BaseLLMProvider subclass instance
            - model_name: str model identifier (e.g., "qwen3:8b")
            - max_tokens: int maximum tokens for completion
            - provider_type: str (e.g., "ollama", "openai")
    """
```

**Action Items**:
- [ ] Add return type annotation to `get_provider_for_role`
- [ ] Add docstring with tuple structure
- [ ] Update `setup_pipeline_mocks` to include comment about 4-tuple

**Effort**: 15 minutes

---

### 3.5 Add ResponseCache Test Fixture

**Severity**: MEDIUM
**Risk**: Tests needing ResponseCache create their own redis_client, leading to inconsistency.

**Current State**: `test_response_cache.py` creates local `redis_client` fixture:

```python
@pytest.fixture
def redis_client():
    store = {}
    client = MagicMock()
    # ... custom implementation
```

**Required Changes**:

```python
# In conftest.py
@pytest.fixture
def response_cache_setup(mock_redis_client):
    """Provide ResponseCache with mocked Redis for testing."""
    from services.cache import ResponseCache
    cache = ResponseCache()
    cache._redis = mock_redis_client
    return cache
```

**Action Items**:
- [ ] Create `response_cache_setup` fixture in conftest.py
- [ ] Update tests to use shared fixture

**Effort**: 30 minutes

---

## Priority 4: 🟡 MEDIUM — Configuration

### 4.1 Document Missing Environment Variables

**Severity**: MEDIUM
**Risk**: Deployments fail due to undocumented required environment variables.

**Current State**: `.env.example` missing many used env vars.

**Missing from .env.example**:

| Variable | Purpose | Required |
|----------|---------|----------|
| `CELERY_TASK_SECRET` | HMAC signing for Celery tasks | Yes (production) |
| `WEBHOOK_SECRET_KEY` | Fernet encryption for webhook secrets | Yes (if using webhooks) |
| `GOOGLE_API_KEY` | Google search provider | No |
| `GOOGLE_CSE_ID` | Google Custom Search Engine ID | No |
| `DEAD_LETTER_ALERT_THRESHOLD` | Alert threshold for stuck articles | No |
| `CONFIG_CACHE_REDIS_URL` | Separate Redis for config cache | No |

**Required Changes**:

```bash
# Add to .env.example

# =============================================================================
# CELERY SECURITY
# =============================================================================
# Secret for HMAC signing of Celery task arguments (minimum 32 characters)
CELERY_TASK_SECRET=

# =============================================================================
# WEBHOOKS
# =============================================================================
# Fernet encryption key for webhook secrets
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
WEBHOOK_SECRET_KEY=

# =============================================================================
# SEARCH PROVIDERS (Optional)
# =============================================================================
GOOGLE_API_KEY=
GOOGLE_CSE_ID=

# =============================================================================
# ALERTING
# =============================================================================
# Dead letter alert threshold (default: 10)
DEAD_LETTER_ALERT_THRESHOLD=10
```

**Action Items**:
- [ ] Update .env.example with all missing variables
- [ ] Update docs/configuration.md with complete variable list
- [ ] Add comments explaining generation commands

**Effort**: 30 minutes

---

### 4.2 Clean Up Duplicate Beat Schedule Definition

**Severity**: MEDIUM
**Risk**: Confusion about which schedule definition is actually used; potential for stale config.

**Current State**: `config.py` has:
1. `CeleryBeatConfig.CELERY_BEAT_SCHEDULE` class attribute (static)
2. `get_beat_schedule()` function reading from `pipeline.yaml` (dynamic)

The class attribute is dead code - never used in production.

**Required Changes**:

```python
# In config.py

class CeleryBeatConfig:
    """DEPRECATED: Use get_beat_schedule() instead.
    
    This class attribute is kept for reference only.
    Actual beat schedule is loaded from pipeline.yaml.
    """
    CELERY_BEAT_SCHEDULE = {}  # Empty - replaced by get_beat_schedule()
```

**Action Items**:
- [ ] Add deprecation comment to CeleryBeatConfig class attribute
- [ ] Verify get_beat_schedule() is used everywhere
- [ ] Remove dead code if confirmed

**Effort**: 15 minutes

---

### 4.3 Validate ENV_VAR Resolution

**Severity**: MEDIUM
**Risk**: Empty `${ENV_VAR}` placeholders pass validation, causing silent failures.

**Current State**: `resolve_env_vars()` in `schemas/common.py` replaces `${VAR}` with value, but empty strings are not re-validated.

**Example**:
```yaml
api_key: ${MISSING_API_KEY}  # Resolves to empty string ""
```

**Required Changes**:

```python
# In schemas/common.py resolve_env_vars()
def resolve_env_var(value: str) -> str:
    match = _ENV_VAR_PATTERN.match(value)
    if match:
        env_value = os.environ.get(match.group(1), "")
        if not env_value:
            # Log warning once per variable
            _warn_missing_env_var(match.group(1))
        return env_value
    return value
```

**Action Items**:
- [ ] Add warning log when env var is missing/empty
- [ ] Consider adding validation in validate_config()

**Effort**: 15 minutes

---

### 4.4 Beat Schedule Reload Fix

**Severity**: MEDIUM
**Risk**: `reload_beat_schedule()` may not properly clear Celery's internal schedule cache.

**Current State**: `routes/admin/api/config.py:reload_config()` calls:
1. `get_config_cache().invalidate_all()`
2. `clear_app_cache()` (from celery_support.py)
3. `Config.reload_beat_schedule(celery_app)`

**Required Changes**: Verify Celery beat schedule reload:

```python
# In config.py
def reload_beat_schedule(celery_app):
    # Clear Celery's internal beat schedule cache
    celery_app.conf.beat_schedule = get_beat_schedule()
    # Force Celery to reload
    celery_app.conf.changed = True
```

**Action Items**:
- [ ] Test reload_beat_schedule() with actual config change
- [ ] Verify Celery workers pick up new schedule
- [ ] Add logging for schedule reload

**Effort**: 30 minutes

---

## Priority 5: 🟢 LOW — Code Quality

### 5.1 Add Tag.articles Backref

**Severity**: LOW
**Risk**: Inconsistent ORM model relationships.

**Current State**: `Article.tags` has many-to-many relationship via `article_tags` table. `Tag` model has no backref.

**Required Changes**:

```python
# In models.py, add to Tag class:
articles = db.relationship(
    "Article",
    secondary=article_tags,
    backref=db.backref("tags", lazy="selectin"),
    lazy="dynamic"
)
```

**Action Items**:
- [ ] Add articles relationship to Tag model

**Effort**: 10 minutes

---

### 5.2 Trend Memory Deduplication

**Severity**: LOW
**Risk**: Same signal proposed multiple times for same topic creates noise.

**Current State**: `propose_trend_memory()` doesn't check for existing similar entries before creating new ones.

**Required Changes**:

```python
# In services/trend_memory.py, add check before saving:
def _is_duplicate_signal(topic: str, signal: str, similarity_threshold: float = 0.8) -> bool:
    existing = TrendMemory.query.filter(
        TrendMemory.topic == topic,
        TrendMemory.expires_at > datetime.now(timezone.utc)
    ).all()
    for entry in existing:
        # Jaccard similarity on word sets
        signal_words = set(signal.lower().split())
        entry_words = set(entry.signal.lower().split())
        if signal_words and entry_words:
            intersection = len(signal_words & entry_words)
            union = len(signal_words | entry_words)
            if union > 0 and intersection / union >= similarity_threshold:
                return True
    return False
```

**Action Items**:
- [ ] Add `_is_duplicate_signal()` function
- [ ] Use in `propose_trend_memory()` before saving

**Effort**: 45 minutes

---

### 5.3 Subagent Chain Escaping Fix

**Severity**: LOW
**Risk**: Chain step results from previous steps aren't re-escaped, could cause XML injection.

**Current State**: `run_subagent_chain()` calls `_escape_prompt_data()` once, but subsequent template formatting may introduce new special characters.

**Required Changes**: Add re-escape in chain processing:

```python
# In services/subagent.py run_subagent_chain()
# After each step, escape results before adding to prompt_data
for step in chain_steps:
    result = run_subagent(...)
    # Escape result before adding to context
    prompt_data[step.name] = _escape_prompt_data({"value": result.synthesis})["value"]
```

**Action Items**:
- [ ] Review subagent chain escaping logic
- [ ] Add re-escape for step results

**Effort**: 30 minutes

---

### 5.4 ModelLimiter Initial Poll Interval

**Severity**: LOW
**Risk**: Initial poll interval of 0.05s is aggressive, may cause Redis load.

**Current State**: `services/limiter.py:46` — `poll_interval = 0.05` (50ms)

**Recommended**: Start higher, e.g., 0.1s (100ms) with backoff multiplier of 1.5.

**Required Changes**:

```python
# In services/limiter.py acquire()
poll_interval = 0.1  # Start at 100ms instead of 50ms
max_poll_interval = 0.5
# ... in loop
poll_interval = min(poll_interval * 1.5, max_poll_interval)
```

**Action Items**:
- [ ] Adjust initial poll_interval and backoff multiplier

**Effort**: 15 minutes

---

### 5.5 ResponseCache Second SET NX Fix

**Severity**: LOW
**Risk**: Second SET NX in `get_or_set()` could overwrite legitimate value.

**Current State**: `services/cache.py:155` — Second `SET NX` without checking if value was already populated.

**Required Changes**:

```python
# Line 155: After acquiring lock, check if value was set by first holder
if not cached:
    cached = self.get(key)
if not cached:
    # Only set if still empty
    self.set(key, loader_fn())
```

**Action Items**:
- [ ] Add double-check before second SET NX

**Effort**: 15 minutes

---

### 5.6 Pipeline Stage Failure Redis TTL Refresh

**Severity**: LOW
**Risk**: Early termination triggers on stale failures (7+ days old).

**Current State**: Redis key for stage failures has 7-day TTL but early termination decision doesn't refresh on repeated failures.

**Required Changes**:

```python
# In services/pipeline_failure.py _track_stage_failure()
# Refresh TTL on each failure
stage_key = f"ainews:article:stage_failures:{article_id}:{stage}"
# Use EXPIRE after HINCRBY to refresh TTL
self._redis.expire(stage_key, 604800)  # 7 days
```

**Action Items**:
- [ ] Add TTL refresh on each stage failure

**Effort**: 15 minutes

---

### 5.7 Circuit Breaker State Persistence

**Severity**: LOW
**Risk**: Circuit breaker state lost on worker restart; in-memory only.

**Current State**: `services/circuit_breaker.py` stores state in memory via `threading.Lock`.

**Recommendation**: Consider `pybreaker` library with Redis backend for production deployments.

**Required Changes**: Research and prototype integration:

```python
# In requirements.txt (optional)
pybreaker>=2.0.0

# Usage pattern
import pybreaker
breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)
breaker.redis_backend = redis_client
```

**Action Items**:
- [ ] Research pybreaker vs custom implementation
- [ ] Prototype Redis-backed circuit breaker
- [ ] Document decision

**Effort**: 2 hours

---

## Priority 6: 🟢 LOW — Performance

### 6.1 Trend Memory Batch Consolidation

**Severity**: LOW
**Risk**: `consolidate_all_topics()` runs query per topic with HIGH entries.

**Current State**: `services/trend_memory.py:335-346` — loop queries each topic separately.

**Required Changes**:

```python
# Single query to get all topics needing consolidation
high_entries = TrendMemory.query.filter(
    TrendMemory.importance == MemoryImportance.HIGH.value,
    TrendMemory.expires_at.is_(None)  # HIGH has no expiry
).all()

# Group by topic
from collections import defaultdict
by_topic = defaultdict(list)
for entry in high_entries:
    by_topic[entry.topic].append(entry)

# Process each topic
for topic, entries in by_topic.items():
    consolidate_topic(topic)
```

**Action Items**:
- [ ] Refactor consolidate_all_topics() to batch query

**Effort**: 30 minutes

---

### 6.2 L1 Cache Sampled Eviction Improvement

**Severity**: LOW
**Risk**: Sampled eviction every 100 reads may not be comprehensive enough under high load.

**Current State**: `services/cache.py:94-97` — `_evict_stale()` called on sampled reads.

**Required Changes**: Consider dedicated cleanup task:

```python
# Add Celery task for periodic full eviction
@celery_app.task
def cleanup_stale_cache():
    cache = get_response_cache()
    cache._evict_stale(force=True)  # Full scan
```

**Action Items**:
- [ ] Add periodic cleanup task for L1 cache
- [ ] Consider making eviction comprehensive instead of sampled

**Effort**: 30 minutes

---

### 6.3 Database Session Handling in Trend Memory

**Severity**: LOW
**Risk**: Commit per-entry in batch creates N commits instead of 1.

**Current State**: `services/trend_memory.py:167` — commits after each entry in loop.

**Required Changes**:

```python
# Commit all entries in single transaction
entries_to_save = []
for entry in extracted.entries[:max_entries]:
    trend_entry = TrendMemory(...)
    entries_to_save.append(trend_entry)

db.session.add_all(entries_to_save)
db.session.commit()  # Single commit
```

**Action Items**:
- [ ] Refactor to batch commit

**Effort**: 15 minutes

---

## Implementation Order

```
Phase 1: Critical Error Handling (30 min)
├── 1.1 JSON parse error handling     (15 min)
└── 1.2 Silent dedup failure alert    (15 min)

Phase 2: Database Indexes (45 min)
├── 2.1 Subscriber active index       (15 min)
├── 2.2 WebhookEvent index            (10 min)
├── 2.3 PipelineRun index             (10 min)
└── 2.4 AuditLog index               (10 min)

Phase 3: Test Infrastructure (2 hours)
├── 3.1 MockRedis fixture             (30 min)
├── 3.2 DNS cache autouse            (15 min)
├── 3.3 Celery task helper           (45 min)
└── 3.4/3.5 Documentation/fixtures   (30 min)

Phase 4: Configuration (1 hour)
├── 4.1 Document env vars             (30 min)
├── 4.2 Beat schedule cleanup        (15 min)
├── 4.3 ENV_VAR validation           (15 min)

Phase 5: Code Quality (3 hours)
├── 5.1 Tag backref                  (10 min)
├── 5.2 Trend memory dedup            (45 min)
├── 5.3 Subagent escaping            (30 min)
├── 5.4 Limiter poll interval       (15 min)
├── 5.5 ResponseCache SET NX        (15 min)
├── 5.6 Stage failure TTL refresh    (15 min)
└── 5.7 Circuit breaker persistence  (2 hrs)

Phase 6: Performance (75 min)
├── 6.1 Batch consolidation          (30 min)
├── 6.2 Cache cleanup task           (30 min)
└── 6.3 Batch commit                 (15 min)

Total estimated time: ~7.5 hours
```

---

## Testing Requirements

1. **Before any changes**:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

2. **After error handling changes**:
```bash
# Test malformed JSON handling
# Test dedup check failure metrics
.venv/bin/python -m pytest tests/test_pipeline.py -v -k "edit or extract"
```

3. **After index migrations**:
```bash
# Verify EXPLAIN QUERY PLAN shows index usage
# Run query_analysis.sh script
./scripts/query_analysis.sh
```

4. **After test infrastructure changes**:
```bash
# Run full test suite with new fixtures
.venv/bin/python -m pytest tests/ -x -q
```

---

## Rollback Plan

| Change | Rollback Method |
|--------|-----------------|
| JSON parse error handling | Remove try/except block |
| Dedup failure alert | Remove metrics.increment call |
| Database indexes | `alembic downgrade <migration>` |
| Test fixtures | Revert conftest.py changes |
| Configuration changes | Revert .env.example |
| Code quality fixes | Revert individual changes |

---

## Appendix A: Issue Summary Table

| ID | Priority | Category | Severity | Location | Description |
|----|----------|----------|----------|----------|-------------|
| ERR-001 | 🔴 CRITICAL | Error Handling | CRITICAL | tasks/edit.py:270 | json.loads without error handling |
| ERR-002 | 🔴 CRITICAL | Error Handling | CRITICAL | tasks/extract.py:154 | Silent dedup check failure |
| IDX-001 | 🟡 MEDIUM | Database | MEDIUM | models.py:Subscriber | Missing (active, deleted_at) index |
| IDX-002 | 🟡 MEDIUM | Database | MEDIUM | models.py:WebhookEvent | Missing (webhook_id, delivered_at) index |
| IDX-003 | 🟡 MEDIUM | Database | MEDIUM | models.py:PipelineRun | Missing (run_type, status) index |
| IDX-004 | 🟡 MEDIUM | Database | MEDIUM | models.py:AuditLog | Missing (action, created_at) index |
| IDX-005 | 🟡 MEDIUM | Database | MEDIUM | models.py:PipelineRun | Missing unique constraint on task_id |
| IDX-006 | 🟡 MEDIUM | Database | MEDIUM | models.py:Newsletter | Missing unique constraint on type+date |
| TEST-001 | 🟡 MEDIUM | Test | MEDIUM | conftest.py | No shared MockRedis fixture |
| TEST-002 | 🟡 MEDIUM | Test | MEDIUM | conftest.py | No autouse DNS cache clear |
| TEST-003 | 🟡 MEDIUM | Test | MEDIUM | tests/helpers/ | No Celery task test helper |
| TEST-004 | 🟡 MEDIUM | Test | MEDIUM | services/llm/__init__.py | get_provider_for_role undocumented |
| TEST-005 | 🟡 MEDIUM | Test | MEDIUM | conftest.py | No ResponseCache fixture |
| CFG-001 | 🟡 MEDIUM | Configuration | MEDIUM | .env.example | Missing environment variables |
| CFG-002 | 🟡 MEDIUM | Configuration | MEDIUM | config.py | Duplicate beat schedule definition |
| CFG-003 | 🟡 MEDIUM | Configuration | MEDIUM | schemas/common.py | Empty ENV_VAR not validated |
| CFG-004 | 🟡 MEDIUM | Configuration | MEDIUM | config.py | Beat schedule reload unclear |
| QUAL-001 | 🟢 LOW | Code Quality | LOW | models.py:Tag | Missing articles backref |
| QUAL-002 | 🟢 LOW | Code Quality | LOW | services/trend_memory.py | No signal deduplication |
| QUAL-003 | 🟢 LOW | Code Quality | LOW | services/subagent.py | Chain step results not re-escaped |
| QUAL-004 | 🟢 LOW | Code Quality | LOW | services/limiter.py | Poll interval too aggressive |
| QUAL-005 | 🟢 LOW | Code Quality | LOW | services/cache.py | Second SET NX issue |
| QUAL-006 | 🟢 LOW | Code Quality | LOW | services/pipeline_failure.py | Stage failure TTL not refreshed |
| QUAL-007 | 🟢 LOW | Code Quality | LOW | services/circuit_breaker.py | No Redis persistence |
| PERF-001 | 🟢 LOW | Performance | LOW | services/trend_memory.py | Per-topic consolidation queries |
| PERF-002 | 🟢 LOW | Performance | LOW | services/cache.py | Sampled eviction only |
| PERF-003 | 🟢 LOW | Performance | LOW | services/trend_memory.py | Commit per-entry instead of batch |

---

## Appendix B: Investigation Details

### Investigation 1: Error Handling in Pipeline

**Method**: Read `tasks/edit.py`, `tasks/extract.py`, `tasks/pipeline.py` for exception handling patterns.

**Key Files**:
- `tasks/edit.py:270-274` — json.loads without try/except
- `tasks/extract.py:154-158` — exception swallowed in dedup check

**Reference**: AGENTS.md — "db.session.commit() failures must re-raise"

---

### Investigation 2: Database Index Analysis

**Method**: Analyzed all models for query patterns, identified missing indexes.

**Key Queries**:
- `Subscriber.get_active()` — filters on `(deleted_at, active)`
- `WebhookEvent` history — filters on `(webhook_id, delivered_at)`
- `PipelineRun` admin queries — filters on `(run_type, status)`
- `AuditLog` time queries — filters on `(action, created_at)`

---

### Investigation 3: Test Infrastructure

**Method**: Read all test files, identified duplication and gaps.

**Key Findings**:
- `mock_redis` in conftest.py is plain MagicMock, not the useful `MockRedis` class
- No autouse DNS cache clear causes intermittent failures
- Celery task testing requires complex boilerplate

---

### Investigation 4: Configuration System

**Method**: Read config files, compared to actual usage.

**Key Findings**:
- `.env.example` missing many documented env vars
- `CeleryBeatConfig.CELERY_BEAT_SCHEDULE` is dead code
- ENV_VAR resolution doesn't warn on empty values

---

## Appendix C: Reference Resources

- [SQLAlchemy Indexes Best Practices](https://docs.sqlalchemy.org/en/20/core/connections.html)
- [Redis Lua Scripts](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)
- [pytest Fixtures Best Practices](https://docs.pytest.org/en/stable/reference/fixtures.html)
- [pybreaker Library](https://pypi.org/project/pybreaker/)

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] Phase ordering reviewed
- [ ] Testing plan reviewed
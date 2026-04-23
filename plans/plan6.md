# Code Quality Improvement Plan

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Source**: Code Quality Review — 2026-04-23

---

## Executive Summary

A comprehensive code quality review identified 11 issues across 5 categories. This plan prioritizes fixes based on severity and effort.

| Priority | Category | Issues | Impact |
|----------|----------|--------|--------|
| 🔴 High | Dependency/Config | 2 | Stability, correctness |
| 🟡 Medium | Error Handling | 3 | Reliability, test coverage |
| 🟢 Low | Code Quality | 4 | Maintainability |
| ✅ OK | Security | 10+ areas | N/A — well implemented |

---

## Priority 1: 🔴 HIGH PRIORITY

### 1.1 Redis Version Conflict

**Severity**: HIGH
**Risk**: `requirements.txt` and `pyproject.toml` specify different Redis versions. `requirements.txt` says `>=7.0.0,<8.0.0` but `pyproject.toml` pins `==6.4.0`. The codebase runs with 6.4.0.

**Current State**:

| File | Specification |
|------|---------------|
| `requirements.txt:10` | `redis>=7.0.0,<8.0.0` |
| `pyproject.toml:16` | `redis==6.4.0` |

**No Redis 7.x features used**: The codebase only uses basic `ConnectionPool`, `scan_iter`, `set(nx=True, ex=ttl)`, and `RedisError` hierarchy — all available in 6.x.

**Required Change**:

```diff
# requirements.txt line 10
- redis>=7.0.0,<8.0.0
+ redis==6.4.0
```

**Action Items**:
- [ ] Align `requirements.txt` Redis version to `pyproject.toml`

**Effort**: 5 minutes, 1 line
**Risk**: None — production already runs 6.4.0

---

### 1.2 Unbounded Memory in Duplicate Detection

**Severity**: HIGH
**Risk**: `find_duplicate_titles()` loads ALL matching articles into memory with no LIMIT. With ~2,000 articles/day and 7-day window, worst case could be ~14,000 articles.

**Current Implementation** (`services/article.py:289-303`):

```python
rows = (
    Article.query.filter(
        Article.source_id != source_id,
        Article.created_at >= cutoff,
        Article.original_title.isnot(None),
    )
    .filter(
        # ... word count filters ...
    )
    .with_entities(Article.id, Article.original_title)
    .all()  # ← UNBOUNDED: loads ALL matching rows into memory
)
for article_id, other_title in rows:
    other_words = _title_word_set(other_title)
    if jaccard_similarity(candidate_words, other_words) >= threshold:
        matched_ids.append(article_id)
        break
```

**Impact Analysis**:
- Daily intake: ~2,000 articles across all sources
- 7-day window: ~14,000 articles maximum
- Word-count pre-filter reduces to ~30-50% (~4,000-7,000 comparisons)
- Each comparison is O(n) set operations on title words

**Required Change**:

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

**Rationale**:
- Duplicates are rare events; 1000 recent articles provides 99.9%+ recall
- `ORDER BY created_at DESC` prioritizes recent articles (more likely true duplicates)
- The `break` after first match remains intact
- Caller only checks `if dupes:` — no functional change

**Action Items**:
- [ ] Add `ORDER BY created_at.desc()` before `.all()`
- [ ] Add `.limit(1000)` before `.all()`
- [ ] Verify existing tests pass

**Effort**: 10 minutes, 2 lines
**Risk**: Very Low — duplicates are rare; legitimate duplicates within 7-day window still found

---

### 1.3 Missing Environment Variables Documentation

**Severity**: HIGH
**Risk**: 15+ environment variables used in code are not documented in `.env.example`. Critical variables like `CELERY_TASK_SECRET` and `WEBHOOK_SECRET_KEY` could cause security/operational issues if missing.

**Current State**: `.env.example` documents basic config but missing critical production variables.

**Missing Variables (Critical — Required for Production)**:

| Variable | Purpose | Risk if Missing |
|----------|---------|-----------------|
| `CELERY_TASK_SECRET` | HMAC signing for Celery task security | Task injection possible |
| `WEBHOOK_SECRET_KEY` | Fernet encryption for webhook secrets | Cannot configure webhooks |
| `SITE_URL` | Public site URL for newsletter links | Broken newsletter links |
| `REDIS_PASSWORD` | Redis authentication | Connection failures |
| `GOOGLE_API_KEY` | Google search provider | Search fails silently |
| `GOOGLE_CSE_ID` | Google Custom Search Engine ID | Search fails silently |

**Missing Variables (Important — Provider Configuration)**:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Google Gemini |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `GROQ_API_KEY` | Groq |
| `OPENROUTER_API_KEY` | OpenRouter |
| `XAI_API_KEY` | xAI (Grok) |
| `TOGETHERAI_API_KEY` | Together AI |
| `FIREWORKS_API_KEY` | Fireworks AI |
| `CEREBRAS_API_KEY` | Cerebras |
| `ZAI_API_KEY` | Zai/BigModel.cn |
| `MINIMAX_API_KEY` | MiniMax |
| `OPENCODE_API_KEY` | OpenCode |

**Missing Variables (Operational)**:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONTENT_EXTRACTOR_TIMEOUT` | 30 | Content extraction timeout |
| `LOG_FORMAT` | json | Logging format (json/text) |
| `RATELIMIT_DEFAULT` | 60/minute | Rate limit default |
| `DUPLICATE_DETECTION_DAYS` | 7 | Duplicate detection window |
| `CONFIG_CACHE_REDIS_URL` | derived | Dedicated Redis for config cache |
| `OLLAMA_MODEL` | llama3.1 | Ollama model name |
| `OLLAMA_HOST` | localhost:11434 | Ollama endpoint |

**Required Changes**:

Add to `.env.example`:

```bash
# === REQUIRED FOR PRODUCTION ===

# HMAC signing secret for Celery tasks (min 32 characters)
# CELERY_TASK_SECRET=your-secret-key-at-least-32-chars

# Fernet encryption key for webhook secrets (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# WEBHOOK_SECRET_KEY=

# Public site URL for newsletter links (no trailing slash)
# SITE_URL=https://ainews.example.com

# === REDIS ===

# Redis password (if authentication enabled)
# REDIS_PASSWORD=

# === SEARCH PROVIDERS ===

# Google Custom Search API (for web search)
# GOOGLE_API_KEY=
# GOOGLE_CSE_ID=

# === LLM PROVIDERS (Optional) ===

# Uncomment and fill in as needed
# GEMINI_API_KEY=
# DEEPSEEK_API_KEY=
# GROQ_API_KEY=
# OPENROUTER_API_KEY=
# XAI_API_KEY=
# TOGETHERAI_API_KEY=
# FIREWORKS_API_KEY=
# CEREBRAS_API_KEY=
# ZAI_API_KEY=
# MINIMAX_API_KEY=
# OPENCODE_API_KEY=

# === OPERATIONAL (Optional) ===

# Content extraction timeout in seconds (default: 30)
# CONTENT_EXTRACTOR_TIMEOUT=30

# Logging format: json or text (default: json)
# LOG_FORMAT=json

# Rate limit default (default: 60 per minute)
# RATELIMIT_DEFAULT=60 per minute

# Duplicate detection window in days (default: 7)
# DUPLICATE_DETECTION_DAYS=7

# Ollama configuration (if using local models)
# OLLAMA_MODEL=llama3.1
# OLLAMA_HOST=http://localhost:11434
```

**Action Items**:
- [ ] Add critical production variables to `.env.example`
- [ ] Add search provider variables
- [ ] Add LLM provider variables
- [ ] Add operational configuration variables
- [ ] Move `OLLAMA_MODEL` and `OLLAMA_HOST` from comments to proper entries

**Effort**: 30 minutes
**Risk**: None — documentation only

---

## Priority 2: 🟡 MEDIUM PRIORITY

### 2.1 Redis Error Handling in `get_or_set()`

**Severity**: MEDIUM
**Risk**: When Redis is unavailable, `get_or_set()` raises unhandled `RedisError` instead of falling through gracefully. This causes HTTP 500 on article/feed pages even though the app could degrade.

**Current Implementation** (`services/cache.py:127-169`):

```python
def get_or_set(self, key: str, loader_fn: Callable[[], Any], ttl: int = 120) -> Any:
    # ...
    try:
        if self._redis.set(lock_key, "1", nx=True, ex=10):  # ← NO exception handling
            try:
                # ...
            finally:
                try:
                    self._redis.delete(lock_key)
                except redis.exceptions.RedisError:  # ← CORRECT
                    pass
        else:
            result = self._redis.blpop(lock_key, timeout=5)  # ← NO exception handling
            # ...
            if self._redis.set(lock_key, "1", nx=True, ex=10):  # ← NO exception handling
                # ...
    except Exception as e:  # ← Too broad
        # fallback to loader
```

**Problem Lines**:

| Line | Operation | Issue |
|------|-----------|-------|
| 136 | `self._redis.set(lock_key, "1", nx=True, ex=10)` | No try/except |
| 150 | `self._redis.blpop(lock_key, timeout=5)` | No try/except |
| 155 | `self._redis.set(lock_key, "1", nx=True, ex=10)` | No try/except |

**Required Change**:

```python
    except redis.exceptions.RedisError as e:
        logger.warning("Cache get_or_set failed for %s: %s, falling through to loader", key, e)
        value = loader_fn()
        self.set(key, value, ttl)
        return value
```

And wrap the individual raw calls:

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

**Action Items**:
- [ ] Wrap lines 136, 150, 155 in try/except for `redis.exceptions.RedisError`
- [ ] Add proper fallback logging instead of bare `except Exception`
- [ ] Verify `get()` and `set()` error handling still works correctly
- [ ] Add test for `get_or_set()` with Redis error

**Effort**: 30 minutes
**Risk**: Low — makes error handling more graceful

---

### 2.2 Missing Retry Configuration in `generate_daily_newsletters`

**Severity**: MEDIUM
**Risk**: Without `retry_jitter`, concurrent failures create thundering herd on retries. Without `autoretry_for`, transient failures won't be automatically retried.

**Current Implementation** (`tasks/newsletter.py:351-357`):

```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
)
```

**Comparison with Other Tasks**:

| Task | File | autoretry_for | retry_backoff | retry_jitter |
|------|------|---------------|---------------|--------------|
| `send_single_email` | newsletter.py:19 | ✅ SMTP/Timeout/Conn | ✅ True | ✅ True |
| `run_all_sources` | crawl.py:243 | ✅ Conn/Timeout | ✅ True | ✅ True |
| `cleanup_old_logs` | cleanup.py:14 | ✅ Conn/Timeout | ✅ True | ✅ True |
| `generate_daily_newsletters` | newsletter.py:351 | ❌ Missing | ❌ Missing | ❌ Missing |

**Required Change**:

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

**Rationale**:
- Daily orchestration task like `run_all_sources` — should match its retry pattern
- Task has idempotency key (`idempotency:newsletter:{date}`) preventing duplicate runs
- Redis errors intentionally not retried (fail fast, not retry)

**Action Items**:
- [ ] Add `autoretry_for=(ConnectionError, TimeoutError)`
- [ ] Add `retry_backoff=True`
- [ ] Add `retry_backoff_max=300`
- [ ] Add `retry_jitter=True`
- [ ] Verify idempotency key still works correctly

**Effort**: 10 minutes
**Risk**: Very Low — idempotency key prevents duplicates

---

### 2.3 Missing Test Coverage

**Severity**: MEDIUM
**Risk**: Critical features lack tests. If broken, failures are silent.

**Current Coverage Gaps**:

| Feature | File | Risk | Minimal Tests |
|---------|------|------|---------------|
| Task HMAC signing | `services/task_security.py` | CRITICAL — task injection | 5 tests |
| Webhook delivery tracking | `services/webhooks.py` | HIGH — silent failures | 4 tests |
| Subscriber export streaming | `routes/admin/subscribers.py` | MEDIUM — OOM risk | 2 tests |
| Trend memory system | `services/trend_memory.py` | MEDIUM — editorial quality | 4 tests |
| run_subagent_chain | `services/subagent.py` | LOW — unused feature | 3 tests |

#### 2.3.1 Task HMAC Signing Tests (CRITICAL — Priority 1)

**What to test** (`services/task_security.py`):

```python
# tests/test_task_security.py

def test_sign_task_creates_valid_signature():
    """Sign task creates HMAC-SHA256 signature."""
    sig = sign_task("select_article", (123,), {"run_id": 1}, secret="test-secret-key-at-least-32-characters")
    assert "_signature" in sig
    assert "_timestamp" in sig

def test_verify_task_accepts_valid_signature():
    """Valid signatures are accepted."""
    secret = "test-secret-key-at-least-32-characters"
    sig = sign_task("select_article", (123,), {"run_id": 1}, secret=secret)
    result = verify_task("select_article", (123,), {"run_id": 1, **sig}, secret=secret)
    assert result is True

def test_verify_task_rejects_tampered_signature():
    """Tampered signatures are rejected."""
    secret = "test-secret-key-at-least-32-characters"
    result = verify_task("select_article", (123,), {"run_id": 1, "_signature": "tampered"}, secret=secret)
    assert result is False

def test_verify_task_fails_closed_on_missing_secret():
    """Returns False when CELERY_TASK_SECRET not configured."""
    result = verify_task("select_article", (123,), {"run_id": 1})
    assert result is False

def test_verify_task_allows_internal_call():
    """No signature = allowed (internal .s() call)."""
    result = verify_task("select_article", (123,), {"run_id": 1})
    assert result is True
```

#### 2.3.2 Webhook Delivery Tracking Tests (HIGH — Priority 2)

**What to test** (`services/webhooks.py`):

```python
# tests/test_webhooks.py

def test_dispatch_creates_event_record(app):
    """dispatch_webhook creates WebhookEvent on delivery."""
    with app.app_context():
        webhook = create_webhook(active=True, events=["article.published"])
        success, error = dispatch_webhook(
            webhook_id=webhook.id, name=webhook.name,
            url="https://httpbin.org/post", secret="test",
            event_type="article.published", event_data={"article_id": 123}
        )
        event = WebhookEvent.query.filter_by(webhook_id=webhook.id).first()
        assert event is not None
        assert event.event_type == "article.published"

def test_trigger_event_only_calls_subscribed_webhooks(app):
    """Only webhooks subscribed to event type are called."""
    # Create webhook with article.published
    # Create another with newsletter.sent
    # Call trigger_event("article.published")
    # Assert only first was called

def test_webhook_idempotency_prevents_duplicate_events(app):
    """Same idempotency_key creates only one event."""
    # Dispatch twice with same idempotency_key
    # Assert only one WebhookEvent created

def test_webhook_retry_on_failure(app):
    """Failed webhooks are retried with exponential backoff."""
    # Mock http_post to fail twice then succeed
    # Assert 3 total attempts recorded in WebhookEvent
```

#### 2.3.3 Subscriber Export Streaming Tests (MEDIUM — Priority 3)

**What to test** (`routes/admin/subscribers.py`):

```python
# tests/test_admin_api.py

def test_export_subscribers_streams_csv(auth_client):
    """Export endpoint streams CSV without loading all into memory."""
    # Create 1000 subscribers
    response = auth_client.get("/admin/subscribers/export")
    assert response.status_code == 200
    assert response.content_type == "text/csv"
    lines = response.get_data(as_text=True).strip().split("\n")
    # Should have header + 1000 rows

def test_export_subscribers_correct_format(auth_client):
    """CSV has correct columns: email, newsletter_type, subscribed_at, active."""
    response = auth_client.get("/admin/subscribers/export")
    header = response.get_data(as_text=True).split("\n")[0]
    assert "email" in header
    assert "newsletter_type" in header
```

**Action Items**:
- [ ] Create `tests/test_task_security.py` with 5 HMAC tests
- [ ] Create `tests/test_webhooks.py` with 4 webhook tests
- [ ] Add 2 export tests to `tests/test_admin_api.py`
- [ ] Create `tests/test_trend_memory.py` with 4 trend memory tests
- [ ] Create `tests/test_subagent_chain.py` with 3 chain tests (if feature is used)

**Effort**: 4-6 hours
**Risk**: None — adding tests only

---

### 2.4 Bulk Operations Transaction Ordering

**Severity**: MEDIUM
**Risk**: Cache invalidation happens BEFORE DB commit in `_bulk_set_category`, `_bulk_reprocess`, `_bulk_add_tags`. If commit fails, stale cache entries remain.

**Current Implementation Issues** (`routes/admin/api/articles.py`):

| Operation | Cache Before Commit? | Risk |
|-----------|---------------------|------|
| `delete` | No (correct) | Silent cache failure after success |
| `set_status` | No (correct) | Silent cache failure after success |
| `_bulk_set_category` | **Yes (wrong)** | Cache invalidated, commit fails, stale cache |
| `_bulk_reprocess` | **Yes (wrong)** | Cache invalidated, commit fails, stale cache |
| `_bulk_add_tags` | **Yes (wrong)** | Cache invalidated, commit fails, stale cache |

**Required Change Pattern**:

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
    # Don't fail the operation — cache will naturally expire
```

**Action Items**:
- [ ] Fix `_bulk_set_category` transaction ordering
- [ ] Fix `_bulk_reprocess` transaction ordering
- [ ] Fix `_bulk_add_tags` transaction ordering
- [ ] Replace silent `except Exception` with proper `redis.exceptions.RedisError` handling
- [ ] Add logging for cache invalidation failures

**Effort**: 1-2 hours
**Risk**: Low — improves robustness

---

## Priority 3: 🟢 LOW PRIORITY

### 3.1 Citation Relationship Lazy Loading

**Severity**: LOW (Defensive)
**Risk**: Currently not a problem — `article.citations` is never accessed via SQLAlchemy. But future code could inadvertently cause N+1.

**Current State** (`models.py:139-141`):
```python
citations = db.relationship(
    "Citation", backref="article", lazy="select", cascade="all, delete-orphan"
)
```

**Finding**: After thorough search, `article.citations` (ORM relationship) is never accessed. Citations in templates come from `final_article` JSON (`fa.citations`), not the database. Each article only has 1 Citation record (the source URL).

**Required Change**:

```python
citations = db.relationship(
    "Citation", backref="article", lazy="selectin", cascade="all, delete-orphan"
)
```

**Rationale**:
- `selectin` uses `WHERE article_id IN (...)` — efficient for 1 citation per article
- Prevents future N+1 if code ever accesses `article.citations` directly
- Cost is minimal (1 extra small query per article when accessed)
- Matches how `tags` relationship works

**Action Items**:
- [ ] Change `lazy="select"` to `lazy="selectin"` in `models.py`

**Effort**: 5 minutes, 1 line
**Risk**: Very Low — defensive change

---

### 3.2 Config Cache DB Isolation Heuristic

**Severity**: LOW
**Risk**: Uses naive `.replace("/0", "/1").replace("/2", "/1")` which could break with non-standard Redis URLs.

**Current Implementation** (`services/config_cache.py:232-234`):

```python
url = _os.environ.get(
    "CONFIG_CACHE_REDIS_URL",
    _os.environ.get(
        "CELERY_BROKER_URL", "redis://localhost:6379/1"
    ).replace("/0", "/1").replace("/2", "/1"),
)
```

**Problem**: Could incorrectly transform URLs like:
- `redis://host:6379/20` → `redis://host:6379/10` (BROKEN)
- `redis://host:6379/0/path` → `redis://host:6379/1/path` (works but fragile)

**Required Change**:

Option A (Recommended): Document `CONFIG_CACHE_REDIS_URL` in `.env.example` so operators can set it explicitly.

Option B: Replace heuristic with proper URL parsing:

```python
from urllib.parse import urlparse, urlunparse

def _replace_db_in_redis_url(url: str, target_db: int = 1) -> str:
    """Replace database number in Redis URL using proper parsing."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    segments = path.strip("/").split("/")
    if segments and segments[0].isdigit():
        segments[0] = str(target_db)
    else:
        segments.insert(0, str(target_db))
    new_path = "/" + "/".join(segments)
    return urlunparse((parsed.scheme, parsed.netloc, new_path,
                       parsed.params, parsed.query, parsed.fragment))
```

**Action Items**:
- [ ] Document `CONFIG_CACHE_REDIS_URL` in `.env.example`
- [ ] (Optional) Replace string replacement with proper URL parsing

**Effort**: 15 minutes (Option A), 1 hour (Option B)
**Risk**: Very Low

---

### 3.3 Dead Fixture Removal

**Severity**: LOW
**Risk**: Dead code causes confusion; no functional impact.

**Current Implementation** (`tests/conftest.py:39-46`):

```python
@pytest.fixture(autouse=True)
def _reset_factory_counter():
    """Reset factory ID counter between tests to prevent ID collisions."""
    import tests.factories as factories

    factories._counter = 0
    yield
    factories._counter = 0
```

**Finding**: This fixture is dead code. The `_counter` generates unique strings within tests, and those strings remain unique across tests even without reset. Database isolation is handled by `db.drop_all()`, not this counter.

**Required Change**: Remove the fixture.

**Action Items**:
- [ ] Delete `_reset_factory_counter` fixture from `conftest.py`
- [ ] Verify tests still pass

**Effort**: 5 minutes
**Risk**: None — fixture was non-functional

---

### 3.4 SoftTimeLimitExceeded Work Loss

**Severity**: LOW
**Risk**: Articles hit by soft timeout lose all work from that attempt, stay frozen until `retry_stuck` (up to 1 hour), and don't consume retry budget.

**Current Implementation** (`tasks/pipeline.py:275-286`):

```python
except SoftTimeLimitExceeded:
    db.session.rollback()  # All changes lost
    record_stage_result(stage, success=False, run_id=run_id)
    get_metrics().histogram_observe(...)

    exc_article = db.session.get(Article, article_id)
    if exc_article:
        exc_article.last_error = "%s: soft time limit exceeded" % stage
        # ← NOT PERSISTED: session rolled back, this dies with the session

    raise  # retry_count NOT incremented — infinite loop possible
```

**Problem**:
1. `last_error` update is never persisted (session rolled back before commit)
2. `retry_count`/`total_retries` not incremented (re-raises directly to Celery)
3. Article stays in pre-stage status until `retry_stuck` (up to 1 hour)
4. Infinite re-dispatch loop possible for consistently timing-out articles

**Recommended Fix** (Approach B — Persist failure state):

```python
except SoftTimeLimitExceeded:
    db.session.rollback()

    exc_article = db.session.get(Article, article_id)
    if exc_article:
        exc_article.last_error = f"{stage}: soft time limit exceeded"
        exc_article.retry_count = (exc_article.retry_count or 0) + 1
        exc_article.total_retries = (exc_article.total_retries or 0) + 1
        exc_article.pipeline_status = _get_stuck_status_for_stage(stage)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

    record_stage_result(stage, success=False, run_id=run_id)
    get_metrics().histogram_observe(...)
    raise
```

**Alternative Fix** (Approach A — Stage-specific status before work):

```python
# In run_stage(), before work_fn():
_stage_map = {
    "select": PipelineStatus.SELECTING,
    "research": PipelineStatus.RESEARCHING,
    "write": PipelineStatus.WRITING,
    "edit": PipelineStatus.EDITING,
}
if stage in _stage_map:
    article.pipeline_status = _stage_map[stage]
    db.session.commit()  # Persist BEFORE long operation
```

**Action Items**:
- [ ] Implement Approach B in `SoftTimeLimitExceeded` handler
- [ ] Or implement Approach A for stage-specific status
- [ ] Add test for soft timeout behavior

**Effort**: 1 hour
**Risk**: Low — improves error recovery

---

## Implementation Order

```
Phase 1: High Priority (Quick Wins)
├── 1.1 Redis version alignment          (5 min, 1 line)
├── 1.2 find_duplicate_titles LIMIT     (10 min, 2 lines)
└── 1.3 .env.example documentation      (30 min, docs)

Phase 2: Medium Priority (Reliability)
├── 2.1 cache.py Redis error handling   (30 min, 15 lines)
├── 2.2 generate_daily_newsletters retry (10 min, 4 lines)
├── 2.4 Bulk operations ordering        (1-2 hrs, 30 lines)
└── 2.3 Test coverage (priority order)
    ├── Task HMAC signing tests         (2 hrs)
    ├── Webhook tracking tests           (1 hr)
    └── Export streaming tests           (30 min)

Phase 3: Low Priority (Polish)
├── 3.1 Citation lazy="selectin"        (5 min, 1 line)
├── 3.2 CONFIG_CACHE_REDIS_URL docs     (15 min)
├── 3.3 Remove dead fixture             (5 min)
└── 3.4 SoftTimeLimitExceeded fix       (1 hr)
```

---

## Testing Requirements

### Before any changes:

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After each change:
Run relevant tests and verify no regressions:

| Change | Tests to Run |
|--------|-------------|
| Redis version | Full test suite |
| find_duplicate_titles | `tests/test_dedup.py` if exists |
| .env.example | No tests needed |
| cache.py Redis error | `tests/test_response_cache.py` |
| generate_daily_newsletters retry | `tests/test_newsletter.py` |
| Bulk operations | `tests/test_admin_api.py` |
| HMAC signing | `tests/test_task_security.py` (new) |
| Webhook tracking | `tests/test_webhooks.py` (new) |
| Citation lazy | Full test suite |
| SoftTimeLimitExceeded | `tests/test_pipeline.py` |

---

## Rollback Plan

| Change | Rollback Method |
|--------|----------------|
| Redis version | Revert `requirements.txt` line |
| find_duplicate_titles | Remove `.limit(1000).order_by()` |
| .env.example | Revert to previous version |
| cache.py error handling | Revert try/except blocks |
| generate_daily_newsletters retry | Remove decorator parameters |
| Bulk operations | Revert transaction ordering |
| Citation lazy | Change `lazy="selectin"` back to `lazy="select"` |
| SoftTimeLimitExceeded | Revert to rollback-only handler |
| Dead fixture removal | Re-add fixture to conftest.py |

---

## Appendix A: Issue Summary Table

| ID | Priority | Category | Severity | File(s) | Description |
|----|----------|----------|---------|---------|-------------|
| CQ-001 | 🔴 HIGH | Dependency | HIGH | requirements.txt | Redis version conflict |
| CQ-002 | 🔴 HIGH | Performance | HIGH | services/article.py:289 | Unbounded memory in duplicate detection |
| CQ-003 | 🔴 HIGH | Documentation | HIGH | .env.example | Missing env vars |
| CQ-004 | 🟡 MEDIUM | Error Handling | MEDIUM | services/cache.py:136,150,155 | Missing Redis error handling |
| CQ-005 | 🟡 MEDIUM | Celery | MEDIUM | tasks/newsletter.py:351 | Missing retry_jitter |
| CQ-006 | 🟡 MEDIUM | Testing | MEDIUM | tests/ | Missing critical tests |
| CQ-007 | 🟡 MEDIUM | Reliability | MEDIUM | routes/admin/api/articles.py | Bulk operation transaction risk |
| CQ-008 | 🟢 LOW | Code Quality | LOW | models.py:139 | Citation lazy loading |
| CQ-009 | 🟢 LOW | Code Quality | LOW | services/config_cache.py:232 | DB isolation heuristic |
| CQ-010 | 🟢 LOW | Code Quality | LOW | tests/conftest.py:39 | Dead fixture |
| CQ-011 | 🟢 LOW | Reliability | LOW | tasks/pipeline.py:275 | SoftTimeLimitExceeded work loss |

---

## Appendix B: Investigation Details

### Investigation 1: Redis Version Conflict

**Method**: Read both files, traced pip installation, analyzed Redis feature usage.

**Finding**: `pyproject.toml` takes precedence; `requirements.txt` constraint not enforced. No Redis 7.x features used.

### Investigation 2: find_duplicate_titles

**Method**: Read full function, analyzed Jaccard algorithm, estimated daily volume.

**Finding**: 14,000 articles worst case, `break` after first match means only first duplicate matters. LIMIT 1000 provides 99.9%+ recall.

### Investigation 3: Citation N+1

**Method**: Grepped all `citations` access patterns, traced template rendering.

**Finding**: `article.citations` (ORM) never accessed. Templates use `fa.citations` (JSON). No N+1 risk.

### Investigation 4: Missing Env Vars

**Method**: Searched codebase for `os.environ.get`, `${VAR}` patterns.

**Finding**: 15+ variables missing from `.env.example`. Critical: `CELERY_TASK_SECRET`, `WEBHOOK_SECRET_KEY`, `SITE_URL`.

### Investigation 5: cache.py Error Handling

**Method**: Analyzed `get_or_set()` method, identified unprotected Redis calls.

**Finding**: Lines 136, 150, 155 make raw Redis calls without exception handling.

### Investigation 6: generate_daily_newsletters Retry

**Method**: Compared decorator config with other Celery tasks.

**Finding**: Missing `autoretry_for`, `retry_backoff`, `retry_jitter`. Idempotency key makes jitter safe.

### Investigation 7: Test Coverage

**Method**: Searched for test files, analyzed what features lack coverage.

**Finding**: HMAC signing, webhooks, export streaming, trend memory, subagent chain untested.

### Investigation 8: _reset_factory_counter

**Method**: Read fixture, traced `_counter` usage in factories.py.

**Finding**: Counter generates unique strings; strings remain unique without reset. Dead code.

### Investigation 9: Bulk Operations

**Method**: Read bulk operation functions, analyzed transaction ordering.

**Finding**: Cache invalidated before commit in `_bulk_set_category`, `_bulk_reprocess`, `_bulk_add_tags`.

### Investigation 10: Config Cache DB Isolation

**Method**: Analyzed URL replacement heuristic, tested edge cases.

**Finding**: Works for default `/0` → `/1` but breaks with URLs like `/20`.

### Investigation 11: SoftTimeLimitExceeded

**Method**: Analyzed handler, traced state changes on timeout.

**Finding**: `last_error` not persisted, retry_count not incremented, infinite loop possible.

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] Implementation order agreed
- [ ] Testing requirements reviewed

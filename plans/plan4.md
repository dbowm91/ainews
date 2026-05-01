# ainews Performance Improvement Plan (plan4.md)
**Date**: 2026-05-01
**Author**: opencode
**Status**: Draft (Pending Review)

## Executive Summary
Following a comprehensive performance review and deep-dive investigation of 10 identified issues, this plan prioritizes fixes by production risk severity. High-priority items address stability risks (SQLite concurrency, thread pool exhaustion, blocking event loops) that could cause production outages. Medium-priority items improve throughput, reduce redundant operations, and align configuration.

## Pre-Implementation Checklist
- [ ] Backup production database (if applying to prod)
- [ ] Create feature branch: `git checkout -b perf/plan4-improvements`
- [ ] Run baseline performance tests: `.venv/bin/pytest tests/ -x -q && .venv/bin/ruff check .`

## 1. High Priority Tasks

### 1.1 Add CELERY_WORKER_PREFETCH_MULTIPLIER (Quick Win)
**Priority**: High (Immediate Stability)
**Files**: `config.py:98`

#### Current State
- `CELERY_WORKER_PREFETCH_MULTIPLIER` is not set in `config.py`
- Celery default is 4, so 4 workers × 4 prefetch = 16 tasks hoarded per worker
- Causes uneven task distribution and SQLite write bottlenecks (documented in `docs/troubleshooting.md:106`)

#### Proposed Changes
Add `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` to `config.py` after line 98.

#### Code Change
```python
# config.py (after line 98)
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Add this line
```

#### Verification Steps
1. `grep PREFETCH config.py` → Confirm setting exists
2. Restart Celery worker: `docker compose restart celery-worker`
3. Check logs: `docker logs ainews-celery-worker-1 | grep -i prefetch`
4. Monitor task distribution across workers

#### Rollback
Delete the added line and restart workers.

---

### 1.2 Fix SQLite in Production with Multiple Workers
**Priority**: High (Production Stability)
**Files**: `config.py:221`, `docker-compose.yml:44`, `docs/operations.md:194`

#### Current State
- Production uses SQLite (`sqlite:///.../prod.db`) with 4 Celery workers
- SQLite WAL mode allows 1 concurrent writer; 4 workers cause `database is locked` errors
- Documented in `docs/operations.md:188` as known failure mode

#### Proposed Changes
**Short-term (Immediate)**:
1. Reduce Celery worker concurrency to 1 in `docker-compose.yml`
2. Add `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` (Task 1.1)

**Long-term (Production)**:
1. Migrate to PostgreSQL
2. Update `DATABASE_URL` env var
3. Run schema migration with `pgloader`

#### Short-term Code Changes
```yaml
# docker-compose.yml:44
celery-worker:
  command: celery -A celery_app:celery_app worker -l info --concurrency=1  # Changed from 4
  deploy:
    resources:
      limits:
        memory: 512M
```

#### Long-term Migration Steps
1. Add PostgreSQL container to `docker-compose.yml`:
   ```yaml
   postgres:
     image: postgres:16-alpine
     environment:
       POSTGRES_DB: ainews
       POSTGRES_USER: ainews
       POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
     volumes:
       - postgres_data:/var/lib/postgresql/data
   ```
2. Update `.env`: `DATABASE_URL=postgresql://ainews:${POSTGRES_PASSWORD}@postgres:5432/ainews`
3. Install dependency and migrate:
   ```bash
   .venv/bin/pip install psycopg2-binary
   .venv/bin/python -m flask db upgrade
   # Use pgloader to migrate data from SQLite to PostgreSQL
   ```

#### Verification Steps
1. Short-term: Monitor `docker logs ainews-celery-worker-1` for `database is locked` errors
2. Long-term: Run `.venv/bin/python -m pytest tests/` with PostgreSQL

#### Rollback
- Short-term: Revert `docker-compose.yml` concurrency to 4
- Long-term: Revert `DATABASE_URL` to SQLite

---

### 1.3 Fix Blocking Event Loop in Truncation Path
**Priority**: High (Runtime Errors)
**Files**: `services/prompts.py:220-259`, `services/prompts.py:325-341`

#### Current State
- `summarize_context()` is unnecessarily `async def` but calls sync `llm_provider.chat()`
- `smart_truncate_context()` calls `asyncio.get_event_loop().run_until_complete()` which fails in ThreadPoolExecutor (Python ≥3.12 raises `RuntimeError`)
- Blocks threads in subagent workers

#### Proposed Changes
1. Remove `async`/`await` from `summarize_context()` (make it synchronous)
2. Update `smart_truncate_context()` to call `summarize_context()` directly without asyncio wrapper

#### Code Changes
```python
# services/prompts.py:220-259 (remove async)
def summarize_context(text: str, llm_provider=None, max_tokens: int = 512, temperature: float = 0.0) -> str:
    """Summarize text using LLM to preserve key information."""
    from services.llm import get_provider_for_role
    
    if not text:
        return ""
    
    try:
        if llm_provider is None:
            llm_provider, _, _, _ = get_provider_for_role("editor")
        
        summary_prompt = (
            "Summarize the following text concisely while preserving all key facts, "
            "names, dates, numbers, and attributions. The summary will be used as "
            "context for another LLM task, so precision is critical.\n\n"
            f"<text_to_summarize>\n{esc_xml_text(text)}\n</text_to_summarize>\n\n"
            "Return only the summary text, no explanation or preamble."
        )
        
        response = llm_provider.chat(
            messages=[{"role": "user", "content": summary_prompt}],
            model=llm_provider.default_model,
            system="You are a precise summarizer. Preserve all factual claims, names, dates, and numbers.",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.text.strip() if response and response.text else ""
    except Exception as e:
        logger.warning("LLM summarization failed, will fall back to sliding window: %s", e)
        return ""
```

```python
# services/prompts.py:325-336 (remove asyncio wrapper)
if truncation_llm_enabled and overflow > truncation_llm_threshold:
    try:
        summary = summarize_context(
            text,
            llm_provider=llm_provider,
            max_tokens=truncation_llm_max_tokens,
            temperature=truncation_llm_temperature,
        )
        if summary:
            return summary
    except Exception as e:
        logger.warning("LLM truncation failed, falling back to sliding window: %s", e)
```

#### Verification Steps
1. Run `.venv/bin/python -m pytest tests/` (or relevant prompt tests)
2. Trigger `smart_truncate_context` in subagent worker context
3. Check logs for no `RuntimeError: no running event loop`

#### Rollback
Revert `services/prompts.py` to previous state.

---

### 1.4 Fix Thread Pool Exhaustion Risk
**Priority**: High (Stability)
**Files**: `services/subagent.py:32-33`, `services/llm/openai.py:60-63`, `services/llm/anthropic.py:54-57`, `constants.py:12`

#### Current State
- `ThreadPoolExecutor` has 8 workers, no connection-level timeouts on LLM HTTP clients
- `future.cancel()` does not stop running threads; hung HTTP requests exhaust pool
- LLM client timeout (120s) equals stage timeout, no buffer

#### Proposed Changes
1. Configure httpx with separate connect/read timeouts for all LLM clients
2. Reduce `DEFAULT_LLM_TIMEOUT_SECONDS` to 90s (30s buffer before stage timeout 120s)
3. Add connection pool tuning for LLM clients

#### Code Changes
```python
# constants.py:12
DEFAULT_LLM_TIMEOUT_SECONDS = 90.0  # Reduced from 120.0
DEFAULT_LLM_CONNECT_TIMEOUT = 10.0
```

```python
# services/llm/openai.py:60-63
def _create_client(self):
    import httpx
    from openai import OpenAI, DefaultHttpxClient
    
    limits = httpx.Limits(
        max_connections=int(os.environ.get("LLM_POOL_MAX_CONNECTIONS", "32")),
        max_keepalive_connections=int(os.environ.get("LLM_POOL_MAX_KEEP_ALIVE", "16")),
        keepalive_expiry=int(os.environ.get("LLM_KEEP_ALIVE_EXPIRY", "60")),
    )
    timeout = httpx.Timeout(
        connect=DEFAULT_LLM_CONNECT_TIMEOUT,
        read=DEFAULT_LLM_TIMEOUT_SECONDS,
        write=10.0,
        pool=10.0,
    )
    return OpenAI(
        http_client=DefaultHttpxClient(limits=limits, timeout=timeout),
        **self._client_kwargs
    )
```

(Similar changes for `anthropic.py`, `gemini.py`, `ollama.py` using their respective SDK httpx config)

#### Verification Steps
1. Run `.venv/bin/python -c "from services.llm import get_provider_for_role; p, _, _, _ = get_provider_for_role('selector'); print(p)"` to verify client creation
2. Simulate hung HTTP request and confirm thread times out within 90s
3. Monitor thread pool usage via `threading.enumerate()`

#### Rollback
Revert `constants.py` and LLM client files to previous state.

---

### 1.5 Fix ModelLimiter Polling Inefficiency
**Priority**: High (Throughput)
**Files**: `services/limiter.py:45-67`, `services/cache.py:171-183`

#### Current State
- ModelLimiter uses 50ms→500ms polling loop, 2-20 Redis calls/sec per waiter
- Cache.py uses efficient pub/sub pattern for stampede protection

#### Proposed Changes
Adapt pub/sub pattern from `services/cache.py` to ModelLimiter:
1. Add release channel per provider/model
2. Publish to channel on slot release in `release()`
3. Replace polling with `pubsub.get_message()` in `acquire()`

#### Code Changes
```python
# services/limiter.py acquire() method
def acquire(self, provider_id, model, max_concurrent, timeout=300):
    key = f"{self._prefix}:{provider_id}:{model}"
    release_channel = f"{key}:released"
    deadline = time.monotonic() + timeout
    
    while time.monotonic() < deadline:
        try:
            result = self._acquire_script(keys=[key], args=[max_concurrent, timeout])
            if result:
                return True
        except redis.exceptions.RedisError:
            return False
        
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        
        pubsub = self._redis.pubsub()
        try:
            pubsub.subscribe(release_channel)
            # Re-check after subscribing to avoid race condition
            result = self._acquire_script(keys=[key], args=[max_concurrent, timeout])
            if result:
                return True
            pubsub.get_message(timeout=min(remaining, 1.0))
        finally:
            pubsub.unsubscribe(release_channel)
    
    return False
```

```python
# services/limiter.py release() method
def release(self, provider_id, model, timeout=300):
    key = f"{self._prefix}:{provider_id}:{model}"
    release_channel = f"{key}:released"
    try:
        self._release_script(keys=[key])
        self._redis.publish(release_channel, "1")  # Notify waiters
    except redis.exceptions.RedisError:
        logger.warning("Failed to release model limiter slot: %s", e)
```

#### Verification Steps
1. Run load test with multiple concurrent LLM requests
2. Monitor Redis calls/sec for limiter keys (should reduce from ~20/sec to ~1/sec)
3. Confirm no polling loops in logs

#### Rollback
Revert `services/limiter.py` to previous polling implementation.

---

### 1.6 Fix Redis Contention
**Priority**: High (Throughput)
**Files**: `extensions.py`, `config_cache.py`, `services/circuit_breaker.py`

#### Current State
- 5 services share Redis DB 0 (Celery broker, cache, limiter, pipeline monitor, circuit breaker)
- 3 separate connection pools (max 120+ connections)
- No connection pool coordination

#### Proposed Changes
1. Split Redis services into separate databases:
   - DB 0: Celery broker (keep)
   - DB 1: Celery results (keep)
   - DB 2: Cache + PipelineMonitor
   - DB 3: ModelLimiter
   - DB 4: CircuitBreaker
   - DB 5: ConfigCache
   - DB 15: Rate limiter (keep)
2. Consolidate connection pool management in `extensions.py`
3. Add environment variables for DB selection

#### Code Changes
```python
# extensions.py - Update global pool storage to dict per DB
_redis_pools = {}  # Changed from single _redis_pool

def get_redis(db: int = 0) -> redis.Redis:
    """Get Redis client with shared connection pool for specified DB."""
    global _redis_pools
    if db not in _redis_pools:
        url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        # Parse URL and replace DB
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, 
                             parsed.params, f"db={db}", parsed.fragment))
        
        redis_max_conn = int(os.environ.get("REDIS_MAX_CONNECTIONS", "100"))
        _redis_pools[db] = redis.ConnectionPool.from_url(
            new_url,
            max_connections=redis_max_conn,
            socket_timeout=5,
            socket_connect_timeout=3,
            socket_keepalive=True,
        )
    return redis.Redis(connection_pool=_redis_pools[db])
```

Add environment variables to `.env`:
```bash
REDIS_CACHE_DB=2
REDIS_LIMITER_DB=3
REDIS_CIRCUIT_DB=4
REDIS_CONFIG_DB=5
```

#### Verification Steps
1. Check Redis DB usage: `redis-cli -n 0 INFO keyspace`
2. Monitor connection count: `redis-cli INFO clients`
3. Run load test and confirm no contention errors

#### Rollback
Revert Redis DB configuration and connection pool changes.

---

## 2. Medium Priority Tasks

### 2.1 Standardize Retry Configuration
**Priority**: Medium (Maintainability)
**Files**: `tasks/select.py:50`, `tasks/research.py:52`, `tasks/write.py:39`, `tasks/edit.py:357`, `constants.py:4-6`

#### Current State
- Inconsistent `max_retries` (select=3, others=2)
- `constants.py` defines `MAX_STAGE_RETRIES=3` but not used in task decorators
- `default_retry_delay` mismatch (select=30s, others=60s)

#### Proposed Changes
1. Align all tasks to `max_retries=MAX_STAGE_RETRIES` (3)
2. Standardize `default_retry_delay=60`
3. Reference constants in task decorators

#### Code Changes
```python
# tasks/select.py:50
from constants import MAX_STAGE_RETRIES

@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=MAX_STAGE_RETRIES,  # Changed from 3
    default_retry_delay=60,  # Changed from 30
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
```

(Similar changes for `research.py`, `write.py`, `edit.py`)

#### Verification Steps
1. `grep max_retries tasks/*.py` → Confirm all tasks use `MAX_STAGE_RETRIES`
2. Run `.venv/bin/pytest tests/test_tasks.py`

#### Rollback
Revert task decorators to previous hardcoded values.

---

### 2.2 Implement Bulk SQL Operations for Admin Routes
**Priority**: Medium (Throughput)
**Files**: `routes/admin/api/articles.py:386-461`

#### Current State
- Bulk delete/update uses per-item iteration → N+1 SQL statements
- `joinedload()` used unnecessarily for delete operations

#### Proposed Changes
1. Replace per-item iteration with SQLAlchemy bulk operations
2. Remove unnecessary `joinedload()` for delete/reprocess operations

#### Code Changes
```python
# routes/admin/api/articles.py bulk_delete action
elif action == "delete":
    try:
        # Bulk delete - single SQL statement
        deleted_count = Article.query.filter(
            Article.id.in_(article_ids)
        ).delete(synchronize_session=False)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to delete articles"}), 500
```

```python
# Bulk set_status action
elif action == "set_status":
    # Validate transitions first (still need objects)
    articles = Article.query.filter(Article.id.in_(article_ids)).all()
    for article in articles:
        # ... validation logic ...
    
    # Bulk update - single SQL statement
    try:
        stmt = (
            update(Article)
            .where(Article.id.in_(article_ids))
            .values(pipeline_status=new_status)
        )
        db.session.execute(stmt)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to update articles"}), 500
```

#### Verification Steps
1. Test bulk delete of 100 articles: Confirm 2 SQL statements (SELECT + DELETE)
2. Test bulk status update: Confirm 2 SQL statements (SELECT + UPDATE)
3. Run `.venv/bin/pytest tests/routes/admin/test_articles.py`

#### Rollback
Revert `routes/admin/api/articles.py` to per-item iteration.

---

### 2.3 Tune LLM Client Connection Pooling
**Priority**: Medium (Throughput)
**Files**: `services/llm/openai.py`, `anthropic.py`, `gemini.py`, `ollama.py`

#### Current State
- LLM clients use default httpx connection pools
- No tuning for 8 subagent workers

#### Proposed Changes
(Already included in Task 1.4 code changes above)

#### Verification Steps
1. Monitor connection count via `netstat -an | grep ESTABLISHED | grep :443 | wc -l`
2. Run concurrent subagent tasks and confirm connection reuse

#### Rollback
Revert LLM client httpx configuration.

---

### 2.4 Add Token Count Caching (Optional)
**Priority**: Medium (Optimization)
**Files**: `services/prompts.py:15-35`

#### Current State
- `count_tokens()` uses tiktoken with no caching
- Tiktoken `get_encoding()` is already cached, `encode()` is microseconds-fast
- No urgent need, but add as safety net

#### Proposed Changes
Add `@lru_cache` to `count_tokens()`

#### Code Changes
```python
# services/prompts.py:15-35
from functools import lru_cache

@lru_cache(maxsize=128)
def count_tokens(text: str, model: str | None = None) -> int:
    """Count tokens in text using tiktoken if available, otherwise approximate."""
    try:
        import tiktoken
        if model:
            enc = tiktoken.encoding_for_model(model)
        else:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // _CHARS_PER_TOKEN
```

#### Verification Steps
1. Run `.venv/bin/python -c "from services.prompts import count_tokens; print(count_tokens('test' * 1000))"`
2. Confirm cache hits via `count_tokens.cache_info()`

#### Rollback
Remove `@lru_cache` decorator.

---

## 3. Post-Implementation Steps
1. Run lint: `.venv/bin/ruff check . --exclude .venv`
2. Run tests: `.venv/bin/python -m pytest tests/ -x -q`
3. Commit changes: `git add . && git commit -m "perf: apply plan4 improvements"`
4. Deploy to staging environment first
5. Monitor production metrics for 24 hours before full rollout

## 4. Success Metrics
- [ ] 0 `database is locked` errors in production
- [ ] 50% reduction in Redis calls for ModelLimiter
- [ ] 50x fewer SQL statements for bulk admin operations
- [ ] 0 `RuntimeError: no running event loop` errors
- [ ] Thread pool exhaustion incidents = 0

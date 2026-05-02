# Redis DB Splitting Strategy

## Current State

Redis is used for multiple purposes in the application:
- **Celery broker**: `redis://localhost:6379/0` (DB 0)
- **Celery results**: `redis://localhost:6379/1` (DB 1)
- **Cache** (ResponseCache): Uses default Redis connection
- **Metrics**: Uses default Redis connection
- **Limiter**: Uses default Redis connection
- **Circuit breaker**: Uses default Redis connection

## Rationale for Splitting

Separate Redis databases prevent:
1. **Key collisions**: Different services accidentally using same key names
2. **Namespace pollution**: Metrics keys mixed with cache keys
3. **Flush isolation**: `FLUSHDB` for one service doesn't affect others
4. **Monitoring**: Per-DB metrics in Redis INFO command

## Recommended Configuration

### DB Assignment

| DB | Purpose | Config Variable |
|----|---------|-------------------|
| 0 | Celery broker | `CELERY_BROKER_URL` (default) |
| 1 | Celery results | `CELERY_RESULT_BACKEND` |
| 2 | Response cache | `REDIS_CACHE_DB` (new) |
| 3 | Metrics | `REDIS_METRICS_DB` (new) |
| 4 | Limiter | `REDIS_LIMITER_DB` (new) |
| 5 | Circuit breaker | `REDIS_CIRCUIT_DB` (new) |
| 6 | Pipeline locks | `REDIS_LOCKS_DB` (new) |

### Implementation

#### Step 1: Add Configuration (config.py)

```python
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# DB splitting
CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/1"
REDIS_CACHE_DB = int(os.environ.get("REDIS_CACHE_DB", "2"))
REDIS_METRICS_DB = int(os.environ.get("REDIS_METRICS_DB", "3"))
REDIS_LIMITER_DB = int(os.environ.get("REDIS_LIMITER_DB", "4"))
REDIS_CIRCUIT_DB = int(os.environ.get("REDIS_CIRCUIT_DB", "5"))
REDIS_LOCKS_DB = int(os.environ.get("REDIS_LOCKS_DB", "6"))
```

#### Step 2: Update Services to Use Correct DB

Each service that uses Redis should accept a `db` parameter or use a factory function:

```python
# services/cache.py
def get_redis_client(db: int = REDIS_CACHE_DB) -> redis.Redis:
    return redis.from_url(f"{REDIS_URL}/{db}")
```

#### Step 3: Environment Variables (.env)

```bash
REDIS_URL=redis://localhost:6379
REDIS_CACHE_DB=2
REDIS_METRICS_DB=3
# etc.
```

## Current Implementation Status

**Partially implemented:**
- Celery broker (DB 0) ✓
- Celery results (DB 1) ✓
- Other services: Use default connection (no DB splitting)

**To complete:**
1. Add DB configuration to `config.py`
2. Update `extensions.py` to pass correct DB
3. Update `services/cache.py`, `services/metrics.py`, etc.
4. Add environment variables to `.env.example`

## When to Implement

Complete this when:
- Redis key collisions become problematic
- Need to monitor/flush specific service keys
- Scaling to separate Redis instances per service

For current scale, the partial implementation (broker/results split) is sufficient.

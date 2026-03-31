# Consolidated Improvement Plan

## Overview

Fixes and improvements identified during codebase review. Organized into waves that can be executed in parallel using sub-agents.

**Total: 11 actionable items** across 3 waves. Items marked "no action" are documented for completeness but require no code changes.

---

## No-Action Items

These were assessed and determined to be correct as-is:

- **`.DS_Store` files**: Already ignored in `.gitignore`, none tracked. No action needed.
- **`_title_word_set()` filtering 2-letter terms**: Intentional noise reduction for Jaccard dedup. No action needed.
- **`run_all_sources` blocking for 5 minutes**: Standard Celery group pattern with graceful TimeoutError handling. No action needed (see Wave 3 for minor timeout headroom adjustment).
- **Docker vs systemd bind address**: Each deployment method is correct for its architecture. No action needed.

---

## Wave 1: Mechanical / No-Risk Changes

These items are independent of each other and can be executed in parallel across sub-agents.

### 1.1: f-strings in log calls (24 instances across 10 files)

**Problem:** Project convention requires %-formatting in log calls for deferred string construction. 24 f-string log calls always evaluate even when the log level is filtered out.

**Conversion pattern:**
```python
# Before
logger.warning(f"404 Not Found: {request.method} {request.path}")
logger.error(f"500 Internal Server Error: {e}", exc_info=True)

# After
logger.warning("404 Not Found: %s %s", request.method, request.path)
logger.error("500 Internal Server Error: %s", e, exc_info=True)
```

**Files and lines:**

| File | Lines | Count |
|------|-------|-------|
| `app.py` | 159, 190 | 2 |
| `config.py` | 175 | 1 |
| `logging_config.py` | 124 | 1 |
| `routes/admin/__init__.py` | 118, 158, 181, 210 | 4 |
| `routes/admin/articles.py` | 285 | 1 |
| `routes/admin/review.py` | 68, 93 | 2 |
| `tasks/cleanup.py` | 27, 31, 56, 60 | 4 |
| `tasks/extract.py` | 102, 115, 218, 231 | 4 |
| `adapters/base.py` | 77 | 1 |
| `adapters/web.py` | 50, 53, 62, 64 | 4 |

**Notes:**
- `logger.error(..., exc_info=True)` must preserve `exc_info=True` as a keyword argument after positional args.
- `request_logger.info(...)` at `logging_config.py:124` has an `extra={...}` keyword arg that must be preserved.

**Tests:** No test changes needed.

---

### 1.2: Redis variable shadowing in `tasks/crawl.py` and `tasks/newsletter.py`

**Problem:** Both files assign `redis = get_redis()`, shadowing the `redis` module name. A future `import redis.exceptions` would be silently shadowed.

**Fix:** Rename local variable to `redis_client` in both files.

**`tasks/crawl.py`:**
- Line 35: `redis = get_redis()` -> `redis_client = get_redis()`
- Line 37: `redis.set(...)` -> `redis_client.set(...)`
- Line 39: `redis.get(...)` -> `redis_client.get(...)`
- Line 42: `redis.set(...)` -> `redis_client.set(...)`
- Line 143: `release_lock(redis, ...)` -> `release_lock(redis_client, ...)`

**`tasks/newsletter.py`:**
- Line 315: `redis = get_redis()` -> `redis_client = get_redis()`
- Line 317: `redis.get(...)` -> `redis_client.get(...)`
- Line 325: `redis.set(...)` -> `redis_client.set(...)`
- Line 333: `release_lock(redis, ...)` -> `release_lock(redis_client, ...)`

**Tests:** No new tests needed — rename only, no behavioral change.

---

### 1.3: Prompt file drift documentation

**Problem:** System prompts exist in `pipeline.yaml` (primary) and `prompts/*.txt` (fallback). The fallback files are never actually used at runtime since every stage config includes `system_prompt`. They could drift silently.

**Fix:** Add documentation clarifying the relationship. No code logic changes.

**`services/prompts.py`** — add comment before `_PROMPTS_DIR`:
```python
# Fallback prompts — pipeline.yaml system_prompt fields are the source of truth.
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

**`prompts/README.md`** — create:
```markdown
# Prompt files

These are fallback prompts. The source of truth is `pipeline.yaml` (`system_prompt`
fields under each pipeline stage). These files are only used when `pipeline.yaml`
does not define a `system_prompt` for a given role.
```

**Tests:** No test changes needed.

---

## Wave 2: Small Targeted Fixes

These items are independent of each other and can be executed in parallel across sub-agents. Each touches a different file/module.

### 2.1: `config_unified.py` singleton not thread-safe

**Problem:** `get_config()` at `services/config_unified.py:122` uses a bare global `_instance` without locking. Other singletons (`get_redis`, `get_response_cache`, `get_metrics`, `get_config_cache`) all use `threading.Lock` with double-checked locking.

**Fix:** Add `_config_lock = threading.Lock()` and use double-checked locking.

**`services/config_unified.py`:**
```python
# Add after line 119
import threading
_config_lock = threading.Lock()

# Replace get_config()
def get_config() -> AppConfig:
    """Get the unified app config (cached singleton)."""
    global _instance
    if _instance is not None:
        return _instance
    with _config_lock:
        if _instance is not None:
            return _instance
        _instance = AppConfig.from_flask()
        return _instance

# Update reset_config()
def reset_config() -> None:
    """Reset cached config (for testing)."""
    global _instance
    with _config_lock:
        _instance = None
```

**Tests:** Add a concurrency test in `tests/test_concurrent_access.py` that calls `get_config()` from multiple threads simultaneously and verifies only one instance is created.

---

### 2.2: Unguarded `db.session.commit()` in `app.py:_seed_share_configs()`

**Problem:** `_seed_share_configs()` calls `db.session.commit()` without try/except/rollback. Runs during `create_app()`. If commit fails, the session is left in a bad state.

**Fix:**
```python
def _seed_share_configs():
    from models import ShareConfig

    defaults = [ ... ]  # existing defaults
    for d in defaults:
        existing = ShareConfig.query.filter_by(platform_key=d["platform_key"]).first()
        if not existing:
            db.session.add(ShareConfig(**d))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning("Failed to seed share configs", exc_info=True)
```

**Tests:** No new tests needed — defensive change, existing app creation tests cover this.

---

### 2.3: Bulk article delete — simplify redundant manual cascade

**Problem:** The bulk delete operation manually deletes Citations, ArticleMetrics, ArticleVersions, and article_tags entries before deleting the article. The model relationships already define `cascade="all, delete-orphan"` and FK constraints use `ondelete="CASCADE"`. Manual cleanup is redundant.

**Fix:** Replace manual cascade with simple per-article delete (ORM cascade handles children):

```python
if action == "delete":
    try:
        for article in articles:
            db.session.delete(article)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"message": "Failed to delete articles"}), 500
    return jsonify({"message": f"Deleted {len(articles)} articles"})
```

**Caveat:** SQLite doesn't support ALTER TABLE for FK constraints, but `cascade="all, delete-orphan"` on relationships handles this correctly at the SQLAlchemy level.

**Tests:** Verify existing bulk delete tests still pass. Consider adding a test confirming child records are removed when an article is deleted via bulk endpoint.

---

### 2.4: Tag query optimization on every article edit

**Problem:** Every edit stage runs `Tag.query.order_by(Tag.id.desc()).limit(500).all()` — a full table scan to build tag names for the prompt. The tag list changes infrequently.

**Fix:** Simple approach — remove unnecessary ordering and reduce limit:

```python
existing_tags = [t.name for t in Tag.query.limit(100).all()]
```

Order doesn't matter for a list of names. 100 is sufficient for the foreseeable tag universe. Add caching only if profiling shows this is a bottleneck.

**Tests:** No new tests needed for the simple fix.

---

### 2.5: `lazy="joined"` on Article.citations and Article.tags

**Problem:** Both relationships use `lazy="joined"`, meaning every Article query loads all citations and tags via LEFT JOIN. For list views that don't need this data, this adds unnecessary JOINs and memory.

**Fix:**
```python
citations = db.relationship(
    "Citation", backref="article", lazy="select", cascade="all, delete-orphan"
)
tags = db.relationship("Tag", secondary=article_tags, lazy="selectin")
```

Views that need this data already use `joinedload()` overrides (e.g., `get_articles_paginated()` in `services/article.py:85-89`).

**Tests:** Run full test suite — any test relying on implicit joined loading will surface issues. Check tests that access `article.citations` or `article.tags` without explicit loading.

---

## Wave 3: More Involved Changes

These items have more cross-cutting impact and should be done sequentially after Waves 1-2 are complete and verified.

### 3.1: `_app_cache` never invalidated on config reload

**Problem:** `FlaskTask.__call__` caches Flask app instances in `_app_cache` keyed by config name. When the admin config reload endpoint clears config caches, the cached Flask app instances still hold stale config. New Celery task executions use old config until worker restart.

**Fix:**

**`celery_app.py`:**
```python
def clear_app_cache():
    """Clear cached Flask app instances. Call after config changes."""
    global _app_cache
    with _app_cache_lock:
        _app_cache = {}
```

**`routes/admin/api.py:reload_config`:**
```python
from celery_app import clear_app_cache
clear_app_cache()
```

**Tests:** Add test verifying `clear_app_cache()` empties the cache. Integration test: change config, call reload, verify next Celery task picks up new value.

---

### 3.2: `soft_time_limit` not handled explicitly

**Problem:** 12 tasks define `soft_time_limit=300` alongside `time_limit=360`. None catch `SoftTimeLimitExceeded` — it falls through to generic `except Exception` handlers and is treated as a normal failure rather than a timeout-specific case. No graceful cleanup, no distinction in logs, articles may be left in intermediate states.

**Fix:** Add `SoftTimeLimitExceeded` handling to `run_stage()` in `tasks/pipeline.py` (central error handler for all pipeline stages):

```python
from billiard.exceptions import SoftTimeLimitExceeded

# In run_stage's except block, before generic Exception:
except SoftTimeLimitExceeded:
    db.session.rollback()
    record_stage_result(stage, success=False, run_id=run_id)
    article = db.session.get(Article, article_id)
    if article:
        article.last_error = f"{stage}: soft time limit exceeded"
    raise  # Let Celery handle retry
except Exception as e:
    # existing handler
```

For non-pipeline tasks (`crawl_source`, `run_all_sources`, `generate_daily_newsletters`), add a top-level handler:

```python
from billiard.exceptions import SoftTimeLimitExceeded

try:
    # existing logic
except SoftTimeLimitExceeded:
    db.session.rollback()
    logger.error("Task exceeded soft time limit")
    raise
```

**Tests:** Add test simulating `SoftTimeLimitExceeded` in a pipeline stage, verifying article state is correctly handled (rolled back, error message set).

---

### 3.3: `result.get(timeout=300)` inside task with `time_limit=360`

**Problem:** `run_all_sources()` calls `result.get(timeout=300, propagate=False)`. The task itself has `time_limit=360`. If sources are slow, the hard time limit could kill the orchestration task before `get()` returns, leaving the PipelineRun in an inconsistent state.

**Fix:** Reduce the `get()` timeout to leave headroom:

```python
results = result.get(timeout=240, propagate=False)
```

**Tests:** No behavioral change with timeout reduction. Existing integration tests cover the happy path.

---

## Execution Strategy

### Wave 1 (Parallel)
- Sub-agent A: Item 1.1 (f-strings in log calls — 10 files)
- Sub-agent B: Item 1.2 (Redis shadowing — 2 files)
- Sub-agent C: Item 1.3 (Prompt docs — 2 files)

### Wave 2 (Parallel)
- Sub-agent D: Item 2.1 (config_unified thread safety)
- Sub-agent E: Item 2.2 (unguarded commit in app.py)
- Sub-agent F: Item 2.3 (bulk delete simplification)
- Sub-agent G: Item 2.4 (tag query optimization)
- Sub-agent H: Item 2.5 (lazy="joined" fix)

### Wave 3 (Sequential)
- Sub-agent I: Item 3.1 (app cache invalidation)
- Sub-agent J: Item 3.2 (soft time limit handling)
- Sub-agent K: Item 3.3 (timeout headroom)

### Verification
After each wave:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

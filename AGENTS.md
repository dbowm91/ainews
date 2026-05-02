# AGENTS.md

Conventions for AI coding agents working in this codebase.

## Modular Structure

This file serves as the **index** for contextual agent conventions. Content is distributed into `AGENTS.override.md` files at the module level to reduce context pollution.

### How It Works

- **Root `AGENTS.md`** (this file): Index and global conventions only
- **Module-level `AGENTS.override.md`**: Contextual conventions for that specific module
- Agents should read both: root index + relevant module file(s)

### How to Add/Update Conventions

**When adding conventions for a specific module:**
1. Add to the module's `AGENTS.override.md` file (e.g., `services/AGENTS.override.md`)
2. Do NOT add contextual content to this root file

**When adding global conventions that apply everywhere:**
1. Add to this root file under the appropriate section
2. Consider whether it truly needs to be global or if it's module-specific

### Convention Files Location

| Module | File |
|--------|------|
| Services layer (general) | `services/AGENTS.override.md` |
| LLM providers | `services/llm/AGENTS.override.md` |
| Search services | `services/search/AGENTS.override.md` |
| Tasks & pipeline | `tasks/AGENTS.override.md` |
| Routes (general) | `routes/AGENTS.override.md` |
| Admin routes | `routes/admin/AGENTS.override.md` |
| Testing | `tests/AGENTS.override.md` |
| Static assets | `static/AGENTS.override.md` |
| Schemas | `schemas/AGENTS.override.md` |
| Models | `models/AGENTS.override.md` |
| Templates | `templates/AGENTS.override.md` |

---

## Run before committing

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

**Note:** Mypy is not yet fully implemented; focus on Ruff and Pytest for immediate validation.

---

## Core Mandates

These apply globally and should NOT be moved to module files.

### Fail-Closed Policy (CRITICAL)
All distributed locks (Redis) and limiters MUST fail closed.
- **Incorrect:** Returning `True` or proceeding on `RedisError`.
- **Correct:** Raising the exception or returning `False` to halt execution.
- **Reference:** `tasks/pipeline.py:_acquire_stage_lock` must NOT proceed without a lock.
- **Note on Limiter:** `services/limiter.py:acquire()` returns `False` on RedisError - this is acceptable fail-closed behavior since callers interpret False as "slot not acquired." Both exception-raising and False-return are valid implementations.

### LLM Content Sanitization
`final_article` content is sanitized with `bleach.clean()` allowing only safe tags (`a`, `b`, `i`, `ul`, `li`). Do NOT apply `|e` filter to already-sanitized content in templates.

### Memory Summarization
`smart_truncate_context()` in `services/prompts.py` uses LLM-based summarization for large context overflow.

### Importance-Weighted Truncation
`importance_weighted_truncate()` prioritizes key content segments.

### Token-Aware Truncation
Truncation respects model token limits via `count_tokens()` and `max_tokens_for_model()`.

### Sources & Articles
- **Source CRUD API:** REST endpoints at `/api/v1/sources` for programmatic source management. Supports PATCH for partial updates.
- **FTS5 Search:** Full-text search via `articles_fts` and `articles_admin_fts` virtual tables. Fallback to ILIKE for unsupported queries.
- **Admin Article Validation:** MAX_ constants in `routes/admin/articles.py` limit field lengths (headline: 500, tldr: 300, body: 50000, etc.).
- **Bulk Article Optimization:** N+1 queries prevented via `joinedload(Article.source)` and `joinedload(Article.tags)`.
- **Subscriber Sunset Policy:** Subscribers are flagged inactive after configurable bounce threshold (`SUBSCRIBER_MAX_BOUNCES`, default 5) or inactivity (`SUBSCRIBER_INACTIVITY_DAYS`, default 180 days).
- **Pipeline Status Deprecation:** `PipelineStatus.SELECTING` is deprecated and removed; the selection logic is now integrated into the research phase or handled via explicit assignment.

### Admin API
- **Trend Memory Admin UI:** Admin UI at `/admin/trend-memory` with list view, filtering, stats (total, high/medium/low, expired count), delete individual/purge expired entries, links to source articles.
- **Webhook Management UI:** Admin UI at `/admin/webhooks` with event history, test webhook, resend events. API endpoint `GET /admin/api/webhooks/<id>/events` returns delivery events (HTML for HTMX, JSON for API).

### Dashboard
- **Query Consolidation:** `_compute_dashboard_stats()` uses caching (60s TTL) and consolidated queries with `outerjoin()` and `group_by()` for better performance.
- **SLA Tracking & Analytics:** Article SLA timestamps (`crawled_at`, `selected_at`, `published_at`) with admin endpoint `GET /admin/api/pipeline/sla` returning avg, p50, p95 processing times. Newsletter delivery stats at `GET /admin/api/newsletters/stats`, search analytics at `GET /admin/api/search/analytics`.

---

## Common Patterns Reference

### Adding Audit Logging
```python
from services.audit import log_admin_action

log_admin_action(
    "action_name",
    target_type="resource_type",
    target_id=resource.id,
    details={"key": "value"},
    category="article",  # auth, article, pipeline, webhook, config, subscriber
)
```

### Adding Cache Invalidation
```python
from services.cache import get_response_cache

try:
    cache = get_response_cache()
    cache.invalidate_prefix("cache_key_prefix")
except Exception as e:
    logger.warning("Failed to invalidate cache: %s", e)
```

### Response Cache Stampede Protection
Use Redis pub/sub pattern for stampede protection, not polling:
```python
if not self._redis.set(lock_key, "1", nx=True, ex=ttl):
    # Wait for result via pub/sub
    channel = f"{self._prefix}done:{key}"
    pubsub = self._redis.pubsub()
    pubsub.subscribe(channel)
    try:
        cached = self.get(key)
        if cached is not None:
            return cached
        message = pubsub.get_message(timeout=ttl)
        return self.get(key)
    finally:
        pubsub.unsubscribe(channel)
```

---

## Notes for Future Agents

1. **Preserve Fallback Layers:** The codebase has good fallback patterns (e.g., ResponseCache has multiple fallback strategies, Redis-backed metrics with in-memory fallback). Preserve these when making changes.

2. **Configuration-Driven:** Features support configuration via `pipeline.yaml` or environment variables. Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders.

3. **Exception Handling:** When catching exceptions, prefer specific types (`SQLAlchemyError`, `ValueError`, `KeyError`, `AttributeError`) over broad `Exception` to preserve error context for debugging.

4. **Code Evolution:** Always verify line numbers and code patterns against the current codebase before making changes, as code evolves over time.

5. **Subagent System:** Tool filtering exists via `stage_config.tools` in pipeline.yaml and `initialize_tool_registry()` in services/subagent.py. The `ToolSelector` protocol in `services/tool_selection.py` provides stage-aware tool selection.

6. **Dead Code Removal:** Periodically check for and remove dead code (functions defined but never called). Confirm zero callers via grep before removal.

7. **Parallelization:** Many improvements can be implemented in parallel by separate agents working on different functional areas (e.g., tasks, services, routes, CSS).
## Completed Waves (as of 2026-05-02)

All waves from `plans/plan.md` have been completed:

- **Wave 1** (14 items): Critical Security & Documentation Fixes ✅
- **Wave 2** (20 items): High-Priority Backend Fixes ✅
- **Wave 2.5** (2 items): Pre-Refactor Validation ✅
- **Wave 3** (17 items): Code Quality & Performance ✅ (partial - see Remaining Issues)
- **Wave 4** (10 items): AI Harness & Advanced Features ✅
- **Wave 5** (14 items): Frontend Polish & Low-Priority Items ✅ (partial - see Remaining Issues)

## Remaining Issues (as of 2026-05-02)

The following items were identified during verification but not fully resolved:

### Wave 3 - Code Quality
- **W3-R1: C901 Complexity Violations** (5 functions with complexity >15):
  - `app.py:61`: `create_app` (complexity 31)
  - `routes/admin/api/articles.py:23`: `get_article_ids` (complexity 25)
  - `routes/admin/api/articles.py:351`: `bulk_article_operations` (complexity 19)
  - `routes/admin/articles.py:79`: `articles` (complexity 21)
  - `routes/admin/articles.py:212`: `edit_article` (complexity 16)
  - **Resolution**: Manual refactoring required to break down complex functions

- **W3-R4: ToolSelector Integration** - ToolSelector protocol exists in `services/tool_selection.py` but is NOT integrated into `run_subagent()` path
  - **Status**: Infrastructure exists, integration incomplete

### Wave 5 - Frontend & Low-Priority
- **W5-B2: Subscriber Cleanup Task** - Function exists in `services/subscribers.py` but is NOT scheduled as a Celery task
  - **Missing**: `@shared_task` decorator, not in `config.py:get_beat_schedule()`, not in `pipeline.yaml`
  - **Status**: Dead code currently

- **Font Scale Responsiveness** - No fluid typography using `clamp()` or media queries for font scaling
  - **Status**: Fixed font sizes (16px root), no responsive scaling

### Ruff Violations (Fixed During This Session)
- **BLE001**: Fixed in `services/embeddings.py`, `services/subagent/runner.py`, `adapters/base.py`, `adapters/web.py`
- **RUF100**: Fixed unused noqa comments in `adapters/web.py`, `app.py`, `celery_app.py`
- **S311**: Fixed in `adapters/web.py` (replaced `random.choice()` with `secrets.randbelow()`)

---

## New Features Added (2026-05-02)

During the implementation session, the following items were added:

### Documentation
- `docs/dead_letter.md`: Comprehensive dead letter queue documentation
- `docs/postgresql-migration-strategy.md`: PostgreSQL migration strategy (intentionally staying with SQLite)
- `docs/redis-db-splitting.md`: Redis DB splitting strategy document
- Fixed `README.md` pipeline diagram (removed deprecated SELECTING)
- Fixed `docs/api.md` article ID references
- Fixed `docs/trend-memory.md` and `docs/context-service.md` (19 models, not 18)

### Tests Added
- `tests/test_subagent.py`: Added `TestBuiltInToolsExtended` (12 tests for previously untested tools)
- `tests/test_subagent.py`: Added `TestMiddleware` (9 tests for middleware classes)
- Improved subagent package coverage from 73% to 84%

### Code Fixes
- Fixed N+1 query in `tasks/cleanup.py` (added `contains_eager()`)
- Fixed test failures: `test_ollama.py`, `test_retry.py`, `test_subagent.py`
- Fixed circuit breaker reset in `tests/conftest.py`
- Fixed import patches in test files

---

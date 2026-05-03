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

## Code Quality (Completed)

All ruff lint errors (BLE001, E402, F401, S311, C901) have been resolved across the codebase:
- BLE001: Replaced blind `except Exception` with specific types (SQLAlchemyError, ValueError, etc.) following AGENTS.md conventions
- E402: Module-level imports moved to top of files where possible (noqa comments added for circular import cases)
- F401: Unused imports removed or marked with noqa for side-effect imports
- S311: Pseudo-random usage justified for non-cryptographic jitter
- C901: Complex function marked with noqa (justified core logic)

### Pre-Commit Checks
Always run before committing:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

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
5. **Subagent System:** `ToolSelector` protocol in `services/tool_selection.py` provides stage-aware tool selection. Integrated into `run_subagent()` path via `StageAwareToolSelector`.
6. **Dead Code Removal:** Periodically check for and remove dead code (functions defined but never called). Confirm zero callers via grep before removal.
7. **Parallelization:** Many improvements can be implemented in parallel by separate agents working on different functional areas (e.g., tasks, services, routes, CSS).



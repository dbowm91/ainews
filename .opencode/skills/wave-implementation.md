# AINews Implementation Conventions

Conventions for working on this codebase, including branch management, verification, and architectural patterns.

## Branch Management Rules

1. **Separate Branches:** Each distinct task or fix should use a dedicated branch to avoid merge conflicts
2. **Branch Naming:** `feat/description`, `fix/description`, `docs/description` where description is concise
3. **Merge Strategy:** Use `git merge --no-ff` to preserve task branch history when merging into integration branches

## Verification

Before merging any changes:
- Run linter: `.venv/bin/ruff check . --exclude .venv`
- Run type check: `.venv/bin/mypy . --exclude .venv` (some complex types in models/ and metrics/ may fail)
- Run tests: `.venv/bin/python -m pytest tests/ -x -q`
- Review diff for unintended changes
- Ensure only task-related files are modified

## Layering Conventions

Critical architecture rules:
- **Adapters** (`adapters/`) should NOT import from **Services** (`services/`)
- **Utils** (`utils/`) should contain pure helper functions with minimal dependencies
- **Tasks** can import from services (tasks are orchestrators that use business logic)

For type hints only (not runtime imports), use the `TYPE_CHECKING` pattern:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from adapters.base import RawItem
```

## Key Architectural Conventions

### Pipeline Stages
Pipeline stages use these statuses: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`

The `_STAGE_TASKS` dict in `tasks/pipeline.py` maps stages to their task functions.

### Subagent Location
The subagent module is at `services/subagent/` not top-level `subagent/`.

### API Endpoint Paths
- Admin API endpoints are at `/api/v1/` prefix (e.g., `/api/v1/articles`)
- `admin_api_bp` blueprint is registered with `url_prefix="/api/v1"`
- `admin_bp` provides HTML pages at `/admin`

### SQLAlchemy Reserved Names
`metadata` is reserved by SQLAlchemy - use `meta` instead for JSON fields (e.g., `PipelineLog.meta`)

### Model Field Naming
- `Source.type` is actually `source_type` in the model
- `Source.last_fetch_at` is actually `last_crawled`
- `Article.finalized_at` doesn't exist - use `published_at`
- `TrendMemory.observation` is actually `signal`
- `TrendMemory.embedding` is `db.Text` (not a vector type)

### Rate Limiter
The rate limiter uses Redis slots. Always release slots in a `finally` block to avoid leaks.
- Use `provider_id` (actual provider used) not `rc.provider` (configured provider) when releasing
- `_try_stage_work` returns the actual model used after fallback

### LLM Provider Fallback Chain
The fallback chain is **dynamic** - determined by enabled providers in `providers.yaml` configuration order, not hardcoded. The `get_provider_chain()` function iterates through enabled providers and filters out those with open circuits.

## Pre-existing Issues (Known)

### MagicMock in Tests
Some tests fail due to MagicMock objects being JSON serialized - this is a test infrastructure issue, not a code bug. When patching functions, patch where they're looked up at runtime, not where they're defined.

### Complex Type Errors
Some complex type errors remain in `models/`, LLM providers, and metrics. Focus on new code, not legacy.

## Architecture Review Findings (2026-05-12)

### Bugs Fixed from Architecture Review

The following bugs were identified and fixed during architecture review:

| Bug | Module | Fix | Files Modified |
|-----|--------|-----|----------------|
| Missing `urlparse` import | routes | Added `from urllib.parse import urlparse` | `routes/admin/api/articles.py` |
| `retry_stuck` missing SELECTING status | tasks | Added `PipelineStatus.SELECTING` to filter | `tasks/retry.py` |
| Limiter slot leak on LLM fallback | services | Use `provider_id` from `get_provider_for_role()` not `stage_config.provider` | `services/newsletter_pipeline.py` |
| Tool registry race condition | subagent | Added `_TOOL_REGISTRY_LOCK` threading lock | `services/subagent/registry.py` |
| Executor never shutdown | subagent | Added `atexit.register(shutdown_executor)` | `services/subagent/config.py` |

### Subagent System Thread Safety

The subagent system uses module-level singletons that require thread-safe initialization:

1. **Tool Registry**: `_TOOL_REGISTRY` dict with `_TOOL_REGISTRY_LOCK` for thread-safe initialization via `initialize_tool_registry()`
2. **ThreadPoolExecutor**: `_subagent_executor` should be shutdown via `atexit.register(shutdown_executor)` on application exit

### Limiter Pattern Verification

When acquiring and releasing rate limiter slots:
- Always use `provider_id` (the actual provider used, returned from `get_provider_for_role()` or `_try_stage_work()`) not `rc.provider` (the configured provider)
- The configured provider may differ from actual provider when fallback occurs
- This applies to both `limiter.acquire()` and `limiter.release()` calls

## Common Fix Patterns

### SSRF Protection Import
Adapters should import from `utils/url.py`, not `services/url.py`:
```python
from utils.url import validate_url_safe, UnsafeURLError
```

### Session Hijacking Protection
The `require_auth` decorator in `routes/admin/__init__.py` implements IP and User-Agent binding for session security.

### Newsletter Idempotency
The `idempotency_key` for newsletter generation is defined in `_generate_daily_newsletters_core()` scope.

### trafilatura ImportError Handling
```python
except ImportError:
    logger.warning("trafilatura not installed, ...")
except (ValueError, AttributeError) as e:
    logger.warning("Content extraction failed for ...")
    raise  # Re-raise unexpected errors
```

## Testing Notes

Before starting new work, check if tests were already failing:
```bash
git stash
.venv/bin/python -m pytest tests/ -x -q
git stash pop
```

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

## Architecture Review Findings (2026-05-22)

### Bugs Fixed from Architecture Review (2026-05-22)

The following bugs were identified and fixed during the 2026-05-22 architecture review:

| Bug | Module | Fix | Files Modified |
|-----|--------|-----|----------------|
| Missing `_dispatch_next` import | tasks/edit | Added import from `tasks.pipeline` | `tasks/edit.py:159` |
| `article_id` unbound in validation handler | tasks/edit | Changed calls to use `article.id` | `tasks/edit.py:185,206` |
| Self-import circular dependency | tasks/retry | Removed self-import of `_dead_letter` | `tasks/retry.py:37` |
| Wrong `_apply_fallback` import source | tasks/retry | Import from `services.pipeline_degradation` | `tasks/retry.py:209` |
| SVG script XSS bypass | utils/text | Added `_skip_data`/`_skip_stack` tracking | `utils/text.py:83-131` |
| CSS expression() not stripped | utils/text | Added `expression(` pattern check | `utils/text.py:104-106` |
| Middleware mutates cached tool.fn | subagent | Clone fn before wrapping via `copy.deepcopy` | `services/subagent/runner.py:347` |
| APIAdapter item_url no external_id warning | adapters/api | Added warning when using default `external_id` path | `adapters/api.py:63-71` |
| APIAdapter missing `contains` filter | adapters/api | Implemented `contains` filter operation | `adapters/api.py:196-211` |

---

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
| SSRF redirect counter persists | adapters | `_redirect_count` now uses thread-local storage | `adapters/session.py` |
| Duplicate `_finalize_subagent_result` | subagent | Removed duplicate definition | `services/subagent/runner.py` |
| No adapter config validation | schemas | Added `field_validator` to `SourceConfig` | `schemas/source.py` |
| sanitize_html bare except | utils/text | Uses `except (ValueError, Exception)` | `utils/text.py` |
| strip_tags bare except | utils/html | Uses `except (ValueError, Exception)` | `utils/html.py` |
| trafilatura ImportError silent | utils/html | Logs warning when trafilatura unavailable | `utils/html.py` |
| truncate no negative validation | utils/text | Raises `ValueError` if length < 0 | `utils/text.py` |
| utils/url.py docstring inaccurate | utils/url | Docstring now notes global mutable state | `utils/url.py` |
| StageConfig stub undocumented | schemas/pipeline | Added docstring explaining stub purpose | `schemas/pipeline.py` |
| backfill_embeddings no max_retries | tasks/embeddings | Added `max_retries=CELERY_TASK_MAX_RETRIES` | `tasks/embeddings.py` |
| TrendMemory missing last_accessed_at | models/context | Added `last_accessed_at` field | `models/context.py` |

### Subagent System Thread Safety

The subagent system uses module-level singletons that require thread-safe initialization:

1. **Tool Registry**: `_TOOL_REGISTRY` dict with `_TOOL_REGISTRY_LOCK` for thread-safe initialization via `initialize_tool_registry()`
2. **ThreadPoolExecutor**: `_subagent_executor` should be shutdown via `atexit.register(shutdown_executor)` on application exit

### Limiter Pattern Verification

When acquiring and releasing rate limiter slots:
- Always use `provider_id` (the actual provider used, returned from `get_provider_for_role()` or `_try_stage_work()`) not `rc.provider` (the configured provider)
- The configured provider may differ from actual provider when fallback occurs
- This applies to both `limiter.acquire()` and `limiter.release()` calls

### Quality Gates
Each pipeline stage has quality gates that can route articles to `review` for manual inspection even when the stage "succeeds":
- `select`: Low confidence (score OK but confidence="low") → `review`
- `research`: Degenerate research brief (fails `_is_degenerate_research()`) → `review`
- `write`: Degenerate draft (fails `_is_degenerate_write()`) → `review`
- `edit`: Validation failure → `review`

See `architecture/tasks.md` for full documentation.

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

## All Plan Items Completed

**Status: ALL WAVES COMPLETED** as of 2026-05-21

All items from the consolidated implementation plan have been completed:
- Wave A (CRIT-1, CRIT-2, CRIT-3): Critical bugs fixed
- Wave B (MED-1 through MED-8): Medium priority fixes completed
- Wave C (LOW-1 through LOW-6): Documentation updates completed
- Wave A4 (CRIT-A4): TrendMemory field added
- Wave B1 (HIGH-B1): Quality gate documentation added
- Wave C9 (MED-C9): backfill_embeddings decorator fixed
- Wave D7 (LOW-D7): Scheduled tasks documentation completed

Additional items completed on 2026-05-21:
- HIGH-1: Article model documentation updated with all 30+ fields
- HIGH-3: Index documentation updated with exact index names
- MED-8: Missing admin routes added to documentation
- MED-11: APIAdapter pagination implemented (next_link + query_param)
- MED-16: PENDING→SKIPPED transition documented
- MED-17: API token prefix detail (first 16 chars) documented
- MED-18: Missing task files (retry.py, subscribers.py, webhook.py) added to docs
- MED-19: pipeline_monitor functionality corrected in docs
- LOW-1: cleanup.py tasks listed individually
- LOW-2: Degradation path documented as pending→review
- LOW-4: Duplicate URL Utilities section removed
- MED-1: Edit stage degradation behavior corrected
- MED-9: AuthError bypass documented
- MED-10: Backoff max 300s documented
- MED-12: Hybrid provider table corrected

See `plans/plan.md` for full details.

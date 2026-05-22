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

## Implementation Patterns

### Limiter Slot Leak Prevention
Always use `provider_id or rc.provider` and `model or rc.model` when releasing limiter slots:
```python
finally:
    limiter.release(provider_id or rc.provider, model or rc.model, timeout)
```

### Chain Validation
`run_subagent_chain()` validates chain steps at runtime with `SubagentChainStep.model_validate()`:
```python
for i, step_config in enumerate(step_list[:max_length]):
    if not isinstance(step_config, SubagentChainStep):
        step_config = SubagentChainStep.model_validate(step_config)
```

### Middleware Application
When applying middleware to tool functions, create a new ToolDefinition object:
```python
tools[i] = ToolDefinition(
    name=tool.name,
    description=tool.description,
    parameters=tool.parameters,
    required=tool.required,
    fn=wrapped_fn,  # New wrapped function
)
```

### SSRF Protection Import
Adapters should import from `utils/url.py`, not `services/url.py`:
```python
from utils.url import validate_url_safe, UnsafeURLError
```

### Session Hijacking Protection
The `require_auth` decorator in `routes/admin/__init__.py` implements IP and User-Agent binding for session security.

## Quality Gates
Each pipeline stage has quality gates that can route articles to `review` for manual inspection even when the stage "succeeds":
- `select`: Low confidence (score OK but confidence="low") → `review`
- `research`: Degenerate research brief (fails `_is_degenerate_research()`) → `review`
- `write`: Degenerate draft (fails `_is_degenerate_write()`) → `review`
- `edit`: Validation failure → `review`

See `architecture/tasks.md` for full documentation.

## Testing Notes

Before starting new work, check if tests were already failing:
```bash
git stash
.venv/bin/python -m pytest tests/ -x -q
git stash pop
```

When testing subagent functions that use `_build_context_tools()` or `_build_search_tools()`:
```python
with patch("services.subagent.tools.extensions") as mock_ext:
    mock_ext.db.session.get.return_value = mock_article
    result = tool.fn(article_id=123)
```